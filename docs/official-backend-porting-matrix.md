# Official Backend Porting Matrix & Disposition Plan

This document establishes the official component inventory, categorization, and architectural porting strategy from the source repository:

- **Source Repository:** `https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git`
- **Pinned Source Commit:** `b8bf39f8e94729687c2e877dc164ea8a4f69e2b1`
- **Destination Repository:** `https://github.com/AlvinTubtub/pse-pulse-mmdc-project.git` (PSE Pulse — Personal Azure Edition)
- **Destination Branch:** `main`

---

## 1. Classification Categories & Disposition Definitions

Every module, script, and artifact group from the official backend codebase is classified into one of five rigorous disposition categories:

| Disposition Category | Definition | Architectural Rationale |
| :--- | :--- | :--- |
| **`PORT_NOW`** | Ported immediately in Phase 2B. Direct translation or core adaptation into clean production code. | Essential for canonical 15-company universe, historical bootstrap, database models, and migration provenance. |
| **`PORT_WITH_ADAPTER`** | Components to be ported in upcoming phases (Phase 3) using dedicated adapter layers. | Models and inference engines that need abstraction over storage (Azure Blob vs local disk) and configuration. |
| **`PORT_LATER`** | Components scheduled for subsequent phases (evaluation, backtesting, monitoring). | Secondary pipelines not required for baseline EOD ingestion or inference serving. |
| **`REFERENCE_ONLY`** | Academic research benchmarks, exploratory analysis, UAT surveys, and historical validation logs. | Valuable for domain context and verification, but not part of operational runtime software. |
| **`EXCLUDE_FROM_AZURE_RUNTIME`** | Heavy training code (PyTorch, TensorFlow, hyperparameter loops), local scratch, and monolithic CLI scripts. | Excluded from the production Azure VM runtime to prevent resource contention, memory bloat, and cost overrun. |

---

## 2. Comprehensive Component Inventory & Porting Matrix

### 2.1 Core Source Modules (`src/`)

