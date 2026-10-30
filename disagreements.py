"""disagreements.py — the lane-vs-gate disagreement report.

The tier ledger (`ledger.py`) answers "what did the run COST". This answers the
other question: **where did a lane disagree with the deterministic gate, and
with each other?**

Read-only. It writes nothing, calls no model, and touches no evidence: it
reads the JSONL rows and reconciles them with the house's own
`evidence.explain`, so the verdict it prints is the same verdict the agent
would give — not a second implementation of it.

For every item it prints:

  * the deterministic verdict (from `evidence.explain`),
  * every lane that appears in ANY of the given files, with the lane's own
    value, its citation, and one of three marks:
      AGREES          the lane's value is the deterministic verdict
      DISAGREES       it is not
      NO-LANE-VERDICT the lane produced no verdict row for this item at all

and then, AFTER the full list, the per-lane counts. The counts are reported
ALONGSIDE the list, never instead of it: a count without the rows it counts is
a number nobody can check.

Usage:
    python3 disagreements.py evidence/items.jsonl [more.jsonl ...]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import evidence as ev  # noqa: E402 — the house's own reconciler, not a copy

AGREES = "AGREES"
DISAGREES = "DISAGREES"
NO_LANE_VERDICT = "NO-LANE-VERDICT"


def load_rows(paths: list[str]) -> list[ev.Evidence]:
    """Every row in the given evidence files, in file order."""
    rows: list[ev.Evidence] = []
    for path in paths:
        rows.extend(ev.load_evidence(path))
    return rows


def lanes_in(rows: list[ev.Evidence]) -> list[str]:
    """The lanes that produced a verdict row, sorted."""
    return sorted({r.source for r in rows if r.kind == "verdict"})


def item_report(rows: list[ev.Evidence], items: dict[str, ev.Item],
                item_id: str, lanes: list[str]) -> dict:
    """One item: the deterministic verdict, and every lane's mark."""
    rec = ev.explain(items, rows, item_id)
    deterministic = rec.confidence()
    by_lane = {r.source: r for r in rows
               if r.item_id == item_id and r.kind == "verdict"}
    lanes_out = []
    for lane in lanes:
        row = by_lane.get(lane)
        if row is None:
            lanes_out.append({"lane": lane, "value": "", "citation": "",
                              "mark": NO_LANE_VERDICT})
            continue
        value = (row.value or "").strip().upper()
        lanes_out.append({
            "lane": lane,
            "value": value,
            "citation": row.citation(),
            "mark": AGREES if value == deterministic else DISAGREES,
        })
    return {"item_id": item_id, "title": rec.item.title,
            "deterministic": deterministic, "lanes": lanes_out}


def counts(reports: list[dict]) -> dict[str, dict]:
    """Per-lane agree / disagree / no-verdict counts, across every item."""
    tally: dict[str, dict] = {}
    for report in reports:
        for lane in report["lanes"]:
            row = tally.setdefault(lane["lane"], {"agree": 0, "disagree": 0,
                                                  "no_verdict": 0})
            key = {"AGREES": "agree", "DISAGREES": "disagree",
                   "NO-LANE-VERDICT": "no_verdict"}[lane["mark"]]
            row[key] += 1
    return tally


def render(paths: list[str]) -> str:
    """The whole report as text. Deterministic: no clock, no randomness."""
    rows = load_rows(paths)
    items: dict[str, ev.Item] = {}
    for path in paths:
        items.update(ev.load_items(path))
    lanes = lanes_in(rows)
    item_ids = sorted({r.item_id for r in rows})
    reports = [item_report(rows, items, item_id, lanes) for item_id in item_ids]

    out: list[str] = []
    for report in reports:
        out.append(report["item_id"])
        title = report["title"]
        out.append(f"  deterministic: {report['deterministic']}"
                   + (f"   ({title})" if title else ""))
        for lane in report["lanes"]:
            value = lane["value"] or "—"
            citation = f"  {lane['citation']}" if lane["citation"] else ""
            out.append(f"    {lane['lane']:<24} {value:<12} {lane['mark']}{citation}")
        out.append("")

    out.append("per-lane counts (across every item):")
    for lane, row in sorted(counts(reports).items()):
        out.append(f"  {lane:<24} {row['agree']} agree, {row['disagree']} disagree, "
                   f"{row['no_verdict']} no-verdict")
    out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("evidence", nargs="+", help="evidence JSONL file(s) to read")
    args = ap.parse_args(argv)
    missing = [p for p in args.evidence if not Path(p).is_file()]
    if missing:
        print(f"disagreements: no such file: {', '.join(missing)}", file=sys.stderr)
        return 2
    print(render(args.evidence))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
