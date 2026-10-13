#!/usr/bin/env python3
"""Fail-closed, manifest-verified application and static release activation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path, PurePosixPath
import grp

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
FILE_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
MANIFEST_NAME = "release-manifest.json"
DEMO_SENTINELS = (b"DEMO DATA: Architectural stub projections", b"demo-init-run-0001")
GENERATED_BACKEND_DIRS = {"backend/.venv-api", "backend/.venv-inference"}


def _is_generated_backend_path(relative: str) -> bool:
    return any(relative == prefix or relative.startswith(prefix + "/") for prefix in GENERATED_BACKEND_DIRS)


class ReleaseError(RuntimeError):
    """Raised when a release fails provenance or safety validation."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(raw: object) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise ReleaseError("Manifest contains an empty or invalid file path.")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ReleaseError("Manifest contains an unsafe relative path.")
    return path


def verify_release(root: Path, *, expected_commit: str, expected_type: str) -> dict:
    """Verify every file, reject links/extras, and require the exact release SHA."""
    if not SHA_RE.fullmatch(expected_commit):
        raise ReleaseError("Release identifier must be a full lowercase Git SHA-1.")
    root = Path(root)
    if root.is_symlink():
        raise ReleaseError("Release root must not be a symbolic link.")
    try:
        root = root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ReleaseError("Release root is missing.") from exc
    if not root.is_dir():
        raise ReleaseError("Release root must be a real directory.")
    manifest_path = root / MANIFEST_NAME
    if manifest_path.is_symlink():
        raise ReleaseError("Release manifest must not be a symbolic link.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError("Release manifest is missing or invalid JSON.") from exc
    if manifest.get("commit_sha") != expected_commit:
        raise ReleaseError("Release manifest commit does not match the requested release.")
    if manifest.get("artifact_type") != expected_type:
        raise ReleaseError("Release manifest has the wrong artifact type.")
    if expected_type == "frontend" and manifest.get("demo_mode") is not False:
        raise ReleaseError("Frontend manifest must explicitly record demo_mode=false.")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ReleaseError("Release manifest must list at least one file.")

    expected_paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ReleaseError("Release manifest file entry must be an object.")
        relative = _safe_relative(entry.get("path"))
        relative_text = relative.as_posix()
        if relative_text == MANIFEST_NAME or relative_text in expected_paths:
            raise ReleaseError("Release manifest contains a duplicate or reserved path.")
        expected_paths.add(relative_text)
        expected_sha = entry.get("sha256")
        if not isinstance(expected_sha, str) or not FILE_SHA_RE.fullmatch(expected_sha):
            raise ReleaseError("Release manifest contains an invalid file SHA-256.")
        candidate = root.joinpath(*relative.parts)
        if candidate.is_symlink() or not candidate.is_file():
            raise ReleaseError("Release contains a missing, non-regular, or linked file.")
        if candidate.stat().st_mode & 0o022:
            raise ReleaseError("Release contains a group- or world-writable file.")
        if sha256_file(candidate) != expected_sha:
            raise ReleaseError(f"Release file hash mismatch: {relative_text}")
        if expected_type == "frontend":
            try:
                data = candidate.read_bytes()
            except OSError as exc:
                raise ReleaseError("Unable to read a frontend release asset.") from exc
            if any(sentinel in data for sentinel in DEMO_SENTINELS):
                raise ReleaseError("Frontend release contains known demo fixture content.")

    actual_paths: set[str] = set()
    for candidate in root.rglob("*"):
        relative = candidate.relative_to(root).as_posix()
        if _is_generated_backend_path(relative):
            if candidate.is_dir() and not candidate.is_symlink() and candidate.stat().st_mode & 0o022:
                raise ReleaseError("Generated backend environment has writable group or other permissions.")
            if candidate.is_file() and not candidate.is_symlink() and candidate.stat().st_mode & 0o022:
                raise ReleaseError("Generated backend environment has writable group or other permissions.")
            continue
        if candidate.is_symlink():
            raise ReleaseError("Release trees may not contain symbolic links.")
        if candidate.is_dir() and candidate.stat().st_mode & 0o022:
            raise ReleaseError("Release contains a group- or world-writable directory.")
        if candidate.is_file() and candidate.name != MANIFEST_NAME:
            actual_paths.add(candidate.relative_to(root).as_posix())
    if actual_paths != expected_paths:
        raise ReleaseError("Release tree contains missing or unmanifested files.")
    if expected_type == "frontend":
        if "index.html" not in expected_paths:
            raise ReleaseError("Static export is missing index.html.")
        if not any(path.startswith("_next/static/") for path in expected_paths):
            raise ReleaseError("Static export is missing Next.js static assets.")
    return manifest


def create_manifest(root: Path, commit_sha: str, artifact_type: str, demo_mode: bool) -> Path:
    """Create a content manifest for a finished, offline-built artifact tree."""
    if not SHA_RE.fullmatch(commit_sha):
        raise ReleaseError("A full lowercase Git SHA-1 is required.")
    if artifact_type not in {"backend", "frontend"}:
        raise ReleaseError("artifact_type must be backend or frontend.")
    if artifact_type == "frontend" and demo_mode:
        raise ReleaseError("Production frontend artifacts must be built with demo mode disabled.")
    root = root.resolve(strict=True)
    files = []
    for path in sorted(root.rglob("*")):
        if _is_generated_backend_path(path.relative_to(root).as_posix()):
            continue
        if path.is_symlink():
            raise ReleaseError("Artifact source contains a symbolic link.")
        if path.is_file() and path.name != MANIFEST_NAME:
            files.append({"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)})
    if not files:
        raise ReleaseError("Artifact tree is empty.")
    manifest = {
        "schema_version": 1,
        "artifact_type": artifact_type,
        "commit_sha": commit_sha,
        "demo_mode": False if artifact_type == "frontend" else None,
        "files": files,
    }
    destination = root / MANIFEST_NAME
    temporary = root / f".{MANIFEST_NAME}.tmp"
    temporary.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def _atomic_symlink(target: Path, link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    temp_link = link.parent / f".{link.name}.{os.getpid()}.new"
    try:
        temp_link.symlink_to(target)
        os.replace(temp_link, link)
    finally:
        temp_link.unlink(missing_ok=True)


def _verify_target_ownership(root: Path, group_name: str) -> None:
    try:
        group_id = grp.getgrnam(group_name).gr_gid
    except KeyError as exc:
        raise ReleaseError(f"Required service group is missing: {group_name}.") from exc
    for path in [root, *root.rglob("*")]:
        if _is_generated_backend_path(path.relative_to(root).as_posix()):
            continue
        info = path.lstat()
        if info.st_uid != 0 or info.st_gid != group_id:
            raise ReleaseError("Release ownership does not match root and the approved service group.")
        if info.st_mode & 0o022:
            raise ReleaseError("Release is writable by its service group or other users.")


def _verify_backend_environments(root: Path) -> None:
    """Require root-owned, non-writable production API and inference venvs."""
    try:
        group_id = grp.getgrnam("psepulse").gr_gid
    except KeyError as exc:
        raise ReleaseError("Required service group is missing: psepulse.") from exc
    for relative in ("backend/.venv-api", "backend/.venv-inference"):
        environment = root / relative
        if environment.is_symlink() or not environment.is_dir():
            raise ReleaseError("Backend release is missing a real API or inference virtual environment.")
        python = environment / "bin/python"
        if not python.is_file() or not os.access(python, os.X_OK):
            raise ReleaseError("Backend virtual environment has no executable Python interpreter.")
        for path in [environment, *environment.rglob("*")]:
            info = path.lstat()
            if path.is_symlink():
                if info.st_uid != 0:
                    raise ReleaseError("Backend environment symbolic links must be root-owned.")
                try:
                    resolved = path.resolve(strict=True)
                except FileNotFoundError as exc:
                    raise ReleaseError("Backend environment contains a broken symbolic link.") from exc
                if not resolved.is_relative_to(environment.resolve(strict=True)):
                    # Python virtualenvs may link their interpreter to the OS Python.
                    if path.name not in {"python", "python3", "python3.12"} or not resolved.is_relative_to(Path("/usr/bin")):
                        raise ReleaseError("Backend environment contains an unapproved external symbolic link.")
                continue
            if info.st_uid != 0 or info.st_gid != group_id:
                raise ReleaseError("Backend environment ownership does not match root:psepulse.")
            if info.st_mode & 0o022:
                raise ReleaseError("Backend environment is writable by its service group or other users.")


def activate_existing(root: Path, commit_sha: str, artifact_type: str) -> Path:
    """Atomically switch `root/current` only after full tree verification."""
    root = root.resolve()
    releases = root / "releases"
    release = releases / commit_sha
    current = root / "current"
    previous = root / "previous"
    verify_release(release, expected_commit=commit_sha, expected_type=artifact_type)
    _verify_target_ownership(release, "psepulse" if artifact_type == "backend" else "www-data")
    if artifact_type == "backend":
        _verify_backend_environments(release)
    if current.exists() and not current.is_symlink():
        raise ReleaseError("Current release path exists and is not a symbolic link.")
    if current.is_symlink():
        old_target = current.resolve(strict=True)
        if old_target.parent != releases.resolve(strict=True):
            raise ReleaseError("Current release points outside the managed release directory.")
        _atomic_symlink(old_target, previous)
    _atomic_symlink(release, current)
    _prune_releases(releases, {release.resolve(), previous.resolve() if previous.is_symlink() else release.resolve()})
    return current


def deploy_static(source: Path, root: Path, commit_sha: str) -> Path:
    """Copy a verified prebuilt export, then atomically activate it."""
    source = source.resolve(strict=True)
    verify_release(source, expected_commit=commit_sha, expected_type="frontend")
    root = root.resolve()
    releases = root / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    destination = releases / commit_sha
    if destination.exists():
        verify_release(destination, expected_commit=commit_sha, expected_type="frontend")
    else:
        staging = releases / f".stage-{commit_sha}-{os.getpid()}"
        try:
            shutil.copytree(source, staging, symlinks=False)
            for path in staging.rglob("*"):
                if path.is_dir():
                    path.chmod(0o750)
                elif path.is_file():
                    path.chmod(0o640)
                os.chown(path, 0, grp.getgrnam("www-data").gr_gid)
            staging.chmod(0o750)
            os.chown(staging, 0, grp.getgrnam("www-data").gr_gid)
            verify_release(staging, expected_commit=commit_sha, expected_type="frontend")
            os.replace(staging, destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return activate_existing(root, commit_sha, "frontend")


def rollback(root: Path, artifact_type: str) -> Path:
    """Atomically activate the verified previous release."""
    root = root.resolve()
    current = root / "current"
    previous = root / "previous"
    if not previous.is_symlink():
        raise ReleaseError("No previous release is available for rollback.")
    next_target = previous.resolve(strict=True)
    releases = (root / "releases").resolve(strict=True)
    if next_target.parent != releases:
        raise ReleaseError("Previous release points outside the managed release directory.")
    manifest = json.loads((next_target / MANIFEST_NAME).read_text(encoding="utf-8"))
    commit_sha = manifest.get("commit_sha")
    verify_release(next_target, expected_commit=commit_sha, expected_type=artifact_type)
    _verify_target_ownership(next_target, "psepulse" if artifact_type == "backend" else "www-data")
    if artifact_type == "backend":
        _verify_backend_environments(next_target)
    if current.is_symlink():
        old = current.resolve(strict=True)
        _atomic_symlink(old, previous)
    _atomic_symlink(next_target, current)
    return current


def _prune_releases(releases: Path, protected: set[Path], keep: int = 3) -> None:
    candidates = [p for p in releases.iterdir() if p.is_dir() and not p.is_symlink() and not p.name.startswith(".stage-")]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    retained = set(protected)
    for path in candidates:
        if len(retained) >= keep:
            break
        retained.add(path.resolve())
    for path in candidates:
        if path.resolve() not in retained:
            shutil.rmtree(path)


def _require_root() -> None:
    if os.geteuid() != 0:
        raise ReleaseError("Release activation requires root ownership checks and must run through an approved management channel.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    manifest_parser = sub.add_parser("create-manifest")
    manifest_parser.add_argument("tree", type=Path)
    manifest_parser.add_argument("--commit", required=True)
    manifest_parser.add_argument("--type", choices=("backend", "frontend"), required=True)
    manifest_parser.add_argument("--demo-mode", choices=("true", "false"), default="false")
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("tree", type=Path)
    verify_parser.add_argument("--commit", required=True)
    verify_parser.add_argument("--type", choices=("backend", "frontend"), required=True)
    activate_parser = sub.add_parser("activate")
    activate_parser.add_argument("root", type=Path)
    activate_parser.add_argument("--commit", required=True)
    activate_parser.add_argument("--type", choices=("backend", "frontend"), required=True)
    deploy_parser = sub.add_parser("deploy-static")
    deploy_parser.add_argument("artifact", type=Path)
    deploy_parser.add_argument("root", type=Path)
    deploy_parser.add_argument("--commit", required=True)
    rollback_parser = sub.add_parser("rollback")
    rollback_parser.add_argument("root", type=Path)
    rollback_parser.add_argument("--type", choices=("backend", "frontend"), required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create-manifest":
            path = create_manifest(args.tree, args.commit, args.type, args.demo_mode == "true")
            print(f"manifest created: {path.name}")
        elif args.command == "verify":
            verify_release(args.tree, expected_commit=args.commit, expected_type=args.type)
            print("release manifest and file hashes: verified")
        else:
            _require_root()
            if args.command == "activate":
                path = activate_existing(args.root, args.commit, args.type)
            elif args.command == "deploy-static":
                path = deploy_static(args.artifact, args.root, args.commit)
            else:
                path = rollback(args.root, args.type)
            print(f"active release switched: {path}")
        return 0
    except (ReleaseError, OSError, ValueError) as exc:
        print(f"release operation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
