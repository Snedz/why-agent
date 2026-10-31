# why-agent

**An agent that answers "why", and cites every sentence of the answer.**

Give it a work item. It reads what the card says, what the receipt says, what
the commit says, what the check run said, what the reviewers said — and then it
tells you what happened, with the citation attached to each line.

It does not pick a winner when the sources disagree. That is the whole point.

## Claim Court — the commerce surface of why-agent

Claim Court is the commerce surface of why-agent: the same deterministic
gate, pointed at commerce claims — product listings and business pages
instead of work items. Its corpus is 18 claims
(7 recorded from our pilot salon's public pages, 11 labelled synthetic
fixtures), and the gate returned **12 CONFLICTED / 5 PARTIAL / 1 CORROBORATED**
— every verdict computed by the reconciler and frozen in the corpus. On the
benchmark corpus, a Nemotron Court citation audit scores each reviewer lane's
verdict against the evidence it failed to answer.

| | |
|---|---|
| **Claim Court demo** | https://snedz.github.io/why-agent/demo_lab/claimcourt/ |
| **Corpus** | `claimcourt/` — the 18 claims, their sources and aspect mapping — https://github.com/Snedz/why-agent/tree/main/claimcourt |
| **Claim Court Case Lab** | The demo above is the Case Lab: the 18 claim cards, the Nemotron Court transcript, and the rigor section on one page |
| **Verify one verdict** | `python3 claimcourt/score.py` — re-derives all 18 verdicts from the committed rows and fails on drift |
| **Runtime** | Nebius Token Factory, `https://api.tokenfactory.nebius.com/v1/` — fast reviewer `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` (Nano), narration `nvidia/nemotron-3-super-120b-a12b` (Super), deep reviewer `nvidia/Nemotron-3-Ultra-550b-a55b` (Ultra), vision `nvidia/Nemotron-3.5-Super-VL` |
| **Tavily runtime receipts** | `docs/tavily-live-2026-10-30/` — the raw Tavily responses and ablation results from the 2026-10-30 live run |
| **Licence** | Apache-2.0 |

---

## Nebius × NVIDIA Global AI Hackathon — Best Apps and Agents track

This is the entry. It runs on **Nebius Token Factory**
(`https://api.tokenfactory.nebius.com/v1/`) and uses **NVIDIA Nemotron 3**
open-source models — Super, Nano and Ultra — plus a Tavily live-evidence lane
and a Nemotron Super VL receipt lane.

| | |
|---|---|
| **Demo** — the reconciler, running in your browser | https://snedz.github.io/why-agent/ |
| **Case Lab** (the four verdict states, with every receipt) | https://snedz.github.io/why-agent/demo_lab/ |
| **Claim Court** — the same reconciler on commerce claims | https://snedz.github.io/why-agent/demo_lab/claimcourt/ |
| **Video** (under three minutes) | https://snedz.github.io/why-agent/why-agent-nebius-demo.mp4 |
| **Repository** | https://github.com/Snedz/why-agent |
| **Licence** | Apache-2.0 |

Free of charge, unrestricted, no login and no data collection — including
through the end of the judging period on 2026-12-23.

The demo page is not a page of results: it runs the reconciler in the tab.
Untick a source, type a different value into a claim, or invent an aspect, and
the verdict is recomputed from the rows on screen. On the two lane-dependent
cases one button removes the model-lane rows and shows the verdict flip — the
same flip `demo_lab/flip_check.py` proves in Python. No key, no server, no
network: the corpus and the reconciler are both in the page.

**Try it first — three commands, no key, no network:**

```
git clone https://github.com/Snedz/why-agent && cd why-agent
python3 demo.py                                   # the five cases, as a reader sees them
python3 benchmark/score.py --eval-results benchmark/eval-benchmark-2026-10-28.json
python3 demo_lab/flip_check.py                    # proves the model lanes change the verdict
```

**With a Nebius Token Factory key** (the environment is the only place a key
ever lives):

