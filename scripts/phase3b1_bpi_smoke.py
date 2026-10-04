"""Run the bounded Phase 3B.1 BPI LSTM refit and safe-reload smoke offline."""

from __future__ import annotations

import csv
from datetime import date
import hashlib
import json
import logging
from pathlib import Path
import shutil
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.forecasting.real.artifacts.lstm_state import (  # noqa: E402
    load_lstm_state_artifact,
    persist_lstm_state_artifact,
)
from backend.app.forecasting.real.calendar import PSETradingCalendar  # noqa: E402
from backend.app.forecasting.real.domain import OhlcvRecord  # noqa: E402
from backend.app.forecasting.real.models.lstm import build_delta_sequence_samples  # noqa: E402
from backend.app.forecasting.real.selections import load_selection_catalog  # noqa: E402
from backend.app.forecasting.real.training.lstm import refit_lstm_for_production  # noqa: E402

SOURCE_BPI = Path("/tmp/pse-pulse-official-source/backend/data/raw/BPI.csv")
OUTPUT = Path("/tmp/pse-pulse-phase3b1-smoke")
LOGGER = logging.getLogger("phase3b1_bpi_smoke")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_records(path: Path) -> tuple[OhlcvRecord, ...]:
    records: list[OhlcvRecord] = []
    with path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            records.append(
                OhlcvRecord(
                    trading_date=date.fromisoformat(row["Date"]),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                )
            )
    return tuple(records)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    LOGGER.info("Starting bounded BPI-only Phase 3B.1 offline smoke")
    if not SOURCE_BPI.is_file():
        raise FileNotFoundError(f"Pinned official BPI source data missing: {SOURCE_BPI}")
    if OUTPUT.exists():
        LOGGER.info("Removing prior smoke-only output directory %s", OUTPUT)
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    LOGGER.info("Loading official BPI history and selection catalog")
    records = _load_records(SOURCE_BPI)
    if (
        len(records) != 1649
        or records[0].trading_date != date(2020, 1, 2)
        or records[-1].trading_date != date(2026, 10, 1)
    ):
        raise RuntimeError("BPI smoke history does not match the accepted source boundary")
    bpi = load_selection_catalog()["BPI"]
    if bpi.formal_lstm_selected_epoch_count != 9:
        raise RuntimeError("BPI formal LSTM epoch evidence does not match the catalog")
    LOGGER.info(
        "Authoritative BPI LSTM specification=%s formal_epoch_evidence=%d rows=%d",
        bpi.lstm.as_dict(),
        bpi.formal_lstm_selected_epoch_count,
        len(records),
    )

    LOGGER.info("Running fresh Stage A epoch selection and Stage B full-history refit")
    production_fit = refit_lstm_for_production(
        records,
        selected_specification=bpi.lstm,
    )
    fitted = production_fit.fitted
    LOGGER.info(
        "Refit complete stage_a_epochs=%d formal_epoch_evidence=%d seed=%d samples=%d",
        production_fit.epoch_selection.selected_epoch_count,
        bpi.formal_lstm_selected_epoch_count,
        fitted.seed,
        fitted.training_size,
    )

    artifact_dir = OUTPUT / "BPI"
    artifact_path, metadata_path, metadata = persist_lstm_state_artifact(
        output_directory=artifact_dir,
        symbol="BPI",
        model_version="phase3b1-smoke",
        fitted=fitted,
        data_row_count=len(records),
        trained_through=records[-1].trading_date,
        formal_selected_epoch_count=bpi.formal_lstm_selected_epoch_count,
        selection_provenance=bpi.provenance,
    )
    metadata["artifact_authority"] = "NON_AUTHORITATIVE"
    metadata["purpose"] = "Phase 3B.1 one-company offline smoke only"
    metadata["historical_csv_sha256"] = _sha256(SOURCE_BPI)
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    history_path = artifact_dir / "lstm-training-history.json"
    history_path.write_text(
        json.dumps(
            {
                "symbol": "BPI",
                "formal_selected_epoch_count": bpi.formal_lstm_selected_epoch_count,
                "production_stage_a": production_fit.epoch_selection.as_dict(),
                "stage_b": {
                    "selected_epoch_count": fitted.epoch_count,
                    "seed": fitted.seed,
                    "training_size": fitted.training_size,
                    "scaler": fitted.scaler.state_dict(),
                    "training_target_date_first": records[6].trading_date.isoformat(),
                    "training_target_date_last": records[-1].trading_date.isoformat(),
                },
            },
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    LOGGER.info("Reloading the persisted state through the checksum-first safe loader")
    loaded = load_lstm_state_artifact(
        symbol_directory=artifact_dir,
        expected_symbol="BPI",
        expected_model_version="phase3b1-smoke",
        expected_trained_through=records[-1].trading_date,
        expected_data_row_count=len(records),
    )
    deltas = np.asarray(
        [records[index].close - records[index - 1].close for index in range(1, len(records))],
        dtype=np.float64,
    )
    latest = deltas[-bpi.lstm.lookback :]
    predicted_delta = float(loaded.model.predict_delta_sequences(latest)[0])
    origin_close = records[-1].close
    predicted_close = origin_close + predicted_delta
    target_date = PSETradingCalendar().next_trading_day(records[-1].trading_date)
    if not np.isfinite([predicted_delta, predicted_close]).all() or predicted_close <= 0:
        raise RuntimeError("Safe-reload BPI LSTM inference produced invalid values")

    result = {
        "symbol": "BPI",
        "model_code": "LSTM",
        "model_version": "phase3b1-smoke",
        "artifact_format": "pytorch_state_dict",
        "artifact_filename": artifact_path.name,
        "artifact_sha256": _sha256(artifact_path),
        "trained_through": records[-1].trading_date.isoformat(),
        "raw_data_row_count": len(records),
        "training_size": fitted.training_size,
        "lookback": bpi.lstm.lookback,
        "hidden_size": bpi.lstm.hidden_size,
        "learning_rate": bpi.lstm.learning_rate,
        "batch_size": bpi.lstm.batch_size,
        "formal_selected_epoch_count": bpi.formal_lstm_selected_epoch_count,
        "production_selected_epoch_count": production_fit.epoch_selection.selected_epoch_count,
        "seed": fitted.seed,
        "scaler": fitted.scaler.state_dict(),
        "selection_provenance": bpi.provenance.as_dict(),
        "source_provenance": {
            "repository": metadata["source_repository"],
            "commit": metadata["source_commit"],
            "historical_data_commit": metadata["historical_data_source_commit"],
            "historical_csv_sha256": metadata["historical_csv_sha256"],
        },
        "inference": {
            "loaded_through": records[-1].trading_date.isoformat(),
            "target_date": target_date.isoformat(),
            "origin_close": origin_close,
            "predicted_delta": predicted_delta,
            "predicted_close": predicted_close,
            "persisted_forecast_row": False,
        },
        "environment": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "numpy": np.__version__,
        },
    }
    (OUTPUT / "acceptance.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    LOGGER.info("Completed smoke; acceptance summary: %s", OUTPUT / "acceptance.json")
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
