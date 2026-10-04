"""Integrity and contract tests for the pinned formal selection catalog."""

import csv
import hashlib
from pathlib import Path

import pytest

from backend.app.domain.company_universe import get_all_configured_symbols
from backend.app.forecasting.real.selections import (
    DEFAULT_SELECTION_PATH,
    FORMAL_CUTOFF,
    FORMAL_FINAL_SEED,
    FORMAL_GIT_SHA,
    FORMAL_RUN_ID,
    FORMAL_TUNING_SEEDS,
    SELECTION_CRITERION,
    SELECTION_SOURCE_SHA256,
    SelectionCatalogError,
    load_selection_catalog,
)


def test_authoritative_csv_matches_pinned_sha256():
    assert hashlib.sha256(DEFAULT_SELECTION_PATH.read_bytes()).hexdigest() == SELECTION_SOURCE_SHA256


def test_catalog_has_all_canonical_symbols_and_formal_provenance():
    catalog = load_selection_catalog()
    assert len(catalog) == 15
    assert set(catalog) == set(get_all_configured_symbols())
    for selection in catalog.values():
        provenance = selection.provenance
        assert provenance.formal_run_id == FORMAL_RUN_ID
        assert provenance.formal_cutoff == FORMAL_CUTOFF
        assert provenance.formal_git_sha == FORMAL_GIT_SHA
        assert provenance.selection_criterion == SELECTION_CRITERION
        assert provenance.cv_splits == 5
        assert provenance.tuning_seeds == FORMAL_TUNING_SEEDS
        assert provenance.final_seed == FORMAL_FINAL_SEED
        assert selection.arima_convergence_status == "confirmed_converged"


def test_bpi_authoritative_selection_sentinel():
    bpi = load_selection_catalog()["BPI"]
    assert bpi.lir_alpha == 0.1
    assert bpi.arima.order == (1, 1, 1)
    assert bpi.arima.trend == "n"
    assert bpi.lstm.as_dict() == {
        "lookback": 5,
        "hidden_size": 16,
        "learning_rate": 0.003,
        "batch_size": 32,
    }
    assert bpi.formal_lstm_selected_epoch_count == 9


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with DEFAULT_SELECTION_PATH.open(newline="", encoding="utf-8") as source:
        fields = next(csv.reader(source))
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("lir_selected_alpha", "0"),
        ("arima_p", "99"),
        ("arima_trend", "ct"),
        ("arima_convergence_status", "unknown"),
        ("lstm_lookback", "7"),
        ("lstm_learning_rate", "NaN"),
        ("lstm_tuning_seeds", "11|29|47|99"),
        ("lstm_final_seed", "7"),
        ("cv_splits", "4"),
        ("selection_criterion", "lowest_test_rmse"),
        ("formal_run_id", "other-run"),
        ("formal_cutoff", "2026-09-12"),
        ("formal_git_sha", "b8bf39f8e94729687c2e877dc164ea8a4f69e2b1"),
    ],
)
def test_catalog_rejects_unsupported_or_wrong_provenance(tmp_path, field, value):
    with DEFAULT_SELECTION_PATH.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    rows[0][field] = value
    path = tmp_path / "selection.csv"
    _write_rows(path, rows)
    with pytest.raises(SelectionCatalogError):
        load_selection_catalog(path, expected_sha256=None)


def test_catalog_rejects_wrong_pinned_sha256(tmp_path):
    path = tmp_path / "selection.csv"
    path.write_bytes(DEFAULT_SELECTION_PATH.read_bytes())
    with pytest.raises(SelectionCatalogError, match="SHA-256"):
        load_selection_catalog(path, expected_sha256="0" * 64)


def test_catalog_rejects_duplicate_and_missing_symbols(tmp_path):
    with DEFAULT_SELECTION_PATH.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    path = tmp_path / "selection.csv"
    rows[-1]["symbol"] = rows[0]["symbol"]
    _write_rows(path, rows)
    with pytest.raises(SelectionCatalogError, match="Duplicate"):
        load_selection_catalog(path, expected_sha256=None)

    rows[-1]["symbol"] = "NOT_A_COMPANY"
    _write_rows(path, rows)
    with pytest.raises(SelectionCatalogError, match="Unknown"):
        load_selection_catalog(path, expected_sha256=None)


def test_catalog_rejects_missing_file_and_incomplete_company_universe(tmp_path):
    with pytest.raises(SelectionCatalogError, match="unavailable"):
        load_selection_catalog(tmp_path / "missing.csv", expected_sha256=None)
    with DEFAULT_SELECTION_PATH.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))[:-1]
    path = tmp_path / "selection.csv"
    _write_rows(path, rows)
    with pytest.raises(SelectionCatalogError, match="15 selection rows"):
        load_selection_catalog(path, expected_sha256=None)
