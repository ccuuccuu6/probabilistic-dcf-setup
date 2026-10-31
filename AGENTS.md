# Project intent

Build a reusable probabilistic fundamental forecasting and valuation system, starting with Nestlé. Python performs calculations; Excel provides an inspectable review interface. The package contains a generic AI-driven historical initiation workflow using local company originals and vendor exports, with history from fiscal 2018 onward by default; the obsolete synthetic FX demonstration and setup configs have been removed. API/model/effort settings load from private local `.env` or environment variables; live company-initiation accuracy has not been verified. Construction adds driver interfaces, executable temporary forecasts, reusable fiscal periods, reporting bridges and shared FX data. The 24 October architecture clarification makes the saved backend and validated scenario inputs authoritative; Excel Assumptions is their audit projection. The 25 October request authorizes reusable backend DCF and unattended Nestle, L'Oreal and Danone CLI builds; probabilistic driver forecasting remains deferred.

# Required project context and continuity

Read [PROJECT_BRIEF.txt](PROJECT_BRIEF.txt) as required context for the whole project, together with this file and [README.md](README.md). README contains the current state, next milestone and dated decisions; the brief contains the research cycle and architecture principles. Preserve the user's latest instructions and verify status against the workspace.

Before implementing a substantial task, explain the ultimate ambition and complete research cycle, Nestlé's role in proving reuse, the verified implementation, the next milestone's contribution, and any decisions that risk undermining the ambition. Identify the reusable and company-specific parts and the observable completion criteria.

After meaningful work, update README's current-state, next-milestone and decision sections with verification and limitations. Distinguish confirmed decisions, proposals and unresolved questions. Deliver small, complete steps without losing the wider research cycle or silently changing model structure.

Keep context current during substantive discussions too, even when no code is changed. Record material user requirements, agreed decisions, proposals, unresolved questions and changes of direction before ending the turn. Update the relevant existing document: PROJECT_BRIEF.txt for lasting ambition and architecture, README.md for status, next steps and dated decisions, and AGENTS.md for standing working instructions. Avoid duplicating the same detail across all three or recording every conversational remark. A proposed plan is not approval to implement it; preserve explicit instructions to discuss before building.

Keep the layout as clean and minimal as possible. Use these three project documents for now; keep status, roadmap and decisions in README rather than adding separate handoff files. Prefer a small number of cohesive Python modules over nested packages. Before adding any file or directory, including documentation, explain why existing locations are insufficient and create it only when the implemented step needs it. Avoid placeholder companies, unused settings, empty future directories and duplicate editable assumptions. Explain generated artifacts and preserve earlier runs. Simplicity must preserve economic correctness, evidence provenance and reuse.

# Standing collaboration requirement

The 23 October freshness/usability implementation request authorizes targeted
official-company release discovery and downloading applicable originals for the
construction/update workflow. Record an explicit as-of date, verify publication
dates separately from fiscal periods, and retain historical-vintage mode. This
does not authorize unrelated broad research or change historical-only initiation's
local-source default. Ordinary FX refresh and re-export must make zero AI calls.
Record whether official discovery was performed by the application or assisted
through another verified retrieval method. Blocked access must stop an automatic
update; it is not evidence that no release exists. Keep source-format handling,
company research configuration, financial equations and native presentation
separate. New builds must not require the Bunzl example or an earlier company's
escalation file. Test materially different structures through fresh generation,
and distinguish synthetic provider fixtures from another real-company validation.

Tell the user explicitly when a proposed step weakens this vision or is unlikely to help it work. Explain the concrete issue and propose a practical alternative. Do not silently implement a design that defeats the intended economics, auditability, or reuse.

# Design rules