```
export NEBIUS_API_KEY=...
export TAVILY_API_KEY=...
python3 smoke.py --provider nebius
python3 why_agent.py explain why-alpha --evidence evidence/items.jsonl --provider nebius --narrate
python3 batch_eval.py --provider nebius --evidence benchmark/cases.jsonl --tiers fast,deep --narrate --budget 0.50
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

## The answers it can give

| Verdict | What happened | What the agent does |
|---|---|---|
| `CORROBORATED` | the sources agree and cover the ground | says so, cited line by line |
| `PARTIAL` | the sources agree where they speak, and do not cover everything | says what is corroborated and names the gaps |
| `CONFLICTED` | two sources make different claims about the same thing | shows every side, cites every side, refuses to pick |
| `NO EVIDENCE` | nobody has written anything about this item | says exactly that |

**UNKNOWN is never 0.** An aspect nobody reported is a gap in the evidence, and
it is reported as a gap — not as a pass, and not as a plausible explanation.

---

## The Nebius × NVIDIA build

The reconciler above is deterministic and calls no model. Everything in this
section is new: the same kernel, now fed by model, image, and live-web lanes
running on **Nebius Token Factory** — with every lane output entering as a
*claim*, never a verdict, because any integration can be poisoned.

| Lane | Model (pinned from the account) | What it contributes |
|---|---|---|
| Narration | `nvidia/nemotron-3-super-120b-a12b` | The explanation — then machine-checked twice; a value not literally in the evidence **fails the check** |
| Reviewer, fast | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | An independent verdict, appended as a cited evidence row |
| Reviewer, deep | `nvidia/Nemotron-3-Ultra-550b-a55b` | Same, deeper — disagreements with the fast lane are preserved, never averaged |
| Vision | `nvidia/Nemotron-3.5-Super-VL` | Receipt/screenshot fields (amount, date, counterparty, status) as checkable claims |
| Live evidence | Tavily (via `tavily_lane.py`) | Web pages as claims — a page counts only if the claimed value literally appears in it; the generated answer is never evidence |

### What the run measured

On an adversarial corpus of planted-claim fixtures, scored against a truth file
the lanes never see:

| Scorer | Correct | False approvals |
|---|---|---|
| **The deterministic reconciler (the gate)** | **14/14** | **0** |
| Deep lane — Nemotron 3 Ultra | 9/14 | 1 |
| Fast lane — Nemotron 3 Nano | 6/14 | 2 |

The lanes err in **both** directions: the fast lane believed a card that claimed
a failed deploy had shipped, and the deep lane returned one verdict that did
not parse at all. That is the architecture working as designed, and it is why no
lane output can raise a verdict.

Reproduce it — the numbers above are what this prints:

```
python3 benchmark/score.py --eval-results benchmark/eval-benchmark-2026-10-28.json
```

```
[deterministic] 14/14 correct
  false approvals: 0
