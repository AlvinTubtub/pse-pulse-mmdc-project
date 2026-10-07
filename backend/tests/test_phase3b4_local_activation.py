"""Safety guards for the controlled Phase 3B.4 local validation driver."""

import argparse
import inspect
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.forecasting.real.artifacts.bundle import ACCEPTANCE_BUNDLE_VERSION
from backend.pipeline.forecasting.real_runner import build_arg_parser, run_real_pipeline
from scripts.phase3b4_local_validate import (
    MANIFEST_SHA256,
    INTERNAL_WORKER_ENV,
    Phase3B4Error,
    _run_worker,
    _child_environment,
    _local_sqlite_path,
    _require_execution_confirmations,
    _require_local_validation_target,
    _worker,
    build_parser,
)


def test_phase3b4_defaults_to_plan_only():
    args = build_parser().parse_args([])
    assert args.plan is False
    assert args.execute is False


def test_phase3b4_requires_all_explicit_confirmations():
    args = argparse.Namespace(
        confirm_bundle_version=ACCEPTANCE_BUNDLE_VERSION,
        confirm_manifest_sha=MANIFEST_SHA256,
        confirm_local_validation=True,
    )
    _require_execution_confirmations(args, environment="development")
    args.confirm_manifest_sha = "0" * 64
    with pytest.raises(Phase3B4Error, match="exact --confirm-manifest-sha"):
        _require_execution_confirmations(args, environment="development")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("confirm_bundle_version", "wrong", "exact --confirm-bundle-version"),
        ("confirm_manifest_sha", "0" * 64, "exact --confirm-manifest-sha"),
        ("confirm_local_validation", False, "--confirm-local-validation"),
    ],
)
def test_phase3b4_mutating_worker_confirmation_contract(field, value, message):
    args = argparse.Namespace(
        confirm_bundle_version=ACCEPTANCE_BUNDLE_VERSION,
        confirm_manifest_sha=MANIFEST_SHA256,
        confirm_local_validation=True,
    )
    setattr(args, field, value)
    with pytest.raises(Phase3B4Error, match=message):
        _require_execution_confirmations(args, environment="development")


def test_direct_worker_call_requires_internal_authorization(monkeypatch, tmp_path):
    monkeypatch.delenv(INTERNAL_WORKER_ENV, raising=False)
    args = argparse.Namespace(worker_mode="register", validation_db=tmp_path / "unused.db")
    with pytest.raises(Phase3B4Error, match="internal worker authorization"):
        _worker(args)


def test_phase3b4_refuses_production_execution():
    args = argparse.Namespace(
        confirm_bundle_version=ACCEPTANCE_BUNDLE_VERSION,
        confirm_manifest_sha=MANIFEST_SHA256,
        confirm_local_validation=True,
    )
    with pytest.raises(Phase3B4Error, match="ENVIRONMENT=production"):
        _require_execution_confirmations(args, environment="production")


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://user:secret@remote.example/db",
        "sqlite:///:memory:",
    ],
)
def test_phase3b4_rejects_remote_or_uncloneable_source(url):
    with pytest.raises(Phase3B4Error):
        _local_sqlite_path(url)


def test_phase3b4_requires_exact_external_local_validation_database(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    validation_db = tmp_path / "external" / "phase3b4_validation.db"
    validation_db.parent.mkdir()
    url = "sqlite:///" + str(validation_db)
    _require_local_validation_target(url, validation_db, repo=repo)
    with pytest.raises(Phase3B4Error, match="exact isolated"):
        _require_local_validation_target("sqlite:///" + str(tmp_path / "other.db"), validation_db, repo=repo)
    with pytest.raises(Phase3B4Error, match="outside the Git repository"):
        _require_local_validation_target("sqlite:///" + str(repo / "inside.db"), repo / "inside.db", repo=repo)


def test_process_scoped_switches_do_not_change_parent_environment(monkeypatch):
    monkeypatch.setenv("MODEL_ARTIFACT_ACTIVATION_ENABLED", "false")
    monkeypatch.setenv("REAL_MODELS_ENABLED", "false")
    child = _child_environment("sqlite:////tmp/phase3b4_validation.db", activation=True)
    assert child["MODEL_ARTIFACT_ACTIVATION_ENABLED"] == "true"
    assert child["REAL_MODELS_ENABLED"] == "false"
    assert __import__("os").environ["MODEL_ARTIFACT_ACTIVATION_ENABLED"] == "false"
    assert __import__("os").environ["REAL_MODELS_ENABLED"] == "false"


@pytest.mark.parametrize(
    ("phase", "activation", "inference"),
    [("register", False, False), ("activate", True, False), ("first-run", False, True), ("second-run", False, True)],
)
def test_run_worker_sets_internal_auth_and_mutating_confirmations_only_in_child(
    monkeypatch, tmp_path, phase, activation, inference,
):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stdout="PHASE3B4_WORKER_JSON:{}\n", stderr="")

    monkeypatch.setattr("scripts.phase3b4_local_validate.subprocess.run", fake_run)
    monkeypatch.delenv(INTERNAL_WORKER_ENV, raising=False)
    monkeypatch.setenv("MODEL_ARTIFACT_ACTIVATION_ENABLED", "false")
    monkeypatch.setenv("REAL_MODELS_ENABLED", "false")
    _run_worker(
        phase, tmp_path / "validation.db", bundle_root=tmp_path / "bundle",
        evaluation_receipt=tmp_path / "receipt.json", activation=activation, inference=inference,
    )

    command = captured["command"]
    child = captured["env"]
    assert child[INTERNAL_WORKER_ENV] == "1"
    assert "--confirm-bundle-version" in command
    assert ACCEPTANCE_BUNDLE_VERSION in command
    assert "--confirm-manifest-sha" in command
    assert MANIFEST_SHA256 in command
    assert "--confirm-local-validation" in command
    assert child["MODEL_ARTIFACT_ACTIVATION_ENABLED"] == ("true" if activation else "false")
    assert child["REAL_MODELS_ENABLED"] == ("true" if inference else "false")
    assert INTERNAL_WORKER_ENV not in os.environ
    assert os.environ["MODEL_ARTIFACT_ACTIVATION_ENABLED"] == "false"
    assert os.environ["REAL_MODELS_ENABLED"] == "false"


def test_real_runner_defaults_to_accepted_bundle_and_all_families():
    args = build_arg_parser().parse_args([])
    assert args.bundle_version == ACCEPTANCE_BUNDLE_VERSION
    assert args.models == "LAG_REGRESSION,ARIMA,LSTM"
    signature = inspect.signature(run_real_pipeline)
    assert signature.parameters["bundle_version"].default == ACCEPTANCE_BUNDLE_VERSION
    assert signature.parameters["models"].default == ("LAG_REGRESSION", "ARIMA", "LSTM")
