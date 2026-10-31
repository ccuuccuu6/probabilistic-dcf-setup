"""Credential-free checks of real reservation, migration and recovery boundaries."""
import copy
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import socket
import tempfile
from threading import Event
from time import monotonic
import unittest
from unittest.mock import patch, Mock

from company_initiation.shared_ai import AIError, OpenAIProvider, response_usage
from company_initiation.shared_budget import (BudgetLedger, company_key, ledger_path, reconstruct_allowance,
    company_budget_migration_plan, reset_company_allowance, construction_command_budget, current_build_scope,
    build_record_paths, record_in_build_scope)


SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}},
          "required": ["ok"], "additionalProperties": False}


def response(tokens=100, identifier="resp_fixture"):
    return dict(id=identifier, status="completed", model="gpt-6-luna", service_tier="default",
        usage=dict(input_tokens=tokens, input_tokens_details=dict(cached_tokens=0, cache_write_tokens=0),
                   output_tokens=20, output_tokens_details=dict(reasoning_tokens=10), total_tokens=tokens + 20),
        output=[dict(type="message", content=[dict(type="output_text", text='{"ok":true}')])])


def entry(identifier="call-a", allowance=1.):
    return dict(call_id=identifier, signature="signature-" + identifier, model="gpt-6-luna",
        stage="construction_review", started_at="2026-10-23T00:00:00+00:00", client_request_id="client-" + identifier,
        request=dict(stage="construction_review", instructions="Check the source table.", payload={"table": "fixture"},
                     schema=SCHEMA, model="gpt-6-luna", effort="medium", attempt=0),
        allowance=dict(estimated_cost_usd=allowance, max_output_tokens=16000,
                       estimated_input_tokens=10000, transport_attempts=1, sdk_retries=0))


