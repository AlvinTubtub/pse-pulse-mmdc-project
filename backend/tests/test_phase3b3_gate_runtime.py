"""Focused operational gates for Phase 3B.3 (no production candidate DB access)."""

from datetime import date
import json
from pathlib import Path
import sys
import os
import subprocess

import numpy as np
import pytest

from backend.app.domain.company_universe import get_all_configured_symbols
from backend.app.forecasting.real.domain import OhlcvRecord
from backend.app.forecasting.real.evaluation.gate import GateEvaluationError, validate_phase3b2_evidence
from backend.app.forecasting.real.inference.predictor import predict_with_production_model


def test_lstm_predictor_uses_latest_absolute_close_deltas_and_frozen_predictor():
    class Fitted:
        def __init__(self):
            self.received = None

        def predict_delta_sequences(self, sequences):
            self.received = np.asarray(sequences).copy()
            return np.asarray([2.5])

    history = tuple(
        OhlcvRecord(date(2026, 1, day), 10.0 + day, 11.0 + day, 9.0 + day, 10.0 + day, 100.0)
        for day in range(1, 5)
    )
    fitted = Fitted()
    metadata = {
        "symbol": "ALI", "model_code": "LSTM", "model_version": "v1",
        "trained_through": "2026-01-02", "data_row_count": 2,
        "hyperparameters": {"lookback": 2},
    }
    result = predict_with_production_model(fitted_model=fitted, metadata=metadata, records=history)
    assert fitted.received.shape == (1, 2)
    np.testing.assert_allclose(fitted.received, [[1.0, 1.0]])
    assert result.predicted_delta == 2.5
    assert result.predicted_close == 16.5


def test_lstm_predictor_rejects_nonpositive_reconstructed_close():
    class Fitted:
        def predict_delta_sequences(self, sequences):
            return np.asarray([-100.0])

    history = (
        OhlcvRecord(date(2026, 1, 1), 10, 11, 9, 10, 1),
        OhlcvRecord(date(2026, 1, 2), 10, 11, 9, 10, 1),
    )
    meta = {"symbol": "ALI", "model_code": "LSTM", "trained_through": "2026-01-02", "data_row_count": 2, "hyperparameters": {"lookback": 1}}
    with pytest.raises(RuntimeError, match="non-positive"):
        predict_with_production_model(fitted_model=Fitted(), metadata=meta, records=history)


@pytest.mark.parametrize(
    "days",
    [
        (1, 3, 2),  # out of order
        (1, 2, 2),  # duplicate/non-increasing date
    ],
)
def test_lstm_mapping_predictor_rejects_non_chronological_history(days):
    class Fitted:
        def predict_delta_sequences(self, sequences):
            return np.asarray([0.5])

    history = tuple(
        OhlcvRecord(date(2026, 1, day), 10.0, 11.0, 9.0, 10.0, 1.0)
        for day in days
    )
    metadata = {
        "symbol": "ALI", "model_code": "LSTM", "trained_through": "2026-01-02",
        "data_row_count": 2, "hyperparameters": {"lookback": 1},
    }
    with pytest.raises(ValueError, match="(Non-chronological|Duplicate trading date)"):
        predict_with_production_model(fitted_model=Fitted(), metadata=metadata, records=history)


def test_phase3b2_evidence_requires_exact_45_bound_records(tmp_path):
    rows = [
        {"symbol": symbol, "model_code": model, "origin_date": "2026-10-01", "target_date": "2026-10-02", "safe_reload_passed": True, "origin_close": 1.0, "predicted_delta": 0.1, "predicted_close": 1.1}
        for symbol in get_all_configured_symbols()
        for model in ("LAG_REGRESSION", "ARIMA", "LSTM")
    ]
    path = tmp_path / "bundle_validation.json"
    path.write_text(json.dumps({"results": rows}))
    accepted, digest = validate_phase3b2_evidence(path)
    assert len(accepted) == 45
    assert len(digest) == 64
    path.write_text(json.dumps({"results": rows[:-1]}))
    with pytest.raises(GateEvaluationError, match="exactly 45"):
        validate_phase3b2_evidence(path)


def test_runtime_import_keeps_torch_lazy():
    root = Path(__file__).resolve().parents[2]
    script = r'''import hashlib, json, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
import backend.app.forecasting.real.artifacts.runtime as runtime
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    (root / "ALI").mkdir()
    artifact = root / "ALI" / "lag_regression.joblib"
    artifact.write_bytes(b"fixture")
    metadata = {"symbol":"ALI","model_code":"LAG_REGRESSION","model_version":"2026.10.01-authoritative-v1","artifact_format":"joblib","trained_through":"2026-10-01","data_row_count":1649}
    meta_path = root / "ALI" / "lag_regression.metadata.json"
    meta_path.write_text(json.dumps(metadata))
    entry = {"symbol":"ALI","model_code":"LAG_REGRESSION","model_version":"2026.10.01-authoritative-v1","artifact_format":"joblib","artifact_relative_path":"ALI/lag_regression.joblib","artifact_sha256":hashlib.sha256(artifact.read_bytes()).hexdigest(),"metadata_relative_path":"ALI/lag_regression.metadata.json","metadata_sha256":hashlib.sha256(meta_path.read_bytes()).hexdigest(),"trained_through":"2026-10-01","data_row_count":1649}
    runtime.read_verified_manifest = lambda *a, **k: ({"entries":[entry]}, "4225e60044f000b16147e01f6ff165968523c1efd9647e57d9c7a6f5f5a27454")
    runtime.load_authoritative_model = lambda **k: (object(), SimpleNamespace(symbol="ALI", model_code="LAG_REGRESSION"))
    runtime.load_runtime_artifact(bundle_root=root, symbol="ALI", model_code="LAG_REGRESSION")
assert "torch" not in sys.modules
'''
    env = os.environ.copy()
    result = subprocess.run([sys.executable, "-c", script], cwd=root, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
