"""Unit tests for artifact verification, metadata schema, and fail-closed tampering checks."""

from datetime import date
import json
from pathlib import Path
import pytest

from backend.app.forecasting.real.artifacts.loader import (
    load_bundle_for_symbol,
    load_production_model,
    validate_artifact_against_history,
)
from backend.app.forecasting.real.artifacts.schema import (
    ModelArtifactCompatibilityError,
    ProductionModelMetadata,
)
from backend.app.forecasting.real.artifacts.writer import persist_model_artifact
from backend.app.forecasting.real.config import DEFAULT_ARIMA_CONFIG, DEFAULT_LAG_REGRESSION_CONFIG
from backend.app.forecasting.real.domain import OhlcvRecord
from backend.app.forecasting.real.features.regression_features import build_regression_dataset
from backend.app.forecasting.real.models.arima import ArimaSpecification
from backend.app.forecasting.real.training.refit_arima import refit_arima_for_production
from backend.app.forecasting.real.training.refit_lir import refit_lir_for_production
from backend.tests.test_real_models import _generate_synthetic_series


@pytest.fixture
def sample_artifacts_bundle(tmp_path: Path):
    """Create a temporary valid model artifact bundle with LIR and ARIMA for 'BPI'."""
    bundle_dir = tmp_path / "artifacts" / "2026.03.01-v1"
    bpi_dir = bundle_dir / "BPI"
    bpi_dir.mkdir(parents=True, exist_ok=True)

    records = _generate_synthetic_series(70, start_price=120.0)
    trained_through = records[-1].trading_date
    row_count = len(records)

    # 1. Fit & persist LIR
    dataset = build_regression_dataset(records, DEFAULT_LAG_REGRESSION_CONFIG.features)
    fitted_lir = refit_lir_for_production(dataset, chosen_alpha=0.01)
    lir_params = {
        "alpha": 0.01,
        "feature_names": list(fitted_lir.fit_metadata.feature_names),
        "pacf_selected_lags": list(fitted_lir.pacf_selected_lags),
    }
    lir_meta, _, _ = persist_model_artifact(
        output_directory=bpi_dir,
        symbol="BPI",
        model_code="LAG_REGRESSION",
        model_version="2026.03.01-v1",
        fitted_model=fitted_lir,
        hyperparameters=lir_params,
        trained_through=trained_through,
        data_row_count=row_count,
    )

    # 2. Fit & persist ARIMA
    spec = ArimaSpecification(order=(1, 1, 0), trend="n")
    fitted_arima = refit_arima_for_production(records, selected_specification=spec)
    arima_params = {
        "order": [1, 1, 0],
        "trend": "n",
    }
    arima_meta, _, _ = persist_model_artifact(
        output_directory=bpi_dir,
        symbol="BPI",
        model_code="ARIMA",
        model_version="2026.03.01-v1",
        fitted_model=fitted_arima.model,
        hyperparameters=arima_params,
        trained_through=trained_through,
        data_row_count=row_count,
    )

    return {
        "bundle_dir": bundle_dir,
        "symbol_dir": bpi_dir,
        "records": records,
        "lir_meta": lir_meta,
        "arima_meta": arima_meta,
    }


def test_successful_artifact_load(sample_artifacts_bundle):
    """Verify loading correctly serialized artifacts succeeds."""
    bundle_dir = sample_artifacts_bundle["bundle_dir"]

    # Load LIR
    lir_model, lir_meta = load_bundle_for_symbol(
        bundle_dir=bundle_dir,
        symbol="BPI",
        model_id="LAG_REGRESSION",
    )
    assert lir_meta.symbol == "BPI"
    assert lir_meta.model_code == "LAG_REGRESSION"
    assert lir_model is not None

    # Load ARIMA
    arima_model, arima_meta = load_bundle_for_symbol(
        bundle_dir=bundle_dir,
        symbol="BPI",
        model_id="ARIMA",
    )
    assert arima_meta.symbol == "BPI"
    assert arima_meta.model_code == "ARIMA"
    assert arima_model is not None


