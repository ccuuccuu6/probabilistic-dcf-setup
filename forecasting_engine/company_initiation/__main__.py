"""Run with python -m company_initiation from the project directory."""

import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import platform
import re
import shutil
import sys
from threading import Event, Lock, Thread
from time import monotonic
import traceback
from uuid import uuid4

from company_initiation.shared_project import find_project_root, resolve_data_path


class _AuditStream:
    """Keep terminal behaviour while immediately persisting timestamped output."""

    def __init__(self, console, log, channel, lock):
        self.console, self.log, self.channel, self.lock = console, log, channel, lock
        self.line_start = True

    def __getattr__(self, name):
        return getattr(self.console, name)

    def write(self, text):
        length = len(text)
        self.console.write(text)
        # Interactive waiting ticks bypass this stream; retain their final result.
        text = text.replace("\r", "")
        with self.lock:
            for part in text.splitlines(keepends=True):
                if self.line_start:
                    stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
                    self.log.write(f"[{stamp}] [{self.channel}] ")
                self.log.write(part)
                self.line_start = part.endswith("\n")
            self.log.flush()
        return length

    def flush(self):
        self.console.flush()
        with self.lock:
            self.log.flush()


def _logged_construct(arguments):
    """Start a durable local audit before dispatching any construction work."""
    try:
        directory = find_project_root() / "forecasting_engine" / "company_initiation" / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        company = re.sub(r"[^a-z0-9]+", "-", arguments.company.casefold()).strip("-")[:80] or "company"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = directory / f"{stamp}_{company}_{uuid4().hex}.log"
        log = path.open("x", encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"ERROR: Cannot create construction audit log; construction has not started: {error}", file=sys.stderr)
        return 1
    started = monotonic()
    lock = Lock()
    with log, redirect_stdout(_AuditStream(sys.stdout, log, "stdout", lock)), redirect_stderr(_AuditStream(sys.stderr, log, "stderr", lock)):
        print(f"Construction audit log: {path}", flush=True)
        print(f"Session started (UTC): {datetime.now(timezone.utc).isoformat()}", flush=True)
        # Only public construction options are recorded; never inspect environment settings.
        option_names = ("command", "company", "sources", "as_of", "valuation_date", "valuation_assumptions",
                        "historical_vintage", "model_inputs", "resume", "fx_source", "fx_database",
                        "reference_workbook", "years", "history_years", "start_year", "forecast_years", "budget_usd",
                        "fresh", "recalculate", "escalation_evidence")
        options = {name: getattr(arguments, name) for name in option_names if hasattr(arguments, name)}
        print("Invocation: " + json.dumps(options, ensure_ascii=False, sort_keys=True), flush=True)
        exit_code = 1
        try:
            exit_code = _run(arguments)
            return exit_code
        except KeyboardInterrupt:
            exit_code = 130
            print("Interrupted. Saved run records and this audit log are preserved.", file=sys.stderr, flush=True)
            return exit_code
        except BaseException as error:
            if isinstance(error, SystemExit):
                exit_code = error.code if isinstance(error.code, int) else (0 if error.code is None else 1)
            print("Unexpected construction exception:", file=sys.stderr, flush=True)
            traceback.print_exc()
            raise
        finally:
            outcome = "completed" if exit_code == 0 else "interrupted" if exit_code == 130 else "failed"
            print(f"Session ended (UTC): {datetime.now(timezone.utc).isoformat()}; "
                  f"status={outcome}; exit_code={exit_code}; elapsed_seconds={monotonic() - started:.3f}", flush=True)


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
            console = self.stream.console if isinstance(self.stream, _AuditStream) else self.stream
            console.write(f"\r{label}: waiting {minutes:02d}:{seconds:02d}")
            console.flush()

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
    construct_history = commands.add_parser("construct-history",
        help="Run construction through the historical Excel only; no forecast or DCF handoff")
    for construction_parser in (construct,construct_history):
        construction_parser.add_argument("company")
        construction_parser.add_argument("--as-of", help="Model information date, YYYY-MM-DD; defaults to today's date and is saved")
        construction_parser.add_argument("--historical-vintage", action="store_true", help="Require every source to have verified publication by the as-of date")
        construction_parser.add_argument("--sources", required=True)
        construction_parser.add_argument("--model-inputs", help="Explicit saved sourced company research specification")
        continuation=construction_parser.add_mutually_exclusive_group()
        continuation.add_argument("--resume",metavar="RUN",help="Continue this saved run using its remaining budget; no automatic resume")
        continuation.add_argument("--fresh",action="store_true",help="Start a new run and budget (the default)")
        history=construction_parser.add_mutually_exclusive_group()
        history.add_argument("--years",nargs="+",type=int)
        history.add_argument("--history-years",type=int,help="Override with a rolling count of completed fiscal years")
        history.add_argument("--start-year",type=int,help="First fiscal year, inclusive (default: 2018)")
        construction_parser.add_argument("--budget-usd",type=float,help="New-run allowance, maximum $20 (default: $20); resume keeps its original cap")
    construct.add_argument("--valuation-date", help="DCF date, YYYY-MM-DD; defaults to the model information date")
    construct.add_argument("--valuation-assumptions", help="Optional typed valuation-v1 overrides; normal construction generates its inputs")
    construct.add_argument("--fx-source", help="Local shared FX workbook; source dates and actual/estimate status are preserved")
    construct.add_argument("--fx-database", help="Shared FX database snapshot, consumed without broker downloads")
    construct.add_argument("--reference-workbook", help="Local analyst workbook used as architecture/presentation reference; never a company numeric input")
    construct.add_argument("--forecast-years", type=int, default=5)
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
    history.add_argument("--history-years", type=int,
                         help="Override with a rolling count of fully reported fiscal years evidenced in the archive")
    history.add_argument("--start-year", type=int, help="First fiscal year, inclusive (default: 2018)")
    initiate.add_argument("--forecast-years", type=int, default=5, help="Number of empty forecast columns (default: 5)")
    initiate.add_argument("--budget-usd", type=float,
                          help="Stop at this cumulative estimated USD cost (default and maximum: 20); last request can overshoot")
    continuation = initiate.add_mutually_exclusive_group()
    continuation.add_argument("--resume", metavar="RUN", help="Continue this saved run and its existing budget")
    continuation.add_argument("--fresh", action="store_true", help="Start new research and budget (the default)")
    arguments = parser.parse_args()
    if arguments.command in {"construct", "construct-history", "initiate"}:
        arguments._history_defaulted=all(getattr(arguments,key) is None for key in ("years","history_years","start_year"))
        if arguments._history_defaulted:
            from company_initiation.historic_construction.periods import DEFAULT_HISTORY_START_YEAR
            arguments.start_year=DEFAULT_HISTORY_START_YEAR
        arguments._budget_defaulted=arguments.budget_usd is None
        if arguments._budget_defaulted:arguments.budget_usd=20.
        if arguments.fresh and getattr(arguments,'model_inputs',None):parser.error('--fresh and --model-inputs cannot be combined')
        arguments.fresh=not bool(arguments.resume or getattr(arguments,'model_inputs',None))
    return _logged_construct(arguments) if arguments.command in {"construct", "construct-history"} else _run(arguments)


