# Refractive Systems — reusable model construction

Build a financial model from a **local company source archive**, with traceable
historics, company drivers, temporary assumptions, period-based forecasts and
a portable Excel workbook. Historical-only `initiate` retains its stricter
acceptance gates and blank forecasts.
The default is ten fully reported fiscal years plus their reported interim periods.
Nestlé is the first proving case, not a company-specific Python model.

[PROJECT_BRIEF.txt](PROJECT_BRIEF.txt) holds the wider research cycle;
[AGENTS.md](AGENTS.md) holds standing instructions. This README owns current
operation, verification, next steps and dated decisions. These remain the only
maintained project documents.

## Current state - 24 October 2026

The reusable construction engine now has a causal functional-cost build, dated
regional scope events, separate transaction/translation FX, direct annual forecasts
beyond the detailed horizon, and explicit economic-driver contracts. The
[current Nestlé workbook](outputs/construct_refresh_20261024T164024Z_4c33b3f4/model.xlsx)
contains company information through 23 October and the preserved FX snapshot of
24 October at 15:01 UTC. It is a **provisional model with incomplete portfolio
closing accounting**, visibly labelled on the opening sheet. Passing arithmetic
checks does not resolve missing economic evidence.

All 389 offline tests passed in 359.0 seconds on the final code, including 27
causal financial tests and fresh-company construction/refresh fixtures. Setup doctor
passed. Desktop Excel matched 131,703 cells with zero differences and passed seven
restored sensitivity cases. Python reports 23,771 PASS, zero FAIL/MISSING and 80 warnings.
These include unavailable currency coverage, unmeasured transaction exposure and
material accounting limitations. Actual Excel views were rendered and inspected;
the saved workbook opens on Model near the operating build. See
[delivery verification](outputs/construct_refresh_20261024T164024Z_4c33b3f4/delivery_validation.json)
for exact test, source, layout, visual, budget and reuse evidence. Excel agreement
verifies implementation consistency, not economic calibration or forecast accuracy.

The generic fiscal calendar/as-of policy gives Nestlé Q1, Q2, Q3, Q4, H1, H2 and FY
for 2026–2027, then FY only for 2028–2030. No hidden forecast halves or quarters are
created beyond that horizon. Annual flows, opening balances, financing, depreciation,
tax, working capital and equity roll forward directly. Model and Assumptions have
no 9M columns; source 9M observations and derivations live internally on Historics.
FY shading is darker. Quarterly sales coexist with half-year financial flows and
H1/FY stocks; unsupported quarterly statements and H2 closing stocks remain absent.
Other fiscal calendars and annual/half-year/quarterly statement policies use the
same compiler and entry point; fresh research prompts explicitly permit annual
reporters and distinguish sales from full-statement frequency.

Functional cash-cost pools are authoritative. Their source-reconciled historical
baselines feed independent activity, variable/fixed share, unit-cost, spending and
absolute-budget controls, then translation and separately scheduled D&A. Segment
and group profits aggregate those costs. No forecast function expense is backed
out of a predetermined UTOP or margin. Nestlé uses production/procurement,
distribution/freight, marketing, administration and R&D pools. The marketing split
starts from the disclosed, rounded 8.6% historical advertising/marketing ratio;
future marketing is an independent spending budget, never a sales percentage.
COGS responds to its activity proxy and input costs, independently of selling-price
inflation. RIG includes mix, so its elasticity and variable share are provisional
inputs, not a claim of physical-volume measurement. Segment-by-function baseline
allocations are estimates, while presentation allocations are read-only diagnostics.

Dated operating scope events now sit within their regions and consolidate once.
Russia removes Europe operations from October 2026. The Peranel/Waters venture and
mainstream VMS disposal use explicit end-H1 2027 closing scenarios, with the retained
Waters interest distinct from full consolidation. yfood is added to Europe from its
control date; the regional assignment and undisclosed operating economics are
labelled estimates. Blue Bottle is recorded but cannot be independently quantified
from the supplied disclosures. Partial periods and the following year's annualisation
are handled once; whole-business disposal does not leave ghost revenue or negative
costs. The first annual-only sales/cost base carries the preceding modelled FY,
including its partial-year scope, instead of resetting to the last historical FY.
Full-entity depreciation stops use supplied dates; Waters receives no forecast
D&A after July 2026. Remaining group D&A is allocated proportionally as an explicit
estimate, with no second group deduction. Reporting reorganisations remain separate
from operating scope changes.

**Closing-accounting limitation:** consideration, gross assets/liabilities, retained
JV values/earnings and complete acquisition/disposal bridges are not all disclosed.
Known proceeds and net-asset/CTA amounts are preserved as evidence, but absent
counterparty balances are not invented to force reconciliation. The record and
specification therefore separately report `financial_completeness=incomplete_scope_accounting`.
Operational scope effects are modelled; portfolio cash/equity/asset integration is
not complete. Unknown transferred working-capital balances can affect projected
operating cash flow as well as missing disposal proceeds. Where closing transfers
are supplied, ratio-based closing stocks and cash bridges count them once. Synthetic known-answer closing entries prove the generic interface,
not these unresolved Nestlé transactions.