def test_tampered_binary_fails_sha_verification(sample_artifacts_bundle):
    """Verify modifying 1 byte in .joblib causes fail-closed SHA-256 error prior to deserialization."""
    symbol_dir = sample_artifacts_bundle["symbol_dir"]
    binary_path = symbol_dir / "lag_regression.joblib"

    # Flip 1 byte in the file
    content = bytearray(binary_path.read_bytes())
    content[10] ^= 0xFF
    binary_path.write_bytes(content)

    with pytest.raises(ModelArtifactCompatibilityError, match="SHA-256 checksum mismatch"):
        load_production_model(
            symbol_directory=symbol_dir,
            expected_symbol="BPI",
            expected_model_code="LAG_REGRESSION",
        )


def test_tampered_metadata_symbol_rejected(sample_artifacts_bundle):
    """Verify modifying symbol in metadata causes validation rejection."""
    symbol_dir = sample_artifacts_bundle["symbol_dir"]
    meta_path = symbol_dir / "arima.metadata.json"

    meta_json = json.loads(meta_path.read_text(encoding="utf-8"))
    meta_json["symbol"] = "SM"
    meta_path.write_text(json.dumps(meta_json), encoding="utf-8")

    with pytest.raises(ModelArtifactCompatibilityError, match="symbol mismatch"):
        load_production_model(
            symbol_directory=symbol_dir,
            expected_symbol="BPI",
            expected_model_code="ARIMA",
        )


def test_missing_metadata_or_binary_rejected(sample_artifacts_bundle):
    """Verify missing companion files fail closed."""
    symbol_dir = sample_artifacts_bundle["symbol_dir"]
    meta_path = symbol_dir / "arima.metadata.json"
    meta_path.unlink()

    with pytest.raises(ModelArtifactCompatibilityError, match="Metadata file missing"):
        load_production_model(
            symbol_directory=symbol_dir,
            expected_symbol="BPI",
            expected_model_code="ARIMA",
        )


def test_history_boundary_mismatch_rejected(sample_artifacts_bundle):
    """Verify validate_artifact_against_history detects truncated or shifted history."""
    records = sample_artifacts_bundle["records"]
    meta = sample_artifacts_bundle["lir_meta"]

    # History missing last 5 records
    truncated_records = records[:-5]
    with pytest.raises(ModelArtifactCompatibilityError, match="History length"):
        validate_artifact_against_history(meta, truncated_records)

    # Shifted history (different date at boundary)
    shifted_record = OhlcvRecord(
        trading_date=date(2099, 1, 1),
        open=100.0,
        high=105.0,
        low=99.0,
        close=102.0,
        volume=1000.0,
    )
    shifted_records = list(records[: meta.data_row_count - 1]) + [shifted_record]
    with pytest.raises(ModelArtifactCompatibilityError, match="History boundary date"):
        validate_artifact_against_history(meta, shifted_records)


def test_joblib_load_never_called_on_sha_mismatch(sample_artifacts_bundle, monkeypatch):
    """Prove joblib.load is NEVER called when pre-deserialization SHA-256 verification fails."""
    from unittest.mock import MagicMock
    import backend.app.forecasting.real.artifacts.loader as loader_mod

    mock_load = MagicMock()
    monkeypatch.setattr(loader_mod.joblib, "load", mock_load)

    symbol_dir = sample_artifacts_bundle["symbol_dir"]
    binary_path = symbol_dir / "lag_regression.joblib"
    content = bytearray(binary_path.read_bytes())
    content[5] ^= 0xFF
    binary_path.write_bytes(content)

    with pytest.raises(ModelArtifactCompatibilityError, match="SHA-256 checksum mismatch"):
        load_production_model(
            symbol_directory=symbol_dir,
            expected_symbol="BPI",
            expected_model_code="LAG_REGRESSION",
        )
    mock_load.assert_not_called()


