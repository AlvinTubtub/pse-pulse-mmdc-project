# Phase 3B.3 Acceptance Report

Phase 3B.3 implements and evaluates the activation gate for the frozen Phase 3B.2 bundle. It establishes operational eligibility; it does not activate or register the production candidate in the local database.

## 1. Destination Baseline

- Repository: `AlvinTubtub/pse-pulse-mmdc-project`
- Branch: `main`
- Starting and final HEAD: `e827a4980c5d1f4a65c58487aeaf6cd050f4fe9a`
- `origin/main` matched this HEAD at baseline verification.
- All Phase 3B.3 changes remain uncommitted. No files were staged.

## 2. Frozen Bundle Identity

- Bundle: `2026.10.01-authoritative-v1`
- Manifest SHA-256: `4225e60044f000b16147e01f6ff165968523c1efd9647e57d9c7a6f5f5a27454`
- Inventory: 15 symbols, 45 models, 45 metadata JSON files, and 91 core files.
- Families: LAG_REGRESSION, ARIMA, LSTM.

## 3. Phase 3B.2 Trust Anchor

The required `bundle_validation.json` was present and was not regenerated or modified. Its SHA-256 is `3ab0ca422605379c011374c0be8d5cb765c0d74ceb3a5e859d2efc98fca95129`. It contains 45 unique safe-reload inference records at origin `2026-10-01` and target `2026-10-02`.

## 4. Runtime Loader Integration

Added a PyTorch-free manifest-driven runtime loader. It checks manifest identity, selected entry, metadata identity, safe relative file paths, artifact and metadata hashes, bundle version, trained-through date, and data-row count. LIR and ARIMA dispatch through the Phase 3B.2 authoritative loader. LSTM dispatch imports its state-dict loader only when explicitly requested. The bundle manifest supplies the canonical artifact and metadata paths.

## 5. LIR Runtime Evaluation

The frozen LIR artifacts loaded successfully for all 15 symbols. Forecasts use the persisted Lasso/scaler artifact, causal features through the origin, the selected return lags, and additive Close reconstruction. No refit or selection occurred.

## 6. ARIMA Runtime Evaluation

The frozen ARIMA artifacts loaded successfully for all 15 symbols. Later observations are appended with `refit=False`; the runtime produces one-step forecasts from the persisted converged state. No refit occurred.

## 7. LSTM Runtime Evaluation

The frozen LSTM state dictionaries and scalers loaded successfully for all 15 symbols. Inference uses the latest observed absolute Close-delta lookback and frozen scaler/network, with additive Close reconstruction. No scaler update, hidden-state persistence, or refit occurred.

## 8. PyTorch Dependency Boundary

The FastAPI import subprocess test and LIR/ARIMA-only runtime subprocess test passed without importing PyTorch or the LSTM-heavy modules. LSTM-specific tests passed in the Torch-enabled environment. Base `backend/requirements.txt` and `backend/requirements-models.txt` were not changed; PyTorch remains isolated in `backend/requirements-lstm.txt`.

## 9. ModelArtifact Inactive-by-Default Migration

The ORM default and Alembic migration `0006_model_artifacts_inactive_by_default` set new `is_active` values to false. The migration changes only the server default, preserves existing explicit true/false values, and restores the previous true default on downgrade.

## 10. Candidate Registration Contract

The explicit registration service verifies the complete bundle and exact manifest SHA before inserting candidate rows. It preflights the 15 canonical active companies and one ModelMetadata row for each required family. It uses exact manifest-relative paths and metadata lineage, creates rows inactive, rejects conflicting lineage, and is idempotent for identical bundles. It does not create forecasts. Registration was tested only in isolated temporary databases; no live candidate rows were registered.

## 11. Activation Transaction Contract

