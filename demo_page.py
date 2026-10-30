#!/usr/bin/env python3
"""Generate the demo page — the URL a judge opens.

The landing page is the first thing the rules ask for ("a URL to a working
demo, hosted application, or test build"), so it has to be true. It used to be
a hand-written page for a different hackathon, which meant a judge landed on a
page that did not describe this entry.

Everything factual on the page is read from the repository's own artefacts:

  * the endpoint and the pinned model ids — `providers.py`
  * the gate and lane scores — the same `score_counts` the scorer uses, over
    the same corpus and the same committed run outputs
  * the cost — `tier_ledger.py`
  * the answer the product gives — a verbatim slice of `demo.py`'s real output

The last one is the point: the excerpt on the page is the tool's actual
output, so it cannot drift into a nicer story than the tool tells.

    python3 demo_page.py            # write demo.html
    python3 demo_page.py --check    # fail if the committed demo.html is stale
"""
from __future__ import annotations

import argparse
import html
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "benchmark"))

import evidence as ev  # noqa: E402
import providers  # noqa: E402
import tier_ledger  # noqa: E402
from benchmark import score as scorer  # noqa: E402

PAGE = HERE / "demo.html"
VIDEO = "why-agent-nebius-demo.mp4"
CASE = "why-alpha"


def corpus_scores() -> tuple[dict, dict]:
    """The deterministic gate's score, and the truth it is scored against."""
    truth = tier_ledger.load_json(tier_ledger.TRUTH)
    items = ev.load_items(str(tier_ledger.CASES))
    claims = ev.load_evidence(str(tier_ledger.CASES))
    got = {k: ev.explain(items, claims, k).confidence() for k in truth}
    return got, truth


def lane_scores() -> dict[str, dict]:
    """Each model's score, from the committed run outputs."""
    truth = tier_ledger.load_json(tier_ledger.TRUTH)
    out: dict[str, dict] = {}
    for path in (tier_ledger.BENCH_RESULTS, tier_ledger.DEMO_RESULTS):
        for entry in tier_ledger.load_json(path).get("results", []):
            item = entry.get("item")
            if item not in truth:
                continue
            for tier, result in (entry.get("tiers") or {}).items():
                out.setdefault(tier, {})[item] = result.get("verdict", "")
    scored = {}
    for tier, got in out.items():
        counts = scorer.score_counts(got, truth)
        scored[tier] = {
            "correct": counts["correct"],
            "total": counts["total"],
            "false_approvals": len(counts["false_approvals"]),
        }
    return scored


def excerpt() -> str:
    """A verbatim slice of the tool's real output."""
    out = subprocess.run([sys.executable, str(HERE / "demo.py")],
                         capture_output=True, text=True, cwd=HERE).stdout
    lines = out.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("CASE ")), None)
    if start is None:
        raise SystemExit("demo_page: demo.py printed no CASE block")
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("CASE ") or lines[i].startswith("===")), len(lines))
    block = lines[start:end]
    while block and not block[-1].strip():
        block.pop()
    return "\n".join(block)


def build() -> str:
    profile = providers.PROFILES["nebius"]
    models = profile["models"]
    got, truth = corpus_scores()
    gate = scorer.score_counts(got, truth)
    lanes = lane_scores()
    bench = tier_ledger.load_json(tier_ledger.BENCH_RESULTS)
    summary = bench.get("summary") or {}
    cost = float(summary.get("total_cost_usd") or 0.0)
    retries = summary.get("retries", 0)
    rows = sum(1 for line in tier_ledger.CASES.read_text(encoding="utf-8").splitlines()
               if line.strip())
    items = len(truth)
    e = html.escape

    def lane_row(tier: str, label: str) -> str:
        s = lanes.get(tier)
        if not s:
            return ""
        return (f"<tr><td>{e(label)}</td><td><code>{e(models[tier])}</code></td>"
                f"<td><b>{s['correct']}/{s['total']}</b></td>"
                f"<td>{s['false_approvals']}</td></tr>")

    deep = lane_row("deep", "Reviewer — deep (the contested items)")
    fast = lane_row("fast", "Reviewer — fast (the everyday call)")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>why-agent — an agent that answers why, and cites every sentence</title>
