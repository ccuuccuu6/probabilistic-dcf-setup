"""Small AI boundary; credentials and model choices are supplied by the operator.

Set OPENAI_API_KEY, RESEARCH_MODEL, EXTRACTION_MODEL and REVIEW_MODEL in the
environment or an explicitly selected local settings file before a live run.
No models or credentials are silently selected.
Alternative providers implement AIProvider without changing the research workflow.
"""

from __future__ import annotations

import errno
from http.client import HTTPException, IncompleteRead
import json
import math
import os
from pathlib import Path
import re
import socket
import ssl
from time import monotonic
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4


ROLE_SETTINGS = {
    "researcher": "RESEARCH_MODEL",
    "extractor": "EXTRACTION_MODEL",
    "reviewer": "REVIEW_MODEL",
}

PRICING_DATE = "2026-10-10"
PRICING_SOURCE = "https://developers.openai.com/api/docs/pricing"
# Standard USD per million tokens: ordinary input, cache read, cache write, output.
# Verified against the pricing, model and prompt-caching documentation on this date.
_STANDARD_RATES = {
    "gpt-6.1-sol": (2.0, 0.10, 2.50, 10.0),
    "gpt-6-luna": (0.10, 0.01, 0.125, 0.50),
    "gpt-6-astra": (10.0, 1.0, 12.50, 50.0),
}
_TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_tokens",
                 "output_tokens", "reasoning_tokens", "total_tokens")


class AIError(RuntimeError):
    """A provider failed; the workflow must retain evidence and stop or revise."""


def _local_settings(path: Path | None) -> dict[str, str]:
    """Read four literal assignments without shell execution or interpolation."""
    if path is None:
        return {}
    try:
        content = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError):
        raise AIError("The local API settings file could not be read as UTF-8.") from None
    allowed = {"OPENAI_API_KEY", *ROLE_SETTINGS.values()}
    settings: dict[str, str] = {}
    for line_number, line in enumerate(content.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Z_][A-Z0-9_]*)\s*=\s*(.*)", line)
        if match is None or "\x00" in line:
            raise AIError(f"Malformed local API setting on line {line_number}.")
        name, value = match.groups()
        if name not in allowed:
            raise AIError(f"Unrecognized local API setting on line {line_number}.")
        if name in settings:
            raise AIError(f"Duplicate local API setting on line {line_number}.")
        value = value.strip()
        if value[:1] in {"'", '"'}:
            quote = value[0]
            if len(value) < 2 or value[-1] != quote or quote in value[1:-1]:
                raise AIError(f"Malformed local API setting on line {line_number}.")
            value = value[1:-1]
        elif "'" in value or '"' in value:
            raise AIError(f"Malformed local API setting on line {line_number}.")
        settings[name] = value
    return settings


def _token_count(value: Any) -> bool:
    return type(value) is int and value >= 0


def _model_rates(model: str) -> tuple[float, float, float, float] | None:
    if not isinstance(model, str):
        return None
    return next((rates for base, rates in _STANDARD_RATES.items()
                 if re.fullmatch(re.escape(base) + r"(?:-\d{4}-\d{2}-\d{2})?", model)), None)


def has_known_pricing(model: str) -> bool:
    """Whether the dated standard-price table recognizes this model identifier."""
    return _model_rates(model) is not None


