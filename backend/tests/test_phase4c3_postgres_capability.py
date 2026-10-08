import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "azure_phase4c3_deployment_preflight.sh"
START = "<<'POSTGRES_CAPABILITY_PARSER'\n"
END = "\nPOSTGRES_CAPABILITY_PARSER\n"


def parser_source() -> str:
    source = SCRIPT.read_text(encoding="utf-8")
    start = source.index(START) + len(START)
    end = source.index(END, start)
    return source[start:end]


def capability_fixture(
    *,
    tier_status="Available",
    sku_status="Available",
    version_status="Available",
    restricted="Disabled",
    location_status="Available",
    region=None,
):
    record = {
        "name": "FlexibleServerCapabilities",
        "status": location_status,
        "restricted": restricted,
        "supportedServerEditions": [
            {
                "name": "Burstable",
                "status": tier_status,
                "supportedServerSkus": [
                    {
                        "name": "Standard_B1ms",
                        "status": sku_status,
                        "vCores": 1,
                        "supportedMemoryPerVcoreMb": 2048,
                        "supportedIops": 640,
                        "supportedZones": ["1", "2", "3"],
                        "supportedHaMode": ["SameZone", "ZoneRedundant"],
                    }
                ],
            }
        ],
        "supportedServerVersions": [{"name": "16", "status": version_status}],
    }
    if region is not None:
        record["location"] = region
    return [record]


def classify(document):
    with tempfile.TemporaryDirectory(prefix="phase4c3-postgres-test-") as temp_dir:
        evidence = Path(temp_dir) / "capabilities.json"
        evidence.write_text(json.dumps(document), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-c", parser_source(), str(evidence), "eastasia"],
            check=True,
            capture_output=True,
            text=True,
        )
    return json.loads(result.stdout)