Activation is a separate transaction requiring the exact version and manifest SHA, a passing evaluation receipt, the activation setting, exactly 45 matching inactive candidate rows, and the complete canonical inventory. It checks hashes, paths, formats, training boundaries, row counts, hyperparameters, and provenance; deactivates prior versions for matching company/model pairs; activates the exact candidate set; and verifies 45 active rows before commit. Injected failure rollback and old-version deactivation passed in temporary databases. Activation was not executed.

## 12. Real Forecast Service Lineage Enforcement

Persistent serving defaults to all three runtime model families and requires exactly one already-active artifact row per requested company/model pair. The row must match ModelMetadata, bundle version, format, manifest path, SHA, training boundary, row count, and source provenance. Missing, duplicate, and mismatched lineage fails closed. Serving no longer auto-registers or auto-activates ModelArtifact rows.

## 13. Fixed-Boundary 45/45 Replay

The evaluator truncated each canonical history through `2026-10-01`, derived the target from `PSETradingCalendar`, and reproduced 45 one-step forecasts for `2026-10-02`.

## 14. Phase 3B.2 Reproduction Comparison

All 45 predictions matched the Phase 3B.2 evidence at full precision using `math.isclose(rel_tol=1e-10, abs_tol=1e-8)`. Result: 45/45 matches.

## 15. Current-History 45/45 Shadow Evaluation

All 45 models passed safe loading and finite-positive output checks against current canonical database history. The latest observed origin was `2026-10-01`; the calendar resolved the next target to `2026-10-02`. The evaluation makes no accuracy or model-superiority claim.

## 16. Database Zero-Mutation Proof

Before and after both shadow evaluations, database row deltas were:

- Forecast: 0
- ModelArtifact: 0
- PipelineRun: 0

The read-only activation preflight found 15 canonical companies and three runtime ModelMetadata records.

## 17. Activation Plan

External plan: `~/pse-pulse-production-artifacts/phase3b3/2026.10.01-authoritative-v1/activation_plan.json`

- Inventory validation: PASS, 45 per-artifact entries.
- SHA-256: `26da93fe8da52cfca4cd026b8a4245c96d745d74eb46cce056680c062390f472`
- `executed`: false.

## 18. Eligibility Receipt

External receipt: `~/pse-pulse-production-artifacts/phase3b3/2026.10.01-authoritative-v1/phase3b3_evaluation.json`

- Result: `ELIGIBLE_FOR_ACTIVATION`
- Activation status: `BUT_NOT_ACTIVATED`
- SHA-256: `aa3a6f63cd3ede5c831147d45245f91b2d956416582c9d9bff2b8794fdf1905c`
- `MODEL_ARTIFACT_ACTIVATION_ENABLED=false`
- `REAL_MODELS_ENABLED=false`

## 19. Lightweight Backend Results

Installed only `backend/requirements.txt` and `backend/requirements-models.txt` into an isolated Python 3.12 environment without PyTorch. Compileall passed. Full backend suite: 206 passed, 2 PyTorch-dependent skips, 0 failures. `pip check`: no broken requirements.

## 20. Torch-Enabled Backend Results

Full backend suite with PyTorch available: 254 passed, 0 failures. `pip check`: no broken requirements.

## 21. Frontend Results

- `npm run lint`: PASS
- `npx tsc --noEmit`: PASS
- `npm run build`: PASS, 26 static pages generated
- `npm audit --omit=dev`: PASS, 0 vulnerabilities

## 22. Migration Results

Isolated temporary SQLite migration sequence `0005 -> 0006 -> 0005 -> 0006`: PASS. Explicit active/inactive values remained intact, the new-row default was inactive at 0006, and downgrade restored the prior active default.

## 23. API Regression

17 tests passed for health, companies, latest forecasts, model metadata, and pipeline status endpoints. Public API behavior remained unchanged while both real-model and activation switches were false.

## 24. Frozen Bundle Post-Verification

The Phase 3B.2 verifier was rerun after evaluation: 45/45 safe reloads. The manifest SHA remained `4225e60044f000b16147e01f6ff165968523c1efd9647e57d9c7a6f5f5a27454`. The bundle still contains 45 binaries, 45 metadata files, and 91 core files.