- Latest simplified historical instruction, 31 October 2026: the user approved
  VA import -> company-native historical mapping -> source/period/arithmetic
  checks -> one final historical review -> JSON/Excel. This supersedes mandatory
  bulk-document loading, early core-proof/review loops and forecast preparation
  within VA historical construction. Local originals address specific unresolved
  calendar/definition/reorganisation questions; keep complete relevant statements
  and notes, with VA still owning numerical values. Preserve native labels and
  audit all imported actuals without forcing common financial meanings or marking
  unresolved facts calibration-eligible. Keep material missing/conflicting coverage
  incomplete. Forward drivers, asset schedules, exposures and policies belong in
  forecast construction after a completed historic checkpoint. Keep restatement
  rules, strict initiation, source hashes, fresh-run/explicit-resume semantics,
  durable budgets and unknown reservations. User launches real builds; this task
  authorizes offline verification only, not paid calls or company builds.

- Latest VA-restatement clarification, 31 October 2026: original and revised/restated
  model amounts come directly from eligible company-reported VA cells. Local PDFs
  establish definitions, affected entities and comparative applicability; do not
  re-extract their restated tables or require a numeric bridge merely to use an
  explicitly evidenced restated VA presentation. Catalogue hints may route local
  reporting-change notes to actual content inspection, without treating filenames
  as proof. Python owns canonical IDs, physical-row duplicate references and safe
  version merges. Retain unresolved alternate series and cells outside selection
  only when supported essential coverage exists, expose them to semantic/final
  review and workbook warnings, and keep genuinely missing/conflicting essentials
  blocked. Historical-only testing and strict initiation boundaries remain intact.

- Latest restatement instruction, 31 October 2026: redefined business groups or
  regions retain distinct current and historical identities. Display the complete
  current structure above the complete historical structure, each with totals linked
  only to its own constituent rows. Published restated comparatives may precede the
  operational change date. A numerical revision without a definition change replaces
  the earlier displayed value within the same identity; retain superseded source
  observations for audit. Keep publication vintage, operational dates and financial
  applicability separate. Unknown or conflicting versions remain unresolved. These
  rules belong in reusable mapping, selection and Excel construction, with cited
  company structures supplied as run data. Preserve valid versions during bounded
  repairs; accept only citations actually supplied to each task. User launches paid
  trials; this implementation authorizes offline verification only.

- Latest semantic mapping revision, 31 October 2026: the user approved the known
  semantic-contract fixes and targeted additional Luna work. Source row keys and
  typed financial roles must remain distinct. Supply deduplicated verified period
  metadata, explicit vendor navigation/metric roles and cited reporting declarations
  to mapping. Dated primary hierarchies determine historical coverage; do not force
  today's structure into earlier periods or invent reporting bridges. Check essential
  bindings before remaining detail, then run an early semantic review. Conditional
  evidence-resolution tasks use selected original sections, remain bounded within
  the original allowance and may conclude unresolved. Stop prose-only repairs and
  contradictory basis flags. Keep final combined-history review, strict initiation,
  source-number checks and provisional/independent-acceptance boundaries. Versioned
  contracts reject incompatible saved mappings. User launches paid trials; offline
  saved-response replay and fresh synthetic generation are not real-company validation.

- Latest historical display clarification, 31 October 2026: the user approved
  provisional display of source-checked company-reported VA facts with clear
  financial definitions and period bases even when original/restated provenance
  is unknown. Keep source arithmetic, definition, period basis, provenance,
  publication vintage, independent verification and calibration eligibility as
  separate dimensions. Never mark every vendor fact eligible or derive compatible
  history from unresolved bases. Exclude vendor-normalized/ambiguous facts from
  this policy; conflicts remain failures. Label provisional/incomplete workbooks
  clearly and retain strict `initiate` acceptance. Use the current versioned mapping
  contract and reject incompatible reuse. Fix deterministic parsing/code failures
  in Python rather than asking AI to rename financial rows. Preserve finite source
  numbers and exact citations; permit only serialization-level numeric export
  differences, with exact formulas and structure. Register failed drafts and their
  diagnostics once. User runs the paid retests; offline replays are not live validation.

