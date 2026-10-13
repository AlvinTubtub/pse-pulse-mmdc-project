"""Offline tests for production runtime and data-provenance guards."""

from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from types import SimpleNamespace

from backend.app.production_inputs import (
    ProductionInputError, validate_bundle_coverage, validate_forecast_outcomes,
    verify_calendar_manifest, verify_source_approval_index, verify_source_manifest,
)
from backend.app.runtime_policy import (
    validate_api_listener, validate_database_url, validate_forecast_coverage,
    validate_production_flags, verify_private_database_resolution,
)


class RuntimePolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ca = Path(self.tmp.name) / "root-ca.pem"
        self.ca.write_text("fixture only")
        self.host = "owner-verified.private.postgres.database.azure.com"
        self.url = (f"postgresql+psycopg://unit-test:REDACTED@{self.host}:5432/pse"
                    f"?sslmode=verify-full&sslrootcert={self.ca}")

    def tearDown(self):
        self.tmp.cleanup()

    def test_production_flags_fail_closed(self):
        common = dict(environment="production", debug=False, demo_mode=False,
                      auto_create_schema=False, activation_enabled=False, process_role="api",
                      real_models_enabled=False)
        validate_production_flags(**common)
        for update in ({"demo_mode": True}, {"debug": True}, {"auto_create_schema": True},
                       {"activation_enabled": True}, {"real_models_enabled": True}):
            values = dict(common, **update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_production_flags(**values)

    def test_private_postgres_hostname_and_verify_full_required(self):
        self.assertEqual(validate_database_url(self.url, self.host, str(self.ca)), self.host)
        invalid = ["sqlite:///prod.db", self.url.replace(self.host, "public.postgres.database.azure.com"),
                   self.url.replace("verify-full", "require"), self.url.replace(str(self.ca), "/tmp/no-ca.pem")]
        for url in invalid:
            with self.subTest(url=url.split("@")[0]), self.assertRaises(ValueError):
                validate_database_url(url, self.host, str(self.ca))

    def test_private_dns_passes_and_public_dns_fails(self):
        private = [(None, None, None, None, ("10.2.1.7", 5432))]
        public = [(None, None, None, None, ("203.0.113.9", 5432))]
        self.assertEqual(verify_private_database_resolution(self.host, lambda *a, **k: private), {"10.2.1.7"})
        with self.assertRaises(RuntimeError):
            verify_private_database_resolution(self.host, lambda *a, **k: public)

    def test_loopback_listener_and_exact_forecast_coverage(self):
        validate_api_listener("127.0.0.1", 8000)
        with self.assertRaises(ValueError):
            validate_api_listener("0.0.0.0", 8000)
        expected = {("ALI", "ARIMA"), ("BPI", "LSTM")}
        validate_forecast_coverage(expected, expected, 2)
        with self.assertRaises(ValueError):
            validate_forecast_coverage(expected, {("ALI", "ARIMA")}, 1)
        with self.assertRaises(ValueError):
            validate_forecast_coverage(expected, expected, 3)


class ProductionInputTests(unittest.TestCase):
    def _write(self, path: Path, value: dict) -> str:
        path.write_text(json.dumps(value, sort_keys=True))
        path.chmod(0o640)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_reviewed_calendar_excludes_weekends_and_holidays(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "calendar.json"
            payload = {
                "schema_version": 1, "timezone": "Asia/Manila",
                "source_url": "https://www.pse.com.ph/market/holidays", "source_sha256": "a" * 64,
                "reviewed_by": "offline-owner", "reviewed_at": "2026-10-01T10:00:00+08:00",
                "coverage_start": "2026-10-05", "coverage_end": "2026-10-10",
                "trading_sessions": ["2026-10-05", "2026-10-06", "2026-10-08", "2026-10-09"],
            }
            digest = self._write(path, payload)
            calendar = verify_calendar_manifest(path, digest, date(2026, 10, 7))
            self.assertFalse(calendar.is_session(date(2026, 10, 7)))
            self.assertTrue(calendar.is_session(date(2026, 10, 8)))
            self.assertEqual(calendar.next_session(date(2026, 10, 6)), date(2026, 10, 8))

    def test_unreviewed_calendar_bad_pin_and_weekend_entry_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "calendar.json"
            payload = {
                "schema_version": 1, "timezone": "Asia/Manila",
                "source_url": "https://www.pse.com.ph/market/holidays", "source_sha256": "b" * 64,
                "reviewed_by": "offline-owner", "reviewed_at": "2026-10-01T00:00:00Z",
                "coverage_start": "2026-10-09", "coverage_end": "2026-10-11",
                "trading_sessions": ["2026-10-10"],
            }
            digest = self._write(path, payload)
            with self.assertRaisesRegex(ProductionInputError, "weekend"):
                verify_calendar_manifest(path, digest, date(2026, 10, 10))
            with self.assertRaises(ProductionInputError):
                verify_calendar_manifest(path, "0" * 64, date(2026, 10, 10))

    def test_source_manifest_provenance_hash_and_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "2026-10-05.txt"
            source.write_text("synthetic fixture only for parser-policy tests")
            payload = {
                "schema_version": 1, "source_type": "PSE_DQR",
                "source_url": "https://edge.pse.com.ph/example.pdf", "trade_date": "2026-10-05",
                "retrieved_at": "2026-10-05T18:30:00+08:00", "reviewed_by": "offline-owner",
                "file_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
            sidecar = root / "source.manifest.json"
            digest = self._write(sidecar, payload)
            result, source_sha, manifest_sha = verify_source_manifest(source, sidecar, digest, date(2026, 10, 5))
            self.assertEqual(source_sha, payload["file_sha256"])
            self.assertEqual(manifest_sha, digest)
            self.assertEqual(result["reviewed_by"], "offline-owner")
            payload["trade_date"] = "2026-10-06"
            bad_pin = self._write(sidecar, payload)
            with self.assertRaisesRegex(ProductionInputError, "trade date"):
                verify_source_manifest(source, sidecar, bad_pin, date(2026, 10, 5))

    def test_missing_source_and_unofficial_source_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ProductionInputError):
                verify_source_manifest(root / "missing.pdf", root / "missing.json", "f" * 64, date(2026, 10, 5))
            source = root / "fixture.txt"
            source.write_text("synthetic fixture only")
            payload = {
                "schema_version": 1, "source_type": "PSE_DQR", "source_url": "https://example.invalid/data",
                "trade_date": "2026-10-05", "retrieved_at": "2026-10-05T18:00:00+08:00",
                "reviewed_by": "offline-owner", "file_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
            sidecar = root / "source.json"
            digest = self._write(sidecar, payload)
            with self.assertRaisesRegex(ProductionInputError, "official PSE"):
                verify_source_manifest(source, sidecar, digest, date(2026, 10, 5))

    def test_source_approval_index_pins_multiple_sessions_and_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            digest = "c" * 64
            path = root / "approved.json"
            index = {
                "schema_version": 1,
                "approved_sources": {
                    "2026-10-05": {"manifest_file": "2026-10-05.pdf.manifest.json", "manifest_sha256": digest},
                    "2026-10-06": {"manifest_file": "2026-10-06.txt.manifest.json", "manifest_sha256": "d" * 64},
                },
            }
            index_sha = self._write(path, index)
            manifest_path, found_sha = verify_source_approval_index(path, index_sha, date(2026, 10, 6), root)
            self.assertEqual(manifest_path, root.resolve() / "2026-10-06.txt.manifest.json")
            self.assertEqual(found_sha, "d" * 64)
            index["approved_sources"]["2026-10-06"]["manifest_file"] = "../outside.json"
            bad_pin = self._write(path, index)
            with self.assertRaises(ProductionInputError):
                verify_source_approval_index(path, bad_pin, date(2026, 10, 6), root)

    def test_bundle_and_forecast_coverage_reject_missing_or_duplicate_models(self):
        symbols = {"ALI", "BPI"}
        models = ("ARIMA", "LSTM")
        entries = [{"symbol": symbol, "model_code": model} for symbol in symbols for model in models]
        expected = validate_bundle_coverage(entries, symbols, models)
        self.assertEqual(len(expected), 4)
        with self.assertRaises(ProductionInputError):
            validate_bundle_coverage(entries[:-1], symbols, models)
        outcomes = [SimpleNamespace(symbol=symbol, model_code=model, origin_date=date(2026, 10, 5),
                                    target_date=date(2026, 10, 6), status="PERSISTED", predicted_close=1.25)
                    for symbol in symbols for model in models]
        validate_forecast_outcomes(outcomes, expected, date(2026, 10, 5), date(2026, 10, 6))
        with self.assertRaises(ProductionInputError):
            validate_forecast_outcomes(outcomes[:-1], expected, date(2026, 10, 5), date(2026, 10, 6))
        stale = list(outcomes)
        stale[0] = SimpleNamespace(**{**vars(stale[0]), "target_date": date(2026, 10, 8)})
        with self.assertRaises(ProductionInputError):
            validate_forecast_outcomes(stale, expected, date(2026, 10, 5), date(2026, 10, 6))


if __name__ == "__main__":
    unittest.main()
