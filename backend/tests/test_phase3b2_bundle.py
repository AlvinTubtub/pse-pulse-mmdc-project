"""Bounded manifest and atomicity tests; production training is never run here."""

from datetime import date
import json
import os
import sys
from types import ModuleType
from types import SimpleNamespace
from pathlib import Path

import pytest

from backend.app.domain.company_universe import get_all_configured_symbols
from backend.app.forecasting.real.artifacts import bundle as bundle_module
from backend.app.forecasting.real.artifacts.bundle import (
    ACCEPTANCE_BUNDLE_VERSION,
    BUNDLE_SCHEMA_ID,
    BUNDLE_SCHEMA_VERSION,
    EXPECTED_HISTORY_FIRST_DATE,
    EXPECTED_ROWS_PER_SYMBOL,
    EXPECTED_TRAINED_THROUGH,
    MODEL_FAMILY_ORDER,
    ProductionBundleError,
    build_atomically,
    sha256_file,
    validate_manifest_shape,
    verify_bundle,
)
from backend.app.forecasting.real.selections import load_selection_catalog
from backend.app.forecasting.real.training import bundle as training_bundle
from backend.app.forecasting.real.training.bundle import _persist_lstm_manifest_entry


def _fake_bundle(root: Path, monkeypatch) -> dict:
    catalog = load_selection_catalog()
    entries = []
    metadata_filenames = {
        "LAG_REGRESSION": ("lag_regression.joblib", "lag_regression.metadata.json"),
        "ARIMA": ("arima.joblib", "arima.metadata.json"),
        "LSTM": ("lstm.pt", "lstm.metadata.json"),
    }
    for symbol in get_all_configured_symbols():
        selection = catalog[symbol]
        directory = root / symbol
        directory.mkdir(parents=True)
        for family in MODEL_FAMILY_ORDER:
            binary_name, metadata_name = metadata_filenames[family]
            binary = directory / binary_name
            binary.write_bytes(f"fixture:{symbol}:{family}".encode())
            common = {
                "symbol": symbol,
                "model_code": family,
                "model_version": ACCEPTANCE_BUNDLE_VERSION,
                "artifact_format": "pytorch_state_dict" if family == "LSTM" else "joblib",
                "trained_through": EXPECTED_TRAINED_THROUGH.isoformat(),
                "data_row_count": EXPECTED_ROWS_PER_SYMBOL,
            }
            provenance = selection.provenance.as_dict()
            if family == "LAG_REGRESSION":
                hp = {
                    "alpha": selection.lir_alpha,
                    "feature_names": ["feature"],
                    "pacf_selected_lags": [],
                    "feature_count": 1,
                    "formal_selected_features_evidence": [],
                    "hyperparameter_regime": "AUTHORITATIVE",
                    "test_only_smoke": False,
                    "selection_provenance": provenance,
                }
                selection_summary = {"alpha": selection.lir_alpha}
                evidence = {
                    "authoritative_alpha": selection.lir_alpha,
                    "production_pacf_selected_return_lags": [],
                    "production_feature_names": ["feature"],
                    "production_feature_count": 1,
                    "formal_selected_features_evidence_only": [],
                }
            elif family == "ARIMA":
                hp = {
                    "order": list(selection.arima.order),
                    "trend": selection.arima.trend,
                    "convergence_status": "confirmed_converged",
                    "fit_evidence": {
                        "convergence_status": "confirmed_converged",
                        "fit_attempts": [],
                    },
                    "hyperparameter_regime": "AUTHORITATIVE",
                    "test_only_smoke": False,
                    "selection_provenance": provenance,
                }
                selection_summary = selection.arima.as_dict()
                evidence = {
                    "authoritative_order": list(selection.arima.order),
                    "authoritative_trend": selection.arima.trend,
                    "convergence_status": "confirmed_converged",
                    "fit_attempts": [],
                }
            else:
                hp = {
                    **selection.lstm.as_dict(),
                    "formal_selected_epoch_count": selection.formal_lstm_selected_epoch_count,
                    "production_selected_epoch_count": 3,
                    "seed": 42,
                }
                selection_summary = selection.lstm.as_dict()
                evidence = {
                    **selection.lstm.as_dict(),
                    "formal_selected_epoch_count": selection.formal_lstm_selected_epoch_count,
                    "production_selected_epoch_count": 3,
                    "seed": 42,
                }
            metadata = {**common, "hyperparameters": hp}
            metadata_path = directory / metadata_name
            metadata_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
            entries.append({
                **common,
                "artifact_relative_path": f"{symbol}/{binary_name}",
                "artifact_sha256": sha256_file(binary),
                "artifact_size_bytes": binary.stat().st_size,
                "metadata_relative_path": f"{symbol}/{metadata_name}",
                "metadata_sha256": sha256_file(metadata_path),
                "selection": selection_summary,
                "selection_provenance": provenance,
                "model_evidence": evidence,
            })
    entries.sort(key=lambda item: (item["symbol"], MODEL_FAMILY_ORDER.index(item["model_code"])))
    first = catalog[get_all_configured_symbols()[0]].provenance
    manifest = {
        "schema_id": BUNDLE_SCHEMA_ID,
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "bundle_version": ACCEPTANCE_BUNDLE_VERSION,
        "symbols": list(get_all_configured_symbols()),
        "model_families": list(MODEL_FAMILY_ORDER),
        "model_artifact_count": 45,
        "metadata_file_count": 45,
        "history_first_date": EXPECTED_HISTORY_FIRST_DATE.isoformat(),
        "trained_through": EXPECTED_TRAINED_THROUGH.isoformat(),
        "history_row_count_per_symbol": EXPECTED_ROWS_PER_SYMBOL,
        "total_history_rows": EXPECTED_ROWS_PER_SYMBOL * 15,
        "official_methodology_provenance": {
            "repository": "https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git",
            "commit": "b8bf39f8e94729687c2e877dc164ea8a4f69e2b1",
        },
        "historical_data_provenance": {
            "repository": "https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git",
            "commit": "b8bf39f8e94729687c2e877dc164ea8a4f69e2b1",
            "csv_sha256_by_symbol": {},
        },
        "authoritative_selection_provenance": {
            **first.as_dict(),
            "selection_csv_sha256": "7c648357adaba1e5769d560435bad61a933d67ebb5ee8fc1ded5944416737a97",
            "selection_csv_git_blob": "60fe633c8e2860a56cb46248cd4b937c1a231833",
        },
        "formal_run": {
            "run_id": first.formal_run_id,
            "cutoff": first.formal_cutoff,
            "experiment_git_sha": first.formal_git_sha,
        },
        "entries": entries,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    class Loaded:
        symbol = ""

    def fake_authoritative_loader(*, expected_symbol, **kwargs):
        loaded = Loaded()
        loaded.symbol = expected_symbol
        return object(), loaded

    monkeypatch.setattr(bundle_module, "load_authoritative_model", fake_authoritative_loader)
    def fake_lstm_loader(*, symbol_directory, expected_symbol, **kwargs):
        class Fake:
            metadata = json.loads((symbol_directory / "lstm.metadata.json").read_text(encoding="utf-8"))
            model = object()
        return Fake()

    fake_lstm_state = ModuleType("backend.app.forecasting.real.artifacts.lstm_state")
    fake_lstm_state.load_lstm_state_artifact = fake_lstm_loader
    monkeypatch.setitem(sys.modules, fake_lstm_state.__name__, fake_lstm_state)
    return manifest


def test_bundle_manifest_verifies_45_fake_safe_reload_contracts(tmp_path, monkeypatch):
    _fake_bundle(tmp_path, monkeypatch)
    result = verify_bundle(tmp_path)
    assert result["artifact_count"] == result["safe_reload_count"] == 45


def test_lstm_bundle_persistence_uses_three_value_contract_and_builds_entry(tmp_path):
    symbol = "BPI"
    selection = load_selection_catalog()[symbol]
    symbol_directory = tmp_path / symbol
    symbol_directory.mkdir()
    bundle_root = tmp_path
    production_fit = SimpleNamespace(
        fitted=SimpleNamespace(seed=42),
        epoch_selection=SimpleNamespace(selected_epoch_count=12),
    )
    calls = []

    def three_value_persist(*, output_directory, **kwargs):
        artifact_path = output_directory / "lstm.pt"
        metadata_path = output_directory / "lstm.metadata.json"
        artifact_path.write_bytes(b"safe-state-dict-fixture")
        metadata = {
            "symbol": symbol,
            "model_code": "LSTM",
            "model_version": ACCEPTANCE_BUNDLE_VERSION,
            "artifact_format": "pytorch_state_dict",
            "trained_through": EXPECTED_TRAINED_THROUGH.isoformat(),
            "data_row_count": EXPECTED_ROWS_PER_SYMBOL,
            "artifact_sha256": sha256_file(artifact_path),
        }
        metadata_path.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
        calls.append(kwargs)
        return artifact_path, metadata_path, metadata

    entry = _persist_lstm_manifest_entry(
        persist_artifact=three_value_persist,
        output_directory=symbol_directory,
        bundle_directory=bundle_root,
        symbol=symbol,
        model_version=ACCEPTANCE_BUNDLE_VERSION,
        selection=selection,
        production_fit=production_fit,
    )

    assert len(calls) == 1
    assert entry["artifact_sha256"] == sha256_file(symbol_directory / "lstm.pt")
    assert entry["metadata_sha256"] == sha256_file(symbol_directory / "lstm.metadata.json")
    assert entry["artifact_relative_path"] == "BPI/lstm.pt"
    assert entry["metadata_relative_path"] == "BPI/lstm.metadata.json"
    assert entry["model_evidence"]["production_selected_epoch_count"] == 12


def test_lstm_bundle_persistence_rejects_metadata_checksum_mismatch(tmp_path):
    symbol = "BPI"
    selection = load_selection_catalog()[symbol]
    symbol_directory = tmp_path / symbol
    symbol_directory.mkdir()
    artifact_path = symbol_directory / "lstm.pt"
    metadata_path = symbol_directory / "lstm.metadata.json"
    artifact_path.write_bytes(b"state-dict")
    metadata = {"artifact_sha256": "0" * 64}
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    production_fit = SimpleNamespace(
        fitted=SimpleNamespace(seed=42),
        epoch_selection=SimpleNamespace(selected_epoch_count=12),
    )

    def three_value_persist(**kwargs):
        return artifact_path, metadata_path, metadata

    with pytest.raises(ProductionBundleError, match="checksum differs"):
        _persist_lstm_manifest_entry(
            persist_artifact=three_value_persist,
            output_directory=symbol_directory,
            bundle_directory=tmp_path,
            symbol=symbol,
            model_version=ACCEPTANCE_BUNDLE_VERSION,
            selection=selection,
            production_fit=production_fit,
        )


@pytest.mark.parametrize("mutation", ["44", "46", "duplicate", "missing_company"])
def test_manifest_rejects_incomplete_extra_duplicate_or_missing_company(tmp_path, monkeypatch, mutation):
    manifest = _fake_bundle(tmp_path, monkeypatch)
    if mutation == "44":
        manifest["entries"].pop()
    elif mutation == "46":
        manifest["entries"].append(dict(manifest["entries"][-1], model_code="UNKNOWN"))
    elif mutation == "duplicate":
        manifest["entries"][-1] = dict(manifest["entries"][-2])
    else:
        manifest["symbols"].pop()
    with pytest.raises(ProductionBundleError):
        validate_manifest_shape(manifest)


def test_bundle_verifier_rejects_wrong_artifact_sha(tmp_path, monkeypatch):
    manifest = _fake_bundle(tmp_path, monkeypatch)
    manifest["entries"][0]["artifact_sha256"] = "0" * 64
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ProductionBundleError, match="checksum"):
        verify_bundle(tmp_path)


