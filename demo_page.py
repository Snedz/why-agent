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
import json
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

# The workbench runs the reconciler in the reader's tab. These are the two
# files that make that true, and they are read from disk rather than pasted
# into this generator, so there is exactly one copy of each.
RECONCILER_JS = HERE / "demo_lab" / "reconciler.js"
WORKBENCH_JS = HERE / "demo_lab" / "workbench.js"

# Both corpora, labelled, because a reader should be able to see which file a
# claim came from. `benchmark/cases.jsonl` is the adversarial corpus the scores
# above are measured on; `evidence/items.jsonl` is the one `demo.py` prints.
# Labelled by the file the rows come from, not by a count: two of these
# corpora hold items with no claim rows at all (a card and nothing else), so a
# number in the label disagrees with the length of the list under it.
CORPORA = (
    ("benchmark", "The adversarial corpus — benchmark/cases.jsonl", "cases.jsonl"),
    ("demo", "The demo corpus — evidence/items.jsonl", "items.jsonl"),
    ("claimcourt", "The commerce corpus — claimcourt/cases.jsonl", "cases.jsonl"),
)


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


def _case_lab() -> tuple[dict, dict]:
    """The Case Lab's case notes and its map of lane sources.

    Read from `demo_lab/build.py` rather than copied here: the two pages show
    the same corpus, so they must agree about which rows come from a model
    lane — that is the set the reader is invited to remove to see the flip.
    """
    try:
        sys.path.insert(0, str(HERE / "demo_lab"))
        import build as lab_build  # noqa: PLC0415 - sibling generator, on use
    except ImportError:
        return {}, {}
    return ({c["case_id"]: c for c in lab_build.CASES},
            dict(lab_build.LANE_SOURCES))


def _jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        row = json.loads(line)
        kind = row.get("kind") or "card"
        rows.append({
            "item_id": row["item_id"], "kind": kind,
            "source": row.get("source", kind),
            "locator": row.get("locator", ""),
            "statement": row.get("statement", ""),
            "value": row.get("value", ""),
            "aspect": row.get("aspect", ""),
            "title": row.get("title", ""),
        })
    return rows


def workbench_payload() -> dict:
    """Every item in both corpora, with its claims, as data for the page."""
    notes, lanes = _case_lab()
    paths = {"benchmark": tier_ledger.CASES,
             "demo": HERE / "evidence" / "items.jsonl",
             # The commerce corpus: the same rows and the same reconciler, on
             # claims a shopper reads rather than a card a build system wrote.
             # `claimcourt/score.py` already holds its verdicts to the frozen
             # file; including it here means the browser is held to them too.
             "claimcourt": HERE / "claimcourt" / "cases.jsonl"}
    items: list[dict] = []
    corpora: list[dict] = []

    for corpus_id, label, _name in CORPORA:
        path = paths[corpus_id]
        corpora.append({"id": corpus_id, "label": label,
                        "path": str(path.relative_to(HERE))})
        by_item: dict[str, dict] = {}
        for row in _jsonl(path):
            item_id = row["item_id"]
            if item_id not in by_item:
                note = notes.get(item_id, {})
                by_item[item_id] = {
                    "id": item_id, "corpus": corpus_id, "title": "",
                    "headline": note.get("headline", ""),
                    "note": note.get("note", ""), "rows": [],
                }
                items.append(by_item[item_id])
            if row["kind"] == "card" and row["title"]:
                by_item[item_id]["title"] = row["title"]
            by_item[item_id]["rows"].append({k: v for k, v in row.items()
                                             if k != "title"})

    return {
        "items": items, "corpora": corpora, "lane_sources": lanes,
        "item_count": len(items),
        "row_count": sum(len(i["rows"]) for i in items),
    }


