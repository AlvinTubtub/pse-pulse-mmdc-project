"""Pre-deserialization and persistence checks for company-bound joblib artifacts."""

from datetime import date
import json

import pytest

from backend.app.forecasting.real.artifacts.authoritative import (
    load_authoritative_model,
    persist_authoritative_arima,
    persist_authoritative_lir,
)
from backend.app.forecasting.real.artifacts.schema import ModelArtifactCompatibilityError
from backend.app.forecasting.real.config import DEFAULT_LAG_REGRESSION_CONFIG
from backend.app.forecasting.real.features.regression_features import build_regression_dataset
from backend.app.forecasting.real.selections import load_selection_catalog
from backend.app.forecasting.real.training.refit_arima import refit_arima_for_production
from backend.app.forecasting.real.training.refit_lir import refit_lir_for_production
from backend.tests.test_real_models import _generate_synthetic_series


@pytest.fixture
def authoritative_joblib_artifacts(tmp_path):
    records = _generate_synthetic_series(120, start_price=100.0)
    selection = load_selection_catalog()["BPI"]
    dataset = build_regression_dataset(records, DEFAULT_LAG_REGRESSION_CONFIG.features)
    lir = refit_lir_for_production(dataset, chosen_alpha=selection.lir_alpha)
    lir_dir = tmp_path / "BPI-lir"
    _, _, lir_meta = persist_authoritative_lir(
        output_directory=lir_dir,
        symbol="BPI",
        model_version="2026.10.01-authoritative-v1",
        fitted=lir,
        trained_through=records[-1].trading_date,
        data_row_count=len(records),
        formal_selected_features_evidence=selection.lir_selected_features_evidence,
        selection_provenance=selection.provenance,
    )
    arima = refit_arima_for_production(records, selected_specification=selection.arima)
    arima_dir = tmp_path / "BPI-arima"
    _, _, arima_meta = persist_authoritative_arima(
        output_directory=arima_dir,
        symbol="BPI",
        model_version="2026.10.01-authoritative-v1",
        fitted=arima.model,
        trained_through=records[-1].trading_date,
        data_row_count=len(records),
        selection_provenance=selection.provenance,
    )
    return {
        "selection": selection,
        "lir_dir": lir_dir,
        "lir_meta": lir_meta,
        "arima_dir": arima_dir,
        "arima_meta": arima_meta,
        "records": records,
        "lir": lir,
        "arima": arima.model,
    }


def _write_tamper(metadata_path, mutator):
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    mutator(payload)
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")


def test_authoritative_load_rejects_lir_metadata_before_joblib(authoritative_joblib_artifacts, monkeypatch):
    from backend.app.forecasting.real.artifacts import loader as loader_module

    fixture = authoritative_joblib_artifacts
    metadata_path = fixture["lir_dir"] / "lag_regression.metadata.json"
    original = metadata_path.read_text(encoding="utf-8")
    monkeypatch.setattr(loader_module.joblib, "load", lambda *a, **k: pytest.fail("joblib.load called"))
    selection = fixture["selection"]
    cases = (
        (lambda value: value["hyperparameters"].update(alpha=0.03), "alpha"),
        (lambda value: value.update(symbol="JFC"), "symbol"),
        (lambda value: value["hyperparameters"]["selection_provenance"].update(formal_git_sha="0" * 40), "provenance"),
        (lambda value: value.update(model_version="other"), "version"),
    )
    for mutate, _label in cases:
        metadata_path.write_text(original, encoding="utf-8")
        _write_tamper(metadata_path, mutate)
        with pytest.raises(ModelArtifactCompatibilityError):
            load_authoritative_model(
                symbol_directory=fixture["lir_dir"], expected_symbol="BPI",
                expected_model_code="LAG_REGRESSION", expected_model_version="2026.10.01-authoritative-v1",
                trained_through=fixture["records"][-1].trading_date, data_row_count=len(fixture["records"]),
            )
    metadata_path.write_text(original, encoding="utf-8")
    with pytest.raises(ModelArtifactCompatibilityError, match="history boundary"):
        load_authoritative_model(
            symbol_directory=fixture["lir_dir"], expected_symbol="BPI",
            expected_model_code="LAG_REGRESSION", expected_model_version="2026.10.01-authoritative-v1",
            trained_through=date(2026, 10, 1), data_row_count=len(fixture["records"]),
        )


