"""Locate this checkout and read saved run records."""

import json
import os
from pathlib import Path


def find_project_root(start: Path | None = None) -> Path:
    """Find the nearest checkout containing the package and its build definition."""
    origin = (start or Path.cwd()).resolve()
    for candidate in (origin, *origin.parents):
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "forecasting_engine" / "company_initiation" / "__init__.py"
        ).is_file():
            return candidate
    raise ValueError("Open a terminal in the project folder and try again.")


def resolve_data_path(root: Path, path: str | Path) -> Path:
    """Locate an archive moved from the former local_store layout.

    Saved run records remain unchanged. Only missing paths under this project's
    old data root can be redirected, and the replacement must already exist.
    Company names and file contents have no role in this storage adapter.
    """
    def ordinary_path(value):
        text = str(value)
        if os.name == 'nt':
            if text.startswith('\\\\?\\UNC\\'):
                text = '\\\\' + text[8:]
            elif text.startswith('\\\\?\\'):
                text = text[4:]
        return Path(text)

    root = ordinary_path(root).resolve()
    original = ordinary_path(path)
    original = (original if original.is_absolute() else root / original).resolve()
    if original.exists():
        return original
    try:
        relative = original.relative_to(root / 'local_store')
    except ValueError:
        return original
    candidates = [root / 'data_store' / relative, root / 'data_store' / 'company_data' / relative]
    existing = [candidate.resolve() for candidate in candidates if candidate.exists()]
    if len(existing) > 1:
        raise ValueError('Ambiguous relocated data path: ' + str(original))
    return existing[0] if existing else original


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path.name}.")
    return value


