# Shared research and company models

This describes the intended architecture. Only the setup checks and synthetic FX demonstration are implemented in this starter.

## The organizing rule

Store a piece of evidence once. Interpret it at the shared economic-factor level where appropriate. Apply it to each company through explicit, company-specific relationships.

Coffee research may influence both Nestlé and Keurig Dr Pepper. It should not become a copied report in two folders, two independent readings of the same release, or the same automatic change to both companies' margins.

FX is another shared factor. The shared input is a currency observation or scenario path. The company-specific output might be a revenue-translation adjustment, an input-cost change or a debt revaluation. Those are different effects.

## Keep five kinds of record separate

| Record | Example | Proposed home |
|---|---|---|
| Original source | Coffee crop report, results PDF, FX provider response | Local original-file store, later object storage |
| Extracted fact | Dated coffee price, a management statement with its source passage | Local SQLite, later PostgreSQL |
| Shared factor forecast | Versioned joint coffee/FX assumptions and their evidence | Versioned assumption records |
| Company transmission | Procurement lag, invoicing currency, hedge schedule, exposure estimate | Company-linked, versioned records |
| Model run | Frozen inputs, samples, financial outputs and checks | Run manifest plus files/arrays |

Small structural definitions belong in Git-managed configuration. Rapidly changing data and assumption versions belong in the data store. Do not turn each new observation into a manual edit to the Python financial equations.

Local SQLite is a proposed next-stage metadata store, not an implemented part of this ZIP. It is appropriate for the initial single-machine workflow. Before running concurrent production workers, implement a shared database with migrations, transactions, concurrency controls and backup. Storage access should go through the `data` module, rather than be scattered through company models.

## How uncertainty will be represented

There are three different objects:

1. **Observed data:** what a source measured or said, with units, dates and provenance.
2. **A distribution specification:** the model family, parameters, time dependencies, evidence and version that define possible futures.
3. **Generated numerical paths:** the actual sampled values used for a particular run.

For large runs, a shared FX array could be indexed as `fx[scenario, period, currency]`. Company volume or pricing arrays can have additional segment dimensions. The financial model receives numerical arrays and performs arithmetic; it does not call an AI model once per scenario.

Give every shared simulation run a stable ID and preserve its actual samples. Within that run, scenario 428 must refer to the same joint FX, coffee and macro future wherever it is consumed. Scenario numbers from two independently generated runs are not automatically comparable. Company-specific residual risks can be sampled conditionally on the shared state.

Reusing a seed alone is insufficient if the code, number of draws, random generator or ordering changes. Record samples, input/version references and the seed; preserve code and environment versions.

## FX conventions and economic transmission

Store explicit `base_currency`, `quote_currency` and `quote_per_base`. If base is USD, quote is CHF and the rate is 0.90, then 1 USD buys 0.90 CHF. Never use an unlabeled column called only `FX`.

For coherent synthetic scenarios, define `q_C` as units of currency C per 1 USD. Then units of currency B per 1 A equal `q_B / q_A`. This gives reciprocal and triangular consistency by construction. Choosing USD as a computational reference does not change any company's reporting currency.

For example, if 1 USD = 0.90 CHF and 1 USD = 0.80 EUR, then 1 EUR = 1.125 CHF. These are illustrative numbers, not observed market rates.

Observed quotes need compatible timestamps and quote conventions. Keep the originals and flag conflicts; do not silently alter source data to make it reconcile. Derive cross rates at each common observation time and then aggregate as appropriate: a ratio of two period-average rates is generally not the same as the average of their daily cross rates.

Company mappings need distinct treatment for:

- **Translation:** converting foreign financial results into the reporting currency.
- **Transaction exposure:** differences between a business's revenue, purchase and functional currencies.
- **Hedging:** contract amounts, currencies, periods and rates, including incomplete disclosure.
- **Timing:** procurement contracts, inventory lags and the delay before pricing changes reach customers.
- **Balance-sheet claims:** debt and other amounts whose currency treatment differs from revenue translation.

Use period-average rates only where they are an appropriate approximation for the relevant flows; retain closing rates separately for balance-sheet conversion and explicitly dated rates for a present valuation conversion. Reconcile against the company's disclosed FX bridge. Currency and cash-flow discounting must follow a consistent valuation policy.

A USD-denominated coffee price and exchange rates may both affect local input costs. Convert the commodity price into the relevant purchase/functional currency once, apply contract and inventory timing, then translate the resulting financial statements appropriately. Do not add the same currency effect again as a generic cost surcharge. Commodity types, grades and contract maturities also need distinct definitions; there is no universal undifferentiated coffee price.

The first FX demo intentionally stops at consistent currency levels and simple translation arithmetic. It does not implement these operating, hedging or accounting schedules, or a credible joint distribution.

## How frequent updates should work

The future update workflow is:

1. Ingest a source, preserving its publication time, receipt time, provider and content hash.
2. Extract and validate facts once, retaining exact passages and definitions for qualitative statements.
3. Link repeated reports of the same underlying event so they do not count as independent evidence.
4. Identify which factors and company assumptions depend on those facts.
5. Propose a versioned update, explaining the mechanism and limitations.
6. Apply an approved update rule, calculate affected outputs, run checks and save a new immutable run.
7. Advance the current-result pointer only if the run used the expected current input versions. An older job must not replace newer results.

Publication time and receipt time serve different purposes. Missing publication times should remain explicitly unknown. Revisions must preserve the previous value and availability history, rather than overwrite it.

Separate three frequencies: collecting data, revising assumptions, and recalculating financial results. A new FX tick need not trigger an expensive AI research cycle across every company. Batch observations, cache extraction keyed by document/parser version, use deterministic calculations for routine rates, and invoke AI only where new evidence requires interpretation. Materiality-based triggers can reduce recalculation cost while preserving all observations.

The first model can run manually. Add scheduling after reruns are idempotent, inputs are versioned, and failures preserve the last valid output. Add the continuous research loop separately from routine updates: it proposes and evaluates alternative models rather than silently replacing the production equations.

## Guardrails for the original vision

More collected data does not automatically improve a forecast. Each research stream should identify the assumption it informs, its economic mechanism, its expected lag and how its benefit could be evaluated.

Shared factors do not eliminate company differences. Their transmission must be estimated and checked. An attractive Monte Carlo histogram does not establish calibrated probabilities or an investment edge. First produce a reconciled deterministic Nestlé model, then introduce a small number of justified uncertain drivers, then record prospective forecasts.

Scalability at this stage means reusable boundaries and consistent records. It does not require microservices, separate repositories per company, a large cloud deployment or a fully autonomous agent system before the first calculation works.
