"""Run with python -m company_initiation from the project directory."""

import argparse
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, version
import platform
import shutil
import sys
from threading import Event, Thread
from time import monotonic

from company_initiation.shared_project import find_project_root


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
    evaluate = commands.add_parser("evaluate", help="Evaluate saved backend model and export its typed input contract; zero AI and no Excel")
    evaluate.add_argument("run")
    evaluate.add_argument("--assumptions", help="Typed dated financial_assumptions_v1 JSON payload")
    evaluate.add_argument("--valuation-assumptions", help="Typed valuation-v1 scenario payload; no AI calls")
    saved_review = commands.add_parser("review-saved", help="Export saved partial work or recalculate saved forecasts without AI/credentials")
    saved_review.add_argument("run")
    saved_review.add_argument("--assumptions", help="Changed JSON driver inputs; requires a completed saved forecast specification")
    saved_review.add_argument("--recalculate", action="store_true")
    refresh = commands.add_parser("refresh-fx", help="Refresh shared FX and recalculate a saved model; zero AI calls")
    refresh.add_argument("run", help="Saved run directory or its name in outputs")
    refresh.add_argument("--fx-source", help="Override the stable shared FX path in pyproject.toml")
    refresh.add_argument("--fx-database", help="Shared SQLite database; no broker requests are made")
    refresh.add_argument("--snapshot", help="Use an exact immutable FX snapshot ID")
    refresh.add_argument("--fx-as-of", help="Explicit FX timestamp with timezone; defaults to now, independently of company history")
    refresh.add_argument("--model-inputs", help="Versioned company exposure/policy configuration; historical facts must remain unchanged")
    for name,description in (("fx-import","Import a supplied FX workbook once into the shared database"),
                             ("fx-update","Read-only incremental IBKR FX update"),
                             ("fx-update-ecb","Update ECB reference fixings from its official 90-day XML"),
                             ("fx-status","Show shared FX database coverage and freshness")):
        command=commands.add_parser(name,help=description)
        command.add_argument("--database",help="Shared SQLite path; defaults to pyproject.toml")
        if name=="fx-import":command.add_argument("workbook",nargs="?")
        if name=="fx-update":
            command.add_argument("--host");command.add_argument("--port",type=int);command.add_argument("--client-id",type=int)
            command.add_argument("--pairs",nargs="+");command.add_argument("--overlap-days",type=int)
            command.add_argument("--max-recent-days",type=int);command.add_argument("--session-timezone")
            command.add_argument("--diagnostic",action="store_true")
    export = commands.add_parser("export", help="Re-export and recalculate saved validated inputs; zero AI calls")
    export.add_argument("run", help="Saved run directory or its name in outputs")
    export.add_argument("--rebuild", action="store_true", help="Recompile saved company evidence with current shared calculation code; no new source acceptance")
    export.add_argument("--valuation-date", help="Explicit DCF date, YYYY-MM-DD; defaults to the saved model date")
    update = commands.add_parser("update", help="Discover newer official actuals, preserve history and rebuild the saved company model")
    update.add_argument("run", help="Saved run directory or its name in outputs")
    update.add_argument("--as-of", help="Information date, YYYY-MM-DD; defaults to today")
    construct = commands.add_parser("construct", help="Construct history, company drivers and executable temporary forecasts from local originals")
    construct.add_argument("company")
    construct.add_argument("--as-of", help="Model information date, YYYY-MM-DD; defaults to today's date and is saved")
    construct.add_argument("--valuation-date", help="DCF date, YYYY-MM-DD; defaults to the model information date")
    construct.add_argument("--valuation-assumptions", help="Optional typed valuation-v1 overrides; normal construction generates its inputs")
    construct.add_argument("--historical-vintage", action="store_true", help="Require every source to have verified publication by the as-of date")
    construct.add_argument("--sources", required=True)
    construct.add_argument("--model-inputs", help="Saved sourced company research specification for the integrated segment/three-statement workflow")
    construct.add_argument("--resume", metavar="RUN", help="Explicit verified ancestor for integrated construction recovery; all newer charges remain in the cumulative ledger")
    construct.add_argument("--fx-source", help="Local shared FX workbook; source dates and actual/estimate status are preserved")
    construct.add_argument("--fx-database", help="Shared FX database snapshot, consumed without broker downloads")
    construct.add_argument("--reference-workbook", help="Local analyst workbook used as architecture/presentation reference; never a company numeric input")
    construction_history = construct.add_mutually_exclusive_group()
    construction_history.add_argument("--years", nargs="+", type=int)
    construction_history.add_argument("--history-years", type=int, default=10)
    construct.add_argument("--forecast-years", type=int, default=5)
    construct.add_argument("--budget-usd", type=float, default=20.)
    construct.add_argument("--fresh", action="store_true")
    construct.add_argument("--recalculate", action="store_true", help="Use hidden Microsoft Excel if available, compare formula outputs with Python")
    construct.add_argument("--escalation-evidence", help="Stage-specific evidence supporting an explicitly configured non-Luna model")
    api_check = commands.add_parser("api-check", help="Make one small paid API call and show reported token usage")
    api_check.add_argument("--role", choices=["researcher", "extractor", "reviewer"], default="extractor")
    initiate = commands.add_parser("initiate", help="Build and check historical accounts from a local company archive using configured AI APIs")
    initiate.add_argument("company", help="Company name, ideally with ticker/exchange/country")
    initiate.add_argument("--sources", required=True, help="Local company archive containing financial_reports/, visible_alpha/ and optional transcripts/")
    history = initiate.add_mutually_exclusive_group()
    history.add_argument("--years", nargs="+", type=int,
                         help="Explicit fiscal years, including reported quarters, halves and YTD")
    history.add_argument("--history-years", type=int, default=10,
                         help="Latest fully reported fiscal years evidenced in the archive (default: 10)")
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
                for package in ("openpyxl", "pypdf", "xlrd"):
                    print(f"{package}: {version(package)}")
            except PackageNotFoundError as error:
                raise ValueError("A required package is missing; install the project with python -m pip install -e .") from error
            print(f"Saved runs: {root / 'outputs'}")
            print("PASS: project found and required Python packages are installed. No company config is needed. Doctor does not read credentials or contact OpenAI.")
        elif arguments.command == "evaluate":
            from company_initiation.forecast_construction.periods import evaluate_saved_model
            directory=evaluate_saved_model(root,arguments.run,arguments.assumptions,valuation_payload_file=arguments.valuation_assumptions)
            print(f"Backend evaluation: {directory}")
            print("No AI calls or Excel. Reported history and financial formulas are unchanged.")
            from company_initiation.shared_project import read_json
            evaluation=read_json(directory/'evaluation.json')
            print('Status: '+evaluation['status'])
            return 0 if evaluation['status']=='scenario_evaluated_provisional' else 1
        elif arguments.command == "api-check":
            from company_initiation.shared_ai import OpenAIProvider, aggregate_usage, format_usage, response_usage
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
        elif arguments.command in ("fx-import","fx-update","fx-update-ecb","fx-status"):
            from shared_FX.fx_store import fx_command
            return fx_command(root,arguments)
        elif arguments.command == "review-saved":
            from company_initiation.forecast_construction.construction import review_saved
            directory = review_saved(root, arguments.run, assumptions_file=arguments.assumptions,
                                     recalculate=arguments.recalculate)
            print(f"Offline review workbook: {directory / 'model.xlsx'}")
            print("No API calls. Missing forecast stages remain unmodelled; source/AI acceptance is unchanged.")
        elif arguments.command in ("refresh-fx", "export", "update"):
            from company_initiation.forecast_construction.workflow import offline_export
            import tomllib
            defaults = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")).get("tool", {}).get("research-platform", {})
            fx = None;fx_database=None
            if arguments.command == "refresh-fx":
                fx = arguments.fx_source
                if fx and arguments.fx_database:raise ValueError('Choose the shared FX database or the legacy workbook adapter, not both')
                fx_database=arguments.fx_database or (None if fx else defaults.get('fx-database'))
                if not fx and not fx_database:raise ValueError("Import the shared FX database first with fx-import")
                from pathlib import Path
                fx = (Path(fx) if Path(fx).is_absolute() else root / fx) if fx else None
            if arguments.command == "update":
                from company_initiation.historic_construction.workflow import update_company_inputs
                from company_initiation.forecast_construction.integrated import construct_integrated
                from company_initiation.shared_project import read_json
                from datetime import date
                from pathlib import Path
                parent = Path(arguments.run)
                if not parent.is_absolute() and not parent.exists():parent=root/"outputs"/parent
                config=read_json(parent/"record.json")["configuration"]
                as_of=arguments.as_of or date.today().isoformat()
                inputs=update_company_inputs(root,parent,as_of=as_of,progress=TerminalProgress())
                directory=construct_integrated(root,config['company'],config['sources'],inputs,
                    fx_database=root/defaults['fx-database'] if defaults.get('fx-database') else None,as_of=as_of,
                    forecast_years=config.get('forecast_years',5),include_valuation=True,progress=TerminalProgress())
            else:
                directory = offline_export(root, arguments.run, fx_file=fx,
                    fx_database=root/fx_database if fx_database else None,
                    snapshot_id=getattr(arguments,'snapshot',None),fx_as_of=getattr(arguments,'fx_as_of',None),inputs_file=getattr(arguments,'model_inputs',None),
                    include_valuation=True,valuation_date=getattr(arguments,'valuation_date',None),rebuild=getattr(arguments,'rebuild',False),progress=TerminalProgress())
            print(f"Workbook: {directory / 'model.xlsx'}")
            from company_initiation.shared_project import read_json
            return 0 if read_json(directory / "record.json")["status"] == "complete_provisional" else 1
        elif arguments.command == "construct":
            from company_initiation.shared_project import read_json
            from company_initiation.shared_ai import format_usage, format_stage_usage
            from pathlib import Path
            print("Constructing a provisional model from company originals. Python reads source numbers; unknown inputs remain missing.", flush=True)
            if arguments.model_inputs:
                from company_initiation.forecast_construction.integrated import construct_integrated
                from company_initiation.historic_construction.workflow import ensure_company_history_research
                from company_initiation.dcf_construction.workflow import construct_valuation
                inputs=ensure_company_history_research(root,arguments.company,arguments.sources,arguments.model_inputs,
                    budget_usd=arguments.budget_usd,as_of=arguments.as_of,progress=TerminalProgress())
                directory = construct_integrated(root, arguments.company, arguments.sources, inputs,
                    reference_workbook=arguments.reference_workbook, budget_usd=arguments.budget_usd,
                    forecast_years=arguments.forecast_years, recalculate=arguments.recalculate, progress=TerminalProgress(),
                    escalation_file=arguments.escalation_evidence,fx_file=arguments.fx_source,fx_database=arguments.fx_database,
                    resume=str(inputs.parent) if arguments.resume and inputs!=Path(arguments.model_inputs).resolve() else arguments.resume,
                    as_of=arguments.as_of,historical_vintage=arguments.historical_vintage,include_valuation=True,
                    valuation_date=arguments.valuation_date,valuation_inputs=arguments.valuation_assumptions,
                    valuation_stage=construct_valuation)
            else:
                from company_initiation.historic_construction.workflow import research_company_inputs, ensure_company_history_research
                from company_initiation.dcf_construction.workflow import construct_valuation
                from company_initiation.forecast_construction.integrated import construct_integrated
                from datetime import date
                import tomllib
                from pathlib import Path
                from company_initiation.historic_construction.evidence import inventory_local_sources, source_inventory_fingerprint, saved_source_inventory_compatibility
                from company_initiation.historic_construction.workflow import update_company_inputs
                from company_initiation.shared_budget import company_key
                defaults=tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8')).get('tool',{}).get('research-platform',{})
                as_of=arguments.as_of or date.today().isoformat()
                matching=[]
                for record_path in (root/'outputs').glob('construct_*/record.json'):
                    saved=read_json(record_path)
                    if company_key(saved.get('configuration',{}).get('company','unknown'))==company_key(arguments.company):matching.append(saved)
                latest=max(matching,key=lambda r:Path(r['directory']).stat().st_mtime_ns) if matching and not arguments.fresh else None
                if arguments.resume:
                    if arguments.fresh:raise ValueError('--fresh and --resume cannot be combined')
                    from company_initiation.forecast_construction.integrated import verified_integrated_record
                    selected=Path(arguments.resume)
                    if not selected.is_absolute():selected=root/'outputs'/selected
                    latest=verified_integrated_record(selected,root/'outputs')
                    if company_key(latest['configuration']['company'])!=company_key(arguments.company):
                        raise ValueError('Resume company differs from requested company')
                    if Path(latest['configuration']['sources']).resolve()!=Path(arguments.sources).resolve():
                        raise ValueError('Resume source archive differs; use an explicit fresh research run under the same company budget')
                inputs=Path(latest['directory'])/'company_model_inputs.json' if latest else None
                archive_compatibility=None
                if inputs is not None and inputs.exists():
                    from company_initiation.forecast_construction.integrated import verified_integrated_record
                    latest=verified_integrated_record(latest['directory'],root/'outputs')
                    saved_data=read_json(inputs)
                    same_date=saved_data.get('model_configuration',{}).get('as_of')==as_of
                    current_inventory=inventory_local_sources(Path(arguments.sources))
                    same_archive=latest['configuration'].get('manifest') in {current_inventory['manifest_sha256'],current_inventory['source_manifest_sha256']}
                    if not same_archive and 'inventory.json' in latest.get('artifacts',{}):
                        old_inventory=read_json(Path(latest['directory'])/'inventory.json')
                        same_archive=source_inventory_fingerprint(old_inventory)==current_inventory['source_input_sha256']
                    if not same_archive:
                        archive_compatibility=saved_source_inventory_compatibility(latest,current_inventory,root/'outputs')
                        same_archive=archive_compatibility['compatible']
                    requested=sorted(set(arguments.years)) if arguments.years else None
                    if requested and requested!=saved_data['history_years']:
                        raise ValueError('Requested years differ from saved research; use --fresh for a different history scope')
                    if not same_date or not same_archive:
                        inputs=update_company_inputs(root,latest['directory'],as_of=as_of,progress=TerminalProgress())
                else:
                    inputs=research_company_inputs(root,arguments.company,arguments.sources,as_of=as_of,
                        historical_years=arguments.history_years,years=arguments.years,budget_usd=arguments.budget_usd,
                        historical_vintage=arguments.historical_vintage,fresh=arguments.fresh,progress=TerminalProgress())
                inputs=ensure_company_history_research(root,arguments.company,arguments.sources,inputs,
                    budget_usd=arguments.budget_usd,as_of=as_of,archive_compatibility=archive_compatibility,progress=TerminalProgress())
                fx=arguments.fx_source
                if fx and arguments.fx_database:raise ValueError('Choose the shared FX database or the legacy workbook adapter, not both')
                fx_database=arguments.fx_database or (None if fx else defaults.get('fx-database'))
                directory=construct_integrated(root,arguments.company,arguments.sources,inputs,
                    fx_file=root/fx if fx else None,fx_database=root/fx_database if fx_database else None,as_of=as_of,historical_vintage=arguments.historical_vintage,
                    forecast_years=arguments.forecast_years,budget_usd=arguments.budget_usd,
                    recalculate=True,resume=str(inputs.parent) if arguments.resume and inputs.parent!=Path(latest['directory']) else arguments.resume,include_valuation=True,
                    valuation_date=arguments.valuation_date,valuation_inputs=arguments.valuation_assumptions,
                    valuation_stage=construct_valuation,progress=TerminalProgress())
            record = read_json(directory / "record.json")
            print(f"Status: {record['status']}; outputs: {directory}")
            print(format_usage(record["usage"]))
            print(format_stage_usage(record["usage"]))
            if "budget" in record:
                print("Cumulative budget:", record["budget"])
            for issue in record["issues"]:
                print("Unresolved: " + issue)
            if (directory / "model.xlsx").exists():
                print(f"Open {directory / 'model.xlsx'}; inspect Model's validation summary and editable Assumptions. Detailed checks and source records are in the adjacent audit files.")
                print(record.get("summary", {}))
            return 0 if record["status"] == "complete_provisional" else 1
        else:
            from company_initiation.historic_construction.initiation import initiate_company
            from company_initiation.shared_project import read_json
            print("Reading local annual and reported interim sources; no browser search. Forecast columns remain empty.", flush=True)
            print(f"Estimated cost stop: ${arguments.budget_usd:.2f}, with a conservative allowance checked before each request. Actual billing is known afterward.", flush=True)
            directory = initiate_company(root, arguments.company, years=arguments.years,
                                         historical_years=arguments.history_years, source_directory=arguments.sources,
                                         forecast_years=arguments.forecast_years, max_cost_usd=arguments.budget_usd,
                                         progress=TerminalProgress(), resume=arguments.resume, fresh=arguments.fresh)
            record = read_json(directory / "record.json")
            passed = sum(check["passed"] for check in record["checks"])
            print(f"Checks: {passed}/{len(record['checks'])} passed. Status: {record['status']}")
            print(f"Run record: {directory / 'record.json'}")
            from company_initiation.shared_ai import format_stage_usage, format_usage
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

