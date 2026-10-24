"""Credential-free checks of real reservation, migration and recovery boundaries."""
import copy
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch, Mock

from research_platform.ai import AIError, OpenAIProvider, response_usage
from research_platform.budget import BudgetLedger, company_key, ledger_path, reconstruct_allowance


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
        self.assertEqual(ledger_path("outputs", "Nestle"), ledger_path("outputs", "NESTLE"))
        with self.assertRaises(ValueError):
            BudgetLedger(self.path, "Company", 20.01)


class ProviderRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAIProvider(api_key="SYNTHETIC-TEST-KEY")

    def test_preassigned_identity_survives_single_timeout_without_sdk_retry(self):
        self.provider.next_client_request_id = "saved-before-dispatch"
        with patch("research_platform.ai.urlopen", side_effect=socket.timeout()) as network:
            with self.assertRaises(AIError):
                self.provider.complete(role="reviewer", instructions="fixture", payload={}, schema=SCHEMA)
        self.assertEqual(network.call_count, 1)
        self.assertEqual(self.provider.last_response["_transport"]["client_request_id"], "saved-before-dispatch")
        self.assertEqual(self.provider.last_response["_transport"]["sdk_retries"], 0)
        self.assertIsNone(self.provider.next_client_request_id)

    def test_retrieve_requires_provider_response_id_and_uses_only_get(self):
        with patch("research_platform.ai.urlopen") as network:
            with self.assertRaisesRegex(AIError, "saved provider resp_"):
                self.provider.retrieve_response("2aaabb4a-ab48-4513-b0ea-1bea204fb9b4")
            network.assert_not_called()
        stream = io.BytesIO(json.dumps(response()).encode())
        with patch("research_platform.ai.urlopen", return_value=stream) as network:
            result = self.provider.retrieve_response("resp_fixture")
        self.assertEqual(result["id"], "resp_fixture")
        self.assertEqual(network.call_args.args[0].method, "GET")
        self.assertEqual(network.call_count, 1)


if __name__ == "__main__":
    unittest.main()
