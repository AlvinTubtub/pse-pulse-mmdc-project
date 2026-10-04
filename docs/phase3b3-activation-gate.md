# Phase 3B.3 Candidate Evaluation and Activation Gate

## Frozen trust anchor

Phase 3B.3 consumes the immutable Phase 3B.2 bundle `2026.10.01-authoritative-v1`. Its manifest SHA-256 is `4225e60044f000b16147e01f6ff165968523c1efd9647e57d9c7a6f5f5a27454`. The accepted inventory is the canonical 15-symbol universe with 45 model entries: one LAG_REGRESSION, ARIMA, and LSTM model for each symbol. Model binaries and metadata remain outside Git.

The manifest is the runtime inventory. The unified loader checks bundle version, entry identity, metadata identity, safe relative paths, binary and metadata SHA-256 values, training boundary, and row count before dispatch. LIR and ARIMA use the Phase 3B.2 authoritative joblib loader. LSTM dispatch imports its state-dict loader only on demand; that loader verifies the binary SHA before `torch.load(map_location="cpu", weights_only=True)`. The standard FastAPI import and LIR/ARIMA-only loading path stay PyTorch-free.

## Inference contract

LIR uses its frozen fitted model, causal features through the requested origin, and additive Close reconstruction. ARIMA appends actual closes after its training boundary with `refit=False`, then forecasts one step. LSTM forms the latest frozen-lookback sequence of observed absolute Close deltas, uses the persisted scaler and network without updating either, and reconstructs Close additively. All families must produce finite deltas, finite positive closes, and the next session from `PSETradingCalendar`.

No training, model selection, tuning, scaler fitting, artifact replacement, or online refit occurs in this phase. The evaluator performs a fixed-boundary replay against the immutable Phase 3B.2 `bundle_validation.json`, then performs a current-history shadow run. It writes no Forecast, ModelArtifact, or PipelineRun records and computes no new accuracy score.

## Candidate registration

`register_candidate_bundle` first requires complete 45/45 bundle verification and the exact accepted manifest SHA. It requires one active canonical company record for each symbol and exactly one ModelMetadata record for each runtime model code. It creates 45 ModelArtifact rows using manifest-relative artifact paths, exact metadata, and `is_active=False`. An identical registration is idempotent. Existing lineage conflicts fail closed; no silent updates occur. The service does not forecast, activate, or enable either runtime setting.

## Activation contract

The ORM and migration 0006 make inactive the default for new ModelArtifact rows. The migration changes only the server default and does not rewrite existing values; downgrade restores the prior active default.

Activation is a distinct transaction and requires all of the following: the accepted version and manifest SHA confirmations; complete bundle verification; a passing Phase 3B.3 evaluation receipt; `MODEL_ARTIFACT_ACTIVATION_ENABLED=true`; exactly 45 matching inactive candidate rows; and the canonical 15-by-3 company/family set. It verifies each row's hash, relative path, format, training boundary, row count, and source lineage against the bundle. In one transaction it deactivates older rows for the same company/model pairs, activates the exact candidate set, verifies 45 active rows, and commits. An error rolls the transaction back.

The activation CLI defaults to plan-only. Execution also requires `--execute` and exact version and manifest SHA confirmations. Evaluation never invokes activation. `MODEL_ARTIFACT_ACTIVATION_ENABLED` and `REAL_MODELS_ENABLED` remain false during acceptance; eligibility means `ELIGIBLE_FOR_ACTIVATION BUT_NOT_ACTIVATED`, not live serving.

## Serving lineage

Persistent real forecasting remains guarded by `REAL_MODELS_ENABLED`. It reads only manifest-listed artifacts and requires exactly one active ModelArtifact row for each requested company/model pair. The row must match the selected bundle, ModelMetadata association, format, safe relative path, artifact SHA, training boundary, row count, and source provenance. Serving does not register or activate artifacts. Missing, duplicate, inactive, or mismatched lineage fails closed.

## Evaluation outputs

The local evaluator requires the existing Phase 3B.2 `bundle_validation.json`; it validates 45 unique symbol/family records at origin 2026-10-01 and target 2026-10-02 and records the evidence SHA. It compares full-precision delta and Close forecasts with `math.isclose(rel_tol=1e-10, abs_tol=1e-8)`, then evaluates all 45 models against current canonical history. The activation plan and evaluation receipt are written outside Git beneath `~/pse-pulse-production-artifacts/phase3b3/2026.10.01-authoritative-v1/`.

No Azure resource is provisioned or deployed. Actual activation requires independent review of the implementation, evidence, commit, and CI, followed by separate explicit authorization.
