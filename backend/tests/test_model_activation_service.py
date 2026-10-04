"""Isolated DB tests for inactive candidate registration and explicit activation."""

from datetime import date
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.domain.company_universe import get_all_configured_symbols
from backend.app.forecasting.real.artifacts import bundle as bundle_module
from backend.app.forecasting.real.artifacts import runtime as runtime_module
from backend.app.models.company import Company
from backend.app.models.forecast import Forecast
from backend.app.models.model_artifact import ModelArtifact
from backend.app.models.model_metadata import ModelMetadata
from backend.app.models.pipeline_run import PipelineRun
from backend.app.models.sector import Sector
from backend.app.services import model_activation_service as activation

BUNDLE = "2026.10.01-authoritative-v1"
SHA = "4225e60044f000b16147e01f6ff165968523c1efd9647e57d9c7a6f5f5a27454"
FAMILIES = ("LAG_REGRESSION", "ARIMA", "LSTM")


@pytest.fixture
def candidate_env(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Sector(id=1, name="Property", code="PROP"))
    db.add_all([Company(symbol=symbol, name=symbol, sector_id=1, is_active=True) for symbol in get_all_configured_symbols()])
    db.add_all([ModelMetadata(name=code, code=code, version="0.1.0-stub", is_active=True) for code in FAMILIES])
    db.commit()
    root = tmp_path / "bundle"
    receipt_dir = tmp_path / "phase3b3" / BUNDLE
    receipt_dir.mkdir(parents=True)
    (receipt_dir / "phase3b3_evaluation.json").write_text(json.dumps({
        "decision": "ELIGIBLE_FOR_ACTIVATION", "bundle_version": BUNDLE,
        "manifest_sha256": SHA,
        "verification": {"bundle_version": BUNDLE, "artifact_count": 45, "safe_reload_count": 45},
        "boundary_replay_count": 45, "reproduction_match_count": 45, "current_shadow_count": 45,
        "database_row_deltas": {"Forecast": 0, "ModelArtifact": 0, "PipelineRun": 0},
        "activation_feature_enabled": False, "real_models_enabled": False,
        "activation_database_preflight": {"canonical_company_count": 15, "runtime_model_metadata_count": 3},
        "activation_plan_validation": "PASS", "frozen_bundle_unchanged_after_evaluation": True,
    }))
    entries = []
    for symbol in get_all_configured_symbols():
        directory = root / symbol
        directory.mkdir(parents=True)
        for family in FAMILIES:
            suffix, artifact_format = ("pt", "pytorch_state_dict") if family == "LSTM" else ("joblib", "joblib")
            artifact_path = f"{symbol}/{family.lower()}.{suffix}"
            metadata_path = f"{symbol}/{family.lower()}.metadata.json"
            metadata = {
                "symbol": symbol, "model_code": family, "model_version": BUNDLE,
                "artifact_format": artifact_format, "artifact_sha256": ("a" if family == "LAG_REGRESSION" else "b" if family == "ARIMA" else "c") * 64,
                "trained_through": "2026-10-01", "data_row_count": 1649,
                "hyperparameters": {"family": family},
                "source_repository": "https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git",
                "source_commit": "b8bf39f8e94729687c2e877dc164ea8a4f69e2b1",
                "historical_data_source_repository": "https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git",
                "historical_data_source_commit": "b8bf39f8e94729687c2e877dc164ea8a4f69e2b1",
            }
            (root / metadata_path).write_text(json.dumps(metadata))
            entries.append({
                "symbol": symbol, "model_code": family, "model_version": BUNDLE,
                "artifact_format": artifact_format, "artifact_relative_path": artifact_path,
                "artifact_sha256": metadata["artifact_sha256"], "metadata_relative_path": metadata_path,
                "metadata_sha256": "d" * 64, "trained_through": "2026-10-01", "data_row_count": 1649,
            })
    manifest = {"bundle_version": BUNDLE, "symbols": list(get_all_configured_symbols()), "model_families": list(FAMILIES), "entries": entries}
    monkeypatch.setattr(activation, "verify_bundle", lambda path: {"bundle_version": BUNDLE, "artifact_count": 45, "safe_reload_count": 45})
    monkeypatch.setattr(activation, "read_verified_manifest", lambda *a, **k: (manifest, SHA))
    from backend.app.config import get_settings
    get_settings.cache_clear()
    yield db, root, manifest
    get_settings.cache_clear()
    db.close()
    engine.dispose()


