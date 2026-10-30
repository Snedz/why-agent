# SUBMISSION — Nebius × NVIDIA Global AI Hackathon

**Event:** https://nebiusglobalaihackathon.devpost.com/
**Track:** Best Apps and Agents
**Submissions close:** **Friday 2026-10-30, 10:00 AM PT** (13:00 ET / 10:00 Toronto).
The rules as read on 2026-10-29 are in `docs/NEBIUS_RULES_2026-10-29.md`.

Everything below is ready to paste. **Three things need the founder** — see
§0. Nothing has been submitted, published to Devpost, or uploaded to YouTube
by the build lane; those are behind the founder's accounts and their call.

**On the field labels.** The "Enter a Submission" form is behind a Devpost
login, so its own wording was not readable from here. The answers below are
keyed to the ten numbered submission requirements in the rules, which enumerate
the fields the form asks for. If a label on the form differs, the answer under
it is still the right one — but read the form's wording before pasting.

---

## 0. What only the founder can do

1. **Check eligibility.** The rules exclude entrants resident in Quebec, Brazil,
   Russia, Crimea, Cuba, Iran, North Korea, and anyone subject to OFAC
   sanctions. Confirm the residence before submitting. If the founder is a
   Quebec resident, do not submit.
2. **Upload the video to YouTube** and make it **publicly visible** (the rules
   say publicly visible; unlisted is not the same thing). The file to upload
   is `why-agent-nebius-demo.mp4` at the repository root — 87.54 seconds, under
   the three-minute limit. Step-by-step in §6.
3. **Paste the form** and submit. Every field answer is §1–§5. Join the
   challenge from the founder's account first, or the Submit button will not
   appear.

Nothing in this repository spends money, needs an account, or sends anything.
The Nebius key stays in the environment; it is never committed.

---

## 1. The form fields, in order

### 1.1 Name of your Project

```
why-agent
```

### 1.2 URL to a working demo, hosted app, or test build

```
https://snedz.github.io/why-agent/
```

This is a working demo, not a screenshot: the agent, the adversarial benchmark
and the Case Lab all run. The **Case Lab** — seven cases with every claim, lane
receipt, model id, token count and cost — is at
`https://snedz.github.io/why-agent/demo_lab/`.

### 1.3 Text description explaining features and functionality

```
why-agent answers "why did this happen?" about a work item, and cites every
sentence of the answer.

Cards, commits, check runs, deploy receipts, web pages and model reviews all
make claims about a work item. One deterministic reconciler groups the claims
by aspect and returns one of four verdicts — CORROBORATED, PARTIAL, CONFLICTED
or NO EVIDENCE — with a citation on every line. When sources disagree it does
not pick a winner: it shows every side, cited, and refuses to average them.
An aspect nobody reported is reported as a gap, never as a pass, and never as a
plausible explanation.

The Nebius build feeds it five lanes that run on Nebius Token Factory:

  - NVIDIA Nemotron 3 Super writes the reader-facing explanation, and then it
    is machine-checked: every value the narrative states must already exist in
    the evidence. A value that does not is reported, not removed.
  - Nemotron 3 Nano and Nemotron 3 Ultra each produce an independent reviewer
    verdict over the same claims, appended as cited evidence rows. When they
    disagree, both are kept and the disagreement is the finding.
  - Nemotron 3.5 Super VL reads receipt and screenshot images into checkable
    claims — amount, date, counterparty, status.
  - A Tavily live-evidence lane fetches web pages, and a page counts only if
    the claimed value literally appears in it; a page that misses becomes a
    recorded miss, not a dropped row.

Every lane output enters as a claim, never as a verdict, because any
integration can be poisoned. The model may write the prose; it may not add a
fact.

On an adversarial corpus of 14 planted-claim work items, with a truth file the
lanes never see: the deterministic gate scored 14/14 with zero false
approvals. Nemotron 3 Ultra scored 9/14 with one false approval, and Nemotron 3
Nano scored 6/14 with two — the fast lane believed a card that claimed a failed
deploy had shipped. That gap is the architecture, not a bug: the lanes advise,
and the deterministic reconciler decides.

The Case Lab shows seven cases with every claim, every lane receipt, every
model id, token count and cost. Two of the cases are lane-dependent, and a
script proves it by re-reading the original rows and calling the same
reconciler with and without the lane rows.

No dependency. Python 3.10+. Three commands run it with no key and no network:
python3 demo.py, python3 benchmark/score.py --eval-results
benchmark/eval-benchmark-2026-10-28.json, and python3 demo_lab/flip_check.py.
```