def legacy_fixture(outputs):
    """Preserved shared ledger with verifiable originating company run records."""
    outputs.mkdir(parents=True,exist_ok=True)
    state=dict(version=1,scope='application_continuation',company='First company',company_key=company_key('First company'),
        lineage_id='original-lineage',limit_usd=20.,requests={},imported_runs=[],events=[],
        companies={company_key(c):c for c in ('First company','Second company')})
    for owner,cid,reserve,charge in [('First company','first-known',4.,3.200947785),
            ('First company','first-unknown',.9238415,None),('Second company','second-known',1.,.03760855),
            ('Second company','second-unknown',1.25407475,None)]:
        call=entry(cid,reserve);run=outputs/('origin_'+cid);run.mkdir()
        call['usage']=response_usage(None,'gpt-6-luna') if charge is None else response_usage(response(identifier='resp_'+cid),'gpt-6-luna')
        if charge is not None:call['usage']['estimated_cost_usd']=charge
        (run/'record.json').write_text(json.dumps(dict(configuration={'company':owner},calls=[call],pending_call=None)),encoding='utf-8')
        state['requests'][cid]=BudgetLedger._saved_request(call,run,owner)
        BudgetLedger._settle(state,cid,call['usage'],None,'fixture')
    path=outputs/('construction_budget_'+company_key('First company')+'.json')
    path.write_text(json.dumps(state),encoding='utf-8')
    return path,state


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "budget.json"
        self.provider = OpenAIProvider(api_key="SYNTHETIC-TEST-KEY")
        self.ledger = BudgetLedger(self.path, "Company, TICKER, Exchange", 20.)

    def record(self, calls, **changes):
        config = dict(company="Company, TICKER, Exchange", provider=self.provider.metadata(),
                      years=[2025], sources="old-archive", code={"engine": "v1"})
        config.update(changes)
        return dict(configuration=config, calls=calls, directory="preserved-run", pending_call=None)

    def test_unknown_charge_keeps_reservation_but_allows_affordable_next_request(self):
        self.ledger.reserve(entry(allowance=3.))
        self.ledger.settle("call-a", response_usage(None, "gpt-6-luna"))
        self.ledger.reserve(entry("call-b", 16.))
        summary = self.ledger.summary()
        self.assertEqual(summary["known_cost_usd"], 0)
        self.assertEqual(summary["unresolved_reservations_usd"], 19)
        self.assertEqual(summary["remaining_usd"], 1)
        with self.assertRaisesRegex(AIError, "exceeds cumulative"):
            self.ledger.reserve(entry("call-c", 1.01))
        reopened = BudgetLedger(self.path, "Company, TICKER, Exchange", 20.)
        self.assertEqual(reopened.summary()["unresolved_reservations_usd"], 19)

    def test_settlement_replaces_reservation_exactly_once(self):
        self.ledger.reserve(entry(allowance=3.))
        actual = response_usage(response(), "gpt-6-luna")
        self.assertTrue(self.ledger.settle("call-a", actual, response()))
        self.assertTrue(self.ledger.settle("call-a", actual, response()))
        self.assertEqual(self.ledger.summary()["unresolved_reservations_usd"], 0)
        self.assertEqual(self.ledger.summary()["known_cost_usd"], actual["estimated_cost_usd"])
        with self.assertRaisesRegex(AIError, "Conflicting usage"):
            self.ledger.settle("call-a", response_usage(response(200), "gpt-6-luna"))
        # Earlier saved timeout records cannot undo a later settlement.
        self.ledger.settle("call-a", response_usage(None, "gpt-6-luna"))
        self.assertTrue(self.ledger.summary()["actual_cost_complete"])

    def test_duplicate_dispatch_and_unlogged_sdk_retries_are_rejected(self):
        self.ledger.reserve(entry())
        with self.assertRaisesRegex(AIError, "already reserved"):
            self.ledger.reserve(entry())
        retry = entry("retry")
        retry["allowance"]["sdk_retries"] = 2
        with self.assertRaisesRegex(AIError, "separate reservation"):
            self.ledger.reserve(retry)

    def test_source_year_code_migration_does_not_reset_or_duplicate_spending(self):
        call = entry()
        call.update(response=response(), usage=response_usage(response(), "gpt-6-luna"))
        first = self.ledger.import_record(self.record([call]))
        changed = self.record([call], years=[2016, 2025], sources="new-archive", code={"engine": "v2"})
        changed["directory"] = "migrated-run"
        second = self.ledger.import_record(changed)
        self.assertEqual(first, second)
        self.assertEqual(second["total_requests"], 1)
        self.assertEqual(len(json.loads(self.path.read_text())["imported_runs"]), 2)

    def test_existing_timeout_conservative_maximum(self):
        timed_out = entry(allowance=.89353075)
        timed_out["allowance"]["estimated_input_tokens"] = 3526123
        allowance = reconstruct_allowance(timed_out, self.provider.metadata())
        self.assertEqual(allowance["estimated_cost_usd"], .89353075)
        self.assertEqual(allowance["input_rate_per_million"], .25)
        self.assertEqual(allowance["output_rate_per_million"], .75)
        self.assertTrue(allowance["output_limit_includes_reasoning"])
        self.assertEqual(allowance["paid_tool_calls_max"], 0)

    def test_inherited_unknown_request_keeps_original_limit_and_reservation(self):
        timed_out = entry(allowance=.89353075)
        timed_out["allowance"]["estimated_input_tokens"] = 3526123
        original = self.record([timed_out])
        self.ledger.import_record(original)
        child = copy.deepcopy(original)
        child["directory"] = "child-with-smaller-requests"
        child["configuration"]["provider"]["max_output_tokens"] = 6000
        child["configuration"]["provider"]["pricing"]["rates"] = {}
        # Already recorded costs need no interpretation under new request settings.
        after = self.ledger.import_record(child)
        self.assertEqual(after["total_requests"], 1)
        self.assertEqual(after["unresolved_reservations_usd"], .89353075)
        saved = json.loads(self.path.read_text())["requests"]["call-a"]
        self.assertEqual(saved["allowance"]["max_output_tokens"], 16000)
        self.assertEqual(saved["reservation_usd"], .89353075)
        # When first importing a migrated record, the per-call limit wins too.
        metadata = self.provider.metadata()
        metadata["max_output_tokens"] = 6000
        allowance = reconstruct_allowance(timed_out, metadata)
        self.assertEqual(allowance["max_output_tokens"], 16000)
        self.assertEqual(allowance["estimated_cost_usd"], .89353075)

    def test_pending_call_is_imported_even_if_no_response_or_usage_was_saved(self):
        record = self.record([])
        record["pending_call"] = entry()
        summary = self.ledger.import_record(record)
        self.assertEqual(summary["total_requests"], 1)
        self.assertEqual(summary["unresolved_reservations_usd"], 1.)
        self.assertFalse(summary["actual_cost_complete"])

    def test_no_provider_id_means_no_invented_recovery(self):
        self.ledger.reserve(entry())
        provider = Mock()
        result = self.ledger.recover(provider)
        provider.retrieve_response.assert_not_called()
        self.assertFalse(result[0]["recovered"])
        self.assertEqual(self.ledger.summary()["unresolved_reservations_usd"], 1.)

    def test_recovered_response_is_durably_saved_and_settles_reservation(self):
        request = entry()
        request["response"] = {"id": "resp_fixture"}
        self.ledger.reserve(request)
        provider = Mock()
        provider.retrieve_response.return_value = response()
        results = self.ledger.recover(provider)
        self.assertTrue(results[0]["usage_settled"])
        state = json.loads(self.path.read_text())
        self.assertEqual(state["requests"]["call-a"]["recovered_response"]["id"], "resp_fixture")
        self.assertEqual(self.ledger.summary()["unresolved_reservations_usd"], 0)

    def test_actual_overshoot_is_saved_and_blocks_later_dispatch(self):
        self.ledger.reserve(entry(allowance=1.))
        usage = response_usage(response(), "gpt-6-luna")
        usage["estimated_cost_usd"] = 21.
        self.ledger.settle("call-a", usage)
        self.assertEqual(self.ledger.summary()["remaining_usd"], -1.)
        with self.assertRaises(AIError):
            self.ledger.reserve(entry("new", .01))

    def test_request_id_conflict_cannot_silently_replace_charge(self):
        call = entry()
        self.ledger.import_record(self.record([call]))
        changed = copy.deepcopy(call)
        changed["signature"] = "different-request"
        with self.assertRaisesRegex(AIError, "conflicting identity"):
            self.ledger.import_record(self.record([changed]))

    def test_stable_company_budget_and_hard_maximum(self):
        self.assertEqual(company_key("Nestlé S.A., NESN"), company_key("NESTLE S.A., nesn"))
        outputs=Path(self.temp.name)/'stable'
        self.assertEqual(ledger_path(outputs, "Nestle"), ledger_path(outputs, "NESTLE"))
        with self.assertRaises(ValueError):
            BudgetLedger(self.path, "Company", 20.01)

    def test_independent_companies_wait_for_shared_ownership_index_and_keep_separate_caps(self):
        from company_initiation.shared_budget import _lock, _registry_path
        outputs=Path(self.temp.name)/'concurrent';outputs.mkdir()
        started=[Event(),Event()]
        def reserve_company(index):
            company='Synthetic concurrent '+str(index);started[index].set()
            ledger=BudgetLedger(ledger_path(outputs,company),company)
            ledger.reserve(entry('concurrent-'+str(index),17.))
            with self.assertRaisesRegex(AIError,'exceeds cumulative'):
                ledger.reserve(entry('excess-'+str(index),4.))
            return ledger.summary()
        with ThreadPoolExecutor(max_workers=2) as pool:
            with _lock(_registry_path(outputs)):
                futures=[pool.submit(reserve_company,i) for i in range(2)]
                for event in started:self.assertTrue(event.wait(2))
                self.assertTrue(all(not result.done() for result in futures))
            results=[future.result(timeout=5) for future in futures]
        self.assertEqual([r['unresolved_reservations_usd'] for r in results],[17.,17.])
        index=json.loads(_registry_path(outputs).read_text(encoding='utf-8'))
        self.assertEqual(len(index['requests']),2)
        self.assertEqual(len({request['company_key'] for request in index['requests'].values()}),2)

    def test_budget_lock_timeout_is_bounded_without_replacing_existing_owner(self):
        from company_initiation.shared_budget import _lock, _registry_path
        registry=_registry_path(Path(self.temp.name));started=monotonic()
        with _lock(registry):
            with self.assertRaisesRegex(AIError,'after 0.1s'):
                with _lock(registry,timeout=.1):pass
        self.assertLess(monotonic()-started,2.)
        with _lock(registry,timeout=0):pass

    def test_shared_legacy_migration_preserves_each_company_commitments_and_original_bytes(self):
        outputs=Path(self.temp.name)/'outputs';legacy,state=legacy_fixture(outputs);original=legacy.read_bytes()
        plan=company_budget_migration_plan(outputs)
        self.assertEqual(legacy.read_bytes(),original)
        self.assertEqual(len(list(outputs.glob('construction_company_budget_*.json'))),0)
        first=BudgetLedger(ledger_path(outputs,'First company'),'First company')
        second=BudgetLedger(ledger_path(outputs,'Second company'),'Second company')
        third=BudgetLedger(ledger_path(outputs,'Third company'),'Third company')
        self.assertEqual(first.summary()['lineage_id'],'original-lineage')
        self.assertEqual(first.summary()['known_cost_usd'],3.200947785)
        self.assertEqual(first.summary()['unresolved_reservations_usd'],.9238415)
        self.assertEqual(second.summary()['known_cost_usd'],.03760855)
        self.assertEqual(second.summary()['unresolved_reservations_usd'],1.25407475)
        self.assertEqual(third.summary()['committed_usd'],0)
        self.assertEqual(first.summary()['confirmed_charges_usd'],0)
        self.assertEqual(first.summary()['incurred_estimates_usd'],3.200947785)
        first.reserve(entry('first-new',15.8))
        with self.assertRaisesRegex(AIError,'exceeds cumulative'):first.reserve(entry('first-too-much',.1))
        second.reserve(entry('second-new',18.7))
        third.reserve(entry('third-new',20))
        self.assertEqual(legacy.read_bytes(),original)
        before=second.summary();ledger_path(outputs,'Second company')
        self.assertEqual(second.summary(),before)
        self.assertEqual(len(plan['index']['requests']),4)

    def test_company_budget_rejects_foreign_record_and_counts_shared_paid_request_once(self):
        call=entry('other');call.update(response=response(),usage=response_usage(response(),'gpt-6-luna'))
        other=self.record([call],company='Another company')
        with self.assertRaisesRegex(AIError,'another company record'):self.ledger.import_record(other)
        self.ledger.import_record(self.record([call]))
        second=BudgetLedger(Path(self.temp.name)/'another-budget.json','Another company')
        self.assertEqual(second.import_record(other)['committed_usd'],0)
        self.assertEqual(second.import_record(other)['total_requests'],0)
        self.assertEqual(self.ledger.summary()['total_requests'],1)
        self.assertEqual(len(json.loads(second.path.read_text())['shared_request_references']),1)
        with self.assertRaisesRegex(AIError,'already reserved'):second.reserve(call)

    def test_legacy_attribution_conflict_blocks_without_writing_company_ledgers(self):
        outputs=Path(self.temp.name)/'conflict';legacy,state=legacy_fixture(outputs)
        state['requests']['second-known']['company']='First company'
        state['requests']['second-known']['company_key']=company_key('First company')
        legacy.write_text(json.dumps(state),encoding='utf-8');original=legacy.read_bytes()
        with self.assertRaisesRegex(AIError,'Conflicting company attribution'):ledger_path(outputs,'Third company')
        self.assertEqual(legacy.read_bytes(),original)
        self.assertFalse(list(outputs.glob('construction_company_budget_*.json')))

    def test_interrupted_migration_is_idempotent_and_never_releases_unknown_reserve(self):
        from company_initiation import shared_budget as budget
        outputs=Path(self.temp.name)/'interrupted';legacy,state=legacy_fixture(outputs)
        write=budget._write_atomic
        def interrupted(path,value):
            if path.name=='construction_request_ownership.json':raise OSError('simulated migration interruption')
            write(path,value)
        with patch.object(budget,'_write_atomic',side_effect=interrupted),self.assertRaises(OSError):ledger_path(outputs,'First company')
        first=BudgetLedger(ledger_path(outputs,'First company'),'First company')
        second=BudgetLedger(ledger_path(outputs,'Second company'),'Second company')
        self.assertEqual(first.summary()['total_requests']+second.summary()['total_requests'],4)
        self.assertEqual(first.summary()['unresolved_reservations_usd'],.9238415)
        self.assertEqual(second.summary()['unresolved_reservations_usd'],1.25407475)

    def test_missing_company_wallet_and_changed_legacy_cannot_reset_allowance(self):
        outputs=Path(self.temp.name)/'integrity';legacy,state=legacy_fixture(outputs)
        path=ledger_path(outputs,'First company');original=path.read_bytes();path.unlink()
        with self.assertRaisesRegex(AIError,'missing'):ledger_path(outputs,'First company')
        path.write_bytes(original);legacy.write_text(json.dumps(dict(state,limit_usd=19)),encoding='utf-8')
        with self.assertRaisesRegex(AIError,'legacy budget changed'):ledger_path(outputs,'First company')


class AllowanceResetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.outputs = Path(self.temp.name)
        self.company = 'Synthetic reset company'
        self.ledger = BudgetLedger(ledger_path(self.outputs, self.company), self.company)
        self.provider = OpenAIProvider(api_key='SYNTHETIC-TEST-KEY')

    def reset(self):
        return reset_company_allowance(self.outputs, self.company,
            reason='User explicitly authorized a fresh $20 allowance for this fixture')

    def record(self, calls):
        return dict(configuration=dict(company=self.company, provider=self.provider.metadata()),
            calls=calls, pending_call=None, directory='saved-fixture-run')

    def test_reset_retains_costs_unknowns_ownership_and_immutable_snapshot(self):
        self.ledger.reserve(entry('paid', 4.))
        paid = response_usage(response(), 'gpt-6-luna')
        self.ledger.settle('paid', paid)
        self.ledger.reserve(entry('unknown', 3.))
        self.ledger.settle('unknown', response_usage(None, 'gpt-6-luna'))
        before = json.loads(self.ledger.path.read_text())
        summary = self.reset()
        self.assertEqual(summary['known_cost_usd'], 0)
        self.assertEqual(summary['unresolved_reservations_usd'], 0)
        self.assertEqual(summary['remaining_usd'], 20)
        self.assertEqual(summary['lifetime']['known_cost_usd'], paid['estimated_cost_usd'])
        self.assertEqual(summary['lifetime']['unresolved_reservations_usd'], 3)
        after = json.loads(self.ledger.path.read_text())
        self.assertEqual(after['lineage_id'], before['lineage_id'])
        for cid, request in before['requests'].items():
            self.assertEqual({k: v for k, v in after['requests'][cid].items()
                              if k != 'allowance_period_id'}, request)
        self.assertEqual(after['closed_allowance_periods'][0]['request_ids'], ['paid', 'unknown'])
        closed = copy.deepcopy(after['closed_allowance_periods'])
        self.ledger.settle('unknown', paid)
        settled = self.ledger.summary()
        self.assertEqual(settled['remaining_usd'], 20)
        self.assertEqual(settled['lifetime']['unresolved_reservations_usd'], 0)
        self.assertEqual(json.loads(self.ledger.path.read_text())['closed_allowance_periods'], closed)
        self.assertEqual(len(json.loads((self.outputs / 'construction_request_ownership.json').read_text())['requests']), 2)

    def test_old_imports_do_not_recharge_new_period_or_erase_unknowns(self):
        old = entry('old', 3.)
        self.ledger.import_record(self.record([old]))
        self.reset()
        replay = self.ledger.import_record(self.record([old]))
        self.assertEqual(replay['committed_usd'], 0)
        self.assertEqual(replay['lifetime']['unresolved_reservations_usd'], 3.)
        # Previously unseen original calls are classified by dispatch time too.
        late = entry('late-old', 2.)
        imported = self.ledger.import_record(self.record([old, late]))
        self.assertEqual(imported['remaining_usd'], 20.)
        self.assertEqual(imported['lifetime']['unresolved_reservations_usd'], 5.)
        old['usage'] = response_usage(response(), 'gpt-6-luna')
        settled = self.ledger.import_record(self.record([old, late]))
        self.assertEqual(settled['committed_usd'], 0)
        self.assertEqual(settled['lifetime']['known_cost_usd'], old['usage']['estimated_cost_usd'])
        self.assertEqual(settled['lifetime']['unresolved_reservations_usd'], 2.)

    def test_new_dispatches_use_new_allowance_and_repeat_reset_is_explicit(self):
        first = self.reset()
        # Newly dispatched requests belong to the active period even if a clock
        # is old; only saved-record imports use original timestamp classification.
        self.ledger.reserve(entry('new', 19.))
        with self.assertRaisesRegex(AIError, 'exceeds cumulative'):
            self.ledger.reserve(entry('over', 1.01))
        reopened = BudgetLedger(self.ledger.path, self.company)
        self.assertEqual(reopened.summary()['remaining_usd'], 1.)
        actual = response_usage(response(), 'gpt-6-luna')
        reopened.settle('new', actual)
        self.assertEqual(reopened.summary()['known_cost_usd'], actual['estimated_cost_usd'])
        second = self.reset()
        self.assertNotEqual(first['allowance_period_id'], second['allowance_period_id'])
        self.assertEqual(second['closed_allowance_periods'], 2)
        self.assertEqual(second['remaining_usd'], 20.)
        self.assertEqual(second['lifetime']['known_cost_usd'], actual['estimated_cost_usd'])
        with self.assertRaisesRegex(AIError, 'already reserved'):
            reopened.reserve(entry('new', 1.))

    def test_reset_is_company_specific_and_preserves_legacy_migration(self):
        outputs = self.outputs / 'legacy'
        legacy, _ = legacy_fixture(outputs)
        original = legacy.read_bytes()
        first = BudgetLedger(ledger_path(outputs, 'First company'), 'First company')
        second = BudgetLedger(ledger_path(outputs, 'Second company'), 'Second company')
        second_before = second.summary()
        reset_company_allowance(outputs, 'First company', reason='Explicit test authorization')
        ledger_path(outputs, 'First company')
        self.assertEqual(first.summary()['remaining_usd'], 20.)
        self.assertEqual(first.summary()['lifetime']['total_requests'], 2)
        self.assertEqual(second.summary(), second_before)
        self.assertEqual(legacy.read_bytes(), original)

    def test_active_build_prevents_reset_and_failed_reset_changes_nothing(self):
        from company_initiation.historic_construction.initiation import _initiation_lock
        before = self.ledger.path.read_bytes()
        with _initiation_lock(self.outputs, scope=company_key(self.company)):
            with self.assertRaisesRegex(AIError, 'Another construction'):
                self.reset()
        self.assertEqual(self.ledger.path.read_bytes(), before)
        with _initiation_lock(self.outputs):
            with self.assertRaisesRegex(AIError, 'Another initiation'):
                self.reset()
        self.assertEqual(self.ledger.path.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'authorization reason'):
            reset_company_allowance(self.outputs, self.company, reason=' ')
        with self.assertRaises(ValueError):
            reset_company_allowance(self.outputs, self.company, reason='Explicit', limit=21)
        self.assertEqual(self.ledger.path.read_bytes(), before)

    def test_missing_import_dispatch_date_cannot_hide_unallocated_cost(self):
        self.reset()
        ambiguous = entry('ambiguous')
        ambiguous.pop('started_at')
        with self.assertRaisesRegex(AIError, 'original dispatch timestamp'):
            self.ledger.import_record(self.record([ambiguous]))
        self.assertEqual(self.ledger.summary()['lifetime']['total_requests'], 0)


