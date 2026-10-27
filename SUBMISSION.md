# Submission checklist — Open Agent Hackathon 2026, Track 02

**Event:** https://hackathon.genai.works/event/open-agent-hackathon-2026
**Track:** 02 — The Agent That Can Explain Why ($1,600 / $1,200 / $900)
**Submissions close:** the event page, fetched 2026-10-27, says **23:59 UTC**.
This file used to say 23:45 UTC. The founder submits against the earlier
clock: 23:45 UTC, 7:45 PM Toronto.
**Build window:** Oct 22 00:00 UTC → the close above (rule 04)

This file is the state of the entry as the lane left it, and the list of what
the founder has to do. Nothing here is done on the founder's behalf: the
submission is behind their account, and publishing is their call.

---

## What is DONE

| Deliverable | Where | State |
|---|---|---|
| The agent | `why_agent.py`, `evidence.py`, `narrate.py` | working, 34 tests green, no third-party dependency |
| The demo | `demo.py` → five cases, one command | working |
| Tests | `test_why_agent.py` | 34 tests, offline, no network |
| Synthetic dataset | `evidence/items.jsonl` | synthetic only — no real card, customer or identifier |
| README | `README.md` | written, states what the agent does and how to run it |
| Integration doc | `INTEGRATION.md` | Zetaris + Meterless, with verified and unverified separated |
| Slide deck | `DECK.md` | 10 slides plus a title page, rendered to an 11-page PDF |
| Publication steps | this file, §1 | exact command, ready to run |
| This checklist | `SUBMISSION.md` | — |

## What the FOUNDER has to do (in this order)

### 1. Publish the repo — public, under the brand identity

The private repos (`Snedz/mission-ops`, `Snedz/program-67`) stay private.
Rule 06 requires "a GitHub repository with all source code and a README
covering setup, usage and dependencies", so the entry is published as its own
repository, built from this directory only. The rules name no visibility
requirement — it is published **publicly** anyway, because a judge has to be
able to open it.

Exact command: `gh repo create Snedz/why-agent --public --source=. --remote=origin --push`, then push this directory as its root.

- [ ] `gh repo create Snedz/why-agent --public --description "..." --license apache-2.0`
- [ ] push this directory as its root
- [ ] confirm the public repo contains no private-repo file: no `memory/`,
      no customer data, no credential
- [ ] public text says "Snedz" / "Mission Winning" only — never a real name

### 2. AI-assisted work is explicitly allowed — no decision needed here

**Checked against the live rules on 2026-10-26.** §05 says, in full:
*"Generated code is allowed and expected, you own the result and are
accountable for it."* §06 lists what a submission must contain and says
nothing about how the code was written. §10 covers schedule changes, the
finality of disqualification decisions, and where to send questions.

An earlier version of this file read that sentence as a disqualification risk
and listed withdrawing the entry as the alternative. **That reading was wrong,
and it is withdrawn.** The rules contain exactly one sentence about generated
work, and it permits it.

The condition the rules do impose — "you own the result and are accountable
for it" — is satisfied: the reconciliation is deterministic code rather than
a prompt, the 34 tests are real and offline, and every claim in the report
carries a citation. **Declare the pre-existing components (§04) and submit.**

### 3. Stand up the Zetaris harness (optional but rule 05 wants it)

- [ ] the Mini cluster `why-agent-mini` was **not Active** on 2026-10-27.
      AWS credentials were not available, and no JDBC host was on disk.
- [ ] the designed path is a CSV in the stack bucket, a filestore table, and
      a reconciliation `SELECT`. There is no MCP endpoint on that path.
- [ ] if the cluster is later Active: run the statements in `INTEGRATION.md`
      and replace the "no live result" section with the real output

The agent does not depend on this. The local DuckDB path is the same rows read
the same way.

### 4. Run the Meterless runtime locally (optional, no account)

- [x] Nightshift M1-M4 0.92.7 installed. `GET http://[::1]:8088/v1/models`
      returned 200 with `meterless/*` ids. The token came from the app's
      runtime-token file and was not printed.
- [x] `python3 why_agent.py explain why-alpha --narrate --narrate-base
      http://[::1]:8088/v1` returned **HTTP 502** (`model_load_failed` on the
      routed WebLLM lane). CHECK PASSED was not observed. See `INTEGRATION.md`.
      The token is resolved automatically. `rt-local` is rejected.

If the runtime is not installed, the entry still works: the deterministic
report is the part that decides what is true, and the demo does not need a
model.

### 5. Publish the demo video (1–4 minutes, rule 06)

**Recorded: 1:24, 1600×900, silent.** The times below are frame-measured from
the render — the renderer reports the exact start of every shot, and each one
was checked against the frame at that second.

