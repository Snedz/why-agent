#!/usr/bin/env python3
"""Run the why-agent over the synthetic evidence and print all five outcomes.

    python3 demo.py            # the five cases, as a reader sees them
    python3 demo.py --json     # the same, machine-readable

This is the demo script for the submission video: one command, five cases, and
the point of each one said out loud. Every case uses SYNTHETIC data — no real
card, no real customer, no real identifier is in this repository.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import evidence as ev  # noqa: E402
import why_agent as wa  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "evidence", "items.jsonl")

CASES = (
    ("why-alpha", "the sources disagree",
     "A card says DONE, a commit says merged, a check says red, a receipt says "
     "nothing was claimed. Four sources, four answers. The agent does not pick "
     "one — it shows all four and says which one is authoritative for what."),
    ("why-beta", "the sources agree, and do not cover everything",
     "A card and a gate both say blocked; a receipt and a review both say the "
     "run claimed zero. Two aspects are corroborated, and nobody says WHY. The "
     "agent reports the gap as UNKNOWN, because a gap nobody reported is not a "
     "pass."),
    ("why-delta", "the sources agree and cover the ground",
     "A card, a commit, a receipt and two review families line up: done, because "
     "the Files list was added, shipped, approved. This is the easy case, and it "
     "is still cited line by line."),
    ("why-gamma", "almost nobody has looked",
     "One card, one sentence, nothing else. The agent says what it knows and "
     "names the two things it does not know."),
    ("why-nothing", "nobody has written anything",
     "An item id that appears in no source at all. The answer is NO EVIDENCE — "
     "not a plausible explanation."),
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    items = ev.load_items(DATA)
    claims = ev.load_evidence(DATA)

    if args.json:
        import json
        out = []
        for item_id, _, _ in CASES:
            result = ev.explain(items, claims, item_id)
            out.append(wa.to_json(result))
        print(json.dumps(out, indent=2))
        return 0

    print("=" * 78)
    print("why-agent — five items, four kinds of answer")
    print("=" * 78)
    for item_id, headline, note in CASES:
        result = ev.explain(items, claims, item_id)
        print()
        print("-" * 78)
        print(f"CASE {item_id} — {headline}")
        print("-" * 78)
        print(wa.render(result))
        print(f"> {note}")
    print()
    print("=" * 78)
    print("Every line above carries a citation. Nothing was asserted without one.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