def test_bundle_verifier_rejects_path_traversal(tmp_path, monkeypatch):
    manifest = _fake_bundle(tmp_path, monkeypatch)
    manifest["entries"][0]["artifact_relative_path"] = "../../outside.joblib"
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ProductionBundleError):
        verify_bundle(tmp_path)


def test_bundle_verifier_rejects_symlink_escape(tmp_path, monkeypatch):
    manifest = _fake_bundle(tmp_path, monkeypatch)
    entry = manifest["entries"][0]
    artifact = tmp_path / entry["artifact_relative_path"]
    outside = tmp_path.parent / "outside-phase3b2-artifact"
    outside.write_bytes(artifact.read_bytes())
    artifact.unlink()
    artifact.symlink_to(outside)
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ProductionBundleError, match="escapes"):
        verify_bundle(tmp_path)


def test_build_atomically_finalizes_verified_staging(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    external = tmp_path / "external"
    final, result = build_atomically(
        repository_root=repository,
        output_root=external,
        bundle_version=ACCEPTANCE_BUNDLE_VERSION,
        builder=lambda staging: (staging / "complete").write_text("ok"),
        verifier=lambda staging: (staging / "complete").read_text(),
    )
    assert final == external / ACCEPTANCE_BUNDLE_VERSION
    assert (final / "complete").read_text() == "ok"
    assert result == "ok"
    assert not list(external.glob("*.staging-*"))


def test_build_atomically_failure_leaves_no_final_or_staging(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    external = tmp_path / "external"
    def fail(staging):
        (staging / "partial").write_text("partial")
        raise RuntimeError("injected failure")
    with pytest.raises(RuntimeError, match="injected"):
        build_atomically(
            repository_root=repository,
            output_root=external,
            bundle_version=ACCEPTANCE_BUNDLE_VERSION,
            builder=fail,
            verifier=lambda staging: None,
        )
    assert not (external / ACCEPTANCE_BUNDLE_VERSION).exists()
    assert not list(external.glob(".*.staging-*"))


def test_build_atomically_verifier_failure_leaves_no_final_or_staging(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    external = tmp_path / "external"

    def fail_verification(staging):
        assert (staging / "complete").read_text() == "ready"
        raise RuntimeError("injected verifier failure")

    with pytest.raises(RuntimeError, match="verifier failure"):
        build_atomically(
            repository_root=repository,
            output_root=external,
            bundle_version=ACCEPTANCE_BUNDLE_VERSION,
            builder=lambda staging: (staging / "complete").write_text("ready"),
            verifier=fail_verification,
        )
    assert not (external / ACCEPTANCE_BUNDLE_VERSION).exists()
    assert not list(external.glob(".*.staging-*"))


def test_validation_promotion_failure_removes_final_bundle_and_evidence(tmp_path, monkeypatch):
    repository = tmp_path / "repo"
    repository.mkdir()
    external = tmp_path / "external"
    staging_validation = external / ".bundle_validation.phase3b2.tmp"
    validation_path = external / "bundle_validation.json"

    def builder(staging):
        (staging / "manifest.json").write_text("{}", encoding="utf-8")
        staging_validation.write_text('{"results": []}\n', encoding="utf-8")

    def fail_after_creating_sidecar(source, destination, *, on_promoted):
        os.link(source, destination)
        on_promoted()
        raise RuntimeError("injected validation promotion failure")

    monkeypatch.setattr(training_bundle, "_promote_validation_evidence", fail_after_creating_sidecar)
    with pytest.raises(RuntimeError, match="validation promotion failure"):
        training_bundle._finalize_bundle_with_validation(
            repository_root=repository,
            output_root=external,
            bundle_version=ACCEPTANCE_BUNDLE_VERSION,
            builder=builder,
            verifier=lambda staging: {"verified": True},
            staging_validation=staging_validation,
            validation_path=validation_path,
            starting_counts=(0, 0),
            read_counts=lambda: (0, 0),
        )

    assert not (external / ACCEPTANCE_BUNDLE_VERSION).exists()
    assert not list(external.glob(".*.staging-*"))
    assert not staging_validation.exists()
    assert not validation_path.exists()


def test_validation_promotion_success_keeps_bundle_and_sidecar_sibling(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    external = tmp_path / "external"
    staging_validation = external / ".bundle_validation.phase3b2.tmp"
    validation_path = external / "bundle_validation.json"

    def builder(staging):
        (staging / "manifest.json").write_text("{}", encoding="utf-8")
        staging_validation.write_text('{"results": []}\n', encoding="utf-8")

    final, verification, counts = training_bundle._finalize_bundle_with_validation(
        repository_root=repository,
        output_root=external,
        bundle_version=ACCEPTANCE_BUNDLE_VERSION,
        builder=builder,
        verifier=lambda staging: {"verified": True},
        staging_validation=staging_validation,
        validation_path=validation_path,
        starting_counts=(0, 0),
        read_counts=lambda: (0, 0),
    )
    assert final == external / ACCEPTANCE_BUNDLE_VERSION
    assert (final / "manifest.json").is_file()
    assert validation_path.read_text(encoding="utf-8") == '{"results": []}\n'
    assert not staging_validation.exists()
    assert verification == {"verified": True}
    assert counts == (0, 0)


@pytest.mark.parametrize("changed_counts", [(1, 0), (0, 1)])
def test_database_row_delta_rejected_before_atomic_publication(tmp_path, monkeypatch, changed_counts):
    repository = tmp_path / "repo"
    repository.mkdir()
    external = tmp_path / "external"
    db = object()
    monkeypatch.setattr(training_bundle, "_database_row_counts", lambda session: changed_counts)

    def builder(staging):
        (staging / "partial").write_text("not publishable", encoding="utf-8")
        training_bundle._require_unchanged_database_rows(db, starting_counts=(0, 0))

    with pytest.raises(ProductionBundleError, match="changed forecast or ModelArtifact"):
        build_atomically(
            repository_root=repository,
            output_root=external,
            bundle_version=ACCEPTANCE_BUNDLE_VERSION,
            builder=builder,
            verifier=lambda staging: None,
        )
    assert not (external / ACCEPTANCE_BUNDLE_VERSION).exists()
    assert not list(external.glob(".*.staging-*"))


def test_build_atomically_refuses_existing_target_and_repo_paths(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    external = tmp_path / "external"
    existing = external / ACCEPTANCE_BUNDLE_VERSION
    existing.mkdir(parents=True)
    with pytest.raises(ProductionBundleError, match="already exists"):
        build_atomically(
            repository_root=repository,
            output_root=external,
            bundle_version=ACCEPTANCE_BUNDLE_VERSION,
            builder=lambda staging: pytest.fail("builder should not run"),
            verifier=lambda staging: None,
        )
    with pytest.raises(ProductionBundleError, match="outside"):
        build_atomically(
            repository_root=repository,
            output_root=repository / "artifacts",
            bundle_version=ACCEPTANCE_BUNDLE_VERSION,
            builder=lambda staging: pytest.fail("builder should not run"),
            verifier=lambda staging: None,
        )


def test_legacy_all_resolves_canonical_company_universe():
    from backend.app.forecasting.real.training.refit import resolve_symbols

    symbols = resolve_symbols("ALL")
    assert tuple(symbols) == tuple(get_all_configured_symbols())
    assert len(symbols) == len(set(symbols)) == 15