Costs follow one FX route: functional-currency cost, invoice-to-functional transaction
effect with explicit lag/hedge terms, then functional-to-reporting translation once.
Each pool can have its own mix. Unmeasured Nestlé cost translation and procurement
exposures are independent editable zero scenarios with labelled stress ranges;
zero does not assert domestic costs or no exposure. Revenue translation retains the
organic cross-term. Annual applied financial percentages divide summed monetary
impacts by summed bases. Where historical attribution was never disclosed, 144 mixed
2026 FY FX/OCI/share-count support summaries remain unavailable with exact component
reasons; they are not filled with zero. Future controls and statement totals remain
required. Reported historical company FX is unchanged.

Cash currency effects, operating transaction FX, financing remeasurement, foreign
balance movements and OCI have separate inputs. Working-capital FX/scope movements
do not become operating cash movements; cash FX does not automatically feed reserves.
Cash-translation and OCI attribution mismatches fail validation. Foreign asset/D&A
currency exposure remains incomplete: the independent translation test establishes
cash-operating-margin invariance, not complete foreign-operation EBIT/asset translation.

The FX database preserves originals, native observations, revisions and frozen
snapshots. Valid direct observations take priority; same-currency crosses use aligned
underlying dates/timestamps and retain their lineage. Crosses are calculated daily
before averaging. Reciprocal/cross checks quarantine inconsistencies using the stated
5% tolerance; this is not a claim of exact no-arbitrage across differently sampled
providers. Completed dates use actuals, current periods mix actuals and spot held over
remaining publication dates, and future periods hold eligible spot. Past gaps stay
missing. Reference fixings and broker MIDPOINT closes have distinct definitions.

| Currency | Selected coverage and limitation |
|---|---|
| BRL | Genuine ECB EUR crosses through 23 October. Q4 CHF per BRL average 0.1636198521; dated fixing proxy 0.1633531026. It is not blank and is not a live IBKR BRL quote. |
| CNH | Five native broker daily bars are retained but unapproved for historical selection; the required overlap was insufficient. Frozen USD cross spot exists; the Q4 period average remains unavailable. CNY stays separate. |
| ARS | Last selected genuine observation 25 September; stale spot/current-period gaps remain explicit. |
| VES | No genuine observations or eligible spot. No substitute currency is used. |

The daily archive starts in 2018; the 2016–2017 model-history gap remains visible.
The FX sheet exposes per-currency provider, observation date, spot date/time, type,
gaps and transition status; a global latest date does not imply universal coverage.
The previous read-only TWS handshake succeeded at 127.0.0.1:7496/client 71, server
178; this continuation did not repeat live broker requests or change account settings.

Factory-count revenue allocations and ARS/VES-to-BRL substitutions are removed.
Only principal-country customer-sales estimates remain, with unresolved residuals:

| Revenue basket | Unallocated share |
|---|---:|
| Americas | 15.82% |
| Asia/Oceania/Africa | 60.44% |
| Europe | 55.92% |
| Nespresso, Waters, Other | 100% each |

The weighted unallocated share is about 44.57% using the selected FY2025 segment
reference. Even the allocated amounts are customer-geography proxies, not verified
functional currencies: all baskets are flagged as weak exposure evidence. Costs do
not copy revenue baskets. The 1.00x calibration remains an unfitted scenario
multiplier and cannot cure missing data, hedges or unknown exposures.

Repurchases no longer infer an execution price from book equity. Inactive buybacks
allow a missing price; positive cash requires a valid price and explicit share timing.
Closing and weighted-average shares are distinct. The current opening share count
still uses weighted-average history as a disclosed proxy. Dividend amounts are
annual cash pools with separate payment schedules; annual payout diagnostics divide
annual dividends by matching annual profit instead of averaging interim ratios.
Recurring restructuring and
operating adjustments persist under explicit temporary policies, and their effects
are separated from underlying profit growth. Lease renewal, capex, tax settlement,
flat balance-sheet accounts and foreign-asset FX remain provisional. The research
artifact classifies supported policies, simplifications and unresolved inputs,
including future IFRS 18 presentation not yet certified in this management model.

All supplied company observations remain unchanged. Active history uses 2,608
company-document cells, 2,070 calculations, ten company-reported VA cells and 99
calendar calculations; these are cell counts, not unique disclosures. Standardized
VA analytics and consensus do not become company actuals. Native Model, Assumptions,
Historics, FX and Historical Segments remain self-contained. Workbook edits do not
update Python inputs or renew frozen reviews; there is no Bunzl runtime dependency.