- Latest VA mapping implementation, 31 October 2026: the user approved the seven
  reliability corrections after the three live failures. Keep source-format unit
  and percent conventions in the evidence adapter, semantic row/version decisions
  in historical research and hash-bound permitted-field patch orchestration in the
  shared runtime. Python expands eligible periods; version intervals require cited
  coverage, not guessed historical relabelling. Not-assessed work is pending and
  financial amounts cannot disappear as presentation diagnostics. Preserve source,
  cadence, basis, coverage, budget and final-review gates. Save compatible validated
  cohorts and clearly incomplete historical Excel on failure, printing its path.
  Reject incompatible saved mapping contracts visibly. Distinguish local archived
  response replay, synthetic fixtures and new live validation. User launches retests;
  implementation does not authorize paid calls or a forecast/DCF handoff.

- Latest stage-testing instruction, 31 October 2026: the user currently wants
  historical construction only. Use `construct-history` for the VA-backed stage;
  do not hand it automatically to forecast or DCF construction. Keep the separate
  stricter `initiate` route. Historical finalization must verify source/date and
  historical derivation checks and export a provisional Excel plus audit record,
  without downstream imports or calculations. VA research starts with the latest
  eligible actual periods and current definitions, then works backwards. Preserve
  older segment identities and use current structures historically only where cited
  restatements/bridges support them; keep workbook columns chronological and history
  from 2018 by default. User launches the three company tests; do not run paid builds.

- Latest run/budget policy, 31 October 2026: an ordinary terminal `construct` or
  `construct-history` or `initiate` command starts new research in a new run with an independent allowance
  (default $20). The user authorizes this default; `--fresh` is a redundant alias.
  Reuse earlier work only when the command explicitly selects it with `--resume RUN`
  or saved `--model-inputs`; explicit update/export commands already name their run.
  All stages and retries within one construction share one allowance. Resume uses
  the selected build's original cap and remaining allowance, even after newer fresh
  builds; it must not open another budget. Retain earlier charges, unknown reservations,
  ownership and frozen runs as lifetime evidence. This supersedes automatic resume
  and the former company-wide allowance across independent terminal builds. Do not
  launch paid builds while implementing or testing this policy.

- Latest historical source priority, 31 October 2026: construction uses supplied
  company-reported Visible Alpha spreadsheets as the primary numerical history.
  AI maps row meanings and reporting versions; Python reads exact eligible actual
  cells, preferring populated Filings on the same row/period to VA Actuals. Exclude
  standardized datasets, consensus, estimates and analytics helpers from primary
  inputs. Preserve cell citations, alternate supplied series, missing values and
  original bytes. Normal VA construction and local refresh must not require
  online historical discovery or full PDF numeric reconstruction. Local company
  documents support accounting definitions, reorganisations and missing policies.
  Mark independent primary verification and online freshness as unperformed; do
  not call vendor history independently verified or point-in-time evidence. Keep
  material ambiguities incomplete. Explicit `update` may discover newer originals
  without rebuilding the supplied historical archive. Historical-only `initiate`
  retains its stricter company-original reconstruction and acceptance requirements.

- Latest history and allowance instruction, 25 October 2026: standard history
  starts at fiscal 2018 inclusive and extends through the latest evidenced completed
  fiscal year, with reported current interims. This supersedes the rolling ten-year
  default; explicit year selections remain supported. Retain earlier source facts
  when needed for opening balances/comparatives without silently restoring older
  requested model years. The user explicitly authorized a fresh $20 allowance with
  zero current-period spending for Nestle, L'Oreal and Danone. Keep old charges,
  unknown reservations and ownership records as historical/lifetime evidence;
  resetting the allowance is not a provider refund or permission to erase them.
  The 31 October default-run policy now authorizes independent terminal allowances;
  retries within a build cannot reset its allowance. User launches the builds;
  do not run paid builds while preparing these changes.

