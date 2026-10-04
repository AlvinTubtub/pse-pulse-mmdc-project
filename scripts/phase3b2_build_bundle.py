"""CLI for the offline authoritative Phase 3B.2 45-artifact bundle."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sys

os.environ["CUDA_VISIBLE_DEVICES"] = ""
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.database import SessionLocal  # noqa: E402
from backend.app.forecasting.real.artifacts.bundle import ACCEPTANCE_BUNDLE_VERSION  # noqa: E402
from backend.app.forecasting.real.training.bundle import build_authoritative_bundle  # noqa: E402

LOGGER = logging.getLogger("phase3b2_bundle_builder")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sequential offline builder for the pinned authoritative 15-company, 45-artifact bundle."
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("/tmp/pse-pulse-official-source"),
        help="Verified pinned official source checkout used only for historical parity.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path.home() / "pse-pulse-production-artifacts",
        help="External persistent artifact root; must resolve outside the Git repository.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = parse_args(argv)
    db = SessionLocal()
    try:
        result = build_authoritative_bundle(
            db=db,
            repository_root=ROOT,
            output_root=args.output_root,
            official_source_root=args.source_root,
            bundle_version=ACCEPTANCE_BUNDLE_VERSION,
        )
        printable = {
            key: (str(value) if isinstance(value, Path) else value)
            for key, value in result.items()
        }
        print(json.dumps(printable, indent=2, sort_keys=True, allow_nan=False))
        LOGGER.info("BUNDLE VERIFICATION PASSED 45/45; manifest_sha256=%s", result["manifest_sha256"])
        return 0
    except Exception:
        LOGGER.exception("Authoritative Phase 3B.2 build failed; no partial bundle was finalized")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
