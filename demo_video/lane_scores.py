#!/usr/bin/env python3
"""Print the reviewer lanes' scores — advisory, beside the gate.

The scorer prints a combined verdict at the end, and that verdict counts the
lanes' false approvals too: the run fails a criterion that only the
deterministic gate has to meet, because a lane that falsely approves is
exactly why the lane stays advisory. That is a true statement about the
run, but on its own on screen it reads as "the project failed".

This prints the same numbers, computed by the same `score_counts` the scorer
uses, with each lane's false approvals named — so the comparison is legible
and nothing is hidden. The combined verdict and its exit code are in
`benchmark/score.py` and in `docs/BENCHMARK_RESULTS_2026-10-28.md`.

    python3 demo_video/lane_scores.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmark"))

import evidence as ev  # noqa: E402
import tier_ledger  # noqa: E402
from benchmark import score as scorer  # noqa: E402

LABELS = {"fast": "reviewer fast", "deep": "reviewer deep"}


def main() -> int:
    truth = tier_ledger.load_json(tier_ledger.TRUTH)
    items = ev.load_items(str(tier_ledger.CASES))
    claims = ev.load_evidence(str(tier_ledger.CASES))
    got = {item_id: ev.explain(items, claims, item_id).confidence()
           for item_id in truth}
    gate = scorer.score_counts(got, truth)

    data = tier_ledger.load_json(tier_ledger.BENCH_RESULTS)
    tiers = sorted({t for r in data["results"] for t in r.get("tiers", {})})

    print("NEBIUS REVIEWER LANES — advisory only; the deterministic gate decides")
    print("=" * 72)
    print()
    print(f"  {'scorer':38} {'correct':>8}  false approvals")
    print(f"  {'deterministic reconciler (the gate)':38} "
          f"{gate['correct']:>3}/{gate['total']:<4}  {len(gate['false_approvals'])}")
    rows = []
    for tier in tiers:
        lane = {r["item"]: r["tiers"][tier]["verdict"]
                for r in data["results"]
                if r["item"] in truth and tier in r.get("tiers", {})}
        if not lane:
            continue
        counts = scorer.score_counts(lane, truth)
        rows.append((tier, counts))
        print(f"  {LABELS.get(tier, tier):38} "
              f"{counts['correct']:>3}/{counts['total']:<4}  {len(counts['false_approvals'])}")
    print()
    for tier, counts in rows:
        if counts["false_approvals"]:
            print(f"  {LABELS.get(tier, tier)} falsely approved: "
                  + ", ".join(counts["false_approvals"]))
    summary = data.get("summary") or {}
    print()
    print(f"  corpus: {len(truth)} items, "
          f"{sum(1 for l in tier_ledger.CASES.read_text(encoding='utf-8').splitlines() if l.strip())} claim rows"
          f" · reviewer-lane cost ${float(summary.get('total_cost_usd') or 0.0):.3f}"
          f" · {summary.get('retries', 0)} retries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