- Storage layout, 25 October 2026: Python packages live in `forecasting_engine/`.
  Company originals live in `data_store/company_data/<company>/`; shared FX and
  reference workbooks remain directly under `data_store/`. Keep data ignored by
  Git, preserve saved run records, and resolve legacy storage paths when reading
  them without bypassing evidence hashes or code/provider compatibility gates.

- Package layout, 25 October 2026: `forecasting_engine/company_initiation` owns three ordered
  stages: `historic_construction`, `forecast_construction`, `dcf_construction`.
  Historical construction must not import either downstream stage. Pass cited
  company inputs and stage results forward. Shared root files use the `shared_`
  prefix; FX modules live in `forecasting_engine/shared_FX`. Keep financial behavior unchanged
  during relocation and keep company-specific preparation code out of the engine.
  The user requested deletion of the six old Nestle preparation scripts; preserve
  their produced data and prior run records, not executable/text script copies.

- Stage exports, 25 October 2026: save a separate Excel checkpoint at the end
  of historical construction, forecast construction and DCF construction, before
  beginning the next stage. Preserve earlier checkpoints on later-stage failure.
  Keep shared presentation in clearly named shared Python code, history free of
  downstream imports, and file export distinct from financial acceptance.

- Latest architecture clarification, 24 October 2026: the saved backend owns the
  financial model and typed, dated scenario inputs. Excel is a formula-auditable
  projection; workbook edits do not silently change backend inputs. Preserve
  compatible validated overrides on refresh and reject incompatible ones visibly.
  Separate reported facts, deterministic history, estimated baselines, structural
  parameters, forecast assumptions, policy controls and results. Never calibrate
  against allocated estimates as independent reported observations.
- Latest scope and budget instruction, 25 October 2026: complete the remaining CFO,
  dilution and hedge-comparator corrections; add a reusable deterministic backend
  DCF; and run Nestle, L'Oreal and Danone through the public construction CLI.
  The user supplied the latter companies' VA files and explicitly authorized these
  builds, superseding the 24 October stop. Fresh L'Oreal/Danone construction must
  use raw sources and application-generated configuration, without Codex-written
  mappings, intermediate company scripts or output patches. Record interventions
  and distinguish genuinely fresh stages from cached/resumed stages. Preserve the requested
  years and reported interims; do not shrink coverage to pass.
- Each construction build has its own cumulative $20 API cap. Attribute existing charges and
  unresolved reservations using saved request evidence, count each once, preserve
  legacy records and enforce each allowance before dispatch. Shared work must be
  allocated consistently once overall; unused company budgets cannot subsidise
  another. Preserve unknown reservations. The earlier shared-budget instruction is
  superseded, not permission to discard paid work or release uncertain charges.
- DCF consumes the existing operating model, typed valuation assumptions and dated
  market/balance inputs without Excel or LLM evaluation. Use explicit unlevered
  operating cash flows, one coherent lease convention, retained SBC economics,
  valuation-date stub and cash/debt/share bridges, dated portfolio consideration
  and proceeds, sustainable terminal reinvestment, and an enterprise/equity bridge
  without double counting associates, NCI or future cash. Mark provisional inputs.
  Export one auditable Valuation sheet; all sensitivities use the same backend.
  A forecasting agent, Monte Carlo, options valuation and trading remain deferred.
- Construction must estimate material announced/completed portfolio consequences
  with primary evidence, explicit methods and uncertainty alternatives. Distinguish
  control dates, held-for-sale dates and depreciation cessation, and maintain
  accounting counterparts without balancing plugs. Keep one company-specific
  primary consolidation hierarchy. Continue clearly distinguishing synthetic tests
  from completed real-company unattended builds.