def test_authoritative_load_rejects_arima_metadata_before_joblib(authoritative_joblib_artifacts, monkeypatch):
    from backend.app.forecasting.real.artifacts import loader as loader_module

    fixture = authoritative_joblib_artifacts
    metadata_path = fixture["arima_dir"] / "arima.metadata.json"
    original = metadata_path.read_text(encoding="utf-8")
    monkeypatch.setattr(loader_module.joblib, "load", lambda *a, **k: pytest.fail("joblib.load called"))
    cases = (
        lambda value: value["hyperparameters"].update(order=[0, 1, 0]),
        lambda value: value["hyperparameters"].update(trend="t"),
        lambda value: value["hyperparameters"].update(convergence_status="confirmed_non_converged"),
        lambda value: value["hyperparameters"]["selection_provenance"].update(formal_git_sha="0" * 40),
        lambda value: value.update(model_version="other"),
    )
    for mutate in cases:
        metadata_path.write_text(original, encoding="utf-8")
        _write_tamper(metadata_path, mutate)
        with pytest.raises(ModelArtifactCompatibilityError):
            load_authoritative_model(
                symbol_directory=fixture["arima_dir"], expected_symbol="BPI",
                expected_model_code="ARIMA", expected_model_version="2026.10.01-authoritative-v1",
                trained_through=fixture["records"][-1].trading_date, data_row_count=len(fixture["records"]),
            )
    metadata_path.write_text(original, encoding="utf-8")
    with pytest.raises(ModelArtifactCompatibilityError, match="history boundary"):
        load_authoritative_model(
            symbol_directory=fixture["arima_dir"], expected_symbol="BPI",
            expected_model_code="ARIMA", expected_model_version="2026.10.01-authoritative-v1",
            trained_through=date(2026, 10, 1), data_row_count=len(fixture["records"]),
        )


def test_authoritative_persistence_rejects_mismatched_lir_and_arima_before_write(
    authoritative_joblib_artifacts, tmp_path
):
    fixture = authoritative_joblib_artifacts
    selection = fixture["selection"]
    lir = refit_lir_for_production(
        build_regression_dataset(fixture["records"], DEFAULT_LAG_REGRESSION_CONFIG.features),
        chosen_alpha=0.03,
    )
    with pytest.raises(ValueError, match="alpha"):
        persist_authoritative_lir(
            output_directory=tmp_path / "bad-lir", symbol="BPI", model_version="bad",
            fitted=lir, trained_through=fixture["records"][-1].trading_date,
            data_row_count=len(fixture["records"]),
            formal_selected_features_evidence=selection.lir_selected_features_evidence,
            selection_provenance=selection.provenance,
        )
    with pytest.raises(ValueError, match="provenance"):
        persist_authoritative_lir(
            output_directory=tmp_path / "bad-lir-provenance", symbol="BPI", model_version="bad",
            fitted=fixture["lir"], trained_through=fixture["records"][-1].trading_date,
            data_row_count=len(fixture["records"]),
            formal_selected_features_evidence=selection.lir_selected_features_evidence,
            selection_provenance=type(selection.provenance)(formal_git_sha="0" * 40),
        )
    assert not list((tmp_path / "bad-lir").glob("*.joblib"))
    assert not list((tmp_path / "bad-lir-provenance").glob("*.joblib"))

    wrong_spec_fit = refit_arima_for_production(
        fixture["records"], selected_specification=type(selection.arima)((0, 1, 0), "n")
    ).model
    with pytest.raises(ValueError, match="specification"):
        persist_authoritative_arima(
            output_directory=tmp_path / "bad-arima", symbol="BPI", model_version="bad",
            fitted=wrong_spec_fit, trained_through=fixture["records"][-1].trading_date,
            data_row_count=len(fixture["records"]), selection_provenance=selection.provenance,
        )
    with pytest.raises(ValueError, match="provenance"):
        persist_authoritative_arima(
            output_directory=tmp_path / "bad-arima-provenance", symbol="BPI", model_version="bad",
            fitted=fixture["arima"], trained_through=fixture["records"][-1].trading_date,
            data_row_count=len(fixture["records"]),
            selection_provenance=type(selection.provenance)(formal_git_sha="0" * 40),
        )
    assert not list((tmp_path / "bad-arima").glob("*.joblib"))
    assert not list((tmp_path / "bad-arima-provenance").glob("*.joblib"))
