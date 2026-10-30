"""Tests for the demo page — demo_page.py and demo.html.

    python3 -m unittest test_demo_page -v

Offline, no model, no network. The landing page is the URL the rules ask for,
and a judge opens it before anything else, so the gates here are about it
being TRUE: the numbers come from the committed run outputs, the excerpt is the
tool's real output, and it does not describe a different hackathon.
"""
import html
import json
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "benchmark"))

import demo_page  # noqa: E402
import tier_ledger  # noqa: E402


class GeneratedTests(unittest.TestCase):
    """The page is generated from the repository's artefacts."""

    def test_the_committed_page_is_exactly_what_the_generator_writes(self):
        committed = demo_page.PAGE.read_text(encoding="utf-8")
        self.assertEqual(demo_page.build(), committed,
                         "demo.html is not what demo_page.py generates — run "
                         "`python3 demo_page.py`")

    def test_the_check_mode_passes(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "demo_page.py"), "--check"],
            capture_output=True, text=True, cwd=HERE)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("matches the generated output", proc.stdout)


class PageTests(unittest.TestCase):
    """What the page is allowed to claim."""

    @classmethod
    def setUpClass(cls):
        cls.page = demo_page.PAGE.read_text(encoding="utf-8")
        cls.text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", cls.page))

    def test_the_page_describes_this_entry(self):
        self.assertIn("Nebius × NVIDIA Global AI Hackathon", self.page)
        self.assertIn("Best Apps and Agents", self.page)
        self.assertIn("api.tokenfactory.nebius.com/v1", self.page)

    def test_the_page_does_not_describe_a_different_hackathon(self):
        # It used to. A judge landing on a page for another event reads the
        # wrong entry.
        for stale in ("Open Agent Hackathon 2026 · Track 02",
                      "Track 02: The Agent That Can Explain Why"):
            self.assertNotIn(stale, self.page,
                             f"the page still claims {stale!r}")

    def test_the_page_points_at_this_entry_s_video(self):
        self.assertIn("why-agent-nebius-demo.mp4", self.page)
        self.assertIn('<source src="why-agent-nebius-demo.mp4"', self.page)

    def test_the_page_links_the_case_lab_and_the_repository(self):
        self.assertIn('href="demo_lab/"', self.page)
        self.assertIn("https://github.com/Snedz/why-agent", self.page)

    def test_every_model_id_on_the_page_is_the_pinned_one(self):
        import providers
        models = providers.PROFILES["nebius"]["models"]
        for tier in ("standard", "fast", "deep", "vision"):
            self.assertIn(models[tier], self.page,
                          f"the page does not name the {tier} model id")

    def test_the_scores_on_the_page_are_the_committed_scores(self):
        got, truth = demo_page.corpus_scores()
        counts = __import__("benchmark.score", fromlist=["score_counts"]).score_counts(got, truth)
        self.assertIn(f"<b class=\"good\">{counts['correct']}/{counts['total']}</b>",
                      self.page)
        lanes = demo_page.lane_scores()
        for tier, s in lanes.items():
            self.assertIn(f"<b>{s['correct']}/{s['total']}</b>", self.page,
                          f"the page does not carry the {tier} lane's score")

    def test_the_cost_and_retry_count_on_the_page_are_the_committed_ones(self):
        summary = tier_ledger.load_json(tier_ledger.BENCH_RESULTS).get("summary") or {}
        self.assertIn(f"${float(summary.get('total_cost_usd') or 0.0):.3f}", self.page)
        self.assertIn(f"{summary.get('retries', 0)} retries", self.page)

    def test_the_excerpt_is_the_tools_real_output(self):
        """The excerpt is a verbatim slice of `demo.py` — not a nicer story."""
        out = subprocess.run([sys.executable, os.path.join(HERE, "demo.py")],
                             capture_output=True, text=True, cwd=HERE).stdout
        block = demo_page.excerpt()
        self.assertIn(block, out, "the excerpt is not a verbatim slice of demo.py")
        for line in block.splitlines():
            if not line.strip():
                continue
            self.assertIn(line, self.text,
                          f"the excerpt line {line!r} is not on the page")

    def test_the_page_says_the_claims_are_synthetic(self):
        self.assertIn("Synthetic data only", self.page)

    def test_the_page_makes_no_network_request(self):
        self.assertNotIn("<script", self.page)
        self.assertNotIn('src="http', self.page)


if __name__ == "__main__":
    unittest.main()
