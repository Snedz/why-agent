#!/usr/bin/env python3
"""Prove that the lane-dependent cases really depend on their lanes.

A page can claim "remove the lane row and the verdict changes". This script
does not believe the page. For every case file it:

  1. re-reads the ORIGINAL claim rows from the repository's corpus — not from
     the case file, so a case file that drifted from the corpus is caught;
  2. calls the house's own reconciler (evidence.explain) to get the verdict;
  3. removes the lane rows and calls the same reconciler again;
  4. asserts the first verdict is the recorded one, and that the two differ.

The reconciler here is the same function the CLI uses and the same one
benchmark/score.py scores with. Nothing is re-derived.

    python3 demo_lab/flip_check.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import evidence as ev  # noqa: E402

CASES_DIR = HERE / "cases"
CORPUS = ROOT / "benchmark" / "cases.jsonl"
ITEMS = ROOT / "evidence" / "items.jsonl"


def claims_for(case_id: str) -> tuple[list[ev.Evidence], dict[str, ev.Item]]:
    """The ORIGINAL rows for one case, loaded by the house's own loader."""
    path = CORPUS if case_id.startswith("bm-") else ITEMS
    items = ev.load_items(str(path))
    claims = [c for c in ev.load_evidence(str(path)) if c.item_id == case_id]
    return claims, items


def main() -> int:
    case_files = sorted(CASES_DIR.glob("*.json"))
    if not case_files:
        print("no case files — run demo_lab/build.py first")
        return 1

    print(f"flip check: {len(case_files)} case file(s)\n")
    print(f"{'case':26} {'with lanes':16} {'without lane rows':22} {'flips':6}")
    print("-" * 74)

    failures: list[str] = []
    lane_dependent = 0

    for path in case_files:
        case = json.loads(path.read_text(encoding="utf-8"))
        case_id = case["case_id"]
        claims, items = claims_for(case_id)

        with_lanes = ev.explain(items, claims, case_id).confidence()

        lane_rows = set(case.get("lane_dependency", {}).get("lane_rows") or [])
        kept = [c for c in claims if c.source not in lane_rows]
        without_lanes = (ev.explain(items, kept, case_id).confidence()
                         if lane_rows else "—")

        # 1. the computed verdict must equal the one the case file publishes
        if with_lanes != case["verdict"]:
            failures.append(f"{case_id}: computed {with_lanes} != case file {case['verdict']}")
        # 2. and it must equal the one the recorded run produced
        recorded = case.get("recorded_deterministic") or case.get("planted_truth") or ""
        if recorded and with_lanes != recorded:
            failures.append(f"{case_id}: computed {with_lanes} != recorded {recorded}")
        # 3. the case file's own flip claim must be true
        if lane_rows and without_lanes == with_lanes:
            failures.append(f"{case_id}: removing {sorted(lane_rows)} did not change the verdict")
        # 4. and the case file's published flip must match what we just measured
        if lane_rows:
            lane_dependent += 1
            published = case["lane_dependency"]["verdict_without_lane_rows"]
            if published != without_lanes:
                failures.append(f"{case_id}: case file says {published} without lanes, "
                                f"measured {without_lanes}")

        print(f"{case_id:26} {with_lanes:16} {without_lanes:22} "
              f"{('yes' if lane_rows else '—'):6}")

    print()
    print(f"lane-dependent cases: {lane_dependent}")
    if lane_dependent < 2:
        failures.append(f"only {lane_dependent} lane-dependent case(s); the card requires 2")

    if failures:
        print("\nFAIL")
        for line in failures:
            print(f"  {line}")
        return 1
    print("\nPASS — every lane-dependent case flips, and every verdict is the recorded one")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
