"""Checksum-before-deserialization and state validation for .pt artifacts."""

from datetime import date
import json

import pytest

torch = pytest.importorskip("torch", reason="Install backend/requirements-lstm.txt")

from backend.app.forecasting.real.artifacts.lstm_state import (
    load_lstm_state_artifact,
    persist_lstm_state_artifact,
)
from backend.app.forecasting.real.artifacts.schema import ModelArtifactCompatibilityError
from backend.app.forecasting.real.artifacts.writer import compute_artifact_sha256
from backend.app.forecasting.real.config import LstmSpecification
from backend.app.forecasting.real.models.lstm import (
    DeltaScaler,
    FittedLstmModel,
    UnivariateDeltaLSTM,
)
from backend.app.forecasting.real.selections import SelectionProvenance


def _artifact(tmp_path):
    spec = LstmSpecification(5, 16, 0.003, 32)
    fitted = FittedLstmModel(
        network=UnivariateDeltaLSTM(spec.hidden_size),
        scaler=DeltaScaler().fit([float(value) for value in range(15)]),
        specification=spec,
        epoch_count=4,
        seed=42,
        training_size=10,
    )
    paths = persist_lstm_state_artifact(
        output_directory=tmp_path / "BPI",
        symbol="BPI",
        model_version="phase3b1-smoke",
        fitted=fitted,
        data_row_count=16,
        trained_through=date(2026, 10, 1),
        formal_selected_epoch_count=9,
        selection_provenance=SelectionProvenance(),
    )
    return paths[0].parent, paths[0], paths[1]


def _rewrite_consistent_checkpoint(directory, artifact, metadata_path, update):
    metadata = _metadata(metadata_path)
    checkpoint = torch.load(artifact, map_location="cpu", weights_only=True)
    update(metadata, checkpoint)
    torch.save(checkpoint, artifact)
    metadata["artifact_sha256"] = compute_artifact_sha256(artifact)
    _write_metadata(metadata_path, metadata)


