"""Single source of truth for the configured 15-company universe in PSE Pulse.

Adapted from the official Capstone backend (backend/config/companies.py)
for the personal Azure edition.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping, Sequence, Dict


@dataclass(frozen=True, slots=True)
class ConfiguredCompany:
    """Metadata for one modeled Philippine Stock Exchange equity."""

    symbol: str
    name: str
    sector: str
    pse_issue_name: str

    @property
    def raw_filename(self) -> str:
        return f"{self.symbol}.csv"


# Canonical sectors for the official 15-company universe
SECTOR_METADATA: Final[Mapping[str, Dict[str, str]]] = MappingProxyType({
    "Financials": {
        "code": "FIN",
        "description": "Banking and Financial Institutions",
    },
    "Industrial": {
        "code": "IND",
        "description": "Manufacturing, Electricity, and Food Industry",
    },
    "Property": {
        "code": "PROP",
        "description": "Real Estate and Property Developers",
    },
    "Services": {
        "code": "SERV",
        "description": "Telecommunications and Logistics Services",
    },
    "Mining and Oil": {
        "code": "MO",
        "description": "Mining, Metals, and Energy Exploration",
    },
})


# The official 15 modeled equities
OFFICIAL_15_COMPANIES: Final[tuple[ConfiguredCompany, ...]] = (
    ConfiguredCompany("ALI", "Ayala Land, Inc.", "Property", "AYALA LAND"),
    ConfiguredCompany("APX", "Apex Mining Co., Inc.", "Mining and Oil", "APEX MINING"),
    ConfiguredCompany("BPI", "Bank of the Philippine Islands", "Financials", "BANK PH ISLANDS"),
    ConfiguredCompany("GLO", "Globe Telecom, Inc.", "Services", "GLOBE TELECOM"),
    ConfiguredCompany("ICT", "International Container Terminal Services, Inc.", "Services", "INTL CONTAINER"),
    ConfiguredCompany("JFC", "Jollibee Foods Corporation", "Industrial", "JOLLIBEE"),
    ConfiguredCompany("MBT", "Metropolitan Bank & Trust Company", "Financials", "METROBANK"),
    ConfiguredCompany("MEG", "Megaworld Corporation", "Property", "MEGAWORLD"),
    ConfiguredCompany("MER", "Manila Electric Company", "Industrial", "MERALCO"),
    ConfiguredCompany("NIKL", "Nickel Asia Corporation", "Mining and Oil", "NICKEL ASIA"),
    ConfiguredCompany("PGOLD", "Puregold Price Club, Inc.", "Services", "PUREGOLD"),
    ConfiguredCompany("SCC", "Semirara Mining and Power Corporation", "Mining and Oil", "SEMIRARA MINING"),
    ConfiguredCompany("SECB", "Security Bank Corporation", "Financials", "SECURITY BANK"),
    ConfiguredCompany("SHLPH", "Shell Pilipinas Corporation", "Industrial", "SHELL PILIPINAS"),
    ConfiguredCompany("SMPH", "SM Prime Holdings, Inc.", "Property", "SM PRIME HLDG"),
)


COMPANY_BY_SYMBOL: Final[Mapping[str, ConfiguredCompany]] = MappingProxyType({
    company.symbol: company for company in OFFICIAL_15_COMPANIES
})


def get_configured_company(symbol: str) -> ConfiguredCompany:
    """Return configured company metadata or raise ValueError for unknown symbols."""
    normalized = symbol.strip().upper()
    try:
        return COMPANY_BY_SYMBOL[normalized]
    except KeyError as exc:
        raise ValueError(f"Unknown configured company symbol: {symbol!r}") from exc


def get_all_configured_symbols() -> Sequence[str]:
    """Return alphabetical list of the 15 configured company symbols."""
    return tuple(c.symbol for c in sorted(OFFICIAL_15_COMPANIES, key=lambda x: x.symbol))