- Latest financial correction, 24 October 2026: functional cash-cost pools must causally determine profit. Forecast marketing from independent spending/activity budgets and COGS from activity, fixed costs and unit inputs, never from sales ratios or a predetermined margin. RIG is a labelled activity proxy with an explicit elasticity, not physical volume. Regional scope events carry effective dates, one-time annualisation and separate accounting bridges. Distinguish functional-currency translation, invoice-currency transaction effects, cash currency movements, debt remeasurement and net-asset OCI; missing exposure is a limitation, never a balancing plug. Repurchases require an execution price only when active and weighted shares reflect timing. Dividend policy and payment schedules are separate; recurring adjustments cannot disappear silently.
- Forecast detail is configured relative to the as-of fiscal year (current and next fiscal years by default); later company forecasts run directly at FY frequency without synthetic hidden interims. Preserve historical cumulative observations internally, but export no 9M columns on Model or Assumptions. Validate saved Excel visibility and opening views. Economic driver contracts distinguish spending/activity inputs, allocation estimates and presentation diagnostics; detailed exposure controls belong in support matrices. Validate independent financial behaviour as well as Python/Excel agreement, using another fiscal calendar and reporting cadence without claiming a second real-company validation.
- Latest correction, 24 October 2026: use the shared local SQLite FX store, with idempotent imports, immutable snapshots, provider overlap checks and read-only local IBKR ingestion. Routine ingestion, spot-held projections and company refresh/export make zero LLM calls. Preserve native quotes, original dates on carried values and projected status; never fill missing past observations with current spot. Build daily crosses before averaging, extend the complete forecast horizon, and distinguish averages from closing rates. Company revenue and cost baskets, explicit proxy currencies, supported geographic estimates and calibration multipliers belong in cited run inputs; default multipliers are 1.0, not fitted ratios. Model retains compact outputs; FX holds detailed matrices and Assumptions owns editable weights/multipliers. No orders, credentials in artifacts, subscriptions or account-setting changes.
- Reporting policy, 24 October 2026: visible Model/Assumptions order is Q1, Q2, Q3, Q4, H1, H2, FY, with darker FY columns; keep 9M internally. Nestlé uses quarterly sales/disclosed drivers, direct H1/H2/FY profit and cash flow, and H1/FY stock snapshots with blank H2 balances. Remove unsupported quarterly calculations and assumptions. Preserve genuine quarterly statements for other companies. Use explicit company-reported/standardized VA file roles or labelled combined sections, never a fixed bottom-of-sheet rule. Standardized data is a secondary comparison, never an implicit missing-primary substitute. Preserve exact statutory/underlying definitions and adjusted-to-statutory bridges. Synthetic fixtures are not another real-company validation.
- Latest period/FX correction, 23 October 2026: Assumptions owns editable forecast values and formulas; Model driver boxes are linked displays with navigation. Period construction must preserve Q1/Q2/H1/Q3/Q4/H2/FY and cumulative 9M, explicit fiscal dates, actual/derived/forecast status and basis compatibility. Derive only compatible flows; alias closing stocks by date, weight shares and recompute ratios/EPS. Preserve current-year actuals and build remaining forecasts at the configured frequency. Keep current and legacy segment identities, cited numerical reporting bridges and predecessor research context separate. Use the local FX workbook as a shared factor source with code/date lookup, publication-date weighting and original actual/estimate status; never invent company exposures or closing rates. Company periods, currency, segment mappings and economic policy overrides belong in inputs. A structurally different fixture must exercise the same compiler; fixture success is not a second real-company validation.
- Latest correction, 23 October 2026: `construct` must produce a real, segment-driven, integrated company model, with Bunzl used only as a structure/presentation reference. A flat historical draft or synthetic forecast is insufficient. Retain the requested historical years, disclosed interims and reporting versions. Segment sales/profit must drive group forecasts; link all three statements, working capital, assets, financing, tax, equity and shares. Use one authoritative editable control per assumption on Assumptions, with linked boxes beside its Model calculation, and populate driver/dependency registers. Temporary assumptions must have a stated initialization and economic interpretation. Probabilistic models and trading remain deferred; the 25 October instruction above now authorizes deterministic DCF.
- For each company construction attempt the user authorizes $20 cumulatively, including its previous known charges and conservative reservations for unknown charges. A reserved unknown request does not prohibit later work when total commitments fit. Preserve one durable ledger across retries, folders, settings changes and migrations; settle each request once, retain unknown results and try provider retrieval only with genuine provider identifiers. Reserve bounded input/output/reasoning/tool/retry costs before dispatch. This supersedes the unknown-charge hard stop below for `construct`; historical-only `initiate` retains its older policy.
- Construction now retrieves relevant original tables, complete sections and notes with surrounding context, expanding when needed. Parse/index once and reuse saved work. Coherent segment/statement/schedule tasks replace repeated entire-report prompts and exhaustive blind-first gating. Preserve originals and numeric citations; targeted review is not semantic proof or a claim of statistically independent errors. The whole-document rules below continue to describe historical-only `initiate`.
- Start construction with Luna, fix context and decomposition first, and escalate a narrow financial failure when cheaper attempts are inadequate and the cumulative budget allows. Do not make supplier comparison an artificial prerequisite for completing the real model. Bounded request/retry limits should lead to useful decomposition, not abandonment of a recoverable task.
- Accept the actual workbook only after source/period/basis checks, independent financial controls, integrated reconciliations, meaningful sensitivities, desktop Excel recalculation and visible layout inspection. Restore inputs after sensitivity tests. Unresolved material errors remain incomplete; repeat ordinary continuations without asking for approval. Company mappings and reporting hierarchies belong in generated run data, never bespoke exported-cell patches.
- Latest scope update, 22 October 2026: build `construct` from local originals through supported historics, sourced/provisional drivers, explicit forecasting formulas, editable temporary assumptions, executable forecasts, validation and a professional `.xlsx`. This supersedes earlier prohibitions on assumptions/forecast calculations for this milestone. Keep strict historical `initiate` available with its existing acceptance gates. A partial construction workbook is explicitly provisional and does not confer historical acceptance.
- Start every construction stage with `gpt-6-luna`; use low reasoning for narrow selection/mapping and medium for financial structure, drivers, formulas and review. Evaluate settings. Before a stronger narrow route, record the failure, input/instruction fixes, bounded precise repairs and actual Luna trial results on the failing cases. Repeated appropriate medium-effort failures do not require an artificial low-effort trial. No silent Sol fallback or required supplier comparison. Supplier shortlist: OpenAI, Anthropic, Google; OpenAI-only implementation is acceptable.
- Keep driver interfaces (ID, entity, period, units, scale, scenario, value, provenance) independent of future forecasting models. Temporary inputs must stay editable in the assumptions layer, missing distinct from zero. One restricted financial expression representation must generate Python calculations and Excel formulas. No unsupported coefficients, Monte Carlo or probabilities; deterministic DCF follows the 25 October scope above.
- Construction may export supported partial models with precise missing-data reports when disclosures are absent. Preserve separate data/reconciliation, source-review, economic-behaviour and framework-completeness statuses. Do not weaken strict initiation acceptance or describe provisional construction history as accepted.
- Construction now has configurable call, repair, generated-token and monetary limits, superseding the prior no-call-ceiling instruction for this command. Retain the cumulative $20 maximum, conservative pre-dispatch allowance, unknown-charge stop and durable call journals. Provider retries are zero by default; technical failures are separate from financial failures.