def test_joblib_load_never_called_on_schema_version_mismatch(sample_artifacts_bundle, monkeypatch):
    """Prove joblib.load is NEVER called when schema_version is unsupported."""
    from unittest.mock import MagicMock
    import backend.app.forecasting.real.artifacts.loader as loader_mod

    mock_load = MagicMock()
    monkeypatch.setattr(loader_mod.joblib, "load", mock_load)

    symbol_dir = sample_artifacts_bundle["symbol_dir"]
    meta_path = symbol_dir / "arima.metadata.json"
    meta_json = json.loads(meta_path.read_text(encoding="utf-8"))
    meta_json["schema_version"] = 999
    meta_path.write_text(json.dumps(meta_json), encoding="utf-8")

    with pytest.raises(ModelArtifactCompatibilityError, match="Unsupported model artifact schema_version"):
        load_production_model(
            symbol_directory=symbol_dir,
            expected_symbol="BPI",
            expected_model_code="ARIMA",
        )
    mock_load.assert_not_called()


def test_joblib_load_never_called_on_schema_id_mismatch(sample_artifacts_bundle, monkeypatch):
    """Prove joblib.load is NEVER called when schema_id is unsupported."""
    from unittest.mock import MagicMock
    import backend.app.forecasting.real.artifacts.loader as loader_mod

    mock_load = MagicMock()
    monkeypatch.setattr(loader_mod.joblib, "load", mock_load)

    symbol_dir = sample_artifacts_bundle["symbol_dir"]
    meta_path = symbol_dir / "arima.metadata.json"
    meta_json = json.loads(meta_path.read_text(encoding="utf-8"))
    meta_json["schema_id"] = "unknown-schema"
    meta_path.write_text(json.dumps(meta_json), encoding="utf-8")

    with pytest.raises(ModelArtifactCompatibilityError, match="Unsupported model artifact schema_id"):
        load_production_model(
            symbol_directory=symbol_dir,
            expected_symbol="BPI",
            expected_model_code="ARIMA",
        )
    mock_load.assert_not_called()


def test_joblib_load_never_called_on_path_traversal(sample_artifacts_bundle, monkeypatch):
    """Prove joblib.load is NEVER called when metadata attempts directory traversal."""
    from unittest.mock import MagicMock
    import backend.app.forecasting.real.artifacts.loader as loader_mod

    mock_load = MagicMock()
    monkeypatch.setattr(loader_mod.joblib, "load", mock_load)

    symbol_dir = sample_artifacts_bundle["symbol_dir"]
    meta_path = symbol_dir / "arima.metadata.json"
    meta_json = json.loads(meta_path.read_text(encoding="utf-8"))
    meta_json["artifact_filename"] = "../other.joblib"
    meta_path.write_text(json.dumps(meta_json), encoding="utf-8")

    with pytest.raises(ModelArtifactCompatibilityError, match="Unsafe or invalid artifact_filename|Path traversal detected"):
        load_production_model(
            symbol_directory=symbol_dir,
            expected_symbol="BPI",
            expected_model_code="ARIMA",
        )
    mock_load.assert_not_called()


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("wrong_sha", "SHA-256 checksum mismatch"),
        ("wrong_symbol", "symbol mismatch"),
        ("wrong_family", "model_code mismatch"),
        ("wrong_version", "model_version mismatch"),
        ("wrong_schema_id", "Unsupported model artifact schema_id"),
        ("wrong_schema_version", "Unsupported model artifact schema_version"),
        ("unsafe_filename", "Unsafe or invalid artifact_filename"),
        ("path_traversal", "Unsafe or invalid artifact_filename|Path traversal detected"),
        ("missing_metadata", "Metadata file missing"),
        ("missing_required_metadata", "Missing required hyperparameters"),
        ("missing_binary", "Model binary file missing"),
    ],
)
def test_security_pre_deserialization_matrix_never_loads(
    sample_artifacts_bundle, monkeypatch, case, message
):
    """All artifact identity, schema, metadata, path and checksum failures preclude joblib.load."""
    from unittest.mock import MagicMock
    import backend.app.forecasting.real.artifacts.loader as loader_mod

    mock_load = MagicMock()
    monkeypatch.setattr(loader_mod.joblib, "load", mock_load)
    symbol_dir = sample_artifacts_bundle["symbol_dir"]
    meta_path = symbol_dir / "arima.metadata.json"
    if case == "missing_metadata":
        meta_path.unlink()
    else:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        if case == "wrong_sha":
            payload["artifact_sha256"] = "0" * 64
        elif case == "wrong_symbol":
            payload["symbol"] = "ALI"
        elif case == "wrong_family":
            payload["model_code"] = "LAG_REGRESSION"
        elif case == "wrong_version":
            payload["model_version"] = "other-bundle"
        elif case == "wrong_schema_id":
            payload["schema_id"] = "unsupported"
        elif case == "wrong_schema_version":
            payload["schema_version"] = 99
        elif case == "unsafe_filename":
            payload["artifact_filename"] = "nested/arima.joblib"
        elif case == "path_traversal":
            payload["artifact_filename"] = "../arima.joblib"
        elif case == "missing_required_metadata":
            payload["hyperparameters"].pop("order")
        elif case == "missing_binary":
            payload["artifact_filename"] = "missing.joblib"
        meta_path.write_text(json.dumps(payload), encoding="utf-8")

    kwargs = {
        "symbol_directory": symbol_dir,
        "expected_symbol": "BPI",
        "expected_model_code": "ARIMA",
    }
    if case == "wrong_version":
        kwargs["expected_model_version"] = "expected-bundle"
    with pytest.raises(ModelArtifactCompatibilityError, match=message):
        load_production_model(**kwargs)
    mock_load.assert_not_called()


