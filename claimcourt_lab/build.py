#!/usr/bin/env python3
"""Build the Claim Court Case Lab from the repository's own artefacts.

A second front door, next to demo_lab/ (which it does not modify): the
claims a customer actually reads — a salon's hours, a listing's materials,
a sale price — checked by the same deterministic reconciler, with the
Nemotron Court transcript (court.py) as the debate view and the original
14-case adversarial benchmark as the rigor section underneath.

    python3 claimcourt_lab/build.py           # write cases/*.json, court.json, index.html
    python3 claimcourt_lab/build.py --check   # fail if the committed files are stale

Same house rule as demo_lab/build.py: generate, don't assert. Every
verdict on the page is computed here by the real reconciler; every score
in the rigor section is computed from the committed benchmark files with
benchmark/score.py's own counting function; the court section renders
court/debate-replay.json as generated. If a number on this page cannot be
traced to a committed file, it does not ship.
"""
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import evidence as ev  # noqa: E402
import providers  # noqa: E402

CC_CASES = ROOT / "claimcourt" / "cases.jsonl"
CC_TRUTH = ROOT / "claimcourt" / "truth.json"
DEBATE = ROOT / "court" / "debate-replay.json"
BENCH_CASES = ROOT / "benchmark" / "cases.jsonl"
BENCH_TRUTH = ROOT / "benchmark" / "truth.json"
BENCH_EVAL = ROOT / "benchmark" / "eval-benchmark-2026-10-28.json"
LAB_CASES = ROOT / "demo_lab" / "cases"
OUT_DIR = HERE / "cases"
COURT_OUT = HERE / "court.json"
INDEX = HERE / "index.html"


