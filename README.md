# Research platform — reusable company initiation

Build a cited historical financial model from a **local company source archive**,
check it, and generate an inspectable Excel workbook with **blank forecasts**.
The default is ten fully reported fiscal years plus their reported interim periods.
Nestlé is the first proving case, not a company-specific Python model.

[PROJECT_BRIEF.txt](PROJECT_BRIEF.txt) holds the wider research cycle;
[AGENTS.md](AGENTS.md) holds standing instructions. This README owns current
operation, verification, next steps and dated decisions. These remain the only
maintained project documents.

## Current state — 11 October 2026

Local initiation is implemented in the existing modules. The terminal command
requires a source folder and never starts browser discovery or downloads new
company evidence. The original injected acquisition route remains for regression
fixtures/explicit adapter tests, not a terminal mode. Earlier runs remain preserved.

The implementation includes local input snapshots and unchanged originals, an AI
reporting map, ten-year history by default, annual extraction/review tasks, cited
reporting versions, period-specific equations, independent company-source checks,
coverage/structure reviews, a combined-history challenge and formula-based Excel.
It preserves compatible completed work across interruptions, reports elapsed time
and stage/whole-run tokens and costs, and enforces the cumulative $20 estimate stop
plus a conservative allowance before sending each new local OpenAI request.

No assumptions, distributions, forecast calculations, DCF, news scheduler, database
or cloud service is implemented. **Live company-model accuracy and completed
ten-year cost remain unverified.** The supplied Visible Alpha workbook has been
inspected and its historical input selection checked locally. Its financial
mappings have not yet completed a live initiation. Scripted success and correct
cell selection do not establish real-company AI extraction accuracy.

The last browser-based Nestlé attempt cost $22.5400894 with no completed historical
rows/checks. Large repeated contexts and failed source navigation dominated that
attempt; it is not a per-year price to multiply by five. Earlier $5–15 completion
estimates were withdrawn. This rewrite removes that acquisition loop and improves
context/cost control, but actual savings require a completed benchmark.

## Source folders

Use the existing Git-ignored location:

```text
local_store/nestle/
  visible_alpha/
  financial_reports/
  transcripts/
  sources.csv
```

Create categories when storing actual originals. No new input folders or company
documents were created during this rewrite. Readable primary company evidence in
`financial_reports/` is required. Vendor exports can supply structured actuals;
they cannot independently verify themselves. Transcripts and `sources.csv` are
optional. Storing a file does not automatically send it to an AI.

The current inventory accepts 439 originals: 372 financial-report files, 66 transcripts
and `visible_alpha/NESN_CH Visible Alpha.xlsx`. The index includes restatements,
accounting definitions and transaction documents. Its five `not-found` entries
concern event transcripts, not a demonstrated absence of financial statements.
Collection metadata still needs source-level verification during initiation.
Earlier local checks accepted the 438 public originals and verified their supplied
hashes; all 136 public spreadsheets (38 XLS and 98 XLSX) parsed. The additional
VA workbook also parses, with no formulas or Excel error cells. Its original bytes
are preserved, including future consensus. These are readability/selection checks,
not acceptance of financial mappings or reporting definitions.

Keep unmodified VA exports, their labels/definitions, fiscal dates, currencies,
units, actual/estimate flags and export dates. Current exports may contain revised
history and do not establish what was known at an earlier date. Consensus estimates
must stay distinguishable from actual history and the future blank forecast model.

For the supplied VA template, initiation uses the lower company-specific/reporting
tables as instructed by the user. The upper standardized tables through Ratios
cannot supply model inputs. Within company tables, prefer `Filings`, then eligible
`VA Actuals` on a verified compatible basis. Company documents fill gaps and provide
independent support. A vendor actual label can include inferred quarterly numbers;
it does not prove that the company directly disclosed that period or definition.

