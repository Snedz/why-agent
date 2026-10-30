# why-agent

**An agent that answers "why", and cites every sentence of the answer.**

Give it a work item. It reads what the card says, what the receipt says, what
the commit says, what the check run said, what the reviewers said — and then it
tells you what happened, with the citation attached to each line.

It does not pick a winner when the sources disagree. That is the whole point.

```
$ python3 demo.py
```

---

## Nebius × NVIDIA build (submission period, Oct 2026)

The reconciler above is deterministic and calls no model. Everything in
this section is new: the same kernel, now fed by model, image, and live-web
lanes running on **Nebius Token Factory** — with every lane output entering
as a *claim*, never a verdict, because any integration can be poisoned.

| Lane | Model (pinned from the account) | What it contributes |
|---|---|---|
| Narration | `nvidia/nemotron-3-super-120b-a12b` | The explanation — then machine-checked twice; a value not literally in the evidence **fails the check** |
| Reviewer, fast | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | An independent verdict, appended as a cited evidence row |
| Reviewer, deep | `nvidia/Nemotron-3-Ultra-550b-a55b` | Same, deeper — disagreements with the fast lane are preserved, never averaged |
| Vision | `nvidia/Nemotron-3.5-Super-VL` | Receipt/screenshot fields (amount, date, counterparty, status) as checkable claims |
| Live evidence | Tavily (via `tavily_lane.py`) | Web pages as claims — a page counts only if the claimed value literally appears in it; the generated answer is never evidence |
| MCP surface | none — it calls no model | The verdict, the claims grouped by aspect and the lane disagreements, over MCP. A submission carrying a verdict is **refused at the boundary**: integrations contribute claims, never verdicts |

**Measured, 2026-10-28** (receipts in `docs/`): on a 14-case adversarial
corpus the deterministic gate scored **14/14 with zero false approvals**;
the Ultra lane scored 9/14 (one false approval), the Nano lane 6/14 (two —
including believing a card that claimed a failed deploy had shipped). The
lanes advise; the gate decides. Reviewer cost for 17 judged items: Nano
$0.0028, Ultra $0.0373. Narration checker: 17 flagged values across 13
corpus narrations, zero invented facts on classification.

- Full results and named misses: `docs/BENCHMARK_RESULTS_2026-10-28.md`
- Cost/latency ledger and its gaps: `docs/TIER_LEDGER.md`
- Every submission claim mapped to its proof: `docs/CLAIM_MAP.md`
- Why raw checker pass rates mislead: `docs/NARRATION_CHECK_ANALYSIS_2026-10-28.md`
- What pre-existed, what was added, and the honest limits: `docs/SIGNIFICANT_UPDATE.md`

Run the lanes (keys from the environment only):

```
export NEBIUS_API_KEY=...        # Token Factory
export TAVILY_API_KEY=...        # live-evidence lane only
python3 smoke.py --provider nebius
python3 why_agent.py explain why-alpha --evidence evidence/items.jsonl --provider nebius --narrate
python3 batch_eval.py --provider nebius --evidence benchmark/cases.jsonl --tiers fast,deep --narrate --budget 0.50
python3 benchmark/score.py --eval-results benchmark/eval-benchmark-2026-10-28.json
```

---

## The problem it is for

In a busy engineering system the answer to "why did this happen?" is scattered
across places that never talk to each other. The card says DONE. The commit
says merged. The check run says red. The receipt says nothing was claimed. A
review says approved, for a different card.

A person resolves this by opening five files and holding the five facts in their
head. An agent that reads one source sounds confident and is wrong most of the
time — worse than no answer, because nobody checks a confident answer.

So this agent reads all of them and does the one thing a single-source agent
cannot do: **it notices that they disagree, and it says so with both sides
cited.**

## The three answers it can give

| Verdict | What happened | What the agent does |
|---|---|---|
| `CORROBORATED` | the sources agree and cover the ground | says so, cited line by line |
| `PARTIAL` | the sources agree where they speak, and do not cover everything | says what is corroborated and names the gaps |
| `CONFLICTED` | two sources make different claims about the same thing | shows every side, cites every side, refuses to pick |
| `NO EVIDENCE` | nobody has written anything about this item | says exactly that |

**UNKNOWN is never 0.** An aspect nobody reported is a gap in the evidence, and
it is reported as a gap — not as a pass, and not as a plausible explanation.

## Watch it

The demo video and the deck are published with this repository:

- **Demo:** https://snedz.github.io/why-agent/
- **Video (MP4, 2:28):** https://snedz.github.io/why-agent/why-agent-demo.mp4
- **Deck (PDF, 13 pages):** https://snedz.github.io/why-agent/why-agent-deck.pdf

No upload step and no third-party account: GitHub Pages serves it from this
repository.

## Install and run

No dependency. Python 3.10+.

