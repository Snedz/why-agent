#!/usr/bin/env python3
"""Show the narration check: the model may write prose, it may not add a fact.

Two halves, and they are labelled differently on purpose:

  1. the RECORDED run — what the checker actually returned on the real
     2026-10-28 Token Factory narrations, read from the committed eval files;
  2. the checker running HERE, on two FIXTURE narrations, using the same three
     functions the CLI uses (`extract_values`, `allowed_terms`,
     `find_unsupported`).

The fixtures are not recorded model output and are not presented as such.

    python3 demo_video/narration_check.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import evidence as ev  # noqa: E402
import narrate as na  # noqa: E402

DEMO_RESULTS = ROOT / "eval-results-2026-10-28.json"
BENCH_RESULTS = ROOT / "benchmark" / "eval-benchmark-2026-10-28.json"
ITEMS = ROOT / "evidence" / "items.jsonl"

FIXTURES = [
    # A states a value the evidence really contains, so the check passes on the
    # value rather than on the absence of one.
    ("A", 'The gate run is still red, so why-alpha is still "failing".'),
    # B states an identifier that appears nowhere in the evidence.
    ("B", "The deploy receipt deadbee1 shows the release shipped."),
]


def main() -> int:
    print("NARRATION CHECK — the model may write the prose, it may not add a fact")
    print("=" * 72)
    print()
    print("RECORDED — the real 2026-10-28 Token Factory run:")
    demo = json.loads(DEMO_RESULTS.read_text(encoding="utf-8"))
    for entry in demo.get("results", []):
        narr = entry.get("narration") or {}
        flags = ", ".join(narr.get("unsupported_values") or []) or "none"
        print(f"  {entry['item']:12} check {str(narr.get('check')):8} unsupported: {flags}")
    bench = json.loads(BENCH_RESULTS.read_text(encoding="utf-8"))
    summary = bench.get("summary") or {}
    checks = summary.get("narration_checks") or {}
    print(f"  corpus: {checks.get('PASSED', 0)} PASSED, {checks.get('FAILED', 0)} FAILED"
          f"  ·  classified: invented facts 0")
    print("  (every flag is classified in docs/NARRATION_CHECK_ANALYSIS_2026-10-28.md)")
    print()

    items = ev.load_items(str(ITEMS))
    claims = ev.load_evidence(str(ITEMS))
    result = ev.explain(items, claims, "why-alpha")
    allowed = na.allowed_terms(result)

    print("THE CHECKER, running here on two FIXTURE narrations (not recorded model output):")
    for label, text in FIXTURES:
        values = na.extract_values(text)
        unsupported = na.find_unsupported(values, allowed)
        print()
        print(f"  narration {label}: {text!r}")
        print(f"    stated values: {', '.join(values) if values else 'none'}")
        print(f"    unsupported:   {', '.join(unsupported) if unsupported else 'none'}")
        if unsupported:
            print("    ## CHECK FAILED — the narrative stated values the evidence "
                  "does not contain")
            for value in unsupported:
                print(f"    - `{value}`")
            print("    These were not removed. Read them as claims, not facts.")
        else:
            print("    ## CHECK PASSED — every value the narrative stated exists "
                  "in the evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
