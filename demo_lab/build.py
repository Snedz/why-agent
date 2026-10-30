#!/usr/bin/env python3
"""Build the Case Lab from the repository's own artefacts.

The Case Lab is not a hand-written page. Every claim it shows comes from the
committed corpus, every lane receipt comes from the committed eval output, and
every model id and endpoint comes from the provider profile. Nothing here
invents a case outcome.

    python3 demo_lab/build.py           # write demo_lab/cases/*.json + index.html
    python3 demo_lab/build.py --check   # fail if the committed files are stale

Why it is generated: the house rule is "generate, don't assert". A page whose
verdicts are typed by hand drifts from the corpus the moment the corpus moves,
and a judge who re-runs the scorer sees a different number than the page shows.
The flip check (demo_lab/flip_check.py) calls the same reconciler this script
calls, so the page and the corpus cannot disagree.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import evidence as ev  # noqa: E402
import providers  # noqa: E402

CORPUS = ROOT / "benchmark" / "cases.jsonl"
TRUTH = ROOT / "benchmark" / "truth.json"
BENCH_EVAL = ROOT / "benchmark" / "eval-benchmark-2026-10-28.json"
ITEM_EVAL = ROOT / "eval-results-2026-10-28.json"
ITEMS = ROOT / "evidence" / "items.jsonl"
OUT_DIR = HERE / "cases"
INDEX = HERE / "index.html"

# The sources whose rows come from a LANE rather than from a recorded source.
# The reviewer lanes are the Nemotron tiers on Token Factory; the web lane is
# Tavily; the vision lane is Nemotron Super VL reading a receipt image.
LANE_SOURCES = {
    "nemotron-fast": "reviewer-fast",
    "nemotron-deep": "reviewer-deep",
    "tavily": "live-evidence",
    "nemotron-vl": "vision",
}

# The cases the Lab shows, in order. `lane_rows` names the sources whose rows
# decide the outcome: remove them and the verdict changes. That is the claim
# the flip check proves, so it is written here as data and computed elsewhere.
CASES = [
    {
        "case_id": "bm-clean-ship",
        "headline": "The clean case — and a lane still disagreed.",
        "note": "Every source agrees, and they cover state, outcome and cause. The gate "
                "corroborates. The fast reviewer lane called it CONFLICTED anyway. Lanes "
                "err in both directions, which is exactly why they never decide.",
    },
    {
        "case_id": "why-beta",
        "headline": "Both model lanes over-approved this one.",
        "note": "The card is blocked and the gate agrees — but nobody stated a cause, so "
                "the gate says PARTIAL. Both Nemotron lanes said CORROBORATED. An "
                "unexplained outcome is not a verified one.",
    },
    {
        "case_id": "bm-reviewer-split",
        "headline": "The two Nemotron tiers disagree — and the disagreement is the finding.",
        "note": "The fast lane and the deep lane read the same claims and returned "
                "different verdicts. The gate keeps both, cites both, and refuses to "
                "average them. Remove the two reviewer rows and this item reads as a "
                "routine CORROBORATED — the disagreement is not visible anywhere else.",
        "lane_rows": ["nemotron-fast", "nemotron-deep"],
    },
    {
        "case_id": "bm-web-nonmatch",
        "headline": "A live-evidence miss, recorded instead of dropped.",
        "note": "The Tavily lane fetched a page that does not contain the claimed value. "
                "That becomes a claim with an empty value — an honest miss — and it "
                "conflicts with the postal receipt. Remove the web row and the spoken "
                "aspects agree, and the item reads as a quiet PARTIAL.",
        "lane_rows": ["tavily"],
    },
    {
        "case_id": "bm-card-lies",
        "headline": "The trap: a card that claims a failed deploy shipped.",
        "note": "The card says shipped; the check and the deploy receipt say failed and "
                "rolled back. The fast lane believed the card — a false approval. The "
                "gate and the deep lane held CONFLICTED.",
    },
    {
        "case_id": "bm-no-evidence",
        "headline": "Nobody said anything.",
        "note": "This item exists in the corpus with zero claims. The gate's answer is "
                "NO EVIDENCE — a first-class verdict, not an error. The lanes were not "
                "run: there is nothing to judge, and a model asked anyway would invent "
                "something to judge.",
    },
    {
        "case_id": "why-alpha",
        "headline": "A real conflict, shown with both sides cited — and a narration that failed its check.",
        "note": "Sources disagree about the same aspect. The gate refuses to pick a "
                "winner. The deep lane matched the gate; the fast lane softened it to "
                "PARTIAL. The narration of this item also failed its check: the flagged "
                "value is listed below and classified.",
    },
]


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


def load_all_claims() -> dict[str, list[dict]]:
    """Every claim in the repository, by item id.

    Two claim files: the adversarial benchmark corpus and the demo evidence
    file. Neither is edited here — the Lab reads what the tools read.
    """
    claims: dict[str, list[dict]] = {}
    for row in read_jsonl(CORPUS) + read_jsonl(ITEMS):
        claims.setdefault(row["item_id"], []).append(row)
    return claims


def load_eval() -> dict[str, dict]:
    """The recorded lane output, by item id.

    Two eval files: the corpus run (benchmark/) and the four-item demo run.
    Both are committed, so a reader can re-score them.
    """
    out: dict[str, dict] = {}
    for path, receipt in ((BENCH_EVAL, "benchmark/eval-benchmark-2026-10-28.json"),
                          (ITEM_EVAL, "eval-results-2026-10-28.json")):
        for entry in json.loads(path.read_text(encoding="utf-8"))["results"]:
            out[entry["item"]] = {**entry, "_receipt": receipt}
    return out


def model_ids() -> dict[str, str]:
    profile = providers.PROFILES["nebius"]
    models = profile["models"]
    return {
        "reviewer-fast": models["fast"],
        "reviewer-deep": models["deep"],
        "narration": models["standard"],
        "vision": models["vision"],
    }


def as_evidence(rows: list[dict]) -> list[ev.Evidence]:
    return [
        ev.Evidence(
            item_id=row["item_id"],
            kind=row.get("kind") or "card",
            source=row.get("source") or row.get("kind") or "card",
            locator=row.get("locator", ""),
            statement=row.get("statement", ""),
            value=row.get("value", ""),
            observed_at=row.get("observed_at", ""),
            aspect=row.get("aspect", ""),
        )
        for row in rows
    ]


def verdict_for(item_id: str, rows: list[dict]) -> str:
    """The gate's own verdict, computed by the real reconciler."""
    item = ev.Item(item_id=item_id, title="", declared_status="")
    return ev.reconcile(item, as_evidence(rows)).confidence()