## 25. Official Source Integrity

The pinned official source checkout was not used or modified. Its required pinned identity remains an external provenance value only.

OFFICIAL SOURCE REPOSITORY WAS NOT MODIFIED.

## 26. Repository Hygiene

No model binaries, bundle manifests, bundle-validation evidence, activation plans, or Phase 3B.3 receipts were found in the Git repository. `git diff --check` passed. The evaluation plan and receipt remain outside Git.

## 27. Pre-Commit Git Status

Branch `main`, HEAD `e827a4980c5d1f4a65c58487aeaf6cd050f4fe9a`. The Phase 3B.3 patch is uncommitted and unstaged. Exact changed paths are visible in `git status --short`; no commit or push was made.

- `.github/workflows/ci.yml`
- `PHASE3B3_ACCEPTANCE_REPORT.md`
- `backend/alembic/versions/0006_model_artifacts_inactive_by_default.py`
- `backend/app/config.py`
- `backend/app/forecasting/real/artifacts/runtime.py`
- `backend/app/forecasting/real/evaluation/__init__.py`
- `backend/app/forecasting/real/evaluation/gate.py`
- `backend/app/forecasting/real/inference/next_day.py`
- `backend/app/forecasting/real/inference/predictor.py`
- `backend/app/models/model_artifact.py`
- `backend/app/services/model_activation_service.py`
- `backend/app/services/real_forecast_service.py`
- `backend/tests/test_model_activation_service.py`
- `backend/tests/test_phase3b3_gate_runtime.py`
- `backend/tests/test_phase3b3_migration.py`
- `backend/tests/test_real_forecast_service.py`
- `backend/tests/test_real_lstm_dependency_boundary.py`
- `docs/model-porting-plan.md`
- `docs/phase3b3-activation-gate.md`
- `scripts/phase3b3_activate_bundle.py`
- `scripts/phase3b3_evaluate_bundle.py`

## 28. Deferred Real Activation

No candidate rows were registered in the local database, no artifact rows were activated, no forecast was persisted by the evaluator, and both safety switches remain false. Eligibility does not authorize activation.

## 29. Deferred Azure Deployment

NO AZURE RESOURCES WERE CREATED OR DEPLOYED.

## 30. Post-Review Correction

Final review found that the real-serving unit-test fixture mislabeled its mocked LSTM prediction as ARIMA. The fixture now maps each family to its exact `ModelId`, supplies the production LSTM format and `<symbol>/lstm.pt` path, and proves 3/3 model-family forecasts are generated and persisted with all three metadata families. The Mapping/LSTM predictor now validates strictly chronological history before checking positional training-boundary and lookback data; regression tests reject both out-of-order and duplicate dates.

Post-review verification: focused serving/runtime/dependency-boundary tests, 19 passed; lightweight backend, 208 passed and 2 skipped; Torch-enabled backend, 256 passed; API regressions, 17 passed; migration sequence, passed; frontend lint, typecheck, and build passed with 26 static pages; production dependency audit found 0 vulnerabilities. Both backend environments passed `pip check`.

No candidate artifact, accepted prediction, activation plan, or evaluation receipt changed. Frozen evidence remains: activation plan SHA-256 `26da93fe8da52cfca4cd026b8a4245c96d745d74eb46cce056680c062390f472`; evaluation receipt SHA-256 `aa3a6f63cd3ede5c831147d45245f91b2d956416582c9d9bff2b8794fdf1905c`; manifest SHA-256 `4225e60044f000b16147e01f6ff165968523c1efd9647e57d9c7a6f5f5a27454`; bundle verifier 45/45.

## Required Decision

PHASE 3B.3 ACTIVATION GATE:
ELIGIBLE_FOR_ACTIVATION
BUT_NOT_ACTIVATED