- Work step by step. The user's latest instruction explicitly authorizes AI APIs and bounded research/review/revision for historical initiation. Keep that workflow local; schedulers, databases, cloud services and broader orchestration still require a concrete need.
- Current scope is reusable historical initiation from a company query and local source archive: establish identity/reporting structure from supplied originals, extract and reconcile history, and prepare blank forecasts/accounting links. The user authorized local Visible Alpha/company documents in place of wide browser discovery, with fiscal 2018 onward by default. Do not silently restore browser fallback. Company-specific mappings must emerge as cited run data, not bespoke extractors or prerequisite configs. For the historical-only `initiate` command, do not implement assumptions, distributions, forecast calculations or DCF, or require a user-completed model and describe it as pulling the numbers.
- Preserve unchanged local originals and a hashed inventory, including optional sources.csv. Metadata and filenames are hints, not verified company evidence. Distinguish actuals from estimates and original from restated/vendor-normalized history; current exports do not prove point-in-time availability. Python reads saved spreadsheet values and does not run vendor add-ins. Missing caches, unreadable required sources and insufficient archive coverage cannot be silently waived. Blind numeric reconstruction must use primary company financial_reports, not the same vendor export.
- Prefer company-specific/reported VA historical tables, with eligible Filings cells before VA Actuals on a compatible verified basis. The upper standardized tables through Ratios and vendor analytics helpers are excluded as model inputs. Recognize the vendor template generically, record the user's section designation and parser evidence, and reject unsupported layouts rather than guessing company mappings. Python must enforce row/column eligibility and fiscal-period matching even when AI labels a cell actual. VA Actuals can include inferred quarters; company sources remain necessary for independent support. Preserve consensus and its original context for later work, without filling current forecast columns or treating consensus as our own forecast.
- Give reporting changes across the requested history explicit treatment: per-period bases, dated cited change ledger, versioned segment identities, and period-specific equations/calculated compositions. Preserve original segment labels and distinguish changed definitions through row identities/bases. Use published restatements or visible comparability breaks; never fabricate old results on today's regional structure. Require documented bridges for mixed bases, including cited no-effect treatment where a change genuinely leaves cash unchanged. Multi-year runs need a separate combined-history challenge in addition to annual source/coverage/structure reviews.
- Include reported quarterly, half-year and cumulative nine-month disclosures alongside annuals for selected fiscal years. Require explicit period dates and cited disclosure coverage; distinguish stocks, flows, averages and ratios. Do not silently omit interims, treat cumulative figures as standalone quarters, fill missing facts with zero, or invent full quarterly statements from sales-only releases. Cross-period derivations require a separate explicit implementation and compatible reporting bases.
- Run the configured workflow without routine human checkpoints. AI proposes references and accounting relationships; Python reads source numbers and performs calculations. Require complete source and financial-structure reviews, preserve challenges/revisions, and enforce budgets. Missing evidence, unsupported formats and unresolved checks terminate as incomplete, never as approved history. AI agreement and balanced statements do not prove accuracy or completeness; never promise zero errors. Test API behavior with mocks before paid runs, and distinguish those tests from live-provider validation.
- Preserve independent check contexts: blind source reconstruction receives concepts and periods, not candidate values/citations/interpretations or prior verdicts; record its facts before semantic comparison. Record an evidence-first coverage inventory before revealing candidate rows, and withhold other verdicts from structural review. Require review-local original context, retain disagreements, and rerun gates after revisions within the monetary budget. Distinguish independent source support from identities that balance by construction; shared models/parsers still prevent a claim of statistically independent errors.
- Read whole selected company documents for extraction and each independent review, retaining all extracted text and numeric indexes in that context's subsequent calls. The user-authorized VA historical input view is an explicit exception: Python selects company metric rows and requested-year actual/filing columns, retaining headings, notes, units, legends, missing markers and original cell/token indexes. Exclude standardized tables, forecast values and vendor helper calculations from that task's input while preserving the complete original. Do not reintroduce arbitrary page batching or application character caps; keep provider/parser limits and failures explicit, without silent truncation or claims that extracted text includes rendered visual context.
- Annual task scopes may use separate document contexts to control cost; they still read complete selected documents, preserve all saved evidence and merge through cross-year checks. Keep stable document messages before changing feedback for possible cache reuse; do not claim unmeasured cache savings or ten-year affordability. Archived transcripts are not automatic AI inputs. The 22 October Luna-first policy supersedes the prior Sol-only/medium defaults; keep explicit per-stage settings and measured comparisons.
- Use the user's $20 cumulative estimated-cost stop, with no routine request/draft-count ceiling on the normal route. Keep targeted repairs and technical retries bounded. Count every stage and charged failed call; stop on unknown costs or no progress. Construction preserves earlier unresolved requests as conservative reserved commitments, without calling those allowances actual charges. Report whole-run and per-stage tokens/costs during execution and in saved results. Disclose that the final in-flight request can overshoot because usage arrives afterward. Do not silently change models; only move demonstrably low-stakes work to a cheaper model with adequate evidence.
- Check a conservative local cost allowance before dispatching new OpenAI requests; do not count allowances as charged usage or promise an exact invoice ceiling. Preserve the post-response stop and unknown-charge guard. Resume compatibility includes the local archive/index, model/effort settings and request layout; a source-mode migration or changed folder must not silently create a new budget.
- Resume only an explicitly selected compatible initiation, reusing completed AI work without new calls; a default terminal command starts new research. Preserve parent runs and original evidence, reconstruct isolated review contexts, and carry paid usage once across explicit continuations under the original budget. Require exact request/code/provider/parser/source compatibility; never silently restart incompatible or damaged progress. Legacy runs require a new build when they cannot be safely continued.
- Persist pending-call identity before dispatch and durably save responses and usage. An interrupted request with no saved response has an unknown charge and must block further spending; do not assume a zero cost or invent recovery. Prevent concurrent initiations from branching the budget. Distinguish recovery of completed work from retrieval of a lost provider response, which is not implemented.
- Show a live elapsed-time counter for every AI call in an interactive terminal; record each call's duration and print a final duration on success or failure. Redirected output should stay readable. This is elapsed time, not a completion estimate, and must not create background AI calls or retries.
- Keep Excel close to a conventional financial model: generated formulas for derived rows, source inputs, linked historical/forecast arithmetic checks and readable year columns. Historical-only `initiate` keeps blank forecasts; `construct` links editable temporary assumptions to executable forecasts. Generate equations from the same definitions Python uses. Workbook edits do not update saved Python inputs or renew source/AI acceptance; distinguish live arithmetic from frozen reviews.
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