def response_usage(response: dict | None, model: str) -> dict:
    """Normalize reported usage and estimate standard pricing, never an invoice.

    Cache reads/writes are subsets of input tokens; reasoning is already included
    in output tokens. Search content is already in input usage. Only search
    actions incur the web tool fee; opening/finding pages does not add that fee.
    Missing usage, unknown models or unrecognized pricing details stay unknown.
    """
    response = response if isinstance(response, dict) else {}
    actual_model = response.get("model")
    actual_model = actual_model if isinstance(actual_model, str) and actual_model else model
    actual_model = actual_model if isinstance(actual_model, str) else "unknown"
    result = {"model": actual_model, **dict.fromkeys(_TOKEN_FIELDS),
              "web_search_calls": 0, "web_tool_calls": 0, "reported": False,
              "estimated_cost_usd": None, "pricing_date": PRICING_DATE,
              "pricing_source": PRICING_SOURCE}
    output = response.get("output", [])
    tool_pricing_known = isinstance(output, list)
    for item in output if isinstance(output, list) else []:
        if not isinstance(item, dict):
            tool_pricing_known = False
            continue
        if item.get("type") != "web_search_call":
            continue
        result["web_tool_calls"] += 1
        action = item.get("action")
        action_type = action.get("type") if isinstance(action, dict) else None
        if action_type == "search":
            result["web_search_calls"] += 1
        elif action_type not in ("open_page", "find_in_page"):
            tool_pricing_known = False
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return result
    input_details = usage.get("input_tokens_details", {})
    output_details = usage.get("output_tokens_details", {})
    if not isinstance(input_details, dict) or not isinstance(output_details, dict):
        return result
    counts = {"input_tokens": usage.get("input_tokens"),
              "cached_input_tokens": input_details.get("cached_tokens", 0),
              "cache_write_tokens": input_details.get("cache_write_tokens", 0),
              "output_tokens": usage.get("output_tokens"),
              "reasoning_tokens": output_details.get("reasoning_tokens", 0)}
    if not all(_token_count(value) for value in counts.values()):
        return result
    total = counts["input_tokens"] + counts["output_tokens"]
    counts["total_tokens"] = usage.get("total_tokens", total)
    if (not _token_count(counts["total_tokens"]) or counts["total_tokens"] != total
            or counts["cached_input_tokens"] + counts["cache_write_tokens"] > counts["input_tokens"]
            or counts["reasoning_tokens"] > counts["output_tokens"]):
        return result
    result.update(counts)
    result["reported"] = True
    rates = _model_rates(actual_model)
    if rates is None or not tool_pricing_known or response.get("service_tier", "default") != "default":
        return result
    input_rate, cache_rate, write_rate, output_rate = rates
    if counts["input_tokens"] > 272000:
        input_rate *= 2
        cache_rate *= 2
        write_rate *= 2
        output_rate *= 1.5
    ordinary_input = counts["input_tokens"] - counts["cached_input_tokens"] - counts["cache_write_tokens"]
    try:
        cost = (ordinary_input * input_rate + counts["cached_input_tokens"] * cache_rate
                + counts["cache_write_tokens"] * write_rate + counts["output_tokens"] * output_rate) / 1_000_000
        cost += result["web_search_calls"] * 0.01
        if math.isfinite(cost):
            result["estimated_cost_usd"] = round(cost, 10)
    except OverflowError:
        pass
    return result


def aggregate_usage(entries: list[dict]) -> dict:
    """Sum reported subtotals by model and stage, including unsuccessful calls.

    Missing usage is never inferred from another request. Token sums contain only
    reported counts; completeness flags distinguish those subtotals from a full
    bill. Reasoning and cache counters are subsets, not additional token usage.
    """
    def new_totals() -> dict:
        return {"calls": 0, "reported_calls": 0, "missing_usage": 0,
                "missing_pricing": 0, "priced_calls": 0,
                **dict.fromkeys(_TOKEN_FIELDS, 0), "web_search_calls": 0,
                "web_tool_calls": 0, "estimated_cost_usd": 0.0}

    summary = {**new_totals(), "pricing_date": PRICING_DATE,
               "pricing_source": PRICING_SOURCE, "by_model": {}, "by_stage": {}}
    for entry in entries:
        usage = entry.get("usage", entry) if isinstance(entry, dict) else {}
        usage = usage if isinstance(usage, dict) else {}
        model = usage.get("model", "unknown")
        model = model if isinstance(model, str) and model else "unknown"
        stage = entry.get("stage") if isinstance(entry, dict) else None
        stage = stage if isinstance(stage, str) and stage else "unspecified"
        model_group = summary["by_model"].setdefault(model, new_totals())
        stage_group = summary["by_stage"].setdefault(stage, new_totals())
        reported = usage.get("reported") is True and all(
            _token_count(usage.get(field)) for field in _TOKEN_FIELDS)
        if reported:
            reported = (usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]
                        and usage["reasoning_tokens"] <= usage["output_tokens"]
                        and usage["cached_input_tokens"] + usage["cache_write_tokens"]
                        <= usage["input_tokens"])
        cost = usage.get("estimated_cost_usd")
        priced = reported and type(cost) in {int, float} and math.isfinite(cost) and cost >= 0
        for target in (summary, model_group, stage_group):
            target["calls"] += 1
            for field in ("web_search_calls", "web_tool_calls"):
                if _token_count(usage.get(field)):
                    target[field] += usage[field]
            if reported:
                target["reported_calls"] += 1
                for field in _TOKEN_FIELDS:
                    target[field] += usage[field]
                if priced:
                    target["priced_calls"] += 1
                    target["estimated_cost_usd"] += cost
                else:
                    target["missing_pricing"] += 1
            else:
                target["missing_usage"] += 1
    for target in (summary, *summary["by_model"].values(), *summary["by_stage"].values()):
        target["usage_is_complete"] = not target["missing_usage"]
        target["cost_is_complete"] = not (target["missing_usage"] or target["missing_pricing"])
        target["estimated_cost_usd"] = (round(target["estimated_cost_usd"], 10)
            if target["priced_calls"] or not target["calls"] else None)
    return summary


