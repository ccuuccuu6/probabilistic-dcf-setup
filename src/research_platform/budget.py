"""Durable cumulative construction costs, including unresolved request reserves.

The ledger belongs to a company attempt, not a source folder, model or code
version. It never edits the run's original requests, responses or usage. Every
POST has one durable reservation; an actual charge replaces that reservation.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
from time import sleep
import unicodedata
from uuid import uuid4

from .ai import AIError, OpenAIProvider, aggregate_usage, response_usage


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def company_key(company):
    """Stable for accents/case/punctuation, independent of archive and years."""
    normalized = unicodedata.normalize("NFKD", company).casefold()
    normalized = " ".join(re.findall(r"[a-z0-9]+", "".join(
        c for c in normalized if not unicodedata.combining(c))))
    if not normalized:
        raise ValueError("A company identity is required for a cumulative budget")
    return hashlib.sha256(normalized.encode()).hexdigest()[:24]


def ledger_path(outputs, company):
    return Path(outputs) / ("construction_budget_" + company_key(company) + ".json")


def _money(value):
    if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
        raise AIError("Missing or invalid conservative request reservation")
    return Decimal(str(value))


def reconstruct_allowance(entry, metadata):
    """Re-price an old local request with its saved prices and output ceiling.

    The saved byte/framing bound is retained even if a newer request serializer
    is smaller. The complete saved request is independently serialized again;
    the greater bound is used. No credential or provider request is needed.
    """
    saved = entry.get("allowance") or {}
    request = entry.get("request") or {}
    if metadata.get("provider") not in ("openai_responses", "scripted_fixture_no_network"):
        raise AIError("Cannot reconstruct an unknown request for this provider")
    if not all(k in request for k in ("instructions", "payload", "schema", "model", "effort", "stage")):
        raise AIError("Unknown request lacks its saved payload or routing configuration")
    if metadata.get("service_tier", "default") != "default":
        raise AIError("Cannot conservatively reconstruct an unpriced service tier")
    if metadata.get("sdk_retries", 0) != 0 or metadata.get("transport_attempts_per_call", 1) != 1:
        raise AIError("Legacy retries cannot be assumed free or bounded")
    # A continuation's configuration describes its NEW calls. The reservation
    # saved on the individual inherited call preserves that call's actual limit.
    ceiling = saved.get("max_output_tokens", metadata.get("max_output_tokens"))
    if type(ceiling) is not int or ceiling <= 0:
        raise AIError("Legacy request has a missing or invalid per-call output limit")
    saved_pricing = saved.get("pricing") or metadata.get("pricing")
    provider = OpenAIProvider(api_key="offline-reservation-reconstruction",
        models=dict.fromkeys(("researcher", "extractor", "reviewer"), request["model"]),
        reasoning_efforts=dict.fromkeys(("researcher", "extractor", "reviewer"), request["effort"]),
        stage_models={request["stage"]: request["model"]},
        stage_efforts={request["stage"]: request["effort"]},
        max_output_tokens=ceiling, pricing=json.loads(json.dumps(saved_pricing)) if saved_pricing else None)
    computed = provider.estimate_request_cost(role="researcher", instructions=request["instructions"],
        payload=dict(request["payload"], stage=request["stage"]), schema=request["schema"], web=False)
    input_bound = max(computed["estimated_input_tokens"], saved.get("estimated_input_tokens", 0))
    pricing = saved_pricing or provider.metadata()["pricing"]
    rates = pricing["rates"].get(request["model"])
    if not rates or len(rates) != 4:
        raise AIError("Saved model has no dated pricing for reservation reconstruction")
    input_rate, output_rate = max(rates[:3]), rates[3]
    if input_bound > 272000:
        input_rate *= 2
        output_rate *= 1.5
    amount = (Decimal(input_bound) * Decimal(str(input_rate)) +
              Decimal(ceiling) * Decimal(str(output_rate))) / Decimal(1000000)
    # Never reduce an earlier conservative allowance during migration.
    if saved.get("estimated_cost_usd") is not None:
        amount = max(amount, _money(saved["estimated_cost_usd"]))
    return dict(computed, estimated_cost_usd=float(amount), estimated_input_tokens=input_bound,
        input_rate_per_million=input_rate, output_rate_per_million=output_rate,
        pricing_tier="long_context" if input_bound > 272000 else "short_context",
        reconstruction="Saved payload, model, per-call output limit, standard prices, no tools, one transport attempt; maximum of saved/current byte bound",
        original_allowance=copy.deepcopy(saved), actual_charge_known=False)


@contextmanager
def _lock(path):
    """A second local lock also protects callers outside the construction command."""
    with path.with_suffix(path.suffix + ".lock").open("a+b") as handle:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise AIError("Cumulative budget is locked by another process") from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class BudgetLedger:
    """Settlements are idempotent; unresolved reservations remain payable.

    Reserve immediately before dispatch and settle only from returned provider
    usage. Updating a run, source archive, year range or code cannot erase costs.
    """
    def __init__(self, path, company, limit=20.):
        self.path, self.company, self.limit = Path(path), company, float(limit)
        if not 0 < self.limit <= 20 or not math.isfinite(self.limit):
            raise ValueError("Cumulative application budget must be greater than zero and at most $20")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as state:
            if state["company_key"] != company_key(company):
                raise AIError("Budget belongs to another company")
            if state["limit_usd"] != self.limit:
                state["events"].append(dict(action="authorized_limit", previous=state["limit_usd"],
                                           limit_usd=self.limit, time=self._now()))
                state["limit_usd"] = self.limit

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    @contextmanager
    def _transaction(self):
        with _lock(self.path):
            if self.path.exists():
                state = json.loads(self.path.read_text(encoding="utf-8"))
                if state.get("version") != 1 or not isinstance(state.get("requests"), dict):
                    raise AIError("Unrecognized or damaged cumulative budget ledger")
            else:
                state = dict(version=1, company=self.company, company_key=company_key(self.company),
                    lineage_id=uuid4().hex, limit_usd=self.limit, requests={}, imported_runs=[], events=[])
            yield state
            state["updated_at"] = self._now()
            temp = self.path.with_name(self.path.name + ".tmp")
            with temp.open("w", encoding="utf-8") as output:
                json.dump(state, output, ensure_ascii=False, allow_nan=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            for attempt in range(6):
                try:
                    os.replace(temp, self.path)
                    break
                except PermissionError as exc:
                    if os.name != "nt" or getattr(exc, "winerror", None) not in (5, 32, 33) or attempt == 5:
                        raise
                    sleep(.1 * 2 ** attempt)

    @staticmethod
    def _totals(state):
        settled, reserved = Decimal(0), Decimal(0)
        unresolved = []
        for key, request in state["requests"].items():
            if request["status"] == "settled":
                settled += _money(request["actual_cost_usd"])
            else:
                reserved += _money(request["reservation_usd"])
                unresolved.append(key)
        return dict(lineage_id=state["lineage_id"], limit_usd=state["limit_usd"],
            known_cost_usd=float(settled), unresolved_reservations_usd=float(reserved),
            committed_usd=float(settled + reserved),
            remaining_usd=float(Decimal(str(state["limit_usd"])) - settled - reserved),
            settled_requests=len(state["requests"]) - len(unresolved),
            unresolved_requests=unresolved, total_requests=len(state["requests"]),
            actual_cost_complete=not unresolved)

    def summary(self):
        with self._transaction() as state:
            return self._totals(state)

    @staticmethod
    def _call_id(entry):
        result = entry.get("call_id")
        if not isinstance(result, str) or not result:
            raise AIError("A stable call_id is required; unknown requests cannot be discarded")
        return result

    @staticmethod
    def _saved_request(entry, run):
        return dict(call_id=entry["call_id"], stage=entry.get("stage"), model=entry.get("model"),
            signature=entry.get("signature"), source_run=str(run) if run else None,
            client_request_id=entry.get("client_request_id") or
                (entry.get("response") or {}).get("_transport", {}).get("client_request_id"),
            provider_response_id=(entry.get("response") or {}).get("id"),
            reserved_at=entry.get("started_at"), allowance=copy.deepcopy(entry["allowance"]),
            reservation_usd=float(_money(entry["allowance"].get("estimated_cost_usd"))), status="reserved")

    def reserve(self, entry, run=None):
        key = self._call_id(entry)
        request = self._saved_request(entry, run)
        if entry["allowance"].get("transport_attempts", 1) != 1 or entry["allowance"].get("sdk_retries", 0) != 0:
            raise AIError("Each potentially billable transport attempt needs a separate reservation")
        with self._transaction() as state:
            if key in state["requests"]:
                raise AIError("Request ID already reserved; do not dispatch a second potentially billable attempt")
            if _money(request["reservation_usd"]) > Decimal(str(self._totals(state)["remaining_usd"])):
                raise AIError("Next request plus known charges and unresolved reservations exceeds cumulative budget")
            state["requests"][key] = request
            state["events"].append(dict(action="reserve", call_id=key, amount=request["reservation_usd"], time=self._now()))
        return request

    @staticmethod
    def _settle(state, key, usage, response, now):
        request = state["requests"][key]
        cost = aggregate_usage([usage])
        if not cost["cost_is_complete"]:
            if request["status"] == "settled":
                # Importing an older timeout after its real response was recovered
                # cannot restore the reservation or erase the known charge.
                return True
            request["status"] = "unresolved"
            request["unknown_usage"] = copy.deepcopy(usage)
            request["provider_response_id"] = (response or {}).get("id") or request.get("provider_response_id")
            request["client_request_id"] = (response or {}).get("_transport", {}).get("client_request_id") or request.get("client_request_id")
            return False
        amount = float(_money(usage["estimated_cost_usd"]))
        if request["status"] == "settled":
            if request["usage_hash"] != _hash(usage):
                raise AIError("Conflicting usage for an already-settled request")
            return True
        request.update(status="settled", actual_cost_usd=amount, usage=copy.deepcopy(usage),
            usage_hash=_hash(usage), settled_at=now,
            provider_response_id=(response or {}).get("id") or request.get("provider_response_id"))
        state["events"].append(dict(action="settle", call_id=key, actual_cost_usd=amount, time=now))
        return True

    def settle(self, call_id, usage, response=None):
        with self._transaction() as state:
            if call_id not in state["requests"]:
                raise AIError("Cannot settle an unreserved request")
            return self._settle(state, call_id, usage, response, self._now())

    def import_record(self, record):
        """Import a preserved run once; inherited call IDs are deduplicated."""
        configuration = record.get("configuration", {})
        if company_key(configuration.get("company", "")) != company_key(self.company):
            raise AIError("Cannot migrate another company's charges into this attempt")
        entries = list(record.get("calls", []))
        pending = record.get("pending_call")
        if pending and pending.get("call_id") not in {e.get("call_id") for e in entries}:
            entries.append(pending)
        # Deduplicate before interpreting a child run's settings. Inherited
        # requests may have different output limits, models or pricing metadata.
        # Their already-durable original reservation remains authoritative.
        with self._transaction() as state:
            existing = copy.deepcopy(state["requests"])
        prepared = []
        for original in entries:
            entry = copy.deepcopy(original)
            key = self._call_id(entry)
            usage = entry.get("usage", {})
            if key in existing:
                if existing[key].get("signature") != entry.get("signature"):
                    raise AIError("Migrated request ID has conflicting identity")
                entry["allowance"] = copy.deepcopy(existing[key]["allowance"])
            elif not aggregate_usage([usage])["cost_is_complete"]:
                entry["allowance"] = reconstruct_allowance(entry, configuration["provider"])
            elif not entry.get("allowance"):
                entry["allowance"] = dict(estimated_cost_usd=usage["estimated_cost_usd"],
                    method="Already settled historical charge; no new dispatch")
            prepared.append(entry)
        with self._transaction() as state:
            for entry in prepared:
                key = entry["call_id"]
                if key not in state["requests"]:
                    state["requests"][key] = self._saved_request(entry, record.get("directory"))
                elif state["requests"][key].get("signature") != entry.get("signature"):
                    raise AIError("Migrated request ID has conflicting identity")
                self._settle(state, key, entry.get("usage", {}), entry.get("response"), self._now())
            run = record.get("directory")
            if run and run not in state["imported_runs"]:
                state["imported_runs"].append(run)
                state["events"].append(dict(action="import_run", run=run, calls=len(prepared), time=self._now()))
            return self._totals(state)

    def recover(self, provider):
        """GET known Response IDs only; never recreates a lost POST."""
        with self._transaction() as state:
            candidates = [(key, copy.deepcopy(value)) for key, value in state["requests"].items()
                          if value["status"] != "settled"]
        results = []
        for key, request in candidates:
            response_id = request.get("provider_response_id")
            if not isinstance(response_id, str) or not response_id.startswith("resp_"):
                results.append(dict(call_id=key, recovered=False,
                    reason="No saved provider Response ID; client request IDs do not support result retrieval"))
                continue
            try:
                response = provider.retrieve_response(response_id)
                usage = response_usage(response, request["model"], request["allowance"].get("pricing"))
                # Save response and settlement in one durable transaction.
                with self._transaction() as state:
                    state["requests"][key]["recovered_response"] = response
                    settled = self._settle(state, key, usage, response, self._now())
                results.append(dict(call_id=key, recovered=True, usage_settled=settled,
                                    response_status=response.get("status")))
            except AIError as exc:
                results.append(dict(call_id=key, recovered=False, reason=str(exc)))
        with self._transaction() as state:
            state["events"].append(dict(action="recovery_check", results=results, time=self._now()))
        return results
