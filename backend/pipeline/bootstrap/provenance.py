"""Provenance verification for official historical bootstrap repository.

Enforces fail-closed verification of official repository checkout,
pinned Git commit, clean working tree, and SHA-256 file hashes before
any historical market data can be persisted.
"""

from dataclasses import dataclass, field
import hashlib
import json
import logging
from pathlib import Path
import subprocess
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.app.domain.company_universe import OFFICIAL_15_COMPANIES

logger = logging.getLogger(__name__)

EXPECTED_OFFICIAL_REPOSITORY = "https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git"
EXPECTED_OFFICIAL_COMMIT = "b8bf39f8e94729687c2e877dc164ea8a4f69e2b1"
DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parents[2] / "bootstrap-manifests" / "official_repo_b8bf39f_manifest.json"


class BootstrapSourceVerificationError(ValueError):
    """Raised when official bootstrap source fails fail-closed provenance verification."""
    pass


@dataclass(frozen=True)
class VerifiedBootstrapSource:
    """Immutable record of verified historical bootstrap source."""

    repository: str
    commit: str
    source_root: Path
    raw_data_dir: Path
    manifest_sha256s: Dict[str, str]
    file_metadata: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class OfficialSourceVerifier:
    """Fail-closed verifier for official historical bootstrap repository."""

    def __init__(
        self,
        expected_repository: str = EXPECTED_OFFICIAL_REPOSITORY,
        expected_commit: str = EXPECTED_OFFICIAL_COMMIT,
        manifest_path: Optional[Path] = None,
        git_runner: Optional[Callable[[List[str], Path], Tuple[int, str, str]]] = None,
    ):
        self.expected_repository = expected_repository
        self.expected_commit = expected_commit
        self.manifest_path = Path(manifest_path) if manifest_path else DEFAULT_MANIFEST_PATH
        self._git_runner = git_runner or self._default_git_runner

    @staticmethod
    def _default_git_runner(args: List[str], cwd: Path) -> Tuple[int, str, str]:
        cmd = ["git", "-C", str(cwd)] + args
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
            return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
        except Exception as e:
            return 1, "", str(e)

    def verify(
        self,
        source_root: Optional[Path] = None,
        raw_data_dir: Optional[Path] = None,
    ) -> VerifiedBootstrapSource:
        """Verify the supplied historical repository against all 4 integrity gates.

        Gates:
        1. Repository Root & Canonical Path Gate
        2. Git HEAD Commit Gate
        3. Clean Working Tree Gate
        4. Manifest & 15-File SHA-256 Gate

        Fails closed with BootstrapSourceVerificationError on any mismatch.
        """
        if source_root is None and raw_data_dir is None:
            raise BootstrapSourceVerificationError(
                "Either source_root or raw_data_dir must be provided for bootstrap provenance verification."
            )

        resolved_source_root: Optional[Path] = None
        resolved_raw_dir: Optional[Path] = None

        if source_root is not None:
            resolved_source_root = Path(source_root).resolve()
            if not resolved_source_root.is_dir():
                raise BootstrapSourceVerificationError(
                    f"Specified source root does not exist or is not a directory: {source_root}"
                )

        if raw_data_dir is not None:
            resolved_raw_dir = Path(raw_data_dir).resolve()
            if not resolved_raw_dir.is_dir():
                raise BootstrapSourceVerificationError(
                    f"Specified raw data directory does not exist or is not a directory: {raw_data_dir}"
                )

        # Gate 1: Derive & verify repository root
        if resolved_source_root is None:
            assert resolved_raw_dir is not None
            ret, stdout, stderr = self._git_runner(["rev-parse", "--show-toplevel"], resolved_raw_dir)
            if ret != 0:
                raise BootstrapSourceVerificationError(
                    f"Failed to find Git repository root for raw directory {resolved_raw_dir}: {stderr}"
                )
            resolved_source_root = Path(stdout).resolve()
        else:
            ret, stdout, stderr = self._git_runner(["rev-parse", "--show-toplevel"], resolved_source_root)
            if ret != 0:
                raise BootstrapSourceVerificationError(
                    f"Specified source root {resolved_source_root} is not inside a Git repository: {stderr}"
                )
            actual_top = Path(stdout).resolve()
            if actual_top != resolved_source_root:
                raise BootstrapSourceVerificationError(
                    f"Specified source root {resolved_source_root} does not match Git repository toplevel {actual_top}."
                )

        # Enforce canonical path structure
        canonical_raw_dir = (resolved_source_root / "backend" / "data" / "raw").resolve()
        if resolved_raw_dir is None:
            resolved_raw_dir = canonical_raw_dir
        else:
            if resolved_raw_dir != canonical_raw_dir:
                raise BootstrapSourceVerificationError(
                    f"Supplied raw directory {resolved_raw_dir} does not match canonical structure "
                    f"'{canonical_raw_dir}' under repository root {resolved_source_root}."
                )

        if not resolved_raw_dir.is_dir():
            raise BootstrapSourceVerificationError(
                f"Canonical raw data directory does not exist in repository: {resolved_raw_dir}"
            )

        # Gate 2: Verify exact source commit
        ret, stdout, stderr = self._git_runner(["rev-parse", "HEAD"], resolved_source_root)
        if ret != 0:
            raise BootstrapSourceVerificationError(
                f"Failed to resolve Git HEAD for {resolved_source_root}: {stderr}"
            )
        actual_head = stdout.strip()
        if actual_head != self.expected_commit:
            raise BootstrapSourceVerificationError(
                f"Source Git HEAD commit mismatch: actual '{actual_head}' does not match "
                f"pinned official commit '{self.expected_commit}'."
            )

        # Gate 3: Verify clean working tree
        ret, stdout, stderr = self._git_runner(["status", "--porcelain=v1"], resolved_source_root)
        if ret != 0:
            raise BootstrapSourceVerificationError(
                f"Failed to query Git status for {resolved_source_root}: {stderr}"
            )
        if stdout.strip():
            raise BootstrapSourceVerificationError(
                f"Source repository working tree is not clean. Status output:\n{stdout}\n"
                "Official historical bootstrap requires an untouched, clean checkout."
            )

        # Gate 4: Manifest & SHA-256 verification
        if not self.manifest_path.is_file():
            raise BootstrapSourceVerificationError(
                f"Committed bootstrap manifest file missing at {self.manifest_path}."
            )

        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as e:
            raise BootstrapSourceVerificationError(
                f"Failed to parse committed bootstrap manifest JSON at {self.manifest_path}: {e}"
            ) from e

        manifest_commit = manifest.get("source_commit")
        if manifest_commit != self.expected_commit:
            raise BootstrapSourceVerificationError(
                f"Manifest source_commit mismatch: manifest declares '{manifest_commit}', "
                f"expected '{self.expected_commit}'."
            )

        manifest_repo = manifest.get("source_repository")
        if manifest_repo != self.expected_repository:
            raise BootstrapSourceVerificationError(
                f"Manifest source_repository mismatch: manifest declares '{manifest_repo}', "
                f"expected '{self.expected_repository}'."
            )

        symbols_list = manifest.get("symbols", [])
        if not isinstance(symbols_list, list):
            raise BootstrapSourceVerificationError("Manifest 'symbols' must be a list.")

        manifest_symbols_map: Dict[str, Dict[str, Any]] = {}
        for entry in symbols_list:
            if isinstance(entry, dict) and "symbol" in entry:
                manifest_symbols_map[entry["symbol"]] = entry

        canonical_symbols = {c.symbol for c in OFFICIAL_15_COMPANIES}
        if set(manifest_symbols_map.keys()) != canonical_symbols:
            raise BootstrapSourceVerificationError(
                f"Manifest symbol set mismatch: found {set(manifest_symbols_map.keys())}, "
                f"expected {canonical_symbols}."
            )

        manifest_sha256s: Dict[str, str] = {}
        file_metadata: Dict[str, Dict[str, Any]] = {}

        for conf in sorted(OFFICIAL_15_COMPANIES, key=lambda c: c.symbol):
            sym = conf.symbol
            csv_path = resolved_raw_dir / conf.raw_filename
            if not csv_path.is_file():
                raise BootstrapSourceVerificationError(
                    f"Official raw CSV for {sym} missing at {csv_path}."
                )

            # Compute actual file SHA-256
            hasher = hashlib.sha256()
            with open(csv_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            actual_sha = hasher.hexdigest()

            expected_meta = manifest_symbols_map[sym]
            expected_sha = expected_meta.get("sha256")
            if actual_sha != expected_sha:
                raise BootstrapSourceVerificationError(
                    f"SHA-256 hash mismatch for {sym} ({conf.raw_filename}): "
                    f"computed '{actual_sha}' != manifest '{expected_sha}'."
                )

            # Metadata diagnostic & parity checks (row count, first date, last date)
            with open(csv_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]

            if len(lines) < 2:
                raise BootstrapSourceVerificationError(
                    f"Raw CSV file for {sym} ({conf.raw_filename}) is empty or missing data rows."
                )

            data_rows = len(lines) - 1
            expected_rows = expected_meta.get("row_count")
            if expected_rows is not None and data_rows != expected_rows:
                raise BootstrapSourceVerificationError(
                    f"Metadata row_count mismatch for {sym}: actual {data_rows} rows != manifest {expected_rows}."
                )

            actual_first_date = lines[1].split(",")[0].strip()
            expected_first_date = expected_meta.get("first_trade_date")
            if expected_first_date is not None and actual_first_date != expected_first_date:
                raise BootstrapSourceVerificationError(
                    f"Metadata first_trade_date mismatch for {sym}: actual '{actual_first_date}' != manifest '{expected_first_date}'."
                )

            actual_last_date = lines[-1].split(",")[0].strip()
            expected_last_date = expected_meta.get("last_trade_date")
            if expected_last_date is not None and actual_last_date != expected_last_date:
                raise BootstrapSourceVerificationError(
                    f"Metadata last_trade_date mismatch for {sym}: actual '{actual_last_date}' != manifest '{expected_last_date}'."
                )

            manifest_sha256s[sym] = actual_sha
            file_metadata[sym] = expected_meta

        logger.info(
            "Successfully verified official bootstrap source at %s (commit=%s, 15 files verified).",
            resolved_source_root,
            actual_head,
        )

        return VerifiedBootstrapSource(
            repository=manifest_repo,
            commit=actual_head,
            source_root=resolved_source_root,
            raw_data_dir=resolved_raw_dir,
            manifest_sha256s=manifest_sha256s,
            file_metadata=file_metadata,
        )
