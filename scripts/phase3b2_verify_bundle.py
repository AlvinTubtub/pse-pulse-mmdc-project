"""Standalone no-training verifier for the Phase 3B.2 production candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.forecasting.real.artifacts.bundle import (  # noqa: E402
    ACCEPTANCE_BUNDLE_VERSION,
    ProductionBundleError,
    ensure_external_output_root,
    sha256_file,
    verify_bundle,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify an authoritative Phase 3B.2 bundle without training.")
    parser.add_argument(
        "--bundle",
        type=Path,
        default=Path.home() / "pse-pulse-production-artifacts" / ACCEPTANCE_BUNDLE_VERSION,
        help="Candidate bundle directory to verify.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        bundle = args.bundle.expanduser()
        ensure_external_output_root(ROOT, bundle)
        if bundle.is_symlink():
            raise ProductionBundleError("Bundle directory must not be a symlink")
        result = verify_bundle(bundle)
        result["bundle_directory"] = str(bundle.resolve())
        result["manifest_sha256"] = sha256_file(bundle / "manifest.json")
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except Exception as exc:
        print(json.dumps({"verified": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
