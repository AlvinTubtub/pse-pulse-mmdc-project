# Phase 3A.2 Official Methodology Parity Matrix

Reference: uploaded immutable archive `Capstone2-A4103-DigitalDelvers-SY26-27-main (2).zip`.

- Repository identity declared by the task: `https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git`
- Declared source commit: `b8bf39f8e94729687c2e877dc164ea8a4f69e2b1`
- Source mode: uploaded immutable archive (the ZIP has no `.git`; the commit identity is declared, not independently verified)
- Destination base: `main` at `b87ef22c240dd64ef459bccef952062e76b0d5b4`
- ZIP SHA-256: `25c3fad70e6d1894a4b284f4e97fe595e53bfc0ea4de4df4891de8a12159584d`

Dispositions describe the implementation as it stands in Phase 3A.2. Adapter changes are limited to destination data types, persistence, artifact schema, and calendar boundaries; the model mathematics must remain the same.

| Official ZIP path | Destination path | Responsibility | Disposition | Exact parity requirement | Intentional adaptation |
| --- | --- | --- | --- | --- | --- |
| `backend/config/model_config.py` | `backend/app/forecasting/real/config.py` | Feature, LIR, and ARIMA defaults | `PORT_EXACT_LOGIC` | 20 return lags; rolling windows 5/10/20; volume windows 5/20; RSI 14; EMA 12/26; MACD signal 9; Bollinger 20; raw price lags empty; LASSO max_iter 100000, tol 1e-7, zero tolerance 1e-12; ARIMA retries 200/1000 | Destination module names and API settings only |
| `backend/config/pse_holidays.py` | `backend/app/forecasting/real/pse_holidays.py` | PSE closure dates | `PORT_EXACT_LOGIC` | Preserve the source date set and open-session exceptions | None |
| `backend/src/data/calendar.py` | `backend/app/forecasting/real/calendar.py` | PSE next-session calculation | `PORT_WITH_AZURE_ADAPTER` | Same session/holiday rules and computed next session | Destination timezone/settings interface |
| `backend/src/features/targets.py` | `backend/app/forecasting/real/domain.py` | Date[t] to Date[t+1] labels | `PORT_EXACT_LOGIC` | `target_delta = target.close - origin.close` | Destination OHLCV type |
| `backend/src/features/regression_features.py` | `backend/app/forecasting/real/features/regression_features.py` | Causal ordered candidate feature calculation | `PORT_EXACT_LOGIC` | Same formulas, warmup, causal cutoff, deterministic names/order. Defaults produce 47 features: 20 return lags, 27 non-lag features, 0 raw-close lags | Destination domain types and errors only |
| `backend/src/models/base.py` | `backend/app/forecasting/real/models/base.py` | Model interface and close reconstruction | `PORT_EXACT_LOGIC` | LIR predicts absolute Close delta; close is origin plus delta | Destination output type |
| `backend/src/models/lag_regression.py` | `backend/app/forecasting/real/models/lag_regression.py` | Scaled LASSO fit/predict and metadata | `PORT_EXACT_LOGIC` | StandardScaler then sklearn Lasso; configured alpha/iterations/tolerance; preserve coefficient threshold and fit metadata | None to mathematics |
| `backend/src/training/cross_validation.py` | `backend/app/forecasting/real/training/cross_validation.py` | Expanding folds and PACF lag selection | `PORT_EXACT_LOGIC` | Training-only PACF, statsmodels `pacf(method="ywmle")`, source max lag/significance rule and source lag order | None |
| `backend/src/training/train_lir.py` | `backend/app/forecasting/real/training/refit_lir.py` | Fold-local PACF and production LIR fit | `PORT_WITH_AZURE_ADAPTER` | Fit only on causal training observations; preserve selected return lag ordering, LASSO, scaler, target and fit metadata | Refit entry point accepts destination history/config; research tuning orchestration is not run during inference |
| `backend/src/models/arima.py` | `backend/app/forecasting/real/models/arima.py` | Statsmodels ARIMA and state updates | `PORT_EXACT_LOGIC` | Explicit `(p,d,q)` and trend; retry iterations; inspect convergence; require confirmed convergence; finite/positive forecast; append actual with `refit=False`; one-step forecast | None to model method |
| `backend/src/training/train_arima.py` | `backend/app/forecasting/real/training/refit_arima.py` | Candidate fit/evaluation and selected production refit | `PORT_WITH_AZURE_ADAPTER` | Preserve selected specification and statsmodels fitting/convergence semantics | Destination refit result/metadata type |
| `backend/src/training/production_refit.py` | `backend/app/forecasting/real/training/refit.py`; `backend/app/forecasting/real/artifacts/writer.py` | Refit orchestration and artifact persistence | `PORT_WITH_AZURE_ADAPTER` | Preserve trained-through boundary, model parameters, and lineage; no LSTM | Destination JSON/joblib artifact schema and storage layout |
| `backend/src/inference/predictor.py` | `backend/app/forecasting/real/artifacts/loader.py`; `backend/app/forecasting/real/inference/predictor.py` | Artifact checks and LIR/ARIMA inference | `PORT_WITH_AZURE_ADAPTER` | Verify binary SHA before deserialization; LIR additive delta reconstruction; ARIMA one-step state update/forecast; reject invalid predictions | Destination artifact schema, path policy, and domain result |
| `backend/src/inference/next_day.py` | `backend/app/forecasting/real/inference/next_day.py` | Multi-model next-session orchestration | `PORT_WITH_AZURE_ADAPTER` | Same origin and target session for model forecasts | Destination PSE calendar and artifact provider |
| `backend/src/models/lstm.py` | None in Phase 3A | LSTM model | `DEFER_TO_PHASE3B` | No LSTM code or dependency activated in Phase 3A | Explicitly deferred |
| `backend/src/training/train_lstm.py` | None in Phase 3A | LSTM training | `DEFER_TO_PHASE3B` | No LSTM code or dependency activated in Phase 3A | Explicitly deferred |
| `backend/tests/` | `backend/tests/test_real_*.py` | Source-contract verification | `REFERENCE_ONLY` | Destination tests pin target, full default feature-name tuple, PACF/model behavior, artifact and inference contracts against source findings | Tests run against destination adapters |

## Pinned default feature-name order

`return_lag_1` through `return_lag_20`; `return_mean_5`, `return_std_5`, `return_mean_10`, `return_std_10`, `return_mean_20`, `return_std_20`; `volume_log`, `volume_change_1`; `volume_ratio_5`, `volume_z_5`, `volume_ratio_20`, `volume_z_20`; `range_pct`, `open_close_spread_pct`, `close_location_in_range`; `close_relative_sma_5`, `close_relative_sma_10`, `close_relative_sma_20`; `rsi_14`; `ema_relative_12`, `ema_relative_26`; `macd_relative`, `macd_signal_relative`, `macd_histogram_relative`; `bollinger_z_20`, `bollinger_width_20`, `bollinger_position_20`.

The default has 47 names, 20 return lags, and no raw-price lags. Optional configured raw-price lags append after the default feature names.

## Mathematical deviations

None for LIR or ARIMA. LIR target is next-session absolute Close delta and reconstruction is additive. ARIMA remains statsmodels ARIMA with an explicit selected specification, confirmed convergence, `append(actual, refit=False)`, and a one-step forecast.