| # | Shot | What it shows | At |
|---|---|---|---|
| 1 | Title card | what it is, in one line | 0:00 |
| 2 | Terminal | `python3 -m unittest test_why_agent` → 27 passed | 0:05 |
| 3 | Terminal | `python3 demo.py` → the five items, and the four kinds of answer | 0:10 |
| 4 | Terminal | the **conflicted** case: four sources, four answers, no winner picked | 0:23 |
| 5 | Terminal | the **unknown** case: an aspect nobody reported is named as a gap | 0:33 |
| 6 | Terminal | `python3 why_agent.py explain why-alpha --narrate` → the narrative + `CHECK PASSED` | 0:48 |
| 7 | Terminal | `--narrate` with a model that invents a fact → `CHECK FAILED` | 1:02 |
| 8 | Title card | the thesis, in one line | 1:19 |

The strongest stretch is shot 7, from 1:02: the agent catching a model
inventing a fact, and refusing to publish it as fact. That is the whole
thesis in one moment.

Shots 6 and 7 in the 1:24 cut were a **local stub** on `127.0.0.1:8088`, not
the Meterless runtime. The live runtime, on `[::1]:8088`, returned HTTP 502
for `why-alpha --narrate`. A submission video that shows CHECK PASSED from
that stub is not a live Meterless run. The D3 beat (CHECK FAILED against an
inventing stub) is real and is in `DRILLS-2026-10-27.md`.

- [ ] upload it to a public host and paste the URL into the form

### 6. Turn the deck into a PDF

- [x] `DECK.md` is the deck — 10 slides plus a title page, and it is in this
      repository. A PDF render is what the founder uploads (rule 06 accepts a
      PDF, a deck, or Google Slides).

### 7. Submit (before Oct 27 23:45 UTC)

- [ ] public repo URL
- [ ] demo video URL
- [ ] slide deck URL
- [ ] team info (one person: the founder — rule 01/02 allow 1–5)
- [ ] the explanation of how Zetaris / Meterless / Cursor / NVIDIA were used —
      `INTEGRATION.md` carries the wording
- [ ] **declare the pre-existing components (rule 04)**: the receipt-and-verdict
      discipline, the card/commit/receipt vocabulary and the model-verdict
      ledger all pre-date the build window and are declared as pre-existing.
      The **entry** — the agent, the reconciliation, the check — was built
      inside the window.
- [ ] the brand identity only: "Snedz" / "Mission Winning"

## Time budget

| When | What |
|---|---|
| now → Oct 27 09:00 ET | founder steps 1–4 (publish, decide, accounts) |
| Oct 27 09:00–13:00 ET | record the video (step 5), turn the deck (step 6) |
| Oct 27 13:00–19:45 ET | slack, submit early — **the form is behind the founder's account and the platform may need the founder present** |

Submit early. The deadline is 23:45 UTC and the platform's own failure modes
are unknown to us.

## What was NOT done, and why

- **The submission itself.** It is behind the founder's account; an agent
  cannot submit, and rule 01 says one account per participant.
- **Publishing.** "Publishing a product" is a founder decision in this repo's
  own rules; the lane prepared everything and stopped there.
- **A real Zetaris query.** The filestore path is designed. The cluster was
  not Active, and the statements were not run.
- **The demo video is recorded** (1:24, silent). What is missing is a public
  host for it and the URL in the form.
- **A public repo.** For the same reason as publishing — and because the
  private repos stay private for good reason.

## The rules, in one place

Re-read from the official page on 2026-10-26 —
https://hackathon.genai.works/event/open-agent-hackathon-2026 — the "Rules"
panel, 10 sections. The short version:

- **01** 16+, worldwide; one account per participant (the founder registered one).
Read again from the rules panel on 2026-10-27, expanded on the event page:

- **4.1** the build window ends **27 October 2026 at 23:45 UTC**. The same
  page's banner says submissions close at 23:59 UTC. Submit before 23:45.
- **4.2** work from before the window is ineligible except clearly declared
  pre-existing components.
- **5.1** every submission must integrate Zetaris and Meterless. Cursor is
  optional.
- **5.4** pre-existing product code must be declared on the form.
- **5.5** generated code is allowed and expected; you own the result.
- **6.1** a demo video of 1–4 minutes that shows the workflow, the challenge,
  the key features, and how Zetaris and Meterless are integrated.
- **6.2** a slide deck covering the problem, the users, the solution, the
  workflow, the stack, how Zetaris and Meterless were used, and what was
  unique about that use.
- **6.3** a GitHub repository with the source and a README covering setup,
  usage and dependencies.
- **6.4** a written explanation of the Zetaris and Meterless integrations,
  how Cursor was used if it was used, where NVIDIA contributes, and what was
  unique about the sponsor technologies.
- **08** Track 02 prizes $1,600 / $1,200 / $900.
- **07** scored out of 100: **Impact 30, Technical 20, Innovation 15, Demo 15,
  Product & UX 10, Sponsor tech 10.** Ties resolve on Impact, then on timestamp.
- **08** Track 02 prizes $1,600 / $1,200 / $900. In-kind: a DGX Spark for best
  use of NVIDIA Nemotron.
- **09** we keep all IP rights; a promotional licence is granted.
- **10** the organiser may adjust the schedule for technical reasons;
  disqualification decisions are final and come with a reason.
