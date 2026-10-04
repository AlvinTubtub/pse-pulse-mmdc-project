# Phase 3A.2 Acceptance Report

## Destination and source identity

- Destination: `AlvinTubtub/pse-pulse-mmdc-project`
- Required destination branch and HEAD: `main` at `b87ef22c240dd64ef459bccef952062e76b0d5b4`
- Official source repository: `https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git`
- Declared exact source commit: `b8bf39f8e94729687c2e877dc164ea8a4f69e2b1`
- Source mode: uploaded archive; the commit is identified by the ZIP name/top-level directory and declaration, without fabricating a Git checkout
- New archive: `Capstone2-b8bf39f8-official.zip` (44,667,799 bytes)
- New exact-commit ZIP SHA-256: `af32ad179633c59fe4ff291f09a1dccf2907a6da2c7623eb2e442416e5d9b216`

Audit note: the previous `main` snapshot ZIP had SHA-256 `25c3fad70e6d1894a4b284f4e97fe595e53bfc0ea4de4df4891de8a12159584d`, contained the 2026-10-02 update, and failed the required boundary. Acceptance correctly stopped at that point. Source data was never silently truncated.

## Official methodology parity

The new archive's relevant methodology modules are byte-identical to those in the previous reference ZIP. The prior source findings are therefore reconfirmed against the exact-commit archive:

- LIR target: `target.close - origin.close` (absolute next-session Close delta).
- LIR reconstruction: `origin_close + predicted_delta`.
- Feature defaults: 20 return lags; `raw_price_lags = ()`; 47 ordered default features. The complete expected order is pinned in `backend/tests/test_real_features.py` and listed in `docs/phase3a-model-port-matrix.md`.
- PACF: statsmodels `method="ywmle"`, calculated from training data only.
- LIR fit: StandardScaler followed by sklearn Lasso, retaining configured alpha, max iterations, tolerance, coefficient-zero tolerance, fit metadata, and feature ordering.
- ARIMA: statsmodels ARIMA with explicit order and trend, retry/convergence inspection, confirmed convergence, `append(actual, refit=False)`, and a one-step forecast.
- Destination LIR target and additive reconstruction match. Deterministic tests cover 100→103 = delta 3 and origin 100 + delta 2.5 = Close 102.5, and reject multiplicative reconstruction.

**METHODOLOGY PARITY RECONFIRMED AGAINST EXACT-COMMIT ARCHIVE.** No mathematical deviation for LIR or ARIMA was identified.

## Fresh historical acceptance

Before database import, inspected every canonical file in `backend/data/raw/`:

- 15 canonical CSV files, exactly one for each configured symbol.
- Each contains 1,649 rows, dates 2020-01-02 through 2026-10-01, with no duplicate dates and no 2026-10-02 row.
- Total: 24,735 historical rows.

Created `/tmp/pse-pulse-phase3a-acceptance.db` from scratch using Alembic `base -> head`. Imported the new ZIP's validated CSVs through the existing bootstrap CSV validation and a test-only `VerifiedBootstrapSource` record. This isolated archive path does not weaken or modify production Git provenance verification.

Database results: 15 active companies; 24,735 `DailyPrice` rows; 0 duplicate company/date groups. BPI has 1,649 rows from 2020-01-02 through 2026-10-01.

## Fresh BPI smoke and artifact lineage

Generated only under `/tmp/pse-pulse-phase3a-smoke/phase3a-smoke/BPI/`. Smoke settings were LIR alpha `0.001` and ARIMA `(1,1,0)` with trend `n`. Artifacts are marked `NON_AUTHORITATIVE`; official configured convergence behavior remained enabled.

| Symbol | Model | Version | Trained through | Rows | Artifact SHA-256 |
| --- | --- | --- | --- | ---: | --- |
| BPI | LAG_REGRESSION | `phase3a-smoke` | 2026-10-01 | 1,649 | `46be4f8da2901651952499ceff9c94923e7842dfaabef3c8323576808a3b441e` |
| BPI | ARIMA | `phase3a-smoke` | 2026-10-01 | 1,649 | `cec3fef4af2a2f8f7e8a55ec9ebb4d4c56a9c08fe03472750525c36a6f6cd14b` |

Both artifacts record `source_repository` and `historical_data_source_repository` as `https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git`, and both commits as `b8bf39f8e94729687c2e877dc164ea8a4f69e2b1`.

The BPI-only `--dry-run` used 1,649 rows, origin 2026-10-01, and a target of 2026-10-02 computed by `PSETradingCalendar`. LIR produced delta `-0.45581807`, Close `94.04418193`; ARIMA produced delta `-0.23428940`, Close `94.26571060`. Both deltas and prices were finite, and both prices were positive. Zero real forecast rows were persisted. These are **numerically finite and positive smoke-test outputs**; no accuracy or economic-performance claim is made.

## Service, artifact security, and migration acceptance

- Real forecast service lineage and immutability tests pass, including artifact company/family/version mismatch rejection, required real forecast lineage fields, identical rerun behavior, differing-rerun integrity failure, rollback, and a complete 15-company synthetic run producing 30 forecasts.
- Artifact security tests cover wrong SHA, symbol, model family, model version, schema ID/version, unsafe filename, path traversal, missing metadata, missing required metadata, missing binary, loaded object type mismatch, metadata/model mismatch, and training-history boundary mismatch. Every pre-deserialization failure asserts `joblib.load()` was not called.
- Migration acceptance passed on disposable SQLite databases: `base -> head`; `0004 -> 0005`; `0005 -> 0004`; `0004 -> 0005`. No manual SQL `DROP` was used. Tests also confirm `AUTO_CREATE_SCHEMA` defaults false and persistent startup does not call `Base.metadata.create_all` with it disabled; production rejects schema auto-creation.

