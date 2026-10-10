"""Run with python -m research_platform from the project directory."""

import argparse
import platform
import shutil
import sys

from research_platform.data.project import create_local_paths, find_project_root, validate_configs
from research_platform.workflows.demo import run_fx_demo


def main() -> int:
    parser = argparse.ArgumentParser(description="Local setup checks and synthetic shared-FX demo.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Validate configuration and prepare local runtime folders")
    demo = commands.add_parser("demo-fx", help="Write five illustrative shared-FX cases to a fresh folder")
    demo.add_argument("--seed", type=int, default=42)
    arguments = parser.parse_args()
    try:
        root = find_project_root()
        if arguments.command == "doctor":
            _, companies = validate_configs(root)
            paths = create_local_paths(root)
            print(f"Project: {root}")
            print(f"Python: {platform.python_version()} ({sys.executable})")
            print(f"Virtual environment: {'active' if sys.prefix != sys.base_prefix else 'not active; recommended'}")
            print(f"Git executable: {'available' if shutil.which('git') else 'not on PATH; install Git for publishing later'}")
            print(f"Company configurations: {', '.join(c['company_id'] for c in companies)}")
            print("Shared topics: coffee, fx (routing only; no real exposure estimates)")
            for name, path in paths.items():
                print(f"{name}: {path}")
            print("PASS: setup configuration is valid. No data feeds or financial model are connected.")
        else:
            directory = run_fx_demo(root, arguments.seed)
            print("SYNTHETIC DEMO ONLY: arbitrary sample states, not calibrated forecasts.")
            print(f"Saved: {directory}")
            print("Open fictional_company_translation.csv in Excel; inputs.json and manifest.json record the run.")
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