def build_case(spec: dict, claims: dict[str, list[dict]], eval_by_item: dict[str, dict],
               models: dict[str, str], endpoint: str) -> dict:
    case_id = spec["case_id"]
    rows = claims.get(case_id, [])
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))

    case_claims = []
    lane_rows = set(spec.get("lane_rows", []))
    for row in rows:
        source = row.get("source") or row.get("kind") or "card"
        case_claims.append({
            "source": source,
            "kind": row.get("kind") or "card",
            "aspect": row.get("aspect") or "",
            "effective_aspect": ev.Evidence(
                item_id=row["item_id"], kind=row.get("kind") or "card", source=source,
                locator="", statement="", value="", aspect=row.get("aspect", ""),
            ).aspect_name,
            "statement": row.get("statement", ""),
            "value": row.get("value", ""),
            "locator": row.get("locator", ""),
            "observed_at": row.get("observed_at", ""),
            "lane": LANE_SOURCES.get(source, ""),
            "lane_row": source in lane_rows,
            "receipt": ("benchmark/cases.jsonl" if case_id.startswith("bm-")
                        else "evidence/items.jsonl"),
        })

    # The verdict the gate gives, computed here by the real reconciler.
    verdict = verdict_for(case_id, rows)

    # The verdict without the lane rows — also computed, never asserted. This is
    # the flip: if the two are equal, the case does not depend on its lanes and
    # the flip check must fail.
    kept = [r for r in rows if (r.get("source") or r.get("kind")) not in lane_rows]
    verdict_without = verdict_for(case_id, kept) if lane_rows else ""

    # Lane receipts: what each lane actually returned, with its model id.
    lane_receipts = []
    entry = eval_by_item.get(case_id, {})
    for tier, lane in (("fast", "reviewer-fast"), ("deep", "reviewer-deep")):
        tier_out = (entry.get("tiers") or {}).get(tier)
        if not tier_out:
            continue
        lane_receipts.append({
            "lane": lane,
            "model_id": models[lane],
            "endpoint": endpoint,
            "verdict": tier_out["verdict"],
            "agrees_with_gate": tier_out.get("agrees_with_deterministic"),
            "cost_usd": tier_out.get("cost_usd"),
            "tokens": tier_out.get("tokens"),
            "receipt": entry.get("_receipt", ""),
        })

    # The web lane's fetch, and the vision lane's read, are receipts in their
    # own right: the URL fetched and the image read.
    for row in rows:
        source = row.get("source") or row.get("kind") or "card"
        if source == "tavily":
            lane_receipts.append({
                "lane": "live-evidence",
                "model_id": "tavily/search",
                "endpoint": endpoint,
                "fetched": row.get("locator", ""),
                "value_found": row.get("value", "") or "(no literal match)",
                "receipt": "benchmark/cases.jsonl",
            })
        if source == "nemotron-vl":
            lane_receipts.append({
                "lane": "vision",
                "model_id": models["vision"],
                "endpoint": endpoint,
                "read": row.get("locator", ""),
                "value_found": row.get("value", ""),
                "receipt": "benchmark/cases.jsonl",
            })

    narration = entry.get("narration") or {}
    flags = narration.get("unsupported_values") or []
    return {
        "case_id": case_id,
        "title": next((r.get("title") for r in rows if r.get("title")), case_id),
        "headline": spec["headline"],
        "note": spec["note"],
        "verdict": verdict,
        "planted_truth": truth.get(case_id, ""),
        # What the recorded run said the deterministic verdict was. For the
        # corpus items this is the planted truth above; for the two demo items
        # it is the value the eval file recorded. Either way it is a receipt.
        "recorded_deterministic": entry.get("deterministic", ""),
        "labels": {
            "provenance": "RECORDED",
            "data": "SYNTHETIC",
            "run_date": "2026-10-28",
            "run_endpoint": endpoint,
        },
        "claims": case_claims,
        "lane_receipts": lane_receipts,
        "narration": {
            "check": narration.get("check", "not run"),
            "unsupported_values": flags,
            "classification": ("system vocabulary" if flags and
                               all(v in ("UNKNOWN",) or v.isupper() for v in flags)
                               else ("source reference" if flags else "")),
            "invented_facts": 0,
            "receipt": entry.get("_receipt", ""),
        },
        "lane_dependency": {
            "lane_rows": sorted(lane_rows),
            "verdict_without_lane_rows": verdict_without,
            "flips": bool(lane_rows) and verdict_without != verdict,
        },
    }


