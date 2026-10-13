"""Separate strict entry point for the pinned official historical source import."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

from backend.app.config import get_settings
from backend.app.database import SessionLocal, engine
from backend.app.runtime_policy import validate_production_flags
from backend.pipeline.bootstrap.provenance import (
    BootstrapSourceVerificationError,
    OfficialSourceVerifier,
)
from backend.pipeline.bootstrap.service import HistoricalBootstrapService

logger = logging.getLogger("pse_pulse_production_bootstrap")


def verify_migration_head(db) -> str:
    config = Config("backend/alembic.ini")
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError("Production migration graph must have exactly one head.")
    with db.connection() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != heads[0]:
        raise RuntimeError("Target database revision must equal the reviewed Alembic head before bootstrap.")
    return heads[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-conflict-updates", action="store_true")
    args = parser.parse_args(argv)
    settings = get_settings()
    try:
        validate_production_flags(
            environment=settings.ENVIRONMENT,
            debug=settings.DEBUG,
            demo_mode=settings.DEMO_MODE,
            auto_create_schema=settings.AUTO_CREATE_SCHEMA,
            real_models_enabled=settings.REAL_MODELS_ENABLED,
            activation_enabled=settings.MODEL_ARTIFACT_ACTIVATION_ENABLED,
            process_role=settings.PROCESS_ROLE,
        )
        if settings.PROCESS_ROLE != "production-bootstrap":
            raise RuntimeError("Historical import requires the dedicated production-bootstrap role.")
        db = SessionLocal()
        try:
            revision = verify_migration_head(db)
            verified = OfficialSourceVerifier().verify(source_root=args.source_root)
            logger.info("Pinned source and migration head verified; dry_run=%s", args.dry_run)
            summary = HistoricalBootstrapService(
                db=db,
                allow_conflict_updates=args.allow_conflict_updates,
                verifier=OfficialSourceVerifier(),
            ).bootstrap_official_repo(
                source_root=verified.source_root,
                verified_source=verified,
                dry_run=args.dry_run,
            )
            logger.info(
                "Historical bootstrap %s: source_commit=%s migration=%s symbols=%d inserted=%d updated=%d unchanged=%d.",
                summary.status,
                verified.commit,
                revision,
                summary.total_symbols,
                summary.total_rows_inserted,
                summary.total_rows_updated,
                summary.total_rows_unchanged,
            )
            return 0
        finally:
            db.close()
    except BootstrapSourceVerificationError:
        logger.exception("Official historical source provenance verification failed.")
        return 1
    except Exception:
        logger.exception("Production historical bootstrap failed closed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
