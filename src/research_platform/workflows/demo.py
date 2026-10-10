"""Run a synthetic shared-FX demonstration and freeze its input/output files."""

import platform
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from research_platform import __version__
from research_platform.data.project import create_local_paths, validate_configs
from research_platform.factors.fx import SYNTHETIC_LEVELS, cross_rate, generate_currency_states
from research_platform.models.translation import translate_amount
from research_platform.reporting.files import sha256, write_csv, write_json


def run_fx_demo(root: Path, seed: int = 42) -> Path:
    """Create a fresh run directory; never write over a prior run."""
    factors, companies = validate_configs(root)
    paths = create_local_paths(root)
    run_id = "run_" + uuid4().hex
    directory = paths["outputs"] / run_id
    directory.mkdir(exist_ok=False)
    examples = [
        {"company_id": "fictional_company_a", "reporting_currency": "CHF",
         "local_currency": "EUR", "local_amount": 100.0},
        {"company_id": "fictional_company_b", "reporting_currency": "USD",
         "local_currency": "EUR", "local_amount": 100.0},
    ]
    inputs = {
        "synthetic": True,
        "purpose": "Setup/mechanics demonstration; not a forecast or investment analysis.",
        "seed": seed,
        "scenario_count": 5,
        "period": "single_illustrative_period",
        "level_convention": "units_of_currency_per_one_USD",
        "baseline_levels": SYNTHETIC_LEVELS,
        "generator": "Python random.Random; independent uniform +/-5% level perturbations; USD=1",
        "limitation": "Arbitrary synthetic perturbations demonstrate coherent arithmetic, not calibrated probabilities or economic dependencies.",
        "fictional_examples": examples,
        "shared_factor_config_snapshot": factors,
        "company_config_snapshots_not_used_in_calculations": companies,
    }
    write_json(directory / "inputs.json", inputs)
    states = generate_currency_states(seed, 5, inputs["baseline_levels"])
    levels = []
    pairs = []
    translations = []
    for scenario_id, state in enumerate(states, start=1):
        for currency, level in sorted(state.items()):
            levels.append({"synthetic": True, "scenario_id": scenario_id,
                           "currency": currency, "currency_units_per_USD": level})
        for base in sorted(state):
            for quote in sorted(state):
                pairs.append({"synthetic": True, "scenario_id": scenario_id,
                              "base_currency": base, "quote_currency": quote,
                              "quote_units_per_base_unit": cross_rate(state, base, quote)})
        for example in examples:
            translations.append({
                "synthetic": True, "scenario_id": scenario_id, **example,
                "reporting_units_per_local_unit": cross_rate(
                    state, example["local_currency"], example["reporting_currency"]),
                "translated_amount": translate_amount(
                    example["local_amount"], example["local_currency"],
                    example["reporting_currency"], state),
            })
    write_csv(directory / "currency_levels.csv", levels)
    write_csv(directory / "cross_rates.csv", pairs)
    write_csv(directory / "fictional_company_translation.csv", translations)
    file_hashes = {path.name: sha256(path) for path in sorted(directory.iterdir())}
    source_hashes = {
        path.relative_to(root).as_posix(): sha256(path)
        for path in sorted((root / "src" / "research_platform").rglob("*.py"))
    }
    write_json(directory / "manifest.json", {
        "schema_version": 1, "run_id": run_id, "synthetic": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "package_version": __version__, "python_version": platform.python_version(),
        "seed": seed, "scenario_count": 5,
        "sha256": file_hashes, "source_sha256": source_hashes,
        "status": "completed_synthetic_demo",
        "note": "This local manifest detects file changes but is not a tamper-proof production forecast ledger.",
    })
    return directory