```
git clone <this repo> && cd why-agent
python3 -m unittest test_why_agent -v      # 34 tests, no network
python3 demo.py                             # five cases, as a reader sees them
python3 why_agent.py items
python3 why_agent.py explain why-alpha
python3 why_agent.py explain why-alpha --json
```

The evidence file is JSON Lines, one claim per line, and it is meant to be read
with `cat`. A row is a claim by one source:

```json
{"item_id": "why-alpha", "kind": "check", "source": "ci",
 "locator": "synthetic://run/alpha/42", "statement": "the gate run is still red",
 "value": "failing", "observed_at": "2026-10-22T09:41:00Z", "aspect": "state"}
```

An **aspect** is a property of the item, not of the source: `state`,
`outcome`, `cause`. Two claims about the same aspect with different values
contradict each other; two claims about different aspects never do.

The card row is a claim too — it is the source most likely to be stale, and an
agent that cannot notice a stale card cannot notice anything.

### The production path: DuckDB

In a real system the same rows live in one DuckDB file, and the agent reads
them from there:

```
python3 why_agent.py explain <item-id> --duckdb evidence/work.duckdb
```

The file needs two tables — `items(item_id, title, declared_status)` and
`evidence(item_id, kind, source, locator, statement, value, observed_at,
aspect)`. `duckdb` is imported only when this path is used, so the demo still
runs with nothing installed.

## The model may write the prose. It may not add a fact.

The reconciliation is code and decides what is true. The *prose* a reader
wants is not code's best skill, so a model writes it — over any
OpenAI-compatible endpoint — and then it is **checked**: every value the
narrative states must already exist in the evidence.

```
$ python3 why_agent.py explain why-alpha --narrate
## CHECK PASSED — every value the narrative stated exists in the evidence
```

The check has **two passes, because a model may forget to quote**: quoted
spans, *and* every token that looks like a value — an identifier, a number, a
path, a date. Ordinary prose words are not values and are not checked; this is
not a semantic verifier, and pretending otherwise would make the check
useless.

A model that invents a fact is caught, and the invention is **reported, not
removed** — a silent cleanup is how a hallucination becomes a footnote.

## How it would use Zetaris

**Zetaris** is a data harness for AI: a governed semantic layer over the
engines you already run (DuckDB, Spark, Trino, Presto). Data reaches it as
files. For this project that is a CSV in the stack bucket, registered as a
filestore table, then read with a reconciliation `SELECT` in the SQL
workspace or over JDBC. There is no MCP endpoint in that path.

The cards, receipts, verdicts and commits are fragmented sources. The
harness's job is one governed way to query them, and the semantic layer is
where the `aspect` vocabulary belongs. The Hobby tier is free, and a Mini
cluster is BYOC — it deploys into a cloud account — so the account is a
founder step. See `INTEGRATION.md`.

## How it would use Meterless

**Meterless** (Nightshift) is an Apache-2.0 runtime that races a job across
local models, judges the attempts, and returns a receipt for every check. Two
ways it belongs to this project:

1. **As the runtime.** The agent's model calls run as a Nightshift job, so the
   reasoning is local, free, and reproducible — and each run comes back with
   the receipt that the house already insists on.
2. **As the meter.** Nightshift is how the agent's cost is accounted for, in
   the same way this repository accounts for every model call it makes.

Either way the integration is small and honest: the agent does the
reconciliation, the runtime does the racing, and the receipt is the evidence.

See `INTEGRATION.md` for the exact steps, including the path that needs no
account at all.

## Why this is not "an LLM with a prompt"

The reconciliation is code, not a prompt. The tests assert the behaviour:

- a card that disagrees with a commit is a **conflict**, not a merge;
- two sources about *different* aspects never conflict;
- an aspect nobody covered is **UNKNOWN**, not a pass;
- every claim in the report carries a citation;
- an item nobody wrote about gets `NO EVIDENCE`, not a plausible explanation.

A prompt cannot be tested like that. This can, and is.

## Security

The narration check catches invented values. It does not decide whether a model
obeyed an instruction that was hiding in the evidence. How tokens are resolved,
what is rejected, and the poison drills are in [SECURITY.md](SECURITY.md).

## The data in this repository is synthetic

Every card, receipt, verdict, commit and check id here is invented. There is no
real customer, no real identifier, no real project in this repository, and
nothing here is a credential. The production wiring reads a real work
system; the demo reads this one.

## Layout

```
why_agent.py         the CLI and the report
evidence.py           the model: claims, aspects, reconciliation
demo.py               the five cases
test_why_agent.py     34 offline tests
evidence/items.jsonl  the synthetic dataset
INTEGRATION.md        Zetaris + Meterless, step by step
SUBMISSION.md         what is ready, what the founder must do, and by when
DECK.md               the slide deck
```

## Licence

Apache-2.0. See `LICENSE`.