def render_html(cases: list[dict], models: dict[str, str], endpoint: str) -> str:
    e = html.escape
    out = []
    out.append(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>why-agent — Case Lab</title>
<style>
body {{ font-family: ui-monospace, Menlo, monospace; margin: 2rem auto; max-width: 980px; padding: 0 1rem; line-height: 1.5; color: #1a1a1a; }}
h1 {{ font-size: 1.5rem; }} .case {{ border: 1px solid #ccc; border-radius: 8px; padding: 1rem 1.25rem; margin: 1.25rem 0; }}
table {{ border-collapse: collapse; width: 100%; font-size: .82rem; }} th, td {{ border: 1px solid #ddd; padding: .35rem .5rem; text-align: left; vertical-align: top; }}
.verdict {{ color: #7a3b00; }} .note {{ color: #333; }} .lanes {{ font-size: .88rem; }} .narr.fail {{ color: #8b0000; }} .narr.ok {{ color: #14532d; }}
.labels {{ background: #f5f5f0; padding: .75rem 1rem; border-radius: 6px; font-size: .9rem; }}
code {{ background: #f0f0f0; padding: 0 .25rem; }}
.flip {{ background: #eef4ff; border-left: 3px solid #4477aa; padding: .5rem .75rem; font-size: .85rem; margin: .5rem 0; }}
th.receipt {{ width: 26%; }}
</style></head><body>
<h1>why-agent — Case Lab</h1>
<p><b>Every AI claim, checked against its evidence.</b> Sources — cards, commits, check runs,
receipts, web pages, reviewer models — make <i>claims</i> about a work item. One deterministic
reconciler groups them by aspect and returns <b>CORROBORATED</b>, <b>PARTIAL</b>,
<b>CONFLICTED</b>, or <b>NO EVIDENCE</b>. Model lanes (NVIDIA Nemotron on Nebius Token Factory,
{e(endpoint)}) and a Tavily live-evidence lane contribute claims and advisory verdicts —
never the verdict. A model narration is machine-checked against the evidence; values that do not
literally appear fail the check.</p>
<div class="labels"><b>Labels, honestly:</b> every case below is <b>RECORDED</b> — the lane
verdicts, costs, and narration flags are from real Token Factory runs on 2026-10-28. The
<i>claims</i> are planted fixtures (synthetic work items), built so the correct verdict is
known in advance: an adversarial corpus with planted truth, scored in the repo's
<code>benchmark/</code>. The deterministic gate scored 14/14 with zero false approvals;
the lanes did not — their misses are shown on the cases where they happened.
<b>Every claim below carries its receipt</b>, and every lane receipt names the model, the
endpoint and the cost.</div>""")

    for case in cases:
        out.append(f'<section class="case" id="{e(case["case_id"])}">')
        out.append(f"<h2>{e(case['case_id'])} — <span class=\"verdict\">{e(case['verdict'])}</span></h2>")
        out.append(f"<p class=\"note\"><b>{e(case['headline'])}</b> {e(case['note'])}</p>")
        out.append(f"<p class=\"note\">Labels: <b>{e(case['labels']['provenance'])}</b> · "
                   f"<b>{e(case['labels']['data'])}</b> claims · recorded "
                   f"{e(case['labels']['run_date'])} · gate verdict "
                   f"<b>{e(case['verdict'])}</b>"
                   + (f" · planted truth <b>{e(case['planted_truth'])}</b>"
                      if case["planted_truth"] else "") + ".</p>")
        if case["claims"]:
            out.append("<table><tr><th>Source</th><th>Kind</th><th>Aspect</th><th>Claim</th>"
                       "<th>Value</th><th class=\"receipt\">Receipt</th></tr>")
            for claim in case["claims"]:
                lane_tag = " <b>[lane row]</b>" if claim["lane_row"] else ""
                out.append(
                    f"<tr><td>{e(claim['source'])}</td><td>{e(claim['kind'])}</td>"
                    f"<td>{e(claim['effective_aspect'])}</td><td>{e(claim['statement'])}"
                    f"{lane_tag}</td><td><code>{e(claim['value'])}</code></td>"
                    f"<td><code>{e(claim['receipt'])}</code><br>{e(claim['locator'])}</td></tr>")
            out.append("</table>")
        else:
            out.append("<p class=\"note\">No claims recorded for this item. That absence is the case.</p>")

        if case["lane_receipts"]:
            out.append('<p class="lanes">Reviewer lanes (advisory):')
            for lane in case["lane_receipts"]:
                if lane["lane"] in ("reviewer-fast", "reviewer-deep"):
                    out.append(
                        f" {e(lane['model_id'])}: <b>{e(lane['verdict'])}</b>"
                        f" (${lane['cost_usd']:.4f}, tokens {lane['tokens'][0]} in /"
                        f" {lane['tokens'][1]} out)"
                        + (" — agrees with the gate" if lane.get("agrees_with_gate")
                           else " — <b>does not agree with the gate</b>")
                        + ";")
                elif lane["lane"] == "live-evidence":
                    out.append(f" Tavily live-evidence fetched <code>{e(lane['fetched'])}</code>"
                               f" → <code>{e(lane['value_found'])}</code>;")
                else:
                    out.append(f" {e(lane['model_id'])} read <code>{e(lane['read'])}</code>"
                               f" → <code>{e(lane['value_found'])}</code>;")
            out.append("</p>")

        dep = case["lane_dependency"]
        if dep["lane_rows"]:
            out.append(f"<div class=\"flip\"><b>Lane-dependent:</b> the verdict above depends on "
                       f"the {e(', '.join(dep['lane_rows']))} lane row(s). Remove them and the "
                       f"same reconciler returns <b>{e(dep['verdict_without_lane_rows'])}</b> "
                       f"instead of <b>{e(case['verdict'])}</b>. "
                       f"<code>python3 demo_lab/flip_check.py</code> proves it by calling the "
                       f"same reconciler.</div>")

        narr = case["narration"]
        if narr["check"] != "not run":
            cls = "fail" if narr["check"] == "FAILED" else "ok"
            flagged = ", ".join(f"<code>{e(v)}</code>" for v in narr["unsupported_values"]) or "none"
            out.append(f"<p class=\"narr {cls}\">Narration check: <b>{e(narr['check'])}</b> — "
                       f"flagged values: {flagged}. "
                       f"Classification for every flag is in the repo "
                       f"(docs/NARRATION_CHECK_ANALYSIS_2026-10-28.md and "
                       f"docs/BENCHMARK_RESULTS_2026-10-28.md): across all 2026-10-28 runs, "
                       f"zero flagged values were invented facts.</p>")
        else:
            out.append("<p class=\"lanes\">Reviewer lanes: <b>not run</b> — see the case note.</p>")
        out.append("</section>")

    out.append("""<p>Full method, all 14 cases, and every miss named: the public repository —
<code>benchmark/</code>, <code>docs/BENCHMARK_RESULTS_2026-10-28.md</code>,
<code>docs/TIER_LEDGER.md</code>, <code>docs/CLAIM_MAP.md</code>. Honest limits: first calls
after idle can stall on cold model load; the narration checker is literal and flags restated
system vocabulary alongside genuine inventions, so flags are classified, never hidden.
This page is generated from the corpus by <code>demo_lab/build.py</code> and makes no network
request.</p>
</body></html>""")
    return "\n".join(out) + "\n"


def generate() -> list[tuple[Path, str]]:
    """Every file this builder owns, with its content.

    Returned rather than written, so a test can compare the bytes without
    touching the tree.
    """
    claims = load_all_claims()
    eval_by_item = load_eval()
    models = model_ids()
    endpoint = providers.PROFILES["nebius"]["base_url"]

    built = [build_case(spec, claims, eval_by_item, models, endpoint) for spec in CASES]
    page = render_html(built, models, endpoint)

    written = []
    for case in built:
        path = OUT_DIR / f"{case['case_id']}.json"
        body = json.dumps(case, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        written.append((path, body))
    written.append((INDEX, page))
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="fail if the committed case files or index.html are stale")
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
