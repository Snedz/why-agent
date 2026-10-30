"""Score the Claim Court corpus against its frozen verdicts.

truth.json records the verdict the deterministic reconciler computed for
each item when the corpus was frozen (see SOURCES.md). This scorer
recomputes every verdict from cases.jsonl with the same reconciler and
fails if any item drifts — a row edited to make a claim look better is
exactly the failure this exists to catch.

Usage:
  python3 claimcourt/score.py [--cases claimcourt/cases.jsonl]
                              [--truth claimcourt/truth.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import evidence as ev  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    here = Path(__file__).resolve().parent
    ap.add_argument("--cases", default=str(here / "cases.jsonl"))
    ap.add_argument("--truth", default=str(here / "truth.json"))
    args = ap.parse_args()

    truth = json.loads(Path(args.truth).read_text())
    items = ev.load_items(args.cases)
    claims = ev.load_evidence(args.cases)

    drift = []
    for item_id, expected in sorted(truth.items()):
        actual = ev.explain(items, claims, item_id).confidence()
        mark = "ok" if actual == expected else "DRIFT"
        if actual != expected:
            drift.append((item_id, expected, actual))
        print(f"{item_id:28s} frozen={expected:12s} computed={actual:12s} {mark}")
    print(f"corpus: {len(truth)} items, {len(claims)} claim rows")
    if drift:
        print(f"FAIL: {len(drift)} verdict(s) drifted from the frozen corpus")
        return 1
    print("PASS: every computed verdict matches the frozen corpus")
    return 0


if __name__ == "__main__":
    sys.exit(main())