def test_loaded_object_type_mismatch_is_rejected_after_verified_deserialization(
    sample_artifacts_bundle, monkeypatch
):
    """A checksum-valid binary of the wrong class is rejected after one load."""
    from unittest.mock import MagicMock
    import backend.app.forecasting.real.artifacts.loader as loader_mod
    from backend.app.forecasting.real.artifacts.writer import compute_artifact_sha256

    symbol_dir = sample_artifacts_bundle["symbol_dir"]
    meta_path = symbol_dir / "arima.metadata.json"
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    binary_path = symbol_dir / payload["artifact_filename"]
    loader_mod.joblib.dump({"wrong": "type"}, binary_path)
    payload["artifact_sha256"] = compute_artifact_sha256(binary_path)
    meta_path.write_text(json.dumps(payload), encoding="utf-8")

    actual_load = loader_mod.joblib.load
    mock_load = MagicMock(wraps=actual_load)
    monkeypatch.setattr(loader_mod.joblib, "load", mock_load)
    with pytest.raises(ModelArtifactCompatibilityError, match="expected FittedArimaModel"):
        load_production_model(
            symbol_directory=symbol_dir,
            expected_symbol="BPI",
            expected_model_code="ARIMA",
        )
    mock_load.assert_called_once()


def test_metadata_model_state_mismatch_rejected_after_verified_deserialization(
    sample_artifacts_bundle, monkeypatch
):
    """Metadata that disagrees with the loaded LIR state is rejected after checksum verification."""
    from unittest.mock import MagicMock
    import backend.app.forecasting.real.artifacts.loader as loader_mod

    symbol_dir = sample_artifacts_bundle["symbol_dir"]
    meta_path = symbol_dir / "lag_regression.metadata.json"
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    payload["hyperparameters"]["alpha"] = 88.0
    meta_path.write_text(json.dumps(payload), encoding="utf-8")

    actual_load = loader_mod.joblib.load
    mock_load = MagicMock(wraps=actual_load)
    monkeypatch.setattr(loader_mod.joblib, "load", mock_load)
    with pytest.raises(ModelArtifactCompatibilityError, match="Metadata alpha does not match"):
        load_production_model(
            symbol_directory=symbol_dir,
            expected_symbol="BPI",
            expected_model_code="LAG_REGRESSION",
        )
    mock_load.assert_called_once()
