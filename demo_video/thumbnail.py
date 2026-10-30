#!/usr/bin/env python3
"""Draw the YouTube thumbnail.

The thumbnail is the first thing a judge sees of the video, so it carries the
same claim as the title card, at a size where it can actually be read.

    python3 demo_video/thumbnail.py
    -> why-agent-nebius-thumbnail.png  (1280x720)

It is drawn, not cropped out of the video: the video's own title card is
sparse, and at 1280x720 a judge scrolling a gallery reads three words, not a
line of 12 px type.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "why-agent-nebius-thumbnail.png"

W, H = 1280, 720
BG = (11, 15, 20)
GREEN = (126, 231, 135)
WHITE = (215, 224, 234)
DIM = (138, 151, 166)
BLUE = (121, 192, 255)

# MEASURED 2026-10-30: this script ran on a CI runner and failed, because
# /System/Library/Fonts/Monaco.ttf is macOS-only. The list below is ordered by
# preference, so the same command draws the thumbnail wherever it is run. The
# rasterisation differs between platforms -- an image is an artefact, not code
# -- so CI checks the committed thumbnail rather than redrawing it.
FONTS = [
    ("/System/Library/Fonts/Monaco Bold.ttf", "/System/Library/Fonts/Monaco.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf"),
]


def font(size: int, bold: bool = False):
    for bold_path, regular_path in FONTS:
        path = bold_path if bold and Path(bold_path).exists() else regular_path
        if not Path(path).exists():
            continue
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    raise SystemExit("no usable monospace font found -- the thumbnail cannot be drawn")


def main() -> int:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # a hairline of the same green the title card uses, so the thumbnail and
    # the video read as one artefact
    d.rectangle([0, 0, W, 10], fill=GREEN)

    d.text((70, 150), "why-agent", font=font(96, bold=True), fill=GREEN)
    d.text((70, 280), "an agent that answers why —", font=font(42), fill=WHITE)
    d.text((70, 336), "and cites every sentence", font=font(42), fill=WHITE)

    d.text((70, 470), "Runs on Nebius Token Factory with NVIDIA Nemotron 3",
           font=font(28), fill=DIM)
    d.text((70, 512), "The model may write the prose. It may not add a fact.",
           font=font(28), fill=DIM)

    d.rectangle([70, 600, 1210, 660], outline=(33, 41, 52), width=2)
    small = font(26)
    d.text((92, 615), "Nebius × NVIDIA Global AI Hackathon", font=small, fill=BLUE)
    x = 92 + d.textlength("Nebius × NVIDIA Global AI Hackathon  ·  ", font=small)
    d.text((x, 615), "Best Apps and Agents", font=small, fill=BLUE)
    lic = font(24)
    d.text((1210 - d.textlength("Apache-2.0", font=lic) - 22, 617), "Apache-2.0",
           font=lic, fill=DIM)

    img.save(OUT)
    print(f"wrote {OUT.name} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