def test_registration_creates_45_inactive_rows_and_is_idempotent(candidate_env):
    db, root, _ = candidate_env
    assert activation.register_candidate_bundle(db, root) == 45
    assert db.query(ModelArtifact).count() == 45
    assert db.query(ModelArtifact).filter(ModelArtifact.is_active.is_(True)).count() == 0
    assert activation.register_candidate_bundle(db, root) == 0
    assert db.query(ModelArtifact).count() == 45


@pytest.mark.parametrize("field,value", [
    ("artifact_sha256", "f" * 64),
    ("artifact_path", "../escape.joblib"),
    ("artifact_format", "unknown"),
    ("trained_through", date(2025, 1, 1)),
    ("data_row_count", 1648),
    ("source_commit", "f" * 40),
    ("hyperparameters_json", '{"modified":true}'),
])
def test_registration_rejects_conflicting_existing_lineage(candidate_env, field, value):
    db, root, _ = candidate_env
    activation.register_candidate_bundle(db, root)
    row = db.query(ModelArtifact).first()
    setattr(row, field, value)
    db.commit()
    with pytest.raises(activation.ModelActivationError, match="conflicts|exactly 45"):
        activation.register_candidate_bundle(db, root)


@pytest.mark.parametrize("missing", ["company", "family"])
def test_registration_requires_complete_company_and_family_preflight(candidate_env, missing):
    db, root, _ = candidate_env
    if missing == "company":
        db.delete(db.query(Company).filter_by(symbol=get_all_configured_symbols()[0]).one())
    else:
        db.delete(db.query(ModelMetadata).filter_by(code="LSTM").one())
    db.commit()
    with pytest.raises(activation.ModelActivationError):
        activation.register_candidate_bundle(db, root)


def test_activation_feature_flag_and_confirmations_fail_closed(candidate_env, monkeypatch):
    db, root, _ = candidate_env
    activation.register_candidate_bundle(db, root)
    from backend.app.config import get_settings
    with pytest.raises(activation.ModelActivationError, match="false"):
        activation.activate_candidate_bundle(db, root, confirm_bundle_version=BUNDLE, confirm_manifest_sha256=SHA)
    monkeypatch.setenv("MODEL_ARTIFACT_ACTIVATION_ENABLED", "true")
    get_settings.cache_clear()
    with pytest.raises(activation.ModelActivationError, match="SHA-256"):
        activation.activate_candidate_bundle(db, root, confirm_bundle_version=BUNDLE, confirm_manifest_sha256="0" * 64)
    with pytest.raises(activation.ModelActivationError, match="version"):
        activation.activate_candidate_bundle(db, root, confirm_bundle_version="wrong", confirm_manifest_sha256=SHA)


def test_exact_activation_deactivates_prior_version_atomically(candidate_env, monkeypatch):
    db, root, _ = candidate_env
    companies = {r.symbol: r for r in db.query(Company).all()}
    models = {r.code: r for r in db.query(ModelMetadata).all()}
    for symbol in get_all_configured_symbols():
        for family in FAMILIES:
            db.add(ModelArtifact(
                id=f"old-{symbol}-{family}", company_id=companies[symbol].id,
                model_metadata_id=models[family].id, bundle_version="older-v0",
                artifact_format="joblib", artifact_path=f"{symbol}/old.joblib", artifact_sha256="e" * 64,
                trained_through=date(2025, 1, 1), data_row_count=1, hyperparameters_json="{}",
                source_repository="old", source_commit="f" * 40,
                historical_data_source_repository="old", historical_data_source_commit="f" * 40,
                is_active=True,
            ))
    db.commit()
    activation.register_candidate_bundle(db, root)
    from backend.app.config import get_settings
    monkeypatch.setenv("MODEL_ARTIFACT_ACTIVATION_ENABLED", "true")
    get_settings.cache_clear()
    counts_before = (db.query(Forecast).count(), db.query(PipelineRun).count())
    activation.activate_candidate_bundle(db, root, confirm_bundle_version=BUNDLE, confirm_manifest_sha256=SHA)
    assert db.query(ModelArtifact).filter_by(bundle_version=BUNDLE, is_active=True).count() == 45
    assert db.query(ModelArtifact).filter(ModelArtifact.bundle_version == "older-v0", ModelArtifact.is_active.is_(True)).count() == 0
    assert (db.query(Forecast).count(), db.query(PipelineRun).count()) == counts_before


