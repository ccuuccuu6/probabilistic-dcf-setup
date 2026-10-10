# Project intent

Build a reusable probabilistic fundamental forecasting and valuation system, starting with Nestlé. Python performs calculations; Excel provides an inspectable review interface. The package contains the setup/FX demonstration and a generic AI-driven historical initiation workflow. API/model settings load from private local `.env` or environment variables; live company-initiation accuracy has not been verified. It contains no forecast or DCF engine.

# Required project context and continuity

Read [PROJECT_BRIEF.txt](PROJECT_BRIEF.txt) as required context for the whole project, together with this file and [README.md](README.md). README contains the current state, next milestone and dated decisions; the brief contains the research cycle and architecture principles. Preserve the user's latest instructions and verify status against the workspace.

Before implementing a substantial task, explain the ultimate ambition and complete research cycle, Nestlé's role in proving reuse, the verified implementation, the next milestone's contribution, and any decisions that risk undermining the ambition. Identify the reusable and company-specific parts and the observable completion criteria.

After meaningful work, update README's current-state, next-milestone and decision sections with verification and limitations. Distinguish confirmed decisions, proposals and unresolved questions. Deliver small, complete steps without losing the wider research cycle or silently changing model structure.

Keep context current during substantive discussions too, even when no code is changed. Record material user requirements, agreed decisions, proposals, unresolved questions and changes of direction before ending the turn. Update the relevant existing document: PROJECT_BRIEF.txt for lasting ambition and architecture, README.md for status, next steps and dated decisions, and AGENTS.md for standing working instructions. Avoid duplicating the same detail across all three or recording every conversational remark. A proposed plan is not approval to implement it; preserve explicit instructions to discuss before building.

Keep the layout as clean and minimal as possible. Use these three project documents for now; keep status, roadmap and decisions in README rather than adding separate handoff files. Prefer a small number of cohesive Python modules over nested packages. Before adding any file or directory, including documentation, explain why existing locations are insufficient and create it only when the implemented step needs it. Avoid placeholder companies, unused settings, empty future directories and duplicate editable assumptions. Explain generated artifacts and preserve earlier runs. Simplicity must preserve economic correctness, evidence provenance and reuse.

# Standing collaboration requirement

Tell the user explicitly when a proposed step weakens this vision or is unlikely to help it work. Explain the concrete issue and propose a practical alternative. Do not silently implement a design that defeats the intended economics, auditability, or reuse.

# Design rules

- Work step by step. The user's latest instruction explicitly authorizes AI APIs and bounded research/review/revision for historical initiation. Keep that workflow local; schedulers, databases, cloud services and broader orchestration still require a concrete need.
- Current scope is reusable autonomous historical initiation: accept a company query, discover its identity, sources and reporting structure, preserve originals, extract and reconcile history, and prepare blank forecast periods and documented accounting links. Company-specific mappings must emerge as cited run data, not bespoke Python extractors or prerequisite company configs. Do not implement assumptions, distributions, forecast calculations or DCF yet. Do not require the user to supply a completed historical model and describe that as pulling the numbers.
- Run the configured workflow without routine human checkpoints. AI proposes references and accounting relationships; Python reads source numbers and performs calculations. Require complete source and financial-structure reviews, preserve challenges/revisions, and enforce budgets. Missing evidence, unsupported formats and unresolved checks terminate as incomplete, never as approved history. AI agreement and balanced statements do not prove accuracy or completeness; never promise zero errors. Test API behavior with mocks before paid runs, and distinguish those tests from live-provider validation.
- Preserve independent check contexts: blind source reconstruction receives concepts and periods, not candidate values/citations/interpretations or prior verdicts; record its facts before semantic comparison. Record an evidence-first coverage inventory before revealing candidate rows, and withhold other verdicts from structural review. Require review-local original context, retain disagreements, and rerun gates after revisions within the monetary budget. Distinguish independent source support from identities that balance by construction; shared models/parsers still prevent a claim of statistically independent errors.
- Use the user's $20 cumulative estimated-cost stop for initiation, with no request/draft-count ceiling. Count every stage and charged failed call; stop on unknown costs or no progress. Report whole-run and per-stage tokens/costs during execution and in saved results. Disclose that the final in-flight request can overshoot because usage arrives afterward. Do not silently change models; only move demonstrably low-stakes work to a cheaper model with adequate evidence.
- Keep Excel close to a conventional financial model: generated formulas for derived historical rows, source inputs and linked arithmetic checks, readable year columns and blank forecasts. Generate equations from the same definitions Python uses. Workbook edits do not update saved Python inputs or renew source/AI acceptance; distinguish live arithmetic from frozen reviews.
- Store shared evidence and factor states once. Coffee, FX, and other common research can affect several companies; apply separately verified company exposure mappings, purchasing currencies, hedges, and lags.
- Distinguish topic relevance from quantified exposure. Do not invent company exposures to fill a template.
- Preserve source identity, definitions, publication/availability times, and assumption versions when real data storage is implemented.
- Use the same scenario identity across dependent drivers, periods, and companies. Derive FX cross rates from a shared currency state.
- Attach uncertainty to defensible underlying drivers. Calculate dependent financial rows with accounting equations; do not independently randomize revenue, costs, margins, and profits.
- Distinguish provisional judgment from empirically calibrated probabilities. Sampling a distribution does not establish forecasting skill.
- Keep synthetic demonstrations clearly labelled in inputs, outputs, and explanations. Never present demonstration values as company forecasts or market observations.
- Keep equations separate from assumption inputs. Do not let routine evidence updates silently change production model structure.
- Preserve run inputs and results. Never overwrite an earlier run. A local hashed manifest is useful provenance, not a tamper-proof forecast ledger.
- Keep secrets and frequently updated research/output files out of Git. Credentials may be stored in the user's explicitly authorized, Git-ignored `.env`; never put them in tracked code, documentation, prompts, terminal output or run/code snapshots. The environment can override local settings. Do not read or print credential values merely to inspect configuration. Record reported token usage and dated estimated costs, including failed calls when usage is returned; missing usage is unknown, not zero.

# Verification

The first Nestlé reference used 2024–2025 annual history. Its originals, workbook and historical code snapshot remain in the preserved run. The user has now authorized storing the supplied API credential and trying API access/token measurement; model selections are provisional. Keep offline tests credential-free and use a small explicit `api-check` for connection/usage verification. Do not claim a connection test proves live autonomous research accuracy. Preserve earlier runs, including failed attempts. This authorization does not expand scope into forecasting, distributions or DCF.

From the project root after an editable install:

```text
python -m research_platform doctor
python -m unittest discover -s tests -v
```

After configuring the environment slots described in README, `initiate "Nestlé S.A., NESN, SIX, Switzerland" --years 2024 2025` performs live research and creates a new run. Other company queries use the same function. This command uses paid AI calls and is not part of the offline test suite. The former Nestlé-only `--sources` command has been removed with its extractor; preserved runs remain inspectable. `demo-fx` remains available but need not create another project run during historical-model work. Keep checks focused on meaningful financial identities, source extraction, review gates and reproducibility. State what remains unimplemented instead of implying the full platform is ready.
