#!/usr/bin/env python3
"""Render the captured spec into the submission video.

    python3 demo_video/render.py [out.mp4]

The default output is `why-agent-nebius-demo.mp4` at the repository root, which
is what the Pages workflow publishes. The rules ask for less than three
minutes; the renderer prints the measured length, so the check is a reading and
not an estimate.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SPEC = HERE / "_capture" / "spec.json"
DEFAULT_OUT = ROOT / "why-agent-nebius-demo.mp4"


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    if not SPEC.exists():
        print("run demo_video/capture.py first", file=sys.stderr)
        return 1
    proc = subprocess.run([sys.executable, str(HERE / "term_video.py"), str(SPEC), str(out)])
    if proc.returncode:
        return proc.returncode
    length = probe(out)
    if length is None:
        return 0
    print(f"  length: {length:.2f}s")
    if length >= 180:
        print(f"  TOO LONG — the rules ask for less than three minutes ({length:.2f}s)")
        return 1
    print(f"  OK — under the three-minute limit ({length:.2f}s)")
    return 0


def probe(path: Path) -> float | None:
    """The measured duration, in seconds."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True).stdout.strip()
        return float(out) if out else None
    except (OSError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
