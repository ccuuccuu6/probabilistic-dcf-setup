"""Locate this checkout and validate its deliberately minimal configuration."""

import json
import re
from pathlib import Path


def find_project_root(start: Path | None = None) -> Path:
    """Find the nearest parent containing this project's config and pyproject."""
    origin = (start or Path.cwd()).resolve()
    for candidate in (origin, *origin.parents):
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "configs" / "shared_factors.json"
        ).is_file():
            return candidate
    raise ValueError("Open a terminal in the extracted project folder and try again.")


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path.name}.")
    return value


def validate_configs(root: Path) -> tuple[dict, list[dict]]:
    """Reject missing topics, duplicate IDs, and accidental exposure guesses."""
    factors = read_json(root / "configs" / "shared_factors.json")
    topics = factors.get("topics")
    if factors.get("schema_version") != 1 or not isinstance(topics, dict):
        raise ValueError("shared_factors.json needs schema_version=1 and a topics object.")
    if not {"coffee", "fx"}.issubset(topics):
        raise ValueError("The starter configuration requires coffee and fx topics.")
    if not all(isinstance(value, dict) for value in topics.values()):
        raise ValueError("Every shared topic must have a configuration object.")
    if topics["fx"].get("level_convention") != "units_of_currency_per_one_USD":
        raise ValueError("This demonstration requires the documented FX level convention.")
    if topics["fx"].get("numeraire") != "USD":
        raise ValueError("The demonstration requires USD as its numeraire.")
    if topics["fx"].get("quote_convention") != "units_of_quote_currency_per_one_base_currency":
        raise ValueError("The demonstration requires quote-currency units per base-currency unit.")
    companies = []
    identifiers = set()
    for path in sorted((root / "configs" / "companies").glob("*.json")):
        company = read_json(path)
        identifier = company.get("company_id")
        if not isinstance(identifier, str) or not re.fullmatch("[a-z][a-z0-9_]*", identifier):
            raise ValueError(f"Invalid company_id in {path.name}.")
        if identifier in identifiers:
            raise ValueError(f"Duplicate company_id: {identifier}.")
        identifiers.add(identifier)
        if company.get("schema_version") != 1:
            raise ValueError(f"Unsupported schema_version in {path.name}.")
        currency = company.get("reporting_currency", "")
        if not isinstance(currency, str) or not re.fullmatch("[A-Z]{3}", currency):
            raise ValueError(f"Expected a three-letter currency in {path.name}.")
        company_topics = company.get("research_topics")
        if not isinstance(company_topics, list) or not all(
            isinstance(topic, str) and topic in topics for topic in company_topics
        ):
            raise ValueError(f"Unknown or missing research topics in {path.name}.")
        if company.get("exposure_mappings") != []:
            raise ValueError(
                f"{path.name}: real exposure mappings need a future validated schema; "
                "keep this setup template empty."
            )
        companies.append(company)
    if not companies:
        raise ValueError("No company configurations found in configs/companies/.")
    return factors, companies