# Plain strings, not f-strings: CSS and JavaScript are full of braces, and
# doubling every one of them to satisfy an f-string is how a page acquires a
# stray `{{` that nobody notices until it renders.
WORKBENCH_CSS = """
  /* The workbench: the reconciler, running in the reader's tab. */
  .wb { display:grid; grid-template-columns:1.45fr 1fr; gap:16px; align-items:start;
        margin-top:8px; }
  @media (max-width:900px) { .wb { grid-template-columns:1fr; } }
  /* min-width:0 on a grid item: without it the item refuses to shrink below
     its content's min-content width, and a wide table inside it widens the
     whole page instead of scrolling. */
  .wb-panel { background:#0e141c; border:1px solid #26303c; border-radius:10px;
              padding:14px 15px 12px; min-width:0; }
  .wb-picker { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:11px; }
  .wb-picker label { font-size:13px; color:#8b97a6; }
  .wb select, .wb input, .wb button { font:inherit; }
  .wb select { background:#111820; color:#cbd6e2; border:1px solid #26303c;
               border-radius:7px; padding:5px 7px; max-width:100%; }
  .wb button { background:#16202b; color:#cbd6e2; border:1px solid #2c3a4a;
               border-radius:7px; padding:5px 10px; font-size:13px; cursor:pointer; }
  .wb button:hover { background:#1d2a37; }
  .wb-headline { font-size:15px; color:#eaf1f8; margin:0 0 3px; font-weight:600; }
  .wb-meta { font-size:12px; color:#6e7b8b; margin:0 0 10px; }
  .wb-note { font-size:13px; color:#9fb0c3; background:#111820; border-left:3px solid #2c3a4a;
             padding:9px 11px; border-radius:0 7px 7px 0; margin:0 0 11px; }
  /* Six columns will not fit a phone. Two things go wrong if the table is
     allowed to decide: it pushes the page wide and every paragraph beside it
     breaks, and if it is squeezed instead, the claims column collapses to one
     word per line. So the table keeps a legible width and scrolls inside its
     own box — nothing is hidden and nothing is squeezed. */
  .wb-scroll { overflow-x:auto; -webkit-overflow-scrolling:touch; min-width:0; }
  .wb-table { border-collapse:collapse; width:100%; table-layout:fixed; font-size:12.5px;
              margin:0; min-width:560px; }
  .wb-table th { border:none; border-bottom:1px solid #26303c; color:#8b97a6; font-size:10.5px;
                 text-transform:uppercase; letter-spacing:.06em; padding:0 5px 6px;
                 text-align:left; }
  .wb-table td { border:none; border-bottom:1px solid #1a232d; padding:5px;
                 vertical-align:top; color:#cbd6e2; }
  .wb-table tr.off td { opacity:.36; }
  .wb-table td.stmt { color:#9fb0c3; font-size:11.5px; }
  .wb-table td.loc { color:#5f6b7a; font-size:10px; word-break:break-all; }
  .wb-table .kind { color:#6e7b8b; font-size:10.5px; }
  .wb-table .lane { color:#c8a2e0; font-weight:600; }
  .wb-table input.val { width:100%; background:transparent; border:1px solid transparent;
                        border-radius:5px; padding:2px 4px; color:#cbd6e2;
                        font-family:ui-monospace, Menlo, Consolas, monospace; font-size:12.5px; }
  .wb-table input.val:hover { border-color:#26303c; }
  .wb-table input.val:focus { outline:none; border-color:#3d6b4e; background:#101a15; }
  .wb-table select.asp { border:1px solid transparent; background:transparent; padding:1px 2px;
                         font-size:12px; color:#cbd6e2; }
  .wb-table select.asp:hover { border-color:#26303c; }
  .wb-table select.asp.inherited { font-style:italic; color:#9fb0c3; }
  .verdict { font-size:25px; font-weight:700; letter-spacing:-.4px; line-height:1.1;
             margin:0 0 3px; font-family:ui-monospace, Menlo, Consolas, monospace; }
  .v-CORROBORATED { color:#7ee787; }
  .v-PARTIAL { color:#e3b341; }
  .v-CONFLICTED { color:#ff7b72; }
  .v-NOEVIDENCE { color:#9fb0c3; }
  .wb-says { font-size:12.5px; color:#8b97a6; margin:0 0 13px; }
  .wb-says b { color:#eaf1f8; }
  .wb .quiet { color:#6e7b8b; font-size:11.5px; }
  .wb .sec { border-top:1px solid #1f2833; padding-top:10px; margin-top:10px; }
  .wb .sec:first-of-type { border-top:none; padding-top:0; margin-top:0; }
  .wb .sech { font-size:10.5px; text-transform:uppercase; letter-spacing:.08em; color:#8b97a6;
              font-weight:650; margin:0 0 6px; }
  .wb .grp { margin:0 0 9px; }
  .wb .aspname { font-size:12px; font-weight:650; color:#cbd6e2; }
  .wb .cl { font-size:11.5px; color:#9fb0c3; margin:2px 0 0 10px; }
  .wb .cl .who { color:#eaf1f8; font-weight:600; }
  .wb .val2 { background:#16202b; padding:0 4px; border-radius:4px;
              font-family:ui-monospace, Menlo, Consolas, monospace; }
  .wb .cite { color:#5f6b7a; font-size:10.5px; }
  .wb .gap { font-size:11.5px; color:#e3b341; margin:2px 0; }
  .wb-flip { margin-top:11px; padding:9px 11px; background:#101a24; border:1px solid #24405c;
             border-radius:7px; font-size:12px; color:#9fb0c3; }
  .wb-flip b { color:#8cc4f0; }
"""

