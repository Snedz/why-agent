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
import review  # noqa: E402

# The words the system itself uses. A narration that states one of them has
# repeated the system's vocabulary, not invented a fact.
SYSTEM_VOCABULARY = ("UNKNOWN",) + review.VERDICTS


def classify_flag(value: str, source_names: set[str]) -> str:
    """Classify one narration flag.

    The narration checker flags a value the evidence does not support. The flag
    alone is not the finding -- the CLASSIFICATION of every flag is (see
    docs/NARRATION_CHECK_ANALYSIS_2026-10-28.md). This reports the class; it
    does not change what the checker flags, and it does not suppress anything.

    The classes, in the order they are tested:
      system vocabulary  -- the value is one of the system's own words
      quoted empty value -- the value is an empty string in quotes
      source reference   -- the value is a source name the corpus uses
      locator fragment   -- the value looks like a path or a host
      verdict variant    -- the value is a near-miss of a verdict word
      invented           -- anything else, i.e. a value the evidence does not
                            contain. This is the only class that is a finding.
    """
    text = (value or "").strip()
    if text.upper() in SYSTEM_VOCABULARY:
        return "system vocabulary"
    if text in ('""', "''", ""):
        return "quoted empty value"
    if text.lower() in {s.lower() for s in source_names}:
        return "source reference"
    if "/" in text:
        return "locator fragment"
    for word in SYSTEM_VOCABULARY:
        if word.startswith(text.upper()) and text.upper() != word:
            return "verdict variant"
    return "invented"


def narration_flag_classes(results: list[dict], source_names: set[str]) -> dict[str, int]:
    """How many flags of each class the run produced."""
    counts: dict[str, int] = {}
    for entry in results:
        for value in (entry.get("narration") or {}).get("unsupported_values", []):
            name = classify_flag(value, source_names)
            counts[name] = counts.get(name, 0) + 1
    return counts


def print_corpus_summary(results: list[dict], case_rows: int, items: int,
                         summary: dict, source_names: set[str]) -> None:
    """Print the corpus and the run's measured facts.

    Every figure the results docs publish comes from here, so a number in a
    document is a number the runner printed.
    """
    classes = narration_flag_classes(results, source_names)
    classes.setdefault("invented", 0)  # the one class that is a finding: print it even at zero
    flags = sum(classes.values())
    checks = summary.get("narration_checks") or {}
    narrated = sum(1 for r in results if "narration" in r)
    unparseable = sum(1 for r in results for tier in r.get("tiers", {}).values()
                      if (tier.get("verdict") or "") not in review.VERDICTS)
    print(f"corpus: {items} items, {case_rows} claim rows")
    print(f"reviewer-lane cost: ${float(summary.get('total_cost_usd') or 0.0):.3f} "
          f"(narration unmetered), retries {summary.get('retries', 0)}")
    print(f"narration checks: {narrated} checked, {checks.get('PASSED', 0)} PASSED, "
          f"{checks.get('FAILED', 0)} FAILED; {flags} flagged value(s)")
    print("flag classes: " + ", ".join(f"{name} {count}"
                                       for name, count in sorted(classes.items())))
    print(f"unparseable verdicts: {unparseable}")


def score_counts(got: dict[str, str], truth: dict[str, str]) -> dict:
    """Score verdicts against the planted truth, and COUNT what happened.

    The rule lives here, once: an item counts as correct when the verdict is the
    planted one, and a false approval is an item the truth does not call
    CORROBORATED that was called CORROBORATED. `score_verdicts` prints this;
    the tier ledger reads it, so the two can never score differently.
    """
    misses = []
    false_approvals = []
    for item_id, expected in sorted(truth.items()):
        actual = got.get(item_id, "MISSING")
        if actual != expected:
            misses.append((item_id, expected, actual))
            if actual == "CORROBORATED":
                false_approvals.append(item_id)
    return {
        "correct": len(truth) - len(misses),
        "total": len(truth),
        "misses": misses,
        "false_approvals": false_approvals,
    }


def score_verdicts(got: dict[str, str], truth: dict[str, str], label: str) -> int:
    counts = score_counts(got, truth)
    false_approvals = counts["false_approvals"]
    misses = counts["misses"]
    print(f"[{label}] {counts['correct']}/{counts['total']} correct")
    print(f"  false approvals: {len(false_approvals)}")
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
        # The source names come from the CORPUS -- the lanes' rows carry no
        # source, and the corpus is where a source name is defined.
        print_corpus_summary(data["results"], len(claims), len(truth),
                             data.get("summary") or {},
                             {c.source for c in claims})
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
