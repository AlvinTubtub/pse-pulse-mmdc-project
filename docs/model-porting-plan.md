# Forecasting Model Porting & Inference Serving Plan

This document defines the architectural strategy for porting the three forecasting models (ARIMA, Lag-Informed Regression, and LSTM) from the official research repository into the **PSE Pulse — Personal Azure Edition** production architecture.

- **Source Repository:** `https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git` (`b8bf39f8e94729687c2e877dc164ea8a4f69e2b1`)
- **Target Phases:** Phase 2B (Planning & Foundation) $\to$ Phase 3 (Engine Porting & Scoring Pipeline)

---

## 1. Architectural Philosophy: Decoupled Training vs Inference

In the official research repository, model training, cross-validation, and inference were tightly coupled in monolithic scripts with heavy PyTorch, statsmodels, and scikit-learn dependencies. 

For the personal Azure deployment, we enforce a **strict separation of concerns**:

```
+-------------------------------------------------------------+
|              OFFLINE TRAINING WORKFLOW                      |
|  Location: Local Developer Machine / GitHub Actions Runner  |
|  Compute:  High CPU / GPU                                   |
|  Input:    Full Historical Daily OHLCV (2020-2026)          |
|  Output:   Serialized Model Artifacts                       |
|            - arima_orders.json                              |
|            - lir_pipeline.joblib                            |
|            - lstm.pt state_dict + metadata (offline only)   |
|            - manifest.json (SHA-256 Checksums)              |
+-------------------------------------------------------------+
                              |
                     Artifact Deployment
                              v
+-------------------------------------------------------------+
|              AZURE BLOB STORAGE ($web / models / v1/)       |
|  - Immutable versioned storage                              |
|  - Read-only shared access signature (SAS) or system identity|
+-------------------------------------------------------------+
                              |
                    Model Loader / Cache
                              v
+-------------------------------------------------------------+
|              AZURE PRODUCTION SERVING VM (B1s / B2s)        |
|  Location: Linux Azure VM (FastAPI; LSTM not activated)    |
|  Compute:  Burstable 1-2 vCPU, <= 1-2 GB RAM                |
|  Execution: Inference ONLY, 0 Training Cycles               |
|  Speed:    < 150 ms per symbol                              |
|  Storage:  PostgreSQL Database (forecast_records table)     |
+-------------------------------------------------------------+
```

---

## 2. Model-by-Model Porting Specifications

### 2.1 Model 1: Autoregressive Integrated Moving Average (ARIMA)

| Property | Research Baseline | Personal Azure Production Design |
| :--- | :--- | :--- |
| **Model Type** | Univariate Time Series ARIMA $(p, d, q)$ with explicit trend | Native `FittedArimaModel` wrapping `statsmodels.tsa.arima.model.ARIMAResults` |
| **Training Engine**| `statsmodels.tsa.arima.model.ARIMA` with optimizer retry loop | Offline calibration fitting parameters per symbol with convergence proof |
| **Inference Engine**| Dynamic state update via `result.append(actual, refit=False)` | `result.append([actual], refit=False)` + `forecast_one()` (no parameter refitting) |
| **Operational Profile**| State-space recursion without refitting | Bounded one-step evaluation |
| **Artifact Format**| `.joblib` fitted result + companion `.metadata.json` | Checksum-verified destination `.joblib` + `.metadata.json` |

**Authentic Implementation Invariants:**
- Uses standard `statsmodels.tsa.arima.model.ARIMA` (never `pmdarima.auto_arima`).
- Explicit candidate specifications define order $(p, d, q)$ and deterministic trend ($n, c, t, ct$).
- Optimization executes with configured retry iterations (e.g. 200, 1,000) and extracts optimizer convergence evidence (`mle_retvals`).
- In-flight inference consumes new historical observations through state updates (`append(actual, refit=False)`), completely avoiding expensive online parameter re-estimation.
- Forecast generation produces strictly one next-session Close forecast per step with finite check validation.

---

### 2.2 Model 2: Lag-Informed Regression (LIR)

| Property | Research Baseline | Personal Azure Production Design |
| :--- | :--- | :--- |
| **Model Type** | Causal OHLCV Feature Pipeline + PACF + StandardScaler + LASSO | Native `LagRegressionModel` wrapping `StandardScaler` + `Lasso(selection="cyclic")` |
| **Target Variable** | Next-session Close price delta: $Y_{t+1} = P_{t+1} - P_t$ | Delta target ($Y_{t+1}$); Reconstructs $\hat{P}_{t+1} = P_t + \hat{Y}_{t+1}$ |
| **Features** | 47 Causal Candidate Features (returns, volume, spreads, RSI, EMA, MACD, Bollinger) | Pre-computed causal features, filtered by fold/fit PACF return lags |
| **Inference Engine**| `StandardScaler.transform()` + `Lasso.predict()` | Origin feature extraction + `predict_delta()` + `reconstruct_close()` |
| **Operational Profile**| Linear dot-product with StandardScaler transform | Bounded deterministic feature extraction |
| **Artifact Format**| `.joblib` fitted bundle + companion `.metadata.json` | Checksum-verified destination `.joblib` + `.metadata.json` |

**Authentic Implementation Invariants:**
- LIR is NOT a simple 10-price raw regression or Ridge model.
- Candidate features follow a strict causal taxonomy:
  - 20 daily return lags (`return_lag_1` to `return_lag_20`)
  - Rolling return statistics (mean and standard deviation for windows 5, 10, 20)
  - Volume transformations (`volume_log`, 1-day change, rolling ratios and z-scores for windows 5, 20)
  - Price-range indicators (`range_pct`, `open_close_spread_pct`, `close_location_in_range`)
  - Relative moving averages (`close_relative_sma_5`, `10`, `20`)
  - Technical indicators: RSI (period 14), fast/slow EMA (12, 26), MACD (signal 9, histogram, relatives), Bollinger Bands (window 20, 2 std dev)
