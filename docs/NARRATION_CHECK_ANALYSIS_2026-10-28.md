# Narration check analysis — batch eval of 2026-10-28

Source run: `eval-results-2026-10-28.json` (4 demo items, narration on the
standard tier, `nvidia/nemotron-3-super-120b-a12b`, via Token Factory).
Raw result: narration check PASSED on 1 item, FAILED on 3. The raw counts
are not the finding; the classification of every flagged value is.

## The five flagged values, classified

| Item | Flagged value | Classification | Evidence |
|---|---|---|---|
| why-alpha | `UNKNOWN` | System vocabulary | The narration stated an aspect was UNKNOWN — the reconciler's own word for an aspect nobody spoke about. |
| why-beta | `UNKNOWN` | System vocabulary | Same as above. |
| why-beta | `gate/beta` | Reformatted citation | The evidence locator is `synthetic://gate/beta`; the narration dropped the scheme. Same source, shorter string. |
| why-gamma | `UNKNOWN` | System vocabulary | Same as above. |
| why-gamma | `gamma` | Item-name fragment | The item is `why-gamma`; the narration referred to it by its short name. |

**Invented facts: zero.** No flagged value introduced a state, amount,
date, or outcome that the evidence does not contain.

## What this does and does not mean

The two-pass checker compares literally, and literal comparison cannot
distinguish restating the system's own vocabulary from inventing a fact.
That strictness is deliberate — a looser checker is how fabricated
citations get waved through — so this analysis does NOT argue for
weakening it. It argues for reporting discipline:

1. Never publish a narration pass/fail rate without the classification of
   the flagged values beside it. "1/4 passed" and "0 invented facts in 4
   narrations, 5 flags all accounted for" are both true; only the second
   is honest.
2. The benchmark corpus (JOB-nebius-placebo-benchmark) scores narration
   on invented facts, with flags classified by this rubric: invented /
   system vocabulary / reformatted citation / name fragment.
3. A candidate checker refinement — allow-listing the verdict vocabulary
   and normalising locator schemes before comparison — is a design
   decision for the founder, recorded here, NOT applied. If it is ever
   applied, the benchmark must be re-run and both versions reported.
