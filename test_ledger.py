"""Tests for ledger.py — the tier ledger generator.

    python3 -m unittest test_ledger -v

Offline, no model, no network. The gates are the card's: the committed doc is
what the generator writes, running it twice produces the same bytes, a corrupt
input fails rather than emitting a number, and the doc names the price source
and its date.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ledger  # noqa: E402


class RegenerateTests(unittest.TestCase):
    """The committed doc is generated, not typed."""

    def test_the_committed_doc_is_exactly_what_the_generator_writes(self):
        generated = ledger.render()
        committed = ledger.DOC.read_text(encoding="utf-8")
        self.assertEqual(generated, committed,
                         "docs/TIER_LEDGER.md is not what ledger.py generates — "
                         "run `python3 ledger.py`")

    def test_running_it_twice_produces_the_same_bytes(self):
        first = ledger.render()
        second = ledger.render()
        self.assertEqual(first.encode("utf-8"), second.encode("utf-8"))

    def test_the_check_mode_passes_on_a_freshly_generated_doc(self):
        # --check must be the thing CI runs, so it has to work.
        proc = subprocess.run([sys.executable, os.path.join(HERE, "ledger.py"), "--check"],
                              capture_output=True, text=True, cwd=HERE)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_the_gate_still_passes_after_the_scorer_refactor(self):
        # score.py grew score_counts() so the rule has one implementation; the
        # gate's own output and exit code must not have moved.
        proc = subprocess.run([sys.executable, os.path.join(HERE, "benchmark", "score.py")],
                              capture_output=True, text=True, cwd=HERE)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("GATE: PASS", proc.stdout)


class CorruptInputTests(unittest.TestCase):
    """A corrupt input must fail, not produce a number."""

    def test_a_corrupt_results_file_fails_instead_of_emitting_a_number(self):
        tmp = tempfile.mkdtemp(prefix="ledger-bad-")
        self.addCleanup(shutil.rmtree, tmp, True)
        bad = os.path.join(tmp, "eval-results-2026-10-28.json")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("{not json at all")
        original = ledger.DEMO_RESULTS
        ledger.DEMO_RESULTS = __import__("pathlib").Path(bad)
        try:
            with self.assertRaises(ledger.LedgerError):
                ledger.render()
        finally:
            ledger.DEMO_RESULTS = original

    def test_a_missing_results_file_fails(self):
        original = ledger.DEMO_RESULTS
        ledger.DEMO_RESULTS = __import__("pathlib").Path("/tmp/definitely-not-here-xyz.json")
        try:
            with self.assertRaises(ledger.LedgerError):
                ledger.render()
        finally:
            ledger.DEMO_RESULTS = original

    def test_check_mode_reports_a_mismatch_as_a_failure(self):
        tmp = tempfile.mkdtemp(prefix="ledger-doc-")
        self.addCleanup(shutil.rmtree, tmp, True)
        doc = os.path.join(tmp, "TIER_LEDGER.md")
        with open(doc, "w", encoding="utf-8") as fh:
            fh.write("# Tier ledger — hand typed\n")
        original = ledger.DOC
        ledger.DOC = __import__("pathlib").Path(doc)
        try:
            self.assertEqual(ledger.main(["--check"]), 1)
        finally:
            ledger.DOC = original


class TraceabilityTests(unittest.TestCase):
    """Every figure traces to a results JSON, and moves when its source moves."""

    def test_the_doc_names_the_price_source_and_its_date(self):
        text = ledger.DOC.read_text(encoding="utf-8")
        self.assertIn("review.py", text)
        self.assertIn("PRICE_SNAPSHOT", text)
        self.assertIn(ledger.price_snapshot_date(), text)

    def test_a_figure_moves_when_its_source_moves(self):
        # If the doc were hand-typed, changing a committed results file would
        # change nothing. It must change the cost.
        tmp = tempfile.mkdtemp(prefix="ledger-trace-")
        self.addCleanup(shutil.rmtree, tmp, True)
        payload = json.loads(ledger.DEMO_RESULTS.read_text(encoding="utf-8"))
        for entry in payload["results"]:
            for tier, outcome in entry.get("tiers", {}).items():
                outcome["cost_usd"] = float(outcome.get("cost_usd") or 0.0) * 2
        moved = os.path.join(tmp, "eval-results-2026-10-28.json")
        with open(moved, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)

        original = ledger.DEMO_RESULTS
        ledger.DEMO_RESULTS = __import__("pathlib").Path(moved)
        try:
            changed = ledger.render()
        finally:
            ledger.DEMO_RESULTS = original
        self.assertNotEqual(changed, ledger.render(),
                            "doubling the recorded cost changed nothing in the ledger — "
                            "so the figure is not traced to the file")

    def test_the_doc_publishes_no_latency_percentile(self):
        # The harness records no per-call latency, so the ledger must publish
        # none: there is no median because none was measured.
        text = ledger.DOC.read_text(encoding="utf-8").lower()
        self.assertIn("latency", text)
        self.assertIn("not recorded", text)
        for percentile in ("p50", "p95", "p99", "median latency"):
            self.assertNotIn(percentile, text)

    def test_the_doc_publishes_no_number_it_cannot_source(self):
        # Every number in the table has to be one of the recorded ones.
        text = ledger.DOC.read_text(encoding="utf-8")
        table = [l for l in text.splitlines() if l.startswith("| fast") or l.startswith("| deep")]
        self.assertEqual(len(table), 2)
        for line in table:
            cells = [c.strip() for c in line.strip("|").split("|")]
            calls = int(cells[2])
            agree, total = cells[6].split("/")
            self.assertEqual(int(total), calls)
            self.assertLessEqual(int(agree), calls)


if __name__ == "__main__":
    unittest.main()