- PACF Return Lag Selection: Selects statistically significant return lags from training returns ($|r_k| > 1.96 / \sqrt{N}$ via Yule-Walker MLE) while retaining all non-return-lag indicators.
- StandardScaler normalizes features; Scikit-learn `Lasso` fits on normalized features with cyclic coordinate descent and preselected $\alpha$.
- Reconstructs next-day Close price strictly from origin Close + predicted delta: $\hat{P}_{t+1} = P_t + \Delta_{t+1}$. Rejects non-positive or non-finite prices.

---

### 2.3 Model 3: Long Short-Term Memory (LSTM) — Phase 3B.1 foundation

| Property | Research Baseline | Personal Azure Production Design (Phase 3B) |
| :--- | :--- | :--- |
| **Model Type** | Univariate Close-delta LSTM | Canonical PyTorch state-dict implementation |
| **Input Shape** | $(N, L, 1)$ sequence of Close price deltas | Sequence of latest Close deltas |
| **Training Engine**| PyTorch `torch.nn.LSTM` with Adam optimizer | Offline training on development machine |
| **Inference Engine**| PyTorch state dict | Safe offline reload foundation; no production activation |
| **Status**| **Phase 3B.1 foundation** | **All-15 bundle and production activation remain deferred** |

---

## 3. Artifact Storage & Versioning Strategy

Phase 3A development artifacts may use the configured local artifact store. The Phase 3B.2 acceptance bundle is generated only under an external persistent root such as `~/pse-pulse-production-artifacts/`; it is never written into the repository.

```
~/pse-pulse-production-artifacts/
└── 2026.10.01-authoritative-v1/
    ├── manifest.json                   # Bundle metadata, file SHAs, source commit
    ├── ALI/
    │   ├── lag_regression.joblib       # Fitted LIR wrapper
    │   ├── lag_regression.metadata.json# Parameters, coefficients, scaler, SHA-256
    │   ├── arima.joblib                # Fitted ARIMA wrapper
    │   ├── arima.metadata.json         # Order, trend, parameters, fit attempts, SHA-256
    │   ├── lstm.pt                     # CPU-safe PyTorch state dictionary
    │   └── lstm.metadata.json          # LSTM spec, epoch evidence, provenance, SHA-256
    └── ... (15 symbols)
```

### 3.1 Integrity & Verification Safeguards
1. **SHA-256 Checksumming:** Every model binary has its cryptographic SHA-256 hash verified against metadata **BEFORE** `joblib.load()` is executed.
2. **Safe Path Checking:** Artifact paths are verified to remain within designated canonical boundaries, preventing directory traversal attacks.
3. **Training Boundary Verification:** Historical observations must match the model's `trained_through` date and `data_row_count` before inference is permitted.
4. **Fail-Closed Loading:** Any tampering, missing file, or metadata mismatch immediately aborts inference without executing unverified serialized code.

---

## 4. Database Model-Artifact Lineage & Forecast Schema

Database lineage connects model binaries, execution runs, and forecasts:

```
┌─────────────────┐       ┌─────────────────┐
│    companies    │       │ model_metadata  │
└────────┬────────┘       └────────┬────────┘
         │                         │
         │  ┌───────────────────┐  │
         └──┤  model_artifacts  ├──┘
            └─────────┬─────────┘
                      │
            ┌─────────┴─────────┐
            │     forecasts     │
            └───────────────────┘
```

### 4.1 Schema Fields
- **`model_artifacts` Table (Alembic 0005):**
  - `id`: UUID primary key
  - `company_id`: Foreign key to `companies.id`
  - `model_metadata_id`: Foreign key to `model_metadata.id`
  - `bundle_version`: e.g. `v1.0.0`
  - `artifact_format`: `joblib`
  - `artifact_path`: Relative safe path within artifact storage
  - `artifact_sha256`: Cryptographic SHA-256 of the binary artifact
  - `trained_through`: End date of training data
  - `data_row_count`: Exact row count of training history
  - `hyperparameters_json`: JSON-encoded model parameters
  - `source_repository` & `source_commit`: Provenance lineage
  - `created_at`: Timezone-aware timestamp
  - `is_active`: Operational activation flag

- **`forecasts` Table Extensions (Alembic 0005):**
  - `model_artifact_id`: Nullable foreign key to `model_artifacts.id`
  - `origin_date`: Historical reference date ($t$)
  - `predicted_delta`: Predicted next-session price change ($P_{t+1} - P_t$)
  - `target_date`: Target forecast date ($t+1$)
  - `predicted_price`: Reconstructed close price ($P_t + \Delta$)

---

## 5. Implementation Roadmap

1. **Phase 3A — Complete:** Real LIR and ARIMA engines, causal features, trading calendar, refit primitives, safe artifact loading, database lineage, and acceptance.
2. **Phase 3B.1 — Complete:** Pin and validate the official selected-configuration snapshot; port the canonical univariate PyTorch LSTM and safe state-dict artifact foundation.
3. **Phase 3B.2 — Candidate bundle generation:** Build and verify all 45 authoritative artifacts for the canonical 15 companies. This phase does not activate artifacts or persist forecasts.
4. **Phase 3B.3 — Deferred:** Independently evaluate the candidate bundle and gate any real forecast activation or Azure deployment.

The production application dependencies remain lightweight: PyTorch is isolated in `backend/requirements-lstm.txt` and the dedicated CPU LSTM CI job. The Phase 3A `backend/requirements-models.txt` remains unchanged. ONNX conversion and `onnxruntime` are deferred pending separate review after canonical PyTorch parity is accepted.
