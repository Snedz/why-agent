"""Tests for disagreements.py — the lane-vs-gate disagreement report.

    python3 -m unittest test_disagreements -v

Offline: no model, no network, and the report writes nothing — the evidence
files are byte-identical before and after.
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

spec = importlib.util.spec_from_file_location("disagreements", HERE / "disagreements.py")
disagreements = importlib.util.module_from_spec(spec)
spec.loader.exec_module(disagreements)

import evidence as ev  # noqa: E402

# The 2026-10-28 pattern the card names: fast PARTIAL vs deep CONFLICTED on
# why-alpha, and a lane that produced no verdict for one item.
ROWS = [
    {"item_id": "why-alpha", "kind": "card", "source": "card",
     "locator": "synthetic/cards/alpha.md:9", "statement": "the card was marked DONE",
     "value": "DONE"},
    {"item_id": "why-alpha", "kind": "commit", "source": "git",
     "locator": "0c4f1a9 (synthetic)", "statement": "a commit merged the fix",
     "value": "merged", "aspect": "state"},
    {"item_id": "why-alpha", "kind": "check", "source": "ci",
     "locator": "synthetic://run/alpha/42", "statement": "the gate run is still red",
     "value": "failing", "aspect": "state"},
    {"item_id": "why-alpha", "kind": "verdict", "source": "nemotron-fast",
     "locator": "eval-results-2026-10-28.json#fast", "statement": "the fast lane",
     "value": "PARTIAL", "aspect": "outcome"},
    {"item_id": "why-alpha", "kind": "verdict", "source": "nemotron-deep",
     "locator": "eval-results-2026-10-28.json#deep", "statement": "the deep lane",
     "value": "CONFLICTED", "aspect": "outcome"},
    {"item_id": "why-beta", "kind": "card", "source": "card",
     "locator": "synthetic/cards/beta.md:3", "statement": "the card says unknown",
     "value": "UNKNOWN", "aspect": "state"},
    {"item_id": "why-beta", "kind": "verdict", "source": "nemotron-deep",
     "locator": "eval-results-2026-10-28.json#deep", "statement": "the deep lane",
     "value": "PARTIAL", "aspect": "outcome"},
]


def write_fixture(rows=ROWS):
    tmp = tempfile.mkdtemp(prefix="disagree-")
    path = os.path.join(tmp, "evidence.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return path


class ReportTests(unittest.TestCase):
    """What the report says, per item and per lane."""

    def setUp(self):
        self.path = write_fixture()
        self.report = disagreements.render([self.path])

    def test_it_shows_both_lanes_and_marks_the_disagreement(self):
        self.assertIn("nemotron-fast", self.report)
        self.assertIn("nemotron-deep", self.report)
        self.assertIn("DISAGREES", self.report)
        self.assertIn("AGREES", self.report)
        # the fast lane said PARTIAL, the deep lane CONFLICTED
        self.assertIn("PARTIAL", self.report)
        self.assertIn("CONFLICTED", self.report)

    def test_a_lane_with_no_verdict_for_an_item_is_marked(self):
        # nemotron-fast has a row for why-alpha and none for why-beta.
        self.assertIn("NO-LANE-VERDICT", self.report)

    def test_the_deterministic_verdict_is_the_one_the_reconciler_gives(self):
        rows = disagreements.load_rows([self.path])
        items = ev.load_items(self.path)
        for item_id in sorted({r.item_id for r in rows}):
            expected = ev.explain(items, rows, item_id).confidence()
            self.assertIn(expected, self.report)

    def test_the_counts_come_alongside_the_full_list(self):
        # Never instead of it: every lane that appears in the list also appears
        # in the counts, and the counts come after the rows.
        self.assertLess(self.report.index("per-lane counts"),
                        len(self.report))
        for lane in ("nemotron-fast", "nemotron-deep"):
            self.assertGreaterEqual(self.report.count(lane), 2,
                                    "a lane must appear in the list AND the counts")

    def test_the_counts_are_computed_from_the_rows(self):
        rows = disagreements.load_rows([self.path])
        items = ev.load_items(self.path)
        lanes = disagreements.lanes_in(rows)
        reports = [disagreements.item_report(rows, items, i, lanes)
                   for i in sorted({r.item_id for r in rows})]
        tally = disagreements.counts(reports)
        # why-alpha: deep says CONFLICTED (the deterministic verdict) and fast
        # says PARTIAL, so fast disagrees and deep agrees.
        # why-beta: deep says PARTIAL, which IS the deterministic verdict, so
        # deep agrees again -- and fast has no row for why-beta at all.
        self.assertEqual(tally["nemotron-deep"]["agree"], 2)
        self.assertEqual(tally["nemotron-deep"]["disagree"], 0)
        self.assertEqual(tally["nemotron-fast"]["agree"], 0)
        self.assertEqual(tally["nemotron-fast"]["disagree"], 1)
        self.assertEqual(tally["nemotron-fast"]["no_verdict"], 1)
        # every lane x every item is accounted for
        self.assertEqual(sum(sum(v.values()) for v in tally.values()),
                         len(reports) * len(lanes))

    def test_a_citation_is_printed_for_every_verdict_row(self):
        self.assertIn("eval-results-2026-10-28.json#fast", self.report)
        self.assertIn("eval-results-2026-10-28.json#deep", self.report)


class ReadOnlyTests(unittest.TestCase):
    """The report writes nothing."""

    def test_the_evidence_file_is_byte_identical_afterwards(self):
        path = write_fixture()
        before = open(path, "rb").read()
        disagreements.render([path])
        self.assertEqual(before, open(path, "rb").read())

    def test_a_missing_file_is_an_error_not_a_report(self):
        self.assertEqual(
            disagreements.main(["/tmp/definitely-not-here-xyz.json"]), 2)


if __name__ == "__main__":
    unittest.main()
