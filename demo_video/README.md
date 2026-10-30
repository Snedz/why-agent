# The submission video

`why-agent-nebius-demo.mp4` at the repository root is the entry's demo video —
87.54 seconds, measured at render time, under the three-minute limit the rules
ask for.

It is **generated**, not edited by hand. Every frame is real captured output
from a real tool run:

| Shot | What it shows |
|---|---|
| `python3 demo.py` | the conflicted work item — four sources, four answers, no winner picked |
| `python3 demo_video/receipt.py` | the Token Factory receipt: endpoint, pinned model ids, token counts, USD |
| `python3 benchmark/score.py --eval-results …` | the gate 14/14 with zero false approvals, the lanes 9/14 and 6/14 |
| `python3 demo_video/narration_check.py` | the recorded narration checks, and the checker running on two fixtures |
| `python3 demo_lab/flip_check.py` | the two cases that demonstrably change verdict when their lane rows are removed |
| the Case Lab | the published page, at the lane-dependent case, with model ids and costs |

## Re-render it

```
python3 demo_video/capture.py     # runs the tools, captures the output, shoots the page
python3 demo_video/render.py      # paints the frames and writes the mp4
```

`render.py` prints the measured duration and **fails** if the video reaches
three minutes. The timings it prints are read off the rendered frames, so the
shot list in `SUBMISSION.md` is a measurement rather than an estimate.

## A live Token Factory call

Put a key in the environment and the receipt shot becomes a live call:

```
export NEBIUS_API_KEY=...
python3 demo_video/capture.py && python3 demo_video/render.py
```

The caption changes with it — a live shot says "LIVE Token Factory call", a
recorded one says "the recorded 2026-10-28 Token Factory run". The video cannot
claim a live call it did not make, because the wording comes from the same
branch that chooses the shot.

## Two things worth knowing before you change this

- **Chrome's headless screenshot comes out blank when the URL has a
  fragment.** The Case Lab shot is taken of a temporary copy of the page in
  which every case except the one being filmed is hidden. The committed page is
  not touched.
- **Chrome needs its own profile directory.** With the default profile it finds
  the running instance's lock and silently writes no file at all — no error, no
  image.

Both are worked around in `capture.py`, and both are worth a comment if you
touch it, because each one fails quietly.

## What is not in the video

- No third-party trademarks and no copyrighted music. The case files use
  `synthetic://` locators, and the video is silent.
- No personal name and no credential.
- The work items are synthetic; the lanes ran against real models.