def format_usage(summary: dict) -> str:
    """Readable reported totals and an explicitly qualified USD estimate."""
    cost = summary.get("estimated_cost_usd")
    estimate = f"${cost:.6f}" if isinstance(cost, (int, float)) else "unknown"
    gaps = summary.get("missing_usage", 0) + summary.get("missing_pricing", 0)
    qualifier = f" (incomplete; {gaps} call(s) unpriced)" if not summary.get("cost_is_complete") else ""
    if summary.get("calls", 0) and not summary.get("reported_calls", 0):
        return (f"Token usage unavailable for {summary['calls']} call(s). "
                f"Estimated cost: {estimate} USD{qualifier}.")
    token_label = "Reported token subtotal" if summary.get("missing_usage", 0) else "Reported tokens"
    token_gaps = (f" ({summary['missing_usage']} call(s) missing usage)"
                  if summary.get("missing_usage", 0) else "")
    return (f"{token_label}: {summary.get('total_tokens', 0):,} total{token_gaps}; "
            f"{summary.get('input_tokens', 0):,} input "
            f"({summary.get('cached_input_tokens', 0):,} cached, "
            f"{summary.get('cache_write_tokens', 0):,} cache write), "
            f"{summary.get('output_tokens', 0):,} output "
            f"({summary.get('reasoning_tokens', 0):,} reasoning included); "
            f"{summary.get('web_search_calls', 0):,} web searches. "
            f"Estimated cost: {estimate} USD{qualifier}.")


def format_stage_usage(summary: dict) -> str:
    """Compact stage totals for comparing where a run used tokens and money."""
    lines = []
    for stage, totals in summary.get("by_stage", {}).items():
        calls = totals.get("calls", 0)
        if calls and not totals.get("reported_calls", 0):
            tokens = "tokens unavailable"
        else:
            tokens = (f"{totals.get('total_tokens', 0):,} total tokens "
                      f"({totals.get('input_tokens', 0):,} input, "
                      f"{totals.get('output_tokens', 0):,} output)")
            if totals.get("missing_usage", 0):
                tokens += f"; subtotal, {totals['missing_usage']} call(s) missing usage"
        cost = totals.get("estimated_cost_usd")
        estimate = f"${cost:.6f} USD" if isinstance(cost, (int, float)) else "unknown"
        if not totals.get("cost_is_complete", False):
            estimate += " (incomplete)"
        lines.append(f"{stage}: {calls} call(s); {tokens}; estimated cost {estimate}.")
    return "\n".join(lines)


class AIProvider(Protocol):
    """Inject a live provider or a scripted, explicitly synthetic test provider."""

    last_response: dict[str, Any] | None

    def validate_configuration(self) -> None: ...

    def metadata(self) -> dict[str, Any]: ...

    def complete(
        self, *, role: str, instructions: str, payload: dict,
        schema: dict, web: bool = False,
    ) -> dict: ...