## API, backend, and frontend acceptance

API regression tests passed for `GET /health`, `/api/v1/companies`, `/api/v1/forecasts/latest`, `/api/v1/models`, and `/api/v1/pipeline/status`.

- Backend compile: `backend/.venv/bin/python -m compileall backend/app backend/pipeline backend/alembic backend/tests` — PASS.
- Backend suite: `backend/.venv/bin/pytest -v backend/tests` — **139 passed**, exceeding the prior 122-test baseline.
- Dependencies: `backend/.venv/bin/pip check` — `No broken requirements found.`
- Frontend `npm run lint` — PASS.
- Frontend `npx tsc --noEmit` — PASS.
- Frontend `npm run build` — PASS; 26/26 static pages generated.
- Frontend `npm audit --omit=dev` — **0 vulnerabilities**.
- `backend/requirements-models.txt` has no prohibited model dependency declarations.

## Reference integrity and repository hygiene

**OFFICIAL EXACT-COMMIT SOURCE ZIP REFERENCE WAS NOT MODIFIED.** The recursive SHA-256 manifest captured immediately after extraction matches the final manifest: 0 changed, 0 added, 0 removed files.

No generated smoke model artifacts remain in the repository; `backend/artifacts/` contains no files. The acceptance databases and smoke artifacts are under `/tmp`. The repository scan also found only ignored `.venv` dependency test `.pkl` fixtures and the ignored pre-existing `backend/pse_pulse_dev.db`; none is a commit candidate. No prohibited `file:///Users/` references were found in README, docs, or this report.

### Historical pre-commit snapshot

The following destination identity and status were recorded before the initial Phase 3A commit. They are preserved as historical evidence; the Phase 3A.3 section below records the current post-commit correction state.

Final destination identity at that pre-commit snapshot was `main` at `b87ef22c240dd64ef459bccef952062e76b0d5b4`. `git status --short`:

```text
 M .github/workflows/ci.yml
 M README.md
 M backend/app/config.py
 M backend/app/main.py
 M backend/app/models/__init__.py
 M backend/app/models/forecast.py
 M backend/tests/test_config.py
 M backend/tests/test_forecasts.py
 M docs/architecture.md
 M docs/model-porting-plan.md
?? ANTIGRAVITY_PHASE3A_REPORT.md
?? backend/alembic/versions/0005_add_model_artifacts_and_forecast_lineage.py
?? backend/app/forecasting/real/
?? backend/app/models/model_artifact.py
?? backend/app/services/real_forecast_service.py
?? backend/pipeline/forecasting/real_runner.py
?? backend/requirements-models.txt
?? backend/tests/test_real_artifacts.py
?? backend/tests/test_real_calendar.py
?? backend/tests/test_real_features.py
?? backend/tests/test_real_forecast_service.py
?? backend/tests/test_real_models.py
?? docs/model-artifact-contract.md
?? docs/phase3a-model-port-matrix.md
?? docs/real-inference-design.md
```

No files were staged, committed, or pushed. No Azure deployment or Phase 3B work was performed.

RECOMMENDATION: READY FOR CHATGPT REVIEW BEFORE PHASE 3A COMMIT

## Post-Commit CI Correction — Phase 3A.3

- Initial Phase 3A commit: `adc9b2951aa1465c8376ffd6c7d08d584fed9f66` (`feat: add verified LIR and ARIMA forecasting foundation`).
- Failed GitHub Actions run: `37011789268` (`PSE Pulse CI`). Backend reported 136 passed and 2 failed; frontend passed.
- Root cause: the two development lifespan tests assumed `sectors` existed in the application engine. On a clean CI database, `AUTO_CREATE_SCHEMA=false` correctly leaves it absent, so application startup logic correctly skips demo seeding. The create-all test mocked `create_all`, which likewise did not create the table, and the readiness guard correctly skipped seeding.
- Correction: extracted the existing read-only `inspect(engine).has_table("sectors")` check into `_database_schema_ready_for_seed()` and made the tests control schema readiness deterministically. Runtime behavior and Alembic-first safety are unchanged.
- New coverage: schema readiness helper returns true/false based on the `sectors` table; lifespan skips seeding when the schema is missing and auto-create is off; seeds when a migrated schema is ready; seeds after the auto-create path only when readiness is true; and still skips seeding if readiness remains false after mocked `create_all`.
- CI-style backend suite: `ENVIRONMENT=test DEMO_MODE=true DATABASE_URL="sqlite:///:memory:" backend/.venv/bin/pytest -v backend/tests` — **143 passed**.
- Normal backend suite: `backend/.venv/bin/pytest -q backend/tests` — **143 passed**.
- Backend compile: `backend/.venv/bin/python -m compileall backend/app backend/pipeline backend/alembic backend/tests` — PASS.
- Dependencies: `backend/.venv/bin/pip check` — `No broken requirements found.`
- Frontend: `npm run lint` — PASS; `npx tsc --noEmit` — PASS (rerun after the build completed; the first concurrent run overlapped `.next/types` generation); `npm run build` — PASS (26/26 static pages); `npm audit --omit=dev` — **0 vulnerabilities**.
- LIR/ARIMA methodology and artifact contracts were not changed. No Azure deployment or Phase 3B work was performed.
- No files staged, committed, or pushed. Correction scope: `backend/app/main.py`, `backend/tests/test_config.py`, and this report.

RECOMMENDATION: READY FOR CHATGPT REVIEW BEFORE PHASE 3A.3 FIX COMMIT