<meta name="description" content="why-agent reconciles the claims a card, a commit, a check run, a receipt and two Nemotron reviewer models make about a work item, and cites every sentence of the answer. Runs on Nebius Token Factory.">
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; background:#0b0f14; color:#d7e0ea;
         font:16px/1.6 -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif; }}
  main {{ max-width:1040px; margin:0 auto; padding:40px 24px 72px; }}
  h1 {{ font-size:30px; margin:0 0 6px; letter-spacing:-.4px; }}
  h1 span {{ color:#7ee787; }}
  h2 {{ font-size:19px; margin:34px 0 10px; color:#eaf1f8; }}
  p.sub {{ color:#8b97a6; margin:0 0 22px; }}
  p {{ margin:0 0 14px; }}
  video {{ width:100%; border:1px solid #26303c; border-radius:10px; background:#000; display:block; }}
  .row {{ margin-top:18px; display:flex; gap:18px; flex-wrap:wrap; }}
  a {{ color:#7ee787; }}
  .note {{ color:#6e7b8b; font-size:14px; margin-top:14px; }}
  code {{ background:#111820; padding:2px 6px; border-radius:4px; font-size:14px; }}
  pre {{ background:#0e141c; border:1px solid #26303c; border-radius:10px; padding:16px 18px;
         overflow-x:auto; font:13px/1.5 ui-monospace, Menlo, Consolas, monospace;
         color:#cbd6e2; margin:0; }}
  table {{ border-collapse:collapse; width:100%; margin:6px 0 10px; font-size:15px; }}
  th, td {{ border:1px solid #26303c; padding:7px 10px; text-align:left; }}
  th {{ color:#8b97a6; font-weight:600; }}
  .pill {{ display:inline-block; border:1px solid #2c3a4a; border-radius:999px;
           padding:2px 10px; font-size:13px; color:#9fb0c3; margin:0 6px 6px 0; }}
  .good {{ color:#7ee787; }}
</style>
</head>
<body>
<main>
  <h1><span>why-agent</span> — an agent that answers why, and cites every sentence</h1>
  <p class="sub"><b>Nebius × NVIDIA Global AI Hackathon</b> · Best Apps and Agents track ·
     runs on Nebius Token Factory with NVIDIA Nemotron 3</p>

  <div>
    <span class="pill">endpoint {e(profile['base_url'])}</span>
    <span class="pill">Apache-2.0</span>
    <span class="pill">no dependency · Python 3.10+</span>
    <span class="pill">synthetic claims, real model runs</span>
  </div>

  <video controls preload="metadata" poster="why-agent-nebius-poster.png">
    <source src="{VIDEO}" type="video/mp4">
    Your browser cannot play this video. Download it: <a href="{VIDEO}">{VIDEO}</a>
  </video>

  <div class="row">
    <a href="{VIDEO}">Download the video (MP4)</a>
    <a href="demo_lab/">The Case Lab — every claim with its receipt</a>
    <a href="https://github.com/Snedz/why-agent">The repository</a>
    <a href="https://github.com/Snedz/why-agent/blob/main/SUBMISSION.md">The submission packet</a>
  </div>

  <h2>What it does</h2>
  <p>Give it a work item. It reads what the card says, what the receipt says, what the
  commit says, what the check run said, and what two Nemotron reviewer models said —
  and then it tells you what happened, with the citation attached to each line. When
  the sources disagree it does not pick a winner: it shows every side, cites every side,
  and says which source is authoritative for what.</p>

  <h2>The answer it gives</h2>
  <p class="note">This is the tool's real output, not a mock-up — the excerpt is taken
  verbatim from <code>python3 demo.py</code> when this page is generated, so it cannot
  drift into a nicer story than the tool tells.</p>
  <pre class="excerpt">{e(excerpt())}</pre>

  <h2>What the run measured</h2>
  <p>An adversarial corpus of {items} planted-claim work items, with a truth file the
  lanes never see. The deterministic reconciler is the only thing that decides; the
  model lanes contribute claims and an advisory verdict.</p>
  <table>
    <tr><th>Scorer</th><th>Correct</th><th>False approvals</th></tr>
    <tr><td><b>The deterministic reconciler (the gate that ships)</b></td>
        <td><b class="good">{gate['correct']}/{gate['total']}</b></td>
        <td><b class="good">{len(gate['false_approvals'])}</b></td></tr>
    {deep}
    {fast}
  </table>
  <p class="note">The lanes err in both directions — the fast lane believed a card that
  claimed a failed deploy had shipped. That gap is the architecture, not a bug: the
  lanes advise, the reconciler decides. Reviewer-lane cost ${cost:.3f},
  {retries} retries. Reproduce it:
  <code>python3 benchmark/score.py --eval-results benchmark/eval-benchmark-2026-10-28.json</code></p>

  <h2>The models, and what each one is for</h2>
  <table>
    <tr><th>Lane</th><th>Model</th></tr>
    <tr><td>Narration</td><td><code>{e(models['standard'])}</code></td></tr>
    <tr><td>Reviewer — fast (the everyday call)</td><td><code>{e(models['fast'])}</code></td></tr>
    <tr><td>Reviewer — deep (the contested items)</td><td><code>{e(models['deep'])}</code></td></tr>
    <tr><td>Vision — receipt images into claims</td><td><code>{e(models['vision'])}</code></td></tr>
  </table>
  <p class="note">Every lane output enters as a <b>claim</b>, never as a verdict,
  because any integration can be poisoned. The model may write the prose; it may not
  add a fact — every value a narration states is checked against the evidence, and a
  value that is not there is reported, not removed.</p>

  <h2>Run it yourself</h2>
  <pre><code>git clone https://github.com/Snedz/why-agent &amp;&amp; cd why-agent
python3 demo.py                                   # the cases, as a reader sees them
python3 benchmark/score.py --eval-results benchmark/eval-benchmark-2026-10-28.json
python3 demo_lab/flip_check.py                    # proves the model lanes change the verdict</code></pre>

  <h2>Earlier build</h2>
  <div class="row">
    <a href="why-agent-demo.mp4">The October video (MP4, 2:28) — the Open Agent Hackathon build</a>
    <a href="why-agent-deck.pdf">The October slide deck (PDF, 13 pages)</a>
  </div>

  <p class="note">Synthetic data only — no real card, customer or identifier. The
  reconciliation is deterministic Python; the model writes the prose and is checked
  against the evidence. The model runs were real: {items} items, {rows} claim rows,
  recorded 2026-10-28.</p>
</main>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="fail if the committed demo.html is stale")
    args = ap.parse_args(argv)

    body = build()
    current = PAGE.read_text(encoding="utf-8") if PAGE.exists() else None
    if args.check:
        if current != body:
            print(f"STALE: {PAGE.name} is not what demo_page.py generates")
            return 1
        print(f"OK: {PAGE.name} matches the generated output")
        return 0
    PAGE.write_text(body, encoding="utf-8")
    print(f"wrote {PAGE.name} ({len(body)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