| Source Path | Purpose | Dependencies | Disposition | Destination Equivalent | Required Adaptations & Production Suitability |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `src/data/loader.py` | Loads raw CSVs for companies | pandas, numpy | `PORT_NOW` | `backend/pipeline/bootstrap/official_repo_csv.py` | Rewritten to stream and validate with Pydantic/dataclasses, SHA-256 hashing, and batch DB upsert rather than memory DataFrame. |
| `src/data/calendar.py` | Trading calendar & market holiday logic | pandas, datetime | `PORT_NOW` | `backend/pipeline/ingest/calendar.py` | Adapted into a lightweight calendar utility without heavy pandas dependency. |
| `src/data/validator.py` | Validates OHLCV relationships and non-nulls | pandas | `PORT_NOW` | `backend/pipeline/validation/data_validator.py` | Adapted to validate `EODQuote` / `HistoricalQuote` before persistence. Enforces strict high/low bounds and the official raw data validator volume contract: finite nonnegative numeric (preserving fractional values, not integer-only). |
| `src/data/quality_screening.py` | Data quality rules & corporate action screening | pandas, numpy | `PORT_LATER` | `backend/pipeline/validation/quality_screening.py` | Slated for Phase 3 ingestion quality pipeline; detects unusual splits or dividend price jumps. |
| `src/data/split.py` | Train/validation/holdout split logic | numpy | `PORT_LATER` | `backend/pipeline/features/split.py` | Used only during model training runs. Kept offline. |
| `src/features/regression_features.py` | Lag feature generation (lags 1-5, rolling means) | pandas, numpy | `PORT_WITH_ADAPTER` | `backend/pipeline/features/feature_builder.py` | Features generated incrementally in database or lightweight pipeline for inference. |
| `src/features/targets.py` | Target calculation (next-day close, returns) | pandas, numpy | `PORT_WITH_ADAPTER` | `backend/pipeline/features/targets.py` | Adapted to support rolling target verification in database. |
| `src/models/base.py` | Abstract forecasting model interface | abc, numpy | `PORT_WITH_ADAPTER` | `backend/app/forecasting/base.py` | Extended in Phase 1-2 to interface with database repository and versioned artifact registries. |
| `src/models/arima.py` | ARIMA(p,d,q) model definition & fit | statsmodels, pmdarima | `PORT_WITH_ADAPTER` | `backend/app/forecasting/providers/arima.py` | Production inference uses pre-trained serialized model coefficients; statsmodels fit restricted to offline worker. |
| `src/models/lag_regression.py` | Linear regression on lagged price features | scikit-learn | `PORT_WITH_ADAPTER` | `backend/app/forecasting/providers/lag_regression.py` | Ported for inference using joblib/pickle serialized pipelines. Lightweight and safe for production VM. |
| `src/models/lstm.py` | PyTorch/TensorFlow LSTM neural network | torch / tensorflow | `PORT_WITH_ADAPTER` | `backend/app/forecasting/providers/lstm.py` | Model architecture ported for inference only (ONNX Runtime or PyTorch CPU inference); training code strictly isolated. |
| `src/inference/next_day.py` | Next-day forecasting orchestration | models, features | `PORT_WITH_ADAPTER` | `backend/pipeline/forecasting/engine.py` | Adapted to write forecast records into PostgreSQL `forecast_records` table with model versions and confidence metrics. |
| `src/inference/predictor.py` | Generic model scoring wrapper | numpy | `PORT_WITH_ADAPTER` | `backend/app/forecasting/registry.py` | Adapts inference requests to registered forecasting providers. |
| `src/ingestion/pipeline.py` | Ingestion workflow orchestration | pandas, requests | `PORT_NOW` | `backend/pipeline/runner.py` | Replaced by transaction-safe atomic pipeline runner supporting DQR and bootstrap sources. |
| `src/ingestion/parser.py` | EOD report text and table parser | regex, pdfplumber | `PORT_NOW` | `backend/pipeline/ingest/providers/pse_dqr_file.py` | Replaces custom regex parsing with deterministic text/PDF DQR extraction and SHA-256 verification. |
| `src/ingestion/downloader.py` | Network download utilities | requests | `EXCLUDE_FROM_AZURE_RUNTIME` | None | Scraping utilities excluded to comply with official file-only ingestion and ethical data policy. |
| `src/artifacts/manager.py` | Local filesystem artifact registry | os, json, pickle | `PORT_WITH_ADAPTER` | `backend/app/services/artifact_manager.py` | Adapted to support dual backends: local filesystem (development) and Azure Blob Storage (production). |
| `src/artifacts/production_manifest.py`| Manifest metadata tracker | json, hashlib | `PORT_NOW` | `backend/bootstrap-manifests/` & DB `market_data_imports` | Production manifests generated deterministically and tracked in database provenance. |
| `src/ledger/store.py` | Forecast audit ledger | sqlite / json | `PORT_NOW` | PostgreSQL `forecast_records` | Integrated directly into PostgreSQL transactional database with Alembic schema management. |
| `src/monitoring/drift.py` | Distribution drift detection (KS test, PSI) | scipy, numpy | `PORT_LATER` | `backend/app/monitoring/drift_service.py` | Scheduled for Phase 4 operational monitoring service. |
| `src/evaluation/metrics.py` | Directional accuracy, MAPE, RMSE calculations | numpy | `PORT_NOW` | `backend/app/schemas/` & evaluation endpoints | Integrated for model performance tracking and frontend presentation. |
| `src/evaluation/statistical_tests.py`| Diebold-Mariano and DM test suites | scipy, numpy | `PORT_LATER` | `backend/pipeline/evaluation/` | Statistical validation tests retained for periodic model re-certification. |

---

### 2.2 Scripts & Workflows (`scripts/`)

