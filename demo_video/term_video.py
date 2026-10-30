#!/usr/bin/env python3
"""Render a terminal-style screen recording.

Every line shown is real captured output from the real tool. The frames are
painted with Pillow and piped to ffmpeg. The renderer prints the exact start
of every shot, so the description's timestamps are read off the render rather
than estimated.

    python3 demo_video/term_video.py <spec.json> <out.mp4>

A segment is either:

  {"kind": "title", "lines": [...], "subtitle": "...", "tagline": "...", "duration": 4}
  {"kind": "cmd",   "cmd": "$ ...", "file": "...", "ranges": [[start, end], ...],
                    "caption": "...", "hold": 0.5, "rest": 1.5}
  {"kind": "image", "file": "...png", "caption": "...", "duration": 4}

`ranges` are 1-based inclusive line ranges of the captured file; several ranges
in one segment are concatenated, which is how a shot shows two parts of a long
output without scrolling.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1600, 900
FPS = 24
FONT_PATH = "/System/Library/Fonts/Monaco.ttf"
FONT_SIZE = 19
LINE_H = 26
PAD_X = 46
TOP_BAR = 46
BOTTOM_BAR = 54

BG = (11, 15, 20)
PANEL = (18, 24, 33)
TEXT = (215, 224, 234)
DIM = (110, 123, 139)
ACCENT = (126, 231, 135)
CMD_C = (121, 192, 255)
RED = (255, 123, 114)
BORDER = (33, 41, 52)
WINDOW_TITLE = "why-agent — Nebius x NVIDIA"


def font(size: int = FONT_SIZE):
    return ImageFont.truetype(FONT_PATH, size)


def wrap_all(lines: list[str]) -> list[str]:
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    fnt = font()
    max_w = W - 2 * PAD_X
    out: list[str] = []
    for line in lines:
        if measure.textlength(line, font=fnt) <= max_w:
            out.append(line)
            continue
        indent = len(line) - len(line.lstrip(" "))
        pad = " " * indent
        words = line.split(" ")
        cur = ""
        for word in words:
            trial = word if not cur else cur + " " + word
            if measure.textlength(trial, font=fnt) <= max_w - indent:
                cur = trial
            else:
                if cur:
                    out.append(pad + cur)
                cur = word
        if cur:
            out.append(pad + cur)
    return out


def color_for(line: str) -> tuple:
    s = line.strip()
    if s.startswith("$ "):
        return CMD_C
    if "CHECK FAILED" in s or s.startswith("FAILED") or "FALSE APPROVAL" in s:
        return RED
    if "CHECK PASSED" in s or s == "OK" or s.startswith("GATE: PASS"):
        return ACCENT
    if s.startswith("#") or s.startswith("===") or s.startswith("---"):
        return (255, 255, 255)
    if s.startswith("CASE") or s.startswith("NEBIUS"):
        return (242, 204, 96)
    return TEXT


def chrome(img: Image.Image, caption: str) -> Image.Image:
    """The window bar and the caption bar, drawn on top of the content."""
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, TOP_BAR], fill=PANEL)
    d.line([(0, TOP_BAR), (W, TOP_BAR)], fill=BORDER, width=1)
    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = 26 + i * 20
        d.ellipse([cx - 6, TOP_BAR // 2 - 6, cx + 6, TOP_BAR // 2 + 6], fill=color)
    w = d.textlength(WINDOW_TITLE, font=font(17))
    d.text(((W - w) / 2, 13), WINDOW_TITLE, font=font(17), fill=DIM)
    if caption:
        d.rectangle([0, H - BOTTOM_BAR, W, H], fill=PANEL)
        d.line([(0, H - BOTTOM_BAR), (W, H - BOTTOM_BAR)], fill=BORDER, width=1)
        d.text((PAD_X, H - BOTTOM_BAR + 17), caption, font=font(17), fill=DIM)
    return img


def render_frame(lines, typed_cmd, cmd_visible, caption, cursor):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    fnt = font()
    y = TOP_BAR + 22
    if cmd_visible:
        d.text((PAD_X, y), typed_cmd, font=fnt, fill=CMD_C)
        if cursor:
            w = d.textlength(typed_cmd, font=fnt)
            d.rectangle([PAD_X + w + 2, y + 4, PAD_X + w + 11, y + FONT_SIZE + 2], fill=ACCENT)
        y += LINE_H + 6
    for line in lines:
        if y > H - BOTTOM_BAR - LINE_H:
            break
        d.text((PAD_X, y), line, font=fnt, fill=color_for(line))
        y += LINE_H
    return chrome(img, caption)


def title_card(lines, subtitle, tagline):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    big, mid, small = font(52), font(24), font(18)
    y = H // 2 - len(lines) * 44 - 70
    for i, line in enumerate(lines):
        w = d.textlength(line, font=big)
        d.text(((W - w) / 2, y), line, font=big, fill=ACCENT if i == 0 else TEXT)
        y += 74
    w = d.textlength(subtitle, font=mid)
    d.text(((W - w) / 2, y + 8), subtitle, font=mid, fill=DIM)
    w = d.textlength(tagline, font=small)
    d.text(((W - w) / 2, H - 110), tagline, font=small, fill=(88, 100, 116))
    return img


def image_frame(path: str, caption: str):
    """A browser screenshot, scaled to fit the frame."""
    shot = Image.open(path).convert("RGB")
    max_w = W - 40
    max_h = H - TOP_BAR - BOTTOM_BAR - 20
    scale = min(max_w / shot.width, max_h / shot.height)
    shot = shot.resize((max(1, int(shot.width * scale)), max(1, int(shot.height * scale))),
                        Image.LANCZOS)
    img = Image.new("RGB", (W, H), BG)
    img.paste(shot, ((W - shot.width) // 2, TOP_BAR + 10))
    return chrome(img, caption)


def main() -> int:
    spec = json.loads(Path(sys.argv[1]).read_text())
    out = sys.argv[2]
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset",
           "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    frame = [0]
    timeline = []

    def send(img):
        proc.stdin.write(img.tobytes())
        frame[0] += 1

    def hold(seconds, maker):
        for _ in range(max(1, int(seconds * FPS))):
            send(maker())

    for seg in spec["segments"]:
        label = (seg.get("cmd") or seg.get("lines", ["title"])[0])[:58]
        timeline.append((label, frame[0]))
        if seg["kind"] == "title":
            hold(seg.get("duration", 4), lambda s=seg: title_card(
                s["lines"], s.get("subtitle", ""), s.get("tagline", "")))
            continue
        if seg["kind"] == "image":
            path = seg["file"]
            caption = seg.get("caption", "")
            hold(seg.get("duration", 4), lambda p=path, c=caption: image_frame(p, c))
            continue
        text = Path(seg["file"]).read_text().splitlines()
        body = []
        for start, end in seg["ranges"]:
            # Ranges are 1-based and inclusive; the slice is 0-based.
            body.extend(text[start - 1:end])
        body = wrap_all(body)
        cmdtext = seg["cmd"]
        caption = seg.get("caption", "")
        hold_per_line = seg.get("hold", 0.5)
        n = max(1, int(len(cmdtext) * seg.get("type_time", 0.016) * FPS))
        for i in range(n):
            frac = (i + 1) / n
            send(render_frame([], cmdtext[:max(1, int(len(cmdtext) * frac))], True, caption, True))
        for count in range(1, len(body) + 1):
            for _ in range(max(1, int(hold_per_line * FPS))):
                send(render_frame(body[:count], cmdtext, True, caption, False))
        hold(seg.get("rest", 1.5), lambda: render_frame(body, cmdtext, True, caption, False))

    proc.stdin.close()
    proc.wait()
    print(f"wrote {out}")
    print("  MEASURED segment timings (frame-accurate):")
    for i, (label, start) in enumerate(timeline):
        end = timeline[i + 1][1] if i + 1 < len(timeline) else frame[0]
        print(f"    {start / FPS:6.2f}s -> {end / FPS:6.2f}s   {label}")
    print(f"  total: {frame[0] / FPS:.2f}s")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
