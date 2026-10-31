# Refractive Systems — reusable model construction

Build a financial model from a **local company source archive**, with traceable
historics, company drivers, temporary assumptions, period-based forecasts and
a portable Excel workbook. Historical-only `initiate` retains its stricter
acceptance gates and blank forecasts.
The default is fiscal 2018 through the latest evidenced completed fiscal year, plus reported interims.
Nestlé is the first proving case, not a company-specific Python model.

[PROJECT_BRIEF.txt](PROJECT_BRIEF.txt) holds the wider research cycle;
[AGENTS.md](AGENTS.md) holds standing instructions. This README owns current
operation, verification, next steps and dated decisions. These remain the only
maintained project documents.

## Current state - 31 October 2026

**Simplified VA historical construction implemented; user-operated validation next.**
`construct-history` now follows inventory/hashes and numeric preflight -> VA-led
company scope -> native-row/version mapping -> Python source/period/arithmetic
checks -> one combined-history AI review -> historical JSON and Excel. It stops
there. History no longer requires bulk PDF/restatement loading, early core-review
loops, forecast drivers, owned-PPE/ROU schedules, FX exposures or prospective policy
research. These forward-model questions begin inside forecast construction, after
a completed historical checkpoint, using the same build allowance.

Company-reported VA supplies all historical numbers, including revised values.
Local originals are consulted only for concrete unresolved calendar, definition or
reporting-change questions, retaining the relevant complete statement and notes.
Revenue coverage accepts compatible `sales` and `total_revenue` bindings. Native
company rows retain their source labels without forced common-role interpretations
or calibration eligibility. The workbook includes a `VA Source` sheet containing
all eligible imported actuals, including unresolved mappings. Bounded mapping
repairs retain valid work; material unresolved issues still yield an incomplete
checkpoint. Existing old/new reporting blocks and same-definition revision
selection remain in use; source and fiscal-period checks are unchanged.

Resolver citations and repair schemas are compact; Python checks membership,
digests and permitted paths. Provider schema size limits are checked before any
reservation or dispatch. Contracts are `va_semantic_mapping_v7` and
`combined_history_v20`; incompatible previous research is preserved, not silently
resumed. Fresh default runs, explicit-only resume, $20 allowances, durable unknown
reservations and automatic logs remain unchanged. No source modules or additional
configuration directories were added. Strict historical `initiate` is unchanged.

No paid calls or company builds were run for this implementation. Offline fixtures
and saved-request replays do not establish real-company completion, and the moved
forecast-preparation route has not undergone a new live full-model build.

Verification: **229 focused tests ran in 65.536 seconds: 227 passed, two skipped,
zero failures/errors and zero external network attempts.** The skips concern older
archives removed during cleanup. Fresh end-to-end synthetic generation covers
quarterly USD and half-year JPY/March reporting with a reorganisation, no bulk PDF
or forecast calls, one final review and completed/incomplete Excel checkpoints.
Saved-request checks cover the latest L'Oreal revenue failure and full-size Nestle
schema; targeted-context checks retain all selected statements and notes. Budget,
source-number, restatement and package-boundary regressions pass. Doctor, CLI help,
compilation and whitespace checks pass; the three retained v6 runs and frozen
source hashes verify. Receipt:
`outputs/va_native_history_v7_release_20261031T184327Z.log`.

**Latest 17:54 UTC v6 trials diagnosed: genuine workflow regressions.**
The user reiterates that the objective is unchanged: read supplied company-reported
VA and build the historical model. Inspected all three new logs, scope/mapping/
resolver requests and responses, saved observations, workbook contents, code
identities and ledgers. All saved code identities matched the then-current engine and all
registered artifacts verify. No engine changes, paid calls or company builds were
made during this diagnosis. Official OpenAI documentation was consulted only to
check the rejected response schema's documented limits.

| Company | Wall time | Calls | Recorded USD estimate | Retained facts / outcome |
|---|---:|---:|---:|---|
| Nestle | 3m49.759s | 6 (one rejected) | 0.315345475 known | 120 facts, zero completed cohorts; HTTP 400 in evidence resolution |
| L'Oreal | 3m31.840s | 6 | 0.036944775 | 809 facts, first cohort completed; false missing-Sales evidence stop |
| Danone | 2m52.937s | 5 | 0.028700225 | 328 facts, first cohort incomplete; Net income attribution evidence stop |

Total 17 dispatches, **$0.380990475 recorded known estimate**, plus an unresolved
**$0.588573750 reservation** for Nestle's rejected call. The reservation is not a
confirmed charge and remains preserved. Sixteen entries settle as incurred
estimates. All three numeric preflights pass; budgets are not exhausted. All three
export `historical_model_incomplete.xlsx`, with saved read-back/layout checks passed
and 480 / 608 / 118 Model formulas respectively. No early semantic review, final
accounting/history review or downstream stage completes. Shorter runs are earlier
stops. Relative to v5, retained facts change from 467/801/269 to 120/809/328, so the
latest failures include both genuine regressions and progress blocked by new gates.

