# Forecasting Model Porting & Inference Serving Plan

This document defines the architectural strategy for porting the three forecasting models (ARIMA, Lag-10 Linear Regression, and LSTM) from the official research repository into the **PSE Pulse — Personal Azure Edition** production architecture.

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
|            - lstm_model.onnx + lstm_scaler.joblib           |
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
|  Location: Linux Azure VM (FastAPI + ONNX Runtime)          |
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
| **Model Type** | Univariate Time Series ARIMA $(p, d, q)$ | Fitted Auto-ARIMA Parameters / Coefficients |
| **Training Engine**| `pmdarima.auto_arima` / `statsmodels` | Offline calibration fitting parameters per symbol |
| **Inference Engine**| Dynamic in-memory fitting | `statsmodels.tsa.arima.model.ARIMAResults` or lightweight recursive NumPy ARMA filter |
| **Memory Footprint**| High (during model identification) | Low ($< 30\text{ MB}$ for 15 companies) |
| **Latency Target**| $2,000 - 5,000\text{ ms}$ | $< 50\text{ ms}$ per symbol |
| **Artifact Format**| Ad-hoc Python pickle | JSON parameters + fitted autoregressive weights (`arima_params.json`) |

**Porting Action:**
- Isolate hyperparameter grid search to offline scripts.
- Export selected $(p, d, q)$ orders and recent residuals into a compact JSON artifact.
- Production runtime reads the last $k$ historical prices from PostgreSQL, applies the fixed difference and ARMA weights, and outputs the next-day point forecast with confidence intervals.

---

### 2.2 Model 2: Lag-10 Linear Regression (LIR)

| Property | Research Baseline | Personal Azure Production Design |
| :--- | :--- | :--- |
| **Model Type** | Ridge / OLS on 10 lag features | Scikit-learn Linear Regression Pipeline |
| **Features** | $[P_{t-1}, P_{t-2}, \dots, P_{t-10}]$ | Extracted dynamically from recent `daily_prices` |
| **Inference Engine**| Scikit-learn `predict()` | Scikit-learn or raw matrix dot-product in NumPy |
| **Memory Footprint**| Negligible ($< 5\text{ MB}$) | Negligible ($< 5\text{ MB}$) |
| **Latency Target**| $< 20\text{ ms}$ | $< 5\text{ ms}$ per symbol |
| **Artifact Format**| `.pkl` / `.joblib` | Scikit-learn `Pipeline` serialized via Joblib + checksums |

**Porting Action:**
- Train regression weights against the 2020-2026 bootstrap dataset.
- Port feature extractor (`backend/pipeline/features/feature_builder.py`) to query the preceding 10 trading sessions for any symbol.
- Execute inference using pre-loaded Joblib models or pure NumPy weight vectors.

---

### 2.3 Model 3: Long Short-Term Memory (LSTM)

| Property | Research Baseline | Personal Azure Production Design |
| :--- | :--- | :--- |
| **Model Type** | PyTorch / TensorFlow Multi-layer LSTM | ONNX Runtime CPU Inference Engine |
| **Input Shape** | $(N, 30, F)$ (30-day sequence, normalized) | $(1, 30, F)$ single symbol sequence |
| **Training Engine**| PyTorch `torch.nn.LSTM` with Adam optimizer | Offline training on GPU/development machine |
| **Inference Engine**| Full PyTorch runtime | **`onnxruntime`** (Lightweight C++ runtime with Python bindings) |
| **Memory Footprint**| $\sim 1.5 - 2.5\text{ GB}$ (PyTorch package) | $\sim 50 - 100\text{ MB}$ (ONNX Runtime) |
| **Latency Target**| $150 - 300\text{ ms}$ | $< 35\text{ ms}$ per symbol on CPU |
| **Artifact Format**| PyTorch `.pt` / `.pth` state dict | Optimized **`lstm_model.onnx`** + MinMax scaler Joblib |

**Critical Architectural Advantage:**
By exporting the PyTorch LSTM network to **ONNX (Open Neural Network Exchange)**, the production Azure VM does not need to install `torch` or `torchvision` (saving $> 1.8\text{ GB}$ of disk and virtual memory). ONNX Runtime provides deterministic, fast, hardware-optimized CPU scoring.

---

## 3. Artifact Storage & Versioning Strategy

Model artifacts are managed hierarchically in Azure Blob Storage:

```
azure-blob-storage/
└── models/
    ├── v1.0.0/
    │   ├── manifest.json               # Model hashes, training date, commit
    │   ├── arima/
    │   │   ├── ALI_arima.json
    │   │   └── ... (15 symbols)
    │   ├── lag_regression/
    │   │   └── lir_pipeline.joblib
    │   └── lstm/
    │       ├── lstm_model.onnx
    │       └── lstm_scaler.joblib
    └── v1.1.0/
        └── ...
```

### 3.1 Integrity & Verification Safeguards
1. **Manifest Checksumming:** Every model directory contains a `manifest.json` with SHA-256 hashes of all weights and parameters.
2. **Startup Verification:** On API startup, the artifact loader verifies the local cache against the manifest hashes before serving inference traffic.
3. **Graceful Fallback:** If a model artifact fails validation, the system falls back to the previous verified model version or marks the model provider as `DEGRADED`, preventing application crashes.

---

## 4. Database Schema & Forecast Provenance

Forecasts are stored transactionally in PostgreSQL:

```sql
CREATE TABLE forecast_records (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    model_code VARCHAR(32) NOT NULL,       -- 'ARIMA', 'LAG_REGRESSION', 'LSTM'
    model_version VARCHAR(32) NOT NULL,    -- 'v1.0.0'
    forecast_date DATE NOT NULL,           -- Target trade date (t + 1)
    base_date DATE NOT NULL,               -- Historical reference date (t)
    predicted_close NUMERIC(12, 4) NOT NULL,
    lower_bound NUMERIC(12, 4),
    upper_bound NUMERIC(12, 4),
    confidence_level NUMERIC(4, 2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_company_model_date UNIQUE (company_id, model_code, model_version, forecast_date)
);
```

### 4.1 Multi-Version Coexistence
The unique constraint includes `model_version`, allowing multiple model iterations (e.g., `v1.0.0` and `v1.1.0`) to coexist side-by-side. This facilitates:
- Head-to-head performance comparisons.
- Live canary deployments.
- Historical accuracy backtesting against materialized actual closing prices.

---

## 5. Implementation Roadmap (Phase 3)

1. **Step 1: Offline Export Tooling:** Create an offline pipeline to train and export artifacts (`arima_orders.json`, `lir_pipeline.joblib`, `lstm_model.onnx`).
2. **Step 2: ONNX Runtime Integration:** Add `onnxruntime` to backend requirements without adding PyTorch.
3. **Step 3: Inference Pipeline:** Implement `backend/pipeline/forecasting/engine.py` to pull recent prices, score all 15 symbols across the 3 models, and commit to `forecast_records`.
4. **Step 4: End-to-End Test Suite:** Verify end-to-end forecasting pipeline in CI with mock and real ONNX artifacts.
