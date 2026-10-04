"""Ensure opt-in LSTM support does not add PyTorch to normal app startup."""

import os
from pathlib import Path
import subprocess
import sys


def test_normal_fastapi_import_does_not_import_torch_or_train():
    root = Path(__file__).resolve().parents[2]
    code = (
        "import sys; import backend.app.main; "
        "assert 'torch' not in sys.modules; "
        "assert 'backend.app.forecasting.real.models.lstm' not in sys.modules; "
        "assert 'backend.app.forecasting.real.training.lstm' not in sys.modules; "
        "assert 'backend.app.forecasting.real.artifacts.lstm_state' not in sys.modules"
    )
    environment = os.environ.copy()
    environment.update(
        {
            "ENVIRONMENT": "test",
            "DEMO_MODE": "false",
            "DATABASE_URL": "sqlite:///:memory:",
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