The parser recognises repeated fiscal-period/source headers after Ratios without
Nestlé row-number constants. The actual file's boundary is at rows 1198–1199, with
company tables from row 1200; it has no literal company-reported section marker.
The designation is recorded as user-origin, not independently certified by VA.
Each column is classified separately: estimates are interleaved with actuals.
`Consensus`, `E`-labelled periods, unknown classifications, vendor helper rows and
ambiguous dash values cannot become historical observations, even when AI marks
them actual. Unknown vendor layouts use company evidence instead; arbitrary
VA CSV/XLS layouts are not automatically treated as reported actuals.

Python prepares an explicit historical AI input view with company metric rows,
requested-year actual/filing cells, headings, units, notes, legends and missing
markers. Original cell addresses and numeric indexes are retained. Standardized
tables, helper calculations, forecasts, unrequested years and unclassified extra
worksheets are excluded from this view, not deleted from the original. Company
documents still arrive whole. Consensus remains available for later dated research
and comparison; no consensus import/forecast engine is implemented now.

Python reads saved Excel cell values. It does not run VA add-ins or recalculate
imported formulas. Missing formula caches make a source unreadable; existing caches
carry an explicit warning that freshness is unverified. Preserve originals and,
if necessary, add a separately identified self-contained values export.

Company evidence should include consolidated statements and complete notes,
FY/H1 results, Q1/9M sales releases, results presentations, official Excel tables,
APM definitions/reconciliations and restatements. Include opening balances where
absent from earliest comparatives. Transcripts provide management explanations.
Relevant transaction or investor-day documents can explain changes in business
perimeter and reporting; they fit the same folders.

Useful context often already appears in the reports: acquisitions/disposals,
discontinued operations, segment/geographic changes, accounting transitions,
reported/adjusted bridges, FX/organic-growth definitions, debt and leases, pensions,
working-capital composition and changes in shares. Collect targeted missing context,
not every public news item or unused future research category.