def _load_score_module():
    spec = importlib.util.spec_from_file_location(
        "bench_score", ROOT / "benchmark" / "score.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


def as_evidence(rows: list[dict]) -> list[ev.Evidence]:
    return [
        ev.Evidence(
            item_id=r["item_id"], kind=r.get("kind") or "card",
            source=r.get("source") or r.get("kind") or "card",
            locator=r.get("locator", ""), statement=r.get("statement", ""),
            value=r.get("value", ""), observed_at=r.get("observed_at", ""),
            aspect=r.get("aspect", ""),
        )
        for r in rows
    ]


def gate_view(item_id: str, rows: list[dict]) -> dict:
    rec = ev.reconcile(ev.Item(item_id=item_id), as_evidence(rows))
    return {
        "verdict": rec.confidence(),
        "conflicts": [
            {"aspect": a, "values": sorted({c.value for c in g}),
             "citations": [c.citation() for c in g]}
            for a, g in rec.conflicts
        ],
        "agreements": [
            {"aspect": a, "value": g[0].value,
             "citations": [c.citation() for c in g]}
            for a, g in rec.agreements
        ],
        "unknown_aspects": rec.unknown_aspects,
    }


def build_commerce_cases() -> list[dict]:
    rows = read_jsonl(CC_CASES)
    truth = json.loads(CC_TRUTH.read_text(encoding="utf-8"))
    by_item: dict[str, list[dict]] = {}
    for row in rows:
        by_item.setdefault(row["item_id"], []).append(row)

    cases = []
    for item_id in sorted(by_item):
        mine = by_item[item_id]
        card = next(r for r in mine if (r.get("kind") or "card") == "card")
        gate = gate_view(item_id, mine)
        cases.append({
            "case_id": item_id,
            "title": card.get("title", item_id),
            "fixture": card.get("fixture", ""),
            "claim": {
                "statement": card.get("statement", ""),
                "value": card.get("value", ""),
                "source": card.get("source", ""),
                "locator": card.get("locator", ""),
            },
            "verdict": gate["verdict"],
            "frozen_verdict": truth.get(item_id, ""),
            "gate": gate,
            "claims": [
                {
                    "source": r.get("source") or r.get("kind") or "card",
                    "kind": r.get("kind") or "card",
                    "aspect": r.get("aspect") or "",
                    "effective_aspect": ev.Evidence(
                        item_id=item_id, kind=r.get("kind") or "card",
                        source=r.get("source") or "", locator="",
                        statement="", value="",
                        aspect=r.get("aspect", "")).aspect_name,
                    "statement": r.get("statement", ""),
                    "value": r.get("value", ""),
                    "locator": r.get("locator", ""),
                    "observed_at": r.get("observed_at", ""),
                    "fixture": r.get("fixture", ""),
                }
                for r in mine
            ],
            "lanes": {
                "status": "NOT RUN",
                "reason": "no provider key on the build machine; the gate "
                          "verdict above is deterministic and computed from "
                          "the rows shown. Live lanes: RUN_PACK.md step 3.",
            },
            "labels": {
                "data": ("RECORDED — fetched from public pages 2026-10-30"
                         if card.get("fixture") == "recorded"
                         else "SYNTHETIC — planted fixture, labelled as such"),
                "receipt": "claimcourt/cases.jsonl",
            },
        })
    return cases


def build_rigor() -> dict:
    """The benchmark scores, computed from the committed files."""
    score = _load_score_module()
    truth = json.loads(BENCH_TRUTH.read_text(encoding="utf-8"))
    bench_rows = read_jsonl(BENCH_CASES)
    items = ev.load_items(str(BENCH_CASES))
    claims = ev.load_evidence(str(BENCH_CASES))
    gate = {i: ev.explain(items, claims, i).confidence() for i in truth}
    eval_data = json.loads(BENCH_EVAL.read_text(encoding="utf-8"))
    results = {e["item"]: e for e in eval_data["results"]}

    scorers = []
    gate_counts = score.score_counts(gate, truth)
    scorers.append({"name": "Deterministic gate (the reconciler)",
                    "model_id": "evidence.py — no model",
                    **gate_counts})
    for tier, label in (("deep", "Deep lane"), ("fast", "Fast lane")):
        lane = {i: (results.get(i, {}).get("tiers", {}).get(tier, {})
                    .get("verdict", "MISSING")) for i in truth}
        counts = score.score_counts(lane, truth)
        profile = providers.PROFILES["nebius"]["models"]
        scorers.append({"name": f"{label} (advisory)",
                        "model_id": profile[tier], **counts})

    lab_cases = []
    for path in sorted(LAB_CASES.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        lab_cases.append({
            "case_id": case["case_id"],
            "verdict": case["verdict"],
            "headline": case["headline"],
        })

    return {
        "scorers": [
            {"name": s["name"], "model_id": s["model_id"],
             "correct": s["correct"], "total": s["total"],
             "false_approvals": len(s["false_approvals"]),
             "misses": [list(m) for m in s["misses"]]}
            for s in scorers
        ],
        "run": {
            "date": "2026-10-28",
            "corpus": "benchmark/cases.jsonl — 14 items, planted truth",
            "reviewer_lane_cost_usd": eval_data["summary"]["total_cost_usd"],
            "receipt": "benchmark/eval-benchmark-2026-10-28.json",
        },
        "case_lab_cases": lab_cases,
        "case_lab_url": "../demo_lab/index.html",
    }


def render_html(cases: list[dict], debate: dict | None, rigor: dict) -> str:
    e = html.escape
    counts = {}
    for c in cases:
        counts[c["verdict"]] = counts.get(c["verdict"], 0) + 1
    real = sum(1 for c in cases if c["fixture"] == "recorded")
    syn = len(cases) - real
    chart_data = json.dumps([
        {"name": s["name"].split(" (")[0], "correct": s["correct"],
         "false_approvals": s["false_approvals"]}
        for s in rigor["scorers"]
    ])

    out = []
    out.append(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claim Court — every commerce claim, checked against its evidence</title>
<style>
body {{ font-family: ui-monospace, Menlo, monospace; margin: 2rem auto; max-width: 980px; padding: 0 1rem; line-height: 1.5; color: #1a1a1a; }}
h1 {{ font-size: 1.5rem; }} h2.sec {{ margin-top: 2.5rem; border-top: 2px solid #1a1a1a; padding-top: 1rem; }}
.case {{ border: 1px solid #ccc; border-radius: 8px; padding: 1rem 1.25rem; margin: 1.25rem 0; }}
table {{ border-collapse: collapse; width: 100%; font-size: .82rem; }} th, td {{ border: 1px solid #ddd; padding: .35rem .5rem; text-align: left; vertical-align: top; }}
.chip {{ display: inline-block; padding: 0 .5rem; border-radius: 999px; font-weight: 700; font-size: .8rem; }}
.chip.CORROBORATED {{ background: #d9f2d9; color: #14532d; }} .chip.PARTIAL {{ background: #fdf0d5; color: #7a4d00; }}
.chip.CONFLICTED {{ background: #fbdede; color: #8b0000; }} .chip.NO {{ background: #e8e8e8; color: #444; }}
.badge {{ display: inline-block; padding: 0 .5rem; border: 1px solid #888; border-radius: 4px; font-size: .75rem; }}
.badge.synthetic {{ border-color: #8b5cf6; color: #5b21b6; }} .badge.recorded {{ border-color: #0e7490; color: #155e75; }}
.note {{ color: #333; }} .labels {{ background: #f5f5f0; padding: .75rem 1rem; border-radius: 6px; font-size: .9rem; }}
.filters button {{ font: inherit; font-size: .82rem; margin: 0 .25rem .5rem 0; padding: .25rem .6rem; border: 1px solid #888; border-radius: 999px; background: #fff; cursor: pointer; }}
.filters button[aria-pressed="true"] {{ background: #1a1a1a; color: #fff; }}
.flip {{ background: #eef4ff; border-left: 3px solid #4477aa; padding: .5rem .75rem; font-size: .85rem; margin: .5rem 0; }}
.warn {{ background: #fff7e6; border-left: 3px solid #d97706; padding: .5rem .75rem; font-size: .85rem; margin: .5rem 0; }}
code {{ background: #f0f0f0; padding: 0 .25rem; }} details {{ margin-top: .5rem; }} summary {{ cursor: pointer; font-size: .88rem; }}
</style></head><body>
<h1>Claim Court</h1>
<p><b>Every commerce claim, checked against its evidence.</b> The claims below are the ones a
customer actually reads — a salon's hours and phone number, a listing's materials, a sale
price. Each is treated the way why-agent treats a work item: sources make claims, one
deterministic reconciler groups them by aspect and returns <b>CORROBORATED</b>,
<b>PARTIAL</b>, <b>CONFLICTED</b>, or <b>NO EVIDENCE</b>. Model lanes advise; the gate decides.
Tonight's sitting: <b>{len(cases)} claims — {counts.get("CONFLICTED", 0)} CONFLICTED,
{counts.get("PARTIAL", 0)} PARTIAL, {counts.get("CORROBORATED", 0)} CORROBORATED</b>
(computed by the reconciler from the rows on this page, not arranged).</p>
<div class="labels"><b>Labels, honestly:</b> {real} cases are <b>RECORDED</b> — fetched
2026-10-30 from the public pages of our own pilot business (Shenail Hair Salon &amp; Nail Bar,
Niagara Falls) and the directories that list it; their conflicts are real. {syn} cases are
<b>SYNTHETIC FIXTURES</b>, labelled in every title, modelled on real listing patterns; no
fixture names a real third-party seller. The gate verdicts are deterministic and were
computed tonight. <b>Reviewer lanes have NOT run over the commerce corpus yet</b> (no
provider key on the build machine — see RUN_PACK.md), and the Nemotron Court's rebuttal round
below is likewise NOT RUN. The page does not quote a lane verdict that does not exist.</div>

<h2 class="sec">1 · The claims</h2>
<div class="filters" role="group" aria-label="Filter cases">
<button data-filter="all" aria-pressed="true">All {len(cases)}</button>
<button data-filter="recorded" aria-pressed="false">Recorded (real) {real}</button>
<button data-filter="synthetic" aria-pressed="false">Synthetic fixtures {syn}</button>
<button data-filter="CONFLICTED" aria-pressed="false">CONFLICTED {counts.get("CONFLICTED", 0)}</button>
<button data-filter="PARTIAL" aria-pressed="false">PARTIAL {counts.get("PARTIAL", 0)}</button>
<button data-filter="CORROBORATED" aria-pressed="false">CORROBORATED {counts.get("CORROBORATED", 0)}</button>
</div>
<p class="note" id="showing">Showing {len(cases)} of {len(cases)} cases.</p>""")

    for case in cases:
        chip_cls = "NO" if case["verdict"] == "NO EVIDENCE" else case["verdict"]
        badge_cls = "recorded" if case["fixture"] == "recorded" else "synthetic"
        badge_txt = "RECORDED" if case["fixture"] == "recorded" else "SYNTHETIC FIXTURE"
        out.append(f'<section class="case cc-case" data-fixture="{e(case["fixture"])}" '
                   f'data-verdict="{e(case["verdict"])}" id="{e(case["case_id"])}">')
        out.append(f"<h3>{e(case['title'])} — <span class=\"chip {chip_cls}\">"
                   f"{e(case['verdict'])}</span> <span class=\"badge {badge_cls}\">"
                   f"{badge_txt}</span></h3>")
        out.append(f"<p class=\"note\"><b>The claim:</b> {e(case['claim']['statement'])} "
                   f"— <code>{e(case['claim']['value'])}</code> "
                   f"(<code>{e(case['claim']['locator'])}</code>)</p>")
        gate = case["gate"]
        if gate["conflicts"]:
            for c in gate["conflicts"]:
                vals = " vs ".join(f"<code>{e(v)}</code>" for v in c["values"])
                out.append(f"<div class=\"flip\"><b>Conflict on {e(c['aspect'])}:</b> "
                           f"{vals} — cited: {e('; '.join(c['citations']))}.</div>")
        if gate["unknown_aspects"]:
            out.append(f"<p class=\"note\">Aspects nobody spoke to: "
                       f"<b>{e(', '.join(gate['unknown_aspects']))}</b> — an unknown is "
                       f"not a pass, so this cannot read CORROBORATED.</p>")
        if not gate["conflicts"] and not gate["unknown_aspects"]:
            out.append("<p class=\"note\">Every expected aspect is spoken to and no two "
                       "sources disagree — the only shape that earns CORROBORATED.</p>")
        out.append("<details><summary>Evidence rows (each carries its receipt)</summary>")
        out.append("<table><tr><th>Source</th><th>Aspect</th><th>Statement</th>"
                   "<th>Value</th><th>Receipt</th></tr>")
        for claim in case["claims"]:
            out.append(
                f"<tr><td>{e(claim['source'])}</td><td>{e(claim['effective_aspect'])}</td>"
                f"<td>{e(claim['statement'])}</td><td><code>{e(claim['value'])}</code></td>"
                f"<td>{e(claim['locator'])}</td></tr>")
        out.append("</table></details>")
        out.append(f"<p class=\"note\">Reviewer lanes over this corpus: <b>NOT RUN</b> — "
                   f"{e(case['lanes']['reason'])}</p>")
        out.append("</section>")

    # ---- Section 2: the Court -------------------------------------------
    out.append('<h2 class="sec">2 · Nemotron Court — the lanes, cross-examined</h2>')
    if debate is None:
        out.append("<p class=\"note\">No transcript yet — run "
                   "<code>python3 court.py</code> to generate court/debate-replay.json.</p>")
    else:
        s = debate["summary"]
        out.append(f"<p>The reviewer tiers' Round 1 verdicts below are <b>RECORDED</b> from "
                   f"the 2026-10-28 live Token Factory run. On <b>{s['items_with_disagreement']} "
                   f"of {s['items']} items</b> a lane disagreed with the deterministic gate; "
                   f"every disagreement is preserved with its citations, never averaged. The "
                   f"<b>citation audit</b> is computed, not narrated: for each lane verdict it "
                   f"lists the evidence that verdict fails to account for. The rebuttal round "
                   f"is <b>NOT RUN</b> — it is a live model round and no provider key is present "
                   f"tonight (RUN_PACK.md, step 4).</p>")
        for item in debate["items"]:
            gate = item["gate"]
            out.append(f'<section class="case" id="court-{e(item["item"])}">')
            out.append(f"<h3>{e(item['item'])} — gate: <b>{e(gate['verdict'])}</b>"
                       + (f" · planted truth <b>{e(item['planted_truth'])}</b>"
                          if item.get("planted_truth") else "") + "</h3>")
            positions = []
            for p in item["round1"]:
                if p.get("status") == "recorded":
                    positions.append(
                        f"{e(p['tier'])} ({e(p['model_id'])}): <b>{e(p['verdict'])}</b>"
                        f" (${p['cost_usd']:.4f})"
                        + (" — agrees with the gate" if p["agrees_with_gate"]
                           else " — <b>disagrees with the gate</b>"))
                else:
                    positions.append(f"{e(p['tier'])}: <b>not run</b> — {e(p['reason'])}")
            out.append(f"<p class=\"note\">Round 1 (recorded): {'; '.join(positions)}.</p>")
            for a in item["citation_audit"]:
                if a["supported"]:
                    out.append(f"<p class=\"note\">Audit — {e(a['tier'])}: verdict "
                               f"<b>supported</b>; it answers every conflict and "
                               f"missing aspect the gate found.</p>")
                else:
                    un = "; ".join(
                        f"{u['kind']} on {u['aspect']}"
                        + (f" ({'; '.join(u['citations'])})" if u["citations"] else "")
                        for u in a["unanswered"])
                    out.append(f"<div class=\"warn\">Audit — {e(a['tier'])}: verdict "
                               f"<b>not supported</b> as stated. Unanswered: {e(un) if un else 'the gate\u2019s verdict itself — a preserved disagreement'}.</div>")
            if item["exhibits"]:
                ex = "; ".join(
                    f"{e(x['lane'])} read <code>{e(x['locator'])}</code> → "
                    f"<code>{e(x['value']) or '(no literal match)'}</code>"
                    for x in item["exhibits"])
                out.append(f"<p class=\"note\">Exhibits: {ex}.</p>")
            rb = item["rebuttal_round"]
            out.append(f"<p class=\"note\">Rebuttal round: <b>{e(rb['status'])}</b> — "
                       f"{e(rb['reason'])}</p>")
            out.append("</section>")

    # ---- Section 3: rigor ----------------------------------------------
    out.append('<h2 class="sec">3 · Rigor — the adversarial benchmark underneath</h2>')
    out.append(f"<p>Before it judged a single commerce claim, the gate was scored on a "
               f"planted-truth adversarial corpus (agent-work claims, recorded live run "
               f"{e(rigor['run']['date'])}, reviewer-lane cost "
               f"${rigor['run']['reviewer_lane_cost_usd']:.3f}). The lanes' false approvals "
               f"are published, not hidden — they are the evidence for keeping lanes "
               f"advisory. Scores below are computed from the committed files by the same "
               f"counting rule as <code>benchmark/score.py</code>.</p>")
    out.append('<div id="bench-chart" style="width:100%;height:260px"></div>')
    out.append("<table><tr><th>Scorer</th><th>Model</th><th>Correct</th>"
               "<th>False approvals</th></tr>")
    for s in rigor["scorers"]:
        out.append(f"<tr><td>{e(s['name'])}</td><td><code>{e(s['model_id'])}</code></td>"
                   f"<td><b>{s['correct']}/{s['total']}</b></td>"
                   f"<td>{s['false_approvals']}</td></tr>")
    out.append("</table>")
    out.append("<p class=\"note\">The original agent-work cases, with lane receipts and "
               "narration checks, are in the first Case Lab: "
               f"<a href=\"{e(rigor['case_lab_url'])}\">demo_lab/index.html</a> — "
               + "; ".join(f"{e(c['case_id'])} ({e(c['verdict'])})"
                           for c in rigor["case_lab_cases"]) + ".</p>")

    out.append(f"""<p>Generated by <code>claimcourt_lab/build.py</code> from
<code>claimcourt/cases.jsonl</code>, <code>court/debate-replay.json</code> and
<code>benchmark/</code>. The builder makes no network request; the only external call on
this page is the optional ECharts CDN chart, and the table above carries the same numbers
without it.</p>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<script>
(function () {{
  var data = {chart_data};
  if (window.echarts) {{
    var chart = echarts.init(document.getElementById('bench-chart'));
    chart.setOption({{
      title: {{ text: 'Adversarial benchmark — correct verdicts of 14 (recorded 2026-10-28)' }},
      tooltip: {{}},
      xAxis: {{ type: 'value', max: 14 }},
      yAxis: {{ type: 'category', data: data.map(function (d) {{ return d.name; }}).reverse() }},
      series: [{{ type: 'bar', data: data.map(function (d) {{ return d.correct; }}).reverse(),
                  label: {{ show: true, position: 'right' }} }}]
    }});
  }}
  var buttons = document.querySelectorAll('.filters button');
  var cards = document.querySelectorAll('.cc-case');
  var showing = document.getElementById('showing');
  buttons.forEach(function (btn) {{
    btn.addEventListener('click', function () {{
      buttons.forEach(function (b) {{ b.setAttribute('aria-pressed', 'false'); }});
      btn.setAttribute('aria-pressed', 'true');
      var f = btn.getAttribute('data-filter');
      var n = 0;
      cards.forEach(function (card) {{
        var show = f === 'all' || card.getAttribute('data-fixture') === f ||
                   card.getAttribute('data-verdict') === f;
        card.style.display = show ? '' : 'none';
        if (show) n++;
      }});
      showing.textContent = 'Showing ' + n + ' of ' + cards.length + ' cases.';
    }});
  }});
}})();
</script>
</body></html>""")
    return "\n".join(out) + "\n"


def generate() -> list[tuple[Path, str]]:
    cases = build_commerce_cases()
    debate = (json.loads(DEBATE.read_text(encoding="utf-8"))
              if DEBATE.exists() else None)
    rigor = build_rigor()
    page = render_html(cases, debate, rigor)

    written = []
    for case in cases:
        path = OUT_DIR / f"{case['case_id']}.json"
        body = json.dumps(case, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        written.append((path, body))
    if debate is not None:
        body = json.dumps(debate, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        written.append((COURT_OUT, body))
    written.append((INDEX, page))
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="fail if the committed files are stale")
    args = ap.parse_args(argv)

    written = generate()
    stale = []
    for path, body in written:
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == body:
            continue
        stale.append(path.relative_to(ROOT))
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")

    if args.check:
        if stale:
            for name in stale:
                print(f"STALE: {name}")
            print(f"{len(stale)} file(s) differ from the generated output")
            return 1
        print(f"OK: {len(written)} generated file(s) match the committed output")
        return 0

    for path, body in written:
        print(f"wrote {path.relative_to(ROOT)} ({len(body)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
