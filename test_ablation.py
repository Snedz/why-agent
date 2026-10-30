"""Offline tests for the Tavily ablation harness.

    python3 -m unittest test_ablation -v

No network: the ablation is pure reconciliation over in-memory claims, so
the tests build Evidence rows directly and check the diff accounting —
including that a web row which contradicts moves a verdict, a web row that
only agrees does not manufacture a change, and items with no web rows are
counted honestly.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ablation  # noqa: E402
from evidence import Evidence, Item  # noqa: E402


def ev(item_id, kind, value, aspect="state", source=None):
    return Evidence(item_id=item_id, kind=kind, source=source or kind,
                    locator=f"test://{item_id}/{kind}", statement="s",
                    value=value, observed_at="2026-10-28T00:00:00Z",
                    aspect=aspect)


ITEMS = {
    "agree": Item("agree", declared_status="shipped"),
    "contra": Item("contra", declared_status="shipped"),
    "untouched": Item("untouched", declared_status="shipped"),
}

def _full(item_id, value):
    """Claims across all three expected aspects, agreeing on one value."""
    return [
        ev(item_id, "card", value, aspect="state"),
        ev(item_id, "check", value, aspect="outcome"),
        ev(item_id, "commit", value, aspect="cause"),
    ]


CLAIMS = (
    _full("agree", "shipped")
    + [ev("agree", "web", "shipped", source="tavily")]
    + _full("contra", "shipped")
    + [ev("contra", "web", "delayed", source="tavily")]
    + _full("untouched", "shipped")
)


class AblationTests(unittest.TestCase):
    def test_contradicting_web_row_changes_verdict(self):
        report = ablation.ablate(ITEMS, CLAIMS)
        row = next(r for r in report["items"] if r["item_id"] == "contra")
        self.assertEqual(row["verdict_without_web"], "CORROBORATED")
        self.assertEqual(row["verdict_with_web"], "CONFLICTED")
        self.assertTrue(row["changed"])

    def test_agreeing_web_row_does_not_manufacture_change(self):
        report = ablation.ablate(ITEMS, CLAIMS)
        row = next(r for r in report["items"] if r["item_id"] == "agree")
        self.assertEqual(row["verdict_without_web"], "CORROBORATED")
        self.assertEqual(row["verdict_with_web"], "CORROBORATED")
        self.assertFalse(row["changed"])

    def test_summary_counts(self):
        report = ablation.ablate(ITEMS, CLAIMS)
        s = report["summary"]
        self.assertEqual(s["items_total"], 3)
        self.assertEqual(s["items_with_web_rows"], 2)
        self.assertEqual(s["verdicts_changed"], 1)
        self.assertEqual(s["changed_item_ids"], ["contra"])

    def test_empty_value_web_row_counted_not_hidden(self):
        claims = CLAIMS + [ev("agree", "web", "", source="tavily")]
        report = ablation.ablate(ITEMS, claims)
        row = next(r for r in report["items"] if r["item_id"] == "agree")
        self.assertEqual(row["web_rows"], 2)
        self.assertEqual(row["web_rows_with_value"], 1)


if __name__ == "__main__":
    unittest.main()
