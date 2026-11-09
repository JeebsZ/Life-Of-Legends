"""Automated AAB release builder for Google Play Console.
- Auto-reads build_number and build_version from pyproject.toml
- Auto-injects release.jks signing credentials
- Keeps password secure via environment variable or default
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from flet.cli import main

ROOT_DIR = Path(__file__).resolve().parent

# --- 1. Keystore Configuration ---
KEYSTORE_PATH = ROOT_DIR / "release.jks"
KEY_ALIAS = "luma_key"
# Reads from environment variable if set, otherwise uses the password you set below:
KEYSTORE_PASSWORD = os.getenv("LUMA_KEYSTORE_PASSWORD", "m3DY@$!4u1")


def get_version_info() -> tuple[str, str]:
    """Parse build_number and build_version directly from pyproject.toml."""
    pyproject = (ROOT_DIR / "pyproject.toml").read_text(encoding="utf-8")
    num_match = re.search(r'build_number\s*=\s*(\d+)', pyproject)
    ver_match = re.search(r'build_version\s*=\s*"([^"]+)"', pyproject)
    build_num = num_match.group(1) if num_match else "18"
    build_ver = ver_match.group(1) if ver_match else "0.2.2"
    return build_num, build_ver


if __name__ == "__main__":
    build_num, build_ver = get_version_info()
    print(f"--> Building Google Play AAB: LUMA v{build_ver} (Build #{build_num})")

    cmd_args = [
        "flet",
        "build",
        "aab",
        "--bundle-id",
        "com.companions.LUMA",
        "--artifact",
        "LUMA",
        "--build-number",
        build_num,
        "--build-version",
        build_ver,
        "--android-signing-key-store",
        str(KEYSTORE_PATH),
        "--android-signing-key-store-password",
        KEYSTORE_PASSWORD,
        "--android-signing-key-password",
        KEYSTORE_PASSWORD,
        "--android-signing-key-alias",
        KEY_ALIAS,
    ]

    # Append any extra flags passed from command line (e.g. -v, --verbose)
    if len(sys.argv) > 1:
        cmd_args.extend(sys.argv[1:])

    sys.argv = cmd_args
    main()
