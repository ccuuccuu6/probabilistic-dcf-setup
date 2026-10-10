"""Meaningful arithmetic and reproducibility checks for the small setup demo."""

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from research_platform.data.project import find_project_root, validate_configs
from research_platform.factors.fx import cross_rate, generate_currency_states
from research_platform.reporting.files import sha256
from research_platform.workflows.demo import run_fx_demo


PROJECT = Path(__file__).resolve().parents[1]


class CurrencyTests(unittest.TestCase):
    def setUp(self):
        self.states = generate_currency_states(seed=42)

    def test_inverse_quotes(self):
        for state in self.states:
            for base in state:
                for quote in state:
                    self.assertAlmostEqual(
                        cross_rate(state, base, quote) * cross_rate(state, quote, base), 1.0)

    def test_triangular_consistency(self):
        for state in self.states:
            self.assertAlmostEqual(
                cross_rate(state, "EUR", "USD") * cross_rate(state, "USD", "CHF"),
                cross_rate(state, "EUR", "CHF"))

    def test_repeated_seed_and_changed_seed(self):
        self.assertEqual(self.states, generate_currency_states(42))
        self.assertNotEqual(self.states, generate_currency_states(43))

    def test_invalid_levels_rejected(self):
        for state in ({"USD": 1, "EUR": 0}, {"USD": 1, "EUR": float("nan")}, {"USD": 2}):
            with self.assertRaises(ValueError):
                cross_rate(state, "USD", "USD")


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        shutil.copytree(PROJECT / "configs", self.root / "configs")
        shutil.copytree(PROJECT / "src", self.root / "src", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(PROJECT / "pyproject.toml", self.root / "pyproject.toml")

    def tearDown(self):
        self.temporary.cleanup()

    def test_root_from_subdirectory(self):
        self.assertEqual(find_project_root(self.root / "configs" / "companies"), self.root)

    def test_company_templates_are_not_exposures(self):
        _, companies = validate_configs(self.root)
        self.assertTrue(all(company["exposure_mappings"] == [] for company in companies))

    def test_unknown_research_topic_rejected(self):
        path = self.root / "configs" / "companies" / "nestle.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["research_topics"].append("not_configured")
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_configs(self.root)

    def test_runs_repeat_values_without_overwriting(self):
        first = run_fx_demo(self.root, 42)
        before = {file.name: file.read_bytes() for file in first.iterdir()}
        second = run_fx_demo(self.root, 42)
        self.assertNotEqual(first, second)
        self.assertEqual(before, {file.name: file.read_bytes() for file in first.iterdir()})
        for name in ("inputs.json", "currency_levels.csv", "cross_rates.csv", "fictional_company_translation.csv"):
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())

    def test_shared_scenario_used_for_both_company_examples(self):
        directory = run_fx_demo(self.root)
        with (directory / "currency_levels.csv").open(newline="", encoding="utf-8") as handle:
            levels = list(csv.DictReader(handle))
        with (directory / "fictional_company_translation.csv").open(newline="", encoding="utf-8") as handle:
            translations = list(csv.DictReader(handle))
        self.assertEqual(len(translations), 10)
        for scenario_id in range(1, 6):
            state = {r["currency"]: float(r["currency_units_per_USD"])
                     for r in levels if int(r["scenario_id"]) == scenario_id}
            rows = [r for r in translations if int(r["scenario_id"]) == scenario_id]
            self.assertEqual(len(rows), 2)
            by_currency = {r["reporting_currency"]: float(r["translated_amount"]) for r in rows}
            self.assertAlmostEqual(by_currency["CHF"] / by_currency["USD"], state["CHF"])
            self.assertAlmostEqual(by_currency["USD"], 100 / state["EUR"])

    def test_manifest_freezes_inputs_and_hashes(self):
        directory = run_fx_demo(self.root, seed=7)
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["seed"], 7)
        self.assertTrue(manifest["synthetic"])
        self.assertTrue(manifest["source_sha256"])
        for name, expected in manifest["sha256"].items():
            self.assertEqual(sha256(directory / name), expected)


if __name__ == "__main__":
    unittest.main()
