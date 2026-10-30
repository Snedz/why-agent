"""Tests for the submission packet — SUBMISSION.md.

    python3 -m unittest test_submission_packet -v

The packet is the document the founder pastes into the form, so a number in it
that has drifted from the repository is a number the judge reads and cannot
reproduce. These tests hold the packet's factual claims to the artefacts that
produced them.

What is deliberately NOT checked: the number of tests in the suite. It moves
whenever anyone adds one, and the packet's job is to say what the suite
proves, not to count it.

Offline, no model, no network.
"""
import json
import os
import re
import sys
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "benchmark"))

import evidence as ev  # noqa: E402
import providers  # noqa: E402
import tier_ledger  # noqa: E402
from benchmark import score as scorer  # noqa: E402

PACKET = Path(HERE) / "SUBMISSION.md"


class PacketTests(unittest.TestCase):
    """Every number the packet quotes is one the repository produced."""

    @classmethod
    def setUpClass(cls):
        cls.text = PACKET.read_text(encoding="utf-8")
        cls.truth = tier_ledger.load_json(tier_ledger.TRUTH)
        items = ev.load_items(str(tier_ledger.CASES))
        claims = ev.load_evidence(str(tier_ledger.CASES))
        got = {k: ev.explain(items, claims, k).confidence() for k in cls.truth}
        cls.gate = scorer.score_counts(got, cls.truth)
        cls.bench = tier_ledger.load_json(tier_ledger.BENCH_RESULTS)
        cls.summary = cls.bench.get("summary") or {}

    def test_the_gate_score_is_the_committed_score(self):
        self.assertIn(f"{self.gate['correct']}/{self.gate['total']}", self.text)
        self.assertEqual(len(self.gate["false_approvals"]), 0)

    def test_the_lane_scores_are_the_committed_scores(self):
        for tier in ("fast", "deep"):
            lane = {r["item"]: r["tiers"][tier]["verdict"]
                    for r in self.bench["results"]
                    if r["item"] in self.truth and tier in r.get("tiers", {})}
            counts = scorer.score_counts(lane, self.truth)
            self.assertIn(f"{counts['correct']}/{counts['total']}", self.text,
                          f"the packet does not carry the {tier} lane's score")

    def test_the_cost_and_retries_are_the_committed_ones(self):
        self.assertIn(f"${float(self.summary.get('total_cost_usd') or 0.0):.3f}", self.text)
        self.assertIn(f"{self.summary.get('retries', 0)} retries", self.text)

    def test_the_corpus_size_is_the_committed_size(self):
        self.assertIn(f"{len(self.truth)} planted-claim work items", self.text)
        rows = sum(1 for line in tier_ledger.CASES.read_text(encoding="utf-8").splitlines()
                   if line.strip())
        self.assertEqual(rows, 51)

    def test_the_case_lab_counts_are_the_committed_counts(self):
        cases = sorted((Path(HERE) / "demo_lab" / "cases").glob("*.json"))
        self.assertEqual(len(cases), 7)
        self.assertIn("seven cases", self.text)
        dependent = [c for c in (json.loads(p.read_text()) for p in cases)
                     if c["lane_dependency"]["lane_rows"]]
        self.assertEqual(len(dependent), 2)
        self.assertIn("Two of the cases are lane-dependent", self.text)

    def test_the_endpoint_and_the_model_ids_are_the_pinned_ones(self):
        profile = providers.PROFILES["nebius"]
        self.assertIn(profile["base_url"], self.text)
        for tier in ("standard", "fast", "deep", "vision"):
            self.assertIn(profile["models"][tier], self.text,
                          f"the packet does not name the {tier} model id")

    def test_the_track_is_named(self):
        self.assertIn("Best Apps and Agents", self.text)

    def test_the_deadline_is_the_rules_deadline(self):
        self.assertIn("10:00 AM PT", self.text)
        self.assertIn("2026-10-30", self.text)

    def test_the_packet_does_not_quote_a_test_count(self):
        """The suite's size moves whenever anyone adds a test."""
        self.assertIsNone(re.search(r"\b\d{2,4}\s+tests\b", self.text),
                          "the packet quotes a test count, which goes stale — say what "
                          "the suite proves instead")

    def test_the_packet_does_not_quote_a_video_length(self):
        """The length is measured at render time, and the renderer fails at 3 minutes."""
        self.assertIsNone(re.search(r"\b\d{1,3}\.\d{1,2}\s*s(ec|econds)?\b", self.text),
                          "the packet quotes a video length, which goes stale — point at "
                          "demo_video/render.py instead")

    def test_the_packet_says_what_was_not_done(self):
        for honest in ("Nothing has been submitted",
                       "no paid Nebius account",
                       "no commercial licence",
                       "no development contract"):
            self.assertIn(honest.lower(), self.text.lower(),
                          f"the packet no longer says {honest!r}")

    def test_the_packet_names_the_three_founder_steps(self):
        for step in ("Quebec", "YouTube", "paste the form"):
            self.assertIn(step.lower(), self.text.lower(),
                          f"the packet no longer names the {step!r} step")


if __name__ == "__main__":
    unittest.main()
