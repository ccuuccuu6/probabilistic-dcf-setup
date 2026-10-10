# First build milestones

Complete these in order. Do not treat the existence of a folder as a completed feature.

| Step | Concrete work | Finished when |
|---|---|---|
| 1 — Setup | Open the project, create `.venv`, install locally, run doctor/demo, save code history | Commands succeed and the CSVs can be inspected |
| 2 — Define Nestlé rows | Agree reporting periods, current segment structure, financial rows and metric definitions | Every proposed line is reported, calculated or explicitly estimated |
| 3 — Store the first evidence | Archive a small official-source set; implement SQLite source/fact/version records | A historical figure traces to a document passage and availability history |
| 4 — Reconcile history | Build source-linked historical tables and accounting checks | Segment/group totals and material bridges reconcile or have explicit unresolved issues |
| 5 — One financial forecast | Add `models/` with deterministic equations and a cash-flow/valuation policy | One full case reconciles and can be audited against a familiar Excel layout |
| 6 — Review workbook | Add `reporting/`; generate historical, assumption, model and check views | The user can inspect every material line and its logic |
| 7 — First uncertainty | Add NumPy sampling; shared factor paths and selected company drivers | Complete scenarios reconcile and distribution bases are documented |
| 8 — Repeatable updates | Implement dependency routing, immutable assumption/run versions and forecast issuance records | The same evidence does not double-update the model; stale jobs cannot publish over newer ones |
| 9 — Second company | Add company configuration and mappings using existing shared research | Shared evidence and FX paths work without duplicating the research engine |

An initial public-data model can contain uncertainty about poorly observed company exposures. It should not present unreported procurement or hedge details as facts. Identify these gaps explicitly and test valuation sensitivity before deciding whether more data is worth acquiring.

The platform will eventually have frequent ingestion, AI extraction and research, forward evaluation, reverse DCF and catalyst analysis. This setup package intentionally implements only the first milestone's local foundation.
