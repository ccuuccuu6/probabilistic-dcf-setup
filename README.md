# Research platform — reusable company initiation

A local, AI-driven process for discovering a company's reports, building cited
historical financial statements, checking them and preparing **blank forecast
columns**. Nestlé is the first real comparison case. No assumptions, forecast
calculations, distributions or DCF are implemented.

[PROJECT_BRIEF.txt](PROJECT_BRIEF.txt) preserves the wider research ambition;
[AGENTS.md](AGENTS.md) holds working instructions. This README owns current state,
commands, next steps and decisions. These remain the three project documents.

## The function and workflow

`initiate_company(root, company, ...)` in
[initiation.py](src/research_platform/initiation.py) accepts any company query.
It does not require a company configuration or a hand-written company extractor.
Supply a name with ticker, exchange and country when possible to avoid ambiguity.

In financial terms, this commissions the first stage of company research: rebuild
the historical accounts from original disclosures, explain how the figures connect,
check the result and leave room for forecasts. The research and review roles are
separate AI requests; Python reads the cited amounts and performs the calculations.

You supply the company and, optionally, historical years. Without years, discovery
looks for the latest two fully reported annual periods. The process checks its
settings, opens a separate recorded run, then searches the web for the correct
company and authoritative reports. It downloads and preserves the originals with
their source information and retrieval times, so later checks use a saved record
of the evidence rather than a website that might change.

The first analyst works through those documents to propose segments, statements,
supporting schedules, definitions and accounting relationships. For a reported
number it must point to its exact source location; Python reads that location.
Derived figures are calculated from cited components. The first substantial check
then tests the accounting, including segment and group reconciliation, balance
sheet, cash-flow/balance-sheet cash and adjacent-period cash continuity. Documented
definition differences and restatements need explicit bridges. A failed numerical
draft returns for correction before the AI reviews begin.

Once those checks pass, a second pass looks up the reported concepts in batches
without seeing the draft's amounts, citations or interpretations. Its own cited
answers are saved first. Python compares the numbers, and then a separate comparison
checks whether the two selections have the same meaning, period, units and reporting
version. Equal figures alone cannot establish that two definitions are equivalent.
These reviewers navigate the downloaded originals; they do not conduct new web searches.

After those source batches, another pass reads each financial section without
seeing the model and records the disclosures it expects to find. Only afterward
does the structure reviewer see the model, match it against that inventory, and
challenge omissions, definitions and relationships. Earlier numerical results and
source-review verdicts are withheld. This checks what might be missing as well as
whether the included rows are right.

Ordinary disagreements become feedback for another draft, with all checks rerun.
All stages share a **$20 cumulative estimated-cost stopping threshold**. There is
no request-count or draft-count ceiling. Unknown cost, API failures or a repeated
state without progress can stop the process sooner. If every required check passes, the result is a historical
Excel workbook with sources, review results and five blank forecast years by default.
Otherwise the saved result is incomplete, with reasons and no accepted workbook.
All attempts remain recorded, earlier run folders are preserved, and reported token
usage and estimated costs appear as the process runs.

The process ends there. Derived history and linked accounting checks recalculate
in Excel; edits do not change Python's saved results or rerun source/AI reviews.
Forecast assumptions, distributions, DCF and ongoing news maintenance
remain later work. Starting initiation again creates a new run rather than resuming
or updating the earlier one. Passing checks means the configured gates passed, not
that shared source, parsing or AI mistakes have become impossible.

The required coverage decisions span operating segments, income statement, balance
sheet, cash flow, working capital, net debt, equity and shares. Undisclosed or
inapplicable schedules need cited explanations and reviewer acceptance. They are
not filled with zeros. Core statements cannot be waived. Do not add overlapping
segment views or pretend that a company publishes full segment balance sheets.

## Function order when you run initiation

The functions below are called in execution order; their positions within a Python
file do not determine when they run. These are sequential AI role calls coordinated
by Python. Each request receives explicit context rather than an unlimited shared
conversation. The full drafts and source archive remain in Python/run records.