WORKBENCH_HTML = """
  <h2 id="workbench">Try it — the reconciler, running in this tab</h2>
  <p class="note">Pick a case, untick a source, or type a different value into a claim.
  The verdict on the right is recomputed from what is on screen: this is the reconciler
  the Python runs, not a video of it. No key, no server, no network — the corpus and the
  reconciler are both in this page. The JavaScript is a port of
  <code>evidence.reconcile()</code>, and <code>test_demo_app.py</code> runs both over every
  item in both corpora and fails if a verdict, a conflict, a gap or an aspect differs.</p>

  <div class="wb">
    <div class="wb-panel">
      <div class="wb-picker">
        <label for="wb-case">Case</label>
        <select id="wb-case"></select>
        <button id="wb-lanes" hidden></button>
        <button id="wb-reset">Reset</button>
        <button id="wb-add">Add a claim</button>
      </div>
      <p class="wb-headline" id="wb-headline"></p>
      <p class="wb-meta" id="wb-meta"></p>
      <p class="wb-note" id="wb-note" hidden></p>
      <div class="wb-scroll">
      <table class="wb-table">
        <colgroup>
          <col style="width:24px"><col style="width:66px"><col style="width:88px">
          <col style="width:126px"><col><col style="width:88px">
        </colgroup>
        <thead><tr>
          <th></th><th>Source</th><th>Aspect</th><th>Value</th>
          <th>What it claims</th><th>Locator</th>
        </tr></thead>
        <tbody id="wb-rows"></tbody>
      </table>
      </div>
    </div>
    <div class="wb-panel">
      <p class="verdict" id="wb-verdict">&mdash;</p>
      <p class="wb-says" id="wb-says"></p>
      <div class="sec" id="wb-conflict"></div>
      <div class="sec" id="wb-agree"></div>
      <div class="sec" id="wb-gap"></div>
      <div class="sec" id="wb-unexp"></div>
      <div class="wb-flip" id="wb-flip" hidden></div>
    </div>
  </div>

  <noscript><p class="note">JavaScript is off, so the workbench cannot run. The
  <a href="demo_lab/">Case Lab</a> is pre-rendered, shows the same cases with every
  receipt, and needs no JavaScript.</p></noscript>

  <script>window.__WHY_AGENT__ = __WORKBENCH_DATA__;</script>
  <script>__RECONCILER_JS__</script>
  <script>__WORKBENCH_JS__</script>
"""


def _inline_workbench(page: str) -> str:
    """Put the corpus and the two scripts into the page.

    Inlined rather than fetched: the page must make no network request, so a
    judge can open it from a saved file, offline, and the workbench still runs.
    `</` is escaped inside the JSON because a claim value containing `</script>`
    would otherwise close the block it lives in.
    """
    blob = json.dumps(workbench_payload(), ensure_ascii=False).replace("</", "<\\/")
    reconciler = RECONCILER_JS.read_text(encoding="utf-8")
    workbench = WORKBENCH_JS.read_text(encoding="utf-8")
    return (page
            .replace("__WORKBENCH_DATA__", blob)
            .replace("__RECONCILER_JS__", reconciler)
            .replace("__WORKBENCH_JS__", workbench))


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
    # Counted from the corpus, not typed: how much of the evidence the live-web
    # lane actually contributed. The entry claims the Tavily bonus, so the page
    # a judge opens should show that the lane is real and what it added.
    tavily = [r for r in _jsonl(tier_ledger.CASES) if r["source"] == "tavily"]
    tavily_rows = len(tavily)
    tavily_items = len({r["item_id"] for r in tavily})
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

    page = f"""<!DOCTYPE html>
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
{WORKBENCH_CSS}
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
    <a href="demo_lab/claimcourt/">The Claim Court — the same reconciler on commerce claims</a>
    <a href="https://github.com/Snedz/why-agent">The repository</a>
    <a href="https://github.com/Snedz/why-agent/blob/main/SUBMISSION.md">The submission packet</a>
  </div>

{WORKBENCH_HTML}

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

  <h2>The lanes, and what each one is for</h2>
  <table>
    <tr><th>Lane</th><th>What runs it</th></tr>
    <tr><td>Narration</td><td><code>{e(models['standard'])}</code></td></tr>
    <tr><td>Reviewer — fast (the everyday call)</td><td><code>{e(models['fast'])}</code></td></tr>
    <tr><td>Reviewer — deep (the contested items)</td><td><code>{e(models['deep'])}</code></td></tr>
    <tr><td>Vision — receipt images into claims</td><td><code>{e(models['vision'])}</code></td></tr>
    <tr><td>Live evidence — the web, queried at run time</td>
        <td>Tavily search API, via <code>tavily_lane.py</code></td></tr>
  </table>
  <p class="note"><b>The live-web lane queries Tavily at run time</b>, and a page becomes
  evidence only if the claimed value literally appears in it — {tavily_rows} rows across
  {tavily_items} of the corpus items are Tavily's, and one of them records a <i>miss</i>
  rather than dropping the row. A page that does not match cannot quietly become a pass.</p>
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
    return _inline_workbench(page)


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