Latest folders: `outputs/construct_research_20261031T175450Z_8d1bd543` (Nestle),
`outputs/construct_research_20261031T175450Z_beebdd62` (L'Oreal), and
`outputs/construct_research_20261031T175454Z_4af7dc33` (Danone).

Nestle exposes an overbroad v6 correction: `_identity_source_selection` forces all
36 filename/title matches into scope, including old restatement spreadsheets and
numeric appendices. Complete matched originals then bypass section selection and
follow every mapping/resolver task. Its first mapping input grows from 43,410 to
347,990 tokens; scope uses 404,474 tokens. The resolver's saved response schema has
5,622 object properties and 5,607 enum entries for 2,794 citation pairs. This exceeds
the documented 5,000-property and 1,000-enum limits in the
[official Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).
The provider returns HTTP 400; the saved response lacks its specific validation
message/code, so the exact server-reported cause cannot be recovered. The schema
violation is independently reproducible. Numeric inputs still come from VA, but
the AI context now unnecessarily includes bulk numerical restatement originals.

L'Oreal successfully maps all 19 first-cohort targets. Its Net sales row has every
annual value for 2018-2025, source-checked and displayable, under role `total_revenue`.
`_va_coverage_gaps` demands the exact role `sales`, generating eight apparent gaps.
An in-memory role-only diagnostic removes all eight without changing any values;
no saved mapping or financial interpretation was altered. Instead of attempting
the role correction, the mandatory resolver receives headers and only two recent
value examples, without the existing annual mapped facts/candidate, and concludes
that old annual monetary support is absent from the PDFs. Its unresolved verdict
terminates the build before a mapping repair. The extra scope repair also concerns
a financing/tax driver citation, illustrating unnecessary forecasting preparation
on the historical command's critical path.

Danone's reorganisation note is now selected, and 19 decisions/328 facts are retained
(versus six/269 in v5). The blocking Net income row has a clear fiscal basis but an
unresolved Group-versus-parent attribution. Its VA H1-2026 figure is 1,235. The
already-selected 2026 interim report's PDF page 16 reports NET INCOME 1,235, Group
share 1,175 and NCI 60. The resolver receives only 11 of the scope's 44 original
sections, excluding that primary income-statement page and its cash-flow context.
It sees recurring-income definitions instead and stops the entire mapping attempt.
The question is legitimate; the missing-context diagnosis is caused by application
filtering, not an absent upload. Several other row findings remain repairable but
are never patched because this resolver exception aborts first.

Diagnosis: the numerical parser is working, but construction is coupled to an
increasing number of context, canonical-role, scope and proof gates before the
whole historical dataset is assembled. Recent edits introduce bulk context/schema
growth and route internal role/contract errors to financial-evidence research.
Earlier higher cohort counts also included unusable mappings, so they were not
successful company models. The 222 offline checks did not exercise a full-size
Nestle note catalogue/provider schema or the exact new false-coverage/context
interactions. Passing component/mocked tests did not establish end-to-end reliability.

Recommended direction (proposal, not implementation approval): simplify the VA
historical path around deterministic source import, one coherent company-native
mapping/layout, arithmetic/source checks and Excel export. Keep cited company
structure and material definition checks, while separating forecasting driver
research and independent PDF support from primary VA numerical construction.
Treat role mismatches as mapping repairs, retrieve only needed complete local
sections for actual definition gaps, use a compact citation schema with Python
membership validation, and preserve native facts/partial progress when an optional
interpretation remains unresolved. Test the complete saved interactions and request
sizes before further paid trials. Do not merely add retries, models or more gates,
or waive genuinely material financial ambiguities.

**Approved latest-run reliability fixes implemented (v6).**
The user clarified that VA already holds the restated figures. The numerical reader
already used eligible company-reported VA cells; the revised scope, mapping and
resolver instructions explicitly keep original/revised amounts there. PDFs supply
definitions, affected entities and comparative dates. No restated table is
reconstructed from a PDF and no numerical bridge is required merely to establish
an explicitly disclosed comparative presentation.

Python now derives canonical IDs from the AI-selected financial role/entity, and
response schemas constrain duplicates to physical source-row keys and dates to
full ISO dates or null. Accounting aggregation types remain validated. Existing
valid versions stay in Python; repairs append missing versions or replace an exact
failed version without copying the others. Local catalogue hints route relevant
reporting-change originals to content inspection and keep their complete text in
scope evidence. A bounded resolver can correct cited scope applicability dates,
preserving established entity identities and hierarchy compositions. It handles
pending financial findings and newly arising evidence questions after a patch.
The shared runtime remains representation-independent.

An unresolved alternate series can remain outside active selection only when
source-checked coverage exists for the essential concept and periods. Its raw VA
cells, reasons and alternative observation IDs are retained in
`va_unresolved_series.json`, included with historical exports and shown as workbook
warnings. Early semantic and final history reviews inspect them; genuine missing
essential coverage, material conflicts and unresolved definitions of explicitly
restated series remain blocked. The review fingerprint binds these audit decisions. The early review now
explicitly challenges before/after adjustment definitions using the selected VA
values and supplied statement context. Repeated missing legacy entities have stable
display placeholders, fixing the v5 diagnostic-export crash.

All changes reuse existing historical/shared modules. The mapping/review versions
are `va_semantic_mapping_v6` / `combined_history_v19`; old incompatible research is
preserved but cannot silently resume. The user launches fresh historical-only
trials. No paid provider calls, company builds or downstream handoffs were made.
Offline source replay and synthetic acceptance remain distinct from real-company
completion; the latter is still unverified.

Verification: **222 focused tests ran in 41.863 seconds: 220 passed, two skipped,
zero failures/errors and zero external network attempts.** The skips concern older
archives removed during the authorized cleanup. New checks replay the latest
Nestle export failure, the omitted Danone note selection and L'Oreal alternate-series
handling. A synthetic note deliberately contains a conflicting number; all resulting
financial observations still cite VA and use its amounts. Tests cover cited scope-date
correction, append-only repairs, pending/later evidence triggers, essential-gap
blocking and a fresh alternate-series case through early/final review, provisional
historical finalization and Excel/audit export. Quarterly USD and half-year
JPY/March-year-end fixtures continue through the same compiler and exports.
`doctor`, historical CLI help, compilation and whitespace checks passed. All
registered artifacts and frozen VA hashes in the latest three real runs were
verified unchanged. Receipt:
`outputs/va_reliability_v6_release_20261031T175145Z.log`.
This verifies the targeted historical/shared suite, not every repository test,
desktop Excel recalculation or autonomous completion for a real company.

**Preserved 17:17 UTC v5 diagnosis: no completed historical model.**
Read all three logs, saved scope/mapping/resolver replies, validation and rejected
patch records, progress inputs, real workbook cells and durable allowance entries.
Each run's saved Python identity matches the current code. All registered artifact
hashes and frozen VA copies match. This is diagnosis only: no engine changes,
provider calls, company builds or new offline-suite completion claims.

| Company | Wall time | Luna calls | Recorded USD estimate | Retained progress / output |
|---|---:|---:|---:|---|
| Nestle | 10m16.338s | 11 | 0.104323275 | Cohort 1/18 completed, cohort 2 blocked; 21 valid row decisions / 467 observations; draft Excel export crashes |
| L'Oreal | 6m11.732s | 7 | 0.070239400 | Cohort 1/10 blocked; 18 valid decisions / 801 observations; populated incomplete Excel |
| Danone | 7m34.737s | 7 | 0.064883365 | Cohort 1/13 blocked; 6 valid decisions / 269 observations; populated incomplete Excel |

Total **25 calls / $0.239446040 recorded estimate**. All 25 requests reconcile to
settled incurred-estimate ledger entries; no missing usage, pending requests or
unknown reservations. Each fresh run had a $20 allowance, with over $19.89 remaining.
Calls used Luna (low for selection, medium for financial tasks), with zero web
searches. AI-call durations sum to 592.142 / 347.654 / 419.340 seconds respectively;
the remaining wall time is local parsing, checks, persistence and export. Numeric
preflight passed on all 59,261 cells. The observed runtime reductions/increases are
not completion benchmarks. None reached early core semantic review, accounting
review, final combined-history review, historical finalization or forecast/DCF.

Runs: `outputs/construct_research_20261031T171719Z_7ec712c2` (Nestle),
`outputs/construct_research_20261031T171721Z_591489d0` (L'Oreal), and
`outputs/construct_research_20261031T171726Z_e9169866` (Danone).
The latter two contain `historical_model_incomplete.xlsx`, with respectively
600 / 218 Model formulas and 801 / 269 numeric Historics observations. Registered
serialization/layout validation passed; source acceptance and desktop Excel
recalculation were not performed. Nestle has saved progress JSON but no workbook.
Its live VA original now differs from the frozen run copy, with a modification
timestamp of 17:28:03 UTC, after this run ended; this is not evidence of the cause
of its failure. The frozen copy preserves the numbers actually used.

Nestle's resolver citation fix worked and its first cohort finished with 347 facts.
The second cohort adds 120 retained facts but fails canonical model IDs, duplicate
references and historical version coverage. Mapping uses `group_sales` instead of
`sales`; duplicates cite financial IDs instead of physical `row_...` keys. Rejected
whole-row patches remove frozen valid versions, so otherwise useful changes cannot
apply. Its diagnostic export then raises `KeyError` at model_contract.py's reporting
block alias lookup: a missing legacy sales placeholder occurs in multiple historical
hierarchies but is absent from the precomputed display-ID map. This is a regression
in the new block renderer, reproduced directly from the saved inputs without AI.

L'Oreal corrected a year-only `change_date` rejected by ISO date validation, and the
final scope has unbounded current divisions as intended. The extra scope call took
86.838 seconds / $0.016906700. Mapping repairs reduce four findings to one: a second
annual series labelled Operating profit (2025 VA value 8,639.25) has an unresolved
definition. It is repeatedly required to become source-defined because its label is
classified as essential, even though another series was bound. No evidence resolver
ran: the initial pending-row finding has only `$` as its permitted path, while the
resolver detects evidence gaps from field-path names and is called only before the
first patch. An additional semantic error is visible in the retained binding:
8,386.5 is labelled profit before other income/expenses, whereas the supplied 2025
report (PDF page 292, printed page 290) calls 8,386.5 Operational profit after those
items and reports Operating profit of 8,891.9. Balanced/parsed values and a saved
workbook do not resolve these definitions; the final review was never reached.

Danone's inventory includes `financial_reports/2026_reorganisation.pdf`, whose
page 1 explicitly presents restated 2024/2025 indicators under the new zones and
states the operational start of January 2026. Its bytes still match the run inventory.
However selection retained the VA workbook, 2025 URD and 2025 results only; the
reorganisation note was never registered or supplied to scope/mapping/resolution.
The resolver consequently concludes that prior-period new-zone evidence is absent.
Later repairs can widen mapping dates but cannot repair the incorrect scope-level
entity dates. Eleven date findings and seven duplicate-reference findings remain.
The two group structures export with visibly missing constituent totals. One patch
also changed frozen versions and was rejected. These are not missing user uploads.

Proposed next steps (not implemented): deterministic constrained source/model IDs
and ISO date fields; targeted retrieval of relevant local reporting-change notes and
repairable cited scope context; field/append-only version repairs with Python carrying
valid versions forward; concept-level essential coverage plus a targeted semantic
check/resolver for conflicting series, including initial pending findings; and safe
placeholder alias construction for incomplete historical exports. Remove the scope
prompt's contradictory nonoverlap/overlap instructions. Replay these exact new
failures before another paid trial; do not widen retries, hardcode company dates,
force unknown definitions to pass or omit requested history. Smaller mapping inputs
worked (43,410 / 39,414 / 39,615 first-mapping input tokens, versus the preceding
127,095 / 100,145 / 126,504); additional generic Luna calls are not the first fix.

**Approved restatement policy and latest-run fixes implemented (v5).**
The historical compiler now distinguishes two cases. A reporting redefinition
retains separate current and legacy entity identities, presents all current regions
above all historical regions, and generates a separate constituent-linked group
sales total for each structure. Other monetary flow aggregates are explicitly
labelled segment totals because undisclosed corporate adjustments cannot be assumed
zero. A segment unchanged across structures has linked presentation rows backed by
one source observation. Missing disclosed components stay blank and prevent an
unsupported group sum. Current segment sales are checked against separately sourced
group sales using the disclosed numeric rounding, without a balancing adjustment.

A numerical revision with the same financial definition and entity uses the latest
unambiguous cited revised amount in the model. Superseded originals remain in the
saved observations and Historics audit sheet, excluded from active selection and
calibration. Changed definitions are kept separate; equal-vintage conflicting
revisions remain unresolved. Selection is shared by the backend annual bindings,
historical projection and progress checkpoints.

The latest live failures below also have targeted corrections in existing modules:
resolver questions have exact finding IDs and a citation manifest covering the
supplied rows, headers and selected original sections; operational change dates,
comparative applicability and source publication vintage are separate; document
coverage cannot become an unsupported entity birth/death date; failed mappings can
replace their version set while retaining unaffected validated versions; row digests
and permitted paths are constrained in the response schema. Shared period metadata
is deduplicated and semantic tasks receive complete selected section text once,
while numeric indexes remain in the source store. Resolver replies carry conclusions
instead of copying original sections into subsequent repairs. Typed financial roles
are required for canonical segment bindings as well as group/corporate bindings.

The mapping contract is `va_semantic_mapping_v5` and the historical review gate is
`combined_history_v18`; incompatible earlier mappings cannot silently resume. There
are no new source modules, company mappings, extra retry loops or additional routine
AI stages. Company structures, currencies, fiscal calendars and dates remain run
inputs. The standard commands below still start fresh historical-only runs with a
new $20 allowance and fiscal 2018 coverage. The existing real runs and costs are
preserved. No paid calls, company builds or forecast/DCF handoffs were launched.

Verification: **210 focused tests ran in 42.327 seconds: 208 passed, two skipped,
zero failures/errors and zero external network attempts.** The two skips concern
older archives removed during the authorized cleanup. Latest saved Nestle resolver
citations, L'Oreal scope dates and all three real mapping payloads were exercised
offline. Each captured mapping payload is under 70% of its prior serialized size;
this measures context bytes, not live token savings or provider latency. Fresh
quarterly USD and half-year JPY/March-year-end fixtures exercise the same historical
compiler, review/finalization and Excel export. Tests cover same-definition revised
numbers, overlapping restated comparatives, shared unchanged segments, distinct
group formulas and an in-memory sensitivity showing that a new-region change leaves
the old group's total unchanged. The changed input is restored and not saved.
`doctor`, historical CLI help, compilation and whitespace checks passed. The latest
three real workbooks, progress snapshots, original VA files and frozen VA copies
still match their saved hashes. Receipt:
`outputs/va_restatement_v5_release_20261031T171315Z.log`.
This is targeted offline verification, not the full repository suite, desktop Excel
recalculation or a completed autonomous build of another real company. Real-company
historical completion remains unverified until the user's next trials.

**Preserved 16:12 UTC v4 diagnosis: all stopped in their first mapping cohort.**
Reviewed the four new logs (including one mistyped L'Oreal source path), saved
responses/patches, actual workbook cells, registered hashes and request ledgers.
The code matches each run's saved code identity. Diagnosis made no engine changes,
provider calls or company reruns. The user subsequently approved the corrections
and restatement policy implemented above.

| Company | Wall time | Calls | Recorded USD estimate | Retained progress |
|---|---:|---:|---:|---|
| Nestle | 5m45.053s | 7 | 0.063362490 | First cohort of 18; 12 excluded-row decisions, zero source observations; skeleton workbook |
| L'Oreal | 3m44.524s | 7 | 0.110916685 | First cohort of 19; 15 decisions, 569 backend observations; partial workbook |
| Danone | 6m49.344s | 8 | 0.309533045 | First cohort of 24; 21 decisions, 412 backend observations; partial workbook |

Total **22 calls / $0.483812220 recorded estimate**, reconciled to settled
incurred-estimate ledger entries, with no missing usage or unresolved reservations.
Each fresh build had a $20 allowance; none exhausted it. Source/section selection
used low effort; financial tasks used medium; all calls used Luna and made zero
web searches. All numeric preflights passed (59,261 cells). The additional L'Oreal
invocation used `data_store/company_data/loreal#`, failed in 0.106 seconds before
AI/run creation, and incurred no API usage. The table describes its corrected run.

New run folders: `outputs/construct_research_20261031T161220Z_f9c12a41`,
`outputs/construct_research_20261031T161225Z_4bcf13ae`, and
`outputs/construct_research_20261031T161230Z_a3298f59`. Each has a registered
`historical_model_incomplete.xlsx` and matching validation JSON. Export read-back
and layout checks passed; Model formulas number 0 / 308 / 361, and numeric Historics
cells 0 / 563 / 412. Nestle's file is only a diagnostic skeleton. L'Oreal's backend
retains 569 facts while its historical projection contains 563 numeric observations.
No cohort, early core semantic review, accounting review, final historical review
or historical finalization completed. There was no forecast/DCF handoff or desktop
Excel recalculation. Shorter durations reflect earlier failure, not successful
construction becoming faster.

Nestle initially omitted 2018-2024 from six segment-series definitions. Its new
resolver then returned 18 conclusions for six queried rows on each of three
attempts. Each response cited 18 VA source rows explicitly present in the input.
However `_va_resolve_evidence` validates citations only against supporting sections
and headers, excluding those supplied row references. Its generic feedback never
names the rejected references. The three resolver calls consumed 186.311 seconds
and $0.026694790 without dispatching a mapping patch. This is a new contract defect,
not evidence that the supplied VA rows cannot be read. Fixing it alone would not
resolve the omitted historical definitions.

L'Oreal's scope explicitly says no division reorganisation is established by the
selected extracts, but records current divisions with effective bounds of 2025 to
2026 (the observed-document interval). These become hard validity dates in `_va_assess`.
Widening mapping dates to retain 2018-2024 then fails the entity-version date gate.
The permitted fields cannot append or replace a definition-version set, although
the error instructs the model to split it. The first patch increased retained facts
from 244 to 569, but four division rows remained blocked. The final patch was
atomically rejected for one incorrect expected digest; valid saved work was retained.

Danone corrected one scope-stage citation in a second call and its first mapping
patch resolved seven row dispositions. Three regional sales rows remained blocked.
The supplied `financial_reports/2026_reorganisation.pdf`, page 1, explicitly says
the new geography operated from January 2026 and presents restated 2024/2025
comparatives. The schema/gate conflates operational effective dates, applicability
of a restated reporting basis and the interval evidenced by a document. Consequently
valid historical comparatives can be rejected for preceding the operational change.
The repair contract cannot add the needed version structure; narrowing its one
version instead drops earlier periods. The second patch made no change and was rejected.

Context growth is material: first mapping inputs were 127,095 / 100,145 / 126,504
tokens, with shared period catalogues of 802 / 508 / 717 entries (including repeated
source metadata and boilerplate). The resolver returns full original sections and
headers again, which are copied into patch requests alongside the existing context.
Danone's patch prompts totalled 720,892 input tokens; both exceeded the saved pricing
calculator's 272,000-token long-context threshold. They cost $0.187544200 and took
95.798 seconds. No downstream acceptance was obtained from these extra calls.

Proposed next corrections: one citation manifest matching all shown evidence and
specific invalid-reference feedback; separate evidence-coverage dates, operational
change dates, comparative applicability and publication vintage; permit atomic
version-set repairs for failed rows while freezing numeric sources/valid versions;
constrain digest tokens rather than asking Luna to copy arbitrary hashes; factor
period/header metadata and supply only relevant complete sections once per task;
and distinguish support for period arithmetic from support for entity comparability
in resolver conclusions. Add saved-v4 interaction replays and a fresh fixture with
comparatives restated before a later reorganisation date before another paid trial.
These defects were not covered by the earlier 200 passing focused checks. Do not
increase retries, fabricate historical bridges, drop requested years or weaken
financial acceptance to make the builds complete. This diagnosis itself did not
authorize implementation; the subsequent user instruction above did.

**Approved semantic mapping and targeted Luna changes implemented (v4).**
The user approved the seven corrections and targeted additional Luna work discussed
below. All changes are in existing shared/historical modules; no company-specific
mapping tables, source coordinates or exported-cell patches were introduced.

* Source `row_key` is distinct from typed `financial_role`; Python checks canonical
  role/entity bindings during each batch and rejects source keys as model identities.
  Separately reported additional concepts remain supported with meaningful IDs.
* The source adapter preserves exact header/series references, fiscal dates and
  actual-period metadata, shared once through a compact period catalogue. Mapping
  receives clear base-metric/navigation classifications; the VA Analytics control
  is not treated as evidence that a company-reported base metric is a helper.
* The existing scope call now returns cited period/definition declarations, dated
  entity versions and nonoverlapping primary hierarchies. Original supporting
  sections accompany mapping. Coverage uses the hierarchy applicable to the fiscal
  period, without inventing a bridge or applying today's structure backwards.
* Essential statement/revenue candidates are processed first. Python checks their
  annual/group/segment coverage and offers bounded correction of exact gaps before
  remaining detail. One early Luna semantic review follows; a required correction
  is checked again. This does not replace the existing final combined-history review.
* Financial evidence gaps can trigger up to three targeted resolution tasks per
  build, using the selected original sections and full headers. They share the
  existing allowance and normal bounded response repairs. Unresolved essential
  evidence remains incomplete. Repairs must keep basis flags and explanations
  coherent; changing prose without changing substantive findings stops further patches.
* Actual `company_*` selection stage names now have explicit low-effort defaults;
  financial mapping, interpretation and review remain medium. Operator overrides
  remain explicit. These settings have offline routing checks, not a new live
  accuracy/latency benchmark.

The standard commands below still start fresh $20 historical-only runs from fiscal
2018 onward. Old mapping contracts cannot be silently resumed as v4. Original
company files, saved real runs and charged usage remain preserved. No paid API call,
company build, forecast calculation or DCF was launched during implementation.
Verification: **202 focused tests ran in 36.501 seconds: 200 passed, two skipped,
zero failures/errors**, with zero external network attempts. The skips reference
older archived runs removed during the explicit cleanup; the latest three saved
failure patterns were replayed successfully without provider calls. The suite covers
the early semantic review/correction/review sequence, conditional original-evidence
resolution with settled mock usage, semantic nonprogress, coherent period bases,
dated hierarchy coverage, source-ID/role separation, budgets, source parsing and
package boundaries. Both fresh quarterly USD and half-year JPY/reorganisation
fixtures reached `historical_complete_provisional` through the same compiler,
review/finalization functions and Excel export. Receipt:
`outputs/va_mapping_v4_release_20261031T160817Z.log`. `doctor`, CLI help, compilation
and whitespace checks passed. The latest real workbooks, saved mapping progress and
original VA hashes were rechecked unchanged. These checks are not desktop Excel
recalculation or a successful autonomous build for another real company.
The broader repository test attempt was stopped when it entered a lengthy unrelated
synthetic forecast/DCF build; verification is the focused historical/shared suite,
not a claim that every repository test completed. Fresh quarterly USD and half-year
JPY fixtures with different segments, fiscal calendars and a reporting reorganisation
exercise the same historical compiler/finalization/export. Saved real-response
replays remain distinct from fresh autonomous real-company validation.

**Preserved 15:23 UTC retest diagnosis, before v4: three incomplete drafts.**
Read all three fresh logs, saved request/candidate/patch journals, progress snapshots,
allowance ledgers and actual workbook cells. No engine changes, provider calls or
builds were made during diagnosis. All three stopped with exit code 1 before
historical source/accounting review or finalization; no forecast/DCF stage ran.

| Company | Wall time | Calls | Recorded USD estimate | Furthest progress |
|---|---:|---:|---:|---|
| Nestle | 19m21.354s | 26 | 0.165178800 | All 20 cohorts / 378 row decisions; final annual sales coverage check fails |
| L'Oreal | 8m47.331s | 16 | 0.073047175 | All 9 cohorts / 205 row decisions; final current-segment revenue check fails |
| Danone | 4m55.025s | 9 | 0.050463305 | 2/14 cohorts complete; 46/247 validated decisions including work in cohort 3; two repairs leave five essential Sales definitions with unresolved bases |

Latest runs: `outputs/construct_research_20261031T152303Z_e766b896` (Nestle),
`outputs/construct_research_20261031T152305Z_5745778e` (L'Oreal), and
`outputs/construct_research_20261031T152310Z_163598d3` (Danone). Each contains
`historical_model_incomplete.xlsx`, its backend JSON and workbook validation JSON;
the historical stage status is incomplete, not financially accepted. Workbook
read-back/layout checks passed, hashes match the registered artifacts, and streamed
inspection found respectively 3,689 / 3,793 / 396 Model source-link formulas and
13,538 / 7,818 / 1,177 numeric Historics observations. These Model sheets are
populated provisional drafts, unlike the earlier blank drafts. Desktop Excel
recalculation and completed source/financial review remain unperformed.

The zero-AI numeric preflight passed on all 59,261 VA cells. All 51 calls used
Luna/medium, made zero web searches and settled once with known usage; their total
recorded estimate is $0.288689280, using the saved 23 October pricing table, not
provider invoice confirmation. The allowance was not the stopping cause. API time
totals were 1,075.156 / 488.151 / 255.548 seconds; most wall time was in AI calls.
Nestle used 3 source/scope calls, 20 mapping calls and 3 patches; L'Oreal 3 + 9 + 4;
Danone 3 + 3 + 3. Source/scope calls succeeded in producing cited declarations, but
this does not establish the correctness of their financial interpretations.

Nestle's message, `Requested VA year has no mapped consolidated annual sales: 2018`,
is an identifier mismatch: the source-derived 2018-FY Sales value 91,439 is retained
as model row `row_7`, rather than canonical `sales`. Group Total revenue is similarly
`row_177`. The schema permits arbitrary row IDs; per-cohort validation accepts them,
while final coverage requires the exact canonical role. Further current-segment
coverage gaps remain possible after this first failure is repaired.

L'Oreal's `dermatological_beauty` check fails despite retained 2025-FY revenue of
7,204.1: the mapper assigned it to `dermatological_beauty_legacy_sales`. A bounded
patch replaced pending work with legacy identities rather than establishing a
dated current/legacy relationship. Canonical names alone cannot supply a reporting
bridge or justify rewriting the entire history onto today's structure.

Danone fails on five repeated group Sales rows because `basis_status` remains
unresolved (standalone versus cumulative periods). Repairs reword the explanation
without resolving that uncertainty. Mapping payloads include row text, two recent
examples, oldest/latest period IDs and current segment labels, but do not supply
the complete verified period metadata or relevant original reporting-change/notes
context already selected during scope research. Original/restated uncertainty is
still being conflated with period-basis uncertainty in some responses. Nestle also
has 120 accepted observations with `basis_status=period_defined` while the saved
basis description still begins `Unresolved:`: the patch contract allowed flag and
classification changes, but not correction of the contradictory basis field.

Proposals awaiting approval: separate source row keys from constrained model roles;
validate role/entity coherence per cohort; pass verified period metadata and cited
definition/reorganisation context into mapping; model segment versions by date;
check essential coverage early and repair exact gaps; detect unchanged semantic
findings rather than accepting reworded patches; and add end-to-end regression cases
for these actual response patterns. Optimize compact responses and deliberate
stage-effort routing only after these correctness changes. Current low-effort
`construction_select`/`construction_map` settings do not match the `company_*` task
names used here; all actual calls were medium. Do not weaken coverage, invent bridges,
mark every fact eligible or rerun unchanged paid builds as the proposed remedy.

**Additional Luna-call discussion, 31 October:** The user is open to more cheap
Luna calls if they improve reliability. Recommendation, not implementation approval:
first correct deterministic role contracts, period metadata and patch coherence;
enrich the existing reporting-scope call rather than duplicate it. Consider a small
early semantic review of essential bindings and conditional gap-resolution calls
that receive newly supplied original headers/notes and specific unresolved questions.
Preserve Python source binding and bounded, evidence-backed repairs. The combined
VA-history review already exists but these runs failed before reaching it; do not
add a duplicate blanket final review. More calls with unchanged context are unlikely
to resolve the observed failures and add latency. The proposed fixes address known
failures, not proof that unreached accounting/review stages will succeed. No engine
change, provider call or new paid trial is authorized by this discussion alone.

**Earlier user-requested cleanup completed before these retests.** The contents of `outputs/` and
`forecasting_engine/company_initiation/logs/` were sent to the Windows Recycle Bin
(204 output entries and six log files); both folders were retained for new runs.
The latest user-operated retests above have since populated them. All 42 engine/test Python files matched their pre-cleanup hashes.
Original company data remains in `data_store/company_data/`. Earlier run paths,
test receipts and log references below describe historical work and are no longer
present in the workspace. Old runs cannot be resumed unless restored. This explicit
cleanup supersedes preservation of those artifacts for this action; it does not
change the engine, future run budgets or financial acceptance rules.

**Second-round historical reliability fixes implemented; fresh live trials pending.**
The user approved the seven corrections diagnosed from the 14:43 retests below.
The reusable engine now uses `va_semantic_mapping_v3`: finite scientific notation
is supported and native/string numeric round-trips are preflighted before AI;
source selection uses a compact navigation catalogue with exact source-ID choices
and bounded response-contract correction; deterministic parser/integrity failures
stop without spending on irrelevant semantic patches. Duplicate core rows may be
excluded only with cited equivalent retained coverage from the same source.

The approved `provisional_vendor_v1` display policy separates a fact's source
arithmetic, financial definition, period basis, original/restated provenance,
publication vintage and calibration eligibility. Source-checked company-reported
VA facts with clear definitions/bases can populate a visibly provisional Model even
when original/restated provenance is unknown. Their strict eligibility remains
false; no calibration, independent primary verification, point-in-time claim or
cross-basis derivation is inferred. Unresolved definitions/bases and vendor-normalized
facts remain excluded. Conflicting versions remain visible failures. Historical-only
`initiate` keeps its existing stricter standard.

Historical Excel validation now tolerates only numeric serialization differences
(`rel_tol=5e-15`, zero absolute tolerance); formulas and other structure remain exact.
A failed draft and its diagnostic report are registered before failure is reported,
and nested failure handlers attempt the incomplete export only once. Incomplete
and provisional labels remain distinct from completed financial acceptance.

Verification: **163 focused tests passed in 76.532 seconds**, plus four legacy
numeric parsing checks. Offline preflight passed on **59,261 actual VA cells**
(Nestle 27,333; L'Oreal 15,948; Danone 15,980), with original hashes unchanged and
zero AI calls. Nestle's navigation payload falls from about 1.41 million to 126,108
characters while the full inventory remains saved. Local replay re-exported the
two failed draft snapshots; structurally different synthetic fixtures also pass.
`doctor`, historical CLI help and compilation checks passed. Receipts:
`outputs/archive/tests/va_retest_fixes_20261031_release.log` and
`outputs/archive/tests/va_real_source_preflight_20261031.json`.
These are offline/parser/fixture checks, not new real-company validation or desktop
Excel recalculation. No paid call or company build was launched; original runs and
charges remain preserved. Later accounting/review gates have not been established
by the failed live runs and can still expose financial or evidence gaps. User-run
fresh historical trials are next; no forecast or DCF handoff is enabled.

**Preserved 14:43 UTC live retests, before these fixes: all incomplete.**
Read the three latest logs, request/patch journals, progress snapshots, workbook
contents and allowance-ledger entries. No engine change, paid call or company rerun
was performed during this review. Each run was a fresh `construct-history` with its
own $20 allowance. All logs end failed/exit code 1; no completed historical checkpoint,
accounting-structure review or forecast/DCF stage was reached.

| Company | Wall time | Calls | Recorded USD estimate | Progress |
|---|---:|---:|---:|---|
| Nestle | 1m33.180s | 1 | 0.090732850 | Initial source selection returned nonexistent `local_202?`; no mapping or workbook |
| L'Oreal | 10m31.533s | 18 | 0.140207000 | 7/9 cohorts complete; failed in cohort 8; 185/205 row decisions and 7,447 source observations retained including valid work in the failing cohort |
| Danone | 8m47.074s | 16 | 0.067758050 | 9/14 cohorts complete; failed in cohort 10; 186/247 row decisions and 6,138 source observations retained including valid work in the failing cohort |

Total **35 calls/$0.298697900 estimated**, reconciled to settled ledger entries;
zero new unresolved reservations. Earlier lifetime commitments remain separate.
All calls used Luna/medium. L'Oreal used 4 initial source/section/scope calls
(including one corrected original-page citation), 8 mapping calls and 6 patches.
Danone used 3 initial calls, 10 mapping calls and 3 patches. Nestle used one selection
call. These estimates are not invoice confirmation.

Latest records: Nestle `outputs/construct_research_20261031T144428Z_95dd96fc`,
L'Oreal `outputs/construct_research_20261031T144355Z_2503b344`, Danone
`outputs/construct_research_20261031T144321Z_58bea8c9`. L'Oreal and Danone each have
`historical_model_incomplete.xlsx`, but export validation failed before artifact
registration, leaving no registered historical stage output or successful workbook
validation report. The files are readable diagnostic drafts: `Model` has zero values
or formulas; `Historics` has respectively 7,025 and 5,784 numeric observations.
They are not completed usable company models.

L'Oreal stopped on `-2.607164804e-05` in Adjusted LFL - North Asia; Danone on `1e-05`
in M&A - Waters. Native numeric tokens resolve, but Python stringifies the claimed
source value and the strict financial-number parser rejects scientific notation.
The resulting parse failure is wrongly routed as a permitted `row_id` patch.
Both models renamed the financial concept, which cannot fix a numeric parser error,
and exhausted two patches. Earlier entity/coverage patches did allow substantial
progress; the original period-enumeration/unit-spelling failures did not stop these
two runs. Their latest-first source facts and cohort checkpoints were retained.

Fallback Excel read-back also has a deterministic defect: it demands exact numeric
equality after serialization. Read-only comparison found 814 L'Oreal and 632 Danone
numeric mismatches, all within diagnostic `rel_tol=1e-12, abs_tol=1e-12`, with maximum
absolute difference 7.275957614183426e-12. This verifies serialization differences
only, not semantic mapping accuracy. Export is retried twice through nested handlers,
both fail before stage registration and neither prints a successful workbook path.

At the time of diagnosis, eligibility was a separate material blocker: all retained observations had
`eligible=False`. L'Oreal has 6,847 marked unknown restatement and 600 vendor_normalized;
Danone has 6,138 unknown. The current policy excludes these from the model projection,
even when a source number/label is mapped, so fixing parser/export alone leaves blank
Model sheets. Do not simply mark all facts eligible. Separate source arithmetic,
financial definition, dated reporting-basis comparability, original/restated status,
publication vintage and independent verification; define an explicitly provisional
display policy for usable vendor facts while retaining unresolved basis/calibration
restrictions. The subsequently approved policy is implemented above; it is not a
blanket relaxation of history gates.

Proposals from this retest review: constrain initial source selection to catalogue IDs
and validate inside its repair stage; handle finite scientific notation/native numeric
round-trips in Python and preflight local cells; classify deterministic parser/code
failures separately from AI-correctable mappings; use narrowly defined numeric export
tolerances while preserving exact formulas/identities; register/label failed drafts and
their diagnostics reliably through one export handler; permit genuinely verified
duplicate core rows when concept-level coverage is retained (current gate rejects
core duplicate proposals before checking equivalence); and replay these exact cases,
including real-life decimal precision and all-ineligible snapshots, offline before
another user-operated live trial. Nestle's selection catalogue is 444 entries/about
1.41 million payload characters; project a compact verified navigation catalogue
while preserving the full local inventory and originals. These proposals were
subsequently approved and implemented as described above.

**Earlier first-round VA mapping implementation, superseded by v3 above.**
The user approved the seven proposed changes. Construction now uses the versioned
`va_semantic_mapping_v2` contract in the existing historical modules and shared
runtime. AI chooses financial concepts, entities and evidence-backed reporting
versions; Python expands all eligible source periods, chooses canonical units from
the supplied VA unit conventions and preserves original cell references. Currency,
scale and share/per-share distinctions remain explicit; unsupported/foreign units
stay unresolved. A quoted or escaped percent in Excel is a literal percentage-point
label, whereas an unquoted percent formats a stored fraction. Python now distinguishes
these and normalizes once, including the actual VA literal-percent formats.

AI receives explicit target rows plus a separate read-only metric index. Native
labelled entities are grouped and packed into cohorts of up to 24 rows, with live
cohort/row progress. It returns one map/exclude/pending decision per target row;
stable definitions need no period enumeration. Changed definitions require cited,
nonoverlapping intervals covering every available period. Financial amounts remain
in history even without a forecast role; diagnostic exclusions require specific
ratio evidence. Duplicate exclusions must retain matching labelled units, values
and periods in a mapped row. Not-assessed work stays pending. Consolidated annual
sales for each requested year and latest annual segment sales remain mandatory.

Repairs receive the exact previous candidate, its digest, row-level findings and
permitted paths. Python applies only digest-bound permitted changes and validates
the complete resulting schema before adoption; other rows/fields stay frozen.
Cell-level failures remain in audit JSON while repeated findings are grouped for
repair. Initial, repaired and rejected responses, charges and diagnostics persist.
The same conservative allowance and bounded repair limits apply throughout.

Validated cohorts and `va_mapping_progress.json` preserve compatible work. A later
failure saves `historical_model_incomplete.xlsx` and its backend/validation files,
with a visible INCOMPLETE label and printed path. This is a source-checked draft,
not completed historical financial review. Explicit compatible resume replays saved
work under its existing allowance; default commands still start fresh research and
a new $20 allowance. Older completed VA mappings without the new contract are
rejected for reuse rather than silently reinterpreted. Old runs and charges remain
unchanged. Historical-only operation still makes no forecast/DCF handoff.

The three failed live runs below remain preserved and were not rerun here. Local
archived-response replays adapt their old response representation mechanically to
exercise the new deterministic checks; they are not new AI mappings or successful
real-company builds. Fixture exports also cover USD/calendar-year and JPY/March-year
companies with a legacy reporting reorganisation. No company-specific production
mappings, manual workbook patches or paid calls were introduced.
Verification: a **154-test focused regression run passed in 59.014 seconds**,
followed by **51 final checks in 17.979 seconds** after the mapping-contract reuse
guard and cleanup. There are 155 distinct test cases across those two receipts,
with zero failures, errors or skips. `doctor`, historical CLI help, compilation and
changed-file whitespace checks also passed. The checks include actual local saved
response patterns, synthetic full historical exports, literal/native percentages,
definition intervals, forbidden patch mutations, pending exclusions, incomplete
Excel output, explicit resume, allowance continuity and downstream isolation.
Receipts: `outputs/archive/tests/va_mapping_v2_20261031_release.log` and
`outputs/archive/tests/va_mapping_v2_20261031_final.log`. This was a focused suite,
not every repository test; no live provider accuracy or desktop Excel recalculation
was established. Original failed-run artifact hashes and recorded costs were
rechecked unchanged.

**Latest live historical-only attempts: all three stopped before any Excel output.**
Reviewed the user's 31 October terminal logs, saved request/response journals,
repair feedback, artifact hashes and allowance-ledger entries. These were fresh
`construct-history` runs with independent $20 allowances, history from 2018,
information date 2026-10-31 and latest completed FY2025. No construction code was
changed, paid call made or company build rerun during this diagnosis.

| Company | Wall time | AI calls | Recorded USD estimate | Saved run |
|---|---:|---:|---:|---|
| Nestle | 10m 31.601s | 8 | 0.315256750 | `outputs/construct_research_20261031T132932Z_d0308135` |
| L'Oreal | 6m 29.157s | 7 | 0.093361600 | `outputs/construct_research_20261031T132944Z_12462510` |
| Danone | 4m 51.252s | 6 | 0.060866675 | `outputs/construct_research_20261031T132956Z_ed4c2498` |

All 21 calls were recorded as Luna/medium with returned usage; the total estimate
is **$0.469485025**, including unsuccessful mapping/repair attempts. Ledger sums
agree and these new periods have zero unresolved reservations. These are dated
application usage estimates, not invoice confirmation; larger lifetime totals in
the logs include earlier attempts. All logs have failed end markers/exit code 1.

Local inventory, company-reported VA selection, local supporting-section selection
and reporting-scope research completed. Latest-first anchors were 2026-Q3 for
Nestle/L'Oreal and 2026-Q2 for Danone; FY2025 was the completed annual anchor.
Online discovery was not performed. All stopped inside `_va_history_inputs`,
before accounting-structure research, combined-history review, workbook export or
downstream construction. None of these folders has `historical_model.xlsx`,
`company_model_inputs.json`, `company_model_inputs_progress.json` or completed
`va_history_bindings.json`; frozen sources, scope/driver research and all AI replies
remain saved. Artifact hashes were verified.

Nestle formally completed the first 40-row cohort, with 11 mapped and 29 excluded
rows, then exhausted two repairs in the next cohort. Percentage conversion and
unit-format errors preceded the final omission: `row_71`, M&A and others impact -
Nespresso, lost 2024-Q2 and 2024-Q3 from its 53 available periods. L'Oreal's first
40-row cohort passed with zero mappings and 40 generic not-assessed exclusions,
which is a validation weakness rather than successful financial extraction. Its
next cohort hit unit-format errors (`EUR_m` versus the expected `EURm` convention);
the final repair changed Net sales from entity `group` to `corporate`, causing 60
period-level group-identity failures. Danone never completed the first 40-row cohort:
24 rows were initially addressed, a fuller repair introduced double percentage
conversion, and the last reply returned just seven mapped rows with no exclusions.
The final failures were mapping/repair errors, not budget exhaustion, connectivity
or evidence that the VA originals themselves lack the omitted rows/periods.

Proposed next corrections, not implemented by this diagnosis: make Python own
deterministic period expansion and unit/percentage representations; make current
cohort versus full catalogue scope explicit; validate meaningful exclusions and
essential financial coverage; apply bounded field-level repairs without rewriting
valid mappings; retain validated cohort checkpoints with explicit incomplete status.
The 148 offline fixture checks above predate these live failures and do not prove
reliable autonomous real-company mapping.

**Mapping changes discussed with the user, still proposals:** Review of the current
implementation confirms `RunJournal.stage` supplies the original payload and error
strings for each repair, without attaching the preceding candidate answer. The
provider request has no prior-response conversation link. Thus instructions to
preserve valid mappings are not backed by a supplied candidate or an enforced merge.
Some feedback also addresses expanded observation `terms`/entry indexes although
the VA response schema exposes row mappings, `row_key`, `multiplier` and period lists.
This mismatch helps explain partial repairs and changes to previously valid fields;
it is not proof of every model reasoning error's cause.

The proposed implementation sequence is: (1) Python expands exact eligible periods
from row bindings, with explicit cited version intervals for real definition changes;
(2) typed, source-evidenced units/scale/percentage normalization and compatible
role/entity choices, with exact schema options and field-correct errors; (3) supply
the saved candidate plus row-level findings and permit only bounded, hash-bound
patches, merging in Python and retaining rejected attempts; (4) make target cohort
versus context catalogue explicit, use coherent financial tasks, and group repeated
cell failures into actionable row findings while retaining full diagnostic evidence;
(5) require evidenced exclusion reasons and disclosed essential-statement/segment
coverage, keeping not-assessed work pending and genuinely absent data visible;
(6) persist compatible validated cohort progress and export an explicitly incomplete
historical draft on later failure, printing its path, without promoting it to accepted
history or starting later stages; (7) reproduce these saved failure patterns offline
and test the whole chain through final historical export before user-operated live
trials. Replay of actual local saved responses, synthetic regressions and new live
research must be identified separately. Keep fiscal 2018 coverage, reporting versions,
explicit-only continuation, original allowance ownership and source checks intact.
These proposals refine the reusable engine; no company-specific mapping or workbook
patch is proposed. Later accounting/review stages remain unvalidated by these runs.
This discussion made no construction-code changes or paid calls.

**Historical stage can now be run separately:** `construct-history` uses the same
company-reported VA research and combined-history review as `construct`, then
verifies frozen sources, dates and historical derivations and exports
`historical_model.xlsx`. It ends with `historical_complete_provisional` when these
checks pass, without importing or dispatching forecast or DCF construction. A new
`outputs/construct_history_<timestamp>_<id>/` checkpoint retains the handoff JSON,
source validation, history validation, workbook and linked research parents.
Stage-one accounting research still prepares its existing accounting/driver/policy
declarations; this command does not calculate forecasts, run valuation, use shared
FX forecasts or certify independent primary-source/desktop Excel acceptance.
An earlier partial research workbook remains distinguishable from this final
historical checkpoint. Logs and the fresh-run/explicit-resume budget policy apply.

**VA mapping now explicitly starts with the newest eligible actuals.** Scope
selection already asked for current reporting definitions; VA row mapping previously
covered all years together, with cell lists/examples in ascending period order.
Python now orders rows and cells newest-first using fiscal end dates and supplies
a dated `historical_anchor` with the latest actual, latest completed annual, current
segment IDs and reporting basis. It is saved in `va_history_bindings.json` and the
company inputs. Current definitions anchor research; predecessor segments remain
separate unless a cited published restatement or numerical bridge supports reuse.
Future/consensus cells remain excluded. Excel columns remain chronological from
2018 by default; no old geography is retroactively relabelled into today's segments.
Verification: **148 focused offline tests passed** in 49.043 seconds, plus `doctor`
and command help. Synthetic tests exercise the public historical-only command,
prohibit downstream imports, check Excel output and its chronological columns,
keep latest interims separate from completed annuals, reject stale reviews/changed
originals and verify fresh versus resumed allowances. The USD/calendar-year and
JPY/March-year/reorganisation cases are fixtures, not other real-company validation.
Receipt: `outputs/archive/tests/historical_command_20261031_release.log`.
No paid calls, real company builds or desktop Excel recalculation ran; the full
suite was not run.

**Default terminal runs now start fresh with a new budget.** Ordinary `construct`
and `initiate` commands start new research instead of selecting older matching runs.
The new allowance defaults to $20; `--budget-usd` may choose a smaller cap. History,
forecast construction and DCF share that single build allowance. `--fresh` is an
optional alias for the default. Use `--resume RUN` to continue selected compatible
work and its original remaining budget, including an older independent build after
newer fresh builds. Saved `--model-inputs` is also an explicit reuse request; when
it belongs to a saved run, its existing budget is retained. Explicit update/export
and FX-refresh commands continue the named run. Earlier spending, unresolved
reservations, request ownership and run files remain preserved in lifetime records.
Repeating an ordinary command repeats research and may incur new API costs.
No real company allowance was reset and no paid build was launched during this change.
Verification: **146 focused offline tests passed** in 48.735 seconds including
budget isolation, old-run continuation after a newer fresh build, shared stage
limits, preserved unknown charges, command logging, VA history and strict-initiation
resume regressions. Test receipt:
`outputs/archive/tests/new_run_budgets_20261031_regression.log`.
These are fixture checks, not live company validation; the full suite was not run.

To continue a saved construction, add an explicit selector to the ordinary command:

```powershell
python -m company_initiation construct "COMPANY IDENTITY" --sources data_store/company_data/COMPANY --resume outputs/RUN_FOLDER
```

Use the company identity and run folder from the saved attempt. Omitting `--resume`
starts a new build and allowance.

**Historical-construction sequence audited against code:** For VA-backed
`construct`, CLI parsing/logging and explicit saved-input selection precede local source
inventory, locked budget/journal setup, AI identity selection, optional section
selection and AI reporting-scope research. Python then builds fiscal periods,
selects eligible VA cells and expands AI row mappings in cohorts of 40 rows.
An initial historical workbook is saved before accounting-structure research.
The accounting stage also prepares driver/policy declarations for later forecasts;
historical completion is broader than merely populating historical numbers.
Python validates accounting scope, bridges and latest-year segment anchors before
the six-topic AI history review. Final research saves `company_model_inputs.json`,
re-exports history and sets `research_complete`; the CLI verifies/reuses that review
through `ensure_company_history_research`. The backend JSON is the handoff, not
workbook edits. `construct` proceeds automatically; `construct-history` stops with
its own verified historical checkpoint. Some final source/hash/freshness checks and another
historical export still run at the beginning of `forecast_construction.integrated`
before `build_periodic_spec`. The physical module boundary therefore does not
exactly coincide with the final historical-validation boundary. Early workbook
existence is not proof of historical completion or financial acceptance. Historic
export checks saved formulas/layout and compatible flow/stock derivations; it
does not run desktop Excel or establish independent primary-source verification.
This walkthrough changed documentation only and made no research/API calls.

**Implemented: company-reported VA is the primary construction history.** Normal
`construct` detects supplied VA exports, uses explicitly company-reported files
or labelled company-reported sections, and excludes standardized data from primary
inputs. AI maps row meanings, financial roles and supported reporting versions;
Python expands those mappings into exact actual Excel cells across fiscal periods.
Populated Filings takes precedence over VA Actuals for the same row/period; missing
Filings may use an available VA Actual. All available series remain in the saved
binding audit. No consensus, estimate, helper or future-period values enter history.
Unclassified reporting versions remain excluded from model calibration, and
unsupported interim statement cells remain audit evidence rather than silently
becoming reported quarterly statements.

The VA route performs no automatic historical website discovery or full primary
PDF numeric re-extraction. Local originals selected for company reporting and
accounting definitions remain available for scope, leases/cash, reorganisations,
missing policies and later valuation evidence. Explicit `update` retains online
new-release discovery but does not request historical backfill for VA models.
Ordinary local-date/archive refresh uses the VA route. Freshness and independent
primary numeric verification are visibly unperformed on a local build; historical
vintage restrictions and material financial/source errors still apply. These are
provisional construction outputs, not strict historical-initiation acceptance.
Historical-only `initiate` keeps its original independent reconstruction gates.

The same public command uses the VA route for fresh construction with its own
allowance; it does not rewrite earlier runs. Explicit incompatible `--resume`
is rejected. A provisional
historical Excel checkpoint is retained after VA extraction if later accounting
configuration is incomplete, and normal stage/final exports remain in place.
Detailed choices and source references are saved in `va_history_bindings.json`
and `historical_source_review.json` in each new run.

Verification: **95 focused offline tests**, covering the public research entry,
source-policy continuation, local versus explicit online update, frozen-source
review, cell eligibility, missing-versus-zero behavior, stage output, existing
budgets and strict initiation safeguards. Synthetic USD/calendar-year manufacturing
and JPY/March-year equipment/services cases use the same compiler; the latter
retains a legacy division and a reporting reorganisation. These are fixture tests,
not successful real-company models. A read-only parser check recognized all three
supplied real company-reported workbooks: Nestle 378 metric rows/15,144 eligible
cells; L'Oreal 205/8,267; Danone 247/8,516, using the stated fiscal-period window
from 2018 to the 31 October cutoff. Their original hashes remained identical.
This verifies ingestion only. `doctor` and construct help pass. No paid calls,
company builds, Excel desktop recalculation or real-model acceptance ran here.
The full suite was not run. Test receipt:
`outputs/archive/tests/va_primary_history_20261031_release.log`.

**31 October PDF/Markdown discussion:** The user asked whether converting company
documents to Markdown would make AI research easier and more reliable. Current
PDF ingestion uses `pypdf` layout text extraction plus indexed numeric tokens;
`shared_ai._input_messages` sends that evidence as JSON text, not original PDF
files or page images. The current source-format allowlist does not accept `.md`.
Clear headings, preserved tables and footnotes could improve the evidence view,
but merely converting or renaming extracted text cannot recover lost row/column
relationships. PDF parsing has not been established as the cause of the observed
mapping errors. Markdown would not resolve protected-field repair failures,
website 403 responses or repeated large journal writes.
Proposed evaluation, not implementation: use supplied VA spreadsheets for numeric
history; retain PDF originals and generate a reusable Markdown view for narrative
notes, with structured tables where needed, original page/cell references, source
hash and conversion version. Check conversion fidelity on difficult tables before
bulk conversion or claims of lower cost/latency. The user has not authorized a
format migration, manual conversion workload or paid conversion calls.

**31 October source-priority clarification:** The user supplied Visible Alpha
exports to provide historical numbers and questions why construction downloads
historical company releases. The current implementation performs official
discovery across the requested years before mapping, requires primary financial
reports for each year, and supplies eligible VA history alongside those originals.
It therefore does not currently implement the expected VA-led local build.
Earlier independent-source requirements explain the use of company originals,
but do not inherently require downloading history again when suitable local
evidence exists. User intent is to avoid routine online historical backfilling.
Proposed revision for discussion: extract eligible reported VA actuals first;
use local originals for definitions, reporting changes and independent support;
identify specific evidence gaps before any targeted retrieval; keep online
freshness/update research distinct from the local historical build. This does
not deem a second read of VA independent verification or waive missing primary
support. No application behavior changed in this clarification.

**31 October diagnosis of the 25 October terminal attempts:** Traced the three
named command logs through the current CLI, historical research, journal and AI
transport code, and checked each run's saved calls and repair payloads. This was
diagnosis only: no application edits, API calls, builds or workbook exports.
All three stopped inside `research_company_inputs`, before a completed 2018
history, independent numeric reconstruction, historical Excel, forecast or DCF.

| Company | Command elapsed | New AI calls | Saved AI-call duration | New estimated API cost (USD) |
|---|---|---|---|---|
| Nestle | 12m 06.9s | 3 | 2m 22.0s | $0.179484625 |
| L'Oreal | 43m 24.1s | 15 | 15m 37.9s | $1.044924500 |
| Danone | 28m 58.0s | 10 | 12m 12.4s | $0.462529450 |

The 28 new calls total $1.686938575 in recorded estimates, not a verified provider
invoice. They all used `gpt-6-luna`, medium reasoning, and returned without an
AI-transport failure; subsequent Python validation still rejected some answers.
The `Whole run` usage line includes inherited attempts. Current-period ledger
totals and saved call timestamps distinguish these new charges; earlier unresolved
reservations remain preserved. L'Oreal and Danone each reused three earlier
identity/section/scope answers without a new paid call.

Nestle's three official-index requests all returned HTTP 403. L'Oreal completed
six discovery rounds (one round required a correction), with 48 page downloads
and 49 release-download events; Danone completed two rounds with two page and 51
release-download events. Discovery success did not establish numeric coverage.
Both then stopped in the first 2018 operating-performance mapping task. L'Oreal's
initial answer had 43 invalid observations out of 93; Danone's had 74 out of 129.
Errors included nonexistent/out-of-context references, selected tokens differing
from the AI's transcription, and a Danone segment/group role mismatch. Those
counts are validator findings, not a claim that every other observation is correct.

The repair schema asks for whole replacement observations while per-entry
`allowed_fields` permits only selected fields to change. L'Oreal's repair changed
protected fields in 18 of 43 patches; Danone's did so in 8 of 74. The validator
stopped at the first such change. This contract error aborts immediately rather
than reaching the next financial-repair iteration, despite a two-repair setting.
Keeping the protection is necessary; permitting arbitrary changes is not a fix.

Elapsed time outside AI calls was 9m 44.9s, 27m 46.2s and 16m 45.6s respectively.
This includes website retrieval, parsing, saved-run verification, accounting and
persistence, not just Python calculation. A confirmed structural overhead is that
every journal artifact calls `save`, rewriting the whole inherited call history
inside `record.json`. Final records are approximately 313.5 MB, 228.6 MB and
183.9 MB; logs contain 15, 231 and 133 artifact-save events. Profiling is still
needed to attribute the non-AI time precisely; these observations do not prove
OneDrive alone caused the delay.

**Process proposals for discussion, not implemented:** Use field-limited repair
payloads merged by Python; make source/token identifiers easier to select exactly
and map narrower coherent original tables; preflight website access before costly
research and support explicitly dated local-source builds with visibly incomplete
freshness when appropriate; persist large immutable request/response evidence once
with a compact status record; label API-response completion separately from
financial-validation success. Retain source, reporting-basis and independent
review gates. Validate reusable corrections against these saved failure cases
offline before the user launches further company attempts.

**Latest user-run results, checked after 22:53 UTC:** All three companies exited
with code 1; none reached the historical Excel checkpoint or produced any new
model workbook. Nestle's `construct_research_20261025T221517Z_13957c28` stopped
because no evidenced official release index was accessible (22:21 UTC). Danone's
`construct_research_20261025T221331Z_578afdf9` stopped because a mapping repair
changed frozen `classification_basis` and `classification_source_refs` metadata
(22:39 UTC); the repair was rejected and its prior answer retained. These folders
contain research and failure evidence, not completed models. L'Oreal's
`construct_research_20261025T221330Z_a3a9f924` stopped at 22:53 UTC because its
mapping repair changed frozen `terms` metadata; that repair was also rejected.
Checked all three folders for all three stage workbooks and `model.xlsx`: all
absent. No company build processes remained at this check. The requirement to
wait for active builds before the authorized folder migration is now satisfied;
the migration itself has not started.
This status inspection made no paid calls and changed no application code.

**Output organisation while company builds run:** The user has launched the three
terminal builds. Grouped 207 inactive standalone logs, execution receipts and audit
reports under `outputs/archive/`, in `nestle/`, `loreal/`, `danone/`, `tests/` and
`audits/`. Every moved file retains its original contents; SHA-256 checks passed.
`outputs/archive/relocations.json` maps original paths to archived paths and hashes.
Old receipts deliberately retain their original path text; consult that index for
relocated logs/receipts. README references use the new locations.
All 179 run directories present at the move remain in their original locations;
all 28 application Python files are unchanged. Budget ledgers, ownership records,
locks, scenario inputs and active logs were not moved. The engine currently requires
direct-child run directories and stored paths for continuation and cost attribution;
moving those now could interrupt builds. This is the safe archive portion of the
requested tidy-up, not a completed migration of the run storage layout.

**Confirmed next storage change:** The user requires actual model run folders
grouped by company and clearly dated, and chose to defer that move until the
running builds finish. Do not substitute navigation links or hide the flat folders
in VS Code. Target layout:
`outputs/companies/<company>/<YYYY-MM-DD>/<HH-MM-SS>_<run-kind>_<id>/`.
Use each attempt's own creation time in UTC, not an inherited ancestor's start
time or the model's financial as-of date. Company grouping comes from saved run
identity; synthetic tests and shared FX work remain separately identifiable.
At this decision, L'Oreal and Danone processes were still running. No run moves,
application edits, junctions or editor exclusions were made for this follow-up.
The migration has not started and no background migration watcher is installed.

**Latest request: 2018 history and fresh company allowances.** The default historical
scope is now fiscal 2018 onward. The user explicitly authorized a new $20 spending
period for each of Nestle, L'Oreal and Danone. Old charges/reservations remain in
lifetime audit records; they do not consume the newly authorized period. At reset,
each active period had $0 spent, $0 reserved, a $20 limit and $20 remaining; these
are starting balances, not current balances while builds run. All 483 earlier requests, their original charge/reservation
fields, legacy ledger bytes and request ownership were verified preserved.
Verification: **102 combined focused offline tests passed in 13.142 seconds**,
including reset/reimport/settlement safeguards, default and explicit history
selection, fiscal calendars, stage workbooks and CLI logging. `doctor` and CLI
help pass. An additional 15-test focused history selection passed in 5.953 seconds (some
overlap with the combined check). An optional three-test extended synthetic
selection was stopped after 377.3 seconds to bound verification time; it had no
completed receipt and is **not a pass**. That selection included fresh raw-source
construction and two eight-year historical-initiation cases. Full end-to-end
verification therefore remains outstanding. No paid calls or real-company builds
ran for this change.

Different companies can run concurrently in separate terminals. Same-company
construction is protected by a company lock; shared accounting and FX use short
locked transactions. Excel automation instances and output/log folders are separate.
The 46 saved execution receipts for the three companies have process durations
from 3.07 to 32.15 minutes, all with exit code 1. These are incomplete attempts,
not successful full-build benchmarks. A planning estimate is roughly 30-90 minutes
per company, potentially two hours or more with substantial fresh research or
repairs; it is not a measured service guarantee. Concurrent successful complete
builds are not yet validated, and API limits/machine load may cause contention.

**User-operated terminal builds and audit logging:** The user will launch Nestle,
L'Oreal and Danone themselves. Do not start those builds or paid API probes from
this preparation task. Normal `construct` commands now create a unique timestamped
text log under `forecasting_engine/company_initiation/logs/`, ignored by Git.
The log captures console progress, audit-artifact paths, validation status counts,
run-status changes, errors and the terminal exit result; detailed source evidence,
requests/responses and financial checks remain in the referenced `outputs/` run.
This is a process audit trail, not tracing every Python instruction or a guarantee
that every business requirement was validated. Each attempt keeps a separate log.

Pre-reset readiness snapshot, 25 October 2026: latest real attempts are incomplete.
Nestle stopped on a 2017-H1 CFO numeric binding; L'Oreal stopped on a repair that
changed frozen reporting definitions; Danone exhausted repairs on seven 2016-FY
source bindings. Those failures belong to the earlier history scope; the 2018 start does not prove
that the remaining years are correct. Approximate remaining company allowances
before the later authorized reset were $6.41, $8.47 and $15.07 respectively, after incurred
estimates and unresolved reservations; these are not invoice-confirmed balances.
The figures above describe the October 25 allowance period. Under the October 31
policy, repeating a default command starts a new allowance; use `--resume RUN` to
continue that earlier work and its remaining budget.
Today-as-of continuation can require new discovery and review. Desktop Excel is
registered but was not launched in this check; normal construction uses the saved
shared FX database and does not require TWS. FX has BRL and CHF actuals through
23 October; ARS coverage stops 25 September. Do not edit Python during a build:
the runtime guard intentionally stops execution if code changes.

Audit-logging verification: **56 focused offline checks passed** (49 journal,
budget, package/stage-output and timer checks, plus seven CLI-log checks). An
initial test command misspelled the logger test class; the correct seven-test
selection passed separately. `doctor` passes. Tests mock construction dispatch and
provider calls; no company builds, paid API calls, live discovery, broker requests
or desktop Excel launches ran for this preparation task. The full suite was not
repeated.

**Latest folder layout:** Python packages live under `forecasting_engine/`.
Company originals live under `data_store/company_data/<company>/`; shared FX and
the Bunzl reference remain `data_store/FX/` and `data_store/bunzl_example/`.
The four existing company folders (Danone, L'Oreal, Nestle and Unilever) have been
moved without modifying their contents. Packaging, project-root detection, FX
defaults, command examples and Git exclusions use the new paths. The command
remains `python -m company_initiation ...`; the editable installation was refreshed.
Saved runs and budget ledgers remain under `outputs/`. A storage-path adapter
resolves old archive paths when consuming saved records; source hashes and
code/provider compatibility checks still apply. Earlier run records are unchanged.

`tests/` remains a project-level development suite. It verifies company history,
forecast construction, DCF, Excel exports, source provenance, shared FX, budgets,
provider failure/recovery and package boundaries. These checks span packages and
are not a construction stage. `probabilistic_dcf_setup.egg-info/` contains generated
installation metadata (package/dependency names and file lists); it is ignored by
Git and regenerated by installation, so it is not an editable source directory.

Folder-relocation verification: **115 focused offline tests passed in 18.124
seconds**, followed by **4 historical-resume regressions in 6.788 seconds** after
preserving the existing injected-fixture resume behaviour. Checks cover relocation,
source integrity, budgets, discovery continuity, stage workbooks and shared FX.
`doctor` passes from both the project root and the renamed package folder. Local
inventory discovers 83 Danone, 67 L'Oreal and 444 Nestle source files at the new
locations; this is discovery, not financial validation. The Unilever folder remains
empty. Both configured FX files exist. All 598 files captured before relocation
have identical post-move hashes; Windows extended-path verification also reads
four previously uncounted long-path files (602 files in total). No originals or
saved run records were edited. No paid calls, real-company builds or desktop Excel
recalculation ran; the full test suite was not repeated for this layout change.

**Stage exports: an Excel checkpoint at each construction stage.** Successful
historical research saves `historical_model.xlsx` before forecast construction.
The operating model saves `forecast_model.xlsx` before valuation research starts.
DCF saves `dcf_model.xlsx`; `model.xlsx` remains the final-output compatibility
filename. New integrated runs contain all applicable checkpoints. Earlier files
remain available if a later stage fails, and saved run records hash the artifacts
and list them under `stage_outputs`. Existing run folders are not rewritten.

The historical workbook contains supported reported/derived history, source
references, historical formulas, review status and reporting versions/bridges.
It contains no forecast or valuation sheets. Forecast exports add the operating
framework and Assumptions, and DCF exports add Valuation. Refresh/export also
produces these checkpoints using saved inputs with zero AI calls. Exported or
provisional status does not mean financial acceptance: the stage-one and
stage-two checkpoints request Excel calculation on opening, while the existing
final desktop recalculation/acceptance gates remain unchanged.

Formatting is deterministic Python using `openpyxl`. Shared fonts, colours,
number formats and sheet/table conventions are in `shared_excel.py`. Historical
layout is in `historic_construction/model_excel.py`; operating and Valuation
layout is in `forecast_construction/model_excel.py`. The model specification
supplies company rows, section labels, fiscal periods, currencies and supported
presentation overrides. No example workbook is required at runtime and no AI
call is added to format or export a workbook.

Stage-export verification: **83 focused offline tests passed in 9.293 seconds**,
covering stage order, checkpoint preservation after DCF failure, historical
formulas and package boundaries, workbook layout, valuation and saved-input
export. `doctor` passes. These are synthetic/mocked checks; no paid API calls,
real-company builds or desktop Excel recalculation ran for this change. The
full suite was not repeated for this stage-export change.

**Package-layout baseline:** The application is now
`company_initiation`. Construction runs historical research and reconstruction,
then the operating forecast framework, then valuation research and DCF, before
export. Shared root modules use the `shared_` prefix; FX lives in `forecasting_engine/shared_FX`.
This is a location/boundary refactor, not a new financial-model revision or a
claim of unattended company acceptance. No paid calls or company builds ran for
this change. Verification: the full offline run completed **772 tests in 806.151 seconds**,
with 771 passes and one stale test reference to the old evidence-file hash key.
That test path was corrected; **all 60 targeted reuse, package-boundary and DCF
checks then passed in 1.894 seconds**, including the formerly failing test.
`doctor` passes. The full suite was not repeated after this test-only correction
and two package-description docstring updates. The complete result and rerun
receipt are preserved in `outputs/archive/tests/package_layout_verification_20261025.log`.
The different-company cases are synthetic fixtures, not real-company validation.

The historical package has no imports of forecast or DCF packages. It saves a
`historical_model.json` audit projection alongside the cited
`company_model_inputs.json` passed to forecast construction. Existing accounting
research still gathers cited policy declarations with historical definitions;
forecast equations and future values are constructed only in stage 2. Stage 3
uses the evaluated operating model and the same cumulative journal and ledger.
Refresh, scenario evaluation and export retain their zero-AI paths.

The six bespoke Nestle preparation/review Python scripts under earlier `outputs`
configuration folders were deleted at the user's request. Their produced data,
workbooks, evidence and frozen run records remain. There is no company-name branch
in the active engine. Company assumptions and mappings remain input data.

Use `python -m company_initiation ...` for all commands. Existing
`[tool.research-platform]` configuration keys and the distribution name are
retained for settings compatibility. Source snapshot keys now include package
paths and cover every stage plus shared FX; strict code compatibility may reject
an old result for direct reuse. Existing charges, unresolved reservations and
saved originals are preserved, not reset by the package rename.

**Preserved pre-refactor run history follows.** References below to then-current
runs and suites describe earlier executions; this refactor has not resumed them.

**New revision in progress:** the latest request authorizes backend DCF plus actual
CLI construction of Nestle, L'Oreal and Danone using each company's raw sources.
The earlier stop on the latter two and shared $20 budget are superseded: each now
has a separate cumulative $20 allowance, with attributable prior charges and
reservations preserved. The 25 October completed output below is the baseline,
not completion of this new milestone. Record fresh/cached stages and every manual
intervention; no company-specific output patch can count as unattended success.

The new shared code implements visible portfolio/FX CFO components, a separate
estimated diluted denominator where disclosure is insufficient, continuing-profit
anti-dilution treatment, independent current/prior hedge terms, deterministic FCFF
valuation and one Valuation audit sheet. Focused valuation and export tests pass;
saved scenarios propagate into valuation without AI or Excel. An earlier full
offline suite passed **516 tests in 636.271 seconds** in
`outputs/archive/tests/unattended_full_offline_20261025_final.log`. Later source-context,
discovery, valuation-unit and date-validation fixes have focused passing tests;
the latest completed frozen full suite passed **724 tests in 906.142 seconds** in
`outputs/archive/tests/unattended_full_offline_20261025_frozen_v14.log`. Its execution receipt
records the same package hashes as Nestle attempt 18, L'Oreal attempt 20 and Danone
attempt 20 at dispatch. These tests do not establish real-company financial acceptance;
the subsequent live failures and their shared corrections are recorded below.

The current public continuations are **Nestle attempt 22, L'Oreal attempt 24 and
Danone attempt 24**, started at 18:17 UTC with identical hashes for 16 package
modules. Source/tests are frozen and full offline suite v17 is running alongside
them. The combined focused check passes **141 tests in 12.661 seconds**. Actual
Nestle preparation and scope replay preserves the saved review and targets only
four failed dispositions; full financial acceptance remains pending.
The prior cycle added no API charges: Nestle 20
stopped on an input-digest check, and the other companies stopped at the code guard.
Normal preparation had appended four saved source-selection notes; financial
observations were unchanged. The correction accepts only that exact delta from a
hash-verified selection artifact and preserves the full saved review context.
Actual N20 preparation replay passes, 88 related tests pass, and the combined
root check passes 117 tests in 8.751 seconds.

The current full suite, v17, is running against the frozen combined changes.
V16 was intentionally stopped before completion (exit -1, 435.777 seconds), so it
is not a pass. V15 is also preserved: 730 tests in 746.428 seconds, with 14
source-change-guard failures/errors after edits began. The latest completed
passing full suite remains v14 above. Start/end hashes now record code drift
explicitly for every new public execution.

Nestle 21 successfully recovered the saved version-review route. Its final scope
answer still omits Q1/9M from four structured dispositions, although the prose
discusses sales-only releases. No historical fact was reconstructed or accepted.
The shared correction now freezes valid targets and unaffected dispositions,
retains its own prior answer, and revalidates every required period. Its durable
protocol retains prior paid attempts and prevents a continuation resetting the
bounded correction allowance. Genuine primary-evidence gaps stop without
whole-answer regeneration.

Danone 23 repaired all ten invalid source-token bindings across two bounded
patches while preserving all 57 entries and unaffected bindings. It then stopped
on incompatible free-text reporting-basis labels. Separately, coverage inspection
found that the latest selection omitted an available H1 financial report and
cumulative 9M disclosure. Numeric validity does not make that reduced scope
complete. The shared coverage fix now inspects relevant primary candidates and
retains hash-verified prior cadence as obligations for current revalidation;
metadata and earlier AI claims cannot themselves establish financial facts.
L'Oreal 23 reached mapping with complete selected evidence and retained H1/9M
coverage. Its initial candidate contains 29 source-binding errors and seven
growth contributions incorrectly assigned to the monetary sales role. Four of
those ratios have valid bindings. The new shared role check identifies 33 rows
requiring correction and prevents ratios/stocks from satisfying revenue coverage;
identity corrections retain the source amount, units, type and definition. All
38 related tests pass. The saved first patch remains unaccepted after the code guard.
No current real-company run has passed the new historical and valuation gates.

A further read-only audit found a closing-share provenance defect to correct
before final acceptance: an explicitly estimated historical closing count is
currently written as a reported fact. The saved Nestle 2025 count of 2,572.2m
matches its cited original disclosure, but lacks a machine-verified observation
binding. Preserve estimates as estimates; reported closing counts and legacy
dilution claims need an exact validated observation or Python-resolved source
terms. This correction is queued while the frozen history trials and suite run;
no company value has been changed and it is not yet implemented.

Two shared corrections are now under live verification. Numeric repairs previously
received errors but not their own prior answer, causing valid rows to be
regenerated or lost. The new bounded correction identifies exact entries, freezes
unaffected facts and reporting versions, scopes missing additions and revalidates
the complete result. Blind reconstruction sees only its own prior answer. All 43
focused tests pass; D20 replay identifies 37 corrections and 84 frozen entries
with unchanged originals and zero API calls.

A verified, unconsumed historical version-repair route can now resume independent
reconstruction without repeating its completed cohort review. Exact source,
input, request, provider/model/parser and retained-allegation checks precede
replay; the complete history gate remains mandatory afterward. All 88 related
tests pass. N19 replay reproduces the exact scope signature without an API call
and preserves its rejection, with precise concept/period/reference feedback.
Independent review is clear and the combined root check passes 117 tests in
8.751 seconds after the preparation correction.

L'Oreal and Danone began from supplied VA originals and application-retrieved
public disclosures; their continuations are not wholly fresh initiations. No
company mappings, financial values or workbook outputs have been manually repaired.

The shared corrections now under live verification are:

- Exact source-token, unit, temporal-metric, row and period checks reject invalid
  mapping answers and report all independent errors in one bounded repair. A
  construction-only source adapter translates explicit fiscal periods for the
  vendor validator, including June year-ends and custom IDs. It preserves original
  cells and strict actual/estimate eligibility. The actual L'Oreal Q1 reference
  now passes unchanged; earlier failures at this boundary were application errors.
- Numeric-format guidance explains decimal/thousands conventions and separates
  source interpretation from unit scaling. The strict initiation schema is
  unchanged. The new construction mapping schema intentionally prevents exact
  cache reuse of older numeric requests. Danone attempt 19 had 16 invalid rows
  after repair. Attempt 20 under the new guidance has no locale, fiscal-slot or
  role errors, but exact source-token mismatches increase from 37 of 121 proposed
  rows to 82 of 141 in its saved repair. Those candidates remain rejected; saved
  responses are not accepted facts. Attempt 21 then saved a smaller 57-observation
  answer: read-only binding replay finds ten exact-token mismatches and no locale
  errors. The other 47 pass only that narrow binding check, not financial acceptance.
  Twenty-four focused mapping tests pass.
- Official discovery preserves complete observed-link evidence, structured HTML
  dates, original-PDF datelines, unresolved coverage obligations and deferred
  releases. Repeated continuation follows hash-bound navigation ancestry. It
  retains completed metadata over identical interrupted raw selections, while
  new claims, dates, period references or bytes require review. Twenty focused
  metadata/checkpoint tests pass; zero-AI L'Oreal replay restores the identical
  67-source catalogue and its two resolved datelines without changing originals.
- Discovery research contexts retain each distinct complete claim while keeping
  repeated restoration provenance in the raw audit. Concise selection purposes
  prevent the full obligation context from being repeated inside every limitation.
  L'Oreal's failed request shrank from 3.51 MB to 0.99 MB in offline replay with all
  389 units and 5,815 numeric indexes unchanged; no new live L'Oreal mapping has
  yet verified that request. Danone 21 used 444 units and 3,506 numeric indexes.
- Source contexts retain complete selected sections and every numeric index.
  Parsed originals are keyed by source/parser hashes. Lossless historical matrices
  retain all observations and reporting versions. Verified provider context/output
  failures allow bounded topic or period decomposition; identical capped requests
  cannot be redispatched. Changed prompts/schemas are different requests and do
  not qualify as exact cache hits. The original byte limit is 50 MiB; the separate
  500-page PDF limit remains explicit.
- Combined-history review retains substantive allegations across continuations.
  Source-present missing versions may enter independent additive reconstruction;
  missing originals or unresolved accounting interpretations cannot be waived.
  Every scope finding now needs a cited typed disposition. Proposal-only results
  preserve facts, checkpoint inputs and trigger the full gate again. Repeated
  unchanged proposals and duplicate source bindings stop. The actual Nestle
  replay retains all 12 findings, 268 original units and 1,262 observations.
  Its real restated cash-flow gaps remain unaccepted; a guessed basis label cannot
  establish that an already-saved version is absent. Eighty-one related tests pass
  and independent review is clear.
- Shared accounting extensions support cited extra expense functions, net
  adjustment accounts, ordinary equity issuance, noncommon-equity principal and
  coupons, investment movements and cash-flow overdraft scope. Structural empty
  buckets remain separate from reported zero facts and calibration. Cash coupons
  and after-tax EPS attribution remain distinct; senior equity and debt enter
  common-equity valuation once.
- Valuation research must resolve all six dated cited claim/dilution inputs
  before completion or cache reuse. Unsupported zeros and material unknown event
  dates/payment/tax block acceptance. DCF requires complete elapsed cash/stock
  bridges and the declared forecast horizon; missing statement halves cannot hide
  behind annual aggregates. Forty-seven valuation/scenario/export checks pass,
  and the populated Nestle diagnostic's cash flows, opening bridge, terminal value
  and per-share value are exactly unchanged. Its six unsupported claim inputs
  still make that old diagnostic incomplete under current gates.

The earlier combined focused run passed **113 tests in 9.009 seconds**. The latest full
fresh-entry fixtures passed in **1,146.050 seconds** using actual synthetic XLSX
source reading, compilation and export, with mocked providers/discovery/desktop
bridges. They exercise different segments, GBP, a June year-end, statement cadence
and a reporting reorganisation, plus zero-AI shared-FX refresh. These are fixture
results, not validation of another real company. The new frozen full suite and
real-company continuations remain incomplete; the latest completed full suite
and subsequent focused verification are reported above.

The 18:10 UTC budget audit reconciles **436 uniquely owned requests across 81
originating journals**, with no pending/active calls at that stopped checkpoint.
All 426 prior proofs and original journal bytes are unchanged; ten new settled
charges reconcile (two Nestle, six L'Oreal and two Danone). All 14 old unresolved
reservations and the legacy shared ledger are
preserved. Invoice-confirmed charges are zero; incurred amounts below are
usage-priced estimates, not an invoice reconciliation. Current active-call
allowances can temporarily reduce availability beyond this checkpoint.

| Company | Incurred estimate | Unresolved reserve | Remaining allowance |
|---|---:|---:|---:|
| Nestle | $7.894490025 | $5.205755625 | $6.899754350 |
| L'Oreal | $7.012676055 | $3.476854500 | $9.510469445 |
| Danone | $3.789511120 | $0.264994500 | $15.945494380 |

Request-level proof: `outputs/archive/audits/cross_company_budget_audit_20261025T181014_743430Z.json`.
The matching chronology records 67 stopped attempt logs and 39 execution receipts:
`outputs/archive/audits/cross_company_execution_audit_20261025T181026_890779Z.json`.
Earlier attempts without receipts have no invented wall-clock duration. Each new
CLI receipt records the command, start/end, exit status and package hashes.
Source changes stop a process after settling an in-flight response and before
another dispatch; only exact compatible completed work is reused. Application
costs exclude Codex development work and are independent for each company.

A preserved zero-AI diagnostic DCF at
`outputs/construct_refresh_20261025T061418Z_255cca33` passed 24,909 checks with 94
warnings and no FAIL/MISSING under its then-current gates, plus 241,753 actual
Excel cell comparisons and seven restored sensitivities. An independent 161-check
numerical audit covered DCF, dilution and procurement FX (maximum residual
3.64e-12). A normal-renderer presentation review at
`outputs/nestle_valuation_display_review_20261025T062728Z` matched all 334 valuation
targets and sampled seven actual Excel PDF pages. These are diagnostic evidence,
not completion of current historical/valuation research or unattended acceptance.

The public `evaluate` command was exercised on that diagnostic twice with zero
AI/Excel calls: `outputs/evaluate_20261025T072958_3e973d9c` changes a typed operating
pricing input; `outputs/evaluate_20261025T073024_df4d6b01` changes only the risk-free
rate. Operating changes propagate into DCF, while the valuation-only change
preserves operating outputs. All snapshots retain source-input hashes and equation
identities. `outputs/backend_scenario_cli_proof_20261025.json` records the numerical
comparisons. These are interface tests, not researched forecasts or recommendations.
The earlier completed operating-model baseline follows.

The backend construction revision is verified on Nestlé and synthetic reuse
fixtures. The [current Nestlé workbook](outputs/construct_refresh_20261025T004450Z_20b38540/model.xlsx)
contains 1,927 rows, six segments and 557 assumptions, with 2016-2025 history and
2026-2030 temporary forecasts. Company evidence is dated through 23 October; the
preserved FX snapshot is dated 24 October at 15:01 UTC. The final preserved run is
`construct_refresh_20261025T004450Z_20b38540`. Earlier runs and interrupted attempts
remain preserved. The [delivery audit](outputs/construct_refresh_20261025T004450Z_20b38540/delivery_validation.json)
records checks, limitations, costs and preserved execution issues.

The [full offline suite](outputs/archive/tests/backend_engine_delivery_tests_20261025.log)
passed **438 tests in 457.636 seconds**. After the final calendar classification
and presentation changes, 32 focused tests also passed. The final run reports 24,810 PASS,
80 WARNING and zero FAIL/MISSING checks. Microsoft Excel compared **236,622 cells
with zero differences**, passed seven sensitivity cases with inputs restored, and
passed saved-workbook layout checks. Seventeen candidate views and six final actual-Excel rendered views were sampled
across the operating build, statements and support sheets; this is not an
inspection of every cell. Small support-label clipping and source-label glyph
issues remain. Final coverage headers, calendar classifications and backend-authority labels
were checked in the last export. Excel agreement establishes implementation consistency,
not economic calibration or forecasting accuracy.

**These are temporary scenarios, not researched forecasts.** The baseline reaches
26.37% underlying trading margin and CHF7.91 adjusted EPS in FY2030. The saved
[driver bridge](outputs/construct_refresh_20261025T004450Z_20b38540/driver_bridge.json) explains the increase
from FY2025: pricing and RIG continue at their temporary historical settings while
input-cost inflation and nominal marketing/administration/research budget increases
remain zero; scope and currency assumptions also reduce expenses. No profit or
margin target is imposed, but these optimistic operating assumptions need research
before the result can be used as an investment base case.

Saved backend inputs, financial equations and validated scenario payloads are
authoritative. Excel is an inspectable projection; editing its yellow input cells
changes that workbook only. `input_contract.json` identifies each writable driver,
entity, period, unit, currency, frequency, value type and model version. Typed
payloads reject incompatible periods, units, history, formulas and read-only
calibration controls. `evaluate` recalculates a saved model without AI, Excel or
source discovery; export and refresh preserve validated overrides and the pinned
FX snapshot unless an explicit FX refresh selects a new snapshot.

The [typed scenario demonstration](outputs/evaluate_20261025T014749_2781a65a/scenario_demo.json)
changed regional pricing, an independent marketing budget and a cost-currency mix.
It passed 6,026 backend checks with 69 warnings and no FAIL/MISSING, plus eleven
independently calculated numerical effects. All 8,207 historical/derived cells,
row definitions, equations, paid-call journal and FX snapshot were preserved.
This demonstration uses the final delivered model. It produced no workbook and
made no API call. Ordinary input
changes do not renew frozen source or AI review acceptance.

The reusable financial build now includes:

- Functional cash-cost pools with one method per pool: activity and unit cost, an
  incremental budget, budget growth or an absolute budget. One effective activity
  sensitivity avoids overlapping variable-share/elasticity controls. Corporate
  costs and segment allocations reconcile to disclosed group functions; allocation
  estimates are distinct from reported facts. Marketing is an independent budget.
- Dated operating and closing events, separate control/accounting/held-for-sale
  dates, partial-period annualisation, retained-investment income and explicit
  gain/goodwill bridges. Held-for-sale assets and working capital are removed once;
  stopped depreciation is not deducted twice. Reporting reorganisations retain
  predecessor identities and are not acquisition growth.
- Separate transaction FX, functional-currency translation, cash translation,
  monetary remeasurement and foreign-balance/OCI accounting. Reported historical
  FX remains unchanged. Native observations and timestamps are preserved; crosses
  are formed daily before averaging, and missing past rates are never filled with
  current spot. Exposure coverage and uncertainty are distinct from rate coverage.
- SBC expense/addback/equity links, company-defined adjusted-earnings bridges,
  basic/diluted EPS and sourced closing shares, plus timed financing, maturities,
  refinancing and share issuance. Legal share capital is distinguished from share
  premium where supported. Financial ratios use their correct aggregate bases.

Nestlé's portfolio closing accounts and treasury exposures remain **estimated**,
not newly disclosed facts. Russia, Peranel/Waters, mainstream VMS, yfood and
Blue Bottle are represented with cited facts and explicit provisional amounts or
limits. Undisclosed gross balances, consideration allocations, retained values,
profitability and event timing require judgment. The saved
[eight portfolio alternatives](outputs/construct_refresh_20261025T004450Z_20b38540/scope_alternatives_20261025.json)
exercise earlier closing, Russia sales/profit shares and yfood valuation; all are
deterministic configuration tests, not probabilities. The record's
`financial_completeness=provisional` does not certify those estimated economics.

The [company driver map](outputs/construct_refresh_20261025T004450Z_20b38540/company_driver_map.json),
[portfolio estimates and sources](outputs/construct_refresh_20261025T004450Z_20b38540/financial_research.json)
and [writable input contract](outputs/construct_refresh_20261025T004450Z_20b38540/input_contract.json)
are preserved beside the workbook. The
source preparation under `outputs/nestle_backend_configuration_20261024/` is a
preserved research artifact, not a reusable-engine dependency. Thirteen
[targeted primary-source checks](outputs/construct_refresh_20261025T004450Z_20b38540/primary_revalidation.json)
pass on material recent history and opening balances. They do **not** recertify
the full ten-year history. Original, restated and derived observations retain
their separate identities and reporting bases; standardized VA analytics and
consensus are not substituted for company actuals. Existing source/AI reviews
remain frozen, with their earlier scope disclosed.

Nestlé uses quarterly sales/drivers, half-year financial flows and H1/FY stock
snapshots. Visible detailed columns are Q1, Q2, Q3, Q4, H1, H2 and FY for 2026-2027,
then FY only through 2030; 9M remains internal. Unsupported quarterly statements
and H2 closing stocks stay absent. These calendars, frequencies, segment identities,
currencies, disclosures and accounting policies come from company inputs.

| Currency | Selected coverage and limitation |
|---|---|
| BRL | Genuine ECB EUR crosses through 23 October; populated historical/forecast rates. The forward anchor is a dated fixing proxy, not a live IBKR BRL quote. |
| CNH | Five native broker daily bars retained but not approved for historical selection because overlap was insufficient. Frozen USD-cross spot exists; missing historical/current-period averages stay missing. CNY is separate. |
| ARS | Last selected genuine observation 25 September; stale spot and missing current-period coverage remain explicit. |
| VES | No genuine observations or eligible spot; no substitute currency is used. |

Customer-geography revenue baskets, cost translation/transaction mixes and foreign
asset/debt/cash exposures are provisional hypotheses. Unallocated portions and
scenario-neutral treatment remain explicit; a 1.00x adjustment multiplier is an
unfitted control, not evidence that exposures are accurate. The daily FX archive
starts in 2018, leaving 2016-2017 coverage absent. Provider transitions require
recorded overlap approval. The previously successful read-only TWS handshake was
not repeated during this delivery; no broker orders or account changes were made.

The public fresh-company fixtures pass using a synthetic GBP company with two
different segments, a June year-end, half-year forecast and quarterly statement
policies, and a dated predecessor split. Actual local XLSX source reading,
compilation, Python checks and workbook export run; provider responses, official
discovery and desktop Excel bridges are mocked. Separate tests cover annual
reporters, aggregate-only organic growth and estimated segment D&A. Repeated
shared-database FX refreshes make zero AI calls and preserve warning counts and
budget totals. **No second real company has been validated.** Fresh ten-year
research accuracy/cost and unattended official-site access remain unproven; the
current operating-company contract is not a universal bank/insurance model.

Before the latest 25 October authorization, L'Oréal and Danone were stopped
examples. At that earlier checkpoint, L'Oréal had $0.03760855 known charges and a
$1.25407475 unresolved reservation; Danone had no paid calls. The new trials have
since incurred further calls under separate company ledgers. Preserve the earlier
originals, records and attributable charges; the earlier stop is superseded.

The preserved former shared ledger covers the earlier work:
`outputs/construction_budget_8a61bc040e9925d621ac9562.json`. It records
**$3.238556335 known**, **$2.177916250 reserved**, $5.416472585 committed and
$14.583527415 then available under its $20 limit: 70 settled and three
unresolved requests. Reservations are not confirmed charges or an invoice ceiling.
Luna remains the initial research/review route; bounded context repairs precede
any justified narrow escalation. Ordinary evaluation, FX operations and export
remain zero-AI.

## Construct, update and export

After an editable install, the normal commands are:

```powershell
python -m company_initiation construct "Company name, ticker, exchange" --sources data_store/company_data/company
python -m company_initiation update RUN
python -m company_initiation refresh-fx RUN
python -m company_initiation export RUN
```

To evaluate a backend scenario without opening Excel or calling an AI provider:

```powershell
python -m company_initiation evaluate RUN --assumptions path/to/assumptions.json
python -m company_initiation export EVALUATION_RUN
```

Build the `financial_assumptions_v1` payload from the saved `input_contract.json`:
include company, scenario ID, as-of date, model digest and an `inputs` array. Every
entry identifies `driver_id`, `period_id`, `unit`, `currency`, `frequency`,
`value_type` and `value`. Use exact contract values; percentage-point contributions
are decimals (one point is 0.01). History, formulas and read-only structural/calibration
parameters cannot be overwritten through this interface. Writable exposure or
structural controls are explicitly listed in the contract. Each evaluation saves a
new immutable run with its payload, contract, results and validation; it does not
renew source acceptance. Exporting that run creates the optional review workbook.

`RUN` is the directory name printed by the previous command, or an absolute run
path. Construction generates new company research inputs by default; `--resume RUN`
explicitly reuses compatible saved work and its remaining allowance. Update checks current official disclosures,
adds independently reconstructed facts and rebuilds. Refresh-FX reads a new snapshot of the shared database and recalculates; export
recalculates frozen saved inputs. Both are
strictly zero-AI operations and create new preserved output folders. Keep ancestors:
continuations may share verified immutable source snapshots stored there.

`pyproject.toml` holds the shared `fx-database`, bootstrap-only `fx-source`,
non-secret broker settings and `cheap-review-repairs` default. Import once, then
update the database independently of any company:

```powershell
python -m pip install -e ".[ibkr]"
python -m company_initiation fx-import
python -m company_initiation fx-update --diagnostic --pairs EUR/USD USD/CHF USD/MXN
python -m company_initiation fx-update
python -m company_initiation fx-update-ecb
python -m company_initiation fx-status
python -m company_initiation refresh-fx RUN
python -m company_initiation export RUN
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
`-m company_initiation fx-update`. Start in: the project root. Schedule after the
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
python -m company_initiation construct "Nestlé S.A., NESN, SIX, Switzerland" --sources data_store/company_data/nestle --as-of 2026-10-23
```

From the project-root PowerShell terminal, run each company in its own terminal tab if concurrent execution is wanted.
Each invocation creates its own log automatically; no `Tee-Object` is required.
Use these company identities to retain consistent lifetime spending attribution:

```powershell
.\.venv\Scripts\python.exe -u -m company_initiation construct "Nestlé S.A., NESN, SIX, Switzerland" --sources data_store/company_data/nestle --budget-usd 20
.\.venv\Scripts\python.exe -u -m company_initiation construct "L'Oreal S.A., OR, Euronext Paris" --sources data_store/company_data/loreal --budget-usd 20
.\.venv\Scripts\python.exe -u -m company_initiation construct "Danone S.A., BN, Euronext Paris" --sources data_store/company_data/danone --budget-usd 20
```

To test only historical construction, run these instead:

```powershell
.\.venv\Scripts\python.exe -u -m company_initiation construct-history "Nestlé S.A., NESN, SIX, Switzerland" --sources data_store/company_data/nestle --budget-usd 20
.\.venv\Scripts\python.exe -u -m company_initiation construct-history "L'Oreal S.A., OR, Euronext Paris" --sources data_store/company_data/loreal --budget-usd 20
.\.venv\Scripts\python.exe -u -m company_initiation construct-history "Danone S.A., BN, Euronext Paris" --sources data_store/company_data/danone --budget-usd 20
```

Each command stops after `historical_model.xlsx` and prints its absolute path.
It creates a fresh allowance by default. Add `--resume outputs/RUN_FOLDER` to
continue saved compatible work and its remaining allowance. This is the VA-backed
construction route; the separate `initiate` command retains stricter independent
primary-document historical acceptance. No forecast/DCF options are exposed by
`construct-history`.

`Nestle` and `Nestlé` normalize to the same company budget key.
The log path is printed before construction; detailed audit files and checkpoint
workbooks stay in `outputs/`. Success uses exit code 0, incomplete/error uses 1,
and a keyboard interruption uses 130. Closing or forcibly killing the process may
leave an unfinished log; its missing end marker must not be interpreted as success.

The default is fiscal 2018 onward and five forecast years. `--start-year` changes
the first requested fiscal year; `--history-years` selects an explicit rolling
count and `--years` selects specific completed history. A command without an explicit
saved-run selection starts new research and a new allowance (default $20).
`--fresh` is a redundant alias; `--resume RUN` continues the selected run's existing
allowance. Omitted history, budget cap and as-of settings on resume retain saved
values. An explicitly changed archive or as-of date invokes compatibility/update
checks. `--historical-vintage --as-of YYYY-MM-DD`
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
reserved within their original build across continuation, migration and refresh,
and remain visible in lifetime totals after new builds. There is no routine request-count
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
data_store/company_data/nestle/
  visible_alpha/
  financial_reports/
  transcripts/
  sources.csv
```

Create categories when storing actual originals. Company originals remain Git-ignored;
synthetic test inputs live under ignored `outputs/` with explicit labels. Readable primary company evidence in
`financial_reports/` is required. Vendor exports can supply structured actuals;
they cannot independently verify themselves. Transcripts and `sources.csv` are
optional. Storing a file does not automatically send it to an AI.

The 22 October inventory accepted 439 originals: 372 financial-report files, 66 transcripts
and `visible_alpha/NESN_CH Visible Alpha.xlsx`. The index includes restatements,
accounting definitions and transaction documents. Its five `not-found` entries
concern event transcripts, not a demonstrated absence of financial statements.
Collection metadata still needs source-level verification during initiation.
Current archives now contain separate `VA Company Reported.xlsx` and
`VA Standardised.xlsx` exports for each of Nestlé, L'Oréal and Danone, plus
application-retrieved public disclosures. Use each run's hashed inventory for its
actual source set; file counts are not evidence of accepted historical coverage.
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
materials. FY2018–FY2025 is eight complete years; keep published 2026 documents
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
.\.venv\Scripts\python.exe -m company_initiation initiate "Nestlé S.A., NESN, SIX, Switzerland" --sources data_store/company_data/nestle
```

The default requests fiscal 2018 through the latest fully reported fiscal year
evidenced in the archive, including reported interims. It cannot silently omit
requested years.
For the smaller initial validation slice:

```powershell
.\.venv\Scripts\python.exe -m company_initiation initiate "Nestlé S.A., NESN, SIX, Switzerland" --sources data_store/company_data/nestle --years 2024 2025
```

Use `--start-year YYYY` for a different first year or `--history-years N`
for an explicit rolling count; these alternatives cannot be combined with `--years`.
`--forecast-years N` changes blank forecast columns; `--budget-usd` can reduce,
but cannot increase, the $20 limit.

Repeating the ordinary command starts new research with a new allowance. Use
`--resume outputs/<run-folder>` to select compatible saved progress and its remaining
budget. Explicitly resumed accepted results return without AI calls; interrupted
work continues in a new folder with paid usage carried once. `--fresh` is an optional
alias for the default. All older runs remain preserved.

A changed archive location/content/index, code, parser environment or model/effort
settings can block explicit continuation. Omit `--resume` to start a new independent
build. Preserve ancestors referenced by continuations.
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
.\.venv\Scripts\python.exe -m company_initiation doctor
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
PDF vision is implemented. Parser failures remain explicit. Limits include 50 MiB
per original, 500 PDF pages, 3,000 indexed units per document, spreadsheet dimensions of
10,000 rows/300 columns and archive checks. The twelve-document cap does not apply
to local archives. History accepts 1–30 fiscal years, default ten. Historical-only
`initiate` retains its 500-row limit; the integrated `construct` model is not subject
to that row cap. Provider context/output limits and unusual financial
structures can still prevent completion. These limits cannot justify omissions.

| Location | Purpose |
|---|---|
| `forecasting_engine/company_initiation/__main__.py` | Public CLI and ordered stage handoffs |
| `forecasting_engine/company_initiation/historic_construction/` | `evidence.py`: originals and parsing; `initiation.py`: strict historical workflow; `workflow.py`: discovery, historical reconstruction and review; `model_contract.py`: historical definitions and handoff; `periods.py`: calendars and compatible historical derivations; `model_excel.py`: historical workbook |
| `forecasting_engine/company_initiation/forecast_construction/` | `integrated.py`: operating model and schedules; `periods.py`: forecast graph/scenarios; `construction.py`: original generic construction and Excel checks; `workflow.py`: refresh/export; `model_excel.py`: workbook rendering |
| `forecasting_engine/company_initiation/dcf_construction/` | `valuation.py`: deterministic DCF; `workflow.py`: valuation evidence, assumptions and stage-3 calculation |
| `forecasting_engine/company_initiation/shared_ai.py` | Shared provider settings, API requests, token accounting and allowances |
| `forecasting_engine/company_initiation/shared_budget.py` | Shared cumulative company ledgers and unresolved reservations |
| `forecasting_engine/company_initiation/shared_runtime.py` | Shared schemas, restricted expressions, request journals, JSON persistence and runtime source identity |
| `forecasting_engine/company_initiation/shared_artifacts.py` | Shared source freezing, saved-run validation, source snapshots and checkpoint registration |
| `forecasting_engine/company_initiation/shared_excel.py` | Shared fonts, colours, number formats and sheet/table styles |
| `forecasting_engine/company_initiation/shared_project.py` | Shared checkout discovery and saved JSON loading |
| `forecasting_engine/shared_FX/` | `fx.py`: source adapter, rates and configured baskets; `fx_store.py`: shared SQLite/snapshots; `ibkr.py`: read-only TWS ingestion |
| `tests/test_package_layout.py` | Dependency direction, historical-only output and a synthetic different-company structure |
| `tests/test_setup.py` | Offline synthetic financial/provider/parser/workflow checks |
| `tests/test_construction.py` | Known-answer construction, economic-error, workbook and cost/resume cases |
| `tests/test_integrated_model.py`, `tests/test_integrated_graph.py`, `tests/test_model_sources.py` | Financial controls, exact source normalization, graph and saved-result integrity |
| `tests/test_periods.py`, `tests/test_periodic_model.py`, `tests/test_fx.py`, `tests/test_model_excel.py`, `tests/test_budget.py` | Different-company fixtures, period/FX semantics, workbook authority and cost recovery |
| `README.md`, `PROJECT_BRIEF.txt`, `AGENTS.md` | Current operation, wider ambition and standing instructions |
| `pyproject.toml`, `.gitignore` | Dependencies and exclusions |
| `data_store/company_data/<company>/` | User originals, Git-ignored; no automatic AI upload |
| `outputs/initiate_<company>_<time>_<id>/` | Frozen record, copied sources, calls and accepted workbook |

Historical `initiate` runs contain `record.json`, `calls.jsonl`, `sources/` and, only on acceptance,
`model.xlsx`. An interrupted `model.pending.xlsx` is not accepted. Preserve
ancestor folders and back up ignored research separately. A hash is provenance,
not a tamper-proof forecast ledger. Python environments/caches/build metadata are
generated support. `.git/COMMIT_EDITMSG` is Git scratch space. Old FX/demo/config
code stays removed; preserved synthetic outputs and the first Nestlé annual
reference are historical artifacts, not current inputs.

## Next milestone

The user runs fresh `construct-history` trials for Nestle, L'Oreal and Danone with
the implemented v7 path. Inspect the final historical review, eligible VA coverage,
native labels, old/new reporting blocks and their own group totals, revised-value
selection and completed versus incomplete workbook status. Record actual calls,
duration and cost rather than extrapolating from offline fixtures. Do not run paid
trials or downstream forecasts/DCF while preparing these commands. Preserve all
prior runs, frozen sources, known charges and unknown reservations.

The paragraphs below record superseded milestones; the simplified path above is
the current next step. No real company has completed this revised path yet.

The approved v5 restatement, citation, date, version-repair and context corrections
above are implemented. The next live step is the user's fresh `construct-history`
trials for Nestle, L'Oreal and Danone. Inspect both reporting-structure blocks and
their formulas, revised-value selection, full requested coverage, early semantic
review and final accounting/history review before claiming completion. Preserve
the current failed runs and costs. Offline fixtures and saved-response replays do
not establish successful autonomous history for any of the three real companies.
Do not launch paid builds or hand historical-only runs to forecasting/DCF here.
Earlier proposal/pending-implementation paragraphs below record prior discussions.

The latest user-operated retests reached usable diagnostic export, but none completed
history. Discuss the semantic mapping, period/context, reporting-version and early
coverage corrections proposed above before implementing or launching another paid
trial. Passing parser/export tests did not establish correct canonical bindings or
current-versus-legacy segment treatment. Keep these new runs and their charges.
The earlier pending-live statements below describe prior milestones.

No company has completed the revised historical stage. Both rounds of approved
mapping, parser, error-routing, export and provisional-display corrections above
are implemented and checked offline. The user-requested cleanup removed the old
local mapping checkpoints; fresh runs are next. Restoring an old checkpoint must
not bypass compatibility checks or silently reinterpret its contract. The next live
step is the user's fresh `construct-history` trials for Nestle, L'Oreal and Danone
using the commands below. Check mapping coverage, numeric representations, retained
reporting changes, source/accounting review and final versus incomplete workbook
status. Later accounting/review stages were not reached by the prior live attempts
and may expose additional gaps; offline checks do not establish successful live
history. The preparation task does not launch paid builds or downstream handoff.

The user is currently testing the historical stage only. The new public
`construct-history` command and latest-first VA mapping support that test; do not
launch full builds or automatically hand its output to forecasting or DCF during
these tests. The user runs the Nestle, L'Oreal and Danone commands above. Review
their historical outputs and saved limitations before considering the later stages.

The user subsequently authorized the VA source-priority change above, which is
implemented and checked offline. User-operated real builds are the next live
verification step. Each fresh command now receives its own allowance; explicit
continuations preserve their selected build's allowance. This change does
not authorize launching paid builds from the preparation task. Field-limited
repairs and compact journal persistence are implemented. The previously
authorized storage migration remains separate and unimplemented.
Markdown ingestion is also under discussion: compare evidence quality on a small
representative sample before deciding whether to add it as a derived source view.

The user selected an actual company/date folder migration after the active builds
finish. Keep their Python source, run paths, budget/lock paths and active logs stable
until then. Implement one shared run-location/discovery layer, remove assumptions
that a run's parent is the outputs root, and resolve earlier stored paths without
rewriting immutable evidence or bypassing hashes. New runs must use the grouped
layout too. Verify resume, ancestor/source loading and budget attribution before
moving existing runs; preserve ledger and lock identities. Completion requires
the flat run list to be physically grouped, with no navigation-link substitute.

Folder layout, package separation and stage exports are verified to the extent recorded above. The following
real-company milestone remains pending; the relocation does not resume it or
establish successful company builds.

Complete the newly authorized public-CLI builds for Nestlé, L'Oréal and Danone,
including the remaining financial corrections and deterministic backend DCF.
L'Oréal and Danone must begin from their supplied originals without manually
prepared model inputs. Preserve fiscal 2018 onward and disclosed interims, independent
source checks, cumulative build budgets and prior unresolved reservations.
Record every shared-code intervention and distinguish fresh stages from cached
responses. Final outputs must use the same code and retain specific incomplete
statuses where evidence, external access or the budget prevents completion.

After construction, challenge temporary operating and terminal assumptions using
the typed input interface and dated evidence. The forecasting agent, probability
distributions and Monte Carlo remain deferred. Numerical agreement does not
establish forecasting skill, and synthetic fixtures do not substitute for the
three requested real-company trials.

## Decisions

| Date | Status | Decision |
|---|---|---|
| 31 October 2026 | Approved simplified historical path implemented; live retest pending | v7/v20 uses VA-led scope, native rows, deterministic source/period checks and one final historical review. Remove mandatory bulk originals and early proof loops; move forward accounting/drivers/exposures/policies into forecast construction after the historical checkpoint. Keep targeted local definition context, compact schemas with Python membership/digest checks, complete VA audit values, restatement rules, material-error incompleteness, source hashes, allowances and explicit resume. No paid calls or real-company builds during implementation; offline fixtures/replays are separate evidence. |
| 31 October 2026 | Simplified historical direction agreed; walkthrough only | User endorses VA import, company-native structure/mapping, checks and historical Excel. Keep budgets/provenance, source values, periods, restatement rules and auditable completion statuses. Cut mandatory bulk PDF loading, move forecast preparation to its stage, replace repeated early proof gates with appropriately routed corrections and a focused review of assembled history. Explain current order and proposed keep/change/cut decisions before implementation; no engine changes or paid calls in this turn. |
| 31 October 2026 | v6 regressions diagnosed; scope reaffirmed, simplification proposed | The user's objective remains supplied VA to historical Excel. Latest three attempts fail after 229.759/211.840/172.937 seconds; 17 dispatches cost $0.380990475 known estimate plus a preserved $0.588573750 unknown reservation. Nestle's forced 36-source context inflates prompts and generates an out-of-limit response schema; L'Oreal's populated revenue history fails an exact-role gate then an irrelevant PDF evidence test; Danone's resolver omits an already-selected income statement. Propose a simpler VA import/mapping/check/export path with targeted semantic support and separated forecast preparation. No engine changes, paid calls or builds during diagnosis; discussion is not implementation approval. |
| 31 October 2026 | Latest-run fixes approved and implemented; VA numerical priority reaffirmed | v6 derives canonical IDs in Python, constrains physical duplicate keys/ISO dates, preserves valid versions through append/exact-version repairs, retrieves local reporting-change notes for semantics and allows cited scope-date corrections. Pending/new evidence gaps reach the bounded resolver. Supported alternate series remain auditable outside selection with early/final review and warnings; genuinely unsupported essentials stay blocked. Stable missing-row aliases fix draft export. Restated amounts remain VA cells; PDFs explain definitions/dates without table reconstruction. User launches fresh trials; no paid calls or company builds during implementation. |
| 31 October 2026 | Latest v5 trials diagnosed; targeted corrections proposed | All three remain incomplete: Nestle 616.338s/11 calls/$0.104323275, L'Oreal 371.732s/7/$0.070239400, Danone 454.737s/7/$0.064883365. Two populated incomplete workbooks; Nestle's new shared missing-row placeholder crashes export. ID/duplicate contracts, frozen-version repairs and definition/date evidence still block mapping. Danone's available local reorganisation note was omitted; L'Oreal has an unresolved alternate profit series and a retained mislabelled profit binding. Propose specific retrieval/schema/repair/semantic/export fixes, preserving source/history/acceptance gates. No engine changes, paid calls or company reruns during diagnosis. |
| 31 October 2026 | Restatement policy and latest-run corrections approved and implemented | v5 retains current and historical structures in separate ordered blocks with their own linked totals; unchanged-definition numerical revisions supersede displayed originals while preserving audit facts. Separate operational change dates from comparative applicability and publication vintage. Repair failed version sets without changing unaffected versions, constrain digests/paths, align resolver citations/questions, and remove repeated semantic context. Keep source values, years, budgets and acceptance gates. User launches paid retests; fixtures/replays do not prove real-company completion. |
| 31 October 2026 | New v4 trials diagnosed; interaction fixes proposed | Latest runs all stop in cohort 1; total 22 calls/$0.483812220 estimated, no unknown charges. Nestle resolver rejects VA row citations shown in its input; L'Oreal/Danone encounter date-coverage and version-splitting constraints the patch schema cannot express. Danone's supplied restatement note demonstrates why operational change dates cannot bound comparative applicability. Context duplication inflates repair prompts. Three diagnostic workbooks exist, with Nestle empty. Proposed contract/date/repair/context corrections remain unimplemented; no engine changes or paid calls during diagnosis. |
| 31 October 2026 | Semantic contracts and targeted Luna workflow approved and implemented | v4 separates physical row keys from typed financial roles, supplies compact verified period metadata and cited reporting context, checks dated essential coverage before detail, and adds an early semantic review plus bounded conditional evidence-resolution tasks. Repairs preserve numbers, reject contradictory basis flags and stop semantic nonprogress. Actual selection stage names receive explicit low-effort routing; financial tasks remain medium. User runs fresh trials; offline fixtures/replays do not establish live company completion. |
| 31 October 2026 | Targeted additional Luna calls discussed; proposal only | User is receptive to extra Luna spending for reliability. Recommend enriched existing scope research, an early essential-binding semantic check and conditional evidence-gap resolution after deterministic contract/context fixes. Avoid blind retries and duplicate final review; existing combined-history review was not reached. Call count alone does not establish accuracy or completion. No implementation or provider calls during discussion. |
| 31 October 2026 | Latest 15:23 retests diagnosed; semantic fixes proposed | All three have registered populated incomplete Excel drafts with passed serialization/layout checks, but no completed historical review: Nestle fails canonical annual-sales binding after 20/20 cohorts; L'Oreal fails current Dermatological Beauty revenue binding after 9/9; Danone stops in cohort 3 on five unresolved Sales bases. Total 51 Luna/medium calls, $0.288689280 recorded estimate, zero web calls or unresolved charges. Propose constrained financial roles, verified period and reporting-change context, dated segment identities, early repairable coverage and semantic-progress/coherence tests. Diagnosis only; no engine changes or paid reruns. |
| 31 October 2026 | Explicit cleanup completed | The user requested clearing outputs and logs without harming code. With no Python runs active, recycled all 204 entries inside outputs and six company-initiation logs, retaining the empty parent folders and original company data. All 42 engine/test Python hashes were unchanged. Earlier artifact references are historical; resume requires restoration and normal compatibility gates. No provider calls or builds were made. |
| 31 October 2026 | Second-round historical fixes approved and implemented; live validation pending | Add scientific-number parsing and zero-AI source preflight, compact enum-constrained source selection with bounded contract repair, deterministic-error routing, verified duplicate coverage, strict numeric serialization tolerance and discoverable failed drafts with one export attempt. The v3 mapping contract and provisional vendor display policy separate display from calibration, reporting-basis compatibility and independent acceptance; strict initiation remains unchanged. 163 focused tests plus four legacy parsing checks and 59,261 real-source numeric checks passed offline. No paid builds were launched. |
| 31 October 2026 | Latest live retests reviewed; further fixes proposed | The 14:43 runs all fail: Nestle source-ID selection, L'Oreal/Danone scientific-number parsing routed into ineffective row-ID repairs. Total 35 calls/$0.298697900 estimated, no new unknown charges. Mapping progressed to 7/9 and 9/14 cohorts with partial checkpoints, but draft exports fail exact float read-back and both Model sheets are blank because all observations are ineligible. Propose parser/preflight and typed error fixes, source-ID constraints, numeric serialization tolerances, reliable draft registration, concept-level duplicate coverage and a separate provisional vendor-history eligibility policy. No engine changes or paid calls during review. |
| 31 October 2026 | Approved VA mapping redesign implemented; live retest pending | Python owns period expansion and evidence-based units/percentage normalization; AI returns typed semantic row/version decisions. Repair requests include the candidate and bounded digest-bound changes, with frozen valid fields, complete schema validation and retained diagnostics. Enforce meaningful exclusion/coverage rules, separate targets from context, pack coherent bounded cohorts and persist incomplete Excel/progress checkpoints. Preserve explicit-only resume, original allowances/charges, fiscal 2018 coverage and reporting versions. Read-only saved-response replay and synthetic exports remain distinct from live company validation; no paid builds were run. |
| 31 October 2026 | Mapping redesign explained; awaiting implementation instruction | Recommend deterministic period/unit handling, typed role/entity choices, supplied-candidate bounded patches, clear cohort/context separation, meaningful exclusion/coverage gates and incomplete progress checkpoints, with regression replay through export. Code inspection additionally finds repair calls omit the candidate being corrected and some feedback targets expanded fields absent from the VA mapping schema. Preserve source/basis/history/budget boundaries. These remain proposals; no construction-code changes, provider calls or live reruns were made. |
| 31 October 2026 | Three live historical-only runs diagnosed; fixes proposed | All failed during VA row mapping before any historical Excel: Nestle 10m31.601s/8 calls/$0.315256750; L'Oreal 6m29.157s/7/$0.093361600; Danone 4m51.252s/6/$0.060866675. Total $0.469485025 estimated with no new unknown charges. Latest-first scope and local ingestion operated, but repairs omitted periods/rows, used incompatible unit/percent representations and changed group identity. L'Oreal also exposed accepted not-assessed exclusions. Propose deterministic expansion/units, explicit cohort scope, meaningful coverage gates and bounded patches/checkpoints; no construction-code change or paid rerun performed in this diagnosis. |
| 31 October 2026 | Historical-only construction command and latest-first VA mapping implemented | `construct-history` shares generic construction research, checks and historical Excel output, then stops before downstream imports or execution. It preserves new-run budgets, explicit resume and automatic logs. Map latest eligible reported actuals first; retain separate legacy definitions and require cited restatements/bridges for old/current compatibility. Workbook columns remain chronological. The user is testing history only; no paid builds were launched during implementation. |
| 31 October 2026 | Fresh terminal runs and independent allowances implemented | Default `construct`/`initiate` starts new research and a new allowance (default $20). Only explicit saved-run selections reuse work; `--resume RUN` preserves that build's original cap and remaining allowance, including after newer independent builds. All construction stages share one budget. Old charges, reservations, ownership and runs remain preserved. No paid build authorized or launched by this implementation task. |
| 31 October 2026 | Actual historical sequence documented; no implementation change | Explain the current VA `construct` path from CLI through historical handoff, including cache/budget/repair branches. Distinguish the early partial workbook from `research_complete`, accounting/forecast-policy research already performed inside history, and final historical source checks located at the start of the forecast module. JSON remains authoritative; no new feature or build authorized by this walkthrough. |
| 31 October 2026 | VA primary-history change implemented and checked offline | Company-reported VA provides construction numbers; AI maps rows and Python reads actual cells with source/period checks and Filings precedence. Normal VA builds stay local with explicit freshness/independent-verification limitations; PDFs support notes and definitions. Explicit update searches for newer releases without multi-year backfill. Preserve strict initiation, budgets and original runs. Fixture/real-file ingestion checks are not full real-company validation. |
| 31 October 2026 | PDF/Markdown tradeoff explained; no format migration approved | AI currently receives extracted PDF text and numeric indexes, not PDF images. Consider faithful Markdown for narrative context and structured tables for needed figures, preserving original citations and conversion provenance. Markdown quality must be tested; it is not a fix for the observed repair-contract, access or persistence failures. No conversion or application changes. |
| 31 October 2026 | Historical-source intent clarified; implementation revision under discussion | Supplied VA exports are intended to provide historical numbers without routine online historical backfilling. Current construction instead requires primary reports and performs multi-year official discovery first. Discuss VA-led local extraction, local primary verification and targeted gap/update retrieval separately; preserve provenance and explicit independent-review limitations. No code changes or new research calls. |
| 31 October 2026 | Diagnosis completed; process revisions proposed for discussion | Audit the three 25 October logs, exact saved calls and mapping repairs. New usage is 28 Luna/medium calls costing an estimated $1.68694; all attempts stop before historical export. Nestle fails on three official-site 403 responses; L'Oreal/Danone fail on protected-field changes in repairs after substantial source-binding errors. Field-limited repairs, clearer identifiers, access preflight, compact persistence and explicit validation progress are proposals, not implemented changes or authorization for new paid builds. |
| 25 October 2026 | Actual company/date migration authorized after active builds finish | Group real run directories under `outputs/companies/<company>/<YYYY-MM-DD>/<time>_<kind>_<id>/`, using the attempt's UTC creation time. User chose to wait for running builds rather than create navigation links or editor exclusions. Update generic run creation, discovery, saved-path resolution and resume/budget checks before migration; preserve original evidence. Not implemented yet. |
| 25 October 2026 | Safe output archive completed; run migration deferred | While the user's builds run, archive 207 inactive standalone diagnostics by company/tests/audits with unchanged bytes and an original-to-new path/hash index. Keep all run directories, budgets, locks, inputs and active logs at their existing paths. Grouping model runs requires compatible path/discovery changes after active builds stop. |
| 25 October 2026 | History and allowance revision implemented and checked offline | Standard history starts fiscal 2018 inclusive, replacing rolling ten years. Open a fresh $20 allowance period for each test company with active spending at zero; preserve lifetime charges and unresolved requests. Different-company commands may run concurrently; successful full-build timing remains unmeasured. |
| 25 October 2026 | User-run launch and audit requirement | User will run the three terminal builds; do not launch them during preparation. Automatically retain a separate timestamped log under `company_initiation/logs` for each construct command, with progress, artifact paths, errors and exit outcome. Keep detailed run evidence under `outputs`, logs ignored by Git and existing company budget identities intact. |
| 25 October 2026 | Folder names implemented and checked offline | Rename `src` to `forecasting_engine`, and `local_store` to `data_store`; group the four existing company archives under `company_data`. Keep shared FX separate. Preserve prior run records and cumulative budgets; resolve legacy archive paths when reading them. Project-level tests cover both packages; generated egg-info remains installation metadata. |
| 25 October 2026 | Implemented stage checkpoints | Save separate historical, operating-forecast and DCF Excel workbooks as each stage finishes. Preserve earlier checkpoints if a later stage fails and retain `model.xlsx` as the final compatibility output. Shared Python presentation rules remain company-neutral; export introduces no AI calls and does not confer financial acceptance. |
| 25 October 2026 | Confirmed package-layout change | Rename `research_platform` to `company_initiation`; run history, forecast framework and DCF in order. Historical construction cannot import downstream stages. Shared functions remain at package root with `shared_` names; FX moves to `forecasting_engine/shared_FX`. Preserve calculation behavior, company-neutral inputs, budgets and prior run evidence. Delete bespoke Nestle preparation scripts rather than retaining text copies. No paid calls or company builds for this refactor. |
| 25 October 2026 | New scope authorized; implementation and real trials in progress | Add deterministic backend DCF and complete public-CLI Nestlé, L'Oréal and Danone builds. Each company has its own cumulative $20 cap, including attributable old charges and unresolved reservations; the old shared ledger remains preserved. New-company inputs must be application-generated from raw sources. This supersedes the earlier pause on L'Oréal/Danone and DCF exclusion. No forecasting agent or probabilistic engine is authorized. |
| 25 October 2026 | Coverage and scope corrections verified locally; live continuation running | An annual-only source selection can omit available interim statements despite passing token checks. Relevant primary candidates now require examination or cited exclusion, and positive cadence survives compatible continuations as pending revalidation. Cited basis adjudication preserves accounting distinctions without exact prose matching; substantive negative findings stop outside output-repair retries. Scope repairs retain their own prior answer and freeze unaffected records; full validation remains mandatory. The combined focused check passes 141 tests. |
| 25 October 2026 | Numeric repair and exact continuation verified locally; real trials running | Whole-answer numeric repairs lacked their previous answer and could lose valid rows. Preserve the own-task response, bind corrections to exact entry identities, freeze unaffected rows and validate the complete merged answer. Blind reconstruction sees only its own previous response. A validated but unconsumed historical version-repair route should resume from exact saved evidence and response identity, with the full gate still required afterward. |
| 25 October 2026 | Runtime recovery verified; final tests pending | Long construction processes stop if application source changes. Returned responses and usage settle before stopping and exact compatible requests can be reused after restart. Final company runs and offline checks must use frozen code; no claim of acceptance from a process mixing loaded and edited source. |
| 25 October 2026 | Correction contracts verified locally; live continuations running | Report all independent numerical-mapping errors in one bounded repair while rejecting partial answers. Preserve company/historical identifiers and reject only exact known-role formatting aliases. After demonstrated review progress, permit one targeted structured-disposition correction against the exact completed context, preserving raw answers and later obligations; full financial gates still apply. Never infer references from narrative or silently repair company facts. |
| 25 October 2026 | Continuation and claim-completeness fixes verified locally | Repeated discovery continuations trace exact hash-bound navigation ancestry and keep the newest evidence state. Valuation research cannot complete or reuse a cache while a required bridge claim or dilution input is absent/unresolved; existing bounded repair handles all such gaps together. Supported dated cited estimates remain provisional, and source review still determines semantic support. |
| 25 October 2026 | Vendor period boundary corrected and verified locally | Adapt construction periods at the source-validation boundary using explicit matching FY dates. Preserve custom model IDs and unchanged legacy initiation, reject contradictory canonical IDs/dates and retain strict vendor row/actual-column eligibility. No source coordinates, company assumptions or AI request period layouts are rewritten. |
| 25 October 2026 | Scope and availability corrections verified locally | Require a cited proposal for every historical-version allegation, then rerun the full gate without waiving findings or relabelling existing facts. Preserve completed publication metadata across identical interrupted replays. DCF cannot omit an elapsed balance bridge, skip required statement periods or change the declared horizon. Construction-only numeric-format guidance clarifies source conventions; changed request schemas do not qualify as exact cache reuse. |
| 25 October 2026 | Recovery and valuation gates verified locally; real trials pending | Compatible concrete history allegations survive retries and require explicit cited disposition; mandatory source support reaches the review. A verified output-token failure permits bounded period mapping without dropping evidence, coverage or financial versions. Unknown material event timing/payment/tax makes DCF incomplete; supported cashless reorganisations and completed events already captured in opening balances remain eligible. These controls preserve charges and make no manual company-data repairs. |
| 25 October 2026 | Continuation verified locally; final trials pending | A valid version-only review may proceed directly to independent additive reconstruction, then rerun the complete gate. Verified output exhaustion can use bounded topic review. A matching completed or navigation-complete discovery checkpoint is revalidated against preserved originals and current contracts before continuing; it is not a new website check or financial acceptance. Changed user sources or metadata cannot be silently ignored, and prior obligations, dates, charges and reservations remain intact. |
| 25 October 2026 | Evidence-routing corrections tested; real trials pending | Missing-period obligations survive empty responses; cited navigation corrections can establish scope but cannot certify financial coverage. Impossible citations receive contract feedback. A recorded context failure permits one complete-section topic decomposition retaining all observations, versions and substantive findings. Identical saved oversized requests are not redispatched; unresolved reservations remain. These are shared application changes, not manual company mappings. |
| 25 October 2026 | Shared fixes verified locally; live completion pending | Blank PDF pages retain explicit indexed empty units; malformed pages still fail. Combined-history review checks required primary evidence even when a reviewer labels its absence a warning. Observed official-link recovery reaches both new-company sites; bounded discovery currently needs better handling of repeated navigation and large contexts. Interrupted requests retain reservations. No new workbook has yet passed final acceptance. |
| 25 October 2026 | Delivered and verified; economic inputs provisional | The full offline suite passes 438 tests. The final run has 24,810 PASS, 80 WARNING and no FAIL/MISSING; actual Excel compares 236,622 cells with no differences and passes seven restored sensitivities. Seventeen candidate views and six final views were sampled. Thirteen targeted source checks and eight portfolio alternatives pass; neither is full historical or forecasting acceptance. Final run: construct_refresh_20261025T004450Z_20b38540; typed scenario: evaluate_20261025T014749_2781a65a. Thirty-two focused tests passed after final metadata and label corrections. |
| 25 October 2026 | Implemented; economic assumptions remain provisional | Backend inputs and validated typed scenario payloads are authoritative; Excel is their audit projection, superseding earlier Assumptions-authoritative wording. Evaluate is deterministic and uses no AI or Excel; refresh/export preserve validated overrides and pinned snapshots. One effective activity sensitivity and one budget method per pool, dated scope/closing/HFS mechanics, linked FX accounting, SBC, adjusted/diluted EPS and financing contracts use reusable inputs. The optimistic FY2030 margin/EPS is a temporary scenario, not a forecast. |
| 25 October 2026 | Earlier checkpoint; scope and budget policy superseded above | L'Oréal and Danone were stopped examples at the earlier checkpoint. The then-shared ledger held $3.238556335 known plus $2.177916250 reserved, before the newly authorized separate-company trials. The 24 October Wi-Fi pause and its interrupted tests remain preserved. |
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
| 11 October 2026 | Storage provided; model/effort trials proposed | Created only data_store/company_data/nestle under its existing Git exclusion for the user's downloads; no automatic import/upload or AI cost. Stored reports support task-specific independent verification and definitions, without blanket inclusion in every prompt; selected documents remain whole. Verified no explicit reasoning setting exists, though all 12 responses in run 45d938bc used medium/standard: reasoning cost about $0.027 of $22.54, with input dominating. Several distinct Luna passes may be economical but require measured comparison with Sol, preserved checks and escalation beyond mere disagreement; no majority-vote equivalence claim. Explicit per-task effort settings remain proposed. No runtime/model changes or paid calls. |
| 11 October 2026 | Collection guidance proposed; no importer or downloads | Recommend three flat input categories under data_store/company_data/nestle: visible_alpha, financial_reports and transcripts, with one sources.csv generated during collection. Use fiscal-period/document-type/publication-date names, preserve original files and restatement versions, and distinguish missing documents from failed retrievals. Public collection prompt covers FY2016-FY2025 and already-published 2026 separately; official Excel tables and APM/restatement documents complement PDFs. Transcript storage does not imply automatic AI reading. Official archives inspected; no new folders/files beyond this README edit, runtime changes or paid initiation calls. |
| 11 October 2026 | Implemented and verified offline; live validation pending | User authorized local VA/company sources and ten years by default. Implemented frozen local originals/no browser, annual tasks with complete selected documents, independent company-source and coverage/structure reviews, combined-history challenge, cited basis/change ledger, period equations, actual/source-scale checks, Excel history labels, conservative pre-call allowance, stable catalogue/document messages and explicit medium reasoning. All 151 offline tests and setup doctor pass, including a complete synthetic decade with reported interims and documented-no-effect cash transitions. User archive: 438 originals/hash checks accepted; all 136 actual spreadsheets parsed. Added pinned xlrd for 38 legacy XLS originals, preserving bytes. Models unchanged; no paid run, financial mapping validation or real VA validation. |
| 11 October 2026 | Confirmed and verified offline; live financial validation pending | Prioritize the user's VA company-specific/reporting section for historical extraction, preferring Filings then independently supported VA Actuals. Recognize the repeated-header boundary after Ratios generically; record that its company-section designation comes from the user, not an explicit vendor label. Deterministically reject standardized/helper/consensus/estimated cells, missing-value dashes and wrong periods. Preload an explicit requested-year historical view with original numeric indexes and context; preserve the complete export and its consensus for a later step. This is a user-authorized exception to whole-document input for VA; company documents remain whole and blind checks remain primary-only. Actual workbook inspection verified all eligible cells in the views: 18.74 MB full numeric index versus 0.476 MB for 2024 and 2.709 MB for 2016–2025 (serialized bytes, not token or invoice savings). All 165 offline tests and doctor pass. No new maintained files/dependencies, model changes, paid calls or changes to originals. |
| 10 October 2026 | Unresolved | Measured unattended accuracy/cost and optimal model mix, additional document/sector support and later production-baseline promotion rules. |
