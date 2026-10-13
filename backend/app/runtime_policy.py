"""Small standard-library production safety policies shared by runtime tests."""

from __future__ import annotations

import ipaddress
from pathlib import Path
import socket
from urllib.parse import parse_qs, urlsplit


def validate_production_flags(*, environment: str, debug: bool, demo_mode: bool,
                              auto_create_schema: bool, real_models_enabled: bool,
                              activation_enabled: bool, process_role: str) -> None:
    if environment.lower() != "production":
        raise ValueError("ENVIRONMENT must be production.")
    if debug or demo_mode or auto_create_schema:
        raise ValueError("DEBUG, DEMO_MODE, and AUTO_CREATE_SCHEMA must be false.")
    if activation_enabled:
        raise ValueError("Model artifact activation is prohibited in production runtime configuration.")
    if process_role not in {"api", "production-eod", "production-bootstrap", "migration"}:
        raise ValueError("Invalid production process role.")
    if real_models_enabled and process_role != "production-eod":
        raise ValueError("Real inference is permitted only in the dedicated production EOD process.")


def validate_database_url(database_url: str, expected_private_host: str | None,
                          root_certificate: str, *, require_file: bool = True) -> str:
    parsed = urlsplit(database_url)
    if parsed.scheme != "postgresql+psycopg":
        raise ValueError("Production requires PostgreSQL through the psycopg driver; SQLite is forbidden.")
    host = (parsed.hostname or "").rstrip(".").lower()
    expected = (expected_private_host or "").rstrip(".").lower()
    if not expected or host != expected:
        raise ValueError("Database host must exactly match the owner-verified private PostgreSQL FQDN.")
    if not host.endswith(".postgres.database.azure.com"):
        raise ValueError("Production database host must be an Azure PostgreSQL Flexible Server FQDN.")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if query.get("sslmode") != ["verify-full"]:
        raise ValueError("Production PostgreSQL TLS requires sslmode=verify-full.")
    if query.get("sslrootcert") != [root_certificate] or not Path(root_certificate).is_absolute():
        raise ValueError("Production PostgreSQL must use the configured absolute trusted root CA bundle.")
    if require_file and not Path(root_certificate).is_file():
        raise ValueError("The configured PostgreSQL trusted root CA bundle is unavailable.")
    return host


def verify_private_database_resolution(host: str, resolver=socket.getaddrinfo) -> set[str]:
    try:
        results = resolver(host, 5432, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise RuntimeError("Private PostgreSQL DNS resolution failed.") from exc
    addresses = {item[4][0] for item in results}
    if not addresses:
        raise RuntimeError("Private PostgreSQL DNS returned no addresses.")
    try:
        private_ranges = (
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
            ipaddress.ip_network("fc00::/7"),
        )
        if any(
            not any(ipaddress.ip_address(address) in network for network in private_ranges)
            for address in addresses
        ):
            raise RuntimeError("PostgreSQL FQDN resolved to a non-private address.")
    except ValueError as exc:
        raise RuntimeError("PostgreSQL DNS returned an invalid address.") from exc
    return addresses


def validate_api_listener(host: str, port: int) -> None:
    if host != "127.0.0.1" or port != 8000:
        raise ValueError("Production API must bind only to 127.0.0.1:8000.")


def validate_forecast_coverage(expected_pairs: set[tuple[str, str]], actual_pairs: set[tuple[str, str]],
                               item_count: int) -> None:
    if not expected_pairs or actual_pairs != expected_pairs or item_count != len(expected_pairs):
        raise ValueError("Forecast outputs do not cover each active company/model exactly once.")