The same fresh CLI path passes a synthetic GBP company with a June year-end,
different segments and a published predecessor split, including database consumption
and zero-AI refresh. Separate fixtures cover genuine quarterly and annual reporters.
Provider and Excel bridges are mocked in onboarding tests; Nestlé's Excel checks are
real desktop runs. **No second real company has been validated.** Fresh ten-year
research accuracy and cost remain unmeasured. The operating-company role contract
is not a universal bank/insurance model; official-index unattended HTTP access also
remains unresolved.

This work made zero application LLM calls. The cumulative known cost is $3.200947785,
with $0.923841500 unresolved reservations: $4.124789285 committed and $15.875210715
remaining under the original $20 ledger. There are 64 settled and two unresolved
requests. Reservations are not charged usage or an invoice ceiling. Luna remains
the inexpensive default; fresh reviews now receive the actual causal period graph.
This deterministic continuation preserves earlier source/AI reviews and does not
claim renewed live AI semantic acceptance.

Repeated refreshes replace current FX-contract and transaction-FX checks rather
than accumulating duplicate warnings; source/AI reviews remain frozen. The renderer
writes unique pane selections and compact review comments. Commentary exceeding
its Excel output limit is preserved in full in the audit artifact with an explicit
cell pointer; source/review inputs are not truncated. One presentation export failed
to open in Excel and remains recorded as incomplete; the corrected export passes.
A later D&A guard exceeded Excel's formula limit; splitting it into a named support
calculation preserved the financial logic. The failed attempt and test logs remain.
The final visual review verified annual carry-forward, stopped depreciation and
payout ratios; eight unchanged views were byte-compared with inspected renders,
and final opening/financing views were inspected directly.

Earlier runs, failed exports and their evidence are preserved. The formerly delivered
12:30 workbook's hash changed after completion, so continuation used its verified
12:07 parent without rewriting that altered file or its record. Company-specific
economics, dates and mappings live in cited run inputs; generic calculations,
source-format adapters and rendering remain separate.

## Construct, update and export

After an editable install, the normal commands are:

```powershell
python -m research_platform construct "Company name, ticker, exchange" --sources local_store/company
python -m research_platform update RUN
python -m research_platform refresh-fx RUN
python -m research_platform export RUN
```

`RUN` is the directory name printed by the previous command, or an absolute run
path. Construction generates company research inputs when absent; repeating a
compatible request reuses saved work. Update checks current official disclosures,
adds independently reconstructed facts and rebuilds. Refresh-FX reads a new snapshot of the shared database and recalculates; export
recalculates frozen saved inputs. Both are
strictly zero-AI operations and create new preserved output folders. Keep ancestors:
continuations may share verified immutable source snapshots stored there.

`pyproject.toml` holds the shared `fx-database`, bootstrap-only `fx-source`,
non-secret broker settings and `cheap-review-repairs` default. Import once, then
update the database independently of any company:

```powershell
python -m pip install -e ".[ibkr]"
python -m research_platform fx-import
python -m research_platform fx-update --diagnostic --pairs EUR/USD USD/CHF USD/MXN
python -m research_platform fx-update
python -m research_platform fx-update-ecb
python -m research_platform fx-status
python -m research_platform refresh-fx RUN
python -m research_platform export RUN
```

`fx-update` requests only recent missing dates plus the configured seven-day overlap
and current bid/ask data. It never re-downloads the full archive. Unsupported direct
pairs can use supported native USD/EUR legs, with crosses calculated locally.
`fx-update-ecb` is an explicit official reference-fixing update, useful where the
broker has no supported contract. `fx-status` saves detailed provider/pair coverage.
Exit code 0 means success; code 2 means incomplete broker data, with successful
pairs preserved and detailed failures saved. These commands all make zero LLM calls.

A company refresh makes no broker request: it reads the database at the current FX
UTC timestamp, freezes the snapshot and recalculates a new preserved run. The company
information date stays separate. `--snapshot ID` replays a specific FX snapshot;
`--fx-as-of TIMESTAMP` chooses an explicit timestamp with timezone. `--model-inputs`
can supply versioned exposure/policy changes while preserving company facts.
`--fx-source PATH` retains an explicit legacy workbook adapter; ordinary operation
uses the database. Export uses saved inputs without refreshing either source.

For Windows Task Scheduler, create a daily task under the logged-in local user.
Program: the absolute project `.venv\Scripts\python.exe` path. Arguments:
`-m research_platform fx-update`. Start in: the project root. Schedule after the
chosen market close, keep TWS/IB Gateway running and authenticated, and inspect the
saved `outputs/fx_update_*/result.json` and task exit status. Do not create an
unattended-login claim: periodic broker reauthentication remains necessary. No task
was installed automatically. Configure the TWS login timezone to match
`session-timezone` (currently Europe/London); this configured timezone has not been
independently read back from TWS. Keep Enable ActiveX and Socket Clients enabled,
Read-Only API checked, port 7496, localhost trusted and client ID 71 available.

