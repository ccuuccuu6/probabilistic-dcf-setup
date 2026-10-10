"""Run with python -m research_platform from the project directory."""

import argparse
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, version
import platform
import shutil
import sys
from threading import Event, Thread
from time import monotonic

from research_platform.project import find_project_root


class TerminalProgress:
    """Print progress and keep one elapsed-time line live during an API request."""

    def __init__(self, stream=None):
        self.stream = stream if stream is not None else sys.stdout

    def __call__(self, message):
        print(message, file=self.stream, flush=True)

    @contextmanager
    def call_timer(self, label):
        started = monotonic()
        stopped = Event()
        interactive = self.stream.isatty()

        def render():
            elapsed = max(0, int(monotonic() - started))
            minutes, seconds = divmod(elapsed, 60)
            self.stream.write(f"\r{label}: waiting {minutes:02d}:{seconds:02d}")
            self.stream.flush()

        def tick():
            while not stopped.wait(1):
                render()

        timer = None
        if interactive:
            render()
            timer = Thread(target=tick, name="ai-call-timer", daemon=True)
            timer.start()
        completed = False
        try:
            yield
            completed = True
        finally:
            stopped.set()
            if timer is not None:
                timer.join()
            elapsed = max(0.0, monotonic() - started)
            outcome = "completed" if completed else "failed"
            prefix = "\r" if interactive else ""
            self(f"{prefix}{label}: {outcome} after {elapsed:.1f}s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Research, check and export a company's historical financial model.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check the project, Python and installed dependencies without API calls")
    api_check = commands.add_parser("api-check", help="Make one small paid API call and show reported token usage")
    api_check.add_argument("--role", choices=["researcher", "extractor", "reviewer"], default="extractor")
    initiate = commands.add_parser("initiate", help="Research and check a company's historical model using configured AI APIs")
    initiate.add_argument("company", help="Company name, ideally with ticker/exchange/country")
    initiate.add_argument("--years", nargs="+", type=int,
                          help="Fiscal years including reported quarters, halves and YTD; default: latest two complete fiscal years")
    initiate.add_argument("--forecast-years", type=int, default=5, help="Number of empty forecast columns (default: 5)")
    initiate.add_argument("--budget-usd", type=float, default=20.0,
                          help="Stop at this cumulative estimated USD cost (default and maximum: 20); last request can overshoot")
    continuation = initiate.add_mutually_exclusive_group()
    continuation.add_argument("--resume", metavar="RUN", help="Resume a specific latest matching run directory; default: automatic")
    continuation.add_argument("--fresh", action="store_true", help="Explicitly start new research instead of reusing saved progress")
    arguments = parser.parse_args()
    try:
        root = find_project_root()
        if arguments.command == "doctor":
            if sys.version_info < (3, 11):
                raise ValueError("Python 3.11 or newer is required")
            print(f"Project: {root}")
            print(f"Python: {platform.python_version()} ({sys.executable})")
            print(f"Virtual environment: {'active' if sys.prefix != sys.base_prefix else 'not active; recommended'}")
            print(f"Git executable: {'available' if shutil.which('git') else 'not on PATH; install Git for publishing later'}")
            try:
                for package in ("openpyxl", "pypdf"):
                    print(f"{package}: {version(package)}")
            except PackageNotFoundError as error:
                raise ValueError("A required package is missing; install the project with python -m pip install -e .") from error
            print(f"Saved runs: {root / 'outputs'}")
            print("PASS: project found and required Python packages are installed. No company config is needed. Doctor does not read credentials or contact OpenAI.")
        elif arguments.command == "api-check":
            from research_platform.ai import OpenAIProvider, aggregate_usage, format_usage, response_usage
            provider = OpenAIProvider.from_env(root / ".env")
            provider.validate_configuration()
            provider.max_output_tokens = 1024
            model = provider.metadata()["models"][arguments.role]
            print(f"Making one small structured-output API test with {model}...", flush=True)
            try:
                with TerminalProgress().call_timer(f"API check ({model})"):
                    result = provider.complete(
                        role=arguments.role, instructions="Connection test only. Return the JSON object with ok set to true.",
                        payload={"purpose": "Verify API access and measure this request's usage."},
                        schema={"type": "object", "properties": {"ok": {"type": "boolean"}},
                                "required": ["ok"], "additionalProperties": False})
                if result != {"ok": True}:
                    raise ValueError("API responded, but the connection test returned an unexpected value")
                print("PASS: API access and structured output work. This does not test financial extraction or web search.")
            finally:
                print(format_usage(aggregate_usage([response_usage(provider.last_response, model)])))
        else:
            from research_platform.initiation import initiate_company
            from research_platform.project import read_json
            print("Researching annual and reported interim accounts through configured AI APIs; forecast columns remain empty.", flush=True)
            print(f"Estimated cost stop: ${arguments.budget_usd:.2f}. Usage is reported after each request; the last request can cross the threshold.", flush=True)
            directory = initiate_company(root, arguments.company, years=arguments.years,
                                         forecast_years=arguments.forecast_years, max_cost_usd=arguments.budget_usd,
                                         progress=TerminalProgress(), resume=arguments.resume, fresh=arguments.fresh)
            record = read_json(directory / "record.json")
            passed = sum(check["passed"] for check in record["checks"])
            print(f"Checks: {passed}/{len(record['checks'])} passed. Status: {record['status']}")
            print(f"Run record: {directory / 'record.json'}")
            from research_platform.ai import format_stage_usage, format_usage
            print("Total usage: " + format_usage(record["usage"]))
            print(format_stage_usage(record["usage"]))
            if record["status"] != "accepted":
                for issue in record["issues"]:
                    print(f"Unresolved: {issue}")
                return 1
            print(f"Open: {directory / 'model.xlsx'}")
            print("Read 'Start here', 'Checks' and 'AI reviews'. Accepted means these checks passed, not an audit or error-free guarantee.")
    except KeyboardInterrupt:
        print("Interrupted. Saved initiation progress is preserved; repeat the same command to resume. "
              "A request interrupted in flight may have an unknown charge and block further spending.", file=sys.stderr)
        return 130
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        for note in getattr(error, "__notes__", []):
            print(note, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

