#!/usr/bin/env python3
"""Plan or explicitly activate the frozen Phase 3B.2 candidate bundle."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.app.database import SessionLocal
from backend.app.forecasting.real.artifacts.bundle import ACCEPTANCE_BUNDLE_VERSION
from backend.app.forecasting.real.artifacts.runtime import read_verified_manifest
from backend.app.services.model_activation_service import activate_candidate_bundle

APPROVED_SHA = "4225e60044f000b16147e01f6ff165968523c1efd9647e57d9c7a6f5f5a27454"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, default=Path.home() / "pse-pulse-production-artifacts" / ACCEPTANCE_BUNDLE_VERSION)
    parser.add_argument("--execute", action="store_true", help="Perform the atomic activation transaction")
    parser.add_argument("--confirm-bundle-version")
    parser.add_argument("--confirm-manifest-sha")
    args = parser.parse_args()
    _manifest, actual_sha = read_verified_manifest(args.bundle_root)
    if actual_sha != APPROVED_SHA:
        parser.error("Frozen bundle SHA does not match the approved manifest identity")
    if not args.execute:
        print(f"PLAN ONLY: would activate {ACCEPTANCE_BUNDLE_VERSION} ({actual_sha}); no database changes made")
        return 0
    if args.confirm_bundle_version != ACCEPTANCE_BUNDLE_VERSION or args.confirm_manifest_sha != APPROVED_SHA:
        parser.error("--execute requires the exact bundle version and manifest SHA confirmations")
    db = SessionLocal()
    try:
        activate_candidate_bundle(
            db, args.bundle_root,
            confirm_bundle_version=args.confirm_bundle_version,
            confirm_manifest_sha256=args.confirm_manifest_sha,
        )
        print("Activation committed.")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"Activation rejected and rolled back: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
