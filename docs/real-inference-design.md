# Real Inference Foundation & Execution Architecture

## 1. Executive Summary

This document details the real forecasting architecture ported into PSE Pulse in Phase 3A. It adapts official research logic from `Capstone2-A4103-DigitalDelvers-SY26-27` (`b8bf39f8e94729687c2e877dc164ea8a4f69e2b1`) to provide production-grade next-session forecasting for Philippine equities under strict memory and safety constraints.

---

## 2. Core Inference Models

### 2.1 Lag-Informed Regression (LIR / LASSO)
- **Target Variable:** One-step price delta:
  $$\Delta \text{Close}_{t+1} = \text{Close}_{t+1} - \text{Close}_t$$
- **Feature Space:** 47 deterministic causal features (return lags 1–20, rolling return moments 5/10/20, volume ratios 5/20, log volume, volume change, price spreads, RSI(14), EMA(12, 26), MACD(12, 26, 9), and Bollinger Bands(20, 2)).
- **Causality:** Every predictor utilizes strictly observations available at or before trading date $t$ (zero future lookahead). Indicator warm-up excludes early unstable rows.
- **Dimensionality Reduction:** Statistically significant return lags are selected using fold-local Sample Partial Autocorrelation (PACF) via Yule-Walker with sample-variance (`ywmle`).
- **Regularization:** Scaled with `StandardScaler` (fit on training observations only) and fit with cyclic coordinate-descent `Lasso`.

### 2.2 Autoregressive Integrated Moving Average (ARIMA)
- **Target Variable:** Price level ($\text{Close}_{t+1}$).
- **Specification:** Order $(p, d, q) = (1, 1, 0)$ with deterministic trend policy ($n$ for differenced series).
- **Online State Evolution:** Rather than refitting on every new daily quote, the production runtime calls:
  ```python
  updated_model = fitted_model.append_actual(new_close_price)
  ```
  This updates the underlying state-space representation and Kalman filter without re-estimating autoregressive coefficients.

---

## 3. PSE Trading Calendar & Session Resolution

Next-session forecasting requires strictly resolving the next legal Philippine Stock Exchange (PSE) trading session:
- **Weekend Invalidation:** Saturday and Sunday are never trading days.
- **Holiday Registry:** `backend/app/forecasting/real/pse_holidays.py` contains verified PSE and SCCP closure dates from 2020 through 2026 based on official PSE memoranda and settlement circulars.
- **Roll Rule:** A Friday market close at Date[t] resolves to the next open session Date[t+1] (typically Monday, or Tuesday if Monday is a recognized public holiday).

---

## 4. Atomic 30-Forecast Persistence & Idempotency

Inference across the 15 tracked companies generates exactly 30 forecasts (15 equities $\times$ 2 models):
- **All-or-Nothing Transaction:** All 30 forecasts and their associated `ModelArtifact` foreign keys are staged within a single database transaction. If any company or model encounters an inference failure, data corruption, or boundary mismatch, the entire transaction calls `db.rollback()`.
- **Run Audit Record:** Execution creates a `PipelineRun` record. On success, `status = "COMPLETED"` and `forecasts_generated = 30`. On failure, `status = "FAILED"` with the exact stack trace logged.
- **Immutable Idempotency:** Running the pipeline multiple times for the same market session returns `UNCHANGED` (0 updates, 0 inserts) when predictions are identical. Differing values raise `RealForecastIntegrityError` and trigger full rollback, preventing untracked overwrites.

---

## 5. Offline Refit and Online Pipeline CLIs

### 5.1 Offline Model Refit Tool
```bash
python -m backend.app.forecasting.real.training.refit \
    --symbols BPI,SM \
    --bundle-version 2026.03.01-v1 \
    --output-dir backend/artifacts/models
```

### 5.2 Production Pipeline Runner
```bash
python -m backend.pipeline.forecasting.real_runner \
    --artifacts-dir backend/artifacts/models \
    --bundle-version 2026.03.01-v1 \
    --dry-run
```