class PostgreSQLCapabilityClassificationTests(unittest.TestCase):
    def test_exact_available_candidate_passes(self):
        result = classify(capability_fixture())
        self.assertEqual(result["classification"], "AVAILABLE")
        self.assertEqual(result["targetRegion"], "eastasia")

    def test_null_burstable_status_is_indeterminate(self):
        result = classify(capability_fixture(tier_status=None))
        self.assertEqual(result["classification"], "INDETERMINATE")
        self.assertEqual(result["burstable"]["status"]["state"], "NULL")

    def test_null_b1ms_status_is_indeterminate(self):
        result = classify(capability_fixture(sku_status=None))
        self.assertEqual(result["classification"], "INDETERMINATE")
        self.assertEqual(result["standardB1ms"]["status"]["state"], "NULL")

    def test_null_postgres_16_status_is_indeterminate(self):
        result = classify(capability_fixture(version_status=None))
        self.assertEqual(result["classification"], "INDETERMINATE")
        self.assertEqual(result["postgres16"]["status"]["state"], "NULL")

    def test_null_location_restriction_is_indeterminate(self):
        result = classify(capability_fixture(restricted=None))
        self.assertEqual(result["classification"], "INDETERMINATE")
        self.assertEqual(result["locationRestricted"]["state"], "NULL")

    def test_disabled_location_status_is_explicitly_restricted(self):
        result = classify(capability_fixture(location_status="Disabled"))
        self.assertEqual(result["classification"], "EXPLICITLY_RESTRICTED")

    def test_visible_location_status_is_indeterminate(self):
        result = classify(capability_fixture(location_status="Visible"))
        self.assertEqual(result["classification"], "INDETERMINATE")

    def test_default_location_status_is_indeterminate(self):
        result = classify(capability_fixture(location_status="Default"))
        self.assertEqual(result["classification"], "INDETERMINATE")

    def test_null_location_status_is_indeterminate(self):
        result = classify(capability_fixture(location_status=None))
        self.assertEqual(result["classification"], "INDETERMINATE")
        self.assertEqual(result["locationStatus"]["state"], "NULL")

    def test_absent_location_status_is_indeterminate(self):
        document = capability_fixture()
        del document[0]["status"]
        result = classify(document)
        self.assertEqual(result["classification"], "INDETERMINATE")
        self.assertEqual(result["locationStatus"]["state"], "ABSENT")

    def test_available_location_status_with_approved_values_passes(self):
        result = classify(capability_fixture(location_status="Available"))
        self.assertEqual(result["classification"], "AVAILABLE")

    def test_explicit_mismatched_region_is_rejected(self):
        result = classify(capability_fixture(region="westus"))
        self.assertEqual(result["classification"], "INDETERMINATE")
        self.assertEqual(result["recordRegion"]["state"], "CONFLICT")

    def test_generic_capability_name_is_accepted(self):
        result = classify(capability_fixture())
        self.assertEqual(result["locationName"], "FlexibleServerCapabilities")
        self.assertEqual(result["classification"], "AVAILABLE")

    def test_disabled_tier_is_explicitly_restricted(self):
        result = classify(capability_fixture(tier_status="Disabled"))
        self.assertEqual(result["classification"], "EXPLICITLY_RESTRICTED")

    def test_disabled_sku_is_explicitly_restricted(self):
        result = classify(capability_fixture(sku_status="Disabled"))
        self.assertEqual(result["classification"], "EXPLICITLY_RESTRICTED")

    def test_disabled_version_is_explicitly_restricted(self):
        result = classify(capability_fixture(version_status="Disabled"))
        self.assertEqual(result["classification"], "EXPLICITLY_RESTRICTED")

    def test_enabled_location_restriction_is_explicitly_restricted(self):
        result = classify(capability_fixture(restricted="Enabled"))
        self.assertEqual(result["classification"], "EXPLICITLY_RESTRICTED")

    def test_visible_or_default_status_never_passes(self):
        for status in ("Visible", "Default"):
            for field in ("tier_status", "sku_status", "version_status"):
                with self.subTest(status=status, field=field):
                    result = classify(capability_fixture(**{field: status}))
                    self.assertEqual(result["classification"], "INDETERMINATE")

    def test_unrelated_version_sixteen_does_not_match(self):
        document = capability_fixture()
        location = document[0]
        location["supportedServerVersions"] = [
            {"name": "15", "status": "Available", "supportedVersionsToUpgrade": ["16"]}
        ]
        result = classify(document)
        self.assertEqual(result["classification"], "INDETERMINATE")
        self.assertFalse(result["postgres16"]["listed"])

    def test_missing_tier_sku_or_version_fails_closed(self):
        for missing in ("tier", "sku", "version"):
            with self.subTest(missing=missing):
                document = capability_fixture()
                if missing == "tier":
                    document[0]["supportedServerEditions"] = []
                elif missing == "sku":
                    document[0]["supportedServerEditions"][0]["supportedServerSkus"] = []
                else:
                    document[0]["supportedServerVersions"] = []
                result = classify(document)
                self.assertEqual(result["classification"], "INDETERMINATE")

    def test_null_status_is_not_reported_as_confirmed_restriction(self):
        document = capability_fixture(
            tier_status=None,
            sku_status=None,
            version_status=None,
            restricted=None,
        )
        result = classify(document)
        self.assertEqual(result["classification"], "INDETERMINATE")
        self.assertEqual(result["blockingReasons"], [])
        self.assertIn("null", result["stopReason"])

    def test_absent_status_and_restriction_are_distinguished(self):
        document = capability_fixture()
        del document[0]["restricted"]
        del document[0]["supportedServerEditions"][0]["status"]
        result = classify(document)
        self.assertEqual(result["classification"], "INDETERMINATE")
        self.assertEqual(result["locationRestricted"]["state"], "ABSENT")
        self.assertEqual(result["burstable"]["status"]["state"], "ABSENT")

    def test_absent_tier_sku_and_version_statuses_are_indeterminate(self):
        document = capability_fixture()
        tier = document[0]["supportedServerEditions"][0]
        sku = tier["supportedServerSkus"][0]
        version = document[0]["supportedServerVersions"][0]
        del tier["status"]
        del sku["status"]
        del version["status"]
        result = classify(document)
        self.assertEqual(result["classification"], "INDETERMINATE")
        self.assertEqual(result["burstable"]["status"]["state"], "ABSENT")
        self.assertEqual(result["standardB1ms"]["status"]["state"], "ABSENT")
        self.assertEqual(result["postgres16"]["status"]["state"], "ABSENT")

    def test_provider_reason_blocks_and_sensitive_identifiers_are_redacted(self):
        document = capability_fixture()
        document[0]["supportedServerEditions"][0]["supportedServerSkus"][0][
            "reason"
        ] = "Restricted for subscription 12345678-1234-1234-1234-123456789abc"
        result = classify(document)
        self.assertEqual(result["classification"], "EXPLICITLY_RESTRICTED")
        self.assertNotIn("12345678-1234-1234-1234-123456789abc", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
