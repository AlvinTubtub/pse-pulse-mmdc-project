# Phase 3B.4 Acceptance Report

Date: 2026-10-06 (Asia/Manila)

### Final pre-commit safety correction

Independent review identified that the suppressed `--worker-mode` option needed an explicit orchestrator-only authorization boundary. Every worker now requires an internal marker that `_run_worker()` adds only to its child process; mutating workers independently enforce the production block and exact bundle version, manifest SHA, and local-validation confirmations. All mutating child commands carry those confirmations, and the no-training guard now covers dry-run inference too. The frozen bundle and accepted forecasts were not changed; the external validation database and Phase 3B.4 receipt were not modified or regenerated.

## 1. Destination baseline

- Repository: `AlvinTubtub/pse-pulse-mmdc-project`
- Branch: `main`
- Starting commit: `0be988b57ab19e0ce462773a574fc7e1dbef461f` (matched `origin/main`)
- Changes in this report remain uncommitted and unpushed pending ChatGPT review.

## 2. Frozen trust anchors and bundle verification

All frozen files were read and hashed; none were regenerated or changed.

- Bundle version: `2026.10.01-authoritative-v1`
- Manifest SHA-256: `4225e60044f000b16147e01f6ff165968523c1efd9647e57d9c7a6f5f5a27454`
- Phase 3B.2 bundle-validation SHA-256: `3ab0ca422605379c011374c0be8d5cb765c0d74ceb3a5e859d2efc98fca95129`
- Phase 3B.3 activation-plan SHA-256: `26da93fe8da52cfca4cd026b8a4245c96d745d74eb46cce056680c062390f472`
- Phase 3B.3 evaluation-receipt SHA-256: `aa3a6f63cd3ede5c831147d45245f91b2d956416582c9d9bff2b8794fdf1905c`
- Standalone bundle pre- and post-verification: 45/45 safe reloads.
- Phase 3B.3 receipt: eligible, not activated; boundary replay, reproduction, and current shadow each 45/45; Forecast, ModelArtifact, and PipelineRun deltas each zero; activation preflight 15 companies and three model families.

## 3. Source database isolation and non-mutation

The configured source was local SQLite at `pse_pulse_dev.db`; no database credentials were printed. It was opened read-only and cloned with SQLite's backup API. The source remained at its initial Alembic revision 0005; only the external clone was upgraded to 0006.

The source fingerprint, including SQLite sidecars, was identical before and after validation. Main database SHA-256: `0f7f1386a57e10e13a292508ae3efc52fa8d5ab968a12bdb9cce42b5a1ff9874`; WAL and SHM sidecars were absent.

Source baseline: 18 companies total, 15 active canonical companies, 24,795 DailyPrice rows, three ModelMetadata rows, zero ModelArtifact rows, 240 Forecast rows, and four PipelineRun rows. The canonical symbols matched the project universe; each required family had exactly one metadata row; market data reached 2026-10-01. No candidate rows, active candidate rows, or non-demo forecasts linked to this bundle were present.

Validation database: `~/pse-pulse-production-artifacts/phase3b4/2026.10.01-authoritative-v1/phase3b4_validation.db`, outside Git. Its SHA-256 is `d65935ac9d865008ced7e49688446e44fe21750a0b1beec006c9c149aaafddbe`.

## 4. Registration and activation

- Registration inserted 45 exact candidate rows, all inactive; second registration inserted zero and left all lineage unchanged.
- Registration created zero Forecast and zero PipelineRun rows.
- Process-scoped activation permission was true only in the dedicated activation subprocess. Exact bundle version, manifest SHA, and the accepted Phase 3B.3 receipt were supplied.
- Atomic activation left 45 candidate rows active and zero inactive; activation created zero Forecast and zero PipelineRun rows.
- A fresh ordinary process with both switches false confirmed 45 active rows and 45/45 bundle verification after restart.

The first driver attempt completed these phases and the dry run before committing the first persistent batch. A post-commit reporting helper then failed on an incorrect `DailyPrice` import path. The helper was fixed. The driver resumed only after confirming the exact expected isolated post-first-run database counts; a fresh read-only validator then verified the first run's rows, lineage, shared dates, and audit record. No source database change, duplicate forecast, activation repetition, or row deletion occurred during recovery.

## 5. Runner defaults and persistence atomicity

`backend/pipeline/forecasting/real_runner.py` now defaults to the authoritative accepted bundle version and `LAG_REGRESSION,ARIMA,LSTM` in both its CLI and `run_real_pipeline()` signature.

The success path now sets `PipelineRun` to COMPLETED before the single transaction commit that persists it with all forecasts. On failure, rollback removes the attempted forecasts and running audit row; the service explicitly inserts a FAILED PipelineRun with the same run identifier in a new transaction. Regression tests cover injected commit failure, rollback, failure audit recording, and one-commit successful persistence.

