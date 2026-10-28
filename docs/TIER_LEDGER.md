# Tier ledger — measured 2026-10-28, Token Factory

Generated from `eval-results-2026-10-28.json` (4 demo items) and
`benchmark/eval-benchmark-2026-10-28.json` (13 benchmark items; the
zero-claim item cannot be lane-run). Prices are the dated snapshot in
`review.py` (per 1M tokens, in/out): Nano 0.06/0.24, Super 0.30/0.90,
Ultra 1.00/3.00 USD.

| Tier | Model | Calls | Tokens in | Tokens out | Cost | Agrees with gate |
|---|---|---|---|---|---|---|
| fast | nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B | 17 | 3,833 | 10,881 | $0.0028 | 8/17 |
| deep | nvidia/Nemotron-3-Ultra-550b-a55b | 17 | 3,833 | 11,147 | $0.0373 | 12/17 |

On the adversarial corpus scored against planted truth (not just
agreement): deep 9/14, fast 6/14, gate 14/14 —
`docs/BENCHMARK_RESULTS_2026-10-28.md`.

## The honest reading

Ultra costs ~13× Nano per call and buys real accuracy (12 vs 8
agreements; 9 vs 6 corpus-correct). It still falsely approved once and
returned one unparseable verdict. Routing consequence: **Nano for cheap
first-pass claims triage, Ultra on escalation, neither as a gate** — the
deterministic reconciler, which costs nothing and scored 14/14, decides.

## What this ledger does not contain

- **Narration cost.** The harness does not meter the narration call
  (Super tier), so every total in the eval files is a reviewer-lane
  total, not a run total. Metering it is a recorded harness fix.
- **Latency.** Per-call latency is not recorded by the harness; the only
  latency facts on record are qualitative (tiers ~1s warm; one ~3-minute
  cold-load stall). No median is published because none was measured.