def _strict_json(text: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError("Non-finite JSON number")

    def unique_keys(pairs: list[tuple[str, Any]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Non-finite JSON number")
        return number

    return json.loads(text, parse_constant=reject_constant, parse_float=finite_float,
                      object_pairs_hook=unique_keys)


def _provider_error_code(error: HTTPError) -> str | None:
    """Expose only known machine codes, never an error body's credential echo."""
    try:
        data = _strict_json(error.read(65537).decode("utf-8"))
    except (OSError, HTTPException, ValueError, UnicodeError, AttributeError):
        return None
    detail = data.get("error") if isinstance(data, dict) else None
    code = detail.get("code") if isinstance(detail, dict) else None
    allowed = ("invalid_api_key", "insufficient_quota", "model_not_found",
               "permission_denied", "rate_limit_exceeded", "billing_hard_limit_reached",
               "invalid_request_error", "invalid_value", "unsupported_value",
               "context_length_exceeded", "account_deactivated")
    return code if isinstance(code, str) and code in allowed else None


def _transport_failure(error: Exception) -> dict:
    """Retain diagnostic categories/codes, never exception text or partial bodies."""
    cause = error.reason if isinstance(error, URLError) and isinstance(error.reason, Exception) else error
    if isinstance(cause, ssl.SSLCertVerificationError):
        kind = "tls_certificate_error"
    elif isinstance(cause, ssl.SSLError):
        kind = "tls_error"
    elif (isinstance(cause, TimeoutError) or getattr(cause, "errno", None) == errno.ETIMEDOUT
          or getattr(cause, "winerror", None) == 10060):
        kind = "timeout"
    elif isinstance(cause, socket.gaierror):
        kind = "dns_error"
    elif isinstance(cause, ConnectionError):
        kind = "connection_error"
    elif isinstance(cause, IncompleteRead):
        kind = "interrupted_response"
    elif isinstance(cause, HTTPException):
        kind = "protocol_error"
    else:
        kind = "network_error"
    detail = {"failure_kind": kind}
    for name in ("errno", "winerror"):
        value = getattr(cause, name, None)
        if type(value) is int:
            detail[name] = value
    return detail


class OpenAIProvider:
    """Responses API adapter using the standard library; no automatic paid retries.

    Model slots may share an identifier, but agreement then does not provide
    independent evidence. The researcher model must support web search, and all
    selected models must support the supplied strict structured-output schemas.
    """

    def __init__(
        self, *, api_key: str = "", models: dict[str, str] | None = None,
        base_url: str = "https://api.openai.com/v1", timeout: float = 120,
        max_output_tokens: int = 16000,
    ) -> None:
        self._api_key = api_key.strip()
        self.models = dict(models or {})
        self.endpoint = base_url.rstrip("/") + "/responses"
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens
        self.last_response: dict[str, Any] | None = None

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> OpenAIProvider:
        """Read literal local settings, with process environment taking precedence.

        No implicit file search or environment mutation occurs. An explicitly
        empty process setting overrides a local value and fails validation.
        """
        settings = _local_settings(env_file)
        for name in ("OPENAI_API_KEY", *ROLE_SETTINGS.values()):
            if name in os.environ:
                settings[name] = os.environ[name]
        return cls(
            api_key=settings.get("OPENAI_API_KEY", ""),
            models={role: settings.get(name, "").strip()
                    for role, name in ROLE_SETTINGS.items()},
        )

    def validate_configuration(self) -> None:
        missing = ([] if self._api_key else ["OPENAI_API_KEY"])
        missing += [name for role, name in ROLE_SETTINGS.items()
                    if not isinstance(self.models.get(role), str)
                    or not self.models[role].strip()]
        if missing:
            raise AIError("Configure these environment variables before a live run: "
                          + ", ".join(missing))
        address = urlsplit(self.endpoint)
        if (address.scheme != "https" or not address.hostname or address.username
                or address.password or address.query or address.fragment):
            raise AIError("The AI endpoint must be HTTPS without embedded credentials.")
        if self.timeout <= 0 or self.timeout > 300:
            raise AIError("The AI timeout must be greater than zero and at most 300 seconds.")
        if (type(self.max_output_tokens) is not int
                or not 1 <= self.max_output_tokens <= 32000):
            raise AIError("The output token limit must be an integer from 1 to 32000.")

    def metadata(self) -> dict[str, Any]:
        """Safe run provenance; API keys and authorization headers are excluded."""
        return {"provider": "openai_responses", "models": dict(self.models),
                "endpoint": self.endpoint,
                "max_output_tokens": self.max_output_tokens, "timeout": self.timeout,
                "service_tier": "default"}

    def complete(
        self, *, role: str, instructions: str, payload: dict,
        schema: dict, web: bool = False,
    ) -> dict:
        self.last_response = None
        self.validate_configuration()
        if role not in ROLE_SETTINGS:
            raise AIError("Unknown AI role; expected researcher, extractor or reviewer.")
        if not isinstance(payload, dict) or not isinstance(schema, dict):
            raise AIError("AI payload and response schema must be JSON objects.")
        body: dict[str, Any] = {
            "model": self.models[role], "store": False, "service_tier": "default",
            "instructions": instructions,
            "input": [{"role": "user", "content": [{"type": "input_text",
                       "text": json.dumps(payload, ensure_ascii=False, allow_nan=False)}]}],
            "text": {"format": {"type": "json_schema", "name": "research_result",
                                  "schema": schema, "strict": True}},
            "max_output_tokens": self.max_output_tokens,
        }
        if web:
            body["tools"] = [{"type": "web_search"}]
            body["tool_choice"] = "required"
            body["include"] = ["web_search_call.action.sources"]
        transport = {"client_request_id": str(uuid4()), "timeout_seconds": self.timeout}
        request = Request(
            self.endpoint, data=json.dumps(body, allow_nan=False).encode("utf-8"),
            headers={"Authorization": "Bearer " + self._api_key,
                     "Content-Type": "application/json",
                     "X-Client-Request-Id": transport["client_request_id"]}, method="POST",
        )
        started = monotonic()
        self.last_response = {"status": "transport_error", "_transport": transport}
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                self.last_response["status"] = "response_error"
                transport["failure_kind"] = "response_too_large"
                raise AIError("AI response exceeded the 16 MiB safety limit.")
            result = _strict_json(raw.decode("utf-8"))
        except HTTPError as exc:
            self.last_response["http_status"] = exc.code
            transport["failure_kind"] = "http_error"
            error_code = _provider_error_code(exc)
            if error_code is not None:
                self.last_response["error_code"] = error_code
            detail = f" ({error_code})" if error_code is not None else ""
            raise AIError(f"AI provider returned HTTP {exc.code}{detail}; no automatic retry.") from None
        except (URLError, OSError, HTTPException) as exc:
            transport.update(_transport_failure(exc))
            elapsed = monotonic() - started
            codes = ", ".join(f"{name}={transport[name]}" for name in ("errno", "winerror") if name in transport)
            detail = transport["failure_kind"].replace("_", " ") + (f"; {codes}" if codes else "")
            raise AIError(f"AI transport failure ({detail}) after {elapsed:.1f}s "
                          f"(configured timeout {self.timeout:g}s). Client request ID: "
                          f"{transport['client_request_id']}. Usage and charge are unknown; no automatic retry.") from None
        except (ValueError, UnicodeDecodeError):
            self.last_response["status"] = "response_error"
            transport["failure_kind"] = "invalid_json"
            raise AIError("AI provider returned an invalid JSON response.") from None
        finally:
            transport["elapsed_seconds"] = round(monotonic() - started, 6)
        if not isinstance(result, dict):
            self.last_response["status"] = "response_error"
            transport["failure_kind"] = "invalid_json"
            raise AIError("AI provider returned a non-object response.")
        result["_transport"] = transport
        self.last_response = result
        if result.get("status") != "completed":
            raise AIError("AI response was incomplete or failed; it cannot be accepted.")
        output = result.get("output")
        if not isinstance(output, list) or not all(isinstance(item, dict) for item in output):
            raise AIError("AI provider returned malformed output items.")
        if web and not any(item.get("type") == "web_search_call"
                           and item.get("status") == "completed" for item in output):
            raise AIError("Source discovery did not complete a web search.")
        parts = []
        for item in output:
            if item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list) or not all(isinstance(part, dict) for part in content):
                raise AIError("AI provider returned malformed message content.")
            for part in content:
                if part.get("type") == "refusal":
                    raise AIError("AI provider declined the request; no result was accepted.")
                if part.get("type") == "output_text":
                    parts.append(part.get("text", ""))
        if not parts or not all(isinstance(part, str) for part in parts):
            raise AIError("AI provider returned no structured text result.")
        try:
            data = _strict_json("\n".join(parts))
        except ValueError:
            raise AIError("AI output was not a valid strict JSON object.") from None
        if not isinstance(data, dict):
            raise AIError("AI output must be a JSON object.")
        return data
