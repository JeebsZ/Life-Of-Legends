"""Encode the shipped WAVs to OGG Vorbis for the Android APK (smaller), with ffmpeg.

    .venv/Scripts/python tools/sfx/encode_ogg.py           # changed files only
    .venv/Scripts/python tools/sfx/encode_ogg.py --all     # re-encode everything

src/assets/sfx/*.wav   -> src/assets/ogg/sfx/*.ogg
src/assets/voice/*.wav -> src/assets/ogg/voice/*.ogg
Stale OGGs (their WAV is gone) are removed. The notification sounds (ogg/sfx/notify_0*.ogg)
are also copied to the flet_lumen_notify Android module's res/raw, where phone notifications
play them (one channel per sound). PC / desktop runs keep playing the WAVs; on Android
sfx.py / audio.py load /ogg/... and the APK excludes assets/sfx and assets/voice (see
tools/sfx/README.md "APK: OGG").

ffmpeg with libvorbis is needed and nothing is installed by this script. It looks at
$LOL_FFMPEG, then PATH, then KNOWN (ffmpeg builds already on this PC). Encoding: libvorbis,
mono, -q:a 4 (~80 kbps mono, transparent for UI sounds and speech).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "src" / "assets"
JOBS = (("sfx", "ogg/sfx"), ("voice", "ogg/voice"))
KNOWN = (
    r"C:\Program Files (x86)\Steam\steamapps\common\Once Human\ffmpeg.exe",
)
QUALITY = "4"
RAW = (ROOT / "extensions" / "flet_lumen_notify" / "src" / "flutter" / "flet_lumen_notify"
       / "android" / "src" / "main" / "res" / "raw")


def find_ffmpeg() -> str | None:
    for cand in (os.environ.get("LOL_FFMPEG"), shutil.which("ffmpeg"), *KNOWN):
        if cand and Path(cand).is_file() and _has_vorbis(cand):
            return cand
    return None


def _has_vorbis(exe: str) -> bool:
    try:
        out = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True,
                             check=False, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return " libvorbis " in out


def main(argv: list[str]) -> int:
    exe = find_ffmpeg()
    if exe is None:
        print("No ffmpeg with libvorbis found (set LOL_FFMPEG). Nothing encoded.")
        return 1
    force = "--all" in argv
    total_wav = total_ogg = n = 0
    for src_dir, dst_dir in JOBS:
        src, dst = ASSETS / src_dir, ASSETS / dst_dir
        dst.mkdir(parents=True, exist_ok=True)
        wavs = sorted(src.glob("*.wav"))
        for old in dst.glob("*.ogg"):
            if not (src / f"{old.stem}.wav").exists():
                old.unlink()
        for wav in wavs:
            ogg = dst / f"{wav.stem}.ogg"
            if force or not ogg.exists() or ogg.stat().st_mtime < wav.stat().st_mtime:
                subprocess.run([exe, "-nostdin", "-y", "-loglevel", "error", "-i", str(wav),
                                "-ac", "1", "-c:a", "libvorbis", "-q:a", QUALITY,
                                "-map_metadata", "-1", str(ogg)], check=True)
                n += 1
            total_wav += wav.stat().st_size
            total_ogg += ogg.stat().st_size
    RAW.mkdir(parents=True, exist_ok=True)
    for ogg in sorted((ASSETS / "ogg" / "sfx").glob("notify_0*.ogg")):
        shutil.copyfile(ogg, RAW / ogg.name)
    print(f"encoded {n} file(s) with {exe}")
    print(f"WAV {total_wav / 1024:.0f} KB -> OGG {total_ogg / 1024:.0f} KB (in the APK)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