class CommandBudgetTests(unittest.TestCase):
    """Fresh public commands and explicit continuations, without a provider call."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.outputs=Path(self.temp.name)/'outputs';self.company='SYNTHETIC independent builds'

    def ledger(self,limit=20):
        return BudgetLedger(ledger_path(self.outputs,self.company),self.company,limit)

    def journal(self,name,ledger):
        from company_initiation.shared_runtime import RunJournal
        directory=self.outputs/name;directory.mkdir()
        return RunJournal(directory,OpenAIProvider(api_key='SYNTHETIC-OFFLINE-KEY'),
            dict(company=self.company,limits=dict(usd=ledger.limit)),ledger=ledger)

    def test_fresh_budget_ignores_old_commitments_and_keeps_lifetime_evidence(self):
        with construction_command_budget(self.outputs,self.company,20) as first:
            ledger=self.ledger();ledger.reserve(entry('known',5))
            usage=response_usage(response(),'gpt-6-luna');usage['estimated_cost_usd']=4.
            ledger.settle('known',usage);ledger.reserve(entry('unknown',3))
            journal=self.journal('construct_first',ledger)
            first_record=copy.deepcopy(journal.state)
        with construction_command_budget(self.outputs,self.company,20) as second:
            self.assertNotEqual(first['allowance_period_id'],second['allowance_period_id'])
            self.assertEqual(second['remaining_usd'],20)
            self.assertEqual(second['total_requests'],0)
            self.assertEqual(second['lifetime']['known_cost_usd'],4)
            self.assertEqual(second['lifetime']['unresolved_reservations_usd'],3)
            self.assertEqual(list(build_record_paths(self.outputs,'construct_*/record.json')),[])
            self.assertFalse(record_in_build_scope(first_record))
            self.ledger().reserve(entry('second',2))
        self.assertEqual(self.ledger().summary()['remaining_usd'],18)
        self.assertIsNone(current_build_scope())

    def test_older_resume_uses_original_remaining_budget_after_a_newer_fresh_build(self):
        with construction_command_budget(self.outputs,self.company,10) as first:
            ledger=self.ledger(10);ledger.reserve(entry('old-unknown',7))
            original=self.journal('construct_first',ledger).state
        with construction_command_budget(self.outputs,self.company,20):
            self.ledger().reserve(entry('new-unknown',5))
        newest=self.ledger().summary()
        with construction_command_budget(self.outputs,self.company,None,previous=original) as resumed:
            self.assertEqual(resumed['allowance_period_id'],first['allowance_period_id'])
            self.assertEqual(resumed['remaining_usd'],3)
            self.assertEqual(resumed['limit_usd'],10)
            ledger=self.ledger(10)
            with self.assertRaisesRegex(AIError,'exceeds cumulative'):
                ledger.reserve(entry('too-much',3.01))
            saved=ledger.reserve(entry('continued',2))
            self.assertEqual(saved['allowance_period_id'],first['allowance_period_id'])
            self.assertEqual(ledger.summary()['remaining_usd'],1)
            self.assertEqual(list(build_record_paths(self.outputs,'construct_*/record.json')),
                             [Path(original['directory'])/'record.json'])
        after=self.ledger().summary()
        self.assertEqual(after['allowance_period_id'],newest['allowance_period_id'])
        self.assertEqual(after['remaining_usd'],newest['remaining_usd'])
        self.assertEqual(after['lifetime']['unresolved_reservations_usd'],14)
        with self.assertRaisesRegex(ValueError,'original run budget'):
            with construction_command_budget(self.outputs,self.company,20,previous=original):pass

    def test_stages_share_one_cap_and_only_current_build_records(self):
        with construction_command_budget(self.outputs,self.company,20) as first:
            history=self.ledger();history.reserve(entry('history',12))
            historic=self.journal('construct_research_first',history)
            forecast=self.ledger();self.assertEqual(forecast.summary()['remaining_usd'],8)
            forecast.reserve(entry('forecast',7))
            dcf=self.ledger()
            with self.assertRaisesRegex(AIError,'exceeds cumulative'):dcf.reserve(entry('dcf',2))
            dcf.reserve(entry('dcf',1))
            self.assertEqual(dcf.summary()['remaining_usd'],0)
            self.assertEqual(historic.state['configuration']['budget_session_id'],first['allowance_period_id'])
            self.assertTrue(record_in_build_scope(historic.state))
            self.assertEqual(list(build_record_paths(self.outputs,'construct_*/record.json')),
                             [historic.directory/'record.json'])

    def test_company_lock_is_shared_by_stages_but_blocks_other_threads(self):
        from company_initiation.historic_construction.initiation import _initiation_lock
        with construction_command_budget(self.outputs,self.company,20):
            with _initiation_lock(self.outputs,scope=company_key(self.company)):pass
            def competing_command():
                with construction_command_budget(self.outputs,self.company,20):pass
            with ThreadPoolExecutor(max_workers=1) as pool:
                with self.assertRaisesRegex(AIError,'Another construction'):
                    pool.submit(competing_command).result(timeout=10)

    def test_cli_default_fresh_and_explicit_resume_preserve_selected_budget(self):
        from company_initiation.__main__ import main,_run
        root=self.outputs.parent;records=[];calls=[]
        def dispatch(arguments):
            scope=current_build_scope(self.outputs,self.company)
            before=self.ledger(arguments.budget_usd).summary()
            calls.append((arguments.fresh,arguments.resume,before['remaining_usd'],arguments.years,arguments.as_of))
            ledger=self.ledger(arguments.budget_usd)
            ledger.reserve(entry('command-'+str(len(calls)),2))
            journal=self.journal('construct_command_'+str(len(calls)),ledger)
            journal.configuration.update(as_of='2026-10-01',years=[2024,2025])
            journal.save();records.append(copy.deepcopy(journal.state))
            return 0
        argv=['company_initiation','construct',self.company,'--sources','fixture']
        with patch('company_initiation.__main__.find_project_root',return_value=root), \
             patch('company_initiation.__main__._logged_construct',side_effect=_run), \
             patch('company_initiation.__main__._dispatch',side_effect=dispatch), \
             patch('company_initiation.shared_artifacts.verified_integrated_record',side_effect=lambda path,outputs:next(
                 record for record in records if Path(record['directory'])==Path(path))), \
             patch('builtins.print'),patch('company_initiation.shared_ai.urlopen',side_effect=AssertionError('No network')):
            for _ in range(2):
                with patch('sys.argv',argv):self.assertEqual(main(),0)
            with patch('sys.argv',argv+['--resume',records[0]['directory']]):self.assertEqual(main(),0)
        self.assertEqual([item[0] for item in calls],[True,True,False])
        self.assertEqual([item[2] for item in calls],[20,20,18])
        self.assertEqual(calls[-1][3:],([2024,2025],'2026-10-01'))
        self.assertEqual(records[0]['budget']['allowance_period_id'],records[2]['budget']['allowance_period_id'])
        self.assertNotEqual(records[0]['budget']['allowance_period_id'],records[1]['budget']['allowance_period_id'])
        self.assertEqual(self.ledger().summary()['remaining_usd'],18)

    def test_initiate_default_is_fresh_and_resume_flag_is_explicit(self):
        from company_initiation.__main__ import main,_run
        root=self.outputs.parent
        argv=['company_initiation','initiate',self.company,'--sources','fixture']
        with patch('company_initiation.__main__.find_project_root',return_value=root), \
             patch('company_initiation.__main__._dispatch',return_value=0) as dispatch:
            with patch('sys.argv',argv):self.assertEqual(main(),0)
            self.assertTrue(dispatch.call_args.args[0].fresh)
            saved=root/'outputs/initiate_saved';saved.mkdir(parents=True)
            request=dict(years=[2024],historical_years=None,start_year=None,max_cost_usd=8.)
            (saved/'record.json').write_text(json.dumps(dict(request=request)),encoding='utf-8')
            with patch('sys.argv',argv+['--resume',str(saved)]):self.assertEqual(main(),0)
            args=dispatch.call_args.args[0]
            self.assertFalse(args.fresh);self.assertEqual(args.budget_usd,8.)
            self.assertEqual(args.years,[2024])
        for command in ('construct','initiate'):
            with patch('sys.argv',['company_initiation',command,self.company,'--sources','fixture','--fresh','--resume','saved']), \
                 patch('sys.stderr',io.StringIO()),self.assertRaises(SystemExit):main()

    def test_initiate_can_resume_an_older_independent_run_but_not_branch_its_continuation(self):
        from company_initiation.historic_construction.initiation import _saved_run
        self.outputs.mkdir()
        request=dict(company_query=self.company,historical_years=None,years=[2024],forecast_years=5,start_year=None)
        def save(name,started,parent=None):
            path=self.outputs/name;path.mkdir()
            record=dict(request=request,started_at=started,parent_run=str(parent) if parent else None)
            (path/'record.json').write_text(json.dumps(record),encoding='utf-8');return path
        first=save('initiate_first','2026-10-01T00:00:00+00:00')
        save('initiate_second','2026-10-02T00:00:00+00:00')
        self.assertEqual(_saved_run(self.outputs,request,first,False)[0],first)
        self.assertEqual(_saved_run(self.outputs,request,None,True),(None,None))
        child=save('initiate_first_child','2026-10-03T00:00:00+00:00',first)
        with self.assertRaisesRegex(ValueError,'newer continuation'):_saved_run(self.outputs,request,first,False)
        self.assertEqual(_saved_run(self.outputs,request,child,False)[0],child)


class ProviderRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAIProvider(api_key="SYNTHETIC-TEST-KEY")

    def test_preassigned_identity_survives_single_timeout_without_sdk_retry(self):
        self.provider.next_client_request_id = "saved-before-dispatch"
        with patch("company_initiation.shared_ai.urlopen", side_effect=socket.timeout()) as network:
            with self.assertRaises(AIError):
                self.provider.complete(role="reviewer", instructions="fixture", payload={}, schema=SCHEMA)
        self.assertEqual(network.call_count, 1)
        self.assertEqual(self.provider.last_response["_transport"]["client_request_id"], "saved-before-dispatch")
        self.assertEqual(self.provider.last_response["_transport"]["sdk_retries"], 0)
        self.assertIsNone(self.provider.next_client_request_id)

    def test_retrieve_requires_provider_response_id_and_uses_only_get(self):
        with patch("company_initiation.shared_ai.urlopen") as network:
            with self.assertRaisesRegex(AIError, "saved provider resp_"):
                self.provider.retrieve_response("2aaabb4a-ab48-4513-b0ea-1bea204fb9b4")
            network.assert_not_called()
        stream = io.BytesIO(json.dumps(response()).encode())
        with patch("company_initiation.shared_ai.urlopen", return_value=stream) as network:
            result = self.provider.retrieve_response("resp_fixture")
        self.assertEqual(result["id"], "resp_fixture")
        self.assertEqual(network.call_args.args[0].method, "GET")
        self.assertEqual(network.call_count, 1)


if __name__ == "__main__":
    unittest.main()
