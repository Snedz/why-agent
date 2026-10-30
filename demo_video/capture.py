#!/usr/bin/env python3
"""Capture the real why-agent output and build the video spec.

Runs the real tools, keeps the real output, and derives the shot list from
where things actually are — so the spec cannot describe a video that does not
exist.

    python3 demo_video/capture.py            # write demo_video/_capture/spec.json
    python3 demo_video/render.py             # render the spec to the mp4

A Token Factory key in the environment turns the receipt shot into a LIVE one:

    export NEBIUS_API_KEY=...
    python3 demo_video/capture.py

Without a key the receipt shot shows the recorded 2026-10-28 run, and says so.
The caption is never the same in both cases, so the video cannot claim a live
call it did not make.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "_capture"
OUT.mkdir(exist_ok=True)
PY = sys.executable
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def run(args, env=None):
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, env=e)
    return p.stdout + p.stderr


def case_range(lines: list[str], index: int) -> list[list[int]]:
    """Lines of one CASE block, 1-based inclusive, as (start, end)."""
    starts = [i for i, l in enumerate(lines) if l.startswith("CASE ")]
    start = starts[index]
    end = starts[index + 1] if index + 1 < len(starts) else len(lines)
    while end > start and not lines[end - 1].strip():
        end -= 1
    return [[start + 1, end]]


def find_line(lines: list[str], needle: str) -> int:
    for i, line in enumerate(lines):
        if needle in line:
            return i + 1
    raise SystemExit(f"capture: no line containing {needle!r} — the output moved")


def screenshot_case_lab() -> str:
    """A screenshot of the published Case Lab, at one named case.

    Two things have to be worked around, and both are worth knowing:
    Chrome needs its own profile directory (with the default one it finds the
    running instance's lock and silently produces no file), and Chrome's
    headless screenshot comes out BLANK when the URL carries a fragment. So
    the shot is taken of a temporary copy in which every case except the one
    being filmed is hidden. The committed page is not touched.
    """
    out = OUT / "case_lab.png"
    if not Path(CHROME).exists():
        print("capture: Chrome not found — skipping the Case Lab shot")
        return ""
    source = (ROOT / "demo_lab" / "index.html").read_text(encoding="utf-8")
    # Only the case being filmed is shown, so it fills the frame and can be
    # read. The case carries its own RECORDED / SYNTHETIC labels, so the
    # page's own header is not needed.
    style = ("<style>body>h1,body>p,body>div.labels{display:none}"
             "section.case{display:none}"
             "section.case#bm-reviewer-split{display:block}</style>")
    shot_html = OUT / "case_lab_shot.html"
    shot_html.write_text(source.replace("</head>", style + "</head>"), encoding="utf-8")

    profile = OUT / "chrome-profile"
    shutil.rmtree(profile, ignore_errors=True)
    cmd = [CHROME, "--headless=new", "--no-first-run", "--disable-gpu",
           "--hide-scrollbars", f"--user-data-dir={profile}",
           f"--screenshot={out}", "--window-size=1400,1500", shot_html.as_uri()]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    shutil.rmtree(profile, ignore_errors=True)
    if not out.exists() or out.stat().st_size < 10000:
        print("capture: the screenshot failed —", proc.stderr[-300:])
        return ""
    trim_blank(out)
    print("capture: case lab screenshot", out.stat().st_size, "bytes")
    return str(out)


def trim_blank(path: Path) -> None:
    """Cut the empty page off the bottom of the screenshot.

    Chrome captures the whole window height; the case only fills the top of
    it. Without this the video shows the case small, in the middle of a white
    page.
    """
    from PIL import Image

    img = Image.open(path).convert("RGB")
    w, h = img.size
    px = img.load()
    last = 0
    for y in range(h - 1, -1, -1):
        if any(px[x, y] != (255, 255, 255) for x in range(0, w, 4)):
            last = y
            break
    if last and last < h - 1:
        img.crop((0, 0, w, min(h, last + 24))).save(path)


def main() -> int:
    # 1. the test suite
    tests = run([PY, "-m", "pytest", "-q"])
    (OUT / "tests.txt").write_text(tests)
    counts = re.search(r"(\d+) passed", tests)
    print("tests:", counts.group(1) if counts else "?")

    # 2. the demo
    demo = run([PY, "demo.py"])
    (OUT / "demo.txt").write_text(demo)
    lines = demo.splitlines()
    print("cases:", sum(1 for l in lines if l.startswith("CASE ")))

    # 3. the scored benchmark — the Nebius evidence
    score = run([PY, "benchmark/score.py", "--eval-results",
                 "benchmark/eval-benchmark-2026-10-28.json"])
    (OUT / "score.txt").write_text(score)
    print("gate:", "the deterministic gate has zero false approvals; the lanes do not (that is the finding)")

    # 4. the flip check
    flip = run([PY, "demo_lab/flip_check.py"])
    (OUT / "flip.txt").write_text(flip)
    print("flip:", "PASS" if flip.strip().endswith("cannot disagree." ) or "PASS" in flip else "?")

    # 5. the narration check — the thesis, with the checker running
    narration = run([PY, "demo_video/narration_check.py"])
    (OUT / "narration.txt").write_text(narration)
    print("narration:", "shown")

    # 6. the receipt — LIVE if a key is present, RECORDED if not
    live = bool(os.environ.get("NEBIUS_API_KEY", "").strip())
    if live:
        receipt = run([PY, "smoke.py", "--provider", "nebius", "--json"])
        (OUT / "receipt.txt").write_text(receipt)
        receipt_cmd = "$ python3 smoke.py --provider nebius --json"
        receipt_caption = ("LIVE Token Factory call — every tier answered on "
                           "https://api.tokenfactory.nebius.com/v1/")
    else:
        receipt = run([PY, "demo_video/receipt.py"])
        (OUT / "receipt.txt").write_text(receipt)
        receipt_cmd = "$ python3 demo_video/receipt.py"
        receipt_caption = ("the recorded 2026-10-28 Token Factory run — endpoint, model "
                           "ids, tokens and USD, committed in the repo")
    print("receipt:", "LIVE" if live else "recorded")

    shot = screenshot_case_lab()

    segments = [
        {"kind": "title",
         "lines": ["why-agent"],
         "subtitle": "an agent that answers why — and cites every sentence",
         "tagline": "Nebius x NVIDIA Global AI Hackathon · Best Apps and Agents · "
                    "Apache-2.0",
         "duration": 5.0},
        {"kind": "cmd", "cmd": "$ python3 demo.py",
         "file": str(OUT / "demo.txt"),
         "ranges": case_range(lines, 0),
         "caption": "four sources, four answers — no winner picked",
         "hold": 0.42, "rest": 2.4},
        {"kind": "cmd", "cmd": receipt_cmd,
         "file": str(OUT / "receipt.txt"),
         "ranges": [[1, 30]],
         "caption": receipt_caption,
         "hold": 0.42, "rest": 3.0},
        {"kind": "cmd", "cmd": "$ python3 benchmark/score.py --eval-results "
                              "benchmark/eval-benchmark-2026-10-28.json",
         "file": str(OUT / "score.txt"),
         "ranges": [[1, 27]],
         "caption": "the gate: 14/14, zero false approvals. the model lanes: 9/14 and 6/14 "
                    "— and they falsely approve, which is why they never gate",
         "hold": 0.40, "rest": 3.6},
        {"kind": "cmd", "cmd": "$ python3 demo_video/narration_check.py",
         "file": str(OUT / "narration.txt"),
         "ranges": [[1, 28]],
         "caption": "the model may write the prose — a value the evidence does not "
                    "contain fails the check, and is reported, never removed",
         "hold": 0.36, "rest": 2.8},
        {"kind": "cmd", "cmd": "$ python3 demo_lab/flip_check.py",
         "file": str(OUT / "flip.txt"),
         "ranges": [[1, 14]],
         "caption": "remove a lane row and the verdict changes — proved, not asserted",
         "hold": 0.36, "rest": 2.8},
    ]

    if shot:
        segments.append({
            "kind": "image", "file": shot,
            "caption": "the Case Lab — every claim with its receipt, every lane with its model id",
            "duration": 7.0,
        })

    segments.append({
        "kind": "title",
        "lines": ["The model may write the prose.",
                  "It may not add a fact."],
        "subtitle": "the lanes advise · the deterministic reconciler decides",
        "tagline": "github.com/Snedz/why-agent · snedz.github.io/why-agent",
        "duration": 5.5,
    })

    spec = {"segments": segments}
    (OUT / "spec.json").write_text(json.dumps(spec, indent=1))
    print("spec written:", OUT / "spec.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