| Step | Function(s) | What happens |
|---|---|---|
| 1 | `main()` → `find_project_root()` | Read the terminal command and find the project folder. |
| 2 | `initiate_company()` → `OpenAIProvider.from_env()` → `validate_configuration()` | Validate years/limits and load private API/model settings. No AI call yet. |
| 3 | `SourceStore(...)`, `save()` | Create a unique run, initialize its source index and write an in-progress record with code/dependency versions. |
| 4 | `ask()` → `OpenAIProvider.complete()` → `validate_shape()` | Send the discovery instructions with web search enabled; require a structured response. The same call/logging path is reused for every later AI request. |
| 5 | `validate_discovery()` | Check identity fields, fiscal dates, requested coverage and supplied publication dates. These mechanical checks do not prove the selected company/source is correct. |
| 6 | `add_sources()` → `SourceStore.add()` → `download()` → `_units()` | Archive original files with hashes/timestamps and index their pages, spreadsheet rows or HTML chunks. |
| 7 | `ask()` with extraction instructions; `catalog()`, `search()`, `read()` | AI navigates the archive, requests additional source URLs, saves batches of cited row definitions, then proposes a complete candidate. `save_rows` and `propose` are response actions handled inside `initiate_company()`, not separate Python functions. |
| 8 | `materialize_and_check()` → `SourceStore.resolve()` / `parse_number()` | Read cited numbers, apply declared units/signs, calculate derived rows and test accounting, dependencies, coverage and gaps. Failed checks return to step 7. |
| 9 | `review("source_review", ...)` → `compare_source_facts()` | Blindly reconstruct reported concepts in batches of up to 20. Only concept identity and requested periods are supplied; the reviewer selects and reads its own numeric/header context. Save its facts before comparing amounts, units and entities. |
| 10 | `review("source_alignment", ...)` → `_review_issues()` | After the blind answer is recorded, compare meanings and reporting vintages against the candidate and originals. Require a cited reasoned verdict for every reported row; equal amounts alone cannot establish equivalent definitions. |
| 11 | `review("coverage_inventory", ...)` → `validate_inventory()` | Independently inventory all eight sections, without candidate rows, definitions or verdicts. Save each cited inventory before revealing the model. |
| 12 | `review("model_review", ...)` → `compare_inventory()` / `_review_issues()` | Match every expected item to a candidate row and challenge nine structural topics. Other review verdicts and numerical check results are withheld. Missing lines, duplicate matches or unresolved coverage differences block acceptance. |
| 13 | The attempt loop in `initiate_company()` | Send unresolved findings back to step 7; rerun all gates and retain earlier proposals/checks/reviews. Continue while making progress under the shared estimated-cost threshold. |
| 14 | `export_workbook()` → `save()` → return to `main()` | If every gate passes, publish the historical workbook with blank forecast columns, finalize the record and print paths/status. Otherwise record an incomplete result. |

After every attempted AI call, `response_usage()`, `aggregate_usage()` and
`format_usage()` extract reported usage and print cumulative stage and run totals;
`enforce_budget()` checks the cost before another result can be used. `save()` updates
the current run record and `calls.jsonl` keeps the detailed call history.
`format_stage_usage()` prints the final breakdown, including incomplete runs.
`_object()`, `_array()` and `_enum()` merely build the required response formats.

Source discovery is currently called once. Only that stage has web search enabled;
later `search()` calls search downloaded documents. The extractor can request known
additional URLs, but there is no second web-research stage. Discovery validation
failures and provider errors (including HTTP 429, refusal or an incomplete response)
stop the run; they do not trigger automatic paid retries. Financial/format validation
issues inside the proposal/review loop can trigger revision. Rerunning the command
starts a new run; saved records do not yet provide resumable execution.

Each extraction decision is another paid request. Each source batch of at most 20
reported rows has a blind reconstruction and a separate meaning comparison. Eight
section inventories and the final structure review also use repeated requests to
navigate evidence and answer. Revisions repeat the checks. The old global and local
request/draft ceilings are removed; all these stages share the dollar threshold.
After the function returns, there are no background
AI calls, news monitoring or Excel-triggered requests. `api-check` is a separate,
explicit one-call command. Downloads, numeric calculations and export run locally.

AI still chooses the semantic mapping, scale/sign and proposed relationships.
Python reading a real number prevents invented numeric literals, but does not by
itself prove that number belongs to the right company, row or period. Source and
structure reviews address that remaining risk; their agreement is not a guarantee.
The first real Nestlé run remains unverified because the last generation test
returned HTTP 429. This sequence includes the independently reconstructed facts,
coverage inventory and stronger reconciliations added after the original walkthrough;
it does not describe a new successful live run.