def _run(arguments) -> int:
    """One explicit build/budget scope surrounds every construction stage."""
    try:
        root=find_project_root()
        if arguments.command=='initiate':
            if arguments.resume:
                selected=Path(arguments.resume)
                if not selected.is_absolute() and not selected.exists():selected=root/'outputs'/selected
                if selected.name=='record.json':selected=selected.parent
                from .shared_project import read_json
                saved=read_json(selected/'record.json')['request']
                arguments.resume=str(selected.resolve())
                if getattr(arguments,'_history_defaulted',False):
                    arguments.years=saved.get('years');arguments.history_years=saved.get('historical_years');arguments.start_year=saved.get('start_year')
                if getattr(arguments,'_budget_defaulted',False):arguments.budget_usd=saved['max_cost_usd']
            return _dispatch(arguments)
        if arguments.command not in {'construct','construct-history','update','export','refresh-fx'}:
            return _dispatch(arguments)
        from .shared_artifacts import verified_integrated_record
        from .shared_budget import construction_command_budget
        selected=getattr(arguments,'resume',None) if arguments.command in {'construct','construct-history'} else arguments.run
        if not selected and getattr(arguments,'model_inputs',None):
            candidate=Path(arguments.model_inputs).resolve().parent
            if (candidate/'record.json').is_file():selected=candidate
        previous=None
        if selected:
            path=Path(selected)
            if not path.is_absolute() and not path.exists():path=root/'outputs'/path
            if path.name=='record.json':path=path.parent
            previous=verified_integrated_record(path,root/'outputs')
            company=previous['configuration']['company']
            if arguments.command in {'construct','construct-history'}:
                from .shared_budget import company_key
                if company_key(company)!=company_key(arguments.company):raise ValueError('Resume company differs from requested company')
                if getattr(arguments,'resume',None):arguments.resume=str(path.resolve())
                saved_inputs=path/'company_model_inputs.json'
                saved_data=json.loads(saved_inputs.read_text(encoding='utf-8')) if saved_inputs.is_file() else {}
                if getattr(arguments,'as_of',None) is None:
                    arguments.as_of=previous['configuration'].get('as_of') or saved_data.get('model_configuration',{}).get('as_of')
                if getattr(arguments,'_history_defaulted',False):
                    cfg=previous['configuration']
                    arguments.years=cfg.get('years');arguments.history_years=cfg.get('historical_years');arguments.start_year=cfg.get('start_year')
                    if not any(value is not None for value in (arguments.years,arguments.history_years,arguments.start_year)):
                        arguments.years=saved_data.get('history_years')
            limit=None if getattr(arguments,'_budget_defaulted',True) else arguments.budget_usd
        else:
            company=arguments.company;limit=arguments.budget_usd
        with construction_command_budget(root/'outputs',company,limit,previous=previous) as budget:
            arguments.budget_usd=budget['limit_usd']
            print(('New run budget: ' if previous is None else 'Continuing run budget: ')+json.dumps(budget),flush=True)
            return _dispatch(arguments)
    except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
        print(f'ERROR: {error}',file=sys.stderr)
        return 1


