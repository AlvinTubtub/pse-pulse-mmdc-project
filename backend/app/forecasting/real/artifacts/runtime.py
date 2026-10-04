"""Manifest-driven, family-aware production artifact loading.

The module itself is PyTorch-free.  Torch-backed code is imported only when an
LSTM entry is explicitly requested.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from backend.app.forecasting.real.artifacts.authoritative import load_authoritative_model
from backend.app.forecasting.real.artifacts.bundle import (
    ACCEPTANCE_BUNDLE_VERSION,
    MODEL_FAMILY_ORDER,
    ProductionBundleError,
    validate_manifest_shape,
)
from backend.app.forecasting.real.artifacts.schema import ModelArtifactCompatibilityError

ACCEPTED_MANIFEST_SHA256 = "4225e60044f000b16147e01f6ff165968523c1efd9647e57d9c7a6f5f5a27454"


@dataclass(frozen=True, slots=True)
class RuntimeArtifact:
    model: Any
    metadata: Any
    entry: Mapping[str, Any]
    bundle_root: Path


def _safe_file(root: Path, relative: object) -> Path:
    if not isinstance(relative, str):
        raise ModelArtifactCompatibilityError("Manifest path must be a string")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts or "\\" in relative or not posix.parts:
        raise ModelArtifactCompatibilityError(f"Unsafe manifest path: {relative!r}")
    unresolved = root / Path(*posix.parts)
    cursor = root
    for part in posix.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ModelArtifactCompatibilityError(f"Manifest path contains a symlink: {relative}")
    resolved_root = root.resolve()
    path = unresolved.resolve()
    if resolved_root not in path.parents or not path.is_file():
        raise ModelArtifactCompatibilityError(f"Manifest file missing or outside bundle: {relative}")
    return path


def read_verified_manifest(bundle_root: Path, *, expected_version: str = ACCEPTANCE_BUNDLE_VERSION) -> tuple[dict[str, Any], str]:
    """Read and verify manifest identity and digest before loading any model."""
    if Path(bundle_root).is_symlink():
        raise ModelArtifactCompatibilityError("Bundle directory must not be a symlink")
    root = Path(bundle_root).resolve()
    manifest_path = _safe_file(root, "manifest.json")
    raw = manifest_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    manifest = json.loads(raw)
    entries = validate_manifest_shape(manifest)
    if manifest["bundle_version"] != expected_version:
        raise ModelArtifactCompatibilityError("Bundle version confirmation mismatch")
    if len(entries) != 45 or len(manifest["symbols"]) != 15 or tuple(manifest["model_families"]) != MODEL_FAMILY_ORDER:
        raise ModelArtifactCompatibilityError("Manifest inventory is not the accepted 15 by 3 universe")
    return manifest, digest


def load_runtime_artifact(
    *, bundle_root: Path,
    symbol: str,
    model_code: str,
    expected_version: str = ACCEPTANCE_BUNDLE_VERSION,
    expected_manifest_sha256: str | None = None,
) -> RuntimeArtifact:
    """Load exactly the manifest-bound family, preserving pre-deserialization SHA checks."""
    root = Path(bundle_root).resolve()
    manifest, manifest_sha = read_verified_manifest(root, expected_version=expected_version)
    if manifest_sha != ACCEPTED_MANIFEST_SHA256:
        raise ModelArtifactCompatibilityError("Runtime manifest SHA-256 is not the accepted frozen bundle identity")
    if expected_manifest_sha256 is not None and manifest_sha != expected_manifest_sha256:
        raise ModelArtifactCompatibilityError("Bundle manifest SHA-256 mismatch")
    matches = [e for e in manifest["entries"] if e["symbol"] == symbol and e["model_code"] == model_code]
    if len(matches) != 1:
        raise ModelArtifactCompatibilityError(f"Expected exactly one manifest entry for {symbol}/{model_code}")
    entry = matches[0]
    artifact_path = _safe_file(root, entry["artifact_relative_path"])
    metadata_path = _safe_file(root, entry["metadata_relative_path"])
    for path, key in ((artifact_path, "artifact_sha256"), (metadata_path, "metadata_sha256")):
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry[key]:
            raise ModelArtifactCompatibilityError(f"Manifest checksum mismatch: {entry[key]}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ModelArtifactCompatibilityError("Artifact metadata must be an object")
    expected_fields = {
        "symbol": symbol,
        "model_code": model_code,
        "model_version": expected_version,
        "artifact_format": entry["artifact_format"],
        "trained_through": entry["trained_through"],
        "data_row_count": entry["data_row_count"],
    }
    if any(metadata.get(key) != value for key, value in expected_fields.items()):
        raise ModelArtifactCompatibilityError(f"Metadata disagrees with manifest for {symbol}/{model_code}")
    if model_code in ("LAG_REGRESSION", "ARIMA"):
        if entry["artifact_format"] != "joblib":
            raise ModelArtifactCompatibilityError("Joblib model family has an unexpected artifact format")
        model, loaded_metadata = load_authoritative_model(
            symbol_directory=artifact_path.parent,
            expected_symbol=symbol,
            expected_model_code=model_code,
            expected_model_version=expected_version,
            trained_through=date.fromisoformat(entry["trained_through"]),
            data_row_count=entry["data_row_count"],
        )
        return RuntimeArtifact(model, loaded_metadata, entry, root)
    if model_code == "LSTM":
        if entry["artifact_format"] != "pytorch_state_dict":
            raise ModelArtifactCompatibilityError("LSTM artifact format mismatch")
        # Importing the safe LSTM loader is the sole runtime boundary that imports torch.
        from backend.app.forecasting.real.artifacts.lstm_state import load_lstm_state_artifact

        loaded = load_lstm_state_artifact(
            symbol_directory=artifact_path.parent,
            expected_symbol=symbol,
            expected_model_version=expected_version,
            expected_trained_through=date.fromisoformat(entry["trained_through"]),
            expected_data_row_count=entry["data_row_count"],
        )
        if dict(loaded.metadata) != metadata:
            raise ModelArtifactCompatibilityError("Safe-loaded LSTM metadata changed during load")
        return RuntimeArtifact(loaded.model, metadata, entry, root)
    raise ProductionBundleError(f"Unsupported runtime model family: {model_code}")
