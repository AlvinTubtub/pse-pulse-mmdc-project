"""Standard-library verification for reviewed PSE calendar and source manifests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import math

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ProductionInputError(ValueError):
    """A production data or calendar input failed provenance checks."""


@dataclass(frozen=True)
class ApprovedCalendar:
    sha256: str
    coverage_start: date
    coverage_end: date
    trading_sessions: frozenset[date]

    def is_session(self, session_date: date) -> bool:
        return self.coverage_start <= session_date <= self.coverage_end and session_date in self.trading_sessions

    def next_session(self, origin: date) -> date:
        if not self.is_session(origin):
            raise ProductionInputError("Forecast origin is not an approved trading session.")
        for candidate in sorted(item for item in self.trading_sessions if item > origin):
            if candidate <= self.coverage_end:
                return candidate
        raise ProductionInputError("Approved calendar does not cover the next forecast session.")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _official_pse_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    return parsed.scheme == "https" and (host == "pse.com.ph" or host.endswith(".pse.com.ph"))


def _verified_json(path: Path, expected_sha256: str) -> tuple[dict, str]:
    if not SHA256_RE.fullmatch(expected_sha256 or ""):
        raise ProductionInputError("A pinned SHA-256 is required for each reviewed manifest.")
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o022:
        raise ProductionInputError("A reviewed manifest is missing, linked, or writable by untrusted users.")
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise ProductionInputError("A reviewed manifest does not match its pinned SHA-256.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductionInputError("A reviewed manifest is invalid JSON.") from exc
    if not isinstance(value, dict):
        raise ProductionInputError("A reviewed manifest must contain a JSON object.")
    return value, actual


def verify_calendar_manifest(path: Path, expected_sha256: str, trade_date: date) -> ApprovedCalendar:
    payload, digest = _verified_json(Path(path), expected_sha256)
    if payload.get("schema_version") != 1 or payload.get("timezone") != "Asia/Manila":
        raise ProductionInputError("Calendar manifest schema or timezone is not approved.")
    if not _official_pse_url(payload.get("source_url")) or not SHA256_RE.fullmatch(str(payload.get("source_sha256", ""))):
        raise ProductionInputError("Calendar source provenance is missing or not from the official PSE domain.")
    if not str(payload.get("reviewed_by", "")).strip():
        raise ProductionInputError("Calendar manifest lacks a named reviewer.")
    try:
        reviewed_at = datetime.fromisoformat(str(payload["reviewed_at"]).replace("Z", "+00:00"))
        coverage_start = date.fromisoformat(payload["coverage_start"])
        coverage_end = date.fromisoformat(payload["coverage_end"])
        sessions = [date.fromisoformat(item) for item in payload["trading_sessions"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise ProductionInputError("Calendar manifest contains invalid dates or review time.") from exc
    if reviewed_at.tzinfo is None or coverage_start > coverage_end:
        raise ProductionInputError("Calendar review time or coverage interval is invalid.")
    if len(sessions) != len(set(sessions)) or sessions != sorted(sessions):
        raise ProductionInputError("Calendar session dates must be sorted and unique.")
    if any(item < coverage_start or item > coverage_end or item.weekday() >= 5 for item in sessions):
        raise ProductionInputError("Calendar contains an out-of-range date or a weekend session.")
    if not coverage_start <= trade_date <= coverage_end:
        raise ProductionInputError("Requested date is outside approved calendar coverage.")
    return ApprovedCalendar(digest, coverage_start, coverage_end, frozenset(sessions))


def verify_source_manifest_record(manifest_path: Path, expected_manifest_sha256: str,
                                  trade_date: date, expected_source_sha256: str) -> tuple[dict, str]:
    payload, manifest_sha = _verified_json(Path(manifest_path), expected_manifest_sha256)
    if payload.get("schema_version") != 1 or payload.get("source_type") != "PSE_DQR":
        raise ProductionInputError("Source manifest type is not the approved PSE DQR format.")
    if payload.get("trade_date") != trade_date.isoformat():
        raise ProductionInputError("Source manifest trade date does not match the requested session.")
    if payload.get("file_sha256") != expected_source_sha256 or not SHA256_RE.fullmatch(expected_source_sha256 or ""):
        raise ProductionInputError("Source manifest does not identify the imported source hash.")
    if not _official_pse_url(payload.get("source_url")) or not str(payload.get("reviewed_by", "")).strip():
        raise ProductionInputError("Source provenance must identify the official PSE source and reviewer.")
    try:
        retrieved = datetime.fromisoformat(str(payload["retrieved_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError) as exc:
        raise ProductionInputError("Source retrieval timestamp is missing or invalid.") from exc
    if retrieved.tzinfo is None:
        raise ProductionInputError("Source retrieval timestamp must include a timezone.")
    return payload, manifest_sha


def verify_source_manifest(source_file: Path, manifest_path: Path, expected_manifest_sha256: str,
                           trade_date: date) -> tuple[dict, str, str]:
    source_file = Path(source_file)
    if source_file.is_symlink() or not source_file.is_file() or source_file.suffix.lower() not in {".pdf", ".txt"}:
        raise ProductionInputError("Official source file is missing, linked, or has an unsupported format.")
    if source_file.stat().st_mode & 0o022:
        raise ProductionInputError("Official source file must not be writable by untrusted users.")
    source_sha = sha256_file(source_file)
    payload, manifest_sha = verify_source_manifest_record(
        manifest_path, expected_manifest_sha256, trade_date, source_sha
    )
    return payload, source_sha, manifest_sha


def verify_source_approval_index(path: Path, expected_sha256: str, trade_date: date,
                                 incoming_dir: Path) -> tuple[Path, str]:
    index, _ = _verified_json(Path(path), expected_sha256)
    if index.get("schema_version") != 1:
        raise ProductionInputError("Source approval index schema is not supported.")
    approvals = index.get("approved_sources")
    if not isinstance(approvals, dict):
        raise ProductionInputError("Source approval index has no approved_sources map.")
    entry = approvals.get(trade_date.isoformat())
    if not isinstance(entry, dict):
        raise ProductionInputError("No owner-approved source manifest exists for the requested session.")
    name = entry.get("manifest_file")
    digest = entry.get("manifest_sha256")
    if not isinstance(name, str) or Path(name).name != name or name in {"", ".", ".."}:
        raise ProductionInputError("Approved source manifest name is not a simple filename.")
    if not SHA256_RE.fullmatch(str(digest or "")):
        raise ProductionInputError("Approved source manifest index entry has an invalid SHA-256.")
    approved_path = (Path(incoming_dir) / name).resolve(strict=False)
    resolved_dir = Path(incoming_dir).resolve(strict=True)
    if approved_path.parent != resolved_dir:
        raise ProductionInputError("Approved source manifest path escaped the protected incoming directory.")
    return approved_path, digest


def validate_bundle_coverage(entries: list[dict], symbols: set[str], model_codes: tuple[str, ...]) -> set[tuple[str, str]]:
    expected = {(symbol.upper(), code.upper()) for symbol in symbols for code in model_codes}
    actual = {(str(entry.get("symbol", "")).upper(), str(entry.get("model_code", "")).upper())
              for entry in entries if isinstance(entry, dict)}
    if not expected or actual != expected or len(entries) != len(expected):
        raise ProductionInputError("Approved model bundle does not cover every active company/model exactly once.")
    return expected


def validate_forecast_outcomes(items, expected_pairs: set[tuple[str, str]], origin_date: date,
                               target_date: date) -> None:
    actual = {(str(item.symbol).upper(), str(item.model_code).upper()) for item in items}
    if not expected_pairs or actual != expected_pairs or len(items) != len(expected_pairs):
        raise ProductionInputError("Forecast outputs do not cover each active company/model exactly once.")
    for item in items:
        if item.origin_date != origin_date or item.target_date != target_date:
            raise ProductionInputError("Forecast lineage dates do not match the approved session calendar.")
        if item.status not in {"PERSISTED", "UNCHANGED"}:
            raise ProductionInputError("Forecast result has an unexpected persistence state.")
        try:
            close = float(item.predicted_close)
            delta = float(item.predicted_delta)
            lower = None if item.lower_bound is None else float(item.lower_bound)
            upper = None if item.upper_bound is None else float(item.upper_bound)
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            raise ProductionInputError("Forecast output contains a missing or invalid numerical value.") from exc
        if not math.isfinite(close) or close <= 0 or not math.isfinite(delta):
            raise ProductionInputError("Forecast output contains a non-positive price or non-finite value.")
        if lower is not None and not math.isfinite(lower):
            raise ProductionInputError("Forecast lower bound is not finite.")
        if upper is not None and not math.isfinite(upper):
            raise ProductionInputError("Forecast upper bound is not finite.")
        if lower is not None and upper is not None and lower > upper:
            raise ProductionInputError("Forecast bounds are inconsistent.")
