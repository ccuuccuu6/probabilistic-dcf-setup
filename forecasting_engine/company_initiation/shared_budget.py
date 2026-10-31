"""Durable cumulative construction costs, including unresolved request reserves.

Each terminal build owns an allowance shared by all of its stages and explicit
continuations. A shared ownership index prevents charging a paid request twice. Every
POST has one durable reservation; an actual charge replaces that reservation.
An explicit authorized reset opens a new allowance period without deleting costs.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from decimal import Decimal
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
from time import monotonic, sleep
from threading import get_ident
import unicodedata
from uuid import uuid4

from company_initiation.shared_ai import AIError, OpenAIProvider, aggregate_usage, response_usage

_BUILD_SCOPE = ContextVar('company_construction_build_scope', default=None)


def current_build_scope(outputs=None, company=None):
    scope = _BUILD_SCOPE.get()
    if scope is None:return None
    if scope.get('owner_thread')!=get_ident():return None
    if outputs is not None and Path(outputs).resolve()!=scope['outputs']:return None
    if company is not None and company_key(company)!=scope['company_key']:return None
    return scope


def command_owns_company_lock(outputs, key):
    scope=current_build_scope(outputs)
    return bool(scope and scope['company_key']==key and scope.get('lock_owned'))


def record_in_build_scope(record):
    """Only selected-build work may supply implicit within-build continuations."""
    scope=current_build_scope()
    if scope is None:return True
    config=record.get('configuration',{});budget=record.get('budget',{})
    identity=config.get('budget_session_id') or budget.get('allowance_period_id') or budget.get('lineage_id')
    return company_key(config.get('company','unknown'))==scope['company_key'] and identity==scope.get('period_id')


def build_record_paths(outputs, pattern):
    """Avoid searching unrelated saved runs in a fresh or selected command."""
    scope=current_build_scope(outputs)
    if scope is None:return Path(outputs).glob(pattern)
    return [path/'record.json' for path in scope['directories']
            if (path/'record.json').is_file() and (path/'record.json').match(pattern)]


def register_build_directory(directory):
    scope=current_build_scope()
    if scope is not None:
        path=Path(directory).resolve()
        if path.parent!=scope['outputs']:raise ValueError('Build directory is outside its output root')
        if path not in scope['directories']:scope['directories'].append(path)


@contextmanager
def construction_command_budget(outputs, company, limit, *, previous=None):
    """A new command opens a budget; explicit continuation selects its old one.

    One OS company lock covers all stages. Nested stage locks in this context
    share ownership; other processes/threads cannot reset or branch this build.
    No provider call is made and no previous charge or reservation is deleted.
    """
    from .historic_construction.initiation import _initiation_lock
    outputs=Path(outputs).resolve()
    if not (previous is not None and limit is None) and (type(limit) not in (int,float) or not math.isfinite(limit) or not 0<limit<=20):
        raise ValueError('Run budget must be greater than zero and at most $20')
    with _initiation_lock(outputs,scope=company_key(company)):
        scope=dict(outputs=outputs,company_key=company_key(company),lock_owned=True,
                   fresh=previous is None,period_id=None,owner_thread=get_ident(),
                   directories=[Path(previous['directory']).resolve()] if previous else [])
        token=_BUILD_SCOPE.set(scope)
        try:
            path=ledger_path(outputs,company)
            old_limit=(json.loads(path.read_text(encoding='utf-8'))['limit_usd'] if path.exists()
                       else (previous or {}).get('budget',{}).get('limit_usd',limit))
            if old_limit is None:raise AIError('Saved run has no verifiable budget limit')
            ledger=BudgetLedger(path,company,old_limit)
            if previous is None:
                summary=_open_allowance(ledger,'New terminal construction run: independent budget authorized by the default-run policy',limit)
                scope['period_id']=summary['allowance_period_id']
            else:
                ledger.import_record(previous)
                saved=previous.get('budget',{})
                scope['period_id']=(previous.get('configuration',{}).get('budget_session_id')
                    or saved.get('allowance_period_id') or saved.get('lineage_id'))
                if not scope['period_id']:raise AIError('Saved run has no verifiable budget identity; explicit continuation cannot open a new budget')
                with ledger._transaction() as state:
                    summary=BudgetLedger._totals(state,scope['period_id'])
                if limit is not None and float(limit)!=summary['limit_usd']:
                    raise ValueError('Resume must keep the original run budget limit')
            scope['limit_usd']=summary['limit_usd']
            yield summary
        finally:
            _BUILD_SCOPE.reset(token)


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
    """Migrate legacy commitments once, then select the independent company cap."""
    outputs=Path(outputs)
    migrate_company_budgets(outputs)
    return outputs / ("construction_company_budget_"+company_key(company)+".json")


def reset_company_allowance(outputs, company, *, reason, limit=20.):
    """Open an explicitly authorized allowance period, retaining all prior costs.

    This administrative operation is never called by construction or resume.
    Existing run locks prevent resetting a company while a build is active.
    """
    from company_initiation.historic_construction.initiation import _initiation_lock
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('An explicit authorization reason is required to reset an allowance')
    if isinstance(limit, bool) or not isinstance(limit, (int, float)) or not math.isfinite(limit) or not 0 < limit <= 20:
        raise ValueError('New company allowance must be greater than zero and at most $20')
    outputs = Path(outputs)
    with _initiation_lock(outputs), _initiation_lock(outputs, scope=company_key(company)):
        path = ledger_path(outputs, company)
        # Opening the existing limit avoids an unrelated authorized_limit event.
        previous_limit = json.loads(path.read_text(encoding='utf-8'))['limit_usd'] if path.exists() else limit
        ledger = BudgetLedger(path, company, previous_limit)
        return _open_allowance(ledger,reason,limit)


def _open_allowance(ledger, reason, limit):
    """Retire the default period while keeping it available for explicit resume."""
    with ledger._transaction() as state:
        now = ledger._now()
        previous = state.get('allowance_period') or dict(id=state['lineage_id'], started_at=None,
            reason='Original cumulative allowance before the first explicit reset')
        for request in state['requests'].values():
            request.setdefault('allowance_period_id', ledger._request_period(state, request))
        old_totals = ledger._totals(state)
        closed = dict(previous, closed_at=now, limit_usd=state['limit_usd'],
            request_ids=sorted(cid for cid, request in state['requests'].items()
                               if request['allowance_period_id'] == previous['id']),
            totals_at_close={k: v for k, v in old_totals.items()
                             if k not in ('lifetime', 'allowance_period_id', 'allowance_started_at', 'closed_allowance_periods')})
        state.setdefault('closed_allowance_periods', []).append(closed)
        state['allowance_period'] = dict(id=uuid4().hex, started_at=now, reason=reason.strip())
        state['limit_usd'] = float(limit)
        state['events'].append(dict(action='authorized_allowance_reset', time=now, reason=reason.strip(),
            previous_period_id=previous['id'], allowance_period_id=state['allowance_period']['id'],
            previous_totals=copy.deepcopy(closed['totals_at_close']), limit_usd=float(limit),
            policy='New spending allowance only; previous charges and unresolved reservations remain in lifetime accounting.'))
        return ledger._totals(state)


def _write_atomic(path, state):
    temp=path.with_name(path.name+'.tmp')
    with temp.open('w',encoding='utf-8') as output:
        json.dump(state,output,ensure_ascii=False,allow_nan=False,indent=2)
        output.flush();os.fsync(output.fileno())
    for attempt in range(6):
        try:os.replace(temp,path);break
        except PermissionError as exc:
            if os.name!='nt' or getattr(exc,'winerror',None) not in (5,32,33) or attempt==5:raise
            sleep(.1*2**attempt)


def _registry_path(outputs):
    return Path(outputs)/'construction_request_ownership.json'


def _registry(outputs):
    path=_registry_path(outputs)
    state=json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(version=1,companies={},requests={},legacy_sources={})
    if state.get('version')!=1 or any(not isinstance(state.get(k),dict) for k in ('companies','requests','legacy_sources')):
        raise AIError('Unrecognized or damaged company budget ownership index')
    return state


def _request_owner(request, ledger, record_cache):
    """Use original request/run attribution, never the next company's allowance."""
    explicit=request.get('company');origin=None;run=request.get('source_run')
    evidence=[]
    if run:
        path=Path(run)/'record.json'
        if path not in record_cache:
            if not path.is_file():raise AIError('Budget attribution needs the saved originating run: '+str(path))
            record_cache[path]=json.loads(path.read_text(encoding='utf-8'))
        record=record_cache[path]
        matches=list(record.get('calls',[]))+([record['pending_call']] if record.get('pending_call') else [])
        matches=[c for c in matches if c.get('call_id')==request['call_id']]
        if not matches or any(c.get('signature')!=request.get('signature') for c in matches):
            raise AIError('Originating run does not verify the budget request identity')
        origin=record.get('configuration',{}).get('company')
        evidence.append(dict(kind='originating_run',path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    if explicit and origin and company_key(explicit)!=company_key(origin):
        raise AIError('Conflicting company attribution between saved request and originating run')
    owner=explicit or origin
    if owner is None:
        if len(ledger.get('companies',{ledger['company_key']:ledger['company']}))!=1:
            raise AIError('Shared legacy request has no evidenced company attribution')
        owner=ledger['company'];evidence.append(dict(kind='sole_legacy_company',company=owner))
    key=company_key(owner)
    if request.get('company_key',key)!=key:raise AIError('Saved company attribution key disagrees with its name')
    evidence.append(dict(kind='saved_request_company' if explicit else 'derived_original_owner',company=owner))
    return owner,evidence


def _merge_request(requests, request):
    key=request['call_id'];old=requests.get(key)
    if old:
        if old.get('signature')!=request.get('signature') or old.get('company_key')!=request.get('company_key'):
            raise AIError('Migrated request ID has conflicting identity or company attribution')
        if old['status']=='settled' and request['status']=='settled':
            if old.get('usage_hash')!=request.get('usage_hash') or _money(old['actual_cost_usd'])!=_money(request['actual_cost_usd']):
                raise AIError('Conflicting usage for an already-settled request')
            return
        if old['status']=='settled':return
        if request['status']!='settled':
            if _money(request['reservation_usd'])>_money(old['reservation_usd']):
                old['reservation_usd']=request['reservation_usd'];old['allowance']=copy.deepcopy(request['allowance'])
            return
    requests[key]=copy.deepcopy(request)
    if old and 'allowance_period_id' in old:
        requests[key]['allowance_period_id'] = old['allowance_period_id']


def _register_state(index, path, state):
    key=state['company_key'];name=path.name
    previous=index['companies'].get(key)
    if previous and previous['ledger']!=name:raise AIError('Company budget already has a different active ledger')
    index['companies'][key]=dict(company=state['company'],ledger=name,lineage_id=state['lineage_id'])
    registered={cid for cid,r in index['requests'].items() if r['company_key']==key}
    if registered-set(state['requests']):raise AIError('Company ledger lost a previously registered paid request')
    for cid,request in state['requests'].items():
        if request.get('company_key')!=key:raise AIError('Company ledger contains another company charge')
        saved=index['requests'].get(cid)
        owner=dict(company_key=key,company=state['company'],ledger=name,signature=request.get('signature'))
        if saved and saved!=owner:raise AIError('Request ID has conflicting global company attribution or identity')
        index['requests'][cid]=owner


def company_budget_migration_plan(outputs):
    """Read-only plan: preserve legacy bytes and attribute every commitment once."""
    outputs=Path(outputs);index=_registry(outputs);states={};cache={};origins={}
    for path in sorted(outputs.glob('construction_company_budget_*.json')):
        state=json.loads(path.read_text(encoding='utf-8'))
        if state.get('version')!=2 or state.get('scope')!='company_continuation':raise AIError('Invalid company budget ledger')
        states[state['company_key']]=(path,state)
    for path in sorted(outputs.glob('construction_budget_*.json')):
        raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        if path.name in index['legacy_sources']:
            if index['legacy_sources'][path.name]['sha256']!=sha:raise AIError('Preserved legacy budget changed after migration')
            continue
        legacy=json.loads(raw)
        if legacy.get('version')!=1 or not isinstance(legacy.get('requests'),dict):raise AIError('Unrecognized legacy budget ledger')
        allocations=[]
        for cid,old in legacy['requests'].items():
            if old.get('call_id')!=cid:raise AIError('Legacy request dictionary identity mismatch')
            owner,evidence=_request_owner(old,legacy,cache);key=company_key(owner)
            if key not in states:
                lineage=legacy['lineage_id'] if key==legacy['company_key'] else _hash([legacy['lineage_id'],key])[:32]
                target=outputs/('construction_company_budget_'+key+'.json')
                states[key]=(target,dict(version=2,scope='company_continuation',company=owner,company_key=key,
                    lineage_id=lineage,limit_usd=legacy['limit_usd'],requests={},imported_runs=[],events=[],shared_request_references=[],migration_sources=[]))
            state=states[key][1]
            request=copy.deepcopy(old);request.update(company=owner,company_key=key)
            _merge_request(state['requests'],request)
            allocations.append(dict(call_id=cid,company=owner,company_key=key,status=request['status'],evidence=evidence))
            if path.name not in state.setdefault('migration_sources',[]):state['migration_sources'].append(path.name)
        index['legacy_sources'][path.name]=dict(sha256=sha,lineage_id=legacy['lineage_id'],allocations=allocations,
            policy='Separate company caps; source ledger retained unchanged; original request ownership preserved.')
        origins[path.name]=sha
    for path,state in states.values():_register_state(index,path,state)
    for key,info in index['companies'].items():
        if key not in states and not (outputs/info['ledger']).is_file():raise AIError('Registered company budget is missing')
    return dict(index=index,ledgers={str(path):state for path,state in states.values()},new_legacy_sources=origins,
        totals={key:BudgetLedger._totals(state) for key,(path,state) in states.items()})


def migrate_company_budgets(outputs):
    """Commit a checked plan under the global ownership lock; restart safely."""
    outputs=Path(outputs);outputs.mkdir(parents=True,exist_ok=True)
    with _lock(_registry_path(outputs)):
        plan=company_budget_migration_plan(outputs)
        # Write all wallets before the completion index. If interrupted, the next
        # plan merges identical requests and cannot erase or duplicate a charge.
        for name,state in plan['ledgers'].items():
            path=Path(name)
            if not path.exists() or json.loads(path.read_text(encoding='utf-8'))!=state:_write_atomic(path,state)
        index_path=_registry_path(outputs)
        if not index_path.exists() or _registry(outputs)!=plan['index']:_write_atomic(index_path,plan['index'])
        return plan


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
def _lock(path, *, timeout=10.):
    """Serialize short ledger/index transactions, with bounded contention waiting.

    Independent companies share the ownership index only while local accounting
    is read and committed. Waiting never releases an existing reservation or
    bypasses the company cap; no provider call is made while this lock is held.
    """
    if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not math.isfinite(timeout) or not 0<=timeout<=30:
        raise ValueError('Budget lock timeout must be between zero and thirty seconds')
    with path.with_suffix(path.suffix + ".lock").open("a+b") as handle:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        deadline=monotonic()+timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES,errno.EAGAIN,errno.EDEADLK):raise
                remaining=deadline-monotonic()
                if remaining<=0:
                    raise AIError(f'Cumulative budget is locked by another process after {timeout:g}s: {path.name}') from None
                sleep(min(.05,remaining))
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
        scope=current_build_scope(self.path.parent,company)
        self.period_id=scope.get('period_id') if scope else None
        if not 0 < self.limit <= 20 or not math.isfinite(self.limit):
            raise ValueError("Cumulative company budget must be greater than zero and at most $20")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as state:
            if self.period_id and self.period_id!=(state.get('allowance_period') or {}).get('id'):
                selected=self._totals(state,self.period_id)
                if selected['limit_usd']!=self.limit:raise ValueError('Resume must keep the original run budget limit')
            elif state["limit_usd"] != self.limit:
                state["events"].append(dict(action="authorized_limit", previous=state["limit_usd"],
                                           limit_usd=self.limit, time=self._now()))
                state["limit_usd"] = self.limit

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    @contextmanager
    def _transaction(self):
        with _lock(_registry_path(self.path.parent)), _lock(self.path):
            index=_registry(self.path.parent)
            peers={self.path.parent/item['ledger'] for item in index['companies'].values()}
            peers.update(self.path.parent.glob('construction_company_budget_*.json'))
            for path in peers-{self.path}:
                if not path.exists():raise AIError('Registered company budget is missing')
                peer=json.loads(path.read_text(encoding='utf-8'))
                _register_state(index,path,peer)
            if self.path.exists():
                state = json.loads(self.path.read_text(encoding="utf-8"))
                if state.get("version") != 2 or state.get('scope')!='company_continuation' or not isinstance(state.get("requests"), dict):
                    raise AIError("Legacy budgets must be migrated through ledger_path before spending")
                if state.get('company_key')!=company_key(self.company):raise AIError('Company budget identity does not match the requested company')
            else:
                state = dict(version=2, scope='company_continuation',company=self.company, company_key=company_key(self.company),
                    lineage_id=uuid4().hex, limit_usd=self.limit, requests={}, imported_runs=[], events=[],shared_request_references=[])
            _register_state(index,self.path,state)
            yield state
            _register_state(index,self.path,state)
            state["updated_at"] = self._now()
            _write_atomic(self.path,state)
            _write_atomic(_registry_path(self.path.parent),index)

    @staticmethod
    def _request_period(state, request):
        """Retain original ownership, including late imports of pre-reset calls."""
        active = state.get('allowance_period')
        if active is None:
            return state['lineage_id']
        saved = request.get('allowance_period_id')
        if saved is not None:
            valid = {active['id']} | {period['id'] for period in state.get('closed_allowance_periods', [])}
            if saved not in valid:
                raise AIError('Request references an unknown allowance period')
            return saved
        # A previously unseen saved call may be found on a later resume. Its
        # original dispatch timestamp, not its import time, determines ownership.
        try:
            started = datetime.fromisoformat(request['reserved_at'])
            if started.tzinfo is None:
                raise ValueError('Missing timezone')
        except (KeyError, TypeError, ValueError):
            raise AIError('Cannot assign an imported request to an allowance period without its original dispatch timestamp') from None
        for period in state.get('closed_allowance_periods', []):
            if started <= datetime.fromisoformat(period['closed_at']):
                return period['id']
        return active['id']

    @staticmethod
    def _request_totals(requests, *, limit=None):
        settled, reserved, confirmed = Decimal(0), Decimal(0), Decimal(0)
        unresolved = []
        for key, request in requests.items():
            if request["status"] == "settled":
                settled += _money(request["actual_cost_usd"])
                if request.get('charge_status')=='confirmed':confirmed+=_money(request['actual_cost_usd'])
            else:
                reserved += _money(request["reservation_usd"])
                unresolved.append(key)
        result = dict(known_cost_usd=float(settled), unresolved_reservations_usd=float(reserved),
            confirmed_charges_usd=float(confirmed),incurred_estimates_usd=float(settled-confirmed),
            committed_usd=float(settled + reserved),
            settled_requests=len(requests) - len(unresolved),
            unresolved_requests=unresolved, total_requests=len(requests),
            actual_cost_complete=not unresolved)
        if limit is not None:
            result['remaining_usd'] = float(Decimal(str(limit)) - settled - reserved)
        return result

    @staticmethod
    def _totals(state, period_id=None):
        requests = state['requests']
        active = state.get('allowance_period')
        selected=active;limit=state['limit_usd']
        if period_id is not None and (not active or period_id!=active['id']):
            if active is None and period_id==state['lineage_id']:selected=None
            else:
                selected=next((item for item in state.get('closed_allowance_periods',[]) if item['id']==period_id),None)
                if selected is None:raise AIError('Saved run references an unknown budget period')
                limit=selected['limit_usd']
        if active:
            requests = {cid: request for cid, request in requests.items()
                         if BudgetLedger._request_period(state, request) == selected['id']}
        totals = BudgetLedger._request_totals(requests, limit=limit)
        totals.update(lineage_id=state['lineage_id'], limit_usd=limit)
        if selected:
            totals.update(allowance_period_id=selected['id'], allowance_started_at=selected['started_at'],
                closed_allowance_periods=len(state.get('closed_allowance_periods', [])),
                lifetime=BudgetLedger._request_totals(state['requests']))
        return totals

    def summary(self):
        with self._transaction() as state:
            return self._totals(state,self.period_id)

    @staticmethod
    def _call_id(entry):
        result = entry.get("call_id")
        if not isinstance(result, str) or not result:
            raise AIError("A stable call_id is required; unknown requests cannot be discarded")
        return result

    @staticmethod
    def _saved_request(entry, run, company):
        result=dict(call_id=entry["call_id"], stage=entry.get("stage"), model=entry.get("model"),
            company=company, company_key=company_key(company),
            signature=entry.get("signature"), source_run=str(run) if run else None,
            client_request_id=entry.get("client_request_id") or
                (entry.get("response") or {}).get("_transport", {}).get("client_request_id"),
            provider_response_id=(entry.get("response") or {}).get("id"),
            reserved_at=entry.get("started_at"), allowance=copy.deepcopy(entry["allowance"]),
            reservation_usd=float(_money(entry["allowance"].get("estimated_cost_usd"))), status="reserved")
        if entry.get('allowance_period_id'):result['allowance_period_id']=entry['allowance_period_id']
        return result

    def reserve(self, entry, run=None):
        key = self._call_id(entry)
        request = self._saved_request(entry, run, self.company)
        if entry["allowance"].get("transport_attempts", 1) != 1 or entry["allowance"].get("sdk_retries", 0) != 0:
            raise AIError("Each potentially billable transport attempt needs a separate reservation")
        with self._transaction() as state:
            if key in _registry(self.path.parent)['requests']:
                raise AIError("Request ID already reserved; do not dispatch a second potentially billable attempt")
            if _money(request["reservation_usd"]) > Decimal(str(self._totals(state,self.period_id)["remaining_usd"])):
                raise AIError("Next request plus known charges and unresolved reservations exceeds cumulative budget")
            if state.get('allowance_period'):
                request['allowance_period_id'] = self.period_id or state['allowance_period']['id']
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
            charge_status='incurred_estimate',pricing_basis='Returned provider usage priced using the saved dated rates; not an invoice confirmation',
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
        source_company = configuration.get("company", "")
        source_company_key = company_key(source_company)
        if source_company_key!=company_key(self.company):
            raise AIError('Cannot import another company record into this company allowance')
        entries = list(record.get("calls", []))
        pending = record.get("pending_call")
        if pending and pending.get("call_id") not in {e.get("call_id") for e in entries}:
            entries.append(pending)
        # Deduplicate before interpreting a child run's settings. Inherited
        # requests may have different output limits, models or pricing metadata.
        # Their already-durable original reservation remains authoritative.
        with self._transaction() as state:
            existing = copy.deepcopy(state["requests"])
            owners=copy.deepcopy(_registry(self.path.parent)['requests'])
        prepared = []
        shared=[]
        for original in entries:
            entry = copy.deepcopy(original)
            key = self._call_id(entry)
            usage = entry.get("usage", {})
            if key in owners and owners[key]['company_key']!=source_company_key:
                if owners[key]['signature']!=entry.get('signature'):raise AIError('Shared request ID has conflicting identity')
                shared.append(dict(call_id=key,owner_company=owners[key]['company'],owner_company_key=owners[key]['company_key'],
                    signature=entry.get('signature'),referencing_run=record.get('directory'),policy='Paid once by its original company; reused evidence does not transfer the charge'))
                continue
            if key in existing:
                if existing[key].get("signature") != entry.get("signature"):
                    raise AIError("Migrated request ID has conflicting identity")
                if existing[key].get("company_key", source_company_key) != source_company_key:
                    raise AIError("Migrated request ID has conflicting company attribution")
                entry["allowance"] = copy.deepcopy(existing[key]["allowance"])
            elif not aggregate_usage([usage])["cost_is_complete"]:
                entry["allowance"] = reconstruct_allowance(entry, configuration["provider"])
            elif not entry.get("allowance"):
                entry["allowance"] = dict(estimated_cost_usd=usage["estimated_cost_usd"],
                    method="Already settled historical charge; no new dispatch")
            prepared.append(entry)
        with self._transaction() as state:
            for reference in shared:
                if reference not in state.setdefault('shared_request_references',[]):state['shared_request_references'].append(reference)
            for entry in prepared:
                key = entry["call_id"]
                if key not in state["requests"]:
                    state["requests"][key] = self._saved_request(entry, record.get("directory"), source_company)
                    if state.get('allowance_period'):
                        state['requests'][key]['allowance_period_id'] = self._request_period(state, state['requests'][key])
                elif state["requests"][key].get("signature") != entry.get("signature"):
                    raise AIError("Migrated request ID has conflicting identity")
                self._settle(state, key, entry.get("usage", {}), entry.get("response"), self._now())
            run = record.get("directory")
            if run and run not in state["imported_runs"]:
                state["imported_runs"].append(run)
                state["events"].append(dict(action="import_run", run=run, calls=len(prepared), time=self._now()))
            return self._totals(state,self.period_id)

    def recover(self, provider):
        """GET known Response IDs only; never recreates a lost POST."""
        with self._transaction() as state:
            candidates = [(key, copy.deepcopy(value)) for key, value in state["requests"].items()
                          if value["status"] != "settled" and (not self.period_id or self._request_period(state,value)==self.period_id)]
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
