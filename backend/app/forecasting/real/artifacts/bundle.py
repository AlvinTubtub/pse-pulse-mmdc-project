"""Atomic authoritative bundle construction and fail-closed manifest verification."""

from __future__ import annotations

from collections import Counter
from datetime import date
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any, Callable

from backend.app.domain.company_universe import get_all_configured_symbols
from backend.app.forecasting.real.artifacts.authoritative import load_authoritative_model
from backend.app.forecasting.real.artifacts.schema import ModelArtifactCompatibilityError
from backend.app.forecasting.real.artifacts.writer import compute_artifact_sha256
from backend.app.forecasting.real.selections import load_selection_catalog

BUNDLE_SCHEMA_ID = "pse-pulse.production-bundle"
BUNDLE_SCHEMA_VERSION = 1
ACCEPTANCE_BUNDLE_VERSION = "2026.10.01-authoritative-v1"
MODEL_FAMILY_ORDER = ("LAG_REGRESSION", "ARIMA", "LSTM")
EXPECTED_HISTORY_FIRST_DATE = date(2020, 1, 2)
EXPECTED_TRAINED_THROUGH = date(2026, 10, 1)
EXPECTED_ROWS_PER_SYMBOL = 1649


class ProductionBundleError(ValueError):
    """Raised when bundle construction or verification fails closed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entry_key(entry: dict[str, Any]) -> tuple[str, int]:
    try:
        return str(entry["symbol"]), MODEL_FAMILY_ORDER.index(str(entry["model_code"]))
    except (KeyError, ValueError) as exc:
        raise ProductionBundleError("Manifest contains an unknown model family or missing identity") from exc


def validate_manifest_shape(manifest: Any) -> list[dict[str, Any]]:
    """Validate cardinality and identity before touching any artifact paths."""
    if not isinstance(manifest, dict):
        raise ProductionBundleError("Bundle manifest must be a JSON object")
    if manifest.get("schema_id") != BUNDLE_SCHEMA_ID or manifest.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise ProductionBundleError("Unsupported production bundle schema")
    if manifest.get("bundle_version") != ACCEPTANCE_BUNDLE_VERSION:
        raise ProductionBundleError("Unexpected authoritative bundle version")
    symbols = list(get_all_configured_symbols())
    if manifest.get("symbols") != symbols:
        raise ProductionBundleError("Manifest symbols differ from the canonical company universe")
    if manifest.get("model_families") != list(MODEL_FAMILY_ORDER):
        raise ProductionBundleError("Manifest model family list is invalid")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or len(entries) != 45:
        raise ProductionBundleError("Manifest must contain exactly 45 model entries")
    counts: Counter[tuple[str, str]] = Counter()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ProductionBundleError("Manifest entries must be JSON objects")
        symbol = entry.get("symbol")
        family = entry.get("model_code")
        if symbol not in symbols or family not in MODEL_FAMILY_ORDER:
            raise ProductionBundleError(f"Unknown manifest identity: {symbol!r}/{family!r}")
        counts[(symbol, family)] += 1
    expected = {(symbol, family) for symbol in symbols for family in MODEL_FAMILY_ORDER}
    if set(counts) != expected or any(count != 1 for count in counts.values()):
        raise ProductionBundleError("Manifest must contain exactly one entry per company and model family")
    if entries != sorted(entries, key=_entry_key):
        raise ProductionBundleError("Manifest entries are not in canonical deterministic order")
    if manifest.get("model_artifact_count") != 45 or manifest.get("metadata_file_count") != 45:
        raise ProductionBundleError("Manifest artifact and metadata totals must both be 45")
    if manifest.get("history_first_date") != EXPECTED_HISTORY_FIRST_DATE.isoformat():
        raise ProductionBundleError("Manifest history first date is invalid")
    if manifest.get("trained_through") != EXPECTED_TRAINED_THROUGH.isoformat():
        raise ProductionBundleError("Manifest trained_through is invalid")
    if manifest.get("history_row_count_per_symbol") != EXPECTED_ROWS_PER_SYMBOL:
        raise ProductionBundleError("Manifest per-symbol history row count is invalid")
    if manifest.get("total_history_rows") != EXPECTED_ROWS_PER_SYMBOL * len(symbols):
        raise ProductionBundleError("Manifest total history row count is invalid")
    return entries


def _safe_bundle_file(root: Path, relative_path: Any) -> Path:
    if not isinstance(relative_path, str):
        raise ProductionBundleError("Manifest artifact paths must be strings")
    posix = PurePosixPath(relative_path)
    if posix.is_absolute() or ".." in posix.parts or "\\" in relative_path or not posix.parts:
        raise ProductionBundleError(f"Unsafe manifest path: {relative_path!r}")
    resolved_root = root.resolve()
    candidate = (root / Path(*posix.parts)).resolve()
    if candidate == resolved_root or resolved_root not in candidate.parents:
        raise ProductionBundleError(f"Manifest path escapes bundle root: {relative_path!r}")
    if not candidate.is_file():
        raise ProductionBundleError(f"Bundle file is missing: {relative_path}")
    return candidate


def verify_bundle(bundle_directory: Path) -> dict[str, Any]:
    """Verify hashes, authoritative metadata, then safe-reload all 45 artifacts."""
    if Path(bundle_directory).is_symlink():
        raise ProductionBundleError("Bundle directory must not be a symlink")
    root = Path(bundle_directory).resolve()
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductionBundleError("Bundle manifest is missing or unreadable") from exc
    entries = validate_manifest_shape(manifest)
    catalog = load_selection_catalog()
    first_selection = catalog[get_all_configured_symbols()[0]]
    if manifest.get("official_methodology_provenance") != {
        "repository": "https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git",
        "commit": "b8bf39f8e94729687c2e877dc164ea8a4f69e2b1",
    }:
        raise ProductionBundleError("Manifest official methodology provenance is invalid")
    history_provenance = manifest.get("historical_data_provenance")
    if not isinstance(history_provenance, dict) or history_provenance.get("repository") != "https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git" or history_provenance.get("commit") != "b8bf39f8e94729687c2e877dc164ea8a4f69e2b1":
        raise ProductionBundleError("Manifest historical data provenance is invalid")
    selection_provenance = manifest.get("authoritative_selection_provenance")
    if not isinstance(selection_provenance, dict):
        raise ProductionBundleError("Manifest selection provenance is missing")
    for key, expected in first_selection.provenance.as_dict().items():
        if selection_provenance.get(key) != expected:
            raise ProductionBundleError("Manifest formal selection provenance is invalid")
    if selection_provenance.get("selection_csv_sha256") != "7c648357adaba1e5769d560435bad61a933d67ebb5ee8fc1ded5944416737a97" or selection_provenance.get("selection_csv_git_blob") != "60fe633c8e2860a56cb46248cd4b937c1a231833":
        raise ProductionBundleError("Manifest pinned selection snapshot identity is invalid")
    formal_run = manifest.get("formal_run")
    if formal_run != {
        "run_id": first_selection.provenance.formal_run_id,
        "cutoff": first_selection.provenance.formal_cutoff,
        "experiment_git_sha": first_selection.provenance.formal_git_sha,
    }:
        raise ProductionBundleError("Manifest formal run identity is invalid")
    tracked_files = {"manifest.json"}
    for entry in entries:
        symbol = entry["symbol"]
        family = entry["model_code"]
        expected_binary = {
            "LAG_REGRESSION": "lag_regression.joblib",
            "ARIMA": "arima.joblib",
            "LSTM": "lstm.pt",
        }[family]
        expected_metadata = {
            "LAG_REGRESSION": "lag_regression.metadata.json",
            "ARIMA": "arima.metadata.json",
            "LSTM": "lstm.metadata.json",
        }[family]
        if entry.get("artifact_relative_path") != f"{symbol}/{expected_binary}":
            raise ProductionBundleError("Manifest artifact path does not match its identity")
        if entry.get("metadata_relative_path") != f"{symbol}/{expected_metadata}":
            raise ProductionBundleError("Manifest metadata path does not match its identity")
        artifact_path = _safe_bundle_file(root, entry["artifact_relative_path"])
        metadata_path = _safe_bundle_file(root, entry["metadata_relative_path"])
        tracked_files.update((entry["artifact_relative_path"], entry["metadata_relative_path"]))
        artifact_sha = sha256_file(artifact_path)
        metadata_sha = sha256_file(metadata_path)
        if artifact_sha != entry.get("artifact_sha256") or metadata_sha != entry.get("metadata_sha256"):
            raise ProductionBundleError(f"Bundle checksum mismatch: {symbol}/{family}")
        if artifact_path.stat().st_size != entry.get("artifact_size_bytes"):
            raise ProductionBundleError(f"Artifact size mismatch: {symbol}/{family}")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProductionBundleError(f"Unreadable metadata: {symbol}/{family}") from exc
        if not isinstance(metadata, dict):
            raise ProductionBundleError(f"Metadata must be an object: {symbol}/{family}")
        for key in ("symbol", "model_code", "model_version", "artifact_format", "trained_through", "data_row_count"):
            if metadata.get(key) != entry.get(key):
                raise ProductionBundleError(f"Manifest/metadata mismatch for {symbol}/{family}: {key}")
        if entry.get("model_version") != ACCEPTANCE_BUNDLE_VERSION:
            raise ProductionBundleError("Entry model_version differs from accepted bundle version")
        if entry.get("trained_through") != EXPECTED_TRAINED_THROUGH.isoformat() or entry.get("data_row_count") != EXPECTED_ROWS_PER_SYMBOL:
            raise ProductionBundleError(f"Invalid history boundary in entry for {symbol}/{family}")
        selection = catalog[symbol]
        if entry.get("selection_provenance") != selection.provenance.as_dict():
            raise ProductionBundleError(f"Manifest selection provenance mismatch for {symbol}/{family}")
        if family == "LAG_REGRESSION":
            if entry.get("selection") != {"alpha": selection.lir_alpha}:
                raise ProductionBundleError(f"LIR selection mismatch for {symbol}")
            model, loaded = load_authoritative_model(
                symbol_directory=root / symbol,
                expected_symbol=symbol,
                expected_model_code=family,
                expected_model_version=ACCEPTANCE_BUNDLE_VERSION,
                trained_through=EXPECTED_TRAINED_THROUGH,
                data_row_count=EXPECTED_ROWS_PER_SYMBOL,
            )
            expected_evidence = {
                "authoritative_alpha": selection.lir_alpha,
                "production_pacf_selected_return_lags": metadata["hyperparameters"]["pacf_selected_lags"],
                "production_feature_names": metadata["hyperparameters"]["feature_names"],
                "production_feature_count": metadata["hyperparameters"]["feature_count"],
                "formal_selected_features_evidence_only": metadata["hyperparameters"]["formal_selected_features_evidence"],
            }
            if entry.get("model_evidence") != expected_evidence:
                raise ProductionBundleError(f"Manifest LIR evidence mismatch for {symbol}")
        elif family == "ARIMA":
            if entry.get("selection") != selection.arima.as_dict():
                raise ProductionBundleError(f"ARIMA selection mismatch for {symbol}")
            model, loaded = load_authoritative_model(
                symbol_directory=root / symbol,
                expected_symbol=symbol,
                expected_model_code=family,
                expected_model_version=ACCEPTANCE_BUNDLE_VERSION,
                trained_through=EXPECTED_TRAINED_THROUGH,
                data_row_count=EXPECTED_ROWS_PER_SYMBOL,
            )
            arima_hp = metadata["hyperparameters"]
            expected_evidence = {
                "authoritative_order": arima_hp["order"],
                "authoritative_trend": arima_hp["trend"],
                "convergence_status": arima_hp["convergence_status"],
                "fit_attempts": arima_hp["fit_evidence"]["fit_attempts"],
            }
            if entry.get("model_evidence") != expected_evidence:
                raise ProductionBundleError(f"Manifest ARIMA evidence mismatch for {symbol}")
        else:
            from backend.app.forecasting.real.artifacts.lstm_state import load_lstm_state_artifact

            expected_lstm = selection.lstm.as_dict()
            if entry.get("selection") != expected_lstm:
                raise ProductionBundleError(f"LSTM selection mismatch for {symbol}")
            lstm = load_lstm_state_artifact(
                symbol_directory=root / symbol,
                expected_symbol=symbol,
                expected_model_version=ACCEPTANCE_BUNDLE_VERSION,
                expected_trained_through=EXPECTED_TRAINED_THROUGH,
                expected_data_row_count=EXPECTED_ROWS_PER_SYMBOL,
            )
            model, loaded = lstm.model, lstm.metadata
            if loaded != metadata:
                raise ProductionBundleError(f"Safe-loaded LSTM metadata differs from manifest file for {symbol}")
            lstm_hp = metadata["hyperparameters"]
            expected_evidence = {
                **selection.lstm.as_dict(),
                "formal_selected_epoch_count": lstm_hp["formal_selected_epoch_count"],
                "production_selected_epoch_count": lstm_hp["production_selected_epoch_count"],
                "seed": lstm_hp["seed"],
            }
            if entry.get("model_evidence") != expected_evidence:
                raise ProductionBundleError(f"Manifest LSTM evidence mismatch for {symbol}")
        loaded_symbol = loaded.symbol if hasattr(loaded, "symbol") else loaded.get("symbol")
        if loaded_symbol != symbol:
            raise ProductionBundleError(f"Safe loader identity mismatch for {symbol}/{family}")
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    if actual_files != tracked_files:
        raise ProductionBundleError(f"Bundle contains missing or unmanifested files: {sorted(actual_files ^ tracked_files)}")
    if any(path.is_symlink() for path in root.rglob("*")):
        raise ProductionBundleError("Bundle must not contain symlinks")
    return {"bundle_version": manifest["bundle_version"], "artifact_count": 45, "safe_reload_count": 45}


def ensure_external_output_root(repository_root: Path, output_root: Path) -> Path:
    repository = Path(repository_root).resolve()
    external = Path(output_root).expanduser().resolve()
    if external == repository or repository in external.parents:
        raise ProductionBundleError("Artifact output root must resolve outside the Git repository")
    return external


def build_atomically(
    *,
    repository_root: Path,
    output_root: Path,
    bundle_version: str,
    builder: Callable[[Path], Any],
    verifier: Callable[[Path], Any],
) -> tuple[Path, Any]:
    """Build and verify in a sibling staging directory, then atomically rename."""
    if bundle_version != ACCEPTANCE_BUNDLE_VERSION:
        raise ProductionBundleError("Unexpected acceptance bundle version")
    external_root = ensure_external_output_root(repository_root, output_root)
    external_root.mkdir(parents=True, exist_ok=True)
    final_directory = external_root / bundle_version
    if os.path.lexists(final_directory):
        raise ProductionBundleError(f"Final bundle target already exists: {final_directory}")
    staging = Path(tempfile.mkdtemp(prefix=f".{bundle_version}.staging-", dir=external_root))
    try:
        builder(staging)
        result = verifier(staging)
        if os.path.lexists(final_directory):
            raise ProductionBundleError(f"Final bundle target appeared during build: {final_directory}")
        os.rename(staging, final_directory)
        return final_directory, result
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
