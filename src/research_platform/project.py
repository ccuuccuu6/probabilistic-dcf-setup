"""Locate this checkout and read saved run records."""

import json
from pathlib import Path


def find_project_root(start: Path | None = None) -> Path:
    """Find the nearest checkout containing the package and its build definition."""
    origin = (start or Path.cwd()).resolve()
    for candidate in (origin, *origin.parents):
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "src" / "research_platform" / "__init__.py"
        ).is_file():
            return candidate
    raise ValueError("Open a terminal in the project folder and try again.")


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path.name}.")
    return value