def _dispatch(arguments) -> int:
    try:
        root = find_project_root()
        if getattr(arguments, 'sources', None):
            arguments.sources = str(resolve_data_path(root, arguments.sources))
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
                inputs=update_company_inputs(root,parent,as_of=as_of,progress=TerminalProgress(),online=True)
                directory=construct_integrated(root,config['company'],resolve_data_path(root,config['sources']),inputs,
                    fx_database=root/defaults['fx-database'] if defaults.get('fx-database') else None,as_of=as_of,
                    forecast_years=config.get('forecast_years',5),budget_usd=arguments.budget_usd,include_valuation=True,progress=TerminalProgress())
            else:
                directory = offline_export(root, arguments.run, fx_file=fx,
                    fx_database=root/fx_database if fx_database else None,
                    snapshot_id=getattr(arguments,'snapshot',None),fx_as_of=getattr(arguments,'fx_as_of',None),inputs_file=getattr(arguments,'model_inputs',None),
                    include_valuation=True,valuation_date=getattr(arguments,'valuation_date',None),rebuild=getattr(arguments,'rebuild',False),progress=TerminalProgress())
            print(f"Workbook: {directory / 'model.xlsx'}")
            from company_initiation.shared_project import read_json
            return 0 if read_json(directory / "record.json")["status"] == "complete_provisional" else 1
        elif arguments.command in {"construct", "construct-history"}:
            from company_initiation.shared_project import read_json
            from company_initiation.shared_ai import format_usage, format_stage_usage
            from pathlib import Path
            history_only=arguments.command=='construct-history'
            print("Constructing "+('historical data only' if history_only else 'a provisional model')+
                  ". Python reads source numbers; unknown inputs remain missing.", flush=True)
            if arguments.model_inputs:
                from company_initiation.historic_construction.workflow import ensure_company_history_research
                from company_initiation.historic_construction.periods import requested_history_years
                supplied=read_json(Path(arguments.model_inputs))
                requested=requested_history_years(max(supplied['history_years']),years=arguments.years,
                    historical_years=arguments.history_years,start_year=arguments.start_year)
                if requested!=supplied['history_years']:
                    raise ValueError('Saved --model-inputs has a different history scope; omit --model-inputs to research the requested scope, or explicitly select its years')
                inputs=ensure_company_history_research(root,arguments.company,arguments.sources,arguments.model_inputs,
                    budget_usd=arguments.budget_usd,as_of=arguments.as_of,progress=TerminalProgress())
                if history_only:
                    return _historical_result(root,arguments,inputs)
                from company_initiation.forecast_construction.integrated import construct_integrated
                from company_initiation.dcf_construction.workflow import construct_valuation
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
                from datetime import date
                import tomllib
                from pathlib import Path
                from company_initiation.historic_construction.evidence import inventory_local_sources, source_inventory_fingerprint, saved_source_inventory_compatibility
                from company_initiation.historic_construction.workflow import update_company_inputs
                from company_initiation.shared_budget import company_key, build_record_paths, record_in_build_scope
                defaults=tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8')).get('tool',{}).get('research-platform',{})
                as_of=arguments.as_of or date.today().isoformat()
                matching=[]
                for record_path in build_record_paths(root/'outputs','construct_*/record.json'):
                    saved=read_json(record_path)
                    if record_in_build_scope(saved) and company_key(saved.get('configuration',{}).get('company','unknown'))==company_key(arguments.company):matching.append(saved)
                latest=max(matching,key=lambda r:Path(r['directory']).stat().st_mtime_ns) if matching and not arguments.fresh else None
                if arguments.resume:
                    if arguments.fresh:raise ValueError('--fresh and --resume cannot be combined')
                    from company_initiation.shared_artifacts import verified_integrated_record
                    selected=Path(arguments.resume)
                    if not selected.is_absolute():selected=root/'outputs'/selected
                    latest=verified_integrated_record(selected,root/'outputs')
                    if company_key(latest['configuration']['company'])!=company_key(arguments.company):
                        raise ValueError('Resume company differs from requested company')
                    if resolve_data_path(root,latest['configuration']['sources'])!=Path(arguments.sources).resolve():
                        raise ValueError('Resume source archive differs; omit --resume to start a new run with a new budget')
                inputs=Path(latest['directory'])/'company_model_inputs.json' if latest else None
                archive_compatibility=None
                if inputs is not None and inputs.exists():
                    from company_initiation.shared_artifacts import verified_integrated_record
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
                    from company_initiation.historic_construction.periods import requested_history_years
                    latest_scope_year=max(max(saved_data['history_years']),max(arguments.years or [0]),arguments.start_year or 0)
                    requested=requested_history_years(latest_scope_year,years=arguments.years,
                        historical_years=arguments.history_years,start_year=arguments.start_year)
                    from company_initiation.historic_construction.workflow import VA_SOURCE_POLICY,VA_MAPPING_CONTRACT
                    va_supplied=any(s.get('category')=='visible_alpha' for s in current_inventory['sources'])
                    old_source_policy=(va_supplied and (
                        saved_data.get('model_configuration',{}).get('historical_source_policy')!=VA_SOURCE_POLICY or
                        saved_data.get('model_configuration',{}).get('va_mapping_contract')!=VA_MAPPING_CONTRACT))
                    if old_source_policy:
                        if arguments.resume:raise ValueError('Explicit resume uses the earlier historical source policy; omit --resume to start a new run using company-reported VA')
                        print('Using company-reported VA as primary history; retaining prior evidence and spending records.',flush=True)
                        inputs=None
                        archive_compatibility=None
                    elif requested!=saved_data['history_years']:
                        if arguments.resume:raise ValueError('Explicit resume has a different history scope; omit --resume to start a new run with the requested scope')
                        print('History scope changed; researching the requested fiscal years while retaining prior evidence and spending records.',flush=True)
                        inputs=None
                        archive_compatibility=None
                    elif not same_date or not same_archive:
                        inputs=update_company_inputs(root,latest['directory'],as_of=as_of,progress=TerminalProgress())
                if inputs is None or not inputs.exists():
                    inputs=research_company_inputs(root,arguments.company,arguments.sources,as_of=as_of,
                        historical_years=arguments.history_years,years=arguments.years,start_year=arguments.start_year,budget_usd=arguments.budget_usd,
                        historical_vintage=arguments.historical_vintage,fresh=arguments.fresh,resume=arguments.resume,progress=TerminalProgress())
                inputs=ensure_company_history_research(root,arguments.company,arguments.sources,inputs,
                    budget_usd=arguments.budget_usd,as_of=as_of,archive_compatibility=archive_compatibility,progress=TerminalProgress())
                if history_only:
                    return _historical_result(root,arguments,inputs)
                from company_initiation.forecast_construction.integrated import construct_integrated
                from company_initiation.dcf_construction.workflow import construct_valuation
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
            for stage in ('historical','forecast','dcf'):
                output=record.get('stage_outputs',{}).get(stage)
                if output:print(f"{stage.capitalize()} workbook: {directory / output['workbook']}")
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
                                         historical_years=arguments.history_years, start_year=arguments.start_year, source_directory=arguments.sources,
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
        print("Interrupted. Saved progress is preserved; use --resume RUN to continue its existing budget. "
              "A request interrupted in flight may have an unknown charge and block further spending.", file=sys.stderr)
        return 130
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        for note in getattr(error, "__notes__", []):
            print(note, file=sys.stderr)
        return 1
    return 0


def _historical_result(root, arguments, inputs):
    """Finish stage one without importing or dispatching either later stage."""
    from .historic_construction.workflow import complete_historical_model
    from .shared_project import read_json
    from .shared_ai import format_usage,format_stage_usage
    directory=complete_historical_model(root,arguments.company,arguments.sources,inputs,
        budget_usd=arguments.budget_usd,progress=TerminalProgress())
    record=read_json(directory/'record.json')
    print(f"Status: {record['status']}; outputs: {directory}")
    print(f"Historical workbook: {directory / 'historical_model.xlsx'}")
    print(format_usage(record['usage']));print(format_stage_usage(record['usage']))
    print('Run budget:',record['budget'])
    for issue in record['issues']:print('Unresolved: '+issue)
    print('Stopped after historical construction. No forecast or DCF construction was started.')
    return 0 if record['status']=='historical_complete_provisional' else 1


if __name__ == "__main__":
    raise SystemExit(main())

