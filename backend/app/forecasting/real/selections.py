"""Fail-closed parser for the pinned formal ForecastPH selection snapshot."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import io
import math
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from backend.app.domain.company_universe import get_all_configured_symbols
from backend.app.forecasting.real.config import (
    DEFAULT_ARIMA_CONFIG,
    DEFAULT_LAG_REGRESSION_CONFIG,
    DEFAULT_LSTM_CONFIG,
    LstmConfig,
    LstmSpecification,
)
from backend.app.forecasting.real.models.arima import ArimaSpecification

OFFICIAL_REPOSITORY = (
    "https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git"
)
SELECTION_SOURCE_COMMIT = "b8bf39f8e94729687c2e877dc164ea8a4f69e2b1"
SELECTION_SOURCE_FILE = "backend/research-result/selected_configurations.csv"
SELECTION_SOURCE_GIT_BLOB = "60fe633c8e2860a56cb46248cd4b937c1a231833"
SELECTION_SOURCE_SHA256 = "7c648357adaba1e5769d560435bad61a933d67ebb5ee8fc1ded5944416737a97"
FORMAL_RUN_ID = "FORECASTPH_FORMAL_20260911_01"
FORMAL_CUTOFF = "2026-09-11"
FORMAL_GIT_SHA = "8359270bffcd43dd41830a01bb2f4e2d4c527b56"
SELECTION_CRITERION = "mean_validation_rmse"
FORMAL_CV_SPLITS = 5
FORMAL_TUNING_SEEDS = (11, 29, 47)
FORMAL_FINAL_SEED = 42
DEFAULT_SELECTION_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "authoritative"
    / "forecastph_selected_configurations_20260911.csv"
)


class SelectionCatalogError(ValueError):
    """Raised when the authoritative selection evidence is absent or invalid."""


@dataclass(frozen=True, slots=True)
class SelectionProvenance:
    source_repository: str = OFFICIAL_REPOSITORY
    source_snapshot_commit: str = SELECTION_SOURCE_COMMIT
    source_file: str = SELECTION_SOURCE_FILE
    source_git_blob: str = SELECTION_SOURCE_GIT_BLOB
    source_sha256: str = SELECTION_SOURCE_SHA256
    formal_run_id: str = FORMAL_RUN_ID
    formal_cutoff: str = FORMAL_CUTOFF
    formal_git_sha: str = FORMAL_GIT_SHA
    selection_criterion: str = SELECTION_CRITERION
    cv_splits: int = FORMAL_CV_SPLITS
    tuning_seeds: tuple[int, ...] = FORMAL_TUNING_SEEDS
    final_seed: int = FORMAL_FINAL_SEED

    def as_dict(self) -> dict[str, object]:
        return {
            "selection_source_repository": self.source_repository,
            "selection_snapshot_commit": self.source_snapshot_commit,
            "selection_source_file": self.source_file,
            "selection_source_git_blob": self.source_git_blob,
            "selection_source_sha256": self.source_sha256,
            "formal_run_id": self.formal_run_id,
            "formal_cutoff": self.formal_cutoff,
            "formal_git_sha": self.formal_git_sha,
            "selection_criterion": self.selection_criterion,
            "cv_splits": self.cv_splits,
            "lstm_tuning_seeds": list(self.tuning_seeds),
            "lstm_final_seed": self.final_seed,
        }


@dataclass(frozen=True, slots=True)
class AuthoritativeModelSelection:
    symbol: str
    lir_alpha: float
    arima: ArimaSpecification
    arima_convergence_status: str
    lstm: LstmSpecification
    formal_lstm_selected_epoch_count: int
    lir_selected_features_evidence: tuple[str, ...]
    provenance: SelectionProvenance


def _required(row: dict[str, str], field: str, symbol: str) -> str:
    value = row.get(field)
    if value is None or value == "":
        raise SelectionCatalogError(f"{symbol}: required field {field!r} is missing")
    return value


def _integer(row: dict[str, str], field: str, symbol: str) -> int:
    raw = _required(row, field, symbol)
    try:
        if raw.strip() != raw or any(character in raw for character in ".eE"):
            raise ValueError
        return int(raw)
    except ValueError as exc:
        raise SelectionCatalogError(f"{symbol}: {field} must be an integer") from exc


def _number(row: dict[str, str], field: str, symbol: str) -> float:
    raw = _required(row, field, symbol)
    try:
        value = float(raw)
    except ValueError as exc:
        raise SelectionCatalogError(f"{symbol}: {field} must be numeric") from exc
    if not math.isfinite(value):
        raise SelectionCatalogError(f"{symbol}: {field} must be finite")
    return value


def _boolean(row: dict[str, str], field: str, symbol: str) -> bool:
    raw = _required(row, field, symbol)
    if raw not in {"true", "false"}:
        raise SelectionCatalogError(f"{symbol}: {field} must be true or false")
    return raw == "true"


def _selection_from_row(row: dict[str, str]) -> AuthoritativeModelSelection:
    symbol = _required(row, "symbol", "row")
    lir_alpha = _number(row, "lir_selected_alpha", symbol)
    if lir_alpha <= 0 or lir_alpha not in DEFAULT_LAG_REGRESSION_CONFIG.alpha_grid:
        raise SelectionCatalogError(f"{symbol}: LIR alpha is outside the declared grid")

    order = tuple(_integer(row, f"arima_{part}", symbol) for part in ("p", "d", "q"))
    p, d, q = order
    config = DEFAULT_ARIMA_CONFIG
    trend = _required(row, "arima_trend", symbol)
    if p not in config.p_values or d not in config.d_values or q not in config.q_values:
        raise SelectionCatalogError(f"{symbol}: ARIMA order is outside the declared grid")
    if trend not in config.trends_for_d(d):
        raise SelectionCatalogError(f"{symbol}: ARIMA trend is invalid for d={d}")
    convergence = _required(row, "arima_convergence_status", symbol)
    if convergence != "confirmed_converged":
        raise SelectionCatalogError(f"{symbol}: ARIMA convergence is not confirmed")
    drift_enabled = _boolean(row, "arima_drift_enabled", symbol)
    arima = ArimaSpecification(order=(p, d, q), trend=trend)
    if arima.drift_enabled != drift_enabled:
        raise SelectionCatalogError(f"{symbol}: ARIMA drift flag disagrees with order/trend")

    lstm = LstmSpecification(
        lookback=_integer(row, "lstm_lookback", symbol),
        hidden_size=_integer(row, "lstm_hidden_size", symbol),
        learning_rate=_number(row, "lstm_learning_rate", symbol),
        batch_size=_integer(row, "lstm_batch_size", symbol),
    )
    lstm_config = DEFAULT_LSTM_CONFIG
    if (
        lstm.lookback not in lstm_config.lookback_lengths
        or lstm.hidden_size not in lstm_config.hidden_sizes
        or lstm.learning_rate not in lstm_config.learning_rates
        or lstm.batch_size not in lstm_config.batch_sizes
    ):
        raise SelectionCatalogError(f"{symbol}: LSTM specification is outside the declared grid")

    epoch_count = _integer(row, "lstm_selected_epoch_count", symbol)
    if epoch_count < 1 or epoch_count > lstm_config.max_epochs:
        raise SelectionCatalogError(f"{symbol}: formal selected epoch count is invalid")
    seeds_raw = _required(row, "lstm_tuning_seeds", symbol)
    try:
        tuning_seeds = tuple(int(seed) for seed in seeds_raw.split("|"))
    except ValueError as exc:
        raise SelectionCatalogError(f"{symbol}: malformed tuning seeds") from exc
    if tuning_seeds != FORMAL_TUNING_SEEDS:
        raise SelectionCatalogError(f"{symbol}: tuning seeds do not match formal contract")
    if _integer(row, "lstm_final_seed", symbol) != FORMAL_FINAL_SEED:
        raise SelectionCatalogError(f"{symbol}: final seed does not match formal contract")
    if _integer(row, "cv_splits", symbol) != FORMAL_CV_SPLITS:
        raise SelectionCatalogError(f"{symbol}: cv_splits does not match formal contract")
    if _required(row, "selection_criterion", symbol) != SELECTION_CRITERION:
        raise SelectionCatalogError(f"{symbol}: selection criterion mismatch")
    if _required(row, "formal_run_id", symbol) != FORMAL_RUN_ID:
        raise SelectionCatalogError(f"{symbol}: formal run id mismatch")
    if _required(row, "formal_cutoff", symbol) != FORMAL_CUTOFF:
        raise SelectionCatalogError(f"{symbol}: formal cutoff mismatch")
    if _required(row, "formal_git_sha", symbol) != FORMAL_GIT_SHA:
        raise SelectionCatalogError(f"{symbol}: formal Git SHA mismatch")

    feature_evidence = tuple(
        value
        for value in row.get("lir_selected_features", "").split("|")
        if value
    )
    return AuthoritativeModelSelection(
        symbol=symbol,
        lir_alpha=lir_alpha,
        arima=arima,
        arima_convergence_status=convergence,
        lstm=lstm,
        formal_lstm_selected_epoch_count=epoch_count,
        lir_selected_features_evidence=feature_evidence,
        provenance=SelectionProvenance(),
    )


def load_selection_catalog(
    path: Path = DEFAULT_SELECTION_PATH,
    *,
    expected_sha256: str | None = SELECTION_SOURCE_SHA256,
) -> Mapping[str, AuthoritativeModelSelection]:
    """Load, pin, and validate every company selection; no partial catalog is returned."""
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise SelectionCatalogError(f"Authoritative selection CSV is unavailable: {source}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise SelectionCatalogError("Authoritative selection CSV SHA-256 mismatch")
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if not reader.fieldnames or "symbol" not in reader.fieldnames:
            raise SelectionCatalogError("Selection CSV header is missing the symbol column")
        required_columns = {
            "symbol",
            "lir_selected_alpha",
            "lir_selected_features",
            "arima_p",
            "arima_d",
            "arima_q",
            "arima_trend",
            "arima_drift_enabled",
            "arima_convergence_status",
            "lstm_lookback",
            "lstm_hidden_size",
            "lstm_learning_rate",
            "lstm_batch_size",
            "lstm_selected_epoch_count",
            "lstm_tuning_seeds",
            "lstm_final_seed",
            "selection_criterion",
            "cv_splits",
            "formal_run_id",
            "formal_cutoff",
            "formal_git_sha",
        }
        if not required_columns <= set(reader.fieldnames):
            missing_columns = sorted(required_columns - set(reader.fieldnames))
            raise SelectionCatalogError(f"Selection CSV is missing columns: {missing_columns}")
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise SelectionCatalogError("Selection CSV is malformed") from exc
    if len(rows) != 15:
        raise SelectionCatalogError(f"Expected 15 selection rows, found {len(rows)}")

    selections: dict[str, AuthoritativeModelSelection] = {}
    canonical = set(get_all_configured_symbols())
    for row in rows:
        if None in row:
            raise SelectionCatalogError("Selection CSV row contains unexpected extra columns")
        selection = _selection_from_row(row)
        if selection.symbol not in canonical:
            raise SelectionCatalogError(f"Unknown selection symbol: {selection.symbol}")
        if selection.symbol in selections:
            raise SelectionCatalogError(f"Duplicate selection symbol: {selection.symbol}")
        selections[selection.symbol] = selection
    missing = canonical - selections.keys()
    if missing:
        raise SelectionCatalogError(f"Missing canonical selections: {sorted(missing)}")
    return MappingProxyType(selections)