## API settings and first test

The connection is implemented in [ai.py](src/research_platform/ai.py). Local credentials
and model choices are stored in the project-root `.env`, which is ignored by Git.
Its contents are never copied into run records. Process environment variables override
the file, so a temporary experiment need not edit it. The loader accepts these four
literal settings; it does not execute shell commands or expand variables:

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | API credential; keep it out of source files and Git |
| `RESEARCH_MODEL` | Model supporting Responses web search and structured output |
| `EXTRACTION_MODEL` | Model for document navigation and reporting-map proposals |
| `REVIEW_MODEL` | Model for source and financial-structure challenges |

For the first correctness benchmark, all three model slots use **`gpt-6.1-sol`**.
This is a provisional selection, not a financial-accuracy result. No current AI
role is clearly low-stakes: discovery, extraction and reviews all make material
evidence or accounting judgments. Mechanical number reads, calculations and exports
already run in Python. Keep Sol unchanged; use measured stage costs and accuracy
before deciding whether a later Luna extraction comparison is worthwhile.
GPT-6 Astra is an optional stronger benchmark
if Sol demonstrably struggles, rather than an automatic escalation.
[Official model guidance](https://developers.openai.com/api/docs/guides/latest-model).

In PowerShell, `$env:EXTRACTION_MODEL = "gpt-6-luna"` overrides that role for the
current terminal. Remove the override to use `.env` again. Keep credentials out of
tracked files and never paste the `.env` contents into logs or documentation.
Missing settings stop before downloads or run creation.

The supplied adapter uses the
[OpenAI Responses API](https://developers.openai.com/api/docs/guides/structured-outputs)
and [web search](https://developers.openai.com/api/docs/guides/tools-web-search).
Another provider can implement the small `AIProvider` interface and be passed as
`provider=` without rewriting the workflow. Research, extraction and review are
separate calls with separate model slots, not independently proven sources of truth.
The same model may fill several slots; even different models can share errors.

First, make one small paid connection test from the VS Code PowerShell terminal:

```powershell
.\.venv\Scripts\python.exe -m research_platform api-check
```

It checks the extraction model with a 1,024-output-token limit, including reasoning,
and prints reported token usage and estimated cost. It does not download company
reports or create a research run. `--role researcher` or `--role reviewer` selects
another configured model. This check does not exercise web search or financial accuracy.

To start the actual company initiation:

```powershell
.\.venv\Scripts\python.exe -m research_platform initiate "Nestlé S.A., NESN, SIX, Switzerland" --years 2024 2025
```

The same command accepts another company name. Without `--years`, discovery selects
the latest two fully reported annual periods. `--forecast-years` controls the number
of empty future columns (default five); fiscal date definitions remain in the record.

Live execution makes paid API calls. **The whole run stops when its returned-usage
cost estimate reaches or exceeds $20**, including research, navigation, all reviews,
revisions, search fees and failed requests with reported charges. There is no
request-count ceiling. The former `--max-calls` option has been removed.
`--budget-usd 5` can lower the threshold; the current maximum is $20. The Python
argument is `max_cost_usd`, also defaulting to 20. Existing per-response output,
document/context and financial-data limits remain; these are not call-count caps.

The guard runs before each request and after recording each response. A crossing
response is saved but cannot advance research or publish an accepted workbook,
even if it was the final review. Missing usage or unrecognized pricing stops the
run as incomplete; configured model prices must be known before research starts.
The **last request can overshoot $20** because the provider returns usage after
charging. This is a strict stop on the reported estimate, not an exact invoice cap.
The adapter does not automatically retry failed paid requests.

Removing the old call ceilings permits complete independent reviews on larger
models. Repeated unchanged navigation or a failed candidate resubmitted without
new evidence stops as no progress. Reading previously unread source context is
progress, even if the proposed numbers stay unchanged. Review efficiency and actual
cost still need measurement; passing within $20 is not guaranteed.

## Model costs and token usage

Standard API prices checked on **10 October 2026**, in USD per million tokens:

| Model | Input | Cached input | Cache writes | Output, including reasoning |
|---|---:|---:|---:|---:|
| `gpt-6-luna` | $0.10 | $0.01 | $0.125 | $0.50 |
| `gpt-6.1-sol` | $2.00 | $0.10 | $2.50 | $10.00 |
| `gpt-6-astra` | $10.00 | $1.00 | $12.50 | $50.00 |

Search actions add $0.01 each; retrieved search content is also billed at model
token rates. The estimator counts search actions rather than charging page opens
and text finds as searches. [Official pricing](https://developers.openai.com/api/docs/pricing),
[web-search billing](https://developers.openai.com/api/docs/guides/tools-web-search).

For initial planning, allow roughly **$5-15 per substantial all-Sol attempt**,
including the possibility that it ends incomplete. This is an unmeasured ballpark,
not a price quote, statistical range or cap. For illustration, 2 million input
tokens, 200,000 output tokens and 20 searches cost **$6.20** at ordinary Sol rates,
or **$7.20** if all input incurs cache-write pricing. Smaller attempts can cost less;
large evidence contexts, longer reasoning and revisions can exceed the allowance.
Each normal request permits up to 16,000 output tokens, including reasoning. A run
can end incomplete at the spending threshold; the final request can overshoot it.

Keep Sol as the provisional first correctness benchmark. Compare Luna extraction
later against the same evidence and error criteria; the fraction of tokens it would
replace is unknown, and reviews can dominate usage. Do not assume a twentyfold
reduction in the whole bill from changing one role. Astra's ordinary input/output
token rates are five times Sol's, with no demonstrated benefit in this workspace.
The $20 estimated-cost stopping guard is implemented. More efficient review context
delivery remains a possible measured improvement. No model settings changed.

The terminal displays **total, input and output tokens and estimated USD for both
the active stage and the whole run after every call**, then a breakdown of every
incurred stage at termination. Stages are `discover`, `extract`, `source_review`,
`source_alignment`, `coverage_inventory` and `model_review`; retries/revisions and
returned charges on failed calls accumulate into their stage. `calls.jsonl` records each
call's reported input, cached input, cache writes, output, reasoning and search counts;
`record.json` contains totals plus `usage.by_stage` and `usage.by_model` breakdowns.
The workbook's Start here sheet includes the same run/stage summaries. Reasoning tokens are already part
of output and are not charged twice. Cache reads/writes are portions of total input,
not extra input tokens. Pricing is frozen as a dated code snapshot in each run.
[Caching definitions](https://developers.openai.com/api/docs/guides/prompt-caching).

The estimator applies documented long-context rates above 272,000 input tokens per
request and explicitly requests standard service. Unknown models, unsupported service
tiers or missing usage make the cost incomplete; unavailable counts are not invented
as zero. Unknown cost stops initiation. Local estimates are not an invoice; the
post-response stopping threshold cannot prevent its final request overshooting. Compare with your
[OpenAI usage dashboard](https://platform.openai.com/usage) for account billing.

## Outputs and how to check them

Each invocation creates a new `outputs/initiate_<company>_<time>_<id>/` folder:

| Artifact | What it contains |
|---|---|
| `record.json` | Request, status, discovered identity/periods, source metadata, proposals, revisions, resolved figures, equations, checks, review results, errors, usage/cost totals, code snapshot and dependency versions |
| `calls.jsonl` | Timestamped prompts, supplied evidence, structured responses, provider responses/model identifiers, reported usage and estimated cost; no API key or authorization header |
| `sources/` | Original documents with hashes; created only when documents are obtained |
| `model.xlsx` | Historical model with calculated rows linked by Excel formulas, reported source inputs, live arithmetic checks alongside recorded results, blank forecast columns, AI reviews and Sources |

A source's publication date is AI-discovered metadata checked against available
evidence, not an authenticated availability timestamp. Unknown dates remain null;
retrieval times record when this process actually received the document. Local
hashes and saved code support traceability, not a tamper-proof audit ledger.

Open `record.json` first for status. For an accepted workbook, start with **Start
here**, **Checks**, **AI reviews** and **Sources**. Historical-cell comments identify
the saved document, unit and numeric-token index. For an XLSX source, the corresponding
logged evidence also identifies the original cell. Check definitions, dates and units
alongside the amount. Python stores normalized base-unit values; Excel shows each
row in its documented source scale. **Checks** now includes the basis of each check
(source corroboration, arithmetic construction, blind reconstruction or inventory).
**AI reviews** shows the independently recorded facts and expected lines as well as
the subsequent cited verdicts. Inspect `record.json`/`calls.jsonl` for complete context.
Same-source reconstruction is explicitly recorded; it is not a second independent
underlying observation. A reported cash-continuity adjustment disclosed only for one
period leaves unrelated historical cells blank, never zero.

Excel now contains **working formulas for derived historical rows**, generated from
the same signed accounting relationships Python uses, with cross-sheet links and
unit/scale conversion. Independently reported totals remain source inputs; Checks
compares them with their components instead of turning evidence into a constructed
balance. Missing/deleted inputs produce an input error rather than silently becoming zero.

The eight financial tabs have company/statement headings, financial lines down the
rows, historical years across columns, frozen headings, number formatting and five
yellow blank forecast columns by default. Reported inputs are blue; calculations
are black, with cross-sheet formulas green. Row IDs, definitions and other audit
metadata are grouped to the right; expand them when needed. Source comments remain.
Start here, Checks, AI reviews and Sources make twelve tabs in total.

Open the workbook in Excel or a compatible calculation engine to calculate its
formulas. Automatic full recalculation is requested; no cached formula results are
provided before opening. Python's frozen numerical results remain in `record.json`
and cell comments. Excel arithmetic updates after edits, but saved Python results,
source reviews and acceptance do not. Checks clearly separates recorded results
from live Excel differences/flags. Edited spreadsheets are local scenarios, not a
second maintained production model or an import into Python. Existing saved workbooks
remain unchanged; these features apply to newly generated exports.

Blank columns and historical accounting links remain a forecast framework, not an
operating forecast engine. No workbook is published for unresolved
runs. An interrupted export can leave `model.pending.xlsx`; it is not a completed
result. `record.json` is authoritative, and an interrupted process can remain
`in_progress`. Earlier run folders are never overwritten.

## Current state and verification — 10 October 2026

The reusable workflow, real API adapter, bounded source reader, numerical checks,
formula-based Excel export, per-stage usage and $20 estimated-cost stop are implemented.
The previous fixed `nestle.py` extractor and its
`--sources` command have been removed. Company-specific definitions now belong in
cited run data. The Nestlé config remains an identity/topic example for setup and
the synthetic FX demonstration; it is not a prerequisite for initiation.

**76 offline tests pass.** They exercise two unrelated fictional companies with
different layouts/currencies, extraction batches, reviewer search/read navigation,
autonomous correction, accounting and precision failures, missing citations, review
omissions, budget exhaustion, immutable runs, source hashes and empty forecast cells.
API responses in the tests are mocked, including incomplete/refused/malformed
responses. Additional tests cover private settings, cache/reasoning accounting,
long-context pricing, missing usage and preserving costs for failed responses.
New cases cover blind context isolation, independently read headers, frozen facts
before semantic comparison, equal-valued definition/vintage disagreements, wrong
years/units/entities, exact versus rounded source comparisons, inventory omissions
and duplicate matches, shared financial totals, fresh checks after repairs, cash and
segment-profit bridges, sparse restatement adjustments and independent liability
components. Formula tests evaluate linked cell arithmetic against Python, cover
scale/sign conversion, sparse periods, source-input edits, injection and Excel's
formula-length limit. Spending tests cover exact/crossed thresholds, a charged final
review, unknown/stale usage, per-stage totals, no-progress stops and successful runs
beyond the former call/navigation/draft ceilings. These use scripted reviewers;
they demonstrate gates, not live AI skill. Setup doctor also passes. No paid calls
were made for this step, and a real Excel application was not used in these tests;
new workbooks request recalculation when opened there.

The user-supplied key is stored locally; a live, non-generating model lookup verified
authentication and access to `gpt-6.1-sol`. The small Responses generation test returned
HTTP 429 without usable token usage or a recognized detailed error code. A restricted
network attempt had failed before this lookup/test. No successful live generation
or full AI company initiation has been verified. Token cost for the failed attempt
is unknown, not recorded as zero. Check the account's rate limits/quota/billing and
retry `api-check` before the first company run; the response did not identify which
limit applied. No earlier company or FX run was changed.

The prior fixed Nestlé reference remains intact:
[model.xlsx](outputs/nestle_2024_2025_20261010T180411Z_c133cf62/model.xlsx).
It contains 263 historical rows and 577 passing checks on the FY2025 publication
basis, including restated 2024 comparisons. Its originals and historical code
snapshot remain beside it. That older result validates its fixed extraction scope;
it does not prove the new AI workflow reproduces it. Earlier failed and FX runs are
also preserved.

Acceptance means the configured checks passed. It is **not an error-free guarantee,
an audit opinion or proof that every disclosure was captured**. AI can miss an
omission or share a semantic error across reviews. Deterministic checks prevent
specific failures; they cannot establish every economic interpretation.

Three complementary gates are implemented: deterministic reconciliations, blind
source reconstruction followed by cited semantic comparison, and an independently
recorded coverage inventory followed by structural review. Earlier verdicts are
withheld from new independent passes. Evidence must have been read within the relevant
review; another stage's reads cannot satisfy that requirement. Every revision reruns
the gates, and disagreements never pass by majority vote.

Cash-flow/balance-sheet cash and adjacent-period continuity need explicit cited
bridges; legitimate definition differences use reported adjustments. Segment profits
must reconcile to their disclosed group measure without assuming it equals net income.
Liabilities may sum independently disclosed components, but deriving them from assets
minus equity cannot satisfy the independent balance-sheet check. Repeated originals
are identified by content hashes. Shared financial totals can serve multiple sections
without duplicate editable rows; distinct expected lines within a section cannot reuse
one row to conceal an omission. Income/outflow signs have a common documented convention
for extraction and reconstruction; stock signs follow the source presentation.

Independence here means separate input context and committed findings, not proven
statistical independence. The same configured reviewer model and document parser can
still share errors; no rendered-page verification or fresh independent web discovery
was added. Semantic equivalence and the initial disclosure inventory still require
AI judgment. Multiple passing gates therefore do not supply a numerical confidence
level. No live API calls or new company outputs were created for this implementation.

Current boundaries: annual statements with signed additive accounting bridges;
up to five historical years, 500 rows and 12 source documents; bounded source sizes,
navigation and context. Text-based PDFs, ordinary XLSX and UTF-8 HTML are supported.
Scanned reports needing OCR, unsupported spreadsheet formats, blocked/paywalled
sites, proxy-only networks, ambiguous entities and unsupported sector conventions
can end incomplete. The source downloader accepts public HTTPS only. This is a
reusable engine with explicit limits, not demonstrated universal company coverage.

## Next milestone

First resolve the generation endpoint's HTTP 429 and obtain a successful `api-check`
with reported usage. Then, with API/model settings stored locally, run the generic process for Nestlé's
2024–2025 accounts and compare it with the preserved originals/reference. Record
wrong mappings, omitted lines, reviewer failures, costs and runtime; improve the
generic workflow from those findings. Then repeat with an unrelated real company
without adding a bespoke extractor. Offline scripted tests are a prerequisite,
not evidence that unattended real research is already reliable.

Check hardening is implemented and tested offline. Next measure missed errors, false
alarms and the additional calls/cost on reviewed real examples, including wrong years,
units, omissions, restatements and overlapping segments. Compare aligned official
disclosures where available without counting repeated figures as independent evidence.
Review document-context and output limits against the actual Nestlé row count before
treating unattended acceptance as reliable; offline scripted cases do not establish it.

Formula exports and spending visibility are now implemented. Use the first successful
live run to inspect the workbook in Excel and measure each stage's tokens, cost and
useful corrections. Optimize expensive stages from those observations without revealing
proposed answers to blind reviewers or downgrading financial judgment merely to reduce
price. The removed request caps no longer impose an artificial row-count bottleneck;
the $20 stopping threshold does not guarantee every company will complete within it.

Keep the scope historical. Forecast drivers and distributions, a separate DCF,
news maintenance and measured forward performance follow this accepted evidence
foundation. The complete research cycle remains in PROJECT_BRIEF.txt.

## Files and local setup

The three new modules replace one Nestlé-only module; each has an implemented role:

| Location | Purpose |
|---|---|
| `src/research_platform/initiation.py` | Reusable research, extraction, review, revision, numerical validation and workbook workflow |
| `src/research_platform/ai.py` | Private settings loader, provider connection, reported token usage and dated cost estimates |
| `src/research_platform/evidence.py` | Original sources, document search/read and numeric parsing |
| `src/research_platform/project.py` | Project discovery and existing setup validation |
| `src/research_platform/fx.py`, `demo.py` | Synthetic currency demonstration |
| `src/research_platform/__main__.py`, `__init__.py` | Terminal commands and package identity |
| `configs/companies/nestle.json`, `configs/shared_factors.json` | Existing setup identity/topics and FX conventions |
| `tests/test_setup.py` | Workflow, source, adapter, financial, setup and FX checks |
| `pyproject.toml`, `.gitignore` | Dependencies and exclusions |
| `PROJECT_BRIEF.txt`, `AGENTS.md`, `README.md` | Ambition, working rules, progress |

No services, database, company-specific code folder or new documentation file was
added. `outputs/` and research data stay out of Git; back them up separately.
`.venv/`, caches and `*.egg-info/` are generated Python support files.
The sole new local settings file, `.env`, is also ignored by Git; it is not code or a
model input archive, and it is unnecessary for offline tests.

Python 3.11+ is required. For a fresh checkout create `.venv`, then install the
project with `python -m pip install -e .`. Existing pinned `openpyxl` and `pypdf`
dependencies are reused; the API connection uses Python's standard library.

```powershell
.\.venv\Scripts\python.exe -m research_platform doctor
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`demo-fx` remains available; running it creates a separate synthetic output folder.

## Decisions

| Date | Status | Decision |
|---|---|---|
| 10 October 2026 | Confirmed | Nestlé first; Python calculates, Excel supports inspection. Preserve the wider research cycle and keep these three documents current. |
| 10 October 2026 | Confirmed | Current financial scope is history plus blank forecasts. Assumptions, distributions, forecast calculations and DCF remain deferred. |
| 10 October 2026 | Superseded | A fixed Nestlé extractor does not satisfy the user's reusable initiation requirement. Its result is preserved as a reference; its code entry point was replaced. |
| 10 October 2026 | Confirmed and implemented | AI discovers companies, sources and reporting structures; separate reviews and deterministic gates drive bounded autonomous revision. This supersedes the earlier deferral of historical AI orchestration. |
| 10 October 2026 | Implemented boundary | Three cohesive modules separate API access, evidence and initiation. Private API/model settings now load from ignored `.env`, with environment overrides; secrets are excluded from run snapshots. |
| 10 October 2026 | Provisional model choice | Start with GPT-6.1 Sol for all roles to establish a correctness baseline. Compare Luna extraction later; Astra requires an observed benefit. Report usage and estimated cost on each call. |
| 10 October 2026 | Verified access; generation unresolved | The key authenticated for a model lookup; a small Responses test returned HTTP 429 without usable usage. No successful live historical initiation or measured company-run cost is claimed. |
| 10 October 2026 | Explicit limitation | No zero-error promise. Unsupported or unresolved cases terminate incomplete; accepted results still require empirical evaluation of real-world accuracy. |
| 10 October 2026 | Confirmed and implemented | The user authorized stronger independent checks: blind source reconstruction with recorded facts before semantic comparison, evidence-first coverage inventory, isolated verdicts, and stronger cash/segment/accounting reconciliations. Every revision reruns gates; no majority approval. Implemented within existing files. |
| 10 October 2026 | Verified offline; live evaluation pending | 76 offline tests and setup doctor pass, including accounting/reviewer isolation, generated formula arithmetic, stage accounting, exact/crossed dollar thresholds, missing usage and progress beyond the removed call ceilings. No paid run or real Excel recalculation was performed for this step. Separate contexts and repeated agreement do not establish statistically independent errors or a confidence percentage. |
| 10 October 2026 | Confirmed and implemented | The user approved working historical Excel formulas and a familiar financial layout. Formulas derive from Python's equation definitions; reported evidence and recorded reviews remain independent, forecasts blank, workbook edits local. No extra project files or older-run changes. |
| 10 October 2026 | Confirmed and implemented | Replace every request/draft-count ceiling with a $20 cumulative estimated-cost stop (lower thresholds allowed). Include all stages and charged failures, stop on unknown costs, preserve no-progress/data checks, and report total and per-stage tokens/USD during and after the run. Last-request overshoot remains possible; this is not an invoice guarantee. |
| 10 October 2026 | Confirmed model choice for this step | Keep Sol for every role: no current AI task is demonstrably low-stakes enough for a confident Luna substitution. Simple mechanical work already runs in Python; revisit model choices using measured stage costs and accuracy. |
| 10 October 2026 | Unresolved | Measured unattended accuracy/cost and optimal model mix, additional document/sector support and later production-baseline promotion rules. |