def test_activation_failure_rolls_back_all_changes(candidate_env, monkeypatch):
    db, root, _ = candidate_env
    companies = {r.symbol: r for r in db.query(Company).all()}
    models = {r.code: r for r in db.query(ModelMetadata).all()}
    for symbol in get_all_configured_symbols():
        for family in FAMILIES:
            db.add(ModelArtifact(
                id=f"old-{symbol}-{family}", company_id=companies[symbol].id,
                model_metadata_id=models[family].id, bundle_version="older-v0",
                artifact_format="joblib", artifact_path=f"{symbol}/old.joblib", artifact_sha256="e" * 64,
                trained_through=date(2025, 1, 1), data_row_count=1, hyperparameters_json="{}",
                source_repository="old", source_commit="f" * 40,
                historical_data_source_repository="old", historical_data_source_commit="f" * 40,
                is_active=True,
            ))
    db.commit()
    activation.register_candidate_bundle(db, root)
    from backend.app.config import get_settings
    monkeypatch.setenv("MODEL_ARTIFACT_ACTIVATION_ENABLED", "true")
    get_settings.cache_clear()
    def fail_flush(*_args, **_kwargs):
        raise RuntimeError("injected activation failure")
    monkeypatch.setattr(db, "flush", fail_flush)
    with pytest.raises(RuntimeError, match="injected"):
        activation.activate_candidate_bundle(db, root, confirm_bundle_version=BUNDLE, confirm_manifest_sha256=SHA)
    monkeypatch.undo()
    assert db.query(ModelArtifact).filter_by(bundle_version=BUNDLE, is_active=True).count() == 0
    assert db.query(ModelArtifact).filter(ModelArtifact.bundle_version == "older-v0", ModelArtifact.is_active.is_(True)).count() == 45


@pytest.mark.parametrize("extra", [False, True])
def test_activation_rejects_incomplete_or_extra_candidate_rows(candidate_env, monkeypatch, extra):
    db, root, _ = candidate_env
    activation.register_candidate_bundle(db, root)
    if extra:
        model = ModelMetadata(name="Other", code="OTHER", version="v1", is_active=True)
        db.add(model)
        db.flush()
        company = db.query(Company).first()
        db.add(ModelArtifact(
            id="extra-row", company_id=company.id, model_metadata_id=model.id, bundle_version=BUNDLE,
            artifact_format="joblib", artifact_path="ALI/other.joblib", artifact_sha256="f" * 64,
            trained_through=date(2026, 10, 1), data_row_count=1649, hyperparameters_json="{}",
            source_repository="src", source_commit="a" * 40,
            historical_data_source_repository="src", historical_data_source_commit="a" * 40,
            is_active=False,
        ))
    else:
        db.delete(db.query(ModelArtifact).first())
    db.commit()
    from backend.app.config import get_settings
    monkeypatch.setenv("MODEL_ARTIFACT_ACTIVATION_ENABLED", "true")
    get_settings.cache_clear()
    with pytest.raises(activation.ModelActivationError, match="missing, extra"):
        activation.activate_candidate_bundle(db, root, confirm_bundle_version=BUNDLE, confirm_manifest_sha256=SHA)
