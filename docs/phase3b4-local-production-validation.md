# Phase 3B.4 — Local Production Validation

## Scope

Phase 3B.4 exercised the Phase 3B.3 candidate only in an isolated local SQLite database. The source database remained read-only and outside the validation transactions. The frozen bundle and four accepted Phase 3B trust anchors remained unchanged. No Azure resources were used.

## Validation environment

- Source: local `pse_pulse_dev.db`, opened read-only and cloned through SQLite's online backup API.
- Validation database: `~/pse-pulse-production-artifacts/phase3b4/2026.10.01-authoritative-v1/phase3b4_validation.db`.
- The clone alone was migrated from Alembic 0005 to 0006. The source database remained at its starting schema and its database/sidecar SHA-256 fingerprint matched before and after execution.
- The external database and Phase 3B.4 receipt are not repository files.

## Candidate registration and activation

The accepted bundle was verified 45/45. The existing `register_candidate_bundle()` service inserted 45 inactive rows, one for each canonical company/model pair. A second registration inserted zero rows and left lineage unchanged. Registration created no Forecast or PipelineRun records.

The existing `activate_candidate_bundle()` service activated exactly those 45 rows in one transaction. Activation used `MODEL_ARTIFACT_ACTIVATION_ENABLED=true` only in its dedicated child process, with exact bundle/SHA confirmations and the accepted Phase 3B.3 evaluation receipt. It created no Forecast or PipelineRun records. A fresh process with both switches false confirmed that all 45 active rows and 45/45 bundle reloads survived process exit.

## Inference and persistence

Inference used the production `RealForecastService` and the frozen artifact bundle. Its inference child processes received `REAL_MODELS_ENABLED=true` only for the duration of that process; activation permission remained false.

- Dry run: 15 companies and 45 predictions, with zero Forecast, ModelArtifact, or PipelineRun changes.
- First persistent run: 45 non-demo forecasts and one completed non-demo PipelineRun. Each family contributed 15 forecasts. All records linked to the exact active manifest artifact, shared origin date 2026-10-01 and target date 2026-10-02, and passed finite/positive price, calendar, and provenance checks.
- Second fresh-process run: zero new forecasts, 45 unchanged forecasts with original IDs and lineage, zero artifact changes, and one completed audit PipelineRun.
- A runtime guard monitored the LIR, ARIMA, and LSTM training entrypoints during persistent inference. None was reached.

Successful persistence now flushes forecast rows and the completed PipelineRun together and commits once. An injected commit failure test confirms the forecasts roll back and a separate FAILED PipelineRun audit row is created after rollback. Immutability tests reject changes to an existing forecast's artifact, origin, price, or delta.

## Defaults, API, and dependencies

The real runner defaults to bundle `2026.10.01-authoritative-v1` and all three families. The FastAPI read-only validation passed for `/health`, `/api/v1/companies`, `/api/v1/forecasts/latest`, `/api/v1/models`, and `/api/v1/pipeline/status` with both safety switches false. All 45 real forecasts were visible, and API startup caused no database changes.

PyTorch remains limited to `backend/requirements-lstm.txt`; normal application/model requirements were not changed. LSTM loading remains lazy for normal API imports.

## Recovery note

The first driver attempt completed registration, activation, restart checks, dry-run inference, and committed the first 45-forecast batch. A subsequent post-commit reporting helper failed because it imported `DailyPrice` from a nonexistent module path. The helper was corrected. The driver resumed only after checking the exact expected isolated database state; a read-only validator confirmed all 45 first-run forecasts and their lineage before it ran the second inference and API checks.

## Internal worker authorization

The suppressed worker modes are internal entrypoints. Each worker requires `PHASE3B4_INTERNAL_WORKER=1`, which the orchestrator adds only to the subprocess environment created by `_run_worker()`; direct worker invocation is rejected. Registration, activation, and both persistent inference workers independently recheck the non-production environment and the exact bundle version, manifest SHA, and local-validation confirmation. The orchestrator passes those confirmations to each mutating child. Activation and real-inference permissions remain scoped to their respective child processes, and the no-training guard runs for dry-run as well as persistent inference.
