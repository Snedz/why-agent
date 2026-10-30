# RUN PACK — Claim Court lane (Nebius × NVIDIA, submit day Fri Oct 30, 2026)

Everything below runs from the worktree root. The build was done WITHOUT
provider keys on the machine, so tonight's surface renders **recorded**
results (the 2026-10-28 live Token Factory run) and **computed**
deterministic verdicts. The moment the keys land in the environment, the
live steps below replace the replayed ones — each step says what it
writes and how the surface picks it up. **Never invent a number: a claim
without a run behind it does not ship.**

## Env vars (names only — values via the founder's secure channel)

| Var | Used by | Effect without it |
|---|---|---|
| `NEBIUS_API_KEY` | steps 3, 4 (`court.py --live`, `batch_eval.py`) | live lanes refuse with a clean error; surface stays on recorded/computed data |
| `TAVILY_API_KEY` | step 5 (fresh evidence fetches) | optional tonight; recorded exhibits already in the corpora |

Provider endpoints/models resolve from `providers.py` (Token Factory:
`https://api.tokenfactory.nebius.com/v1/`; fast Nano 30B, standard Super
120B, deep Ultra 550B, vision Super VL). Pin a different model per tier
with `WHY_AGENT_NEBIUS_<TIER>_MODEL` if a judge-facing run needs it.

## Step 0 — verify the offline state (no keys needed, ~10 s)

```bash
python3 claimcourt/score.py          # 18 items PASS — computed == frozen
python3 benchmark/score.py           # gate 14/14, 0 false approvals
python3 claimcourt_lab/build.py --check   # 20 generated files match
python3 court.py                     # regenerates court/debate-replay.json (replay)
python3 claimcourt_lab/build.py      # rebuild the surface after any regen
```

If `court.py` regenerates the transcript, `claimcourt_lab/build.py` must
be re-run (the lab embeds the transcript) and `--check` re-passed.

## Step 1 — open the demo as it stands (no keys needed)

Serve the lab statically (same pattern as the existing Case Lab):

```bash
python3 -m http.server 8765 --directory claimcourt_lab
# → http://localhost:8765/  (Claim Court front door)
# → ../demo_lab/index.html is the original agent-work Case Lab
```

## Step 2 — what is already frozen (do not re-derive tonight)

- `claimcourt/cases.jsonl` + `claimcourt/truth.json` — 18 claims:
  7 RECORDED from the pilot salon's public pages (fetched 2026-10-30
  04:36–04:37 UTC; provenance in `claimcourt/SOURCES.md`), 11 SYNTHETIC
  fixtures labelled in every row. Verdicts computed by the reconciler:
  12 CONFLICTED / 5 PARTIAL / 1 CORROBORATED.
- `benchmark/eval-benchmark-2026-10-28.json` — the recorded live run
  (gate 14/14; deep 9/14, 1 false approval; fast 6/14, 2 false approvals;
  reviewer-lane cost $0.033).
- `court/debate-replay.json` — Round 1 recorded + citation audit
  computed; rebuttal round NOT RUN (labelled).

## Step 3 — LIVE: reviewer lanes over the commerce corpus (needs NEBIUS_API_KEY)

```bash
NEBIUS_API_KEY=... python3 batch_eval.py \
  --evidence claimcourt/cases.jsonl --tiers fast,deep --narrate \
  --out claimcourt/eval-claims-live.json
```

Expected: one JSON with per-item deterministic verdicts, per-tier lane
verdicts + costs, and narration checks (budget cap defaults to $0.25;
first-token stalls of ~3 min on cold models are a known platform trait —
the harness retries and records what it got). Cold-start note from the
Oct 28 run: allow several minutes per tier batch.

Then fold the lane verdicts into the surface: the lab currently prints
"Reviewer lanes over this corpus: NOT RUN" from `build_commerce_cases()`.
After this run exists, update that block in `claimcourt_lab/build.py` to
read verdicts from `claimcourt/eval-claims-live.json` (mark them LIVE +
run timestamp), rebuild, re-run `--check`, and update this pack's Step 2
list. Do not hand-edit the generated JSON/HTML.

## Step 4 — LIVE: hold the Nemotron Court (needs NEBIUS_API_KEY)

```bash
# Cross-examination over the benchmark corpus (the Court's home turf):
NEBIUS_API_KEY=... python3 court.py --live --budget 0.50 \
  --out court/debate-live.json

# Or over the commerce corpus:
NEBIUS_API_KEY=... python3 court.py --live --evidence claimcourt/cases.jsonl \
  --budget 0.50 --out court/debate-live-commerce.json
```

Expected: Round 1 runs fast+deep per item; the rebuttal round runs on
contested items only (any lane ≠ gate, or lanes split). Transcripts mark
every position LIVE with the run timestamp; UNPARSEABLE answers are kept
verbatim. To put a live transcript on the surface, point
`claimcourt_lab/build.py`'s `DEBATE` at the live file, rebuild, re-check.

## Step 5 — OPTIONAL: fresh Tavily evidence (needs TAVILY_API_KEY)

Only if a claim needs re-fetching before the freeze (e.g. re-check the
salon's directory hours). The recorded rows are already frozen with
crawl timestamps; adding fresh rows changes computed verdicts, so any
edit to `claimcourt/cases.jsonl` requires: re-run `claimcourt/score.py`
(expect drift → re-freeze `truth.json` only from computed output),
rebuild the lab, re-check. Never edit a frozen verdict by hand.

## Freeze checklist (before anything is pushed or submitted)

- [ ] `python3 claimcourt/score.py` → PASS (computed == frozen truth)
- [ ] `python3 claimcourt_lab/build.py --check` → OK (surface == artefacts)
- [ ] Every number on the surface traces to a committed run file:
      commerce verdicts → computed from `claimcourt/cases.jsonl`;
      rigor scores → `benchmark/eval-benchmark-2026-10-28.json` +
      `benchmark/cases.jsonl`; court positions → `court/debate-*.json`;
      costs → the same eval JSONs. Spot-check three.
- [ ] Live vs replayed is labelled in the data files themselves
      (`mode`, `labels`, per-case `lanes.status`), not just in prose.
- [ ] Synthetic fixtures are labelled in data (`"fixture": "synthetic"`)
      AND in UI copy (badge + title prefix). No fixture names a real
      third-party seller.
- [ ] Full test suite green: `python3 -m pytest -q` (or the repo venv).
- [ ] Secret scan before any push: no key material in the diff
      (`git diff origin/main --stat`, then eyeball new files; keys live
      in env only, never in files).
- [ ] demo_lab/ untouched (`git status` shows no demo_lab changes) — the
      live Case Lab URL judges already have must not move tonight.
