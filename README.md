# Research platform — starting with Nestlé

A small Python setup and **synthetic FX demonstration**, not a company forecast.

Use this README for commands, current progress and decisions.
[PROJECT_BRIEF.txt](PROJECT_BRIEF.txt) holds the full ambition and research principles.
[AGENTS.md](AGENTS.md) tells coding assistants how to work. These are the only project documents to maintain.

## Run it

From the project folder in PowerShell, using the existing environment:

```powershell
.\.venv\Scripts\python.exe -m research_platform doctor
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m research_platform demo-fx
```

`doctor` checks the setup without creating placeholder directories.
Tests check FX identities, validation and reproducibility.
Each `demo-fx` command saves five files in a new `outputs/run_.../` folder:
inputs, currency levels, cross rates, fictional-company translations and a manifest.
Open the CSVs in Excel. Saved runs are intentionally kept separate.

For a fresh checkout only, create the environment and install the package first:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Select `.venv\Scripts\python.exe` as the Python interpreter in VS Code.
Python 3.11 or newer is required. No API keys or runtime dependencies are needed.
Reinstall after changing package metadata or dependencies, not after ordinary code edits.

## Where things belong

| Location | Purpose |
|---|---|
| `src/research_platform/project.py` | Find the project and validate configuration |
| `src/research_platform/fx.py` | Synthetic currency states, cross rates and translation |
| `src/research_platform/demo.py` | Run the demonstration and save its files |
| `src/research_platform/__main__.py` | The two terminal commands |
| `src/research_platform/__init__.py` | Package identity and version |
| `configs/` | Nestlé identity and shared-topic definitions; no real exposures |
| `tests/test_setup.py` | Checks for the implemented behavior |
| `outputs/` | Generated, preserved runs; ignored by Git |
| `pyproject.toml`, `.gitignore` | Package setup and files excluded from Git |

`.venv/`, `__pycache__/` and `*.egg-info/` are generated Python installation/cache files.
`.git/` is Git's history. These are not additional modelling work to maintain.
Keep them out of manual cleanup; obsolete caches from moved modules are removed as part of the refactor.

**When modelling begins:** introduce `src/research_platform/nestle.py` for Nestlé's equations.
The proposed research store is `local_store/research.sqlite`, with original documents under
`local_store/raw_sources/`. Versioned distribution assumptions would be loaded once,
sampled into coherent driver paths, and passed into the model. Save those inputs,
actual samples and results with the run. None of these future capabilities is created yet.
The brief contains the detailed input and FX rules. Split code into more modules only when actual complexity requires it.

## Current state — 10 October 2026

Implemented: configuration validation, five shared synthetic currency states,
translation for two fictional companies, CSV/JSON exports and manifests with input/output/source hashes.
Nestlé configuration is still an identity/topic template with empty exposures.

Verified after cleanup using the existing Windows editable installation and Python 3.13.16:
doctor, all ten tests and the demo pass. Tests used the approved temporary-folder access.
The three earlier runs are preserved: all 15 original file hashes are unchanged.
The verification run is `outputs/run_6ba4ccf58b144a469f96b37fc42ec1d5/`; its numerical
CSVs match the earlier seed-42 run exactly, and its output/source hashes validate.
Original source files for the earlier runs remain in Git commit `12a43be`.
Documentation links and original economic rules were checked; unused data directories stay absent.
Local hashes aid provenance but are not a tamper-proof forecast ledger.

Not implemented: real company history/model, evidence database, live ingestion, AI integration,
calibrated distributions, Excel review workbook, reverse valuation, catalysts or forward evaluation.
Source coverage, exposure estimates and a backup for future ignored research data remain unresolved.
These local changes are uncommitted; live remote state and repository privacy have not been checked.

## Next milestone

Define Nestlé's reporting specification from official sources:
periods, disclosure frequencies, segment vintages, financial rows, units and metric definitions.
Every row must be reported, calculated, estimated or explicitly missing, with a source reference or gap.
Identify the sales/profit, cash-flow and equity-value reconciliation bridges.
Do not manufacture undisclosed quarters or treat reported free cash flow as automatically identical to valuation cash flow.

Then build a small source/fact/version registry, reconcile history and implement one deterministic case.
The full sequence is in brief section 10. Record useful provisional forecasts as soon as
targets, reporting vintages, horizons, resolution rules, baselines and frozen inputs/output exist;
reverse valuation and complete automation must not delay them.

## Decisions

| Date | Status | Choice and reason |
|---|---|---|
| 10 October 2026 | Confirmed | The brief is required context. Its settled choices include Nestlé first, Python calculations, Excel review, local development and shared evidence with explicit company effects. |
| 10 October 2026 | Confirmed | Keep the minimum understandable layout. This cleanup reduces maintained project files from 26 to 13, replacing the seven-document/five-subpackage scaffold with three documents and five Python files. Progress, next steps and decisions now live here; unique architecture detail lives in the brief. Add a file only for a concrete need that existing locations cannot sensibly serve. |
| 10 October 2026 | Confirmed | Remove the unused Keurig Dr Pepper configuration, empty environment example and unused data directories. Retain earlier runs and their frozen configuration snapshots. No second company has been selected. |
| 10 October 2026 | Proposed | One local SQLite registry for evidence and versioned assumptions, with frozen run snapshots. This avoids competing editable assumption stores. The earlier nested model-file proposal is simplified to `nestle.py`; create it only when implementing the model. |