Forecast immutability tests reject differences in artifact ID, origin, predicted price, or predicted delta. Active-lineage tests cover inactive/missing/duplicate rows and mismatches in bundle, SHA, path, format, training boundary, and provenance; failures write no new real forecasts.

## 6. Dry run and persistent inference

- Dry run: 15 companies, 45 predictions, with zero Forecast, ModelArtifact, and PipelineRun deltas.
- First persistent run: 15 companies, 45 non-demo forecasts, 45 persisted forecasts, and one completed non-demo PipelineRun. Inference-step deltas were Forecast +45, ModelArtifact +0, PipelineRun +1.
- Family counts: LAG_REGRESSION 15; ARIMA 15; LSTM 15.
- Every forecast links to the exact active manifest ModelArtifact, has an origin and target, is non-demo, and has a PipelineRun ID. Runtime checks compared format, relative path, SHA, training boundary, row count, and both source provenance pairs to the frozen manifest/metadata. All values were finite and predicted prices positive.
- Shared origin date: 2026-10-01. PSETradingCalendar target date: 2026-10-02.
- Second inference ran in a new process: zero new forecasts, 45 unchanged forecasts retaining their IDs and lineage, zero ModelArtifact changes, and one additional completed audit PipelineRun.
- Final validation DB totals: 45 candidate artifacts, all 45 active; 45 non-demo candidate forecasts; 285 forecasts overall; six PipelineRuns overall.

The inference processes received `REAL_MODELS_ENABLED=true` only for their own process; activation permission was false. An entrypoint guard monitored production LIR/ARIMA/LSTM training functions during dry-run inference, first persistent inference, and second persistent inference; none was reached.

## 7. API, safety, and dependency checks

Against only the isolated validation database, with both normal safety switches false:

- `GET /health`: passed.
- `GET /api/v1/companies`: all 15 canonical companies visible.
- `GET /api/v1/forecasts/latest`: all 45 real forecasts visible, all three families represented.
- `GET /api/v1/models`: all three families visible.
- `GET /api/v1/pipeline/status`: completed real inference visible.
- API startup caused zero database row changes.

Normal settings still default `MODEL_ARTIFACT_ACTIVATION_ENABLED=false` and `REAL_MODELS_ENABLED=false`. LSTM/PyTorch remains isolated in `backend/requirements-lstm.txt`; neither standard requirements file was changed. Normal API imports remain Torch-free.

## 8. Regression results

- Compileall over `backend/app`, `backend/pipeline`, `backend/alembic`, `backend/tests`, and `scripts`: passed.
- Lightweight environment installed only `backend/requirements.txt` and `backend/requirements-models.txt`: 233 passed, 3 skipped, 0 failures; `pip check` found no broken requirements. (Python 3.13.9 temporary environment; no PyTorch installed.)
- Torch-enabled backend environment: 281 passed, 1 skipped, 0 failures; `pip check` found no broken requirements.
- Focused Phase 3B.4 safety/regression set: 54 passed.
- Phase 3B.4 local-activation test module: 16 passed.
- Focused API and migration regression: 18 passed. Migration sequence 0005 → 0006 → 0005 → 0006 passed; Alembic head remains `0006_model_artifacts_inactive_by_default`.
- Frontend lint: passed; TypeScript typecheck: passed; build: passed, 26 static pages; production npm audit: 0 vulnerabilities.

## 9. External Phase 3B.4 receipt

Receipt: `~/pse-pulse-production-artifacts/phase3b4/2026.10.01-authoritative-v1/phase3b4_activation_receipt.json`

- Decision: `LOCAL_PRODUCTION_VALIDATED`
- Receipt SHA-256: `d544d03ea90bb26afd06a08f14944917ecbe6735c5df7f569ea4a89a9de62295`
- The receipt records the frozen hashes, source non-mutation fingerprints, validation DB identity and hash, registration/idempotency, activation, restart check, dry-run, both inference runs, family counts, API result, normal false safety settings, no-training guard, and post-run 45/45 bundle verification.
- The receipt and database remain outside Git.

## 10. Repository hygiene and provenance

No model binaries, database files, frozen external evidence, or Phase 3B.4 receipt were added to the repository. `git diff --check` passed. No source checkout of `AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27` was modified.

No Azure resources were created or deployed. No commit or push was made. The safety correction and its focused regression tests are included in this review state.

## Required Phase Decision

PHASE 3B.4 LOCAL PRODUCTION GATE:
LOCAL_PRODUCTION_VALIDATED
AZURE_NOT_DEPLOYED
