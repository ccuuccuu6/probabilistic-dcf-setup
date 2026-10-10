# Project intent

Build a reusable probabilistic fundamental forecasting and valuation system, starting with Nestlé. Python will perform calculations; Excel will provide an inspectable review interface. The current package is a setup scaffold and synthetic FX demonstration only.

# Standing collaboration requirement

Tell the user explicitly when a proposed step weakens this vision or is unlikely to help it work. Explain the concrete issue and propose a practical alternative. Do not silently implement a design that defeats the intended economics, auditability, or reuse.

# Design rules

- Work step by step. Establish the local data and calculation path before external APIs, schedulers, cloud services, or elaborate agent orchestration. A small local SQLite evidence registry can precede the financial model; do not introduce services before they solve a concrete need.
- Store shared evidence and factor states once. Coffee, FX, and other common research can affect several companies; apply separately verified company exposure mappings, purchasing currencies, hedges, and lags.
- Distinguish topic relevance from quantified exposure. Do not invent company exposures to fill a template.
- Preserve source identity, definitions, publication/availability times, and assumption versions when real data storage is implemented.
- Use the same scenario identity across dependent drivers, periods, and companies. Derive FX cross rates from a shared currency state.
- Attach uncertainty to defensible underlying drivers. Calculate dependent financial rows with accounting equations; do not independently randomize revenue, costs, margins, and profits.
- Distinguish provisional judgment from empirically calibrated probabilities. Sampling a distribution does not establish forecasting skill.
- Keep synthetic demonstrations clearly labelled in inputs, outputs, and explanations. Never present demonstration values as company forecasts or market observations.
- Keep equations separate from assumption inputs. Do not let routine evidence updates silently change production model structure.
- Preserve run inputs and results. Never overwrite an earlier run. A local hashed manifest is useful provenance, not a tamper-proof forecast ledger.
- Keep secrets and frequently updated research/output files out of Git. Do not add user credentials or real data to this scaffold.

# Verification

From the project root after an editable install:

```text
python -m research_platform doctor
python -m unittest discover -s tests -v
python -m research_platform demo-fx
```

Keep checks focused on meaningful financial identities, validation, and reproducibility. State what remains unimplemented instead of implying the full platform is ready.
