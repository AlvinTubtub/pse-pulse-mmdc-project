# Phase 3B.1 Acceptance Report

## 1. Destination Baseline

- Repository: `AlvinTubtub/pse-pulse-mmdc-project`
- Branch: `main`
- Required starting HEAD: `14ebcc12df885c20e1f951a892b54d368ebf7b0a` (verified)
- Changes remain unstaged and uncommitted.

## 2. Official Source Identity

- Official repository: `AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27`
- Pinned source snapshot: `b8bf39f8e94729687c2e877dc164ea8a4f69e2b1` (verified)
- Source worktree is clean; its push URL is `DISABLED_DO_NOT_PUSH`.

## 3. Authoritative Selection Snapshot

- Destination snapshot: `backend/config/authoritative/forecastph_selected_configurations_20260911.csv`
- Official Git blob: `60fe633c8e2860a56cb46248cd4b937c1a231833`
- SHA-256: `7c648357adaba1e5769d560435bad61a933d67ebb5ee8fc1ded5944416737a97`
- Byte comparison with the pinned source passed.

## 4. Formal Run Provenance

- Run ID: `FORECASTPH_FORMAL_20260911_01`
- Cutoff: `2026-09-11`
- Formal experiment Git SHA: `8359270bffcd43dd41830a01bb2f4e2d4c527b56`
- Selection criterion: `mean_validation_rmse`; CV splits: 5
- Tuning seeds: 11, 29, 47; final seed: 42
- The formal experiment SHA, source snapshot commit, and historical data commit are retained as distinct provenance fields.

## 5. Selection Catalog Validation

The fail-closed catalog validates the pinned digest, all 15 canonical companies, supported LIR/ARIMA/LSTM grids, and shared formal provenance. Targeted catalog tests passed: 19 tests, including the BPI regression sentinel and malformed/corrupted catalog cases.

## 6. LIR Selection Semantics

The catalog carries the formal selected alpha. Formal selected feature names remain audit evidence; production feature selection continues to be based on current production history. Phase 3A LIR implementation files were not changed.

## 7. ARIMA Selection Semantics

The catalog carries selected order, trend, drift, and confirmed-convergence evidence. Phase 3A ARIMA implementation files were not changed.

## 8. LSTM Methodology Parity

The port uses univariate historical Close deltas to predict the next absolute Close delta, with additive Close reconstruction. No OHLCV, technical, LIR, or sector features were added. Sequence continuity, lookahead, finite-value, and target contracts are covered by tests.

## 9. LSTM Config Contract

The reference grid is lookbacks `(5, 10, 20)`, hidden sizes `(16, 32)`, learning rates `(0.001, 0.003)`, and batch size `(32,)`, or 12 specifications. Tuning seeds are `(11, 29, 47)`, final seed is 42, CV splits are 5, maximum epochs are 100, patience is 10, minimum improvement is `1e-6`, stopping tail proportion is 0.15, and minimum stopping samples are 5. No grid search or new tuning was performed.

## 10. LSTM Sequence/Scaler Contract

Inputs have shape `[batch, lookback, 1]`, and each target is the immediately following Close delta. Scalers fit only the declared training block and use population standard deviation (`ddof=0`), with a scale fallback of `1.0` for a constant block.

## 11. Network Architecture

The model is one `nn.LSTM(input_size=1, hidden_size=selected, batch_first=True)` followed by one `nn.Linear(hidden_size, 1)` applied to the last output timestep. No additional layers or features were introduced.

## 12. Training and Determinism

Training uses Adam, MSE loss, chronological minibatch slices, and no shuffling. Python, NumPy, and PyTorch seeds are set; deterministic algorithms are enabled and cuDNN benchmarking is disabled where applicable. Same-environment deterministic fixture tests passed. Exact numeric identity across PyTorch versions, operating systems, hardware, or implementation versions is not promised.

## 13. Stage-A / Stage-B Production Refit

Stage A selects fresh production epochs from the chronological stopping tail. Stage B creates a fresh scaler and model and fits all available labeled production samples for that count using seed 42. The formal selected epoch count is not reused as the production epoch count.

## 14. LSTM Artifact Security

Artifacts store structured CPU state dictionaries in `pytorch_state_dict` `.pt` format. The loader validates metadata identity, path, history boundary, required hyperparameters, and SHA-256 before `torch.load(..., map_location="cpu", weights_only=True)`. Loaded schema, specification, epochs, seed, scaler, tensor finiteness, and strict state-dict compatibility are then checked. Pre-load and post-load rejection cases are covered by tests.

