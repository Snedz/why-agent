# What changed in the submission period (2026-10-28 → 2026-10-29)

This is the plain account: what was already here, what was added, and what is
still not good enough. No adjectives the artefacts cannot support.

## What pre-existed

The **Open Agent build**, through commit `5bafca2` (2026-10-27): `why_agent.py`,
`evidence.py`, `narrate.py`, `demo.py`, `test_why_agent.py`, the
`evidence/items.jsonl` fixture, `docs/`, the demo page, the deck, the video and
the Pages workflow.

Two things it already did, and which did not change:

- **The deterministic reconciler** (`evidence.py`) reads claims and reconciles
  them — agreement, conflict, or unknown. It calls no model. A model's verdict
  is a claim like any other, and it is weighed like one.
- **The narration checker** (`narrate.py`) compares what a model said against
  the evidence and flags any value the evidence does not support.

## What was added

**2026-10-28 — the Nebius × NVIDIA build (`b62c3ed8`).** `providers.py` (the
Token Factory profile, with the model ids pinned from the account), the tiered
Nemotron reviewer lanes in `review.py`, `tavily_lane.py` (live web evidence — a
page counts only when the claimed value literally appears in it),
`vision_lane.py` (Super VL receipt fields as claims), `batch_eval.py` (the
tiered harness, with a retry and a budget cap) and `smoke.py` (the preflight).

**2026-10-28 — the adversarial benchmark and the claim map (`521ecff`).**
`benchmark/cases.jsonl` (14 items), `benchmark/truth.json` (the planted truth,
kept separate from what a lane sees), `benchmark/score.py` (the
zero-false-approvals gate), the run output
`benchmark/eval-benchmark-2026-10-28.json`, and `docs/CLAIM_MAP.md`.

**2026-10-28 — the tier ledger (`6116ae6`), the README's Nebius section
(`919ee6c`), the Case Lab (`b02d61a`, six labelled cases) and its Pages
publish (`92ca93c`), and two more lanes from the same day: the Zetaris
live-evidence lane (`a86175d`) and a Tavily on/off ablation harness
(`30e4b44`).**

**2026-10-29 — the gaps the queue named.** The offline test gaps and the
flaky-suite fix (`aa1c882`), the MCP surface (`9d998c9`), the tier ledger's
generator (`5111bec`), the benchmark test (`208fffb`), the smoke receipt
(`04aa4d8`), and the significant-update document itself.

**On the commit list.** This document names the *work*, with the dates it
happened. The exact list of commits is `git log 5bafca2..HEAD` — it changes
with every commit, and a stale list is worse than a pointer.

## The honest limits

- **The lanes advise; the reconciler decides.** On the corpus the deterministic
  gate scored **14/14** with **zero** false approvals. The deep lane scored
  **9/14** with **1** false approval; the fast lane **6/14** with **2** —
  including believing a card that claimed a failed deploy had shipped.
- **One lane verdict was unparseable**, and it is recorded as-is rather than
  coerced.
- **The narration checker fails more often than it passes.** Across the 13
  corpus narrations: **3 PASSED**, **10 FAILED**, **17** flagged values. Across
  the 4 demo narrations: 1 PASSED, 3 FAILED. Every flag is classified and no
  invented facts were found on a manual review — but the harness does not
  persist the narration text, only the flagged values, so the classification is
  of the flags.
- **Every cost total is a reviewer-lane total.** The harness does not meter the
  narration call, so no total here is a run total.
- **No latency percentile is published.** The harness records no per-call
  latency: there is no median because none was measured.
- **The Token Factory free period ended 2026-10-22**, so pinned gateway runs
  bill at standard rates.
- **The corpus has 14 items and 51 claim rows.** One item carries no claims at
  all, which is why it cannot be lane-run and why the lanes score it MISSING.
- **The MCP server is stdlib-only** — the official MCP Python SDK was not
  installed and the card allowed no other new dependency — **it is not
  deployed, and it has no auth.**
- **No users, no revenue, no adoption.** None is claimed here, because none
  exists: this submission period is a build, not a launch.