The first Nestlé reference used 2024–2025 annual history. Its originals, workbook and historical code snapshot remain in the preserved run. The user has now authorized storing the supplied API credential and trying API access/token measurement; model selections are provisional. Keep offline tests credential-free and use a small explicit `api-check` for connection/usage verification. Do not claim a connection test proves live autonomous research accuracy. Preserve earlier runs, including failed attempts. Construction now includes the temporary executable forecasts authorized on 22 October and the deterministic backend DCF authorized on 25 October. Probabilistic forecasting models, distributions, Monte Carlo and the future forecasting agent remain deferred.

From the project root after an editable install:

```text
python -m company_initiation doctor
python -m unittest discover -s tests -v
```

After configuring settings and collecting originals, `initiate "Nestlé S.A., NESN, SIX, Switzerland" --sources data_store/company_data/nestle` requests fiscal 2018 onward and reported interims. Add `--years 2024 2025` for a smaller validation slice. The generic local `--sources` folder option does not restore the former Nestlé-specific extractor. Default terminal commands start a new run and allowance; `--fresh` is an alias. `--resume RUN` explicitly selects compatible saved work and its existing budget. Compatible interrupted runs continue in a new folder; explicitly resumed accepted results return without AI. Preserve linked ancestors and earlier browser attempts. Another company uses the same function with its own archive. New research uses paid AI calls and is not part of the offline suite. Do not restore unused demos or prerequisite configs. Keep checks focused on financial identities, exact source extraction, history changes, review gates, resumability and reproducibility. State live-validation and parser/context limitations rather than implying the full platform is ready.
