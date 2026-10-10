"""Financial parsing, arithmetic and reproducibility checks."""

import ast
import copy
import hashlib
from http.client import BadStatusLine, IncompleteRead
import io
import json
import os
import re
import socket
import ssl
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from uuid import UUID

from openpyxl import Workbook, load_workbook

from research_platform.project import find_project_root, read_json
from research_platform.__main__ import TerminalProgress
from research_platform.ai import AIError, OpenAIProvider, aggregate_usage, response_usage
from research_platform.evidence import SourceStore, download, parse_number
from research_platform.initiation import (REVIEW_TOPICS, SECTIONS, _rounding_bound,
                                          export_workbook, initiate_company, materialize_and_check)


PROJECT = Path(__file__).resolve().parents[1]


class HistoricalParsingTests(unittest.TestCase):
    def test_numbers_preserve_reported_sign_and_thousands(self):
        for value, expected in (
            (1234, 1234.0),
            (-1234.5, -1234.5),
            ("1 234", 1234.0),
            ("1\u00a0234", 1234.0),
            ("(1 234)", -1234.0),
            ("(3.51)", -3.51),
        ):
            with self.subTest(value=value):
                self.assertEqual(parse_number(value), expected)

    def test_only_explicit_reported_dashes_are_zero(self):
        for value in ("-", "\u2013", "\u2014", 0, "0"):
            with self.subTest(value=value):
                self.assertEqual(parse_number(value), 0.0)

    def test_missing_ambiguous_and_nonfinite_numbers_are_rejected(self):
        for value in (
            None, "", "   ", "not disclosed", "n/a", "1 2 3", True, False,
            float("nan"), float("inf"), float("-inf"), "NaN", "Infinity",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_number(value)

    def test_decimal_locale_is_explicit_and_percent_is_not_an_amount(self):
        self.assertEqual(parse_number("1.234,50", "comma_decimal"), 1234.5)
        self.assertEqual(parse_number("(1,234.50)", "dot_decimal"), -1234.5)
        self.assertEqual(parse_number("3,5%", "comma_decimal"), 0.035)
        self.assertEqual(parse_number("1,234", "dot_decimal"), 1234)
        self.assertEqual(parse_number("1,234", "comma_decimal"), 1.234)
        with self.assertRaises(ValueError):
            parse_number("1.234,50", "dot_decimal")


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.package = self.root / "src" / "research_platform"
        self.package.mkdir(parents=True)
        (self.package / "__init__.py").write_bytes(
            (PROJECT / "src" / "research_platform" / "__init__.py").read_bytes())
        (self.root / "pyproject.toml").write_bytes((PROJECT / "pyproject.toml").read_bytes())

    def tearDown(self):
        self.temporary.cleanup()

    def test_root_from_subdirectory_without_company_configs(self):
        self.assertFalse((self.root / "configs").exists())
        self.assertEqual(find_project_root(self.package), self.root)

    def test_unrelated_pyproject_is_not_a_project_root(self):
        (self.package / "__init__.py").unlink()
        with self.assertRaises(ValueError):
            find_project_root(self.root)

    def test_read_run_record(self):
        path = self.root / "record.json"
        path.write_text('{"status": "incomplete"}', encoding="utf-8")
        self.assertEqual(read_json(path), {"status": "incomplete"})

    def test_read_run_record_rejects_nonobjects(self):
        path = self.root / "record.json"
        for value in ("[]", "null", "42"):
            with self.subTest(value=value):
                path.write_text(value, encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_json(path)


class TerminalProgressTests(unittest.TestCase):
    class InteractiveStream(io.StringIO):
        def isatty(self):
            return True

    def test_timer_counts_up_while_request_is_still_running(self):
        stream = self.InteractiveStream()
        with TerminalProgress(stream).call_timer("Call 1: extract"):
            self.assertIn("waiting 00:00", stream.getvalue())

            def elapsed_ticks():
                return [int(minutes) * 60 + int(seconds)
                        for minutes, seconds in re.findall(r"waiting (\d+):(\d+)", stream.getvalue())]

            deadline = time.monotonic() + 3
            while max(elapsed_ticks()) < 1 and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertGreaterEqual(max(elapsed_ticks()), 1)
            self.assertGreaterEqual(len(elapsed_ticks()), 2)
            self.assertNotIn("completed", stream.getvalue())
        self.assertIn("completed after", stream.getvalue())
        self.assertTrue(stream.getvalue().endswith("s\n"))

    def test_failure_stops_timer_thread_and_reports_elapsed_time(self):
        stream = self.InteractiveStream()
        before = {thread.ident for thread in threading.enumerate()}
        with self.assertRaisesRegex(RuntimeError, "synthetic transport failure"):
            with TerminalProgress(stream).call_timer("Call 2: extract"):
                self.assertTrue(any(thread.name == "ai-call-timer" and thread.ident not in before
                                    for thread in threading.enumerate()))
                raise RuntimeError("synthetic transport failure")
        self.assertFalse(any(thread.name == "ai-call-timer" and thread.ident not in before
                             for thread in threading.enumerate()))
        self.assertIn("failed after", stream.getvalue())

    def test_redirected_output_has_one_completion_line_without_carriage_returns(self):
        stream = io.StringIO()
        with TerminalProgress(stream).call_timer("Call 3: model_review"):
            self.assertEqual(stream.getvalue(), "")
        self.assertNotIn("\r", stream.getvalue())
        self.assertEqual(len(stream.getvalue().splitlines()), 1)
        self.assertIn("completed after", stream.getvalue())


class SyntheticCompany:
    """Invented disclosures only; deliberately different layouts, no company map."""

    def __init__(self, variant=0):
        self.name = ("Fictional Hearth Appliances plc", "Fictional Meadow Diagnostics SA")[variant]
        self.currency = ("USD", "EUR")[variant]
        self.sheet = ("Statements", "Group accounts")[variant]
        self.reverse_columns = bool(variant)
        self.column_periods = ["2024", "2025"]
        self.source = {
            "id": "annual", "url": f"https://example.invalid/synthetic-{variant}.xlsx",
            "title": "SYNTHETIC TEST DISCLOSURE", "published_at": "2026-02-10",
            "reason": "Invented primary disclosure for an offline software test.",
            "kind": "annual_report",
        }
        # ID, section, accounting role, entity, two annual observations.
        specifications = [
            ("segment_a", "segments", "segment_revenue", "Alpha", (600, 650)),
            ("segment_b", "segments", "segment_revenue", "Beta", (400, 450)),
            ("profit_a", "segments", "segment_profit", "Alpha", (60, 70)),
            ("profit_b", "segments", "segment_profit", "Beta", (40, 50)),
            ("segment_group_profit", "income_statement", "segment_group_profit", "group", (100, 120)),
            ("revenue", "income_statement", "revenue", "group", (1000, 1100)),
            ("expenses", "income_statement", "other", "group", (-900, -980)),
            ("net_income", "income_statement", "net_income", "group", (100, 120)),
            ("assets", "balance_sheet", "total_assets", "group", (1000, 1200)),
            ("liabilities", "balance_sheet", "total_liabilities", "group", (600, 720)),
            ("equity", "balance_sheet", "total_equity", "group", (400, 480)),
            ("cash_close", "cash_flow", "cash_close", "group", (100, 130)),
            ("balance_sheet_cash", "balance_sheet", "balance_sheet_cash", "group", (100, 130)),
            ("inventory", "balance_sheet", "other", "group", (100, 110)),
            ("receivables", "balance_sheet", "other", "group", (120, 130)),
            ("payables", "balance_sheet", "other", "group", (-80, -90)),
            ("debt", "balance_sheet", "other", "group", (300, 350)),
            ("cash_open", "cash_flow", "cash_open", "group", (70, 100)),
            ("cash_change", "cash_flow", "cash_change", "group", (30, 30)),
            ("operating", "cash_flow", "operating_cash", "group", (60, 70)),
            ("investing", "cash_flow", "investing_cash", "group", (-20, -25)),
            ("financing", "cash_flow", "financing_cash", "group", (-10, -15)),
            ("working_capital", "working_capital", "working_capital", "group", (140, 150)),
            ("net_debt", "net_debt", "net_debt", "group", (200, 220)),
            ("share_capital", "equity", "other", "group", (200, 220)),
            ("minority_interest", "equity", "other", "group", (20, 25)),
            ("shares", "shares", "other", "group", (100, 100)),
        ]
        if variant:
            specifications.reverse()
        self.rows = []
        self.display_values = {}
        self.units = []
        for number, (row_id, section, role, entity, values) in enumerate(specifications, 3):
            ref = {"source_id": "annual", "unit_id": f"{self.sheet}!R{number}"}
            self.units.append(ref)
            self.display_values[row_id] = list(values)
            self.rows.append({
                "id": row_id, "section": section, "label": row_id.replace("_", " "),
                "entity": entity, "definition": "Synthetic disclosed " + row_id + "; reported sign retained.",
                "unit": "shares" if row_id == "shares" else self.currency,
                "scale": 1, "sign": 1, "role": role,
                "time_basis": ("opening_balance" if row_id == "cash_open" else
                               "closing_balance" if section in ("balance_sheet", "equity", "shares", "net_debt", "working_capital")
                               or row_id == "cash_close" else "flow"),
                "unavailable": [],
                "observations": [
                    {"period": str(year), "reference": dict(ref, number_index=(1 - index if variant else index),
                                                      number_format="dot_decimal")}
                    for index, year in enumerate((2024, 2025))
                ],
                "terms": [], "definition_refs": [
                    {"source_id": "annual", "unit_id": f"{self.sheet}!R1"},
                    {"source_id": "annual", "unit_id": f"{self.sheet}!R2"}, ref],
            })
        self.discovery = {
            "company": {"legal_name": self.name, "identifier": "SYNTHETIC-" + str(variant),
                        "exchange": "NONE", "country": ("US", "FR")[variant], "currency": self.currency},
            "periods": [{"id": str(year), "year": year, "kind": "annual", "start": f"{year}-01-01", "end": f"{year}-12-31"}
                        for year in (2024, 2025)],
            "period_coverage": [
                {"year": year, "slot": slot, "status": "not_disclosed",
                 "explanation": "Synthetic issuer publishes annual accounts only; no interim disclosure.",
                 "source_ids": ["annual"]}
                for year in (2024, 2025) for slot in ("Q1", "Q2", "Q3", "Q4", "H1", "H2", "9M")],
            "sources": [self.source], "notes": [], "blocking_issues": [],
        }
        relations = {
            "revenue": [("segment_a", 1), ("segment_b", 1)],
            "segment_group_profit": [("profit_a", 1), ("profit_b", 1)],
            "net_income": [("revenue", 1), ("expenses", 1)],
            "balance_sheet_cash": [("cash_close", 1)],
            "cash_change": [("operating", 1), ("investing", 1), ("financing", 1)],
            "working_capital": [("inventory", 1), ("receivables", 1), ("payables", 1)],
            "net_debt": [("debt", 1), ("cash_close", -1)],
        }
        self.candidate = {
            "reporting_basis": "Synthetic FY2025 disclosure with FY2024 comparatives; no restatement.",
            "rows": self.rows,
            "equations": [
                {"target": target, "terms": [{"row_id": row, "coefficient": coefficient}
                                            for row, coefficient in terms],
                 "explanation": "Synthetic disclosed composition of " + target}
                for target, terms in relations.items()
            ],
            "coverage": [{"section": section, "period": str(year), "status": "complete",
                          "explanation": "All material lines in this deliberately small synthetic disclosure.",
                          "references": [{"source_id": "annual", "unit_id": f"{self.sheet}!R1"}]}
                         for section in SECTIONS for year in (2024, 2025)],
            "cash_continuity": [{"period": "2025", "previous_period": "2024", "terms": [],
                                 "explanation": "The synthetic adjacent annual periods use the same cash definition.",
                                 "references": [{"source_id": "annual", "unit_id": f"{self.sheet}!R1"}]}],
            "gaps": [],
        }
        self.fetches = []

    def payload(self):
        book = Workbook()
        sheet = book.active
        sheet.title = self.sheet
        scope = ("annual accounts only, no interim disclosure" if len(self.column_periods) == 2 else
                 "full annual and H1 accounts; Q1 and nine-month sales-only releases; no standalone Q2, Q3, Q4 or H2")
        sheet.append(["SYNTHETIC: " + self.name + "; reporting currency " + self.currency
                      + "; units 1; " + scope + "; no further schedules."])
        headings = [("FY" + value if "-" not in value else value) for value in self.column_periods]
        sheet.append(["Reported line", *(list(reversed(headings)) if self.reverse_columns else headings)])
        for row in self.rows:
            values = self.display_values[row["id"]]
            sheet.append([row["label"], *(list(reversed(values)) if self.reverse_columns else values)])
        output = io.BytesIO()
        book.save(output)
        return output.getvalue()

    def fetch(self, url):
        if url != self.source["url"]:
            raise AssertionError("Unrecognized synthetic source URL")
        self.fetches.append(url)
        return self.payload(), url, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def include_interims(self):
        """Invented complete H1 accounts and sales-only Q1/9M disclosures."""
        self.reverse_columns = False
        interim_periods = [
            {"id": "2025-Q1", "year": 2025, "kind": "quarter", "start": "2025-01-01", "end": "2025-03-31"},
            {"id": "2025-H1", "year": 2025, "kind": "half_year", "start": "2025-01-01", "end": "2025-06-30"},
            {"id": "2025-9M", "year": 2025, "kind": "year_to_date", "start": "2025-01-01", "end": "2025-09-30"},
        ]
        self.discovery["periods"] = [self.discovery["periods"][0], *interim_periods, self.discovery["periods"][1]]
        self.column_periods += [item["id"] for item in interim_periods]
        for item in self.discovery["period_coverage"]:
            if item["year"] == 2025 and item["slot"] in ("Q1", "H1", "9M"):
                item.update(status="reported", explanation="Synthetic H1 full accounts and Q1/9M sales disclosures.")
        half_values = {
            "assets": 1100, "liabilities": 660, "equity": 440, "cash_close": 115,
            "balance_sheet_cash": 115, "inventory": 105, "receivables": 125, "payables": -85,
            "debt": 325, "cash_open": 100, "working_capital": 145, "net_debt": 210,
            "share_capital": 210, "minority_interest": 22.5, "shares": 100,
        }
        context = {"source_id": "annual", "unit_id": f"{self.sheet}!R1"}
        for row in self.rows:
            values = self.display_values[row["id"]]
            sales = row["role"] in ("revenue", "segment_revenue")
            half = half_values.get(row["id"], values[1] * 0.5)
            extras = [values[1] * 0.2 if sales else None, half, values[1] * 0.75 if sales else None]
            numeric_index = 2
            for period, value in zip(interim_periods, extras):
                if value is None:
                    row["unavailable"].append({"period": period["id"],
                                               "explanation": "Sales-only release does not disclose this financial line.",
                                               "references": [copy.deepcopy(context)]})
                else:
                    reference = dict(row["observations"][0]["reference"], number_index=numeric_index)
                    row["observations"].append({"period": period["id"], "reference": reference})
                    numeric_index += 1
            values.extend(extras)
        for period in interim_periods:
            for section in SECTIONS:
                status = ("complete" if period["kind"] == "half_year" else
                          "partial" if section in ("segments", "income_statement") else "not_disclosed")
                self.candidate["coverage"].append({"section": section, "period": period["id"], "status": status,
                                                   "explanation": "H1 full accounts; Q1 and 9M disclose sales only.",
                                                   "references": [copy.deepcopy(context)]})
        self.candidate["cash_continuity"].append({"period": "2025-H1", "previous_period": "2024", "terms": [],
                                                  "explanation": "H1 opens at prior annual closing cash, on the same basis.",
                                                  "references": [context]})
        return self


class ScriptedProvider:
    """Scripted decisions test plumbing and gates, not actual AI research quality."""

    last_response = None

    def __init__(self, company, *, mutate=None, review_fault=None, repair=False, batch=False):
        self.company = company
        self.mutate = mutate
        self.review_fault = review_fault
        self.repair = repair
        self.batch = batch
        self.calls = []
        self.proposals = 0
        self.read_requested = False
        self.saved_batches = 0

    def validate_configuration(self):
        pass

    def metadata(self):
        return {"provider": "SYNTHETIC SCRIPTED TEST", "models": {
            role: "gpt-6.1-sol" for role in ("researcher", "extractor", "reviewer")}}

    @staticmethod
    def synthetic_response(stage):
        return {"synthetic": True, "stage": stage, "status": "completed", "model": "gpt-6.1-sol",
                "output": [], "usage": {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100}}

    def complete(self, *, role, instructions, payload, schema, web=False):
        stage = payload["stage"]
        self.calls.append(copy.deepcopy(payload))
        self.last_response = self.synthetic_response(stage)
        if stage == "discover":
            if not web:
                raise AssertionError("Discovery must request web research")
            return copy.deepcopy(self.company.discovery)
        if stage == "extract":
            action = {"action": "propose", "read_requests": [], "sources": [], "rows": [],
                      "delete_row_ids": [], "search_query": "", "candidate": None}
            if not self.read_requested:
                self.read_requested = True
                action.update(action="read", read_requests=[
                    {"source_id": source["id"], "unit_id": unit["id"]}
                    for source in payload["catalog"] for unit in source["units"]])
                return action
            candidate = copy.deepcopy(self.company.candidate)
            if self.mutate and (not self.repair or self.proposals == 0):
                self.mutate(candidate)
            if self.batch and self.saved_batches * 12 < len(candidate["rows"]):
                start = self.saved_batches * 12
                action.update(action="save_rows", rows=candidate["rows"][start:start + 12])
                self.saved_batches += 1
                return action
            self.proposals += 1
            if self.batch:
                candidate["rows"] = []
            action["candidate"] = candidate
            return action
        if stage == "source_review":
            result = {"facts": [], "issues": [], "read_requests": [], "search_query": ""}
            if not payload["evidence"]:
                result["read_requests"] = [
                    {"source_id": source["id"], "unit_id": unit["id"]}
                    for source in payload["catalog"] for unit in source["units"]]
                return result
            disclosed = {row["id"]: row for row in self.company.rows}
            facts = []
            for concept in payload["concepts"]:
                row = disclosed[concept["id"]]
                fact = {key: copy.deepcopy(row[key])
                        for key in ("entity", "unit", "scale", "sign", "definition", "time_basis")}
                fact.update(row_id=concept["id"], reporting_basis=self.company.candidate["reporting_basis"],
                            observations=[dict(copy.deepcopy(observation),
                                               context_refs=copy.deepcopy(row["definition_refs"]))
                                          for observation in row["observations"]
                                          if observation["period"] in concept["periods"]])
                facts.append(fact)
            if self.review_fault == "missing_source":
                facts.pop()
            if self.review_fault == "duplicate_source":
                facts.append(copy.deepcopy(facts[0]))
            if self.review_fault == "missing_source_context":
                facts[0]["observations"][0]["context_refs"] = []
            result["facts"] = facts
            return result
        if stage == "source_alignment":
            result = {"checks": [], "issues": [], "read_requests": [], "search_query": ""}
            if not payload["evidence"]:
                result["read_requests"] = [
                    {"source_id": source["id"], "unit_id": unit["id"]}
                    for source in payload["catalog"] for unit in source["units"]]
                return result
            disclosed = {row["id"]: row for row in self.company.rows}
            for row in payload["rows"]:
                passed, reason = True, "Synthetic semantic source alignment verified."
                if self.review_fault == "definition_disagreement" and row["definition"] != disclosed[row["id"]]["definition"]:
                    passed, reason = False, "Equal numbers describe a different economic definition."
                if self.review_fault == "basis_disagreement" and payload["reporting_basis"] != self.company.candidate["reporting_basis"]:
                    passed, reason = False, "The candidate reporting vintage differs from the source basis."
                result["checks"].append({"row_id": row["id"], "passed": passed, "reason": reason,
                                         "references": copy.deepcopy(disclosed[row["id"]]["definition_refs"])})
            if self.review_fault == "missing_alignment":
                result["checks"].pop()
            if self.review_fault == "duplicate_alignment":
                result["checks"].append(copy.deepcopy(result["checks"][0]))
            if self.review_fault == "missing_alignment_context":
                result["checks"][0]["references"] = []
            if self.review_fault == "unread_alignment_context":
                result["checks"][0]["references"] = [{"source_id": "annual", "unit_id": "Never read"}]
            return result
        if stage == "coverage_inventory":
            section = payload["section"]
            result = {"search_query": "", "read_requests": [], "section": section,
                      "coverage": [{key: copy.deepcopy(value) for key, value in item.items() if key != "section"}
                                   for item in self.company.candidate["coverage"] if item["section"] == section],
                      "items": [], "issues": []}
            if not payload["evidence"]:
                result["read_requests"] = [
                    {"source_id": source["id"], "unit_id": unit["id"]}
                    for source in payload["catalog"] for unit in source["units"]]
                return result
            result["items"] = [{"id": section + "_" + row["id"], "label": row["label"],
                                "entity": row["entity"], "references": copy.deepcopy(row["definition_refs"]),
                                "periods": [observation["period"] for observation in row["observations"]]}
                               for row in self.company.rows if row["section"] == section]
            if self.review_fault == "duplicate_inventory":
                result["items"].append(copy.deepcopy(result["items"][0]))
            if self.review_fault == "empty_inventory":
                result["items"] = []
            if self.review_fault == "wrong_inventory_section":
                result["section"] = "shares" if section != "shares" else "equity"
            return result
        if stage == "model_review":
            checks = [{"topic": topic, "passed": True, "reason": "Synthetic documentary scope checked."}
                      for topic in REVIEW_TOPICS]
            if self.review_fault == "missing_model":
                checks.pop()
            if self.review_fault == "model_reject":
                checks[0].update(passed=False, reason="Synthetic legal identity remains unresolved.")
            if self.review_fault == "duplicate_model":
                checks.append(copy.deepcopy(checks[0]))
            matches = []
            for item in self.company.rows:
                row = next((row for row in payload["rows"] if row["label"] == item["label"]
                            and row["section"] == item["section"]), None)
                matches.append({"inventory_id": item["section"] + "_" + item["id"],
                                "row_id": row["id"] if row else "",
                                "reason": "The independently inventoried line is present." if row
                                          else "The independently inventoried disclosure is missing.",
                                "references": copy.deepcopy(item["definition_refs"])})
            if self.review_fault == "missing_match":
                matches.pop()
            if self.review_fault == "duplicate_match":
                matches.append(copy.deepcopy(matches[0]))
            if self.review_fault == "reused_match":
                next(match for match in matches if match["inventory_id"] == "equity_minority_interest")["row_id"] = "share_capital"
            result = {"checks": checks, "matches": matches, "issues": [], "read_requests": [], "search_query": ""}
            read_ids = {(item["source_id"], item["unit_id"]) for item in payload["evidence"]}
            required = {(ref["source_id"], ref["unit_id"])
                        for match in matches for ref in match["references"]}
            if not required <= read_ids:
                result.update(checks=[], matches=[], read_requests=[
                    {"source_id": source_id, "unit_id": unit_id} for source_id, unit_id in sorted(required - read_ids)])
            return result
        raise AssertionError("Unknown workflow stage: " + stage)


class InitiationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def run_case(self, company=None, provider=None, **kwargs):
        company = company or SyntheticCompany()
        provider = provider or ScriptedProvider(company)
        # These financial scenarios intentionally start independent runs. Resume
        # behavior has separate tests with the public default preserved.
        kwargs.setdefault("fresh", True)
        directory = initiate_company(self.root, company.name, provider=provider, fetcher=company.fetch,
                                     **kwargs)
        record = json.loads((directory / "record.json").read_text(encoding="utf-8"))
        return directory, record, provider

    def test_mixed_annual_half_year_and_sales_only_interims_are_preserved_and_checked(self):
        company = SyntheticCompany().include_interims()
        directory, record, provider = self.run_case(company, years=[2024, 2025])
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertTrue(all(check["passed"] for check in record["checks"]), record["checks"])
        periods = {item["id"]: item for item in record["discovery"]["periods"]}
        self.assertEqual(set(periods), {"2024", "2025", "2025-Q1", "2025-H1", "2025-9M"})
        self.assertEqual(periods["2025-Q1"]["kind"], "quarter")
        self.assertEqual(periods["2025-H1"]["kind"], "half_year")
        self.assertEqual(periods["2025-9M"]["kind"], "year_to_date")
        rows = {row["id"]: row for row in record["rows"]}
        self.assertEqual(rows["revenue"]["values"]["2025-Q1"], 220)
        self.assertEqual(rows["revenue"]["values"]["2025-H1"], 550)
        self.assertEqual(rows["revenue"]["values"]["2025-9M"], 825)
        self.assertNotIn("2025-Q2", rows["revenue"]["values"])
        self.assertNotIn("2025-Q3", rows["revenue"]["values"])
        self.assertNotIn("2025-Q1", rows["net_debt"]["values"])
        self.assertEqual({item["period"] for item in rows["net_debt"]["unavailable"]}, {"2025-Q1", "2025-9M"})
        coverage = {(item["section"], item["period"]): item["status"] for item in record["candidate"]["coverage"]}
        self.assertEqual(coverage[("income_statement", "2025-Q1")], "partial")
        self.assertEqual(coverage[("balance_sheet", "2025-Q1")], "not_disclosed")
        self.assertEqual(coverage[("balance_sheet", "2025-H1")], "complete")
        self.assertTrue(any(check["name"] == "balance_sheet:2025-H1" for check in record["checks"]))
        self.assertTrue(any(check["name"] == "cash_rollforward:2025-H1" for check in record["checks"]))
        source_calls = [call for call in provider.calls if call["stage"] == "source_review"]
        revenue = [concept for call in source_calls for concept in call["concepts"] if concept["id"] == "revenue"]
        self.assertTrue(revenue and all(set(concept["periods"]) == set(periods) for concept in revenue))
        book = load_workbook(directory / "model.xlsx", data_only=False)
        try:
            sheet = book["net_debt"]
            header = {str(cell.value): cell.column for cell in sheet[4]}
            quarter_column = next(column for value, column in header.items() if "2025-Q1" in value)
            debt_row = next(row for row in sheet if row[0].value == "net debt")
            self.assertIsNone(debt_row[quarter_column - 1].value)
            self.assertTrue(debt_row[quarter_column - 1].comment)
        finally:
            book.close()

    def test_cash_continuity_uses_dated_predecessor_not_previous_interim_column(self):
        company = SyntheticCompany().include_interims()
        directory, record, _ = self.run_case(company)
        self.assertEqual(record["status"], "accepted", record["issues"])
        book = load_workbook(directory / "model.xlsx", data_only=False)
        try:
            sheet = book["cash_flow"]
            header = {str(cell.value): cell.column for cell in sheet[4]}
            annual_2024 = next(column for value, column in header.items() if "2024" in value)
            half_2025 = next(column for value, column in header.items() if "2025-H1" in value)
            close_row = next(row for row in sheet if row[0].value == "cash close")
            prior_annual_cell = close_row[annual_2024 - 1]
            half_cell = close_row[half_2025 - 1]
            for name in ("cash_continuity:2025-H1", "cash_continuity:2025"):
                check = next(row for row in book["Checks"] if row[0].value == name)
                self.assertIn(f"'cash_flow'!{prior_annual_cell.coordinate}", check[6].value)
                self.assertNotIn(f"'cash_flow'!{half_cell.coordinate}", check[6].value)
                self.assertEqual(WorkbookTests.arithmetic_value(book, check[6]), 0)
            same_date = next(row for row in book["Checks"] if str(row[0].value).startswith("stock_date_consistency:cash_open:"))
            self.assertEqual(same_date[6].data_type, "f")
            self.assertEqual(WorkbookTests.arithmetic_value(book, same_date[6]), 0)
            opening = next(row for row in sheet if row[0].value == "cash open")
            opening[half_2025 - 1].value += 1
            self.assertEqual(abs(WorkbookTests.arithmetic_value(book, same_date[6])), 1)
        finally:
            book.close()

    def test_discovery_cannot_silently_skip_interim_cadence_or_accept_wrong_dates(self):
        for fault in ("missing_slot", "duplicate_slot", "missing_reported_period", "wrong_quarter_dates", "wrong_half_dates"):
            with self.subTest(fault=fault):
                company = SyntheticCompany().include_interims()
                if fault == "missing_slot":
                    company.discovery["period_coverage"].pop()
                elif fault == "duplicate_slot":
                    company.discovery["period_coverage"].append(copy.deepcopy(company.discovery["period_coverage"][0]))
                elif fault == "missing_reported_period":
                    company.discovery["periods"] = [item for item in company.discovery["periods"] if item["id"] != "2025-Q1"]
                elif fault == "wrong_quarter_dates":
                    next(item for item in company.discovery["periods"] if item["id"] == "2025-Q1")["end"] = "2025-06-30"
                else:
                    next(item for item in company.discovery["periods"] if item["id"] == "2025-H1")["end"] = "2025-09-30"
                directory, record, provider = self.run_case(company)
                self.assertEqual(record["status"], "incomplete")
                self.assertEqual([call["stage"] for call in provider.calls], ["discover"])
                self.assertEqual(company.fetches, [])
                self.assertFalse((directory / "model.xlsx").exists())

    def test_missing_interim_values_require_read_citations_and_explicit_absence(self):
        def missing_observation(candidate):
            row = next(row for row in candidate["rows"] if row["id"] == "shares")
            row["observations"] = [item for item in row["observations"] if item["period"] != "2025-H1"]

        def missing_citations(candidate):
            next(row for row in candidate["rows"] if row["id"] == "net_debt")["unavailable"][0]["references"] = []

        def unread_citations(candidate):
            next(row for row in candidate["rows"] if row["id"] == "net_debt")["unavailable"][0]["references"][0]["unit_id"] = "Never read"

        for mutation in (missing_observation, missing_citations, unread_citations):
            with self.subTest(mutation=mutation.__name__):
                company = SyntheticCompany().include_interims()
                directory, record, _ = self.run_case(company, ScriptedProvider(company, mutate=mutation))
                self.assertEqual(record["status"], "incomplete")
                self.assertFalse((directory / "model.xlsx").exists())

    def test_independent_inventory_requires_every_disclosed_period_of_a_matched_row(self):
        def omit_half_year(candidate):
            row = next(row for row in candidate["rows"] if row["id"] == "minority_interest")
            row["observations"] = [item for item in row["observations"] if item["period"] != "2025-H1"]
            row["unavailable"].append({"period": "2025-H1", "explanation": "Incorrect draft omission despite source disclosure.",
                                       "references": copy.deepcopy(row["definition_refs"])})

        company = SyntheticCompany().include_interims()
        directory, record, _ = self.run_case(company, ScriptedProvider(company, mutate=omit_half_year))
        self.assertEqual(record["status"], "incomplete")
        self.assertFalse((directory / "model.xlsx").exists())
        failed = [check for check in record["checks"] if not check["passed"]]
        self.assertTrue(any(check["name"] == "inventory_match:equity_minority_interest" for check in failed), record["issues"])

    def test_shared_stock_date_can_reuse_evidence_but_different_durations_or_dates_cannot(self):
        def share_opening_cash(candidate):
            row = next(row for row in candidate["rows"] if row["id"] == "cash_open")
            annual = next(item for item in row["observations"] if item["period"] == "2025")
            half = next(item for item in row["observations"] if item["period"] == "2025-H1")
            half["reference"] = copy.deepcopy(annual["reference"])

        company = SyntheticCompany().include_interims()
        _, checks = self.deterministic_case(company, share_opening_cash)
        self.assertTrue(all(check["passed"] for check in checks), checks)
        for row_id in ("revenue", "cash_close"):
            def reuse_different_period(candidate):
                row = next(row for row in candidate["rows"] if row["id"] == row_id)
                annual = next(item for item in row["observations"] if item["period"] == "2025")
                half = next(item for item in row["observations"] if item["period"] == "2025-H1")
                half["reference"] = copy.deepcopy(annual["reference"])

            with self.subTest(row_id=row_id), self.assertRaisesRegex(ValueError, "different duration periods or stock dates"):
                self.deterministic_case(company, reuse_different_period)

    def test_stock_balances_for_the_same_date_cannot_disagree_between_period_columns(self):
        company = SyntheticCompany().include_interims()
        for row_id, half_value in (("cash_open", 101), ("cash_close", 116),
                                   ("balance_sheet_cash", 116), ("net_debt", 209)):
            company.display_values[row_id][3] = half_value
        _, checks = self.deterministic_case(company)
        duplicate_date = [check for check in checks if check["name"].startswith("stock_date_consistency:cash_open:")]
        self.assertTrue(duplicate_date)
        self.assertTrue(any(not check["passed"] and abs(check["difference"]) == 1 for check in duplicate_date))
        self.assertTrue(next(check for check in checks if check["name"] == "cash_rollforward:2025-H1")["passed"])

    def test_optional_annual_subtotal_absence_does_not_invalidate_complete_half_year_accounts(self):
        company = SyntheticCompany().include_interims()
        subtotal = copy.deepcopy(next(row for row in company.rows if row["id"] == "minority_interest"))
        reference = {"source_id": "annual", "unit_id": f"{company.sheet}!R{len(company.rows) + 3}"}
        subtotal.update(id="optional_equity_subtotal", label="Optional annual equity subtotal",
                        definition="Separately disclosed annual subtotal, not a mandatory equity role.",
                        observations=[{"period": str(year), "reference": dict(reference, number_index=index,
                                                                              number_format="dot_decimal")}
                                      for index, year in enumerate((2024, 2025))],
                        definition_refs=[*subtotal["definition_refs"][:2], reference])
        subtotal["unavailable"].append({"period": "2025-H1", "explanation": "H1 accounts omit this optional annual subtotal.",
                                        "references": [reference]})
        company.rows.append(subtotal)
        company.display_values[subtotal["id"]] = [220, 245, None, None, None]
        company.candidate["equations"].append({"target": subtotal["id"],
                                                "terms": [{"row_id": "share_capital", "coefficient": 1},
                                                          {"row_id": "minority_interest", "coefficient": 1}],
                                                "explanation": "Synthetic optional subtotal of separately reported components."})
        _, record, _ = self.run_case(company)
        self.assertEqual(record["status"], "accepted", record["issues"])
        half_check = next(check for check in record["checks"] if check["name"] == "equation:optional_equity_subtotal:2025-H1")
        self.assertTrue(half_check["passed"])
        self.assertEqual(half_check["basis"], "not_applicable")
        row = next(row for row in record["rows"] if row["id"] == subtotal["id"])
        self.assertNotIn("2025-H1", row["values"])

    def test_discovery_notes_continue_and_preserve_independent_review_contexts(self):
        company = SyntheticCompany()
        notes = [
            "Use consolidated group accounts, not the separate parent-company accounts.",
            "Use FY2025 accounts and their FY2024 comparatives for a consistent basis.",
            "Do not mix later reorganized segments with the earlier comparable series.",
            "An optional spreadsheet mirror is unavailable; the primary disclosure is usable.",
            "Future periods are blank workbook columns, not forecasts to research.",
        ]
        company.discovery["notes"] = notes
        directory, record, provider = self.run_case(company, years=[2024, 2025], forecast_years=3)
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertEqual(record["discovery"]["notes"], notes)
        self.assertEqual(record["issues"], [])
        discovery_call = provider.calls[0]
        self.assertEqual(set(discovery_call),
                         {"stage", "company_query", "historical_years", "years", "as_of"})
        self.assertEqual(discovery_call["years"], [2024, 2025])
        self.assertEqual(record["request"]["forecast_years"], 3)
        self.assertEqual(record["request"]["max_cost_usd"], 20)
        log = [json.loads(line) for line in (directory / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(log[0]["result"]["notes"], notes)
        for stage in ("extract", "model_review"):
            entries = [entry for entry in log if entry["stage"] == stage]
            self.assertTrue(entries)
            self.assertTrue(all(entry["payload"]["discovery"]["notes"] == notes for entry in entries))
        for stage in ("source_review", "coverage_inventory"):
            calls = [call for call in provider.calls if call["stage"] == stage]
            self.assertTrue(calls)
            for call in calls:
                self.assertEqual(set(call["discovery"]), {"company", "periods"})
                self.assertTrue(all(note not in json.dumps(call) for note in notes))
        book = load_workbook(directory / "model.xlsx", data_only=False)
        try:
            for section in SECTIONS:
                sheet = book[section]
                columns = [cell.column for cell in sheet[4] if "forecast (blank)" in str(cell.value)]
                self.assertEqual(len(columns), 3)
                self.assertTrue(all(sheet.cell(row, column).value is None
                                    for row in range(5, sheet.max_row + 1) for column in columns))
        finally:
            book.close()

    def test_discovery_blockers_stop_before_downloads_and_preserve_usage(self):
        for blocker in ("Company identity is ambiguous between two unrelated issuers.",
                        "Required annual accounts could not be located."):
            with self.subTest(blocker=blocker):
                company = SyntheticCompany()
                company.discovery["notes"] = ["The workflow should continue if evidence is sufficient."]
                company.discovery["blocking_issues"] = [blocker]
                directory, record, provider = self.run_case(company)
                self.assertEqual(record["status"], "incomplete")
                self.assertIn(blocker, " ".join(record["issues"]))
                self.assertEqual([call["stage"] for call in provider.calls], ["discover"])
                self.assertEqual(company.fetches, [])
                self.assertEqual(record["source_attempts"], [])
                self.assertEqual(record["checks"], [])
                self.assertFalse((directory / "model.xlsx").exists())
                self.assertEqual(record["usage"]["calls"], 1)
                self.assertEqual(record["usage"]["by_stage"]["discover"]["total_tokens"], 1100)
                self.assertGreater(record["usage"]["estimated_cost_usd"], 0)
                log = [json.loads(line) for line in (directory / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
                self.assertEqual(log[0]["result"]["blocking_issues"], [blocker])

    def test_discovery_notes_cannot_replace_required_identity_periods_or_sources(self):
        for missing in ("identity", "periods", "sources"):
            with self.subTest(missing=missing):
                company = SyntheticCompany()
                company.discovery["notes"] = ["Everything needed for extraction is available."]
                if missing == "identity":
                    company.discovery["company"]["legal_name"] = ""
                else:
                    company.discovery[missing] = []
                directory, record, provider = self.run_case(company)
                self.assertEqual(record["status"], "incomplete")
                self.assertTrue(record["issues"])
                self.assertEqual([call["stage"] for call in provider.calls], ["discover"])
                self.assertEqual(company.fetches, [])
                self.assertFalse((directory / "model.xlsx").exists())

    def test_optional_source_download_failure_does_not_discard_complete_evidence(self):
        company = SyntheticCompany()
        optional = dict(company.source, id="optional", url="https://example.invalid/optional.xlsx",
                        title="SYNTHETIC OPTIONAL SPREADSHEET MIRROR")
        company.discovery["sources"].append(optional)
        company.discovery["notes"] = ["Use the primary disclosure if the optional spreadsheet mirror fails."]
        primary_fetch = company.fetch
        attempted = []

        def fetch(url):
            attempted.append(url)
            if url == optional["url"]:
                raise HTTPError(url, 503, "Synthetic unavailable mirror", {}, None)
            return primary_fetch(url)

        company.fetch = fetch
        _, record, provider = self.run_case(company)
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertEqual(attempted, [company.source["url"], optional["url"]])
        self.assertEqual([source["id"] for source in record["sources"]], ["annual"])
        failure = next(item for item in record["source_attempts"] if item["source"]["id"] == "optional")
        self.assertEqual(failure["status"], "failed")
        self.assertIn("503", failure["error"])
        self.assertTrue(failure["started_at"] and failure["finished_at"])
        extraction = next(call for call in provider.calls if call["stage"] == "extract")
        self.assertIn("optional", " ".join(extraction["feedback"]))
        self.assertTrue(record["checks"] and all(check["passed"] for check in record["checks"]))

    def test_unavailable_required_source_cannot_be_approved_by_reassuring_notes(self):
        company = SyntheticCompany()
        company.discovery["notes"] = ["The primary disclosure is accessible and sufficient for every statement."]

        def unavailable(url):
            raise HTTPError(url, 503, "Synthetic unavailable primary disclosure", {}, None)

        company.fetch = unavailable
        directory, record, _ = self.run_case(company)
        self.assertEqual(record["status"], "incomplete")
        self.assertFalse((directory / "model.xlsx").exists())
        self.assertEqual(record["sources"], [])
        self.assertEqual(record["rows"], [])
        self.assertTrue(record["issues"])
        self.assertTrue(record["source_attempts"])
        self.assertTrue(all(item["status"] == "failed" and "503" in item["error"]
                            for item in record["source_attempts"]))

    def test_two_companies_discover_different_layouts_without_configuration(self):
        first = None
        before = None
        for variant in (0, 1):
            company = SyntheticCompany(variant)
            directory, record, provider = self.run_case(company)
            self.assertEqual(record["status"], "accepted", record["issues"])
            self.assertTrue(all(item["passed"] for item in record["checks"]))
            rows = {row["id"]: row for row in record["rows"]}
            self.assertEqual(rows["revenue"]["values"], {"2024": 1000.0, "2025": 1100.0})
            self.assertEqual(rows["net_debt"]["values"], {"2024": 200.0, "2025": 220.0})
            self.assertEqual(rows["revenue"]["unit"], company.currency)
            self.assertFalse((self.root / "configs").exists())
            archived = record["sources"][0]
            self.assertEqual(archived["sha256"], hashlib.sha256(Path(archived["path"]).read_bytes()).hexdigest())
            self.assertTrue(archived["fetched_at"])
            self.assertEqual(record["workbook_sha256"],
                             hashlib.sha256((directory / "model.xlsx").read_bytes()).hexdigest())
            book = load_workbook(directory / "model.xlsx", data_only=False)
            try:
                revenue_row = next(row for row in book["income_statement"] if row[0].value == "revenue")
                self.assertEqual(revenue_row[3].value, 1000)
                for sheet in book:
                    if sheet.title in SECTIONS:
                        forecast_columns = [cell.column for cell in sheet[4]
                                            if "forecast (blank)" in str(cell.value)]
                        self.assertEqual(len(forecast_columns), 5)
                        self.assertTrue(all(sheet.cell(row, column).value is None
                                            for row in range(5, sheet.max_row + 1)
                                            for column in forecast_columns))
                self.assertTrue(any(row[6].data_type == "f" for row in book["Checks"].iter_rows(min_row=2)))
            finally:
                book.close()
            log = [json.loads(line) for line in (directory / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(log), record["call_count"])
            self.assertTrue(all(entry["started_at"] and entry["finished_at"] for entry in log))
            self.assertTrue(all(isinstance(entry["elapsed_seconds"], (int, float))
                                and entry["elapsed_seconds"] >= 0 for entry in log))
            self.assertIn("source_review", [entry["stage"] for entry in log])
            self.assertIn("model_review", [entry["stage"] for entry in log])
            if first is None:
                first = directory
                before = {file.relative_to(first): file.read_bytes() for file in first.rglob("*") if file.is_file()}
            else:
                self.assertNotEqual(first, directory)
                self.assertEqual(before, {file.relative_to(first): file.read_bytes()
                                          for file in first.rglob("*") if file.is_file()})
        # Repeating the identical request must also preserve its earlier run.
        self.run_case(SyntheticCompany())
        self.assertEqual(before, {file.relative_to(first): file.read_bytes()
                                  for file in first.rglob("*") if file.is_file()})

    def test_large_candidates_can_be_saved_in_batches_before_review(self):
        company = SyntheticCompany()
        provider = ScriptedProvider(company, batch=True)
        _, record, _ = self.run_case(company, provider)
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertEqual(len(record["rows"]), len(company.rows))
        self.assertEqual(provider.saved_batches, (len(company.rows) + 11) // 12)

    def test_wrong_source_arithmetic_cannot_be_approved_by_agreement(self):
        for row_id in ("assets", "cash_change"):
            with self.subTest(row_id=row_id):
                company = SyntheticCompany()
                company.discovery["notes"] = ["The source figures appear suitable for historical modelling."]
                company.display_values[row_id][1] += 25
                directory, record, provider = self.run_case(company)
                self.assertEqual(record["status"], "incomplete")
                self.assertFalse((directory / "model.xlsx").exists())
                self.assertTrue(any(not item["passed"] for item in record["checks"]))
                self.assertNotIn("model_review", [call["stage"] for call in provider.calls])

    def test_decimal_precision_limits_tolerance_for_balance_sheet_checks(self):
        company = SyntheticCompany()
        for row_id, amount in (("assets", "1200.25"), ("liabilities", "720.00"), ("equity", "480.00")):
            company.display_values[row_id][1] = amount
        directory, record, _ = self.run_case(company)
        self.assertEqual(record["status"], "incomplete")
        check = next(item for item in record["checks"] if item["name"] == "balance_sheet:2025")
        self.assertAlmostEqual(check["difference"], 0.25)
        self.assertLess(check["tolerance"], 0.02)
        self.assertFalse(check["passed"])
        self.assertFalse((directory / "model.xlsx").exists())

    def test_missing_duplicate_and_unread_references_or_coverage_cannot_pass(self):
        def missing(candidate):
            candidate["rows"][0]["observations"].pop()

        def duplicate(candidate):
            candidate["rows"][0]["observations"][1] = copy.deepcopy(candidate["rows"][0]["observations"][0])

        def unread(candidate):
            candidate["rows"][0]["observations"][0]["reference"]["unit_id"] = "Never read"

        def incomplete_coverage(candidate):
            candidate["coverage"].pop()

        for mutation in (missing, duplicate, unread, incomplete_coverage):
            with self.subTest(mutation=mutation.__name__):
                company = SyntheticCompany()
                company.discovery["notes"] = ["All necessary evidence is believed to be available."]
                directory, record, _ = self.run_case(company, ScriptedProvider(company, mutate=mutation))
                self.assertEqual(record["status"], "incomplete")
                self.assertTrue(record["issues"])
                self.assertFalse((directory / "model.xlsx").exists())

    def test_reviewer_can_request_original_context_independently(self):
        class Reader(ScriptedProvider):
            searched_context = False
            requested_context = False

            def complete(self, **kwargs):
                payload = kwargs["payload"]
                if payload["stage"] == "model_review" and not self.searched_context:
                    self.searched_context = True
                    self.calls.append(copy.deepcopy(payload))
                    self.last_response = self.synthetic_response("model_review")
                    return {"checks": [], "matches": [], "issues": [], "search_query": "FY2024", "read_requests": []}
                if payload["stage"] == "model_review" and not self.requested_context:
                    self.requested_context = True
                    self.calls.append(copy.deepcopy(payload))
                    self.last_response = self.synthetic_response("model_review")
                    if not any(item["unit_id"] == f"{self.company.sheet}!R2"
                               for item in payload["search_results"]["matches"]):
                        raise AssertionError("Reviewer did not receive requested archive search results")
                    return {"checks": [], "matches": [], "issues": [], "search_query": "", "read_requests": [
                        {"source_id": "annual", "unit_id": f"{self.company.sheet}!R2"}]}
                if payload["stage"] == "model_review":
                    if not any(item["unit_id"] == f"{self.company.sheet}!R2" for item in payload["evidence"]):
                        raise AssertionError("Reviewer did not receive requested source context")
                return super().complete(**kwargs)

        company = SyntheticCompany()
        provider = Reader(company)
        _, record, _ = self.run_case(company, provider)
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertTrue(provider.searched_context)
        self.assertTrue(provider.requested_context)
        self.assertGreaterEqual(sum(call["stage"] == "model_review" for call in provider.calls), 3)

    def test_every_required_review_must_be_present_and_pass(self):
        for fault in ("missing_source", "duplicate_source", "missing_source_context", "missing_alignment",
                      "duplicate_alignment", "missing_alignment_context",
                      "unread_alignment_context",
                      "missing_model", "duplicate_model", "model_reject"):
            with self.subTest(fault=fault):
                company = SyntheticCompany()
                directory, record, _ = self.run_case(company, ScriptedProvider(company, review_fault=fault))
                self.assertEqual(record["status"], "incomplete")
                self.assertTrue(record["issues"])
                self.assertFalse((directory / "model.xlsx").exists())
                if fault == "model_reject":
                    self.assertIn("identity", " ".join(record["issues"]))

    def test_source_review_can_repair_a_semantic_mapping_without_a_human(self):
        def wrong_share_definition(candidate):
            rows = {row["id"]: row for row in candidate["rows"]}
            rows["shares"]["observations"] = copy.deepcopy(rows["share_capital"]["observations"])

        company = SyntheticCompany()
        provider = ScriptedProvider(company, mutate=wrong_share_definition, repair=True)
        directory, record, _ = self.run_case(company, provider)
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertEqual(len(record["attempts"]), 2)
        self.assertIn("shares", " ".join(record["attempts"][0]["issues"]))
        shares = next(row for row in record["rows"] if row["id"] == "shares")
        self.assertEqual(shares["values"], {"2024": 100.0, "2025": 100.0})
        repairs = [call for call in provider.calls if call["stage"] == "extract" and call["feedback"]]
        self.assertTrue(repairs)
        self.assertTrue(record["attempts"][0]["reviews"])
        for attempt in record["attempts"]:
            self.assertTrue(any(review["stage"] == "source_review" for review in attempt["reviews"]))
        blind_calls = [call for call in provider.calls if call["stage"] == "source_review"]
        self.assertGreaterEqual(sum(not call["evidence"] for call in blind_calls), 4)
        log = [json.loads(line) for line in (directory / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(log), record["call_count"])
        self.assertEqual(record["usage"]["calls"], record["call_count"])
        self.assertTrue(any("shares" in json.dumps(entry["result"].get("facts", []))
                            for entry in log if entry["stage"] == "source_review"))

    def test_independent_passes_hide_candidate_and_previous_verdicts(self):
        company = SyntheticCompany()
        directory, record, provider = self.run_case(company)
        self.assertEqual(record["status"], "accepted", record["issues"])
        blind = [call for call in provider.calls if call["stage"] == "source_review"]
        inventory = [call for call in provider.calls if call["stage"] == "coverage_inventory"]
        models = [call for call in provider.calls if call["stage"] == "model_review"]
        self.assertTrue(blind and inventory and models)
        for call in blind:
            self.assertEqual(set(call["discovery"]), {"company", "periods"})
            for concept in call["concepts"]:
                self.assertEqual(set(concept), {"id", "label", "section", "entity", "periods"})
            for hidden in ("rows", "candidate", "reporting_basis", "checks", "source_reviews", "feedback", "facts"):
                self.assertNotIn(hidden, call)
        for call in inventory:
            for hidden in ("rows", "concepts", "candidate", "coverage", "checks", "reviews", "feedback", "facts"):
                self.assertNotIn(hidden, call)
        self.assertEqual({call["section"] for call in inventory}, set(SECTIONS))
        first_model = next(index for index, call in enumerate(provider.calls) if call["stage"] == "model_review")
        self.assertEqual({call["section"] for call in provider.calls[:first_model]
                          if call["stage"] == "coverage_inventory"}, set(SECTIONS))
        for call in models:
            for hidden in ("checks", "source_reviews", "facts", "reviews", "feedback", "independent_checks"):
                self.assertNotIn(hidden, call)
            self.assertEqual({item["section"] for item in call["inventory"]}, set(SECTIONS))
        log = [json.loads(line) for line in (directory / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
        aligned = [entry for entry in log if entry["stage"] == "source_alignment"]
        self.assertTrue(aligned)
        for entry in aligned:
            for hidden in ("checks", "source_reviews", "reviews", "feedback", "independent_checks"):
                self.assertNotIn(hidden, entry["payload"])
            reconstructed = [fact for previous in log[:entry["call"] - 1]
                             if previous["stage"] == "source_review" for fact in previous["result"]["facts"]]
            self.assertTrue(all(fact in reconstructed for fact in entry["payload"]["facts"]))
        self.assertTrue(any(entry["stage"] == "coverage_inventory" and entry["result"]["items"] for entry in log))
        self.assertTrue(any(entry["stage"] == "source_review" and entry["result"]["facts"] for entry in log))

    def test_blind_reconstruction_rejects_valid_tokens_with_wrong_meaning(self):
        def wrong_number(candidate):
            rows = {row["id"]: row for row in candidate["rows"]}
            rows["shares"]["observations"] = copy.deepcopy(rows["share_capital"]["observations"])

        def wrong_year(candidate):
            row = next(row for row in candidate["rows"] if row["id"] == "share_capital")
            for observation in row["observations"]:
                observation["reference"]["number_index"] = 1 - observation["reference"]["number_index"]

        def wrong_scale(candidate):
            next(row for row in candidate["rows"] if row["id"] == "shares")["scale"] = 1000

        def wrong_entity(candidate):
            next(row for row in candidate["rows"] if row["id"] == "shares")["entity"] = "Unrelated legal entity"

        for mutation in (wrong_number, wrong_year, wrong_scale, wrong_entity):
            with self.subTest(mutation=mutation.__name__):
                company = SyntheticCompany()
                directory, record, provider = self.run_case(company, ScriptedProvider(company, mutate=mutation))
                self.assertEqual(record["status"], "incomplete")
                self.assertFalse((directory / "model.xlsx").exists())
                self.assertIn("source_review", [call["stage"] for call in provider.calls])
                self.assertTrue(record["attempts"][0]["reviews"])
                self.assertTrue(any(not check["passed"] and check["name"].startswith("blind_source:")
                                    for check in record["checks"]), record["issues"])

    def test_independent_inventory_blocks_omission_even_when_all_verdicts_approve(self):
        def omit_supplement(candidate):
            candidate["rows"] = [row for row in candidate["rows"] if row["id"] != "minority_interest"]

        company = SyntheticCompany()
        directory, record, provider = self.run_case(company, ScriptedProvider(company, mutate=omit_supplement))
        self.assertEqual(record["status"], "incomplete")
        self.assertFalse((directory / "model.xlsx").exists())
        self.assertTrue(all(check["passed"] for check in record["checks"]
                            if not check["name"].startswith(("inventory", "independent"))))
        model = next(review["result"] for review in record["reviews"] if review["stage"] == "model_review")
        self.assertTrue(all(check["passed"] for check in model["checks"]))
        missing = next(match for match in model["matches"] if match["inventory_id"] == "equity_minority_interest")
        self.assertEqual(missing["row_id"], "")
        self.assertIn("minority_interest", " ".join(record["issues"]))

    def test_equal_values_do_not_override_a_failed_definition_or_vintage_alignment(self):
        def wrong_definition(candidate):
            next(row for row in candidate["rows"] if row["id"] == "shares")["definition"] = "A different economic share measure."

        def wrong_vintage(candidate):
            candidate["reporting_basis"] = "Original FY2024 vintage, inconsistent with the FY2025 comparative source."

        for mutation, fault in ((wrong_definition, "definition_disagreement"), (wrong_vintage, "basis_disagreement")):
            with self.subTest(fault=fault):
                company = SyntheticCompany()
                directory, record, _ = self.run_case(company, ScriptedProvider(company, mutate=mutation, review_fault=fault))
                self.assertEqual(record["status"], "incomplete")
                blind = [check for check in record["checks"] if check["name"].startswith("blind_source:")]
                self.assertTrue(blind and all(check["passed"] for check in blind))
                alignment = [review["result"] for review in record["reviews"] if review["stage"] == "source_alignment"]
                self.assertTrue(any(not check["passed"] for result in alignment for check in result["checks"]))
                self.assertFalse((directory / "model.xlsx").exists())

    def test_one_source_unit_disagreement_at_equal_precision_is_not_rounding(self):
        def swap_years(candidate):
            row = next(row for row in candidate["rows"] if row["id"] == "shares")
            for observation in row["observations"]:
                observation["reference"]["number_index"] = 1 - observation["reference"]["number_index"]

        company = SyntheticCompany()
        company.display_values["shares"] = [100, 101]
        directory, record, _ = self.run_case(company, ScriptedProvider(company, mutate=swap_years))
        self.assertEqual(record["status"], "incomplete")
        blind = [check for check in record["checks"] if check["name"].startswith("blind_source:shares:")]
        self.assertEqual(len(blind), 2)
        self.assertTrue(all(abs(check["difference"]) == 1 and not check["passed"] for check in blind))
        self.assertFalse((directory / "model.xlsx").exists())

    def test_different_source_precision_accepts_equivalent_rounded_disclosure(self):
        company = SyntheticCompany()
        company.display_values["shares"] = [100.4, 101.4]
        rounded = dict(company.source, id="rounded", url="https://example.invalid/rounded-shares.xlsx",
                       title="SYNTHETIC ROUNDED SHARE SUMMARY", kind="results")
        company.discovery["sources"].append(rounded)
        original_fetch = company.fetch

        def fetch(url):
            if url != rounded["url"]:
                return original_fetch(url)
            book = Workbook()
            sheet = book.active
            sheet.title = "Rounded"
            sheet.append(["SYNTHETIC " + company.name + "; same share definition and FY2025 comparative basis; whole shares."])
            sheet.append(["Reported line", "FY2024", "FY2025"])
            sheet.append(["shares", 100, 101])
            output = io.BytesIO()
            book.save(output)
            return output.getvalue(), url, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        def use_rounded_source(candidate):
            row = next(row for row in candidate["rows"] if row["id"] == "shares")
            row["definition_refs"] = [{"source_id": "rounded", "unit_id": f"Rounded!R{number}"}
                                      for number in (1, 2, 3)]
            for observation in row["observations"]:
                observation["reference"].update(source_id="rounded", unit_id="Rounded!R3")

        company.fetch = fetch
        _, record, _ = self.run_case(company, ScriptedProvider(company, mutate=use_rounded_source))
        self.assertEqual(record["status"], "accepted", record["issues"])
        blind = [check for check in record["checks"] if check["name"].startswith("blind_source:shares:")]
        self.assertEqual(len(blind), 2)
        self.assertTrue(all(check["passed"] and 0 < abs(check["difference"]) < check["tolerance"] for check in blind))

    def test_independent_sections_can_reference_one_shared_equity_total(self):
        class SharedTotalProvider(ScriptedProvider):
            def complete(self, **kwargs):
                result = super().complete(**kwargs)
                payload = kwargs["payload"]
                equity = next(row for row in self.company.rows if row["role"] == "total_equity")
                if payload["stage"] == "coverage_inventory" and payload["section"] == "equity" and result["items"]:
                    result["items"].append({"id": "equity_total_equity", "label": equity["label"],
                                            "entity": equity["entity"], "references": copy.deepcopy(equity["definition_refs"]),
                                            "periods": [observation["period"] for observation in equity["observations"]]})
                if payload["stage"] == "model_review" and result["checks"]:
                    result["matches"].append({"inventory_id": "equity_total_equity", "row_id": equity["id"],
                                              "reason": "The equity schedule repeats the same consolidated equity total.",
                                              "references": copy.deepcopy(equity["definition_refs"])})
                return result

        company = SyntheticCompany()
        _, record, _ = self.run_case(company, SharedTotalProvider(company))
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertEqual(sum(row["role"] == "total_equity" for row in record["rows"]), 1)
        names = {check["name"] for check in record["checks"] if check["passed"]}
        self.assertIn("inventory_match:balance_sheet_equity", names)
        self.assertIn("inventory_match:equity_total_equity", names)

    def test_incomplete_or_duplicate_independent_inventory_and_matches_fail(self):
        for fault in ("empty_inventory", "duplicate_inventory", "wrong_inventory_section",
                      "missing_match", "duplicate_match", "reused_match"):
            with self.subTest(fault=fault):
                company = SyntheticCompany()
                directory, record, _ = self.run_case(company, ScriptedProvider(company, review_fault=fault))
                self.assertEqual(record["status"], "incomplete")
                self.assertTrue(record["issues"])
                self.assertFalse((directory / "model.xlsx").exists())

    def test_each_independent_stage_must_read_its_own_evidence(self):
        class SkipsReading(ScriptedProvider):
            def __init__(self, company, stage):
                super().__init__(company)
                self.skipped_stage = stage

            def complete(self, **kwargs):
                payload = kwargs["payload"]
                if payload["stage"] == self.skipped_stage and not payload["evidence"]:
                    # Return final scripted selections immediately, without asking
                    # the workflow to read any source in this independent stage.
                    evidence = [{"source_id": source["id"], "unit_id": unit["id"]}
                                for source in payload["catalog"] for unit in source["units"]]
                    kwargs = dict(kwargs, payload=dict(payload, evidence=evidence))
                return super().complete(**kwargs)

        for stage in ("source_review", "coverage_inventory", "model_review"):
            with self.subTest(stage=stage):
                company = SyntheticCompany()
                directory, record, _ = self.run_case(company, SkipsReading(company, stage))
                self.assertEqual(record["status"], "incomplete")
                self.assertIn("not independently read", " ".join(record["issues"]))
                self.assertFalse((directory / "model.xlsx").exists())

    def test_new_independent_calls_respect_dollar_budget_and_preserve_logs(self):
        directory, record, provider = self.run_case(max_cost_usd=0.015)
        self.assertEqual(record["status"], "incomplete")
        self.assertEqual(record["call_count"], 5)
        self.assertEqual(len(provider.calls), 5)
        self.assertIn("budget", " ".join(record["issues"]))
        self.assertFalse((directory / "model.xlsx").exists())
        log = [json.loads(line) for line in (directory / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(log), 5)
        self.assertTrue(any(entry["stage"] == "source_review" for entry in log))
        self.assertEqual(record["usage"]["calls"], 5)
        self.assertAlmostEqual(record["usage"]["estimated_cost_usd"], 0.015)
        self.assertEqual(record["budget"]["status"], "exhausted")
        self.assertAlmostEqual(record["usage"]["by_stage"]["source_review"]["estimated_cost_usd"], 0.006)

    def deterministic_case(self, company, mutate=None):
        candidate = copy.deepcopy(company.candidate)
        if mutate:
            mutate(candidate)
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            store = SourceStore(Path(temporary), fetcher=company.fetch)
            store.add(company.source)
            refs = [{"source_id": source["id"], "unit_id": unit["id"]}
                    for source in store.catalog() for unit in source["units"]]
            evidence = store.read(refs)
            return materialize_and_check(candidate, company.discovery, store,
                                         {(item["source_id"], item["unit_id"]) for item in evidence})

    def test_cash_and_segment_bridges_require_reported_distinct_anchors(self):
        def remove_cash_bridge(candidate):
            candidate["equations"] = [equation for equation in candidate["equations"]
                                      if equation["target"] != "balance_sheet_cash"]

        def remove_segment_bridge(candidate):
            candidate["equations"] = [equation for equation in candidate["equations"]
                                      if equation["target"] != "segment_group_profit"]

        def copy_cash_tokens(candidate):
            rows = {row["id"]: row for row in candidate["rows"]}
            rows["balance_sheet_cash"]["observations"] = copy.deepcopy(rows["cash_close"]["observations"])

        def derive_liabilities(candidate):
            row = next(row for row in candidate["rows"] if row["id"] == "liabilities")
            row.update(observations=[], terms=[{"row_id": "assets", "coefficient": 1},
                                               {"row_id": "equity", "coefficient": -1}])

        def duplicate_segment_entity(candidate):
            next(row for row in candidate["rows"] if row["id"] == "profit_b")["entity"] = "Alpha"

        for mutation, expected in (
            (remove_cash_bridge, "cash_balance_sheet_reconciliation"),
            (remove_segment_bridge, "segment_profit_reconciliation"),
            (copy_cash_tokens, "cash_balance_sheet_reconciliation"),
            (derive_liabilities, "balance_sheet_independent:2025"),
            (duplicate_segment_entity, "segment_entity_coverage"),
        ):
            with self.subTest(mutation=mutation.__name__):
                _, checks = self.deterministic_case(SyntheticCompany(), mutation)
                self.assertFalse(next(check for check in checks if check["name"] == expected)["passed"])

    def test_liability_total_can_sum_independently_reported_components(self):
        company = SyntheticCompany()
        liabilities = next(row for row in company.rows if row["id"] == "liabilities")
        for row_id, values in (("current_liabilities", [350, 400]), ("noncurrent_liabilities", [250, 320])):
            row = copy.deepcopy(liabilities)
            reference = {"source_id": "annual", "unit_id": f"{company.sheet}!R{len(company.rows) + 3}"}
            row.update(id=row_id, label=row_id.replace("_", " "), role="other",
                       definition="Separately reported " + row_id,
                       observations=[{"period": str(year), "reference": dict(reference, number_index=index,
                                                                        number_format="dot_decimal")}
                                     for index, year in enumerate((2024, 2025))],
                       definition_refs=[*liabilities["definition_refs"][:2], reference])
            company.rows.append(row)
            company.display_values[row_id] = values
        liabilities.update(observations=[],
                           definition="Calculated total from independently reported current and noncurrent liabilities.",
                           terms=[{"row_id": row_id, "coefficient": 1}
                                  for row_id in ("current_liabilities", "noncurrent_liabilities")])
        company.display_values["liabilities"] = [None, None]
        _, checks = self.deterministic_case(company)
        self.assertTrue(all(check["passed"] for check in checks), checks)
        balance = [check for check in checks if check["name"].startswith("balance_sheet:")]
        self.assertTrue(balance and all(check["basis"] == "corroboration" for check in balance))

    def test_balanced_cash_statements_still_fail_adjacent_year_cash_discontinuity(self):
        company = SyntheticCompany()
        for row_id, value in (("cash_open", 105), ("cash_close", 135),
                              ("balance_sheet_cash", 135), ("net_debt", 215)):
            company.display_values[row_id][1] = value
        _, checks = self.deterministic_case(company)
        failures = [check for check in checks if not check["passed"]]
        self.assertEqual([check["name"] for check in failures], ["cash_continuity:2025"])
        self.assertEqual(failures[0]["difference"], 5)

    def company_with_cash_adjustment(self, *, sparse=False):
        company = SyntheticCompany()
        adjustment = copy.deepcopy(next(row for row in company.rows if row["id"] == "minority_interest"))
        reference = {"source_id": "annual", "unit_id": f"{company.sheet}!R{len(company.rows) + 3}"}
        adjustment.update(id="cash_scope_adjustment", label="Reported opening cash scope adjustment",
                          section="cash_flow", definition="Reported cash reclassification into the comparative scope.",
                          time_basis="flow",
                          observations=[{"period": str(year), "reference": dict(reference, number_index=index,
                                                                           number_format="dot_decimal")}
                                        for index, year in enumerate((2024, 2025))],
                          definition_refs=[*adjustment["definition_refs"][:2], reference])
        if sparse:
            adjustment["observations"] = [{"period": "2025", "reference": dict(reference, number_index=0,
                                                                             number_format="dot_decimal")}]
            adjustment["unavailable"] = [{"period": "2024", "explanation": "Scope change applies only to FY2025 opening cash.",
                                           "references": [reference]}]
        company.rows.append(adjustment)
        company.display_values["cash_scope_adjustment"] = [None if sparse else 0, 5]
        company.candidate["cash_continuity"][0].update(
            terms=[{"row_id": "cash_scope_adjustment", "coefficient": 1}], references=[reference],
            explanation="The cited cash scope reclassification reconciles closing to next opening cash.")
        for row_id, value in (("cash_open", 105), ("cash_close", 135),
                              ("balance_sheet_cash", 135), ("net_debt", 215)):
            company.display_values[row_id][1] = value
        return company

    def test_adjacent_cash_bridge_accepts_cited_reported_adjustments(self):
        company = self.company_with_cash_adjustment()
        _, checks = self.deterministic_case(company)
        self.assertTrue(all(check["passed"] for check in checks), checks)
        continuity = next(check for check in checks if check["name"] == "cash_continuity:2025")
        self.assertEqual(continuity["basis"], "corroboration")

    def test_sparse_cash_adjustment_preserves_undisclosed_year_as_blank(self):
        company = self.company_with_cash_adjustment(sparse=True)
        directory, record, provider = self.run_case(company)
        self.assertEqual(record["status"], "accepted", record["issues"])
        adjustment = next(row for row in record["rows"] if row["id"] == "cash_scope_adjustment")
        self.assertEqual(adjustment["values"], {"2025": 5.0})
        concepts = [concept for call in provider.calls if call["stage"] == "source_review"
                    for concept in call["concepts"] if concept["id"] == "cash_scope_adjustment"]
        self.assertTrue(concepts and all(concept["periods"] == ["2025"] for concept in concepts))
        book = load_workbook(directory / "model.xlsx", data_only=False)
        try:
            row = next(row for row in book["cash_flow"] if row[0].value == "Reported opening cash scope adjustment")
            self.assertIsNone(row[3].value)
            self.assertEqual(row[4].value, 5)
            continuity = next(item for item in book["Checks"] if item[0].value == "cash_continuity:2025")
            self.assertIn(f"-'cash_flow'!{row[4].coordinate}*1", continuity[6].value)
            self.assertAlmostEqual(WorkbookTests.arithmetic_value(book, continuity[6]), 0)
            row[4].value = 4
            self.assertAlmostEqual(WorkbookTests.arithmetic_value(book, continuity[6]), 1)
        finally:
            book.close()

    def test_sparse_rows_cannot_hide_missing_evidence_or_supply_missing_equation_inputs(self):
        def reused_in_statement(candidate):
            candidate["equations"].append({"target": "minority_interest",
                                            "terms": [{"row_id": "cash_scope_adjustment", "coefficient": 1}],
                                            "explanation": "Invalid reuse of a sparse adjustment in annual statements."})

        def missing_required_period(candidate):
            next(row for row in candidate["rows"] if row["id"] == "cash_scope_adjustment")["observations"] = []

        def uncited_absence(candidate):
            next(row for row in candidate["rows"] if row["id"] == "cash_scope_adjustment")["unavailable"][0]["references"] = []

        company = self.company_with_cash_adjustment(sparse=True)
        with self.assertRaisesRegex(ValueError, "missing or repeated historical observation"):
            self.deterministic_case(company, missing_required_period)
        with self.assertRaisesRegex(ValueError, "cited"):
            self.deterministic_case(company, uncited_absence)
        _, checks = self.deterministic_case(company, reused_in_statement)
        self.assertFalse(next(check for check in checks if check["name"] == "equation:minority_interest:2024")["passed"])

    def test_constructed_cash_identity_is_labelled_and_period_gaps_are_not_compared(self):
        def derived_opening(candidate):
            row = next(row for row in candidate["rows"] if row["id"] == "cash_open")
            row.update(observations=[], terms=[{"row_id": "cash_close", "coefficient": 1},
                                               {"row_id": "cash_change", "coefficient": -1}])

        company = SyntheticCompany()
        _, checks = self.deterministic_case(company, derived_opening)
        cash = [check for check in checks if check["name"].startswith("cash_rollforward:")]
        self.assertTrue(all(check["passed"] and check["basis"] == "arithmetic_construction" for check in cash))
        company.discovery["periods"][1]["start"] = "2025-01-02"
        company.candidate["cash_continuity"] = []
        _, checks = self.deterministic_case(company)
        continuity = next(check for check in checks if check["name"] == "cash_continuity:2025")
        self.assertTrue(continuity["passed"])
        self.assertEqual(continuity["basis"], "not_applicable")

    def test_missing_api_configuration_creates_no_outputs_or_network_calls(self):
        with patch.dict(os.environ, {}, clear=True), patch("research_platform.ai.urlopen") as api:
            with self.assertRaisesRegex(AIError, "OPENAI_API_KEY"):
                initiate_company(self.root, "Arbitrary Unconfigured Company")
            api.assert_not_called()
        self.assertFalse((self.root / "outputs").exists())

    def test_dollar_budget_exhaustion_stops_without_a_workbook(self):
        directory, record, provider = self.run_case(max_cost_usd=0.003)
        self.assertEqual(record["status"], "incomplete")
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(record["call_count"], 1)
        self.assertIn("budget", " ".join(record["issues"]))
        self.assertFalse((directory / "model.xlsx").exists())

    def test_twenty_dollar_stop_includes_crossing_call_and_sends_no_next_request(self):
        class Expensive(ScriptedProvider):
            input_tokens = 1_000_000

            def complete(self, **kwargs):
                result = super().complete(**kwargs)
                self.last_response["usage"] = {"input_tokens": self.input_tokens, "output_tokens": 0}
                return result

        for count, expected in ((1_000_000, 20.0), (1_050_000, 21.0)):
            with self.subTest(estimated_usd=expected):
                company = SyntheticCompany()
                provider = Expensive(company)
                provider.input_tokens = count
                directory, record, _ = self.run_case(company, provider)
                self.assertEqual(record["status"], "incomplete")
                self.assertEqual(record["call_count"], 5)
                self.assertEqual(len(provider.calls), 5)
                self.assertAlmostEqual(record["usage"]["estimated_cost_usd"], expected)
                self.assertEqual(record["budget"]["status"], "exhausted")
                self.assertEqual(record["budget"]["estimated_remaining_usd"], 0)
                self.assertFalse((directory / "model.xlsx").exists())
                log = [json.loads(line) for line in (directory / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
                self.assertEqual(len(log), 5)
                self.assertEqual(log[-1]["stage"], "source_review")
                self.assertAlmostEqual(sum(group["estimated_cost_usd"] for group in record["usage"]["by_stage"].values()), expected)

    def test_budget_crossed_by_final_review_cannot_publish_accepted_workbook(self):
        class ExpensiveFinal(ScriptedProvider):
            def complete(self, **kwargs):
                result = super().complete(**kwargs)
                if kwargs["payload"]["stage"] == "model_review" and not result["read_requests"]:
                    self.last_response["usage"] = {"input_tokens": 0, "output_tokens": 2_000_000}
                return result

        company = SyntheticCompany()
        directory, record, provider = self.run_case(company, ExpensiveFinal(company))
        self.assertEqual(provider.calls[-1]["stage"], "model_review")
        self.assertEqual(record["status"], "incomplete")
        self.assertEqual(record["budget"]["status"], "exhausted")
        self.assertGreaterEqual(record["usage"]["by_stage"]["model_review"]["estimated_cost_usd"], 20)
        self.assertFalse((directory / "model.xlsx").exists())
        self.assertFalse((directory / "model.pending.xlsx").exists())

    def test_unknown_cost_or_stale_provider_response_stops_before_next_request(self):
        class UnknownCost(ScriptedProvider):
            fault = "model"

            def complete(self, **kwargs):
                if self.fault == "stale" and self.calls:
                    self.calls.append(copy.deepcopy(kwargs["payload"]))
                    raise AIError("Synthetic transport failure without a new response")
                result = super().complete(**kwargs)
                if self.fault == "model":
                    self.last_response["model"] = "unpriced-synthetic-model"
                elif self.fault == "tier":
                    self.last_response["service_tier"] = "unpriced-tier"
                elif self.fault == "counts":
                    self.last_response["usage"]["total_tokens"] = -1
                return result

        for fault in ("model", "tier", "counts", "stale"):
            with self.subTest(fault=fault):
                company = SyntheticCompany()
                provider = UnknownCost(company)
                provider.fault = fault
                directory, record, _ = self.run_case(company, provider)
                self.assertEqual(record["status"], "incomplete")
                self.assertEqual(record["call_count"], 2 if fault == "stale" else 1)
                self.assertEqual(record["budget"]["status"], "unknown_cost")
                self.assertFalse(record["usage"]["cost_is_complete"])
                self.assertFalse((directory / "model.xlsx").exists())
                if fault == "stale":
                    self.assertAlmostEqual(record["usage"]["estimated_cost_usd"], 0.003)
                    self.assertEqual(record["usage"]["reported_calls"], 1)
                    self.assertEqual(record["usage"]["by_stage"]["extract"]["missing_usage"], 1)

    def test_transport_failure_retains_known_spend_and_stops_without_retry(self):
        company = SyntheticCompany()
        provider = OpenAIProvider(api_key="SYNTHETIC-SECRET", models={
            role: "gpt-6.1-sol" for role in ("researcher", "extractor", "reviewer")})
        discovery = ScriptedProvider.synthetic_response("discover")
        discovery["output"] = [
            {"type": "web_search_call", "status": "completed", "action": {"type": "search"}},
            {"type": "message", "content": [
                {"type": "output_text", "text": json.dumps(company.discovery)}]},
        ]
        responses = [io.BytesIO(json.dumps(discovery).encode("utf-8")),
                     URLError(TimeoutError("SYNTHETIC-SECRET"))]
        with patch("research_platform.ai.urlopen", side_effect=responses) as network:
            directory, record, _ = self.run_case(company, provider)
        self.assertEqual(network.call_count, 2)
        self.assertEqual(record["call_count"], 2)
        self.assertEqual(record["status"], "incomplete")
        self.assertEqual(record["budget"]["status"], "unknown_cost")
        self.assertAlmostEqual(record["usage"]["estimated_cost_usd"], 0.013)
        self.assertEqual(record["usage"]["reported_calls"], 1)
        self.assertEqual(record["usage"]["missing_usage"], 1)
        self.assertFalse(record["usage"]["cost_is_complete"])
        self.assertIsNone(record["usage"]["by_stage"]["extract"]["estimated_cost_usd"])
        self.assertFalse((directory / "model.xlsx").exists())
        saved_calls = (directory / "calls.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("SYNTHETIC-SECRET", saved_calls + json.dumps(record))
        calls = [json.loads(line) for line in saved_calls.splitlines()]
        self.assertEqual([call["stage"] for call in calls], ["discover", "extract"])
        failure = calls[-1]["provider_response"]
        self.assertEqual(failure["_transport"]["failure_kind"], "timeout")
        self.assertNotIn("usage", failure)
        self.assertIsNone(calls[-1]["usage"]["estimated_cost_usd"])
        self.assertFalse(calls[-1]["usage"]["reported"])

    def test_invalid_budget_or_unpriced_configuration_makes_no_request_or_run(self):
        company = SyntheticCompany()
        provider = ScriptedProvider(company)
        for amount in (True, 0, -1, 20.01, float("nan"), float("inf"), "20"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                initiate_company(self.root, company.name, provider=provider, max_cost_usd=amount)
        with patch.object(provider, "metadata", return_value={"models": {"researcher": "unknown-model"}}):
            with self.assertRaisesRegex(AIError, "known pricing"):
                initiate_company(self.root, company.name, provider=provider)
        self.assertEqual(provider.calls, [])
        self.assertFalse((self.root / "outputs").exists())

    def test_useful_progress_can_exceed_former_request_and_navigation_ceilings(self):
        class ManySteps(ScriptedProvider):
            saves = 0
            reviewer_reads = 0

            def complete(self, **kwargs):
                payload = kwargs["payload"]
                if payload["stage"] == "extract" and self.saves < 65:
                    self.saves += 1
                    self.calls.append(copy.deepcopy(payload))
                    self.last_response = self.synthetic_response("extract")
                    row = copy.deepcopy(self.company.rows[0])
                    row["definition"] += f" Synthetic draft revision {self.saves}."
                    return {"action": "save_rows", "read_requests": [], "sources": [], "rows": [row],
                            "delete_row_ids": [], "search_query": "", "candidate": None}
                if payload["stage"] == "model_review" and self.reviewer_reads < 7:
                    refs = [{"source_id": source["id"], "unit_id": unit["id"]}
                            for source in payload["catalog"] for unit in source["units"]]
                    ref = refs[self.reviewer_reads]
                    self.reviewer_reads += 1
                    self.calls.append(copy.deepcopy(payload))
                    self.last_response = self.synthetic_response("model_review")
                    return {"checks": [], "matches": [], "issues": [], "search_query": "", "read_requests": [ref]}
                return super().complete(**kwargs)

        company = SyntheticCompany()
        messages = []
        _, record, provider = self.run_case(company, ManySteps(company), progress=messages.append)
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertGreater(record["call_count"], 80)
        self.assertGreater(sum(call["stage"] == "extract" for call in provider.calls), 30)
        self.assertGreater(sum(call["stage"] == "model_review" for call in provider.calls), 5)
        self.assertLess(record["usage"]["estimated_cost_usd"], 20)
        self.assertNotIn("max_calls", record["request"])
        self.assertNotIn("max_rounds", record["request"])
        self.assertTrue(any("Stage extract:" in message and "total" in message for message in messages))
        self.assertTrue(any("Run usage:" in message and "estimated" in message.lower() for message in messages))
        self.assertEqual(sum(group["total_tokens"] for group in record["usage"]["by_stage"].values()), record["usage"]["total_tokens"])

    def test_unchanged_failed_candidate_stops_with_original_findings(self):
        company = SyntheticCompany()
        _, record, provider = self.run_case(company, ScriptedProvider(company, review_fault="model_reject"))
        self.assertEqual(record["status"], "incomplete")
        self.assertEqual(provider.proposals, 2)
        self.assertIn("No progress", " ".join(record["issues"]))
        self.assertIn("identity", " ".join(record["issues"]))
        self.assertTrue(record["attempts"][0]["issues"])

    def test_repeated_navigation_without_new_context_stops(self):
        class RepeatingRead(ScriptedProvider):
            def complete(self, **kwargs):
                result = super().complete(**kwargs)
                if kwargs["payload"]["stage"] == "source_review":
                    result.update(facts=[], read_requests=[{"source_id": "annual", "unit_id": f"{self.company.sheet}!R1"}])
                return result

        company = SyntheticCompany()
        _, record, provider = self.run_case(company, RepeatingRead(company))
        self.assertEqual(record["status"], "incomplete")
        self.assertIn("no progress", " ".join(record["issues"]))
        self.assertEqual(sum(call["stage"] == "source_review" for call in provider.calls), 2)

    def test_reading_missing_evidence_allows_resubmitting_an_unchanged_candidate(self):
        class EarlyProposal(ScriptedProvider):
            repaired_context = False

            def complete(self, **kwargs):
                payload = kwargs["payload"]
                if payload["stage"] == "extract" and self.proposals == 1 and not self.repaired_context:
                    self.repaired_context = True
                    self.calls.append(copy.deepcopy(payload))
                    self.last_response = self.synthetic_response("extract")
                    refs = [{"source_id": source["id"], "unit_id": unit["id"]}
                            for source in payload["catalog"] for unit in source["units"]]
                    return {"action": "read", "read_requests": refs, "sources": [], "rows": [],
                            "delete_row_ids": [], "search_query": "", "candidate": None}
                return super().complete(**kwargs)

        company = SyntheticCompany()
        provider = EarlyProposal(company)
        provider.read_requested = True  # Deliberately propose before reading original context.
        _, record, _ = self.run_case(company, provider)
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertEqual(len(record["attempts"]), 2)
        self.assertEqual(record["attempts"][0]["candidate"], record["attempts"][1]["candidate"])
        self.assertTrue(record["attempts"][0]["issues"])

    def test_corrected_drafts_can_exceed_former_three_attempt_limit(self):
        class Correcting(ScriptedProvider):
            def complete(self, **kwargs):
                result = super().complete(**kwargs)
                if kwargs["payload"]["stage"] == "extract" and result["candidate"] is not None and self.proposals < 4:
                    result["candidate"]["reporting_basis"] = f"Synthetic incorrect vintage {self.proposals}"
                return result

        company = SyntheticCompany()
        _, record, provider = self.run_case(company, Correcting(company, review_fault="basis_disagreement"))
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertEqual(provider.proposals, 4)
        self.assertEqual(len(record["attempts"]), 4)
        self.assertLess(record["usage"]["estimated_cost_usd"], 20)
        self.assertTrue(all(attempt["issues"] for attempt in record["attempts"][:3]))
        self.assertTrue(all(any(review["stage"] == "source_review" for review in attempt["reviews"])
                            for attempt in record["attempts"]))

    def test_charged_failure_preserves_error_and_stage_charge_when_budget_exhausted(self):
        class ChargedFailure(ScriptedProvider):
            def complete(self, **kwargs):
                super().complete(**kwargs)
                self.last_response["status"] = "incomplete"
                raise AIError("Synthetic charged provider failure")

        company = SyntheticCompany()
        directory, record, provider = self.run_case(company, ChargedFailure(company), max_cost_usd=0.003)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(record["budget"]["status"], "exhausted")
        self.assertIn("Synthetic charged provider failure", " ".join(record["issues"]))
        self.assertAlmostEqual(record["usage"]["by_stage"]["discover"]["estimated_cost_usd"], 0.003)
        logged = json.loads((directory / "calls.jsonl").read_text(encoding="utf-8").strip())
        self.assertEqual(logged["error"], "Synthetic charged provider failure")
        self.assertIn("budget", logged["budget_stop"])

    def test_run_records_missing_usage_and_charged_incomplete_response(self):
        class MissingUsage(ScriptedProvider):
            def complete(self, **kwargs):
                result = super().complete(**kwargs)
                self.last_response.pop("usage")
                return result

        company = SyntheticCompany()
        directory, record, _ = self.run_case(company, MissingUsage(company))
        self.assertEqual(record["status"], "incomplete")
        self.assertEqual(record["call_count"], 1)
        self.assertEqual(record["usage"]["calls"], record["call_count"])
        self.assertEqual(record["usage"]["missing_usage"], record["call_count"])
        self.assertFalse(record["usage"]["cost_is_complete"])
        self.assertEqual(record["budget"]["status"], "unknown_cost")
        self.assertIsNone(record["usage"]["estimated_cost_usd"])
        self.assertFalse((directory / "model.xlsx").exists())

        class IncompleteProvider(ScriptedProvider):
            def metadata(self):
                return {"provider": "SYNTHETIC SCRIPTED TEST", "models": {
                    role: "gpt-6-luna" for role in ("researcher", "extractor", "reviewer")}}

            def complete(self, **kwargs):
                self.calls.append(copy.deepcopy(kwargs["payload"]))
                self.last_response = {"status": "incomplete", "model": "gpt-6-luna", "output": [],
                                      "usage": {"input_tokens": 1000, "output_tokens": 100,
                                                "total_tokens": 1100}}
                raise AIError("Synthetic output limit reached")

        company = SyntheticCompany()
        messages = []
        directory, record, _ = self.run_case(company, IncompleteProvider(company), progress=messages.append)
        self.assertEqual(record["status"], "incomplete")
        self.assertFalse((directory / "model.xlsx").exists())
        self.assertEqual(record["call_count"], 1)
        self.assertEqual(record["usage"]["reported_calls"], 1)
        self.assertAlmostEqual(record["usage"]["estimated_cost_usd"], 0.00015)
        logged = json.loads((directory / "calls.jsonl").read_text(encoding="utf-8").strip())
        self.assertEqual(logged["provider_response"]["status"], "incomplete")
        self.assertEqual(logged["usage"]["output_tokens"], 100)
        self.assertAlmostEqual(logged["usage"]["estimated_cost_usd"], 0.00015)
        self.assertTrue(any("discover" in message for message in messages))

    def test_circular_definitions_and_incompatible_units_are_rejected(self):
        def cycle(candidate):
            candidate["equations"].append({"target": "expenses",
                                          "terms": [{"row_id": "net_income", "coefficient": 1}],
                                          "explanation": "A deliberately circular accounting relationship."})

        def units(candidate):
            next(row for row in candidate["rows"] if row["id"] == "debt")["unit"] = "shares"

        for mutation, message in ((cycle, "Circular"), (units, "units")):
            with self.subTest(mutation=mutation.__name__):
                company = SyntheticCompany()
                directory, record, _ = self.run_case(company, ScriptedProvider(company, mutate=mutation))
                self.assertEqual(record["status"], "incomplete")
                self.assertIn(message, " ".join(record["issues"]))
                self.assertFalse((directory / "model.xlsx").exists())


class ResumeTests(unittest.TestCase):
    class Provider(ScriptedProvider):
        """Use only supplied context, as a new remote request would after restart."""

        def complete(self, **kwargs):
            payload = kwargs["payload"]
            if payload["stage"] == "extract":
                self.read_requested = bool(payload["evidence"])
                self.saved_batches = (len(payload["draft_row_index"]) + 11) // 12
            return super().complete(**kwargs)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.company = SyntheticCompany()

    def tearDown(self):
        self.temporary.cleanup()

    def run_company(self, provider=None, **kwargs):
        provider = provider or self.Provider(self.company)
        directory = initiate_company(self.root, self.company.name, provider=provider,
                                     fetcher=self.company.fetch, **kwargs)
        return directory, read_json(directory / "record.json"), provider

    def interrupt_after(self, call_count, provider=None, **kwargs):
        provider = provider or self.Provider(self.company)
        completed = 0

        def progress(message):
            nonlocal completed
            if message.startswith("Run usage:"):
                completed += 1
                if completed == call_count:
                    raise KeyboardInterrupt("Synthetic process interruption after durable response")

        with self.assertRaises(KeyboardInterrupt):
            self.run_company(provider, progress=progress, **kwargs)
        directory = max((self.root / "outputs").glob("initiate_*"),
                        key=lambda path: read_json(path / "record.json")["started_at"])
        return directory, read_json(directory / "record.json"), provider

    @staticmethod
    def calls(directory):
        return [json.loads(line) for line in (directory / "calls.jsonl").read_text(encoding="utf-8").splitlines()]

    @staticmethod
    def write_record(directory, record):
        (directory / "record.json").write_text(json.dumps(record), encoding="utf-8")

    def assert_blocked_without_spending(self, error, pattern, **kwargs):
        provider = self.Provider(self.company)
        previous = set((self.root / "outputs").glob("initiate_*"))
        fetches = len(self.company.fetches)
        with self.assertRaisesRegex(error, pattern):
            self.run_company(provider, **kwargs)
        self.assertEqual(provider.calls, [])
        self.assertEqual(len(self.company.fetches), fetches)
        self.assertEqual(set((self.root / "outputs").glob("initiate_*")), previous)

    def test_interrupted_draft_resumes_without_research_refetch_or_duplicate_charges(self):
        parent, saved, first = self.interrupt_after(4, self.Provider(self.company, batch=True))
        parent_bytes = (parent / "record.json").read_bytes()
        original_calls = self.calls(parent)
        self.assertEqual([call["stage"] for call in original_calls], ["discover", "extract", "extract", "extract"])
        self.assertEqual(len(self.company.fetches), 1)
        directory, record, resumed = self.run_company(self.Provider(self.company, batch=True))
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertNotEqual(directory, parent)
        self.assertEqual(record["parent_run"], str(parent.resolve()))
        self.assertEqual((parent / "record.json").read_bytes(), parent_bytes)
        self.assertEqual(self.calls(parent), original_calls)
        self.assertEqual(self.calls(directory)[:len(original_calls)], original_calls)
        self.assertNotIn("discover", [call["stage"] for call in resumed.calls])
        self.assertEqual(len(self.company.fetches), 1)
        self.assertEqual(record["call_count"], len(first.calls) + len(resumed.calls))
        self.assertEqual(record["usage"]["total_tokens"], record["call_count"] * 1100)
        self.assertAlmostEqual(record["usage"]["estimated_cost_usd"], record["call_count"] * 0.003)
        self.assertEqual(record["sources"], saved["sources"])
        self.assertTrue(Path(record["sources"][0]["path"]).is_relative_to(parent))
        self.assertTrue((directory / "model.xlsx").exists())

    def test_restart_inside_blind_review_restores_only_that_reviews_original_context(self):
        parent, saved, _ = self.interrupt_after(4)
        self.assertEqual(self.calls(parent)[-1]["stage"], "source_review")
        self.assertTrue(self.calls(parent)[-1]["result"]["read_requests"])
        directory, record, resumed = self.run_company()
        self.assertEqual(record["status"], "accepted", record["issues"])
        first = resumed.calls[0]
        self.assertEqual(first["stage"], "source_review")
        self.assertTrue(first["evidence"])
        self.assertNotIn("rows", first)
        self.assertNotIn("candidate", first)
        self.assertNotIn("reviews", first)
        self.assertTrue(all(set(concept) == {"id", "label", "section", "entity", "periods"}
                            for concept in first["concepts"]))
        self.assertEqual(record["usage"]["by_stage"]["discover"]["calls"], 1)
        self.assertEqual(record["usage"]["total_tokens"], 1100 * (saved["call_count"] + len(resumed.calls)))

    def test_multiple_continuations_reuse_finished_reviews_and_carry_one_budget(self):
        first, _, _ = self.interrupt_after(7)
        second, second_saved, _ = self.interrupt_after(3)
        self.assertEqual(second_saved["parent_run"], str(first.resolve()))
        self.assertEqual(second_saved["call_count"], 10)
        self.assertTrue(second_saved["reviews"])
        frozen = copy.deepcopy(second_saved["reviews"])
        directory, record, provider = self.run_company()
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertEqual(record["parent_run"], str(second.resolve()))
        self.assertEqual(record["call_count"], 10 + len(provider.calls))
        self.assertEqual(len(self.company.fetches), 1)
        self.assertEqual([item["stage"] for item in record["reviews"][:len(frozen)]],
                         [item["stage"] for item in frozen])
        self.assertEqual([item["result"] for item in record["reviews"][:len(frozen)]],
                         [item["result"] for item in frozen])
        self.assertEqual(self.calls(directory)[:10], self.calls(second))
        self.assertEqual(record["usage"]["total_tokens"], record["call_count"] * 1100)

    def test_interrupting_replay_preserves_future_inherited_calls_and_sources(self):
        first, first_record, _ = self.interrupt_after(3)

        def stop_during_replay(message):
            if message.startswith("Reused call 1:"):
                raise KeyboardInterrupt("Synthetic stop while replaying discovery")

        provider = self.Provider(self.company)
        with self.assertRaises(KeyboardInterrupt):
            self.run_company(provider, progress=stop_during_replay)
        self.assertEqual(provider.calls, [])
        second = max((self.root / "outputs").glob("initiate_*"),
                     key=lambda path: read_json(path / "record.json")["started_at"])
        second_record = read_json(second / "record.json")
        self.assertEqual(second_record["parent_run"], str(first.resolve()))
        self.assertEqual(second_record["sources"], first_record["sources"])
        self.assertEqual(second_record["source_attempts"], first_record["source_attempts"])
        self.assertEqual(self.calls(second), self.calls(first))
        directory, record, provider = self.run_company()
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertEqual(record["parent_run"], str(second.resolve()))
        self.assertEqual(provider.calls[0]["stage"], "source_review")
        self.assertEqual(len(self.company.fetches), 1)
        self.assertEqual(record["call_count"], 3 + len(provider.calls))

    def test_known_cost_failed_call_can_continue_but_its_charge_is_not_erased(self):
        class ChargedFailure(self.Provider):
            def complete(self, **kwargs):
                result = super().complete(**kwargs)
                if kwargs["payload"]["stage"] == "extract":
                    raise AIError("Synthetic response ended after reported usage")
                return result

        parent, before, _ = self.run_company(ChargedFailure(self.company))
        self.assertEqual(before["status"], "incomplete")
        self.assertEqual(before["call_count"], 2)
        self.assertTrue(before["usage"]["cost_is_complete"])
        directory, record, provider = self.run_company()
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertEqual(provider.calls[0]["stage"], "extract")
        self.assertEqual(record["usage"]["total_tokens"], (2 + len(provider.calls)) * 1100)
        self.assertEqual(self.calls(directory)[:2], self.calls(parent))
        self.assertIn("error", self.calls(directory)[1])

    def test_cost_before_interruption_counts_towards_same_twenty_dollar_stop(self):
        class Expensive(self.Provider):
            def complete(self, **kwargs):
                result = super().complete(**kwargs)
                self.last_response["usage"] = {"input_tokens": 1_000_000, "output_tokens": 0}
                return result

        parent, before, _ = self.interrupt_after(4, Expensive(self.company))
        self.assertAlmostEqual(before["usage"]["estimated_cost_usd"], 16.0)
        directory, record, provider = self.run_company(Expensive(self.company))
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(record["call_count"], 5)
        self.assertEqual(record["status"], "incomplete")
        self.assertEqual(record["budget"]["status"], "exhausted")
        self.assertAlmostEqual(record["usage"]["estimated_cost_usd"], 20.0)
        self.assertFalse((directory / "model.xlsx").exists())
        self.assert_blocked_without_spending(AIError, "budget|reached|exhausted")

    def test_unknown_failed_request_blocks_restart_before_any_network_or_output(self):
        class UnknownFailure(self.Provider):
            def complete(self, **kwargs):
                if kwargs["payload"]["stage"] == "extract":
                    self.calls.append(copy.deepcopy(kwargs["payload"]))
                    raise AIError("Synthetic lost response without usage")
                return super().complete(**kwargs)

        parent, record, _ = self.run_company(UnknownFailure(self.company))
        original = (parent / "record.json").read_bytes()
        self.assertFalse(record["usage"]["cost_is_complete"])
        self.assert_blocked_without_spending(AIError, "unknown|usage|cost")
        self.assertEqual((parent / "record.json").read_bytes(), original)

    def test_journaled_response_recovers_stale_pending_checkpoint_without_recharging(self):
        parent, record, _ = self.interrupt_after(3)
        last = self.calls(parent)[-1]
        record["pending_call"] = {key: copy.deepcopy(last[key]) for key in
                                  ("call", "call_id", "stage", "role", "started_at")}
        record["call_count"] = 2
        record["usage"] = aggregate_usage(self.calls(parent)[:2])
        self.write_record(parent, record)
        directory, resumed, provider = self.run_company()
        self.assertEqual(resumed["status"], "accepted", resumed["issues"])
        self.assertEqual(provider.calls[0]["stage"], "source_review")
        self.assertEqual(resumed["call_count"], 3 + len(provider.calls))
        self.assertEqual(resumed["usage"]["total_tokens"], resumed["call_count"] * 1100)
        self.assertEqual(self.calls(directory)[:3], self.calls(parent))

    def test_unjournaled_inflight_request_blocks_restart_without_losing_saved_work(self):
        parent, record, _ = self.interrupt_after(2)
        record["pending_call"] = {"call": 3, "call_id": "synthetic-unanswered-request",
                                  "stage": "extract", "role": "extractor", "started_at": record["started_at"]}
        self.write_record(parent, record)
        original = (parent / "record.json").read_bytes()
        self.assert_blocked_without_spending(AIError, "in-flight|known charge|usage")
        self.assertEqual((parent / "record.json").read_bytes(), original)
        self.assertEqual(len(self.calls(parent)), 2)

    def test_code_environment_provider_and_source_drift_stop_before_continuation(self):
        parent, record, _ = self.interrupt_after(3)
        for key in ("code", "environment", "provider"):
            with self.subTest(drift=key):
                changed = copy.deepcopy(record)
                if key == "code":
                    changed[key]["initiation.py"] += "\n# Synthetic incompatible version\n"
                elif key == "environment":
                    changed[key]["openpyxl"] = "synthetic-other-version"
                else:
                    changed[key]["models"]["reviewer"] = "gpt-6.1-sol-2026-01-01"
                self.write_record(parent, changed)
                self.assert_blocked_without_spending(ValueError, "differs|differ|version|settings")
        self.write_record(parent, record)
        original_path = Path(record["sources"][0]["path"])
        original_path.write_bytes(original_path.read_bytes() + b"synthetic corruption")
        self.assert_blocked_without_spending(ValueError, "hash|content")

    def test_damaged_or_missing_journal_cannot_hide_previously_charged_calls(self):
        parent, record, _ = self.interrupt_after(3)
        journal = parent / "calls.jsonl"
        original = journal.read_bytes()
        journal.write_bytes(original + b'{"call":4,')
        self.assert_blocked_without_spending(AIError, "journal|uncertain")
        journal.write_text("", encoding="utf-8")
        self.assert_blocked_without_spending(AIError, "missing|journal")

    def test_accepted_run_is_reused_by_normalized_query_until_fresh_is_explicit(self):
        accepted, record, _ = self.run_company()
        original = (accepted / "record.json").read_bytes()
        provider = self.Provider(self.company)
        query = "  " + self.company.name.upper().replace(" ", "   ") + "  "
        reused = initiate_company(self.root, query, provider=provider, fetcher=self.company.fetch)
        self.assertEqual(reused, accepted)
        self.assertEqual(provider.calls, [])
        self.assertEqual((accepted / "record.json").read_bytes(), original)
        self.assertEqual(len(self.company.fetches), 1)
        directory, fresh, provider = self.run_company(fresh=True)
        self.assertNotEqual(directory, accepted)
        self.assertEqual(fresh["status"], "accepted", fresh["issues"])
        self.assertIsNone(fresh["parent_run"])
        self.assertEqual(provider.calls[0]["stage"], "discover")
        self.assertEqual(len(self.company.fetches), 2)

    def test_explicit_resume_checks_request_settings_and_disallows_older_branch(self):
        first, _, _ = self.interrupt_after(3)
        second, _, _ = self.interrupt_after(1, resume=first / "record.json")
        self.assert_blocked_without_spending(ValueError, "newer|branch", resume=first)
        self.assert_blocked_without_spending(ValueError, "match", resume=second, years=[2024, 2025])
        self.assert_blocked_without_spending(ValueError, "spending limit", resume=second, max_cost_usd=5)
        self.assert_blocked_without_spending(ValueError, "either|both", resume=second, fresh=True)

    def test_resume_keeps_original_research_date_when_restarted_another_day(self):
        from datetime import date

        parent, before, _ = self.interrupt_after(3)

        class LaterDate(date):
            @classmethod
            def today(cls):
                return cls(2035, 1, 1)

        with patch("research_platform.initiation.date", LaterDate):
            directory, record, provider = self.run_company()
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertEqual(record["request"]["as_of"], before["request"]["as_of"])
        self.assertEqual(provider.calls[0]["stage"], "source_review")
        self.assertEqual(record["call_count"], 3 + len(provider.calls))

    def test_older_nonresumable_runs_need_explicit_fresh_instead_of_silent_paid_restart(self):
        parent, record, _ = self.interrupt_after(3)
        record.pop("resume_version")
        self.write_record(parent, record)
        original = (parent / "record.json").read_bytes()
        self.assert_blocked_without_spending(ValueError, "older|predates|fresh")
        directory, fresh, provider = self.run_company(fresh=True)
        self.assertEqual(fresh["status"], "accepted", fresh["issues"])
        self.assertIsNone(fresh["parent_run"])
        self.assertEqual(provider.calls[0]["stage"], "discover")
        self.assertEqual((parent / "record.json").read_bytes(), original)

    def test_interrupt_during_source_download_retries_only_unfinished_download(self):
        provider = self.Provider(self.company)
        with patch.object(self.company, "fetch", side_effect=KeyboardInterrupt("Synthetic interrupted download")):
            with self.assertRaises(KeyboardInterrupt):
                self.run_company(provider)
        parent = next((self.root / "outputs").glob("initiate_*"))
        self.assertEqual(len(self.calls(parent)), 1)
        directory, record, provider = self.run_company()
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertEqual(provider.calls[0]["stage"], "extract")
        self.assertEqual(len(self.company.fetches), 1)
        self.assertEqual(record["call_count"], len(provider.calls) + 1)
        self.assertEqual(self.calls(directory)[0], self.calls(parent)[0])

    def test_interrupt_during_source_parsing_does_not_create_false_completed_evidence(self):
        with patch.object(SourceStore, "_index", side_effect=KeyboardInterrupt("Synthetic interrupted parser")):
            with self.assertRaises(KeyboardInterrupt):
                self.run_company()
        parent = next((self.root / "outputs").glob("initiate_*"))
        self.assertEqual(len(self.calls(parent)), 1)
        self.assertEqual(len(self.company.fetches), 1)
        directory, record, provider = self.run_company()
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertEqual(provider.calls[0]["stage"], "extract")
        self.assertTrue(all(source["status"] == "ready" for source in record["sources"]))
        self.assertEqual(record["call_count"], len(provider.calls) + 1)
        self.assertEqual(self.calls(directory)[0], self.calls(parent)[0])

    def test_interrupt_during_excel_export_resumes_without_repeating_any_ai_call(self):
        with patch("research_platform.initiation.export_workbook",
                   side_effect=KeyboardInterrupt("Synthetic interrupted workbook export")):
            with self.assertRaises(KeyboardInterrupt):
                self.run_company()
        parent = next((self.root / "outputs").glob("initiate_*"))
        before = read_json(parent / "record.json")
        self.assertNotEqual(before["status"], "accepted")
        self.assertFalse((parent / "model.xlsx").exists())
        directory, record, provider = self.run_company()
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertEqual(provider.calls, [])
        self.assertEqual(record["usage"], before["usage"])
        self.assertEqual(self.calls(directory), self.calls(parent))
        self.assertEqual(record["reviews"], before["reviews"])
        self.assertEqual(len(self.company.fetches), 1)
        self.assertTrue((directory / "model.xlsx").exists())

    def test_source_paths_and_extraction_metadata_must_belong_to_frozen_archive(self):
        parent, record, _ = self.interrupt_after(3)
        changed = copy.deepcopy(record)
        changed["sources"][0]["unit_count"] += 1
        changed["source_attempts"][0]["descriptor"]["unit_count"] += 1
        self.write_record(parent, changed)
        self.assert_blocked_without_spending(ValueError, "extraction metadata|changed")
        outside = self.root / "outside.xlsx"
        outside.write_bytes(Path(record["sources"][0]["path"]).read_bytes())
        changed = copy.deepcopy(record)
        changed["sources"][0]["path"] = str(outside)
        changed["source_attempts"][0]["descriptor"]["path"] = str(outside)
        self.write_record(parent, changed)
        self.assert_blocked_without_spending(ValueError, "outside|ancestry")

    def test_project_lock_prevents_concurrent_budget_branches_and_releases_after_error(self):
        from research_platform.initiation import _initiation_lock

        with _initiation_lock(self.root / "outputs"):
            self.assert_blocked_without_spending(AIError, "Another initiation|active")
        directory, record, _ = self.run_company()
        self.assertEqual(record["status"], "accepted", record["issues"])
        self.assertTrue((directory / "model.xlsx").exists())


class WorkbookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        company = SyntheticCompany()
        for row in company.rows:
            if row["unit"] != "shares":
                row["scale"] = 1000000
            if row["id"] == "debt":
                row["scale"] = 1000
                company.display_values["debt"] = [300000, 350000]
            if row["id"] == "payables":
                row["sign"] = -1
                company.display_values["payables"] = [80, 90]
        candidate = copy.deepcopy(company.candidate)
        rows = {row["id"]: row for row in candidate["rows"]}
        for target in ("net_debt", "working_capital"):
            equation = next(item for item in candidate["equations"] if item["target"] == target)
            rows[target]["terms"] = equation["terms"]
            rows[target]["observations"] = []
            candidate["equations"].remove(equation)
        linked_row = copy.deepcopy(rows["net_debt"])
        linked_row.update(id="linked_debt", label="Linked debt", role="other",
                          terms=[{"row_id": "net_debt", "coefficient": 1}])
        # Put the dependent row first to exercise forward cell references.
        candidate["rows"].insert(0, linked_row)
        store = SourceStore(self.root / "sources", fetcher=company.fetch)
        store.add(company.source)
        refs = [{"source_id": source["id"], "unit_id": unit["id"]}
                for source in store.catalog() for unit in source["units"]]
        evidence = store.read(refs)
        resolved, checks = materialize_and_check(candidate, company.discovery, store,
                                                 {(item["source_id"], item["unit_id"]) for item in evidence})
        self.assertTrue(all(check["passed"] for check in checks), checks)
        self.record = {"status": "accepted", "request": {"forecast_years": 5},
                       "discovery": company.discovery, "candidate": candidate,
                       "rows": resolved, "checks": checks, "sources": store.sources, "reviews": []}

    def export(self):
        before = copy.deepcopy(self.record)
        path = self.root / "model.xlsx"
        export_workbook(path, self.record)
        self.assertEqual(self.record, before, "The exported view must not modify the accepted Python record")
        book = load_workbook(path, data_only=False)
        self.addCleanup(book.close)
        return book

    def cells(self, book, section, row_id):
        sheet = book[section]
        id_column = next(cell.column for cell in sheet[4] if cell.value == "Row ID")
        return next(row for row in sheet.iter_rows(min_row=5) if row[id_column - 1].value == row_id)

    @staticmethod
    def arithmetic_value(book, cell):
        """Evaluate only the exported arithmetic branch for tests, not Excel.

        Resolve the actual saved cell links recursively and interpret a restricted
        arithmetic AST. No eval, arbitrary formula engine or production cache.
        """
        if cell.data_type != "f":
            if not isinstance(cell.value, (int, float)):
                raise ValueError("Missing numeric input")
            return cell.value
        branch = re.search(r",\((.+)\)/([0-9]+),NA\(\)\)$", cell.value)
        if branch is None:
            raise AssertionError("Expected an exported arithmetic formula")

        def reference(match):
            target = book[match[1] or cell.parent.title][match[2]]
            return repr(WorkbookTests.arithmetic_value(book, target))

        text = re.sub(r"(?:'([^']+)'!)?([A-Z]+[0-9]+)", reference, branch[1])

        def calculate(node):
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                return node.value
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                return calculate(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
            if isinstance(node, ast.BinOp):
                left, right = calculate(node.left), calculate(node.right)
                if isinstance(node.op, ast.Add):
                    return left + right
                if isinstance(node.op, ast.Sub):
                    return left - right
                if isinstance(node.op, ast.Mult):
                    return left * right
                if isinstance(node.op, ast.Div):
                    return left / right
            raise AssertionError("Unexpected arithmetic syntax in exported formula")

        return calculate(ast.parse(f"({text})/{branch[2]}", mode="eval").body)

    def test_generated_arithmetic_evaluates_to_python_results_and_detects_changed_inputs(self):
        book = self.export()
        for row in self.record["rows"]:
            cells = self.cells(book, row["section"], row["id"])
            for column, year in ((3, "2024"), (4, "2025")):
                self.assertAlmostEqual(self.arithmetic_value(book, cells[column]),
                                       row["values"][year] / row["scale"])
        for check in book["Checks"].iter_rows(min_row=2):
            if check[6].data_type == "f":
                self.assertAlmostEqual(self.arithmetic_value(book, check[6]), check[3].value)
        # A workbook-only edit breaks a reconciliation, without rewriting its
        # recorded Python PASS or original numeric difference.
        revenue = self.cells(book, "income_statement", "revenue")[3]
        revenue.value += 1
        check = next(row for row in book["Checks"] if row[0].value == "equation:revenue:2024")
        self.assertEqual(self.arithmetic_value(book, check[6]), 1000000)
        self.assertEqual(check[1].value, "PASS")
        self.assertEqual(check[3].value, 0)
        revenue.value = None
        with self.assertRaisesRegex(ValueError, "Missing numeric input"):
            self.arithmetic_value(book, check[6])

    def test_excel_formula_length_limit_stops_export_instead_of_writing_an_invalid_workbook(self):
        source = next(row for row in self.record["rows"] if row["id"] == "debt")
        target = next(row for row in self.record["rows"] if row["id"] == "net_debt")
        target["terms"] = []
        for index in range(300):
            component = copy.deepcopy(source)
            component["id"] = f"debt_component_{index}"
            self.record["rows"].append(component)
            target["terms"].append({"row_id": component["id"], "coefficient": 1})
        path = self.root / "too_long.xlsx"
        with self.assertRaisesRegex(ValueError, "8,192-character formula limit"):
            export_workbook(path, self.record)
        self.assertFalse(path.exists())

    def test_derived_formulas_preserve_cross_sheet_signs_scales_and_forward_links(self):
        book = self.export()
        debt = self.cells(book, "balance_sheet", "debt")
        cash = self.cells(book, "cash_flow", "cash_close")
        net_debt = self.cells(book, "net_debt", "net_debt")
        working_capital = self.cells(book, "working_capital", "working_capital")
        linked = self.cells(book, "net_debt", "linked_debt")
        self.assertLess(linked[0].row, net_debt[0].row)
        by_id = {row["id"]: row for row in self.record["rows"]}
        for column, year in ((3, "2024"), (4, "2025")):
            debt_ref, cash_ref = f"'balance_sheet'!{debt[column].coordinate}", f"'cash_flow'!{cash[column].coordinate}"
            self.assertEqual(net_debt[column].value,
                             f"=IF(COUNT({debt_ref},{cash_ref})=2,(+{debt_ref}*1000-{cash_ref}*1000000)/1000000,NA())")
            self.assertEqual(net_debt[column].data_type, "f")
            # The linked inputs imply exactly the normalized Python amount.
            self.assertEqual(debt[column].value * 1000 - cash[column].value * 1000000,
                             by_id["net_debt"]["values"][year])
            self.assertEqual(linked[column].value,
                             f"=IF(COUNT({net_debt[column].coordinate})=1,(+{net_debt[column].coordinate}*1000000)/1000000,NA())")
            payables = self.cells(book, "balance_sheet", "payables")[column]
            self.assertLess(payables.value, 0)
            self.assertIn(f"+'balance_sheet'!{payables.coordinate}*1000000", working_capital[column].value)
        self.assertEqual(net_debt[3].font.color.rgb, "00008000")
        self.assertEqual(linked[3].font.color.rgb, "00000000")
        self.assertEqual(debt[3].font.color.rgb, "000000FF")

    def test_reported_anchors_stay_inputs_and_live_checks_are_separate_from_baseline(self):
        book = self.export()
        revenue = self.cells(book, "income_statement", "revenue")
        self.assertEqual(revenue[3].value, 1000)
        self.assertEqual(revenue[3].data_type, "n")
        self.assertIn('"source_id": "annual"', revenue[3].comment.text)
        check = next(row for row in book["Checks"] if row[0].value == "equation:revenue:2024")
        self.assertEqual(check[1].value, "PASS")
        self.assertEqual(check[3].value, 0)
        self.assertEqual(check[6].data_type, "f")
        self.assertIn(f"'income_statement'!{revenue[3].coordinate}*1000000", check[6].value)
        self.assertIn("'segments'!", check[6].value)
        self.assertIn("ABS(G", check[7].value)
        self.assertIn("INPUT ERROR", check[7].value)
        structural = next(row for row in book["Checks"] if row[0].value == "required_group_roles")
        self.assertIsNone(structural[6].value)
        self.assertIsNone(structural[7].value)
        instructions = " ".join(str(cell.value) for row in book["Start here"] for cell in row)
        self.assertIn("do not change saved Python", instructions)
        self.assertIn("cannot renew acceptance", instructions)
        self.assertEqual(book.calculation.calcMode, "auto")
        self.assertTrue(book.calculation.fullCalcOnLoad)
        self.assertTrue(book.calculation.forceFullCalc)
        cached = load_workbook(self.root / "model.xlsx", data_only=True)
        self.addCleanup(cached.close)
        self.assertIsNone(self.cells(cached, "net_debt", "net_debt")[3].value)

    def test_untrusted_text_cannot_become_excel_formulas(self):
        attack = '=HYPERLINK("https://example.invalid/leak","open")'
        self.record["discovery"]["company"]["legal_name"] = attack
        self.record["candidate"]["reporting_basis"] = attack
        for row in self.record["rows"]:
            row["label"] = row["definition"] = attack
        self.record["sources"][0]["title"] = attack
        self.record["sources"][0]["url"] = attack
        self.record["checks"][0]["detail"] = attack
        self.record["reviews"] = [{"stage": "model_review", "result": {
            "checks": [{"topic": "entity", "passed": True, "reason": attack}]}}]
        book = self.export()
        injected_cells = [cell for sheet in book for row in sheet for cell in row if cell.value == attack]
        self.assertGreater(len(injected_cells), 20)
        self.assertTrue(all(cell.data_type == "s" for cell in injected_cells))
        formulas = [cell.value for sheet in book for row in sheet for cell in row if cell.data_type == "f"]
        self.assertTrue(formulas)
        self.assertTrue(all(formula.startswith(("=IF(COUNT(", "=IFERROR(IF(ABS(")) for formula in formulas))

    def test_financial_layout_hides_audit_columns_and_keeps_forecasts_and_missing_periods_blank(self):
        sparse = copy.deepcopy(next(row for row in self.record["rows"] if row["id"] == "minority_interest"))
        sparse.update(id="adjustment", label="One-period adjustment", section="cash_flow",
                      values={"2025": 5000000}, observations=[sparse["observations"][1]],
                      unavailable=[{"period": "2024", "explanation": "The adjustment is not disclosed for this period.",
                                    "references": copy.deepcopy(sparse["definition_refs"])}])
        self.record["rows"].append(sparse)
        book = self.export()
        sparse_cells = self.cells(book, "cash_flow", "adjustment")
        self.assertIsNone(sparse_cells[3].value)
        self.assertIn("Unavailable: The adjustment is not disclosed for this period.", sparse_cells[3].comment.text)
        self.assertIn("Statements!R28", sparse_cells[3].comment.text)
        self.assertEqual(sparse_cells[4].value, 5)
        for section in SECTIONS:
            sheet = book[section]
            self.assertEqual(sheet.freeze_panes, "D5")
            self.assertFalse(sheet.sheet_view.showGridLines)
            forecast = [cell.column for cell in sheet[4] if "forecast (blank)" in str(cell.value)]
            self.assertEqual(len(forecast), 5)
            for row in sheet.iter_rows(min_row=5):
                for column in forecast:
                    self.assertIsNone(row[column - 1].value)
                    self.assertEqual(row[column - 1].fill.fgColor.rgb, "00FFF2CC")
            audit_column = next(cell.column_letter for cell in sheet[4] if cell.value == "Row ID")
            self.assertTrue(sheet.column_dimensions[audit_column].hidden)
            self.assertEqual(sheet.column_dimensions[audit_column].outlineLevel, 1)


class EvidenceTests(unittest.TestCase):
    def test_native_spreadsheet_numbers_use_displayed_precision(self):
        book = Workbook()
        sheet = book.active
        formats = (
            (1200, "0.00", 0.005),
            (1200, "#,##0.00", 0.005),
            (-1200, "0.00;[Red](0.00)", 0.005),
            (0.12, "0.00%", 0.00005),
        )
        for raw, number_format, _ in formats:
            sheet.append(["Synthetic amount", raw])
            sheet.cell(sheet.max_row, 2).number_format = number_format
        output = io.BytesIO()
        book.save(output)
        company = SyntheticCompany()
        with tempfile.TemporaryDirectory() as temporary:
            store = SourceStore(Path(temporary), fetcher=lambda url: (
                output.getvalue(), url, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
            store.add(company.source)
            for row, (raw, number_format, expected) in enumerate(formats, 1):
                with self.subTest(number_format=number_format):
                    reference = {"source_id": "annual", "unit_id": f"Sheet!R{row}",
                                 "number_index": 0, "number_format": "dot_decimal"}
                    token = store.read([reference])[0]["numbers"][0]
                    self.assertEqual(token["display_format"], number_format)
                    self.assertEqual(store.resolve(reference), raw)
                    self.assertAlmostEqual(_rounding_bound(reference, 1, store), expected)
                    self.assertAlmostEqual(_rounding_bound(reference, 1000000, store), expected * 1000000)

    def test_scaled_scientific_fraction_and_date_formats_cannot_be_accepted_as_plain_amounts(self):
        book = Workbook()
        sheet = book.active
        formats = ("#,##0,", "0,,", "0.00E+00", "# ?/?", "yyyy-mm-dd")
        for number_format in formats:
            sheet.append(["Synthetic amount", 1200])
            sheet.cell(sheet.max_row, 2).number_format = number_format
        output = io.BytesIO()
        book.save(output)
        company = SyntheticCompany()
        with tempfile.TemporaryDirectory() as temporary:
            store = SourceStore(Path(temporary), fetcher=lambda url: (
                output.getvalue(), url, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
            store.add(company.source)
            for row, number_format in enumerate(formats, 1):
                reference = {"source_id": "annual", "unit_id": f"Sheet!R{row}",
                             "number_index": 0, "number_format": "dot_decimal"}
                with self.subTest(number_format=number_format), self.assertRaises(ValueError):
                    # Date-formatted Excel values become datetime objects and are
                    # not numeric evidence; the other formats fail precision checks.
                    store.resolve(reference)
                    _rounding_bound(reference, 1, store)

    def test_archived_cells_are_exact_and_read_results_cannot_mutate_sources(self):
        company = SyntheticCompany(1)
        with tempfile.TemporaryDirectory() as temporary:
            store = SourceStore(Path(temporary), fetcher=company.fetch)
            source = store.add(company.source)
            row = next(row for row in company.rows if row["id"] == "revenue")
            reference = row["observations"][0]["reference"]
            self.assertEqual(store.resolve(reference), 1000)
            self.assertEqual(source["sha256"],
                             hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest())
            preview = store.catalog(max_units=1)[0]
            self.assertTrue(preview["catalog_truncated"])
            self.assertEqual(len(preview["units"]), 1)
            result = store.search("REVENUE")
            self.assertTrue(any(item["unit_id"] == reference["unit_id"] for item in result["matches"]))
            self.assertFalse(result["truncated"])
            read = store.read([reference])
            read[0]["numbers"][0]["raw"] = 999999
            self.assertEqual(store.resolve(row["observations"][1]["reference"]), 1100)
            for index in (-1, True, 10000):
                with self.subTest(index=index), self.assertRaises(ValueError):
                    store.resolve(dict(reference, number_index=index))
            with self.assertRaises(ValueError):
                store.add(dict(company.source, url="https://example.invalid/different.xlsx"))

    def test_html_retains_table_context_and_excludes_script_numbers(self):
        payload = (b"<html><script>99999</script><table><tr><th>Metric</th><th>FY2025</th></tr>"
                   b"<tr><td>Revenue EUR thousand</td><td>1.234,50</td></tr></table></html>")
        company = SyntheticCompany()
        with tempfile.TemporaryDirectory() as temporary:
            store = SourceStore(Path(temporary), fetcher=lambda url: (payload, url, "text/html"))
            store.add(company.source)
            unit = store.read([{"source_id": "annual", "unit_id": "chunk:1"}])[0]
            self.assertIn("Revenue EUR thousand", unit["text"])
            self.assertNotIn("99999", unit["text"])
            number = next(token for token in unit["numbers"] if token["raw"] == "1.234,50")
            self.assertEqual(store.resolve({"source_id": "annual", "unit_id": "chunk:1",
                                            "number_index": number["index"],
                                            "number_format": "comma_decimal"}), 1234.5)
        with patch("research_platform.evidence.build_opener") as opener:
            for url in ("file:///private", "http://example.invalid", "https://user:password@example.invalid"):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    download(url)
            opener.assert_not_called()


class AIAdapterTests(unittest.TestCase):
    def provider(self):
        return OpenAIProvider(api_key="SYNTHETIC-SECRET", models={
            "researcher": "test-researcher", "extractor": "test-extractor", "reviewer": "test-reviewer"})

    def complete(self, provider, response, *, web=False):
        stream = io.BytesIO(json.dumps(response).encode("utf-8"))
        with patch("research_platform.ai.urlopen", return_value=stream) as network:
            result = provider.complete(role="researcher", instructions="Synthetic instructions",
                                       payload={"synthetic": True},
                                       schema={"type": "object", "properties": {}, "required": [],
                                               "additionalProperties": False}, web=web)
            request = network.call_args.args[0]
        return result, json.loads(request.data)

    def test_env_file_is_literal_allowlisted_and_process_environment_wins(self):
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / ".env"
            literal_key = "SYNTHETIC-SECRET-${HOME}-$(Write-Output ignored)#literal"
            env_file.write_text(
                "# Synthetic offline settings only\n"
                f'OPENAI_API_KEY="{literal_key}"\n'
                "RESEARCH_MODEL='file-researcher'\n"
                "EXTRACTION_MODEL=file-extractor\n"
                "REVIEW_MODEL=file-reviewer\n", encoding="utf-8")
            with patch.dict(os.environ, {"RESEARCH_MODEL": "environment-researcher"}, clear=True), \
                    patch("os.system") as shell, patch("research_platform.ai.urlopen") as network:
                before = dict(os.environ)
                provider = OpenAIProvider.from_env(env_file)
                provider.validate_configuration()
                self.assertEqual(provider._api_key, literal_key)
                self.assertEqual(provider.models, {
                    "researcher": "environment-researcher", "extractor": "file-extractor",
                    "reviewer": "file-reviewer"})
                self.assertEqual(dict(os.environ), before)
                self.assertNotIn(literal_key, json.dumps(provider.metadata()))
                shell.assert_not_called()
                network.assert_not_called()

    def test_env_configuration_errors_do_not_reveal_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / ".env"
            with patch.dict(os.environ, {}, clear=True), patch("research_platform.ai.urlopen") as network:
                env_file.write_text("OPENAI_API_KEY=SYNTHETIC-SECRET\n", encoding="utf-8")
                provider = OpenAIProvider.from_env(env_file)
                with self.assertRaises(AIError) as raised:
                    provider.validate_configuration()
                self.assertIn("RESEARCH_MODEL", str(raised.exception))
                self.assertNotIn("SYNTHETIC-SECRET", str(raised.exception))
                for invalid in ('OPENAI_API_KEY="SYNTHETIC-SECRET\n',
                                'UNRECOGNIZED_SETTING=SYNTHETIC-SECRET\n',
                                'OPENAI_API_KEY=SYNTHETIC-SECRET\nOPENAI_API_KEY=duplicate\n'):
                    with self.subTest(invalid=invalid):
                        env_file.write_text(invalid, encoding="utf-8")
                        with self.assertRaises(AIError) as raised:
                            OpenAIProvider.from_env(env_file)
                        self.assertNotIn("SYNTHETIC-SECRET", str(raised.exception))
                self.assertEqual(dict(os.environ), {})
                network.assert_not_called()

    def test_adapter_requires_real_completed_search_and_strict_output(self):
        provider = self.provider()
        result, sent = self.complete(provider, {"status": "completed", "output": [
            {"type": "web_search_call", "status": "completed"},
            {"type": "message", "content": [{"type": "output_text", "text": "{}"}]}]}, web=True)
        self.assertEqual(result, {})
        self.assertEqual(sent["tools"], [{"type": "web_search"}])
        self.assertEqual(sent["tool_choice"], "required")
        self.assertTrue(sent["text"]["format"]["strict"])
        self.assertFalse(sent["store"])
        self.assertNotIn("SYNTHETIC-SECRET", json.dumps(provider.metadata()))
        with self.assertRaisesRegex(AIError, "web search"):
            self.complete(provider, {"status": "completed", "output": [
                {"type": "message", "content": [{"type": "output_text", "text": "{}"}]}]}, web=True)

    def test_request_diagnostics_have_unique_ids_and_preserve_reported_usage(self):
        provider = self.provider()
        response = {"status": "completed", "usage": {"input_tokens": 9, "output_tokens": 2},
                    "output": [{"type": "message", "content": [
                        {"type": "output_text", "text": "{}"}]}]}
        request_ids = []
        for _ in range(2):
            stream = io.BytesIO(json.dumps(response).encode("utf-8"))
            with patch("research_platform.ai.urlopen", return_value=stream) as network:
                result = provider.complete(role="researcher", instructions="test", payload={},
                                           schema={"type": "object"})
            self.assertEqual(result, {})
            network.assert_called_once()
            self.assertEqual(network.call_args.kwargs["timeout"], 120)
            diagnostics = provider.last_response["_transport"]
            request_id = diagnostics["client_request_id"]
            self.assertEqual(str(UUID(request_id)), request_id)
            headers = {name.lower(): value for name, value in network.call_args.args[0].header_items()}
            self.assertEqual(headers["x-client-request-id"], request_id)
            self.assertEqual(diagnostics["timeout_seconds"], 120)
            self.assertGreaterEqual(diagnostics["elapsed_seconds"], 0)
            self.assertNotIn("failure_kind", diagnostics)
            self.assertEqual(provider.last_response["usage"], response["usage"])
            self.assertNotIn("SYNTHETIC-SECRET", json.dumps(provider.last_response))
            request_ids.append(request_id)
        self.assertNotEqual(*request_ids)

    def test_transport_diagnostics_classify_failures_without_retry_or_secret_leaks(self):
        untrusted_codes = OSError("SYNTHETIC-SECRET")
        untrusted_codes.errno = "SYNTHETIC-SECRET"
        untrusted_codes.winerror = "SYNTHETIC-SECRET"
        cases = [
            (URLError(TimeoutError("SYNTHETIC-SECRET")), "timeout", False),
            (TimeoutError("SYNTHETIC-SECRET"), "timeout", True),
            (URLError(socket.gaierror(-2, "SYNTHETIC-SECRET")), "dns_error", False),
            (URLError(ssl.SSLCertVerificationError(1, "SYNTHETIC-SECRET")), "tls_certificate_error", False),
            (URLError(ssl.SSLError(1, "SYNTHETIC-SECRET")), "tls_error", False),
            (URLError(ConnectionResetError(10054, "SYNTHETIC-SECRET")), "connection_error", False),
            (URLError("SYNTHETIC-SECRET"), "network_error", False),
            (URLError(untrusted_codes), "network_error", False),
            (IncompleteRead(b"SYNTHETIC-SECRET", 20), "interrupted_response", True),
            (BadStatusLine("SYNTHETIC-SECRET"), "protocol_error", True),
        ]
        for error, expected, during_read in cases:
            with self.subTest(kind=expected, during_read=during_read):
                provider = self.provider()
                stream = io.BytesIO(b"")
                with patch("research_platform.ai.urlopen", return_value=stream,
                           side_effect=None if during_read else error) as network, \
                        patch.object(stream, "read", side_effect=error), \
                        self.assertRaises(AIError) as raised:
                    provider.complete(role="researcher", instructions="test", payload={},
                                      schema={"type": "object"})
                network.assert_called_once()
                self.assertEqual(provider.last_response["status"], "transport_error")
                diagnostics = provider.last_response["_transport"]
                self.assertEqual(diagnostics["failure_kind"], expected)
                self.assertEqual(str(UUID(diagnostics["client_request_id"])),
                                 diagnostics["client_request_id"])
                self.assertEqual(diagnostics["timeout_seconds"], 120)
                self.assertGreaterEqual(diagnostics["elapsed_seconds"], 0)
                for key in ("errno", "winerror"):
                    if key in diagnostics:
                        self.assertIs(type(diagnostics[key]), int)
                self.assertNotIn("usage", provider.last_response)
                usage = response_usage(provider.last_response, "gpt-6.1-sol")
                self.assertFalse(usage["reported"])
                self.assertIsNone(usage["estimated_cost_usd"])
                self.assertNotIn("SYNTHETIC-SECRET",
                                 str(raised.exception) + json.dumps(provider.last_response))

    def test_adapter_rejects_refusal_incomplete_and_malformed_results(self):
        provider = self.provider()
        failures = [
            {"status": "incomplete", "output": []},
            {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}]},
            {"status": "completed", "output": []},
            ["not an API object"],
        ]
        for invalid_json in ("not JSON", '{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}', "[]"):
            failures.append({"status": "completed", "output": [
                {"type": "message", "content": [{"type": "output_text", "text": invalid_json}]}]})
        for failure in failures:
            with self.subTest(failure=failure), self.assertRaises(AIError):
                self.complete(provider, failure)
        for read_failure in (None, BadStatusLine("SYNTHETIC-SECRET")):
            error = HTTPError("https://example.invalid/SYNTHETIC-SECRET", 429, "SYNTHETIC-SECRET", {}, None)
            with self.subTest(error_body_interrupted=read_failure is not None), \
                    patch("research_platform.ai.urlopen", side_effect=error) as network, \
                    patch.object(error, "read", return_value=b"", side_effect=read_failure):
                with self.assertRaises(AIError) as raised:
                    provider.complete(role="researcher", instructions="test", payload={},
                                      schema={"type": "object"})
                self.assertEqual(network.call_count, 1)
                self.assertNotIn("SYNTHETIC-SECRET", str(raised.exception))
                self.assertEqual(provider.last_response["status"], "transport_error")
                self.assertEqual(provider.last_response["http_status"], 429)
                self.assertEqual(provider.last_response["_transport"]["failure_kind"], "http_error")
                self.assertNotIn("SYNTHETIC-SECRET", json.dumps(provider.last_response))
                usage = response_usage(provider.last_response, "gpt-6.1-sol")
                self.assertFalse(usage["reported"])
                self.assertIsNone(usage["estimated_cost_usd"])


class AIUsageTests(unittest.TestCase):
    @staticmethod
    def response(model="gpt-6.1-sol", *, input_tokens=1000, output_tokens=100,
                 cached=0, cache_write=0, reasoning=0):
        return {"status": "completed", "model": model, "output": [], "usage": {
            "input_tokens": input_tokens,
            "input_tokens_details": {"cached_tokens": cached, "cache_write_tokens": cache_write},
            "output_tokens": output_tokens,
            "output_tokens_details": {"reasoning_tokens": reasoning},
            "total_tokens": input_tokens + output_tokens}}

    def test_standard_model_rates_partition_cache_without_rebilling_reasoning(self):
        for model, expected in (("gpt-6.1-sol", 0.0267), ("gpt-6-luna", 0.001345),
                                ("gpt-6-astra", 0.1345)):
            with self.subTest(model=model):
                response = self.response(model, input_tokens=10000, output_tokens=1000,
                                         cached=2000, cache_write=1000, reasoning=400)
                usage = response_usage(response, model)
                self.assertTrue(usage["reported"])
                self.assertEqual(usage["input_tokens"], 10000)
                self.assertEqual(usage["cached_input_tokens"], 2000)
                self.assertEqual(usage["cache_write_tokens"], 1000)
                self.assertEqual(usage["output_tokens"], 1000)
                self.assertEqual(usage["reasoning_tokens"], 400)
                self.assertEqual(usage["total_tokens"], 11000)
                self.assertAlmostEqual(usage["estimated_cost_usd"], expected)
                self.assertTrue(usage["pricing_date"])
                self.assertIn("openai.com", usage["pricing_source"])
        dated = response_usage(self.response("gpt-6.1-sol-2026-10-01"), "gpt-6.1-sol")
        self.assertEqual(dated["model"], "gpt-6.1-sol-2026-10-01")
        self.assertAlmostEqual(dated["estimated_cost_usd"], 0.003)

    def test_known_pricing_requires_an_exact_model_or_dated_snapshot(self):
        from research_platform.ai import has_known_pricing

        for model in ("gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra", "gpt-6.1-sol-2026-10-01"):
            self.assertTrue(has_known_pricing(model))
        for model in ("unpriced-model", "gpt-6.1-sol-extra", "prefix-gpt-6-luna", "", None):
            self.assertFalse(has_known_pricing(model))

    def test_long_context_threshold_changes_entire_request_above_272000(self):
        for model, rates in (("gpt-6.1-sol", (2, 0.1, 2.5, 10)),
                             ("gpt-6-luna", (0.1, 0.01, 0.125, 0.5)),
                             ("gpt-6-astra", (10, 1, 12.5, 50))):
            ordinary_rate, cached_rate, write_rate, output_rate = rates
            for count, input_multiplier, output_multiplier in ((272000, 1, 1), (272001, 2, 1.5)):
                with self.subTest(model=model, input_tokens=count):
                    usage = response_usage(self.response(model, input_tokens=count, output_tokens=1000,
                                                         cached=20000, cache_write=12000), model)
                    expected = (((count - 32000) * ordinary_rate + 20000 * cached_rate
                                 + 12000 * write_rate) * input_multiplier
                                + 1000 * output_rate * output_multiplier) / 1000000
                    self.assertAlmostEqual(usage["estimated_cost_usd"], expected)

    def test_search_actions_are_charged_and_unknown_pricing_stays_unknown(self):
        response = self.response()
        response["output"] = [{"type": "web_search_call", "status": "completed",
                               "action": {"type": action}}
                              for action in ("search", "open_page", "find_in_page")]
        usage = response_usage(response, "gpt-6.1-sol")
        self.assertEqual(usage["web_search_calls"], 1)
        self.assertEqual(usage["web_tool_calls"], 3)
        self.assertAlmostEqual(usage["estimated_cost_usd"], 0.013)
        unknown_cases = []
        for action in (None, {"type": "future_action"}):
            unknown = copy.deepcopy(response)
            unknown["output"].append({"type": "web_search_call", "action": action})
            unknown_cases.append(unknown)
        unknown_cases.extend((dict(response, service_tier="priority"),
                              dict(response, model="unpriced-model")))
        for unknown in unknown_cases:
            with self.subTest(unknown=unknown):
                usage = response_usage(unknown, "gpt-6.1-sol")
                self.assertTrue(usage["reported"])
                self.assertIsNone(usage["estimated_cost_usd"])

    def test_aggregate_retains_known_subtotal_and_does_not_fabricate_missing_usage(self):
        entries = [response_usage(self.response(model), model)
                   for model in ("gpt-6.1-sol", "gpt-6-luna", "unpriced-model")]
        missing = response_usage(None, "gpt-6.1-sol")
        self.assertFalse(missing["reported"])
        self.assertIsNone(missing["input_tokens"])
        self.assertIsNone(missing["output_tokens"])
        self.assertIsNone(missing["estimated_cost_usd"])
        total = aggregate_usage([{"usage": entries[0]}, entries[1], entries[2], missing])
        self.assertEqual(total["calls"], 4)
        self.assertEqual(total["reported_calls"], 3)
        self.assertEqual(total["missing_usage"], 1)
        self.assertEqual(total["missing_pricing"], 1)
        self.assertFalse(total["cost_is_complete"])
        self.assertEqual(total["input_tokens"], 3000)
        self.assertEqual(total["output_tokens"], 300)
        self.assertEqual(total["total_tokens"], 3300)
        self.assertAlmostEqual(total["estimated_cost_usd"], 0.00315)
        self.assertIn("gpt-6-luna", total["by_model"])
        self.assertIsNone(aggregate_usage([missing])["estimated_cost_usd"])
        for invalid in ({"input_tokens": -1, "output_tokens": 10},
                        {"input_tokens": True, "output_tokens": 10},
                        {"input_tokens": 10, "output_tokens": 10, "total_tokens": 19}):
            with self.subTest(invalid=invalid):
                usage = response_usage(dict(self.response(), usage=invalid), "gpt-6.1-sol")
                self.assertFalse(usage["reported"])
                self.assertIsNone(usage["estimated_cost_usd"])

    def test_stage_totals_include_revisions_and_charged_failed_calls(self):
        discovery = self.response(input_tokens=2000, output_tokens=300, reasoning=100)
        discovery["output"] = [{"type": "web_search_call", "status": "completed",
                                 "action": {"type": "search"}}]
        extraction = self.response(input_tokens=1000, output_tokens=200, cached=400,
                                   cache_write=100, reasoning=50)
        failed_review = dict(self.response(input_tokens=500, output_tokens=100,
                                         reasoning=90), status="incomplete")
        entries = [
            {"stage": stage, "attempt": attempt, "usage": response_usage(response, "gpt-6.1-sol")}
            for stage, attempt, response in (
                ("discover", 1, discovery), ("extract", 1, extraction),
                ("model_review", 1, failed_review), ("extract", 2, extraction))
        ]
        summary = aggregate_usage(entries)
        self.assertEqual(summary["calls"], 4)
        self.assertEqual(summary["total_tokens"], 5300)
        self.assertEqual(summary["reasoning_tokens"], 290)
        self.assertEqual(summary["total_tokens"], summary["input_tokens"] + summary["output_tokens"])
        self.assertEqual(summary["by_stage"]["extract"]["calls"], 2)
        self.assertEqual(summary["by_stage"]["extract"]["total_tokens"], 2400)
        self.assertEqual(summary["by_stage"]["extract"]["cached_input_tokens"], 800)
        self.assertEqual(summary["by_stage"]["model_review"]["total_tokens"], 600)
        self.assertEqual(summary["by_stage"]["discover"]["web_search_calls"], 1)
        self.assertAlmostEqual(summary["estimated_cost_usd"], 0.02558)
        for key in ("calls", "input_tokens", "output_tokens", "total_tokens", "web_search_calls"):
            self.assertEqual(summary[key], sum(stage[key] for stage in summary["by_stage"].values()))
        self.assertAlmostEqual(summary["estimated_cost_usd"], sum(
            stage["estimated_cost_usd"] for stage in summary["by_stage"].values()))
        self.assertTrue(summary["usage_is_complete"])
        self.assertTrue(all(stage["cost_is_complete"] for stage in summary["by_stage"].values()))

    def test_stage_gaps_distinguish_missing_tokens_from_missing_prices(self):
        known = response_usage(self.response(), "gpt-6.1-sol")
        unknown_price = response_usage(self.response("unpriced-model"), "unpriced-model")
        missing = response_usage(None, "gpt-6.1-sol")
        summary = aggregate_usage([
            {"stage": "extract", "usage": known}, {"stage": "extract", "usage": missing},
            {"stage": "model_review", "usage": unknown_price},
            {"stage": "discover", "usage": missing},
        ])
        extraction = summary["by_stage"]["extract"]
        self.assertEqual(extraction["total_tokens"], 1100)
        self.assertFalse(extraction["usage_is_complete"])
        self.assertFalse(extraction["cost_is_complete"])
        self.assertAlmostEqual(extraction["estimated_cost_usd"], 0.003)
        self.assertTrue(summary["by_stage"]["model_review"]["usage_is_complete"])
        self.assertFalse(summary["by_stage"]["model_review"]["cost_is_complete"])
        self.assertIsNone(summary["by_stage"]["model_review"]["estimated_cost_usd"])
        self.assertIsNone(summary["by_stage"]["discover"]["estimated_cost_usd"])
        self.assertFalse(summary["usage_is_complete"])
        self.assertEqual(summary["missing_usage"], 2)
        self.assertEqual(summary["missing_pricing"], 1)
        self.assertAlmostEqual(summary["estimated_cost_usd"], 0.003)
        self.assertIn("unspecified", aggregate_usage([known])["by_stage"])

    def test_terminal_usage_shows_total_and_stage_subtotals_without_zero_for_unknown(self):
        from research_platform.ai import format_stage_usage, format_usage

        known = response_usage(self.response(reasoning=80), "gpt-6.1-sol")
        missing = response_usage(None, "gpt-6.1-sol")
        summary = aggregate_usage([
            {"stage": "extract", "usage": known}, {"stage": "extract", "usage": missing},
            {"stage": "model_review", "usage": missing},
        ])
        total_line = format_usage(summary)
        stage_lines = format_stage_usage(summary).splitlines()
        self.assertIn("Reported token subtotal: 1,100 total", total_line)
        self.assertIn("2 call(s) missing usage", total_line)
        self.assertIn("80 reasoning included", total_line)
        self.assertIn("extract: 2 call(s); 1,100 total tokens", stage_lines[0])
        self.assertIn("subtotal, 1 call(s) missing usage", stage_lines[0])
        self.assertIn("$0.003000 USD (incomplete)", stage_lines[0])
        self.assertIn("model_review: 1 call(s); tokens unavailable", stage_lines[1])
        self.assertIn("estimated cost unknown (incomplete)", stage_lines[1])
        self.assertNotIn("$0.000000", stage_lines[1])

    def test_rejected_api_responses_still_retain_billable_usage(self):
        adapter = AIAdapterTests()
        provider = adapter.provider()
        for rejected in (
            dict(self.response("gpt-6-luna"), status="incomplete"),
            dict(self.response("gpt-6-luna"), output=[{"type": "message", "content": [
                {"type": "refusal", "refusal": "Synthetic refusal"}]}]),
        ):
            with self.subTest(status=rejected["status"]):
                with self.assertRaises(AIError):
                    adapter.complete(provider, rejected)
                usage = response_usage(provider.last_response, "gpt-6-luna")
                self.assertTrue(usage["reported"])
                self.assertEqual(usage["total_tokens"], 1100)
                self.assertAlmostEqual(usage["estimated_cost_usd"], 0.00015)


if __name__ == "__main__":
    unittest.main()