corpus: 14 items, 51 claim rows
reviewer-lane cost: $0.033 (narration unmetered), retries 0
narration checks: 13 checked, 3 PASSED, 10 FAILED; 17 flagged value(s)
flag classes: invented 0, locator fragment 3, quoted empty value 1, source reference 4, system vocabulary 8, verdict variant 1
unparseable verdicts: 1
[lane:deep] 9/14 correct
[lane:fast] 6/14 correct
```

The corpus is **14 items, 51 claim rows**, and the run cost **$0.033** of
reviewer-lane time with **zero** retries. One item carries no claims at all,
which is why it cannot be lane-run and why the lanes score it MISSING.

### The receipts, and where each claim points

| Claim | Proof |
|---|---|
| Every lane above runs on Token Factory | `providers.py` — the profile, the base URL and the pinned model ids |
| The lanes disagree, and the disagreement is preserved | `eval-results-2026-10-28.json` — `why-alpha` fast=PARTIAL vs deep=CONFLICTED |
| The gate out-ranks the lanes | `benchmark/score.py` — the lanes are scored separately from the gate |
| Zero false approvals on the adversarial corpus | `benchmark/eval-benchmark-2026-10-28.json`, scored by `benchmark/score.py` |
| A web page counts only on a literal match | `tavily_lane.py` — a non-match yields an empty-value row, not a dropped row |
| A forged aspect cannot change a verdict | `evidence.reconcile()` routes an unknown aspect to `unexpected`: cited, ignored, never agreed |
| A VL extraction becomes a claim, never a verdict | `vision_lane.py` — null fields produce no rows; a non-JSON answer raises |
| A client can ask the agent for its verdict | `mcp_server.py` and `test_mcp_server.py` — the server calls no model, and a test forbids it |
| Costs are measured, not estimated | `docs/TIER_LEDGER.md`, generated from the committed run outputs by `tier_ledger.py` |
| The demo URL a judge opens describes this entry, with the measured numbers on it | `demo_page.py` generates `demo.html` from the corpus, the committed run outputs and the provider profile; the answer it shows is a verbatim slice of `demo.py` |
| The page's JavaScript is this reconciler, not a lookalike | `demo_lab/reconciler.js` and `test_demo_app.py` — the port is run under node and `evidence.reconcile()` under Python over every item in both corpora; any difference in verdict, conflict, agreement, gap or aspect order fails the test |
| The page cannot drift from the corpus | `demo_page.py --check`, and `test_demo_app.py` compares the blob embedded in the page against the rows on disk |
| What pre-existed, and what was added | `docs/SIGNIFICANT_UPDATE.md` |

Every row above has a command a reader can run; `docs/CLAIM_MAP.md` is the full
map with the command for each row.

## The Case Lab

The **Case Lab** is the demo a judge can open: seven cases, each showing the
claims, the lane receipts (model id, endpoint, cost, token count), the verdict,
and what decided it. It is generated from the corpus by `demo_lab/build.py`, so
a verdict on the page is the verdict the reconciler returns — never a number
typed by hand.

Two of the cases are **lane-dependent**, and `demo_lab/flip_check.py` proves it
by re-reading the original rows and calling the same reconciler twice:

```
case                       with lanes       without lane rows      flips
bm-reviewer-split          CONFLICTED       CORROBORATED           yes
bm-web-nonmatch            CONFLICTED       PARTIAL                yes
```

`bm-reviewer-split` is the two Nemotron tiers disagreeing: remove the reviewer
rows and a genuine conflict reads as a routine corroboration.
`bm-web-nonmatch` is the Tavily lane recording a miss it did not drop.

## The workbench — the reconciler in the tab

The landing page is a tool, not a poster. `demo_lab/reconciler.js` is a port of
`evidence.reconcile()`, inlined into the page with the corpus, and everything
on the right-hand side is computed by it:

- **Untick a source** and the verdict is recomputed without it.
- **Type a different value** into a claim and the sources stop agreeing — the
  conflict appears with every side cited, and nothing is averaged.
- **Invent an aspect** and watch the forged claim get cited, then ignored by
  the verdict.
- **Remove the model-lane rows** on a lane-dependent case and CONFLICTED
  becomes CORROBORATED, which is the flip `demo_lab/flip_check.py` proves in
  Python.

The picker holds three corpora. Two are about work items. The third is the
**commerce corpus**: the claims a shopper actually reads — a salon's published
hours, a listing's materials, a sale price — run through the same reconciler.
Part of it was fetched from the public pages of a real pilot business and the
directories that list it, and those conflicts are real; the rest is labelled
synthetic fixture in every case file. The **Claim Court** shows them with their
provenance per case — it is the first link on this page.

A port with no parity test is a second implementation that will drift, so
`test_demo_app.py` runs that file under node and the Python under CPython over
every item in both corpora, plus edge cases built to break a careless
translation — a forged aspect alongside complete coverage, an empty string as a
value, `DONE` against `done`, an unknown kind with no aspect. The two answers
must be identical: verdict, conflicts, agreements, gaps, unexpected aspects,
aspect order, source count. If `node` is not installed the test **skips**, and
the skip message says the port is unverified on that machine — an unverified
port is exactly what this repository is built not to ship.

---

## The model may write the prose. It may not add a fact.

The reconciliation is code and decides what is true. The *prose* a reader
wants is not code's best skill, so a model writes it — over any
OpenAI-compatible endpoint, here Nemotron 3 Super on Token Factory — and then
it is **checked**: every value the narrative states must already exist in the
evidence.

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

On the corpus the checker is deliberately noisy: **13** narrations, **3**
PASSED, **10** FAILED, **17** flagged values. Every flag is classified, and the
count of invented facts is **zero** — but that review is of the flags, because
the harness persists the flagged values and not the narration text.

## The evidence model

The reconciliation is code, not a prompt. The tests assert the behaviour:

- a card that disagrees with a commit is a **conflict**, not a merge;
- two sources about *different* aspects never conflict;
- an aspect nobody covered is **UNKNOWN**, not a pass;
- every claim in the report carries a citation;
- an item nobody wrote about gets `NO EVIDENCE`, not a plausible explanation.

A prompt cannot be tested like that. This can, and is.

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

### The MCP surface

`mcp_server.py` exposes the agent over MCP with three tools. The server calls
no model — a test forbids it — and a verdict-shaped submission is refused at
the boundary, so a client cannot push a verdict through the front door.

```
python3 -m pytest -q test_mcp_server.py
```

---

## Install and run

No dependency. Python 3.10+.

```
git clone https://github.com/Snedz/why-agent && cd why-agent
python3 -m unittest discover -v      # the whole suite, offline
python3 demo.py                       # five cases, as a reader sees them
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

## Other integrations

The kernel is not prompt-shaped, so it also sits behind two adapters from the
earlier build in this repository — kept here because they are evidence that the
same reconciliation runs against something other than a model.

- **Zetaris** — a governed semantic layer over the engines you already run.
  The designed path is a CSV in the stack bucket, a filestore table, and a
  reconciliation `SELECT`. See `zetaris_lane.py` and `docs/ZETARIS_LANE.md`.
- **Meterless (Nightshift)** — an Apache-2.0 runtime that races a job across
  local models, judges the attempts, and returns a receipt for every check.
  The token is resolved from the runtime's own token file and is never printed.

## Security

The narration check catches invented values. It does not decide whether a model
obeyed an instruction that was hiding in the evidence. How tokens are resolved,
what is rejected, and the poison drills are in `SECURITY.md`.

## The data in this repository is synthetic

Every card, receipt, verdict, commit and check id here is invented. There is no
real customer, no real identifier, no real project in this repository, and
nothing here is a credential. The production wiring reads a real work
system; the demo reads this one. **No users, no revenue, no adoption** — none
is claimed, because none exists.

## Licence

Apache-2.0. See `LICENSE`.
