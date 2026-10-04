#!/usr/bin/env python3
"""Run the local non-persistent Phase 3B.3 bundle gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.app.database import SessionLocal
from backend.app.forecasting.real.artifacts.bundle import ACCEPTANCE_BUNDLE_VERSION, verify_bundle
from backend.app.forecasting.real.artifacts.runtime import read_verified_manifest
from backend.app.forecasting.real.evaluation.gate import evaluate_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, default=Path.home() / "pse-pulse-production-artifacts" / ACCEPTANCE_BUNDLE_VERSION)
    parser.add_argument("--evidence", type=Path, default=Path.home() / "pse-pulse-production-artifacts" / "bundle_validation.json")
    parser.add_argument("--output-dir", type=Path, default=Path.home() / "pse-pulse-production-artifacts" / "phase3b3" / ACCEPTANCE_BUNDLE_VERSION)
    parser.add_argument("--test-summary", type=Path, required=True, help="JSON acceptance results from the required backend/frontend/API regressions")
    parser.add_argument("--replace-outputs", action="store_true", help="Replace prior Phase 3B.3 outputs for a corrected evaluator run")
    args = parser.parse_args()
    if not args.replace_outputs and ((args.output_dir / "activation_plan.json").exists() or (args.output_dir / "phase3b3_evaluation.json").exists()):
        parser.error("Refusing to overwrite existing Phase 3B.3 outputs")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        test_summary = json.loads(args.test_summary.read_text(encoding="utf-8"))
        required_statuses = {
            "lightweight_backend": "PASS", "torch_enabled_backend": "PASS",
            "lightweight_pip_check": "PASS", "torch_enabled_pip_check": "PASS",
            "frontend_lint": "PASS", "frontend_typecheck": "PASS", "frontend_build": "PASS",
            "frontend_audit": "PASS", "api_regression": "PASS", "migration": "PASS",
            "dependency_boundary": "PASS",
        }
        if any(test_summary.get(key) != expected for key, expected in required_statuses.items()):
            raise RuntimeError("Acceptance test summary is incomplete or contains a failing gate")
        result = evaluate_bundle(db, args.bundle_root, args.evidence)
        post_verification = verify_bundle(args.bundle_root)
        _post_manifest, post_manifest_sha = read_verified_manifest(args.bundle_root)
        if post_manifest_sha != result["manifest_sha256"] or post_verification != result["verification"]:
            raise RuntimeError("Frozen bundle post-evaluation verification differs from initial verification")
        result.update({
            "schema_id": "pse-pulse.phase3b3-evaluation",
            "schema_version": 1,
            "evaluated_at": started,
            "decision": "ELIGIBLE_FOR_ACTIVATION",
            "activation_status": "BUT_NOT_ACTIVATED",
            "post_evaluation_verification": post_verification,
            "frozen_bundle_unchanged_after_evaluation": True,
            "migration_status": test_summary["migration"],
            "acceptance_test_summary": test_summary,
        })
        manifest, digest = read_verified_manifest(args.bundle_root)
        artifacts = []
        for entry in manifest["entries"]:
            artifacts.append({key: entry[key] for key in (
                "symbol", "model_code", "artifact_format", "artifact_relative_path",
                "artifact_sha256", "metadata_sha256", "trained_through", "data_row_count",
            )})
        plan = {
            "schema_id": "pse-pulse.activation-plan", "schema_version": 1,
            "bundle_version": manifest["bundle_version"], "manifest_sha256": digest,
            "decision": result["decision"], "canonical_symbols": manifest["symbols"],
            "model_families": manifest["model_families"], "artifact_count": 45,
            "artifacts": artifacts,
            "database_actions_if_later_authorized": [
                "register candidate rows as inactive", "deactivate previous version rows", "activate exact candidate rows",
            ],
            "executed": False,
        }
        if len(artifacts) != 45 or plan["artifact_count"] != 45 or len(set(plan["canonical_symbols"])) != 15:
            raise RuntimeError("Activation plan inventory failed structural validation")
        result["activation_plan_validation"] = "PASS"
        plan_path = args.output_dir / "activation_plan.json"
        receipt_path = args.output_dir / "phase3b3_evaluation.json"
        with plan_path.open("w" if args.replace_outputs else "x", encoding="utf-8") as stream:
            stream.write(json.dumps(plan, indent=2, sort_keys=True, allow_nan=False) + "\n")
        result["activation_plan_sha256"] = hashlib.sha256(plan_path.read_bytes()).hexdigest()
        with receipt_path.open("w" if args.replace_outputs else "x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
        result["evaluation_receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        # Hash cannot be embedded in its own receipt; report it on stdout for the acceptance report.
        print(json.dumps({"activation_plan": str(plan_path), "activation_plan_sha256": result["activation_plan_sha256"], "evaluation_receipt": str(receipt_path), "evaluation_receipt_sha256": result["evaluation_receipt_sha256"], "decision": result["decision"], "counts": {"verification": result["verification"], "boundary_replay": result["boundary_replay_count"], "reproduction_matches": result["reproduction_match_count"], "current_shadow": result["current_shadow_count"], "database_row_deltas": result["database_row_deltas"]}}, indent=2))
        return 0
    except Exception as exc:
        print(f"PHASE 3B.3 GATE FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
