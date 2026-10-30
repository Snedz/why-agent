"""Tests for the Case Lab — demo_lab/build.py and demo_lab/flip_check.py.

    python3 -m unittest test_case_lab -v

Offline, no model, no network. The gates are the card's: all five cases render
from their files with no network; the two lane-dependent cases demonstrably
flip if their lane rows are removed; and no claim on the page lacks a receipt
in its case file.
"""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "demo_lab"))

import build as lab_build  # noqa: E402
import evidence as ev  # noqa: E402


class GeneratedTests(unittest.TestCase):
    """The page is generated from the corpus, not typed."""

    def test_the_committed_page_is_exactly_what_the_generator_writes(self):
        for path, body in lab_build.generate():
            committed = path.read_text(encoding="utf-8")
            self.assertEqual(body, committed,
                             f"{path.relative_to(lab_build.ROOT)} is not what "
                             f"demo_lab/build.py generates — run `python3 demo_lab/build.py`")

    def test_running_the_builder_twice_produces_the_same_bytes(self):
        first = [(p, b) for p, b in lab_build.generate()]
        second = [(p, b) for p, b in lab_build.generate()]
        self.assertEqual([b for _, b in first], [b for _, b in second])

    def test_the_check_mode_passes(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "demo_lab", "build.py"), "--check"],
            capture_output=True, text=True, cwd=HERE)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("match the committed output", proc.stdout)


class PageTests(unittest.TestCase):
    """What the page is allowed to do, and what it must carry."""

    def setUp(self):
        self.page = lab_build.INDEX.read_text(encoding="utf-8")
        self.cases = [json.loads(p.read_text(encoding="utf-8"))
                      for p in sorted(lab_build.OUT_DIR.glob("*.json"))]

    def test_the_page_makes_no_network_request(self):
        # "renders from their files with no network": nothing on the page may
        # fetch. A <script>, a remote <img> or a remote <a> would all be a
        # request the judge cannot reproduce offline.
        self.assertNotIn("<script", self.page)
        self.assertNotIn('src="http', self.page)
        self.assertNotIn('href="http', self.page)

    def test_every_case_is_present_and_labelled(self):
        self.assertGreaterEqual(len(self.cases), 5,
                                "the card asks for five cases")
        for case in self.cases:
            self.assertIn(case["case_id"], self.page)
            self.assertEqual(case["labels"]["provenance"], "RECORDED")
            self.assertEqual(case["labels"]["data"], "SYNTHETIC")

    def test_all_four_verdict_states_and_a_narration_failure_are_shown(self):
        verdicts = {c["verdict"] for c in self.cases}
        for state in ("CORROBORATED", "PARTIAL", "CONFLICTED", "NO EVIDENCE"):
            self.assertIn(state, verdicts, f"no case shows {state}")
        failed = [c for c in self.cases if c["narration"]["check"] == "FAILED"]
        self.assertTrue(failed, "no case shows a narration CHECK FAILED")

    def test_no_claim_on_the_page_lacks_a_receipt_in_its_case_file(self):
        for case in self.cases:
            for claim in case["claims"]:
                self.assertTrue(claim["locator"],
                                f"{case['case_id']}: claim {claim['statement']!r} "
                                f"has no locator")
                self.assertTrue(claim["receipt"],
                                f"{case['case_id']}: claim {claim['statement']!r} "
                                f"has no receipt file")
                self.assertTrue(
                    (lab_build.ROOT / claim["receipt"]).exists(),
                    f"{case['case_id']}: receipt {claim['receipt']} does not exist")

    def test_every_claim_on_the_page_names_its_receipt(self):
        for case in self.cases:
            for claim in case["claims"]:
                self.assertIn(claim["receipt"], self.page,
                              f"{case['case_id']}: receipt for {claim['statement']!r} "
                              f"is not shown on the page")

    def test_no_claim_was_hand_typed(self):
        """Every claim in a case file is a row from the corpus, unchanged."""
        for case in self.cases:
            path = (lab_build.CORPUS if case["case_id"].startswith("bm-")
                    else lab_build.ITEMS)
            original = {(c.source, c.statement, c.value, c.locator)
                        for c in ev.load_evidence(str(path))
                        if c.item_id == case["case_id"]}
            for claim in case["claims"]:
                key = (claim["source"], claim["statement"], claim["value"],
                       claim["locator"])
                self.assertIn(key, original,
                              f"{case['case_id']}: {key!r} is not a corpus row")

    def test_every_lane_receipt_names_its_model_and_endpoint(self):
        endpoint = lab_build.providers.PROFILES["nebius"]["base_url"]
        found = False
        for case in self.cases:
            for lane in case["lane_receipts"]:
                if lane["lane"] in ("reviewer-fast", "reviewer-deep"):
                    found = True
                    self.assertTrue(lane["model_id"].startswith("nvidia/"))
                    self.assertEqual(lane["endpoint"], endpoint)
                    self.assertIsNotNone(lane["cost_usd"])
                    self.assertEqual(len(lane["tokens"]), 2)
        self.assertTrue(found, "no reviewer lane receipt on the page")


