"""Score the benchmark corpus against its planted truth.

The ship gate is zero false approvals: a case scored CORROBORATED whose
planted truth is anything else fails the run, however the rest scored.
Accuracy is reported per verdict and in full — a run that hides its
failures has failed a second, worse way.

Usage:
  python3 benchmark/score.py [--cases benchmark/cases.jsonl]
                             [--truth benchmark/truth.json]
                             [--eval-results eval-results.json]

With --eval-results (a batch_eval.py output file), lane verdicts for the
same items are scored the same way, per tier, disagreements listed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import evidence as ev  # noqa: E402


def score_verdicts(got: dict[str, str], truth: dict[str, str], label: str) -> int:
    false_approvals = []
    misses = []
    for item_id, expected in sorted(truth.items()):
        actual = got.get(item_id, "MISSING")
        if actual != expected:
            misses.append((item_id, expected, actual))
            if actual == "CORROBORATED":
                false_approvals.append(item_id)
    print(f"[{label}] {len(truth) - len(misses)}/{len(truth)} correct")
    for item_id, expected, actual in misses:
        print(f"  MISS {item_id}: expected {expected}, got {actual}")
    if false_approvals:
        print(f"  FALSE APPROVALS (gate failure): {', '.join(false_approvals)}")
    return len(false_approvals)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    here = Path(__file__).resolve().parent
    ap.add_argument("--cases", default=str(here / "cases.jsonl"))
    ap.add_argument("--truth", default=str(here / "truth.json"))
    ap.add_argument("--eval-results", default=None)
    args = ap.parse_args()

    truth = json.loads(Path(args.truth).read_text())
    items = ev.load_items(args.cases)
    claims = ev.load_evidence(args.cases)
    got = {item_id: ev.explain(items, claims, item_id).confidence()
           for item_id in truth}
    failures = score_verdicts(got, truth, "deterministic")

    if args.eval_results:
        data = json.loads(Path(args.eval_results).read_text())
        tiers = sorted({t for r in data["results"] for t in r.get("tiers", {})})
        for tier in tiers:
            lane = {r["item"]: r["tiers"][tier]["verdict"]
                    for r in data["results"]
                    if r["item"] in truth and tier in r.get("tiers", {})}
            if lane:
                failures += score_verdicts(lane, truth, f"lane:{tier}")

    if failures:
        print(f"GATE: FAIL — {failures} false approval(s)")
        return 1
    print("GATE: PASS — zero false approvals")
    return 0


if __name__ == "__main__":
    sys.exit(main())
