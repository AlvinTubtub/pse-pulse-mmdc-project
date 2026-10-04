# Phase 3B.1 LSTM Port Matrix

Official source snapshot: `AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27` at `b8bf39f8e94729687c2e877dc164ea8a4f69e2b1`.

Formal model-selection evidence is sourced from the exact `backend/research-result/selected_configurations.csv` snapshot (Git blob `60fe633c8e2860a56cb46248cd4b937c1a231833`, SHA-256 `7c648357adaba1e5769d560435bad61a933d67ebb5ee8fc1ded5944416737a97`). Its formal run commit remains `8359270bffcd43dd41830a01bb2f4e2d4c527b56`; this differs intentionally from the source snapshot commit.

| Official source | Destination | Classification | Scope and adaptation |
| --- | --- | --- | --- |
| `backend/config/model_config.py` (`LstmConfig`) | `backend/app/forecasting/real/config.py` | `PORT_EXACT_LOGIC` | The official candidate grid, seed contract, chronological stopping controls, and epoch limits are copied as an immutable config. No grid evaluation runs in this phase. |
| `backend/research-result/selected_configurations.csv` | `backend/config/authoritative/forecastph_selected_configurations_20260911.csv` | `PORT_EXACT_LOGIC` | Copied byte-for-byte and checked against the official Git blob and SHA-256. It is not duplicated as a research-results tree. |
| Formal selection CSV contract | `backend/app/forecasting/real/selections.py` | `PORT_WITH_DESTINATION_ADAPTER` | Strict CSV parser maps official fields to immutable typed selections, canonical symbols, existing LIR/ARIMA configuration grids, and explicit source/formal provenance. Formal selected LIR feature names are retained only as audit evidence. |
| `backend/src/models/lstm.py` | `backend/app/forecasting/real/models/lstm.py` | `PORT_WITH_DESTINATION_ADAPTER` | Sequence, scaler, model, and finite-state behavior follow the pinned implementation. `NextDayForecastPair` and Close reconstruction use the destination domain and helper. PyTorch is imported only by explicitly selected LSTM modules. |
| `backend/src/features/targets.py` | `backend/app/forecasting/real/domain.py` | `PORT_WITH_DESTINATION_ADAPTER` | Uses the destination's equivalent chronological next-day absolute Close-delta pairs. It does not add features to the univariate LSTM. |
| `backend/src/models/base.py` | `backend/app/forecasting/real/models/base.py` | `PORT_EXACT_LOGIC` | Uses the established `origin_close + predicted_delta` reconstruction. |
| `backend/src/training/train_lstm.py` (determinism, stopping, scaler fit, epoch selection, fixed-epoch fit) | `backend/app/forecasting/real/training/lstm.py` | `PORT_WITH_DESTINATION_ADAPTER` | Ports official Stage A chronological-tail RMSE selection and fresh Stage B full-block refit. Destination history/domain types replace official package types. No tuning/CV candidate scoring is ported or executed. |
| `backend/src/training/production_refit.py` (LSTM refit semantics) | `backend/app/forecasting/real/training/lstm.py`, `scripts/phase3b1_bpi_smoke.py` | `PORT_WITH_DESTINATION_ADAPTER` | Exposes an explicit offline function. It uses only the selected LSTM specification, computes a new Stage-A production epoch count, and fits a fresh Stage-B model on all labeled history with seed 42. It is not called by FastAPI startup, requests, or ingestion. |
| `backend/src/training/train_lstm.py` (all-grid tuning, CV search, research histories) | No destination port in this phase | `REFERENCE_ONLY` | Official formal selected configurations are already authoritative. Re-running the grid would be new tuning and is explicitly excluded. |
| `backend/src/training/cross_validation.py` | No destination port in this phase | `REFERENCE_ONLY` | Five-split formal selection evidence is retained in the catalog. Phase 3B.1 does not recompute formal scores. |
| `backend/src/data/split.py` | No destination port for LSTM in this phase | `REFERENCE_ONLY` | No new evaluation or formal run is conducted. |
| `backend/src/inference/predictor.py` (safe state loading and LSTM prediction contract) | `backend/app/forecasting/real/artifacts/lstm_state.py`, `scripts/phase3b1_bpi_smoke.py` | `PORT_WITH_DESTINATION_ADAPTER` | JSON identity/path/history validation and SHA-256 verification precede `torch.load(weights_only=True)`. The smoke reloads the saved state and predicts one next-session delta; no public forecast service wiring is added. |
| `backend/requirements.txt` (official PyTorch range) | `backend/requirements-lstm.txt` | `PORT_WITH_DESTINATION_ADAPTER` | Keeps `torch>=2.2,<3.0` separate from production and Phase 3A model requirements. |
| Official all-company production artifact workflow | Not performed | `DEFER_TO_PHASE3B2` | No all-15 artifact bundles or authoritative `ModelArtifact` rows are generated. |
| ONNX conversion/runtime | Not implemented | `EXCLUDE` | PyTorch state-dict parity is the Phase 3B.1 artifact target. No ONNX packages are added. |

## Explicit methodology boundaries

- Target remains `target_close - origin_close`, with price reconstruction by addition.
- The only LSTM inputs are the preceding Close deltas in `[batch, lookback, 1]` order.
- The network remains one `nn.LSTM(input_size=1, batch_first=True)` followed by one `nn.Linear(hidden_size, 1)` using the last time output.
- Scaling uses training-block deltas only, NumPy population standard deviation (`ddof=0`), and scale `1.0` for a constant block.
- Training uses Adam, MSE, ordered slices without shuffling, and the official deterministic controls. Exact numeric identity across library versions, OSes, and hardware is not claimed.
- Stage A chooses a new epoch count from the most recent chronological training tail; Stage B creates a fresh scaler and model and trains over all labeled production samples for that selected count. Formal selected epochs remain separate evidence.
- No new hyperparameter tuning, LIR/ARIMA changes, database schema changes, public API activation, all-15 training, or Azure deployment is included.