Nestlé's [publications archive](https://www.nestle.com/investors/publications)
identifies Q1/9M releases as sales-only. Its [results archive](https://www.nestle.com/investors/results)
and [presentations archive](https://www.nestle.com/investors/presentations) link related
materials. FY2016–FY2025 is ten complete years; keep published 2026 documents
separately identifiable. Initiation currently selects completed fiscal years,
not an unfinished current fiscal year.

Use lowercase names such as
`nestle_2025-fy_financial-statements_pub-2026-02-19.pdf` and
`nestle_va_group-financials_export-YYYY-MM-DD.xlsx`.
Fiscal period, publication date and export date are different facts. Filename dates
are navigation hints; unverified publication timing remains unknown.

An optional `sources.csv` records relative filename, original title/download URL,
referring page, periods, publication/download dates, reporting basis, retrieval
status and actually calculated hashes. Supplied metadata is retained, not treated
as primary proof. Python hashes originals itself. A found URL is not a downloaded
file; missing archive evidence is not proof of company non-disclosure.

## Run and resume

From the project root after installation and private API configuration:

```powershell
.\.venv\Scripts\python.exe -m research_platform initiate "Nestlé S.A., NESN, SIX, Switzerland" --sources local_store/nestle
```

The default requests ten fully reported fiscal years evidenced in the archive,
including their reported interims. It cannot silently accept fewer years.
For the smaller initial validation slice:

```powershell
.\.venv\Scripts\python.exe -m research_platform initiate "Nestlé S.A., NESN, SIX, Switzerland" --sources local_store/nestle --years 2024 2025
```

Use `--history-years N` instead of `--years` for a different count.
`--forecast-years N` changes blank forecast columns; `--budget-usd` can reduce,
but cannot increase, the $20 limit.

Repeat the same command to reuse the latest compatible progress. Accepted results
return without AI calls; interrupted work continues in a new folder with paid usage
carried once. `--resume outputs/<run-folder>` explicitly selects the latest matching
run. `--fresh` starts new research and a new budget, preserving older runs.

A matching older browser run, changed archive location/content/index, code, parser
environment or model/effort settings cannot silently resume or restart. An explicit
`--fresh` is required to start again. Preserve ancestors referenced by continuations.
The original research date is frozen during resume.

Pending-call identity is saved before dispatch; returned responses/usage are saved
durably afterward. An interrupted request with no saved response has an unknown
charge and blocks further spending. Lost-response retrieval and manual charge
reconciliation are not implemented. Known charged failures remain counted.
An OS lock prevents concurrent initiations from branching a budget.

## Workflow

1. **Validate and preserve inputs.** Python inventories files, hashes the archive
   and optional index, checks matching saved work, copies unchanged originals and
   indexes pages/cells locally. No readable primary reports means no AI call.
   Source errors remain visible; optional failures cannot justify invented data.
2. **Establish the reporting map.** AI reads selected company originals to identify
   the consolidated group, currency, fiscal dates, annual years and disclosure
   cadence. Every year needs cited Q1–Q4, H1–H2 and 9M coverage decisions. A required
   missing file is a gap, not company non-disclosure. No browser fallback exists.
3. **Build each fiscal year's history.** The extractor reuses established concept
   and basis definitions. A recognized VA historical table is preloaded without
   a paid navigation call; the AI adds primary context and uses company tables for
   missing or unsupported cells. It proposes exact numeric references and accounting
   relationships. Python reads the amounts and enforces vendor eligibility/periods. Compatible
   concepts reuse IDs; changed regions retain distinct historical row versions.
   Draft output groups are small; company documents are never page-batched.
4. **Combine and check.** Python checks each annual proposal and the combined
   history, preserving per-period equations and calculated schedules. It does not
   relabel old regions as today's structure. Compatible equal cited cash balances
   can be linked mechanically; cross-basis cash needs reported adjustments or
   documented no-effect evidence, not invented zero plugs.
5. **Reconstruct source facts independently.** A reviewer receives concepts/periods,
   not the candidate's numbers, citations, definitions, basis claims or verdicts.
   It must reconstruct from company financial reports, not the VA export.
   Its facts are saved before Python compares amounts and source-derived precision.
6. **Compare meanings.** Only then does another comparison see candidate and frozen
   reconstruction together. It checks entity, periods, definitions, reporting vintage,
   units, scale and sign. Equal numbers alone cannot establish equivalence.
7. **Check omissions and structure.** For each year/section, an independent inventory
   records expected disclosures before seeing the model. A structural reviewer
   matches the model against that inventory and challenges omissions, overlapping
   segments, accounting links and blank forecasts. Other verdicts remain withheld.
8. **Challenge the complete history.** Multi-year runs receive a separate review
   of accounting/perimeter changes, segment lineage, definitions, restatement
   vintages, cross-year bridges and requested coverage. It must find missing changes,
   not merely approve the proposed ledger.
9. **Revise or publish.** Disagreements return to extraction, with attempts/critiques
   preserved and gates rerun. Missing evidence, unknown costs, insufficient budget,
   API failure or no progress stops incomplete. Only acceptance publishes Excel.

Coverage includes segments, income statement, balance sheet, cash flow, working
capital, net debt, equity and shares. Annual core statements cannot be waived.
Sales-only interims keep unavailable statement cells blank with cited reasons.
No invented quarters, cumulative subtraction, missing-as-zero values or balancing
plugs are implemented.

Accounting gates include segment/group revenue and profit links, assets versus
liabilities/equity, profit links, cash-flow categories, cash balances, date-aware
cash continuity and working-capital/net-debt composition. They distinguish reported
corroboration from identities that balance by construction.

## Historical versions and Excel

Every available local row/period has a cited reporting basis: accounting standards,
consolidation, segment structure, measurement convention and relevant version date.
Unchanged frameworks reuse IDs across annual publications; source metadata separately
preserves publication vintages.

The change ledger records old/new bases, effective dates, affected rows, reasons,
source references and treatment: published restatement or explicit comparability
break. Later recasts do not erase original files or imply point-in-time vendor data.
Equations and derived compositions can differ by period. Changed segments retain
original entity labels and versioned row IDs; overlapping versions cannot be summed.

Mixed-basis equations need cited bridges. Core identities and ordinary calculations
need compatible bases; same-date stocks are compared within a basis. Documented
no-effect cash transitions still need primary evidence, a change ledger and matching
amounts. Equal numbers alone are insufficient. Unsupported historical recasts and
automatic currency conversions are not implemented; they remain explicit gaps.

Excel has familiar financial sections, historical period columns, source inputs,
generated formulas and five blank future annual columns by default. Formulas use
the same definitions as Python. Basis breaks and versioned segments are visible;
the **Reporting basis** sheet and cell comments explain versions and source links.
For VA observations, comments also show the source channel (`Filings`/`VA Actuals`),
original cell and source period. Consensus never fills the blank forecast columns.
No trend calculation silently assumes all years are comparable.

Read **Start here**, **Checks**, **AI reviews**, **Reporting basis** and **Sources**.
Workbook edits recalculate arithmetic, but do not update Python inputs or renew
frozen source/AI acceptance. Offline tests do not claim actual Excel-engine
recalculation or audited Nestlé accuracy.

## Costs and reasoning

Models remain unchanged. No role was silently moved to Luna. The local route
removes paid browser/source-recovery decisions; Python handles file reading,
numbers, hashes and arithmetic. AI handles interpretation and challenge.

The supplied VA workbook's generic complete index was about 18.74 MB of compact
JSON (146,820 numeric entries). The new 2024 company historical view is about
0.476 MB (2,881 entries); the 2016–2025 view is 2.709 MB (24,008 entries). Every
eligible selected company metric cell was checked against its original numeric
index, with no changed values. These are input-size measurements, not token counts
or measured dollar savings. Annual tasks preload their own view; separate primary
number/completeness checks remain required. No model downgrade was made.

The catalogue occupies a stable first message, followed by complete selected
documents in individual messages, then changing drafts/feedback. Compact JSON
avoids duplicate evidence; structural reviews do not resend the full collection
index alongside the catalogue. Each annual task/review retains its own complete
selected company documents and explicit vendor historical views. This supports
[prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching),
but hits/savings require measurement. Preview limits affect navigation only.

Discovery and the combined-history review can still select enough complete documents
to exceed provider capacity or budget. A compact ten-year synthetic fixture does
not prove a large real PDF/VA archive fits. No silent text truncation is permitted.

Reasoning is explicitly **medium / standard** by default. Optional private settings:

```text
RESEARCH_REASONING_EFFORT=medium
EXTRACTION_REASONING_EFFORT=medium
REVIEW_REASONING_EFFORT=medium
```

Supported values: `low`, `medium`, `high`, `xhigh`, `max`.
Effort/model settings enter resume metadata. Previous requests omitted effort,
but all twelve saved responses from the $22.54 run used medium/standard. Reasoning
cost was about $0.027; input dominated. Reasoning is included in output usage.
See [reasoning documentation](https://developers.openai.com/api/docs/guides/reasoning).

The dated code price table (10 October 2026), USD per million tokens:

| Model | Input | Cached input | Cache write | Output including reasoning |
|---|---:|---:|---:|---:|
| GPT-6.1 Sol | 2.00 | 0.10 | 2.50 | 10.00 |
| GPT-6 Luna | 0.10 | 0.01 | 0.125 | 0.50 |
| GPT-6 Astra | 10.00 | 1.00 | 12.50 | 50.00 |

Above 272,000 input tokens per request, configured rates double for input and
multiply output by 1.5. Unknown pricing/usage stops spending. Every charged call,
including failures, contributes once to whole-run and stage totals.

Before a new local OpenAI call, a conservative allowance uses UTF-8 input bytes
plus framing margin, the full output limit, and no assumed cache discount. It
uses the higher applicable input/cache-write rate. No paid token-count call or
new tokenizer dependency is needed. This can stop earlier than necessary.
Allowances are stored separately from actual usage and are never counted as charges.

A request that does not fit the remaining allowance is not sent. The post-response
$20 guard also remains: estimates are not an exact provider invoice guarantee.
Unknown charges block further spending. There is no request/draft-count ceiling.
Interactive calls show live elapsed time and final duration; redirected logs use
readable completion lines. Stage and cumulative tokens/USD follow each call.

## Setup, files and verification

Use Python 3.11+ and the existing environment; install with
`python -m pip install -e .` when needed. Configure `OPENAI_API_KEY`,
`RESEARCH_MODEL`, `EXTRACTION_MODEL` and `REVIEW_MODEL` in ignored `.env` or
environment variables. Environment values override local settings. Secrets never
enter prompts or run/code snapshots. No credentials were inspected or changed here.

```powershell
.\.venv\Scripts\python.exe -m research_platform doctor
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`api-check` is a small paid connection/structured-output test, not a research audit.
Doctor/tests are offline. The full suite passed **165 tests** in 191.8 seconds,
and setup doctor passed. Coverage includes one/two/ten-year local histories,
interims, source integrity, estimated-value rejection, reporting changes, formulas,
isolated reviews, budget allowances and interrupted resume. Thirteen vendor tests
cover company-section eligibility, interleaved consensus columns, fiscal periods,
original numeric references, context retention and primary-only blind reviews.
The actual VA workbook's historical projection was checked locally; these tests
do not validate its financial mappings or complete a live initiation. No paid run
was made for this work.

Supported local originals are PDF, XLS/XLSX, HTML and UTF-8 CSV/TXT. Legacy XLS
uses pinned `xlrd==2.0.2` (Excel 5 or newer), needed for 38 official tables in the user's archive.
Originals remain unchanged; no macros, vendor add-ins or formulas are executed.
Saved formula results are not proof of freshness. No OCR or rendered
PDF vision is implemented. Parser failures remain explicit. Limits include 25 MiB
per original, 500 PDF pages, 3,000 indexed units per document, spreadsheet dimensions of
10,000 rows/300 columns and archive checks. The twelve-document cap does not apply
to local archives. History accepts 1–30 fiscal years, default ten; the combined
model retains a 500-row limit. Provider context/output limits and unusual financial
structures can still prevent completion. These limits cannot justify omissions.

| Location | Purpose |
|---|---|
| `src/research_platform/initiation.py` | Reporting map, model/history ledger, checks, reviews, Excel and resume |
| `src/research_platform/evidence.py` | Local inventory, unchanged originals, parsing, search/read and numeric references |
| `src/research_platform/ai.py` | Private settings, provider, reasoning, stable context, tokens/prices and allowance |
| `src/research_platform/__main__.py` | CLI commands and live timer |
| `src/research_platform/project.py`, `__init__.py` | Project discovery, saved JSON and package identity |
| `tests/test_setup.py` | Offline synthetic financial/provider/parser/workflow checks |
| `README.md`, `PROJECT_BRIEF.txt`, `AGENTS.md` | Current operation, wider ambition and standing instructions |
| `pyproject.toml`, `.gitignore` | Dependencies and exclusions |
| `local_store/<company>/` | User originals, Git-ignored; no automatic AI upload |
| `outputs/initiate_<company>_<time>_<id>/` | Frozen record, copied sources, calls and accepted workbook |

Runs contain `record.json`, `calls.jsonl`, `sources/` and, only on acceptance,
`model.xlsx`. An interrupted `model.pending.xlsx` is not accepted. Preserve
ancestor folders and back up ignored research separately. A hash is provenance,
not a tamper-proof forecast ledger. Python environments/caches/build metadata are
generated support. `.git/COMMIT_EDITMSG` is Git scratch space. Old FX/demo/config
code stays removed; preserved synthetic outputs and the first Nestlé annual
reference are historical artifacts, not current inputs.

## Next milestone

Complete a 2024–2025 local validation using the inspected VA company historical
view and original disclosures. Check definitions and reporting versions as well as
values; the existing offline checks do not complete that financial validation.
Use this smaller validation before paying for the decade. The default remains ten years; explicit
`--years 2024 2025` narrows that empirical test.

Compare the workbook with originals, especially segment changes and reporting
versions. Measure omissions, errors, caching, cost and runtime. Then test the full
decade and another company with the shared engine. Passing arithmetic or repeated
AI agreement does not establish unattended accuracy or a confidence percentage.

If costs remain high, benchmark narrow Luna tasks or verified table/column mappings
applied mechanically across years. Those optimizations are not implemented or proven
Sol-equivalent. Preserve independent checks and complete selected documents.

Forecast drivers/distributions, DCF, news updates and forward evaluation follow
this history foundation. No new maintained module, service, database or handoff
document was needed. The only new dependency is the legacy XLS reader required
by actual collected files.

## Decisions

| Date | Status | Decision |
|---|---|---|
| 10 October 2026 | Confirmed | Nestlé first; Python calculates, Excel supports inspection. Preserve the wider research cycle and keep these three documents current. |
| 10 October 2026 | Confirmed | Current financial scope is history plus blank forecasts. Assumptions, distributions, forecast calculations and DCF remain deferred. |
| 10 October 2026 | Superseded | A fixed Nestlé extractor does not satisfy the user's reusable initiation requirement. Its result is preserved as a reference; its code entry point was replaced. |
| 10 October 2026 | Confirmed and implemented | AI discovers companies, sources and reporting structures; separate reviews and deterministic gates drive bounded autonomous revision. This supersedes the earlier deferral of historical AI orchestration. |
| 10 October 2026 | Implemented boundary | Three cohesive modules separate API access, evidence and initiation. Private API/model settings now load from ignored `.env`, with environment overrides; secrets are excluded from run snapshots. |
| 10 October 2026 | Provisional model choice | Start with GPT-6.1 Sol for all roles to establish a correctness baseline. Compare Luna extraction later; Astra requires an observed benefit. Report usage and estimated cost on each call. |
| 10 October 2026 | Connection verified; research accuracy pending | The user's terminal screenshot confirms a successful Sol api-check: 74 tokens and estimated $0.000252. The earlier HTTP 429 is no longer the latest connection result. No successful full live historical initiation or measured company-run cost is claimed. |
| 10 October 2026 | Explicit limitation | No zero-error promise. Unsupported or unresolved cases terminate incomplete; accepted results still require empirical evaluation of real-world accuracy. |
| 10 October 2026 | Confirmed and implemented | The user authorized stronger independent checks: blind source reconstruction with recorded facts before semantic comparison, evidence-first coverage inventory, isolated verdicts, and stronger cash/segment/accounting reconciliations. Every revision reruns gates; no majority approval. Implemented within existing files. |
| 10 October 2026 | Verified offline; live evaluation pending | 70 offline tests and setup doctor pass after removing obsolete FX/config checks; accounting/reviewer isolation, generated formula arithmetic, stage accounting, dollar thresholds and progress beyond removed call ceilings remain covered. No paid run or real Excel recalculation was performed for this cleanup. Separate contexts and repeated agreement do not establish statistically independent errors or a confidence percentage. |
| 10 October 2026 | Confirmed and implemented | The user approved working historical Excel formulas and a familiar financial layout. Formulas derive from Python's equation definitions; reported evidence and recorded reviews remain independent, forecasts blank, workbook edits local. No extra project files or older-run changes. |
| 10 October 2026 | Confirmed and implemented | Replace every request/draft-count ceiling with a $20 cumulative estimated-cost stop (lower thresholds allowed). Include all stages and charged failures, stop on unknown costs, preserve no-progress/data checks, and report total and per-stage tokens/USD during and after the run. Last-request overshoot remains possible; this is not an invoice guarantee. |
| 10 October 2026 | Confirmed model choice for this step | Keep Sol for every role: no current AI task is demonstrably low-stakes enough for a confident Luna substitution. Simple mechanical work already runs in Python; revisit model choices using measured stage costs and accuracy. |
| 10 October 2026 | Confirmed and implemented | Remove obsolete fx.py/demo.py, starter configs and demo command to reduce clutter. Keep project discovery, current initiation and all saved runs. Real FX research waits for an implemented economic need; its design principles remain in the brief. |
| 10 October 2026 | Verified cleanup | A follow-up source/dependency audit found no additional obsolete active modules. Removed unused duplicate version metadata and the stale generated source-tree egg-info directory; the installed package and doctor still work. Retain necessary support files and saved runs rather than reducing file count for its own sake. |
| 10 October 2026 | Implemented and verified offline; live rerun pending | The first inspected live Nestlé initiation stopped before downloads because discovery put routine scope/basis notes in the fatal issues field (58,105 tokens; estimated $0.1577425). The user authorized the fix: separate notes/blocking_issues, preserve notes for extraction and structural challenge, keep blind contexts isolated, and send only historical settings to discovery. Required evidence and accounting gates remain. All 75 offline tests and doctor pass. Earlier run preserved; no paid rerun for the fix. |
| 10 October 2026 | Observed transport failure; diagnostics verified offline | The next user-run initiation archived four PDFs and saved 41 unverified draft rows, then lost the fifth AI response after 9.58s. Recorded cost is $0.4090896 plus an unknown fifth-call charge. Preserve safe error categories, OS codes, request timing and client request IDs; show the primary failure before the cost guard. All 78 offline tests and doctor pass. No automatic retries, timeout/model changes or agent-triggered paid run. The original network cause and full model accuracy remain unresolved. |
| 10 October 2026 | Confirmed and verified offline | Show a live elapsed counter for each interactive CLI AI call, including api-check, plus final duration on success/failure; save initiation elapsed seconds in calls.jsonl. Redirected output receives one final duration. No background requests, retries or model changes. |
| 10 October 2026 | Confirmed and implemented; live evaluation pending | Historical initiation includes reported quarters, halves and cumulative 9M for selected completed fiscal years. Require cited cadence and per-section/per-period coverage, preserve sparse disclosures, distinguish stocks/flows and cumulative/standalone periods, and date cash bridges explicitly. Generate matching Excel columns/checks. No invented quarters or cross-period subtraction. All 89 offline tests and doctor pass; no paid rerun, new files or earlier-run changes. Source/context/cost limits and unfinished-current-year support remain explicit boundaries. |
| 11 October 2026 | Confirmed and verified offline; live recovery unverified | Resume the newest compatible matching initiation automatically; return accepted results without AI, and require explicit `--fresh` to start new research. Preserve earlier folders and original evidence, replay exact saved calls/source outcomes in isolated contexts, and carry each paid call's tokens/cost once across the continuation lineage. Save pending requests before dispatch, durably journal responses, and serialize initiation with an OS lock. Code/settings/parser/source drift, legacy records and unknown charges stop rather than trigger an unnoticed restart. Recover completed work around document acquisition and Excel export; no lost-response retrieval or usage-reconciliation command is implemented. All 109 offline tests and doctor pass, including 20 resume regressions. No paid calls or new maintained files. |
| 11 October 2026 | Diagnosed; proposed batching superseded | Run 49c86732 completed three paid calls ($0.3365008; 126,620 reported tokens) but both extraction reads exceeded the local evidence-size limit. Requests shrank from 13 units (121,113 measured characters including numeric-index overhead) to 10 (103,958), still above 100,000. Unchanged evidence/feedback triggered the no-progress guard. The user rejected the proposed size-aware page batching in favor of whole documents. The failed run remains preserved. |
| 11 October 2026 | Confirmed and verified offline; live evaluation pending | Read entire selected documents for extraction and every review, retaining full text and numeric indexes across each context's calls. Remove application character caps on indexing, HTML lines, evidence reads and AI inputs. All 112 offline tests and doctor pass; both failed reads from 49c86732 succeed against preserved PDFs. Keep exact citations, review isolation, no-progress detection and the cumulative $20 stop. Provider capacity and existing binary/parser/output limits remain explicit; never silently truncate. Older code/request checkpoints need an explicit fresh start. No new maintained files, dependencies, model changes or paid calls. |
| 11 October 2026 | Observed live failure; cost redesign proposed | Run 45d938bc stopped at $22.5400894 with zero financial rows/checks/reviews. Four source PDFs succeeded, 39 download attempts failed; repeated blocked URLs under renamed IDs escaped the no-progress guard, while each later AI decision received about 587k input tokens with very low cache reuse. Confirmed apostrophe-grouped numbers are split incorrectly. Withdraw the earlier $5–15 completion-planning ballpark. Propose generic parser/retry fixes, usable source recovery, stable full-document cache boundaries and a next-call cost allowance; test Luna only for narrow source-location work, retaining Sol financial judgments/reviews. Identical extraction usage repriced at Luna is $1.11548, not a demonstrated run cost or quality result. No runtime/model changes or paid calls in this diagnosis. |
| 11 October 2026 | User option under discussion; import not implemented | User is considering manually downloading both Visible Alpha history and company financial reports, with roughly ten years needed in practice. Recommend inspecting one unmodified Nestlé export, then a generic import feeding the shared model/check/export workflow with company disclosures for validation and gaps. Use Python for importing values and calculations; preserve actual/estimate distinctions, units, fiscal periods, reporting vintage and original file provenance. Missing export coverage is not company non-disclosure; repeated vendor reads are not independent source confirmation. Manual downloads avoid source-recovery calls but do not remove AI reading/review costs. Current five-year/twelve-source limits and absent local import require explicit work; measure a completed import before estimating ten-year spend. No file supplied, runtime/model changes or paid calls; source strategy remains a proposal. |
| 11 October 2026 | Storage provided; model/effort trials proposed | Created only local_store/nestle under its existing Git exclusion for the user's downloads; no automatic import/upload or AI cost. Stored reports support task-specific independent verification and definitions, without blanket inclusion in every prompt; selected documents remain whole. Verified no explicit reasoning setting exists, though all 12 responses in run 45d938bc used medium/standard: reasoning cost about $0.027 of $22.54, with input dominating. Several distinct Luna passes may be economical but require measured comparison with Sol, preserved checks and escalation beyond mere disagreement; no majority-vote equivalence claim. Explicit per-task effort settings remain proposed. No runtime/model changes or paid calls. |
| 11 October 2026 | Collection guidance proposed; no importer or downloads | Recommend three flat input categories under local_store/nestle: visible_alpha, financial_reports and transcripts, with one sources.csv generated during collection. Use fiscal-period/document-type/publication-date names, preserve original files and restatement versions, and distinguish missing documents from failed retrievals. Public collection prompt covers FY2016-FY2025 and already-published 2026 separately; official Excel tables and APM/restatement documents complement PDFs. Transcript storage does not imply automatic AI reading. Official archives inspected; no new folders/files beyond this README edit, runtime changes or paid initiation calls. |
| 11 October 2026 | Implemented and verified offline; live validation pending | User authorized local VA/company sources and ten years by default. Implemented frozen local originals/no browser, annual tasks with complete selected documents, independent company-source and coverage/structure reviews, combined-history challenge, cited basis/change ledger, period equations, actual/source-scale checks, Excel history labels, conservative pre-call allowance, stable catalogue/document messages and explicit medium reasoning. All 151 offline tests and setup doctor pass, including a complete synthetic decade with reported interims and documented-no-effect cash transitions. User archive: 438 originals/hash checks accepted; all 136 actual spreadsheets parsed. Added pinned xlrd for 38 legacy XLS originals, preserving bytes. Models unchanged; no paid run, financial mapping validation or real VA validation. |
| 11 October 2026 | Confirmed and verified offline; live financial validation pending | Prioritize the user's VA company-specific/reporting section for historical extraction, preferring Filings then independently supported VA Actuals. Recognize the repeated-header boundary after Ratios generically; record that its company-section designation comes from the user, not an explicit vendor label. Deterministically reject standardized/helper/consensus/estimated cells, missing-value dashes and wrong periods. Preload an explicit requested-year historical view with original numeric indexes and context; preserve the complete export and its consensus for a later step. This is a user-authorized exception to whole-document input for VA; company documents remain whole and blind checks remain primary-only. Actual workbook inspection verified all eligible cells in the views: 18.74 MB full numeric index versus 0.476 MB for 2024 and 2.709 MB for 2016–2025 (serialized bytes, not token or invoice savings). All 165 offline tests and doctor pass. No new maintained files/dependencies, model changes, paid calls or changes to originals. |
| 10 October 2026 | Unresolved | Measured unattended accuracy/cost and optimal model mix, additional document/sector support and later production-baseline promotion rules. |
