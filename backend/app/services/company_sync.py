"""Company and Sector synchronization service for PSE Pulse.

Idempotently synchronizes the database company and sector tables against
the authoritative 15-company universe (backend.app.domain.company_universe).
"""

from dataclasses import dataclass
import logging
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from backend.app.domain.company_universe import OFFICIAL_15_COMPANIES, SECTOR_METADATA, ConfiguredCompany
from backend.app.models.sector import Sector
from backend.app.models.company import Company

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CompanySyncResult:
    """Outcome of an idempotent company synchronization run."""

    sectors_created: int
    sectors_updated: int
    companies_inserted: int
    companies_updated: int
    companies_unchanged: int
    total_active_companies: int


class CompanySyncService:
    """Synchronizes database companies and sectors against canonical 15-company universe."""

    def __init__(self, db: Session):
        self.db = db

    def sync_sectors(self) -> Dict[str, Sector]:
        """Ensure all canonical sectors exist and return mapping of sector name -> Sector."""
        sector_map: Dict[str, Sector] = {}

        for sec_name, sec_meta in SECTOR_METADATA.items():
            code = sec_meta["code"]
            desc = sec_meta["description"]

            existing = (
                self.db.query(Sector)
                .filter((Sector.name == sec_name) | (Sector.code == code))
                .first()
            )

            if existing:
                updated = False
                if existing.name != sec_name:
                    existing.name = sec_name
                    updated = True
                if existing.code != code:
                    existing.code = code
                    updated = True
                if existing.description != desc:
                    existing.description = desc
                    updated = True
                sector_map[sec_name] = existing
            else:
                new_sector = Sector(name=sec_name, code=code, description=desc)
                self.db.add(new_sector)
                self.db.flush()
                sector_map[sec_name] = new_sector

        return sector_map

    def sync_companies(self, commit: bool = True) -> CompanySyncResult:
        """Idempotently synchronize configured companies into the database.

        Guarantees:
        - Preserves existing primary keys when symbols match.
        - Normalizes symbols to uppercase.
        - Enforces symbol uniqueness.
        - Updates names and sectors to canonical definitions.
        - Sets is_active = True for the official 15 companies.
        - Does not delete unconfigured or historical companies.
        - Completely idempotent (second run produces 0 inserts, 0 updates).
        """
        sector_map = self.sync_sectors()

        inserted = 0
        updated = 0
        unchanged = 0

        for conf in OFFICIAL_15_COMPANIES:
            sym = conf.symbol.strip().upper()
            target_sector = sector_map.get(conf.sector)
            if not target_sector:
                raise ValueError(f"Unknown sector '{conf.sector}' for configured symbol '{sym}'")

            existing = (
                self.db.query(Company)
                .filter(Company.symbol == sym)
                .first()
            )

            if existing:
                needs_update = False
                if existing.name != conf.name:
                    existing.name = conf.name
                    needs_update = True
                if existing.sector_id != target_sector.id:
                    existing.sector_id = target_sector.id
                    needs_update = True
                if not existing.is_active:
                    existing.is_active = True
                    needs_update = True

                if needs_update:
                    updated += 1
                else:
                    unchanged += 1
            else:
                new_comp = Company(
                    symbol=sym,
                    name=conf.name,
                    sector_id=target_sector.id,
                    is_active=True,
                )
                self.db.add(new_comp)
                self.db.flush()
                inserted += 1

        # Deactivate any active companies not in the official 15-company universe
        canonical_symbols = {conf.symbol.strip().upper() for conf in OFFICIAL_15_COMPANIES}
        obsolete_active = (
            self.db.query(Company)
            .filter(Company.is_active == True, ~Company.symbol.in_(canonical_symbols))
            .all()
        )
        for obs in obsolete_active:
            obs.is_active = False
            updated += 1

        if commit:
            self.db.commit()
        else:
            self.db.flush()

        active_count = self.db.query(Company).filter(Company.is_active == True).count()

        result = CompanySyncResult(
            sectors_created=len(sector_map),
            sectors_updated=0,
            companies_inserted=inserted,
            companies_updated=updated,
            companies_unchanged=unchanged,
            total_active_companies=active_count,
        )

        logger.info(
            "Company synchronization complete: inserted=%d, updated=%d, unchanged=%d, active=%d",
            inserted,
            updated,
            unchanged,
            active_count,
        )
        return result
