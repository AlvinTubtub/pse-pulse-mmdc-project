# Model Artifact Contract & Lineage Specification

## 1. Purpose & Scope

This specification defines the cryptographic and structural contract for production model artifacts in PSE Pulse. In Phase 3A, the engine ports official research models (Lag-Informed Regression / LASSO and ARIMA) and formalizes the serialization format, metadata companion schema, pre-deserialization SHA-256 verification, and database lineage tracking.

---

## 2. Artifact Directory Structure

Model artifacts are partitioned into versioned bundles under `MODEL_ARTIFACTS_DIR` (default: `backend/artifacts/models/`):

```text
backend/artifacts/models/
└── {bundle_version}/                     # e.g., 2026.03.01-v1
    ├── {SYMBOL}/                         # e.g., BPI
    │   ├── lag_regression.joblib         # Serialized LIR estimator & scaler
    │   ├── lag_regression.metadata.json  # Companion metadata with SHA-256
    │   ├── arima.joblib                  # Serialized ARIMA state
    │   └── arima.metadata.json           # Companion metadata with SHA-256
    └── ...
```

---

## 3. Companion Metadata JSON Contract

Every `.joblib` binary MUST be accompanied by a strictly typed `{model_code}.metadata.json` file. Deserialization (`joblib.load()`) is **strictly forbidden** until this metadata is validated and the binary's cryptographic checksum is verified.

### 3.1 Metadata Schema

```json
{
  "schema_id": "pse-pulse.production-model",
  "schema_version": 1,
  "implementation_version": "pse-pulse-v1",
  "symbol": "BPI",
  "model_code": "LAG_REGRESSION",
  "model_version": "2026.03.01-v1",
  "trained_through": "2026-10-01",
  "data_row_count": 1649,
  "artifact_format": "joblib",
  "artifact_filename": "lag_regression.joblib",
  "artifact_sha256": "b62882cf3812e922efa14c908db32808be487a542dc6182f6773acca4d977b51",
  "hyperparameters": {
    "alpha": 0.001,
    "feature_names": ["return_lag_1", "return_lag_2", "rsi_14", "..."],
    "pacf_selected_lags": [1, 2, 5],
    "hyperparameter_regime": "TEST_ONLY",
    "test_only_smoke": true
  },
  "created_at": "2026-10-02T19:25:14.612000+08:00",
  "source_repository": "AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27",
  "source_commit": "b8bf39f8e94729687c2e877dc164ea8a4f69e2b1",
  "historical_data_source_repository": "AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27",
  "historical_data_source_commit": "b8bf39f8e94729687c2e877dc164ea8a4f69e2b1"
}
```

---

## 4. Fail-Closed Cryptographic Verification Rules

To protect against arbitrary bytecode execution vulnerabilities inherent in Python object deserialization, `backend/app/forecasting/real/artifacts/loader.py` enforces a 7-step fail-closed verification pipeline:

1. **Path Traversal Check:** Ensures `directory` and `artifact_filename` resolve strictly within the designated symbol directory.
2. **JSON Schema Validation:** Verifies `schema_id == "pse-pulse.production-model"`, `schema_version == 1`, matching symbol, and model code.
3. **Hyperparameter Contract:** Confirms presence of model-specific parameters:
   - For LIR: `alpha`, `feature_names`, `pacf_selected_lags`.
   - For ARIMA: `order`, `trend`.
4. **Binary Existence & Pre-Hashing:** Computes streaming SHA-256 hash across the serialized `.joblib` binary in 1 MB blocks.
5. **Cryptographic Checksum Equality:** Compares computed SHA-256 against `metadata["artifact_sha256"]`. If mismatched, raises `ModelArtifactCompatibilityError` and aborts immediately without calling `joblib.load()`.
6. **Deserialization Defense:** ONLY after all checks pass is `joblib.load()` executed.
7. **Post-Load State Verification:** Confirms loaded in-memory object instance matches expected types (`LIRFittedModel` or `FittedArimaModel`) and hyperparameters.

---

## 5. Database Lineage Schema (Alembic Revision 0005)

### 5.1 `model_artifacts` Table

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(36)` | PK, UUID | Unique artifact registration ID |
| `company_id` | `INTEGER` | FK (`companies.id`), NOT NULL | Target equity |
| `model_metadata_id` | `INTEGER` | FK (`model_metadata.id`), NOT NULL | Model family reference |
| `bundle_version` | `VARCHAR(50)` | NOT NULL | Artifact bundle version identifier |
| `artifact_format` | `VARCHAR(30)` | NOT NULL, DEFAULT `'joblib'` | Serialization format |
| `artifact_path` | `VARCHAR(500)` | NOT NULL | Filesystem / blob path |
| `artifact_sha256` | `VARCHAR(64)` | NOT NULL, INDEX | Cryptographic binary checksum |
| `trained_through` | `DATE` | NOT NULL | Training cutoff date |
| `data_row_count` | `INTEGER` | NOT NULL | Number of historical rows used |
| `hyperparameters_json` | `TEXT` | NOT NULL | JSON serialization of hyperparameters |
| `source_repository` | `VARCHAR(500)` | NOT NULL | Research origin repository |
| `source_commit` | `VARCHAR(40)` | NOT NULL | Research baseline commit SHA |
| `historical_data_source_repository` | `VARCHAR(500)` | NOT NULL | Historical OHLCV source repository |
| `historical_data_source_commit` | `VARCHAR(40)` | NOT NULL | Historical OHLCV source commit SHA |
| `created_at` | `DATETIME` | NOT NULL | Timestamp of artifact persistence |
| `is_active` | `BOOLEAN` | NOT NULL, DEFAULT `1` | Active flag |

### 5.2 `forecasts` Table Lineage Additions

- `model_artifact_id`: Nullable foreign key to `model_artifacts.id`. Enforced for all real forecasts (`is_demo=False`).
- `origin_date`: Historical date of the last known OHLCV observation (Date[t]).
- `predicted_delta`: Projected close price change (`predicted_close - origin_close`).
- `is_demo`: Set to `False` for production real model forecasts.

---

## 6. Immutability & Safety Gate Rules

### 6.1 Real Forecast Immutability
Real forecasts are audited records. Overwrites and updates via `--force` are strictly forbidden:
- **Identity:** A forecast is identified by `(company_id, model_artifact_id, origin_date, target_date)`.
- **Identical Rerun:** If an identical forecast exists for the same target, execution returns `UNCHANGED` (0 inserts, 0 updates).
- **Integrity Enforcement:** If incoming values differ (price, delta, origin, artifact), `RealForecastIntegrityError` is raised and the transaction is atomically rolled back.

### 6.2 Safety Gate Rule
Real model training and inference pipelines are strictly gated by `REAL_MODELS_ENABLED` in `backend/app/config.py`:
- Default: `REAL_MODELS_ENABLED = False`.
- In production (`ENVIRONMENT=production`) and development, invoking `RealForecastService` raises `RealModelsDisabledError` if `REAL_MODELS_ENABLED` is false.
- There is no runtime bypass flag; configuration must be set intentionally.