The adapter follows IBKR's [FX contracts](https://www.interactivebrokers.com/docs/tws-api/contracts/fx-pairs),
[historical-bar definitions](https://www.interactivebrokers.com/docs/tws-api/doc/md/historical-bars)
and [local API setup](https://www.interactivebrokers.com/campus/trading-lessons/installing-configuring-tws-for-the-api/).
Its [market-data guidance](https://www.interactivebrokers.com/docs/general/market-data-subscriptions/introduction)
says Forex requires no additional market-data subscription. Tested availability is
reported above; an unavailable contract is not treated as a request to buy data.

For the current acceptance date:

```powershell
python -m research_platform construct "Nestlé S.A., NESN, SIX, Switzerland" --sources local_store/nestle --as-of 2026-10-23
```

The default is ten completed fiscal years and five forecast years. `--years` selects
specific completed history; `--fresh` deliberately starts new research under the
same company budget; `--resume RUN` selects a verified ancestor. A changed archive
or as-of date invokes coverage update. `--historical-vintage --as-of YYYY-MM-DD`
requires known publication dates no later than that date; current vendor exports
with unknown availability cannot be represented as point-in-time history.

Advanced `--model-inputs` supports exact reproduction of saved cited research.
`--reference-workbook` only records optional development-reference identity; it
supplies no numbers, formatting, prompts, cache key or resume eligibility.
Neither belongs in normal company production commands. Unknown/unsupported formats,
missing financial anchors, unreconciled facts, blocked official sites and inadequate
budgets stop with preserved incomplete work. The application does not guarantee
every company archive is sufficient for the current financial-role contract.

Historical-only `initiate` remains a separate local-source route with blank forecasts
and stricter historical acceptance. It has not completed accepted live history.
The production construction route uses actual Excel on Windows; lack of desktop
recalculation cannot be represented as verified Excel agreement.

## Review routing and budget

Configured Luna/medium is the default. `integrated_schedules` reviews working
capital/tax, assets/depreciation, financing and their statement links; Python and
Excel do the arithmetic. Explicit source definitions distinguish owned PPE, ROU
assets and any combined amount, with checks against subtracting leases twice.

Each review saves specific failures, repairs missing context or output contracts,
and makes a small configurable number of changed cheap-model attempts. Only a
persistent cited financial interpretation disagreement qualifies for escalation.
The stage generates its own evidence file and temporarily uses the supported premium
route if its allowance fits the same ledger. Missing originals, parser/provider
failures, unchanged feedback and software errors do not justify automatic premium
spending. Passing Luna work incurs no premium call. Routing tests are mocked;
the fair schedule retest above was an actual model call, not replayed success.

An optional `--escalation-evidence` remains for reproducing a deliberately pinned
advanced route; it is not a fresh-build prerequisite. Credentials and intentional
model settings remain in ignored `.env` or environment variables. No secrets were
printed. No stage-wide Sol pin was added or retained by this task.

Every request has a durable identity, conservative preflight allowance and recorded
usage/duration. Known usage replaces its reserve once; unresolved requests stay
reserved across builds, migration and refresh. There is no routine request-count
ceiling on the normal route. Repairs and transport retries remain bounded; no-progress
and unknown/unaffordable cost guards still stop work. The final in-flight request
can overshoot its estimate because usage arrives afterward. Old unrelated browser
research costs remain in their preserved historical records and are not erased.

## Saved demonstrations and unresolved results

The following outputs are ignored local artifacts. Preserve them and their linked
parents; none overwrites originals or an earlier result.

| Output | Verified result and limit |
|---|---|
| [Nestlé historical review workbook](outputs/review_saved_20261022T215257Z_65f93cfa/model.xlsx) | 72 rows, 292 populated historical cells and 32 live historical check cells; all 324 matched Python after Microsoft Excel recalculation. No company forecasts or completed independent source review. |
| [Synthetic executable financial model](outputs/construction_known_answers_20261022T215512Z/model.xlsx) | Price, volume and unit-cost assumptions drive revenue, costs and profit. All 19 tested cells (5 historical, 12 forecast, 2 historical check) matched Python after Excel recalculation. Explicitly synthetic. |
| [Synthetic pricing sensitivity](outputs/construction_known_answers_20261022T210450Z/model_price_sensitivity.xlsx) | First-year pricing 10% to 11% changes revenue 132 to 133.2 and profit 46.4 to 47.6; costs remain 75.6. All 12 forecast cells matched Excel. |
| [Synthetic planted historical error](outputs/construction_known_answers_20261022T215512Z/model_history_error.xlsx) | Changing historical profit from 30 to 31 exposes a live difference of 1 and FAIL against revenue 100 minus costs 60 minus marketing 10. All 19 expected cell values/check statuses matched Excel; the error is deliberately preserved. |
| [Scripted production-path workbook](outputs/construct_synthetic_manufacturing_group_20261022T213930Z_7c81f69d/model.xlsx) | All 13 workflow stages exercised with scripted provider replies; 11 historical/forecast cells matched Excel. It remains a partial synthetic sales model (9 PASS, 9 MISSING), not a complete three-statement model. No paid requests; simulated token/cost fields test guards only. |
| [First real construction trial](outputs/construct_nestl_s_a_nesn_six_switzerland_20261022T212214Z_e0df8f51/record.json) | All 14 calls use Luna, 13 priced and one unknown. Saved historical inputs are reviewable; this preserved trial stopped at its source-check timeout. Later integrated continuations are recorded above. |

The real 2024–2025 trial selected the VA export and twelve complete company PDFs.
It imported 584 source observations, including alternative sources, and selected
292 values across 72 historical rows. It did not reach live driver/formula stages.
The known subtotal is 9,800,723 tokens: 9,719,792 input and 80,931 output (including
30,787 reasoning tokens), with 21,820 reported cached input tokens. These are
reported totals for the thirteen priced calls, not an estimate of the lost call.

| Stage | Calls | Known estimated USD |
|---|---:|---:|
| Selection | 2 | 0.010514475 |
| Evidence-first coverage | 1 | 0.210722350 |
| Row mapping | 6 | 1.351124000 |
| Historical scope/relationships | 3 | 0.683689550 |
| Blind primary-source reconstruction | 2 (one unknown) | 0.219490850 plus unknown |
| Total | 14 (13 priced) | **2.475541225 plus unknown** |

The failed request took 129.8 seconds with a 120-second transport setting; its
client request ID is `2aaabb4a-ab48-4513-b0ea-1bea204fb9b4`. This was a technical
failure with no returned usage, not evidence of bad financial reasoning or zero
charge. The original $5 limit and all ancestor charges remain attached. No retry,
Sol escalation, fresh-budget workaround or paid known-answer evaluation followed.
Whole-document contexts remain expensive in tokens; measured cache reuse was
small. Ten-year affordability and optimal Luna effort are unresolved.

Manual spot checks found material issues requiring semantic review before the
historical draft can seed forecasts:

- The mapped `other_operating_assets_liabilities_change_cash_flow` says it is the
  reported change in other operating assets/liabilities, but its source is VA
  **Other operating cash flow**, `default!FD2103`: CHF 463m for 2025. The company
  financial statements, PDF page 10 (printed page 84), report CHF **(807)m** for
  the specifically named working-capital line: a CHF **1,270m** discrepancy against
  that interpretation. Other non-cash items may explain the broader vendor
  aggregate, but that bridge has not been accepted. Preserve both observations;
  do not force the aggregate into the narrower definition.
- Adding the displayed component segment-sales rows for 2025 gives CHF **96,041m**, versus
  group CHF **89,490m**. The CHF **6,551m** excess equals the NHS row. This indicates
  overlapping reporting definitions rather than mutually exclusive components.
  Verify period-specific identities/restatements before forming a group total.
- No supported segment-to-group or cash-flow reconciliation equation completed.
  Taxes and several financing/cash-flow components are absent from the core row
  mapping. Cash-flow ending cash and balance-sheet cash also require the disclosed
  held-for-sale bridge; a forced equality would be wrong. Driver exposures and
  company forecast assumptions remain ungenerated.

These spot checks are not a complete independent source review. The Excel check
only confirms links, scaling and calculation agreement with saved Python values.
The live known-answer benchmark helper in `tests/test_construction.py` is separate
from unittest discovery and would make paid calls; **it was not run** after the
unknown-charge stop. No measured Luna-versus-Sol/Haiku quality claim is available.

## Source folders

Use the existing Git-ignored location:

```text
local_store/nestle/
  visible_alpha/
  financial_reports/
  transcripts/
  sources.csv
```

Create categories when storing actual originals. No company originals were added;
synthetic test inputs live under ignored `outputs/` with explicit labels. Readable primary company evidence in
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

On 22 October, ordinary path enumeration exposed only 435 originals. The four
additional financial-report PDFs marked downloaded in `sources.csv` are present
and accessible using Windows extended-length paths. Ordinary path checks miss
them at this workspace location. Extended-path handling was implemented and all 439 files inventoried during
this construction work; this is not evidence that the originals were deleted.

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
and comparison; `construct` now saves consensus references separately and calculates its own temporary baseline.

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
number/completeness checks remain required. Those earlier parser measurements used
unchanged model settings; the 22 October construction policy now starts with Luna.

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

Historical-only role reasoning remains **medium / standard**; construction has the
stage defaults described above. Optional private settings:

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

The dated code price table (rechecked 22 October 2026), USD per million tokens:

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
Unknown charges block further historical-initiation spending. Integrated construction
instead retains conservative reservations under the 23 October authorization.
Historical `initiate` has no request/draft-count ceiling; construction uses the
bounded ceilings described above.
Interactive calls show live elapsed time and final duration; redirected logs use
readable completion lines. Stage and cumulative tokens/USD follow each call.

## Setup, files and verification

Use Python 3.11+ and the existing environment; install with
`python -m pip install -e .` when needed. Configure `OPENAI_API_KEY`,
and optional `RESEARCH_MODEL`, `EXTRACTION_MODEL`, `REVIEW_MODEL` in ignored `.env` or
environment variables. Environment values override local settings. Secrets never
enter prompts or run/code snapshots. Credential values were not printed or changed;
only the three private model-selection lines were migrated to Luna.

```powershell
.\.venv\Scripts\python.exe -m research_platform doctor
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`api-check` is a small paid connection/structured-output test, not a research audit.
Doctor/tests are offline. Current verification is recorded above; the following is preserved historical test evidence. The full suite passed **190 tests in 199.0 seconds**
on 22 October (165 historical and 25 construction). After final workbook and
unknown-charge hardening, the expanded **26 construction tests passed in 6.6 seconds**;
the historical modules were unchanged. Setup doctor also passed.
Construction cases cover independently known arithmetic, planted economic and
dependency errors, invalid units, missing versus zero, actual/estimate separation,
sensitivities, lags, workbook generation, offline recalculation, durable request
replay, source/artifact tampering and known/unknown-charge retry behaviour.
Historical coverage includes one/two/ten-year local histories,
interims, source integrity, estimated-value rejection, reporting changes, formulas,
isolated reviews, budget allowances and interrupted resume. Thirteen vendor tests
cover company-section eligibility, interleaved consensus columns, fiscal periods,
original numeric references, context retention and primary-only blind reviews.
The actual VA workbook's historical projection was checked locally; these tests
do not validate its financial mappings or complete a live initiation. The older
historical importer work made no paid run; construction live trials are separately
recorded in the dated decisions and saved outputs.

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
| `src/research_platform/construction.py` | Original construction workflow, shared financial expressions, source contracts and desktop Excel verification |
| `src/research_platform/integrated.py` | Company specification compiler, integrated statements, period schedules and successor research context |
| `src/research_platform/periods.py` | Fiscal calendars, typed observation derivations, compatible bases and the shared period calculation graph |
| `src/research_platform/fx.py` | Source-format adapter, daily cross rates, spot-held projections and configured company baskets |
| `src/research_platform/fx_store.py`, `src/research_platform/ibkr.py` | Shared SQLite evidence/snapshots and optional read-only TWS ingestion |
| `src/research_platform/model_excel.py` | Assumptions-led workbook renderer, live Excel sensitivities and temporary-copy visual exports |
| `src/research_platform/workflow.py` | Dated official discovery, fresh-company research inputs, disclosure reconciliation and zero-AI refresh/export |
| `src/research_platform/budget.py` | One cumulative cost ledger, durable requests and unresolved reservations |
| `src/research_platform/evidence.py` | Local inventory, unchanged originals, parsing, search/read and numeric references |
| `src/research_platform/ai.py` | Private settings, provider, reasoning, stable context, tokens/prices and allowance |
| `src/research_platform/__main__.py` | CLI commands and live timer |
| `src/research_platform/project.py`, `__init__.py` | Project discovery, saved JSON and package identity |
| `tests/test_setup.py` | Offline synthetic financial/provider/parser/workflow checks |
| `tests/test_construction.py` | Known-answer construction, economic-error, workbook and cost/resume cases |
| `tests/test_integrated_model.py`, `tests/test_integrated_graph.py`, `tests/test_model_sources.py` | Financial controls, exact source normalization, graph and saved-result integrity |
| `tests/test_periods.py`, `tests/test_periodic_model.py`, `tests/test_fx.py`, `tests/test_model_excel.py`, `tests/test_budget.py` | Different-company fixtures, period/FX semantics, workbook authority and cost recovery |
| `README.md`, `PROJECT_BRIEF.txt`, `AGENTS.md` | Current operation, wider ambition and standing instructions |
| `pyproject.toml`, `.gitignore` | Dependencies and exclusions |
| `local_store/<company>/` | User originals, Git-ignored; no automatic AI upload |
| `outputs/initiate_<company>_<time>_<id>/` | Frozen record, copied sources, calls and accepted workbook |

Historical `initiate` runs contain `record.json`, `calls.jsonl`, `sources/` and, only on acceptance,
`model.xlsx`. An interrupted `model.pending.xlsx` is not accepted. Preserve
ancestor folders and back up ignored research separately. A hash is provenance,
not a tamper-proof forecast ledger. Python environments/caches/build metadata are
generated support. `.git/COMMIT_EDITMSG` is Git scratch space. Old FX/demo/config
code stays removed; preserved synthetic outputs and the first Nestlé annual
reference are historical artifacts, not current inputs.

## Next milestone

Complete material portfolio closing bridges and obtain verified functional/invoice
currency, hedge and foreign-asset exposures before promoting the Nestlé baseline.
Replace provisional activity, spending, opening-share, lease and flat-balance policies
with source-backed inputs while keeping the causal equations and driver contracts stable.

Resolve unattended official-site access and validate fresh archive-to-model construction
on a second real operating company. Preserve the synthetic calendar/reorganisation
coverage, but measure real source accuracy, omissions and cumulative cost before
claiming autonomous ten-year onboarding or quoting a new-company build price.
Defensible uncertainty, forecast records and empirical evaluation should precede
DCF; later statistical/qualitative forecasting agents remain outside this step.

## Decisions

| Date | Status | Decision |
|---|---|---|
| 24 October 2026 | Implemented; company economic completeness limited | Causal functional costs replace forecast residual allocations; regional scope, separate transaction/translation/OCI FX, timed shares, annual dividend pools and recurring normalisation have explicit contracts and independent tests. Direct annual forecasts follow the configured detailed horizon; 9M is absent from Model/Assumptions. Factory and substitute-currency proxies are removed. Material closing-accounting and exposure gaps remain explicit; arithmetic acceptance is separate from financial completeness. All 389 offline tests pass, with 131,703 real Excel cell comparisons and seven sensitivities. Final visual review corrected annual sales/cost carry-forward, held-for-sale D&A, scope working-capital double-counting and payout-ratio aggregation. Zero new application AI spend. |
| 24 October 2026 | Implemented; exposure estimates provisional | Shared SQLite FX history, read-only IBKR updates, daily-cross spot-held forecasts, separate revenue/cost baskets and editable 1.0 calibration. Nestlé statements use supported half-year cadence; stocks use H1/FY, 9M is internal and FY is shaded. Separated company-reported VA roles replace positional selection. Routine operations are zero-AI; the cumulative ledger and unresolved reservations remain intact. |
| 24 October 2026 | Implemented; live access limitation explicit | Native compact workbook, per-cell actual precedence, dated release coverage, zero-AI FX refresh/export and fresh-company input generation replace the reproduction-only workflow. Q3/9M Nestlé source numbers reconciled independently; synthetic GBP half-year/reorganisation fresh generation passes. Direct official-index access is blocked by HTTP 403; browser-assisted verification supports this delivery, not an unattended discovery claim. |
| 24 October 2026 | Implemented and live retested | Fair Luna schedule review passes with identical repaired evidence plus explicit PPE/ROU identities. Bounded targeted repairs precede automatic stage-local escalation. No permanent schedule Sol pin or user-authored escalation file is required. The earlier unnecessary Sol context escalation and its cost remain recorded. |
| 23 October 2026 | Fresh-build limitation clarified; correction proposed | The displayed command reproduces the completed Nestlé run. Default Luna builds require no escalation file; a newly dispatched non-Luna stage currently requires supplied evidence. Automatic run-derived justification/model escalation is not implemented. The user's reuse concern exposes an orchestration gap; the proposed fix is to generate the record from the new build's own failures and repairs, not reuse Nestlé's file or require a user-authored justification. No runtime change or paid build was requested in this discussion. |
| 23 October 2026 | Implemented; final delivery verified | Assumptions is authoritative. Shared typed periods preserve actuals, live historical derivations, quarterly forecasts and coherent half-year/FY views. Current and legacy segments retain numerical bridges and successor context. All 310 offline tests, desktop Excel baseline/sensitivities and 48 visual views pass with stated support-page sampling limits. The different-company GBP fiscal-calendar/reorganisation fixture uses the same entry point and real synthetic originals; its provider/desktop bridges are mocked. No second real-company validation is claimed. |
| 23 October 2026 | Implemented with explicit provisional policy | Import the supplied shared FX workbook by currency code and dates; preserve estimate labels and missing coverage. H2/FY 2026 uses a disclosed provisional Q4 weekday calendar without holiday exclusions. Future average/closing rates and company exposure interfaces remain separate. No inferred exposures or retranslating reported CHF history. |
| 23 October 2026 | Verified recovery; prior integrity issue preserved | Annual run 175451's workbook hash changed after its recorded completion. Explicitly select verified ancestor 174746; retain the excluded file/record and every later charge/reservation. All five review requests match exactly, so this follow-up incurs no new calls. Default reuse still rejects damaged latest artifacts. |
| 23 October 2026 | Implemented and verified on actual Nestlé workbook | Six segment builds drive the integrated model; ten annual years, reported interims and original segment versions are retained. Bunzl supplies architecture and formatting only. Source controls, independent calculations, live Excel sensitivities and visual inspection pass. Temporary assumptions are executable model inputs, not validated forecasts. |
| 23 October 2026 | Implemented and verified offline/live | One company-attempt ledger preserves known charges and conservative unresolved reserves across migrations. The old timeout reserves $0.893530750; it no longer blocks all progress when total commitments fit $20. Per-request limits/retries remain bounded; provider retrieval requires a real response ID. |
| 23 October 2026 | Implemented | Targeted original sections, cached indexes and coherent review tasks supersede whole-report/blind-first construction gating. Preserve original evidence and disagreements. A 6,000-token statement review exhausted reasoning output; split statements and use a bounded 12,000-token ceiling. Complete formula graph context prevents false missing-dependency/circularity findings. |
| 23 October 2026 | Source-backed decisions | Forecast on the March 2026 restated segment basis; NHS is included in the zones. Preserve older original segment versions separately. Use original annual statement vintages, explicit cash-scope bridges, complete historical cash-flow components, and separately sourced P&L current/deferred tax. No synthetic decade on current geography. |
| 23 October 2026 | Verified construction and reuse | Preserve signed historical derivations and explicit assumption initialization equations. Cash payments use the current P&L tax settlement ratio. Sol medium reviewed schedules after documented Luna scope failures; other reviews remain Luna. Default pricing metadata now round-trips through JSON, and accepted CLI reuse works with an empty API key without new spending. |
| 22 October 2026 | Paid work blocked; real milestone incomplete | Thirteen priced Luna calls cost $2.475541225; a fourteenth timed out at 129.8s with unknown usage/charge. Stop all further paid evaluation, retain the original $5 lineage, and do not infer zero charge. Historical draft exported unpaid; real driver/formula stages and live known-answer evaluation did not complete. |
| 22 October 2026 | Observed financial gaps | The draft mislabels a broader CHF 463m vendor cash-flow aggregate as the specific CHF (807)m company line; displayed segment sales overlap by CHF 6,551m. Preserve source facts and flag missing cash-flow/segment bridges. Excel agreement does not cure these semantic issues. |
| 22 October 2026 | Observed live failures; cheaper input fixes implemented | First mapping and later blind reconstruction hit 16,000 output tokens. Split reporting scope, statement mappings, relationships and blind concept groups without truncating selected documents. Project requested years explicitly while retaining raw comparatives. Constrain vendor row IDs to catalogue members. These fixes were tried on the preserved lineage before the final timeout; no Sol escalation. |
| 22 October 2026 | Recovery hardened and verified offline | Deep-copy exact request/results so later mutations cannot alter checkpoints. A verified durable journal can recover a request-shadow-only mismatch; every usage/response field must agree and request signatures must validate. This does not recover lost provider responses. Add hashed intermediate filenames, source-byte checks, code snapshots and bounded local Windows rename retries. |
| 22 October 2026 | Unpaid review and synthetic pipeline verified | `review-saved` exports/recalculates existing work without credentials or paid calls. Real draft: 292 historical cells and 32 live historical check cells match Excel. Synthetic baseline and planted historical discrepancy: 19 cells/statuses each match Excel. Scripted full workflow: all 13 stages exercised and 11 populated cells match Excel; synthetic incomplete model, not live company success. |
| 22 October 2026 | Unknown-charge guard hardened | Fresh research or a changed year selection cannot bypass the latest unresolved charge for the same company query. An offline regression confirms no request is dispatched. Lost-response recovery remains unimplemented. |
| 22 October 2026 | Excel calculation verified on synthetic known answers | Microsoft Excel COM recalculated the baseline and a pricing-input sensitivity; all 12 forecast cells matched Python in each workbook. Pricing growth 10% to 11% moves first-year revenue 132 to 133.2 and profit 46.4 to 47.6, leaving costs 75.6 unchanged. This is mechanical validation, not company accuracy. |
| 22 October 2026 | Confirmed user scope; mechanics implemented, live evaluation incomplete | Advance construction from blank forecasts to supported history, company drivers, explicit formulas, temporary annual assumptions, executable Python/Excel and four-area validation. Preserve strict initiation and label partial construction outputs provisional. No driver forecasting models, distributions or DCF. |
| 22 October 2026 | Confirmed model policy | Migrate active role defaults/private Sol selections to Luna, centralize stage settings and record bounded precise repairs. An expensive construction route needs documented lower-cost failures; no automatic Sol fallback. OpenAI-only first implementation is acceptable. |
| 22 October 2026 | Verified offline | Repaired editable install and Windows long paths; all 439 originals inventory correctly. The full 190-test suite passed; after final hardening all 26 construction tests pass (191 distinct tests including the 165 unchanged historical regressions). One cohesive construction module and focused test file were needed; no new maintained documentation or services. |
| 22 October 2026 | Status verified; validation still pending | Reviewed the workspace and saved runs for the progress recap. The existing two-year live validation milestone remains next, preceded by the installation and Windows path checks recorded above. No implementation/model changes, paid calls or full test rerun; retain the 11 October test result as historical verification. |
| 10 October 2026 | Confirmed | Nestlé first; Python calculates, Excel supports inspection. Preserve the wider research cycle and keep these three documents current. |
| 10 October 2026 | Superseded for construction on 22 October | Historical scope was history plus blank forecasts. Temporary assumptions and executable forecasts are now authorized for construction; distributions and DCF remain deferred. |
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
| 10 October 2026 | Superseded by 22 October Luna policy | Earlier instruction kept Sol for every role pending evidence. The latest user request explicitly starts construction with Luna and evaluates failures before escalation. |
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