### Authoritative Artifact Binding

Persistence loads the pinned selection catalog and requires the per-company LSTM specification, formal selected epoch evidence, final seed, and provenance to match before it writes an artifact. The safe loader independently loads the catalog and revalidates the metadata specification, formal epoch evidence, final seed, top-level provenance, and nested provenance before `torch.load`. Metadata integer parameters reject booleans and floating-point values. Tests demonstrate that valid-grid but wrong-company configurations and inconsistent selection evidence fail before deserialization; persistence rejection cases produce no `.pt` file. Formal evidence (BPI: 9 epochs) remains separate from freshly selected production epochs (BPI smoke: 3).

## 15. BPI Authoritative Selection

- LIR alpha: `0.1`
- ARIMA order/trend: `(1, 1, 1)` / `n`
- LSTM: lookback 5, hidden size 16, learning rate 0.003, batch size 32
- Formal selected LSTM epochs: 9 (formal evaluation evidence)

## 16. BPI Production-Refit Smoke

The offline smoke used the pinned official BPI history only: 1,649 rows, `2020-01-02` through `2026-10-01`. It trained on 1,643 sequence samples. Fresh Stage A selected **3 production epochs**; Stage B used seed 42. Smoke outputs are confined to `/tmp/pse-pulse-phase3b1-smoke/`.

## 17. BPI Safe Reload and Inference

- Artifact: `lstm.pt`; format: `pytorch_state_dict`
- SHA-256: `a65c814fb17db913ff812c90c9383378265bb1519e2e7b4218715a60b570f9eb`
- Scaler: mean `0.003944174757281553`, scale `2.0088584709000394`, 1,648 observations
- Safe checksum-first reload succeeded.
- Origin: `2026-10-01`, Close `94.5`; calendar-computed target: `2026-10-02`
- Predicted delta: `-0.16966831825640782`; reconstructed Close: `94.33033168174359` (finite and positive)
- No public forecast row was persisted. This is a numerical smoke result, not an accuracy claim.
- Environment: Python 3.12.13, PyTorch 2.14.1, NumPy 2.5.3.

## 18. Phase 3A Regression

Phase 3A LIR, ARIMA, feature, calendar, artifact-security, forecast lineage/immutability, lifespan, and API tests passed in the backend suites. No LIR/ARIMA mathematics or artifact-security code was changed.

## 19. Backend Test Results

Lightweight environment: `pip check` passed; compileall passed; **163 passed, 2 skipped**. The skips are optional LSTM tests when PyTorch is absent.

## 20. LSTM Test Results

Isolated Python 3.12 environment: `pip check` reported “No broken requirements found.” Focused selection/LSTM suite: **68 passed**. Full Torch-enabled backend suite: **211 passed**.

## 21. Frontend Regression

Lint passed; TypeScript check passed; Next.js production build passed and generated 26 static pages. `npm audit --omit=dev` reported **0 vulnerabilities**.

## 22. API/Migration Regression

SQLite migration `base -> head` passed and resolved to `0005_add_model_artifacts_and_forecast_lineage`. Existing tests passed for `/health`, `/api/v1/companies`, `/api/v1/forecasts/latest`, `/api/v1/models`, and `/api/v1/pipeline/status`. Forecast responses remain demo data; the smoke forecast is not exposed.

## 23. Repository Hygiene

`git diff --check` passed. No generated Phase 3B.1 `.pt` artifact is in the repository. The file scan found the pre-existing `backend/pse_pulse_dev.db` and `.pkl` test fixtures inside `backend/.venv`; these were left untouched. Smoke model, metadata, training history, and acceptance JSON remain under `/tmp`.

## 24. Official Source Integrity

Final source check confirmed the pinned HEAD, clean worktree, empty unstaged/staged diffs, and disabled push URL.

OFFICIAL SOURCE REPOSITORY WAS NOT MODIFIED.

## 25. Pre-Commit Destination Git Status (Acceptance Snapshot)

This section records the destination repository state at the Phase 3B.1 pre-commit acceptance checkpoint.

The destination remains on `main` at the required starting HEAD. Intended files are modified or untracked for review; nothing is staged or committed. No commit or push was performed.

## 26. Deferred Phase 3B.2 Work

No all-15 production bundle was generated. No real production forecast was activated. No Azure resources were created or deployed. Phase 3B.2 bundle generation and Phase 3B.3 evaluation/activation remain deferred.

NO AZURE RESOURCES WERE CREATED OR DEPLOYED.