def _metadata(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_metadata(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_state_dict_round_trip_keeps_formal_and_production_epochs_separate(tmp_path):
    directory, artifact, metadata_path = _artifact(tmp_path)
    metadata = _metadata(metadata_path)
    assert metadata["artifact_format"] == "pytorch_state_dict"
    assert metadata["artifact_filename"] == "lstm.pt"
    assert metadata["schema_version"] == 1
    assert metadata["hyperparameters"]["formal_selected_epoch_count"] == 9
    assert metadata["hyperparameters"]["production_selected_epoch_count"] == 4
    loaded = load_lstm_state_artifact(
        symbol_directory=directory,
        expected_symbol="BPI",
        expected_model_version="phase3b1-smoke",
        expected_trained_through=date(2026, 10, 1),
        expected_data_row_count=16,
    )
    assert loaded.model.seed == 42
    assert loaded.model.epoch_count == 4
    assert loaded.model.training_size == 10
    assert loaded.model.scaler.observations == 15
    assert compute_artifact_sha256(artifact) == loaded.metadata["artifact_sha256"]


@pytest.mark.parametrize(
    ("change", "expected_symbol", "expected_version", "expected_boundary"),
    [
        ("sha", "BPI", "phase3b1-smoke", None),
        ("symbol", "BPI", "phase3b1-smoke", None),
        ("family", "BPI", "phase3b1-smoke", None),
        ("version", "BPI", "phase3b1-smoke", None),
        ("format", "BPI", "phase3b1-smoke", None),
        ("schema_id", "BPI", "phase3b1-smoke", None),
        ("schema_version", "BPI", "phase3b1-smoke", None),
        ("unsafe_filename", "BPI", "phase3b1-smoke", None),
        ("path_traversal", "BPI", "phase3b1-smoke", None),
        ("missing_hyperparameters", "BPI", "phase3b1-smoke", None),
        ("date_boundary", "BPI", "phase3b1-smoke", date(2026, 10, 2)),
        ("row_boundary", "BPI", "phase3b1-smoke", 17),
    ],
)
def test_pre_deserialization_failures_never_call_torch_load(
    tmp_path, monkeypatch, change, expected_symbol, expected_version, expected_boundary
):
    directory, artifact, metadata_path = _artifact(tmp_path)
    metadata = _metadata(metadata_path)
    if change == "sha":
        metadata["artifact_sha256"] = "0" * 64
    elif change == "symbol":
        metadata["symbol"] = "JFC"
    elif change == "family":
        metadata["model_code"] = "ARIMA"
    elif change == "version":
        metadata["model_version"] = "other-version"
    elif change == "format":
        metadata["artifact_format"] = "joblib"
    elif change == "schema_id":
        metadata["schema_id"] = "unknown"
    elif change == "schema_version":
        metadata["schema_version"] = 2
    elif change == "unsafe_filename":
        metadata["artifact_filename"] = "../lstm.pt"
    elif change == "path_traversal":
        metadata["artifact_filename"] = "nested/lstm.pt"
    elif change == "missing_hyperparameters":
        metadata["hyperparameters"] = {}
    _write_metadata(metadata_path, metadata)
    monkeypatch.setattr(torch, "load", lambda *args, **kwargs: pytest.fail("torch.load called"))

    with pytest.raises(ModelArtifactCompatibilityError):
        load_lstm_state_artifact(
            symbol_directory=directory,
            expected_symbol=expected_symbol,
            expected_model_version=expected_version,
            expected_trained_through=(
                expected_boundary if isinstance(expected_boundary, date) else date(2026, 10, 1)
            ),
            expected_data_row_count=(expected_boundary if isinstance(expected_boundary, int) else 16),
        )


@pytest.mark.parametrize(
    "tamper",
    [
        "lookback",
        "hidden_size",
        "learning_rate",
        "formal_epochs",
        "nested_provenance",
        "seed_7",
        "lookback_bool",
        "hidden_size_float",
        "batch_bool",
        "learning_rate_bool",
    ],
)
def test_authoritative_selection_tampering_never_calls_torch_load(
    tmp_path, monkeypatch, tamper
):
    directory, artifact, metadata_path = _artifact(tmp_path)

    def update(metadata, checkpoint):
        hp = metadata["hyperparameters"]
        if tamper == "lookback":
            hp["lookback"] = checkpoint["specification"]["lookback"] = 10
            hp["training_size"] = checkpoint["training_size"] = 5
        elif tamper == "hidden_size":
            hp["hidden_size"] = checkpoint["specification"]["hidden_size"] = 32
            checkpoint["model_state_dict"] = UnivariateDeltaLSTM(32).state_dict()
        elif tamper == "learning_rate":
            hp["learning_rate"] = checkpoint["specification"]["learning_rate"] = 0.001
        elif tamper == "formal_epochs":
            hp["formal_selected_epoch_count"] = 8
        elif tamper == "nested_provenance":
            hp["selection_provenance"]["formal_git_sha"] = "0" * 40
        elif tamper == "seed_7":
            hp["seed"] = checkpoint["seed"] = 7
        elif tamper == "lookback_bool":
            hp["lookback"] = True
        elif tamper == "hidden_size_float":
            hp["hidden_size"] = 16.0
        elif tamper == "batch_bool":
            hp["batch_size"] = True
        elif tamper == "learning_rate_bool":
            hp["learning_rate"] = True

    _rewrite_consistent_checkpoint(directory, artifact, metadata_path, update)
    monkeypatch.setattr(torch, "load", lambda *args, **kwargs: pytest.fail("torch.load called"))
    with pytest.raises(ModelArtifactCompatibilityError):
        load_lstm_state_artifact(
            symbol_directory=directory,
            expected_symbol="BPI",
            expected_model_version="phase3b1-smoke",
        )


@pytest.mark.parametrize(
    "tamper", ["specification", "formal_epochs", "provenance", "seed"]
)
def test_persistence_rejects_non_authoritative_bpi_artifacts(tmp_path, tamper):
    spec = LstmSpecification(5, 16, 0.003, 32)
    formal_epochs = 9
    provenance = SelectionProvenance()
    seed = 42
    if tamper == "specification":
        spec = LstmSpecification(10, 16, 0.003, 32)
    elif tamper == "formal_epochs":
        formal_epochs = 8
    elif tamper == "provenance":
        provenance = SelectionProvenance(formal_git_sha="0" * 40)
    elif tamper == "seed":
        seed = 7
    fitted = FittedLstmModel(
        network=UnivariateDeltaLSTM(spec.hidden_size),
        scaler=DeltaScaler().fit([float(value) for value in range(15)]),
        specification=spec,
        epoch_count=4,
        seed=seed,
        training_size=10,
    )
    output_directory = tmp_path / "rejected" / "BPI"
    with pytest.raises(ValueError):
        persist_lstm_state_artifact(
            output_directory=output_directory,
            symbol="BPI",
            model_version="phase3b1-smoke",
            fitted=fitted,
            data_row_count=16,
            trained_through=date(2026, 10, 1),
            formal_selected_epoch_count=formal_epochs,
            selection_provenance=provenance,
        )
    assert not list(tmp_path.rglob("*.pt"))


@pytest.mark.parametrize("missing", ["metadata", "artifact"])
def test_missing_lstm_files_never_call_torch_load(tmp_path, monkeypatch, missing):
    directory, artifact, metadata_path = _artifact(tmp_path)
    (metadata_path if missing == "metadata" else artifact).unlink()
    monkeypatch.setattr(torch, "load", lambda *args, **kwargs: pytest.fail("torch.load called"))
    with pytest.raises(ModelArtifactCompatibilityError):
        load_lstm_state_artifact(
            symbol_directory=directory,
            expected_symbol="BPI",
            expected_model_version="phase3b1-smoke",
        )


@pytest.mark.parametrize(
    "tamper",
    [
        "checkpoint_schema",
        "specification",
        "epoch",
        "seed",
        "non42_seed",
        "scaler_nan",
        "scaler_zero_scale",
        "missing_state_key",
        "bad_state_shape",
        "nonfinite_tensor",
    ],
)
def test_post_load_checkpoint_contract_rejected(tmp_path, tamper):
    directory, artifact, metadata_path = _artifact(tmp_path)
    metadata = _metadata(metadata_path)
    checkpoint = torch.load(artifact, map_location="cpu", weights_only=True)
    hp = metadata["hyperparameters"]
    if tamper == "checkpoint_schema":
        checkpoint["schema_version"] = 2
    elif tamper == "specification":
        checkpoint["specification"]["lookback"] = 10
    elif tamper == "epoch":
        checkpoint["selected_epoch_count"] += 1
    elif tamper in {"seed", "non42_seed"}:
        checkpoint["seed"] = 7
    elif tamper == "scaler_nan":
        checkpoint["scaler"]["mean"] = float("nan")
        hp["scaler"]["mean"] = float("nan")
    elif tamper == "scaler_zero_scale":
        checkpoint["scaler"]["scale"] = 0.0
        hp["scaler"]["scale"] = 0.0
    elif tamper == "missing_state_key":
        checkpoint["model_state_dict"].pop(next(iter(checkpoint["model_state_dict"])))
    elif tamper == "bad_state_shape":
        name = next(iter(checkpoint["model_state_dict"]))
        checkpoint["model_state_dict"][name] = torch.zeros((1,), dtype=torch.float32)
    elif tamper == "nonfinite_tensor":
        name = next(iter(checkpoint["model_state_dict"]))
        checkpoint["model_state_dict"][name].reshape(-1)[0] = float("nan")
    torch.save(checkpoint, artifact)
    metadata["artifact_sha256"] = compute_artifact_sha256(artifact)
    _write_metadata(metadata_path, metadata)
    with pytest.raises(ModelArtifactCompatibilityError):
        load_lstm_state_artifact(
            symbol_directory=directory,
            expected_symbol="BPI",
            expected_model_version="phase3b1-smoke",
        )
