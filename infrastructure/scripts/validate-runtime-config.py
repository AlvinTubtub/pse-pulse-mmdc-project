#!/usr/bin/env python3
"""Root-run permission gate for the API environment file before activation."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import sys

API_ENV = Path("/etc/pse-pulse/api.env")


def validate_api_env_metadata(directory_info, file_info, effective_uid: int) -> None:
    if effective_uid != 0:
        raise RuntimeError("Runtime configuration validation must run as root.")
    if (not stat.S_ISDIR(directory_info.st_mode)
            or directory_info.st_uid != 0
            or directory_info.st_gid != 0
            or stat.S_IMODE(directory_info.st_mode) != 0o750):
        raise RuntimeError("API configuration directory ownership or permissions are unsafe.")
    if (not stat.S_ISREG(file_info.st_mode)
            or file_info.st_uid != 0
            or file_info.st_gid != 0
            or stat.S_IMODE(file_info.st_mode) != 0o600):
        raise RuntimeError("API environment file ownership or permissions are unsafe.")


def validate_api_env_file(path: Path = API_ENV) -> None:
    if path != API_ENV:
        raise RuntimeError("Only the fixed API environment path is permitted.")
    directory_info = path.parent.lstat()
    file_info = path.lstat()
    validate_api_env_metadata(directory_info, file_info, os.geteuid())


def main() -> int:
    try:
        validate_api_env_file()
    except Exception as exc:
        print(f"API environment permission check failed: {exc}", file=sys.stderr)
        return 1
    print("API environment ownership and permissions verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
