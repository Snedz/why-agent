# Benchmark results — 2026-10-28 (live Token Factory run)

Corpus: `benchmark/cases.jsonl`, 14 items, 51 claim rows, planted truth in
`benchmark/truth.json`. Scorer: `benchmark/score.py`. Raw lane output:
`benchmark/eval-benchmark-2026-10-28.json`. Reviewer-lane cost: **$0.033**
(narration is unmetered by the harness — see `docs/TIER_LEDGER.md`),
zero retries. Reproduce: `python3 benchmark/score.py --eval-results
benchmark/eval-benchmark-2026-10-28.json` (the lane scores below are what
it prints; its exit code is 1 by design — see the gate note). Every number in
this document is one the runner prints, and a test says so: it extracts every
figure from this file and fails if the runner's output does not contain it.

## Scores

| Scorer | Correct | False approvals |
|---|---|---|
| Deterministic reconciler (the gate) | **14/14** | **0** |
| Deep lane — Nemotron 3 Ultra | 9/14 | 1 (`bm-missing-cause`) |
| Fast lane — Nemotron 3 Nano | 6/14 | 2 (`bm-card-lies`, `bm-missing-cause`) |

## What the misses mean

- `bm-card-lies` is the corpus's central trap: the card claims a release
  shipped; the check and the deploy receipt say it failed and rolled
  back. The fast lane believed the card (CORROBORATED). The deep lane and
  the gate both returned CONFLICTED.
- `bm-missing-cause` — state and outcome agree, nobody stated a cause.
  Both lanes called it CORROBORATED; the gate's PARTIAL is the correct
  answer, because an unexplained outcome is not a verified one.
- The deep lane also returned one UNPARSEABLE verdict (strict format
  parse; recorded as-is, never coerced) and called `bm-unexpected-aspect`
  PARTIAL where the gate's CORROBORATED is right — the lanes err in both
  directions. They are advisory. This is the architecture working as
  designed, and it is why no lane output can raise a verdict.
- `bm-no-evidence` scores MISSING for both lanes: the harness iterates
  items that have card rows, and an item with zero claims cannot be
  discovered from the file. The gate scores it correctly (NO EVIDENCE)
  because the scorer asks for it by name. Harness gap, recorded here;
  the fix belongs to the benchmark card, not to a quiet edit.

## Gate note

`score.py` prints two verdicts on two lines, because they answer two different
questions. `GATE:` is the deterministic reconciler's — zero false approvals,
and the claim the project ships. `LANES:` is the advisory model tiers' —
printed in full above, and not gating: a lane cannot raise a verdict, so its
false approval is evidence about the model rather than a product failure. The
default exit code follows the gate; `--strict-lanes` makes a lane false
approval exit non-zero as well, for anyone who wants that criterion. The
per-scorer table above is the result — neither line alone is.

## Narration checks on the corpus

13 narrations (the zero-claim item has nothing to narrate): 3 PASSED,
10 FAILED, 17 flagged values in total. Classified as in
`docs/NARRATION_CHECK_ANALYSIS_2026-10-28.md`'s rubric: 8 system
vocabulary (UNKNOWN and friends), 4 source-name references ("CI" — the
checker allow-lists values, not source names), 3 locator fragments,
1 verdict-word variant ("CONFLICT"), 1 quoted empty value (the narration
faithfully described a recorded non-match's empty value). **Invented
facts: zero**, on manual review of the flags against the corpus. One
limit on that review: the harness does not persist narration text, only
the flagged values — so the classification is of the flags, reproducible
from the committed eval JSON, and persisting narratives is a recorded
harness improvement, not a silent gap.