class FlipTests(unittest.TestCase):
    """The card's own gate: the lane-dependent cases really depend on their lanes."""

    def test_the_flip_check_passes(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "demo_lab", "flip_check.py")],
            capture_output=True, text=True, cwd=HERE)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("lane-dependent cases: 2", proc.stdout)
        self.assertIn("PASS", proc.stdout)

    def test_two_cases_flip_and_the_rest_do_not_claim_to(self):
        cases = [json.loads(p.read_text(encoding="utf-8"))
                 for p in sorted(lab_build.OUT_DIR.glob("*.json"))]
        dependent = [c for c in cases if c["lane_dependency"]["lane_rows"]]
        self.assertEqual(len(dependent), 2)
        for case in dependent:
            self.assertTrue(case["lane_dependency"]["flips"])
            self.assertNotEqual(case["verdict"],
                                case["lane_dependency"]["verdict_without_lane_rows"])

    def test_the_flip_check_fails_when_a_lane_row_is_silently_removed(self):
        """A check that cannot fail is a comment. Break a case and it must fail."""
        import shutil
        import tempfile
        tmp = tempfile.mkdtemp(prefix="case-lab-break-")
        self.addCleanup(shutil.rmtree, tmp, True)
        shutil.copytree(os.path.join(HERE, "demo_lab"), os.path.join(tmp, "demo_lab"))
        for name in ("providers.py", "evidence.py"):
            shutil.copy(os.path.join(HERE, name), os.path.join(tmp, name))
        # The flip check re-reads the ORIGINAL rows, so the corpus has to come
        # along — otherwise the check would crash on a missing file instead of
        # reporting the broken case.
        shutil.copytree(os.path.join(HERE, "benchmark"), os.path.join(tmp, "benchmark"))
        os.makedirs(os.path.join(tmp, "evidence"), exist_ok=True)
        shutil.copy(os.path.join(HERE, "evidence", "items.jsonl"),
                    os.path.join(tmp, "evidence", "items.jsonl"))
        target = os.path.join(tmp, "demo_lab", "cases", "bm-reviewer-split.json")
        case = json.loads(open(target, encoding="utf-8").read())
        case["verdict"] = "CORROBORATED"   # a lie about the verdict
        open(target, "w", encoding="utf-8").write(json.dumps(case, indent=2))
        proc = subprocess.run(
            [sys.executable, os.path.join(tmp, "demo_lab", "flip_check.py")],
            capture_output=True, text=True, cwd=tmp)
        self.assertNotEqual(proc.returncode, 0,
                            "the flip check passed a case whose verdict was wrong")
        self.assertIn("FAIL", proc.stdout)


if __name__ == "__main__":
    unittest.main()
