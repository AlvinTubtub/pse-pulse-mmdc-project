"""Offline policy and manifest tests; never invoke Azure or system services."""

from __future__ import annotations

import importlib.util
import json
import os
import ast
import stat
from types import SimpleNamespace
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
RELEASE_PATH = ROOT / "infrastructure/scripts/release_manager.py"
spec = importlib.util.spec_from_file_location("release_manager", RELEASE_PATH)
release_manager = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(release_manager)
CONFIG_VALIDATOR_PATH = ROOT / "infrastructure/scripts/validate-runtime-config.py"
config_spec = importlib.util.spec_from_file_location("validate_runtime_config", CONFIG_VALIDATOR_PATH)
validate_runtime_config = importlib.util.module_from_spec(config_spec)
assert config_spec.loader is not None
config_spec.loader.exec_module(validate_runtime_config)

COMMIT_A = "1" * 40
COMMIT_B = "2" * 40


class RuntimeScriptSafetyTests(unittest.TestCase):
    def test_bootstrap_is_idempotent_and_uses_approved_vm_basics(self):
        script = (ROOT / "infrastructure/scripts/setup-vm.sh").read_text()
        self.assertIn('"${VERSION_ID:-}")" == 24.04', script)
        self.assertIn("mem_kib >= 3 * 1024 * 1024", script)
        self.assertIn("if ! getent group psepulse", script)
        self.assertIn("if ! id -u psepulse", script)
        for name in ("psepulse-api", "psepulse-eod", "psepulse-migration", "psepulse-bootstrap"):
            self.assertIn(name, script)
        self.assertIn("/var/lib/pse-pulse/bootstrap-source", script)
        self.assertIn("apt-get install -y --no-install-recommends", script)
        self.assertNotIn("apt-get upgrade", script)
        self.assertNotIn("ufw", script.lower())
        self.assertNotIn("nodejs", script.lower())
        self.assertIn("disable --now nginx", script)

    def test_bootstrap_and_runtime_scripts_never_open_ssh_or_http(self):
        bootstrap = (ROOT / "infrastructure/scripts/setup-vm.sh").read_text()
        nginx = (ROOT / "infrastructure/nginx/pse-pulse.conf").read_text()
        self.assertNotRegex(bootstrap, r"(?im)^\s*(?:ufw|iptables|nft)\s+.*(?:22|80)")
        self.assertNotRegex(nginx, r"(?im)^\s*listen\s+80\b")
        self.assertNotRegex(nginx, r"(?im)^\s*listen\s+[^;]*:80\b")

    def test_no_runtime_script_creates_azure_resources(self):
        forbidden = ("az group create", "az vm create", "az deployment", "az storage account create", "az provider register")
        for path in (ROOT / "infrastructure/scripts").glob("*"):
            if path.is_file():
                contents = path.read_text(errors="ignore").lower()
                for command in forbidden:
                    self.assertNotIn(command, contents, f"{path.name} contains {command}")

    def test_api_is_loopback_only_and_no_stale_memory_cap(self):
        unit = (ROOT / "infrastructure/systemd/pse-pulse-api.service").read_text()
        self.assertIn("--host 127.0.0.1 --port 8000 --workers 1", unit)
        self.assertIn("backend/.venv-api/bin/uvicorn", unit)
        self.assertNotRegex(unit, r"(?im)^Memory(?:Max|High)=")
        self.assertNotIn("B2ats_v2", unit)

    def test_eod_and_model_installer_use_inference_environment(self):
        unit = (ROOT / "infrastructure/systemd/pse-pulse-eod.service").read_text()
        runner = (ROOT / "infrastructure/scripts/run-pipeline.sh").read_text()
        installer = (ROOT / "infrastructure/scripts/install-model-bundle.sh").read_text()
        self.assertIn("backend/.venv-inference/bin/python", unit)
        self.assertIn("backend/.venv-inference/bin/python", runner)
        self.assertIn("backend/.venv-inference/bin/python", installer)

    def test_api_eod_and_migration_database_credentials_are_separated(self):
        api_unit = (ROOT / "infrastructure/systemd/pse-pulse-api.service").read_text()
        eod_unit = (ROOT / "infrastructure/systemd/pse-pulse-eod.service").read_text()
        migration_unit = (ROOT / "infrastructure/systemd/pse-pulse-migration.service").read_text()
        bootstrap_unit = (ROOT / "infrastructure/systemd/pse-pulse-bootstrap.service").read_text()
        api_env = (ROOT / "infrastructure/config/api.env.example").read_text()
        eod_env = (ROOT / "infrastructure/config/eod.env.example").read_text()
        migration_env = (ROOT / "infrastructure/config/migration.env.example").read_text()
        bootstrap_env = (ROOT / "infrastructure/config/bootstrap.env.example").read_text()
        grants = (ROOT / "infrastructure/postgresql/production-role-privileges.sql.example").read_text()

        self.assertIn("User=psepulse-api", api_unit)
        self.assertIn("EnvironmentFile=/etc/pse-pulse/api.env", api_unit)
        self.assertIn("User=psepulse-eod", eod_unit)
        self.assertIn("EnvironmentFile=/etc/pse-pulse/eod.env", eod_unit)
        self.assertNotIn("api.env", eod_unit)
        self.assertIn("User=psepulse-migration", migration_unit)
        self.assertIn("EnvironmentFile=/etc/pse-pulse/migration.env", migration_unit)
        self.assertNotIn("api.env", migration_unit)
        self.assertIn("User=psepulse-bootstrap", bootstrap_unit)
        self.assertIn("EnvironmentFile=/etc/pse-pulse/bootstrap.env", bootstrap_unit)
        self.assertIn("production_bootstrap", bootstrap_unit)
        self.assertNotIn("WantedBy=", bootstrap_unit)
        self.assertNotIn("api.env", bootstrap_unit)
        self.assertIn("psepulse_api:", api_env)
        self.assertNotIn("psepulse_migrator", api_env)
        self.assertIn("psepulse_eod:", eod_env)
        self.assertNotIn("psepulse_migrator", eod_env)
        self.assertIn("psepulse_migrator:", migration_env)
        self.assertIn("psepulse_bootstrap:", bootstrap_env)
        self.assertIn("PROCESS_ROLE=production-bootstrap", bootstrap_env)
        for env in (api_env, eod_env, migration_env, bootstrap_env):
            self.assertIn("root:root mode 0600", env)
        self.assertIn('GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"api_role"', grants)
        self.assertIn("GRANT INSERT, UPDATE ON TABLE", grants)
        self.assertIn("GRANT INSERT ON TABLE", grants)
        self.assertIn("public.forecasts", grants)
        self.assertNotRegex(grants, r"(?s)GRANT INSERT, UPDATE ON TABLE[^;]*public\.forecasts")
        for sequence in (
            "public.daily_prices_id_seq",
            "public.market_data_imports_id_seq",
            "public.forecasts_id_seq",
            "public.pipeline_runs_id_seq",
            "public.production_sessions_id_seq",
        ):
            self.assertIn(sequence, grants)
        self.assertIn("public.production_sessions", grants)
        self.assertIn('GRANT SELECT ON TABLE\n  public.sectors,\n  public.companies,\n  public.daily_prices\nTO :"bootstrap_role"', grants)
        self.assertIn('GRANT INSERT ON TABLE public.market_data_imports TO :"bootstrap_role"', grants)
        self.assertNotRegex(grants, r'(?s)GRANT .*?public\.forecasts[^;]*:"bootstrap_role"')
        self.assertNotRegex(grants, r'(?s)GRANT CREATE ON SCHEMA[^;]*:"bootstrap_role"')
        self.assertIn("public.sectors_id_seq", grants)
        self.assertIn("public.companies_id_seq", grants)
        self.assertNotRegex(grants, r"(?im)^\s*CREATE\s+ROLE\b")

    def test_production_dependency_installer_requires_hash_complete_locks(self):
        installer = (ROOT / "infrastructure/scripts/stage-backend-release.sh").read_text()
        self.assertIn("requirements-production-api.lock", installer)
        self.assertIn("requirements-production-inference.lock", installer)
        self.assertIn("--require-hashes", installer)
        self.assertIn("refusing range-based installation", installer)
        self.assertIn("--index-url https://pypi.org/simple", installer)
        self.assertNotIn("--no-extra-index-url", installer)
        self.assertIn("PIP_CONFIG_FILE=/dev/null", installer)
        self.assertIn("-u PIP_INDEX_URL -u PIP_EXTRA_INDEX_URL -u PIP_FIND_LINKS", installer)
        self.assertIn("-u PIP_TRUSTED_HOST -u PIP_NO_INDEX", installer)
        self.assertIn("Refusing non-index package source", installer)

    def test_backend_release_archive_contains_activation_dependency_closure(self):
        script = (ROOT / "infrastructure/scripts/build-backend-release.sh").read_text()
        self.assertIn('git -C "$ROOT" archive "$COMMIT_SHA" "${RELEASE_PATHS[@]}"', script)
        block = script.split("RELEASE_PATHS=(", 1)[1].split(")", 1)[0]
        selected = {line.strip() for line in block.splitlines() if line.strip()}
        required = {
            "backend",
            "scripts/phase3b2_verify_bundle.py",
            "infrastructure/config",
            "infrastructure/nginx",
            "infrastructure/systemd",
            "infrastructure/scripts/activate-backend-release.sh",
            "infrastructure/scripts/install-model-bundle.sh",
            "infrastructure/scripts/release_manager.py",
            "infrastructure/scripts/renew-ip-certificate.sh",
            "infrastructure/scripts/run-pipeline.sh",
            "infrastructure/scripts/setup-vm.sh",
            "infrastructure/scripts/stage-backend-release.sh",
            "infrastructure/scripts/validate-runtime-config.py",
        }
        self.assertTrue(required.issubset(selected), f"Release archive omits: {sorted(required - selected)}")
        for relative in required:
            self.assertTrue((ROOT / relative).exists(), f"Required release dependency is missing: {relative}")
        activation = (ROOT / "infrastructure/scripts/activate-backend-release.sh").read_text()
        self.assertIn("infrastructure/scripts/validate-runtime-config.py", activation)
        self.assertIn("infrastructure/scripts/release_manager.py", activation)

    def test_api_environment_permissions_are_checked_by_root_before_activation(self):
        directory = SimpleNamespace(st_mode=stat.S_IFDIR | 0o750, st_uid=0, st_gid=0)
        env_file = SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=0, st_gid=0)
        validate_runtime_config.validate_api_env_metadata(directory, env_file, 0)
        for bad_directory, bad_file, euid in (
            (SimpleNamespace(st_mode=stat.S_IFDIR | 0o750, st_uid=0, st_gid=0), env_file, 1000),
            (SimpleNamespace(st_mode=stat.S_IFDIR | 0o750, st_uid=0, st_gid=1), env_file, 0),
            (SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0, st_gid=0), env_file, 0),
            (directory, SimpleNamespace(st_mode=stat.S_IFREG | 0o640, st_uid=0, st_gid=0), 0),
            (directory, SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=1000, st_gid=0), 0),
            (directory, SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_uid=0, st_gid=0), 0),
        ):
            with self.assertRaises(RuntimeError):
                validate_runtime_config.validate_api_env_metadata(bad_directory, bad_file, euid)

        activation = (ROOT / "infrastructure/scripts/activate-backend-release.sh").read_text()
        unit = (ROOT / "infrastructure/systemd/pse-pulse-api.service").read_text()
        preflight = (ROOT / "backend/app/production_preflight.py").read_text()
        template = (ROOT / "infrastructure/config/api.env.example").read_text()
        self.assertLess(activation.index("validate-runtime-config.py"), activation.index("release_manager.py"))
        self.assertIn("install -d -o root -g root -m 0750 /etc/pse-pulse", (ROOT / "infrastructure/scripts/setup-vm.sh").read_text())
        self.assertIn("User=psepulse-api", unit)
        self.assertIn("EnvironmentFile=/etc/pse-pulse/api.env", unit)
        self.assertIn("ExecStartPre=", unit)
        self.assertIn("root:root mode 0600", template)
        self.assertIn("Production API database configuration is incomplete", preflight)
        self.assertNotIn("/etc/pse-pulse/api.env", preflight)

    def test_production_runner_serializes_retries_by_trading_date(self):
        runner = (ROOT / "backend/pipeline/production_runner.py").read_text()
        session_model = (ROOT / "backend/app/models/production_session.py").read_text()
        session_migration = (ROOT / "backend/alembic/versions/0007_production_session_ledger.py").read_text()
        self.assertIn("pg_advisory_xact_lock", runner)
        self.assertIn(".with_for_update()", runner)
        self.assertIn("already running", runner)
        self.assertIn("trade_date = Column(Date, unique=True", session_model)
        self.assertIn("sa.UniqueConstraint(\"trade_date\")", session_migration)
        # Forecast uniqueness includes run ID, so serialization in the production
        # runner is required to prevent concurrent runs from competing by target.
        forecast_model = (ROOT / "backend/app/models/forecast.py").read_text()
        self.assertIn('"pipeline_run_id",', forecast_model)

    def test_failed_production_session_requires_an_explicit_exact_date_retry(self):
        runner = (ROOT / "backend/pipeline/production_runner.py").read_text()
        self.assertIn('"--retry-failed", action="store_true"', runner)
        self.assertIn("args.retry_failed and (args.scheduled or args.reconcile_pending)", runner)
        self.assertIn('_validate_retry_authorization(existing, retry_failed, source_file, source_manifest)', runner)
        self.assertIn('existing.status == "FAILED" and not retry_failed', runner)
        self.assertIn("not source_file.is_file() or not source_manifest.is_file()", runner)
        self.assertIn("_lock_finalization_claim(db, trade_date, run.id)", runner)
        self.assertIn(".populate_existing()", runner)

    def test_ci_adds_isolated_postgresql_16_migration_and_concurrency_validation(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        postgres_test = (ROOT / "backend/tests/test_production_postgres.py").read_text()
        self.assertIn("image: postgres:16", workflow)
        self.assertIn("pse_phase4d1_test", workflow)
        self.assertIn("ci-only-phase4d1-password", workflow)
        self.assertIn("alembic.ini upgrade head", workflow)
        self.assertIn("test_production_postgres.py", workflow)
        self.assertIn("test_concurrent_finalization_has_one_winner", postgres_test)
        self.assertIn("test_competing_explicit_retries_rollback_provisional_data_and_fail_atomically", postgres_test)
        self.assertIn("PostgreSQL tests only permit", postgres_test)
        self.assertIn("runner._lock_production_session_date", postgres_test)
        self.assertNotIn("secrets.", workflow)
        self.assertNotIn("azure.com", workflow.lower())

    def test_production_settings_are_fields_on_settings_class(self):
        tree = ast.parse((ROOT / "backend/app/config.py").read_text())
        settings = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Settings")
        declared = {
            target.id
            for node in settings.body if isinstance(node, ast.AnnAssign)
            for target in [node.target] if isinstance(target, ast.Name)
        }
        self.assertTrue({"REAL_MODELS_ENABLED", "MODEL_ARTIFACT_ACTIVATION_ENABLED", "MODEL_ARTIFACTS_DIR"}.issubset(declared))

    def test_nginx_https_only_routes_and_hides_docs(self):
        config = (ROOT / "infrastructure/nginx/pse-pulse.conf").read_text()
        self.assertIn("listen 443 ssl", config)
        self.assertIn("server 127.0.0.1:8000", config)
        self.assertIn("return 404", config)
        self.assertIn("ssl_certificate_key", config)
        self.assertIn("/etc/pse-pulse/tls/current/fullchain.pem", config)
        self.assertIn("try_files $uri.html $uri $uri/ =404", config)
        self.assertNotRegex(config, r"(?im)^\s*listen\s+80\b")
        self.assertIn("docs|redoc|openapi", config)

    def test_renewal_is_gated_staging_only_by_default_and_fails_closed(self):
        script = (ROOT / "infrastructure/scripts/renew-ip-certificate.sh").read_text()
        template = (ROOT / "infrastructure/config/acme.env.example").read_text()
        self.assertIn("ACME_ALLOW_PRODUCTION=false", template)
        self.assertIn("LEGO_VERSION=REPLACE_AFTER_REVIEWED_BUILD", template)
        self.assertIn("LEGO_SHA256=REPLACE_AFTER_REVIEWED_BUILD", template)
        self.assertIn("acme-staging-v02.api.letsencrypt.org", template)
        self.assertIn("staging-v02.api.letsencrypt.org", script)
        self.assertIn("stat -c '%u'", script)
        self.assertIn("sha256sum \"$LEGO_BIN\"", script)
        self.assertIn("certificate_switched=true", script)
        self.assertIn("mv -Tf", script)
        self.assertIn("--tls --server", script)
        self.assertIn("--renew-days 3", script)
        self.assertIn("--cert.name", script)
        self.assertIn("actual_lego_version", script)
        self.assertNotIn("--disable-cn", script)
        self.assertNotIn("renew --days", script)
        self.assertIn("--profile shortlived", script)
        self.assertIn('"$LEGO_BIN" run --path "$LEGO_PATH"', script)
        self.assertNotIn('"$LEGO_BIN" --path "$LEGO_PATH" run', script)
        self.assertIn("-checkip", script)
        self.assertIn("nginx -t", script)
        self.assertIn('if [[ "$was_active" == true ]]; then\n  systemctl start nginx.service', script)
        self.assertLess(script.rindex("nginx -t"), script.rindex("systemctl start nginx.service"))
        self.assertNotIn("http-01", script.lower())

    def test_release_activation_scripts_do_not_restart_services_or_use_azure(self):
        for name in ("deploy-static.sh", "activate-backend-release.sh", "build-static.sh"):
            contents = (ROOT / "infrastructure/scripts" / name).read_text()
            self.assertNotIn("az ", contents)
        self.assertNotIn("systemctl restart", (ROOT / "infrastructure/scripts/deploy-static.sh").read_text())
        self.assertIn("NEXT_PUBLIC_DEMO_MODE=false", (ROOT / "infrastructure/scripts/build-static.sh").read_text())
        self.assertIn("npm run typecheck", (ROOT / "infrastructure/scripts/build-static.sh").read_text())

    def test_runtime_units_are_disabled_and_have_local_failure_reporting(self):
        eod = (ROOT / "infrastructure/systemd/pse-pulse-eod.service").read_text()
        timer = (ROOT / "infrastructure/systemd/pse-pulse-eod.timer").read_text()
        tls_timer = (ROOT / "infrastructure/systemd/pse-pulse-cert-renew.timer").read_text()
        migration = (ROOT / "infrastructure/systemd/pse-pulse-migration.service").read_text()
        self.assertIn("OnFailure=pse-pulse-failure-alert", eod)
        self.assertIn("--scheduled --reconcile-pending", eod)
        self.assertNotIn("WantedBy=timers.target", eod)
        self.assertIn("OnCalendar=Mon..Fri *-*-* 10:00:00 UTC", timer)
        self.assertIn("disabled by default", tls_timer)
        self.assertIn("upgrade head", migration)
        self.assertNotIn("WantedBy=", migration)
        journal = (ROOT / "infrastructure/config/90-pse-pulse-journald.conf").read_text()
        self.assertIn("SystemMaxUse=256M", journal)
        self.assertIn("MaxRetentionSec=14day", journal)

    def test_alembic_graph_has_one_linear_current_head(self):
        revisions = {}
        for path in (ROOT / "backend/alembic/versions").glob("*.py"):
            tree = ast.parse(path.read_text())
            values = {}
            for node in tree.body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    if node.targets[0].id in {"revision", "down_revision"}:
                        try:
                            values[node.targets[0].id] = ast.literal_eval(node.value)
                        except (ValueError, TypeError):
                            pass
            if values.get("revision"):
                revisions[values["revision"]] = values.get("down_revision")
        parents = {parent for parent in revisions.values() if parent is not None}
        heads = set(revisions) - parents
        self.assertEqual(heads, {"0008_production_session_lineage"})
        self.assertEqual(revisions["0008_production_session_lineage"], "0007_production_session_ledger")
        self.assertEqual(revisions["0007_production_session_ledger"], "0006_model_artifacts_inactive_by_default")


class ReleaseManifestTests(unittest.TestCase):
    def make_frontend(self, root: Path, commit: str = COMMIT_A, *, demo_mode: bool = False):
        (root / "index.html").write_text("<html><body>production shell</body></html>")
        (root / "_next/static").mkdir(parents=True)
        (root / "_next/static/app.js").write_text("(()=>console.log('runtime'))()")
        manifest = release_manager.create_manifest(root, commit, "frontend", demo_mode)
        return manifest

    def test_valid_manifest_and_complete_static_export_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_frontend(root)
            release_manager.verify_release(root, expected_commit=COMMIT_A, expected_type="frontend")

    def test_missing_release_and_incorrect_sha_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(release_manager.ReleaseError):
                release_manager.verify_release(root / "missing", expected_commit=COMMIT_A, expected_type="frontend")
            self.make_frontend(root)
            with self.assertRaises(release_manager.ReleaseError):
                release_manager.verify_release(root, expected_commit=COMMIT_B, expected_type="frontend")

    def test_tampered_release_fails_hash_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_frontend(root)
            (root / "index.html").write_text("modified")
            with self.assertRaisesRegex(release_manager.ReleaseError, "hash mismatch"):
                release_manager.verify_release(root, expected_commit=COMMIT_A, expected_type="frontend")

    def test_incomplete_static_export_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text("index")
            release_manager.create_manifest(root, COMMIT_A, "frontend", False)
            with self.assertRaisesRegex(release_manager.ReleaseError, "Next.js static assets"):
                release_manager.verify_release(root, expected_commit=COMMIT_A, expected_type="frontend")

    def test_demo_mode_and_fixture_payloads_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(release_manager.ReleaseError):
                release_manager.create_manifest(root, COMMIT_A, "frontend", True)
            self.make_frontend(root)
            (root / "_next/static/app.js").write_text("DEMO DATA: Architectural stub projections")
            release_manager.create_manifest(root, COMMIT_A, "frontend", False)
            with self.assertRaisesRegex(release_manager.ReleaseError, "demo fixture"):
                release_manager.verify_release(root, expected_commit=COMMIT_A, expected_type="frontend")

    def test_invalid_file_permissions_and_symlinks_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_frontend(root)
            asset = root / "_next/static/app.js"
            asset.chmod(0o666)
            with self.assertRaisesRegex(release_manager.ReleaseError, "writable"):
                release_manager.verify_release(root, expected_commit=COMMIT_A, expected_type="frontend")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_frontend(root)
            (root / "linked.js").symlink_to(root / "index.html")
            with self.assertRaisesRegex(release_manager.ReleaseError, "symbolic links"):
                release_manager.verify_release(root, expected_commit=COMMIT_A, expected_type="frontend")

    def test_invalid_release_does_not_replace_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            releases = root / "releases"
            old = releases / COMMIT_A
            old.mkdir(parents=True)
            self.make_frontend(old)
            current = root / "current"
            current.symlink_to(old)
            bad = releases / COMMIT_B
            bad.mkdir()
            (bad / "index.html").write_text("bad")
            with patch.object(release_manager, "_verify_target_ownership"):
                with self.assertRaises(release_manager.ReleaseError):
                    release_manager.activate_existing(root, COMMIT_B, "frontend")
            self.assertEqual(current.resolve(), old.resolve())

    def test_activation_and_rollback_switch_only_verified_releases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            releases = root / "releases"
            releases.mkdir()
            for sha in (COMMIT_A, COMMIT_B):
                directory = releases / sha
                directory.mkdir()
                self.make_frontend(directory, sha)
            with patch.object(release_manager, "_verify_target_ownership"):
                release_manager.activate_existing(root, COMMIT_A, "frontend")
                release_manager.activate_existing(root, COMMIT_B, "frontend")
                self.assertEqual((root / "current").resolve().name, COMMIT_B)
                release_manager.rollback(root, "frontend")
            self.assertEqual((root / "current").resolve().name, COMMIT_A)

    def test_generated_backend_environments_are_excluded_but_permission_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "backend").mkdir()
            (root / "backend/app.py").write_text("production source")
            release_manager.create_manifest(root, COMMIT_A, "backend", False)
            env_bin = root / "backend/.venv-api/bin"
            env_bin.mkdir(parents=True)
            interpreter = env_bin / "python"
            interpreter.write_text("generated runtime")
            interpreter.chmod(0o750)
            release_manager.verify_release(root, expected_commit=COMMIT_A, expected_type="backend")
            interpreter.chmod(0o770)
            with self.assertRaisesRegex(release_manager.ReleaseError, "writable group or other"):
                release_manager.verify_release(root, expected_commit=COMMIT_A, expected_type="backend")


if __name__ == "__main__":
    unittest.main()