| Source Path | Purpose | Dependencies | Disposition | Destination Handling |
| :--- | :--- | :--- | :--- | :--- |
| `scripts/train_all.py` | Full universe retraining script | torch, statsmodels, sklearn | `EXCLUDE_FROM_AZURE_RUNTIME` | Run only in isolated offline training environments (GitHub Actions or Azure ML job). Artifacts exported to Blob Storage. |
| `scripts/forecast_all.py` | Batch next-day forecast generator | src/inference | `PORT_WITH_ADAPTER` | Adapted into `backend/pipeline/runner.py --forecast-only` flag. |
| `scripts/update_eod.py` | Daily EOD refresh loop | src/ingestion | `PORT_NOW` | Fully superseded by `backend/pipeline/runner.py --source-file`. |
| `scripts/reset_artifacts.py` | Deletes and resets local model files | os, shutil | `EXCLUDE_FROM_AZURE_RUNTIME` | Manual destructive operations prohibited in managed production environments. |
| `scripts/export_research_results.py`| Exports tables to CSV for thesis | pandas | `REFERENCE_ONLY` | Not needed for live production runtime. |
| `scripts/pse_corporate_action_screening_30pct.py` | Screens 30% price shocks | pandas | `REFERENCE_ONLY` | Historical data audit script; insights incorporated into documentation. |
| `scripts/validate_frontend_forecasts.py` | Validates API contract against UI | requests, json | `PORT_NOW` | Covered by `backend/tests/` integration test suite. |

---

### 2.3 Research Results & Documentation Artifacts (`research-result/`)

| Directory / Files | Contents | Disposition | Justification |
| :--- | :--- | :--- | :--- |
| `research-result/*.csv` | Historical metrics, principal winners, holdout forecasts | `REFERENCE_ONLY` | Benchmark data used to calibrate baseline forecasts and validation metrics. |
| `research-result/corporate_action_screening/` | Screening logs and ticker consistency checks | `REFERENCE_ONLY` | Audit reference confirming corporate action integrity across 2020-2026. |
| `research-result/system_testing/` | Cross-browser test results, Lighthouse scores | `REFERENCE_ONLY` | Academic chapter evidence; replaced by Playwright CI workflows in destination. |
| `research-result/uat/` | User acceptance testing notebooks and survey scores | `REFERENCE_ONLY` | Human evaluation documentation; archived as academic baseline. |

---

## 3. Production Runtime Separation Strategy

A critical principle of the Personal Azure Edition architecture is the **strict separation between offline model training and production serving**:

```
+-------------------------------------------------------------+
|              OFFLINE ENVIRONMENT (Local / Azure ML)         |
|  - Full dataset access (2020 - 2026)                        |
|  - Heavy dependencies: PyTorch, TensorFlow, CUDA, pmdarima  |
|  - Hyperparameter sweeps, cross-validation, refitting       |
|  - Produces: model.onnx, arima_params.json, scaler.joblib   |
|  - Uploads artifacts -> Azure Blob Storage ($web / models)  |
+-------------------------------------------------------------+
                              |
                     Artifact Deployment
                              v
+-------------------------------------------------------------+
|              PRODUCTION SERVING (Azure B1s / B2s VM)        |
|  - Lightweight dependencies: FastAPI, SQLAlchemy, ONNX/NumPy|
|  - Consumes serialized artifacts from Azure Blob Storage    |
|  - Fast, bounded CPU inference (<150ms per stock)           |
|  - Zero PyTorch training overhead, zero CUDA dependencies    |
|  - Strict memory limit (<1 GB RAM usage)                    |
+-------------------------------------------------------------+
```

### 3.1 Benefits of Runtime Separation
1. **Cost Efficiency:** Running inference on a small B1s/B2s burstable VM avoids the heavy hourly cost of GPU compute or large RAM instances.
2. **Stability:** Decoupling training from serving prevents out-of-memory (OOM) crashes and CPU starvation on the public-facing API.
3. **Security:** Training scripts often execute dynamic code or unpinned external dependencies; production serving images remain minimal, immutable, and fully audited.