### 1.4 URL to the public code repository

```
https://github.com/Snedz/why-agent
```

Public, Apache-2.0 (visible in the repository's About section), all source,
assets and instructions in the tree. The README carries the setup instructions
and a "try it first" block of three commands.

### 1.5 Demonstration video URL

```
PASTE THE YOUTUBE LINK HERE
```

See §6 for the upload. The rules: under three minutes, footage showing the
project functioning, uploaded to and publicly visible on YouTube.

### 1.6 Track

```
Best Apps and Agents
```

The track says: *"Build any app or agent someone would actually use… Power it
with Nemotron models on Nebius through Token Factory. Reach for Nemotron 3
Ultra when you need serious reasoning, and let Nano or Super handle the fast,
everyday calls, so your app stays responsive and your credits stretch
further."* — that is literally the shape of this build: one agent someone would
use, Nemotron 3 Ultra on the contested items, Nano and Super on the everyday
ones.

The other two are plausible and weaker: *Coding and Agentic Engineering* is
fair, but the build is an evidence agent rather than a code-writing agent;
*Personal AI* does not fit — this is a work-item reconciler, not a personal
assistant.

### 1.6a Which awards this entry can be eligible for

| Award | Eligible here? | Why |
|---|---|---|
| Overall (Grand / 2nd / 3rd) | yes | the entry is scored on the four criteria, not on track |
| Best Apps and Agents Track Award — NVIDIA Jetson Orin Nano | yes | this is the track submitted |
| **Best Use of Tavily — $3,000** | **yes** | the live-evidence lane makes a functional runtime call to the Tavily API as part of the solution, which is the eligibility wording verbatim |
| City Winner — $500 | only if the founder attends a Builders & Brews city event | Toronto is one of the 20 listed cities |
| Most Valuable Feedback — $100 + swag | yes, if the feedback field is filled in properly | it is also one of the four equally weighted stage-two criteria |

**Each Project is eligible for one Overall Award OR one Track Award, and one
Bonus Award** — so this entry can be eligible for three prizes at once.

### 1.6b The four equally weighted judging criteria, and where the entry answers each

The stage-two criteria are equally weighted, so it is worth being deliberate
about all four. This table is for the founder's own use, not for pasting.

| Criterion | What in the entry answers it |
|---|---|
| **Technological Implementation** | four pinned NVIDIA Nemotron models behind one OpenAI-compatible Token Factory endpoint; the measured comparison (gate 14/14, Ultra 9/14, Nano 6/14); the cost ledger ($0.033, 0 retries); the MCP surface; the tests that can fail |
| **Design** | a coherent product, not a demo: the four verdicts, the citations, the Case Lab, the MCP server, a README a reader can run — and the honest-labels rule the whole project is built on |
| **Potential Impact** | a real problem for a real audience: "why did this happen?" is answered wrongly, confidently, by single-source agents; the answer shows both sides and cites them |
| **Quality of the Idea** | the non-obvious move: the model lanes are kept and *scored*, and their failures are what keeps them advisory. The idea is that the honest architecture is the one that measures its own model and finds it wanting |

### 1.7 Other links, if the form has a field for them

```
Case Lab:      https://snedz.github.io/why-agent/demo_lab/
Claim map:     https://github.com/Snedz/why-agent/blob/main/docs/CLAIM_MAP.md
Benchmark:     https://github.com/Snedz/why-agent/blob/main/docs/BENCHMARK_RESULTS_2026-10-28.md
Significant update: https://github.com/Snedz/why-agent/blob/main/docs/SIGNIFICANT_UPDATE.md
```

### 1.8 Anything else the form asks that is not covered above

- **Team / organisation** — fill in with the founder's own details. Do not put
  a personal name in the repository; the form is the place for it.
- **"Have you used this technology before?"** and similar — answer truthfully.
  The Nebius Token Factory account was opened for this entry; no Nebius AI
  Cloud compute was used.
- **Prize eligibility / country** — the founder's own details.

---

## 2. The rules-required field: how the NVIDIA models and Token Factory were used

This is the field the rules single out — *"Highlight how you've used NVIDIA
Nemotron or other NVIDIA open source models and where Token Factory accelerated
your workflow and any other Nebius Tools/Services used."* Paste this.

```
Every model call went to Nebius Token Factory at
https://api.tokenfactory.nebius.com/v1/ — one OpenAI-compatible endpoint, with
four NVIDIA open-source models behind it and no per-model glue.

Which NVIDIA model, and what each one was for:

  - nvidia/nemotron-3-super-120b-a12b (Nemotron 3 Super) — writes the
    reader-facing explanation. The prose is the part a model is actually good
    at, and it is the part a checker can catch it getting wrong: every value the
    narrative states is verified against the evidence afterwards, in two passes
    (quoted spans, then every token that looks like a value).
  - nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B (Nemotron 3 Nano) — the fast reviewer
    lane: an independent verdict over the same claims, appended as a cited
    evidence row. This is the everyday call.
  - nvidia/Nemotron-3-Ultra-550b-a55b (Nemotron 3 Ultra) — the deep reviewer
    lane, for the contested items where a cheap answer is not enough. On the
    corpus Ultra and Nano disagreed, and we preserved the disagreement rather
    than averaging it away.
  - nvidia/Nemotron-3.5-Super-VL (Nemotron 3.5 Super VL) — reads receipt and
    screenshot images into checkable claims (amount, date, counterparty,
    status). A null field produces no row at all, and a non-JSON answer raises
    instead of guessing.

Where Token Factory accelerated the workflow:

  - One endpoint, four models, one code path. A tier is a model id, not a
    different integration, so adding the deep lane was a config change. That is
    what made a two-tier review affordable to run on every change instead of
    on a sample.
  - Model ids are pinned to the account, so cost and latency are comparable
    run to run and the ledger is a real measurement rather than an estimate.
  - Per-request billing made the whole adversarial benchmark cheap: 14 items,
    two tiers, two runs, plus the narration checks, cost $0.033 of reviewer-lane
    time with zero retries. The fast tier alone ran 17 reviews for $0.0028.
    At that price we run every lane every time, and we can afford to publish
    the lanes' misses.
  - Cold model load is real: the first call after an idle period can stall. The
    smoke preflight retries once and writes a machine-readable receipt, so a
    stall becomes a receipt instead of a timeout nobody explains.

Other Nebius services used: none. Token Factory only. We did not use Nebius AI
Cloud compute, and we say so rather than implying it.
```

---

## 3. The rules-required field: feedback on Token Factory, AI Cloud and the NVIDIA tools

Paste this.

```
Token Factory had exactly the right shape for this project. One thing about it
cost us real time, and it is worth writing down.

What worked:

  - One OpenAI-compatible base URL for four NVIDIA models. The fast lane and
    the deep lane run the same code and differ only by model id.
  - Per-request billing made a full adversarial benchmark cheap enough to run
    on every change: $0.033 of reviewer-lane time, zero retries. That is what
    let us publish the model lanes' failures instead of quoting a lucky run.
  - The models are open source and their behaviour is scoreable. We can put a
    number on them — 9/14 for Ultra, 6/14 for Nano — instead of a feeling, and
    that number is what decided the architecture.

What was hard:

  - Cold model load. The first call after idle can stall for seconds. We now
    retry once in the preflight and write a machine-readable receipt, so a stall
    shows up as a receipt rather than as a timeout nobody explains. A health
    signal on the model endpoint would have saved that work.
  - Model ids are long and account-specific, and the naming is not uniform
    across tiers (nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B next to
    nvidia/Nemotron-3-Ultra-550b-a55b). We pinned them in one provider profile
    and print them on every lane receipt, which solved it for us; a stable
    alias would have helped.
  - The model response carries no confidence signal we could use to weight the
    two reviewer tiers. So we do not weight them: we cite both and let the
    deterministic gate decide. If Token Factory surfaced a quality or
    confidence hint, that gap would close.

We used Nebius Token Factory only. We did not use Nebius AI Cloud compute for
this entry, so we have no opinion to offer on it.
```

---

## 4. The rules-required field: significant update / pre-existing project

The rules ask for this **only if the project existed before the submission
period** (which opened 2026-08-26). This repository was created **2026-10-27**,
inside the period — so the honest answer to "existed before?" is *no*. Answer
that, and then answer the question the rule is really asking, because the
capability underneath did pre-exist. The full document is
`docs/SIGNIFICANT_UPDATE.md`; paste this summary.

```
This project was created inside the submission period: the repository and the
build are both from 2026-10-27 onward, so it is a new entry rather than an
update to an older one. The capability underneath it did pre-exist, so here is
exactly what is new.

What pre-existed (2026-10-27, the Open Agent Hackathon build): the
evidence-and-verdict discipline, the card/commit/receipt/verdict vocabulary,
the deterministic reconciler and its four verdicts, the claim-shape ledger, and
the MCP surface. That build used a local runtime and two other integrations.

What was added for this submission (2026-10-28 onward):

  - 2026-10-28: the Nebius Token Factory provider profile and four pinned
    NVIDIA Nemotron models; the fast and deep reviewer lanes; the Tavily
    live-evidence lane; the Nemotron Super VL vision lane; the batch-eval
    harness; the smoke preflight; the 14-item adversarial corpus with planted
    truth; the recorded run outputs and the narration-check analysis.
  - 2026-10-29: the MCP server the claim map points at; the generated tier
    ledger; the benchmark gate that can fail; the machine-readable smoke
    receipt; the offline test gaps closed; the Case Lab, generated from the
    corpus with a scripted check proving which cases depend on which lanes;
    this README, the claim map, and the claim-to-receipt table.

The limits, stated plainly: the lanes are slower and less reliable than the
gate (9/14 and 6/14 against 14/14), the narration checker is literal rather
than semantic, and it flags restated system vocabulary alongside genuine
inventions, so every flag is classified rather than hidden. There are no
users, no revenue and no adoption, because there are none. The work item
corpus is synthetic; the lanes ran against real Token Factory models.
```

---

## 5. If the form asks for a one-line tagline

```
An agent that answers why, and cites every sentence — the model may write the
prose, but it may not add a fact.
```

---

## 6. Uploading the video to YouTube

The file is `why-agent-nebius-demo.mp4` at the repository root, 87.54 seconds
(measured, not estimated — `python3 demo_video/render.py` prints it and fails
the build if it reaches three minutes).

1. Open the founder's YouTube Studio → **Create → Upload videos**.
2. Drag in `why-agent-nebius-demo.mp4`.
3. **Visibility: Public.** The rules say publicly visible; `Unlisted` is not
   enough, and a private link cannot be opened by a judge.
4. Title: `why-agent — an agent that answers why, and cites every sentence`.
5. Description (paste):

```
why-agent — Nebius × NVIDIA Global AI Hackathon, Best Apps and Agents track.

An agent that answers "why did this happen?" about a work item, and cites every
sentence of the answer. Cards, commits, check runs, deploy receipts, web pages
and model reviews all make claims; one deterministic reconciler groups them by
aspect and returns CORROBORATED, PARTIAL, CONFLICTED or NO EVIDENCE, and when
the sources disagree it shows every side rather than picking a winner.

Runs on Nebius Token Factory with NVIDIA Nemotron 3 Super, Nemotron 3 Nano,
Nemotron 3 Ultra and Nemotron 3.5 Super VL, plus a Tavily live-evidence lane.
Every lane output enters as a claim, never as a verdict.

On an adversarial corpus of 14 planted-claim work items: the deterministic gate
14/14 with zero false approvals; Nemotron 3 Ultra 9/14; Nemotron 3 Nano 6/14.
That gap is the architecture — the lanes advise, the reconciler decides.

Repo: https://github.com/Snedz/why-agent
Demo: https://snedz.github.io/why-agent/
Case Lab: https://snedz.github.io/why-agent/demo_lab/
```

6. Copy the watch URL and paste it into §1.5.
7. Open the YouTube URL **in a logged-out browser** (or an incognito window) and
   confirm it plays. A link that only plays for the uploader's account fails the
   rule.
8. One line in the repository, so the README points at the video a judge will
   be sent to: in `README.md`, the **Video** row of the submission table
   currently reads
   `https://snedz.github.io/why-agent/why-agent-nebius-demo.mp4` — replace it
   with the YouTube URL and push. The Pages copy stays as it is; it is the
   fallback if YouTube is slow.

The video is also published on GitHub Pages at
`https://snedz.github.io/why-agent/why-agent-nebius-demo.mp4`, so there is a
second URL if YouTube is slow. The rules ask for the YouTube link, so use
YouTube.

---

## 7. What was checked, and what it proved

Every number in the submission answers above is one the repository produced, and
the repository checks that. Run these from a clean clone:

| Command | What it proves |
|---|---|
| `python3 -m pytest -q` | 148 tests, 6 subtests — the suite passes offline |
| `python3 benchmark/score.py --eval-results benchmark/eval-benchmark-2026-10-28.json` | the 14/14 gate, the 9/14 and 6/14 lanes, and the $0.033 |
| `python3 demo_lab/flip_check.py` | two cases really do depend on their lanes |
| `python3 demo_lab/build.py --check` | the Case Lab is generated from the corpus, not typed |
| `python3 -m unittest test_claim_map -v` | every path the README names resolves, and every number it quotes is one the repo produced |

The video is regenerated from the same tools, not edited by hand:
`python3 demo_video/capture.py && python3 demo_video/render.py`.

---

## 8. The honest risks

- **No live Token Factory call in the video.** This Mac has no Token Factory
  key, so the video shows the *recorded* 2026-10-28 run — endpoint, model ids,
  token counts and USD, read from the committed outputs — and the caption says
  so. The committed run outputs are the receipt. If the founder adds
  `NEBIUS_API_KEY` to the environment and re-runs
  `python3 demo_video/capture.py && python3 demo_video/render.py`, the receipt
  shot becomes a **live** call and the caption changes to match. That is the
  only difference between the two videos.
- **"GATE: FAIL" appears at the end of the benchmark output.** It is not the
  deterministic gate failing — that line has zero false approvals. The scorer's
  combined verdict counts the *lanes*' false approvals too, because the run
  fails the criterion "no lane may falsely approve". The video shows the whole
  output and the caption says what the line means.
- **The work items are synthetic.** Every card, receipt, commit and check id is
  invented. The lanes ran against real models; the claims did not come from a
  real customer system. The README says so, and the Case Lab labels every case
  `RECORDED` (the run) and `SYNTHETIC` (the claims).
- **The project is new, not an update.** Answer §4 honestly; do not claim an
  update that did not happen.
- **The "financial or preferential support" clause.** The Sponsor is Nebius
  B.V., and the rules exclude a project developed with financial or preferential
  support from the Sponsor or the Administrator. The free Token Factory credits
  every entrant is given through the contest's own Builder Program are not
  funding, a contract, or a commercial licence — but the line has to hold:
  **no paid Nebius account, no commercial licence, no development contract, no
  investment**, and contest infrastructure only for the prize window. If the
  founder has anything of that kind in place, it needs to be disclosed or
  unwound before submitting.
- **Availability.** The project must stay free of charge and unrestricted until
  the Judging Period ends — **2026-12-23**. The GitHub Pages demo and the Case
  Lab have no login, no analytics and no data collection, so this holds as long
  as the repository and the Pages site stay public. Nothing in this repository
  collects anything from a visitor.
