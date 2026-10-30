"""Tests for the benchmark runner — `benchmark/score.py`.

    python3 -m unittest test_benchmark -v

Offline: no network, no lane call, no model. The lanes are STUBBED — a
stub eval-results file the test writes, with verdicts the test invents — so the
runner is exercised exactly as it runs over a real batch, and nothing reaches
out.

The card's gates are the four tests named `test_the_...` below: the runner runs
offline against stub transports; the planted truth is separate from what the
lanes see; a deliberately mislabelled control case makes the gate fail; and no
number appears in a doc that the runner did not print.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.join(HERE, "benchmark")
sys.path.insert(0, BENCH)
sys.path.insert(0, HERE)

import evidence as ev  # noqa: E402
from score import (classify_flag, narration_flag_classes,  # noqa: E402
                    score_counts, score_verdicts)

CASES = os.path.join(BENCH, "cases.jsonl")
TRUTH = os.path.join(BENCH, "truth.json")
EVAL = os.path.join(BENCH, "eval-benchmark-2026-10-28.json")
RESULTS_DOC = os.path.join(HERE, "docs", "BENCHMARK_RESULTS_2026-10-28.md")

# A stub lane: the truth with one item flipped, so the gate has something to
# catch and the runner has a false approval to report.
STUB_FLANKED = {"bm-clean-ship": "CONFLICTED"}


def stub_eval_results(truth: dict) -> dict:
    """A stub batch_eval output: one lane, one item deliberately mislabelled."""
    return {
        "summary": {"items": len(truth), "total_cost_usd": 0.0, "retries": 0,
                    "tier_agreement": {"fast": "0/0"},
                    "narration_checks": {"PASSED": 0, "FAILED": 0}},
        "results": [
            {"item": item_id, "deterministic": truth[item_id],
             "tiers": {"fast": {"verdict": verdict,
                                "agrees_with_deterministic": verdict == truth[item_id],
                                "cost_usd": 0.0, "tokens": [0, 0]},
                       "narration": {"check": "PASSED", "unsupported_values": []}}}
            for item_id, verdict in sorted({**truth, **STUB_FLANKED}.items())
        ],
    }


class RunnerTests(unittest.TestCase):
    """The runner runs, offline, over stub transports."""

    def test_the_runner_scores_a_stub_lane_offline(self):
        truth = json.loads(Path(TRUTH).read_text(encoding="utf-8"))
        tmp = tempfile.mkdtemp(prefix="bench-")
        self.addCleanup(shutil.rmtree, tmp, True)
        stub = os.path.join(tmp, "stub-eval.json")
        with open(stub, "w", encoding="utf-8") as fh:
            json.dump(stub_eval_results(truth), fh)

        proc = subprocess.run(
            [sys.executable, os.path.join(BENCH, "score.py"),
             "--cases", CASES, "--truth", TRUTH, "--eval-results", stub],
            capture_output=True, text=True, cwd=HERE)
        printed = proc.stdout

        self.assertIn("[deterministic] 14/14 correct", printed)
        # The stub lane agrees with the truth everywhere except the flipped item.
        self.assertIn("[lane:fast] 13/14 correct", printed)
        self.assertIn("bm-clean-ship", printed)
        self.assertEqual(proc.returncode, 1, "a lane's false approval fails the run")

    def test_the_gate_still_passes_on_the_corpus(self):
        truth = json.loads(Path(TRUTH).read_text(encoding="utf-8"))
        items = ev.load_items(CASES)
        claims = ev.load_evidence(CASES)
        got = {item_id: ev.explain(items, claims, item_id).confidence()
               for item_id in truth}
        counts = score_counts(got, truth)
        self.assertEqual((counts["correct"], counts["total"]), (14, 14))
        self.assertEqual(counts["false_approvals"], [],
                         "the deterministic gate must have no false approval")


class TruthSeparationTests(unittest.TestCase):
    """The planted truth is not in what the lanes see."""

    def test_the_corpus_carries_no_planted_truth(self):
        rows = [json.loads(line) for line in Path(CASES).read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")]
        for row in rows:
            for key in ("truth", "expected", "verdict", "planted", "label"):
                self.assertNotIn(key, row,
                                 f"a corpus row carries {key!r}: the lanes must not see the truth")
            self.assertNotIn("CORROBORATED", str(row.get("value", "")))
            self.assertNotIn("CONFLICTED", str(row.get("value", "")))
            self.assertNotIn("PARTIAL", str(row.get("value", "")))

    def test_the_truth_file_is_not_in_the_corpus(self):
        truth = json.loads(Path(TRUTH).read_text(encoding="utf-8"))
        corpus = Path(CASES).read_text(encoding="utf-8")
        for item_id, expected in truth.items():
            self.assertNotIn(f'"{expected}"', corpus,
                             f"the planted verdict for {item_id} appears in the corpus")

    def test_scoring_a_lane_needs_the_lane_verdicts_not_the_truth(self):
        # The scorer compares; it never derives a lane's verdict from the truth.
        truth = json.loads(Path(TRUTH).read_text(encoding="utf-8"))
        lane = dict.fromkeys(truth, "CORROBORATED")
        counts = score_counts(lane, truth)
        expected_false = sum(1 for v in truth.values() if v != "CORROBORATED")
        self.assertEqual(counts["correct"], sum(1 for v in truth.values() if v == "CORROBORATED"))
        self.assertEqual(len(counts["false_approvals"]), expected_false)


class ControlCaseTests(unittest.TestCase):
    """A deliberately mislabelled control case makes the gate fail."""

    def test_a_mislabelled_control_case_makes_the_gate_fail(self):
        truth = json.loads(Path(TRUTH).read_text(encoding="utf-8"))
        items = ev.load_items(CASES)
        claims = ev.load_evidence(CASES)
        got = {item_id: ev.explain(items, claims, item_id).confidence()
               for item_id in truth}

        clean = score_counts(got, truth)
        self.assertEqual(clean["false_approvals"], [])

        # Mislabel ONE item's planted truth. The gate must now refuse it.
        item_id = "bm-clean-ship"
        broken_truth = dict(truth)
        broken_truth[item_id] = "CONFLICTED"
        broken = score_counts(got, broken_truth)
        self.assertEqual(broken["correct"], clean["correct"] - 1)
        self.assertEqual(broken["false_approvals"], [item_id],
                         "the mislabelled case is a false approval, and it must be named")

    def test_the_gate_exits_non_zero_when_a_control_case_is_mislabelled(self):
        truth = json.loads(Path(TRUTH).read_text(encoding="utf-8"))
        tmp = tempfile.mkdtemp(prefix="bench-bad-")
        self.addCleanup(shutil.rmtree, tmp, True)
        broken = os.path.join(tmp, "truth.json")
        mislabelled = dict(truth)
        mislabelled["bm-clean-ship"] = "CONFLICTED"
        with open(broken, "w", encoding="utf-8") as fh:
            json.dump(mislabelled, fh)

        proc = subprocess.run(
            [sys.executable, os.path.join(BENCH, "score.py"),
             "--cases", CASES, "--truth", broken],
            capture_output=True, text=True, cwd=HERE)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("GATE: FAIL", proc.stdout)
        self.assertIn("bm-clean-ship", proc.stdout)


class GateVersusLanesTests(unittest.TestCase):
    """The gate and the lanes are reported on separate lines, and mean
    different things. A lane's false approval is a finding about the model; it
    is not the gate failing, and the output must not conflate them."""

    def _run(self, *extra):
        return subprocess.run(
            [sys.executable, os.path.join(BENCH, "score.py"),
             "--cases", CASES, "--truth", TRUTH, "--eval-results", EVAL, *extra],
            capture_output=True, text=True, cwd=HERE)

    def test_the_committed_run_passes_the_gate_and_fails_the_lanes(self):
        proc = self._run()
        self.assertIn("GATE: PASS", proc.stdout)
        self.assertIn("LANES: FAIL", proc.stdout)
        # The lane failures are still named, one by one, above the summary.
        self.assertIn("MISS bm-card-lies", proc.stdout)
        self.assertIn("FALSE APPROVALS: bm-card-lies, bm-missing-cause", proc.stdout)

    def test_the_exit_code_follows_the_gate_not_the_lanes(self):
        self.assertEqual(self._run().returncode, 0,
                         "a lane's false approval is a finding, not a gate failure")

    def test_strict_lanes_opts_in_to_failing_on_a_lane_false_approval(self):
        proc = self._run("--strict-lanes")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("LANES: FAIL", proc.stdout)

    def test_the_gate_line_does_not_move_when_the_lanes_misbehave(self):
        proc = self._run()
        gate_lines = [l for l in proc.stdout.splitlines() if l.startswith("GATE:")]
        self.assertEqual(gate_lines, ["GATE: PASS — zero false approvals"])
        lane_lines = [l for l in proc.stdout.splitlines() if l.startswith("LANES:")]
        self.assertEqual(len(lane_lines), 1)
        self.assertIn("3 false approval(s)", lane_lines[0])

    def test_a_lane_failure_does_not_stop_the_gate_printing_pass(self):
        """The gate's line is a statement about the gate, not about the run."""
        proc = self._run("--strict-lanes")
        self.assertIn("GATE: PASS", proc.stdout)
        self.assertEqual(proc.returncode, 1, "strict mode still reports failure")


class FlagClassTests(unittest.TestCase):
    """The narration flags are classified, and the classes account for all."""

    def test_the_classes_account_for_every_flag(self):
        payload = json.loads(Path(EVAL).read_text(encoding="utf-8"))
        claims = ev.load_evidence(CASES)
        sources = {c.source for c in claims}
        classes = narration_flag_classes(payload["results"], sources)
        flags = sum(1 for r in payload["results"]
                    for _ in (r.get("narration") or {}).get("unsupported_values", []))
        self.assertEqual(sum(classes.values()), flags)
        self.assertEqual(classes.get("invented", 0), 0,
                         "the run invented no facts, and that is the finding")

    def test_a_value_the_evidence_does_not_contain_is_invented(self):
        self.assertEqual(classify_flag("a number nobody recorded", {"ci"}), "invented")
        self.assertEqual(classify_flag("UNKNOWN", {"ci"}), "system vocabulary")
        self.assertEqual(classify_flag("CI", {"ci"}), "source reference")
        self.assertEqual(classify_flag("example.com/ok", {"ci"}), "locator fragment")
        self.assertEqual(classify_flag("CONFLICT", {"ci"}), "verdict variant")
        self.assertEqual(classify_flag('""', {"ci"}), "quoted empty value")


class DocumentTraceabilityTests(unittest.TestCase):
    """No number appears in a doc that the runner did not print."""

    def _runner_output(self) -> str:
        proc = subprocess.run(
            [sys.executable, os.path.join(BENCH, "score.py"),
             "--cases", CASES, "--truth", TRUTH, "--eval-results", EVAL],
            capture_output=True, text=True, cwd=HERE)
        return proc.stdout

    def test_every_number_in_the_results_doc_is_printed_by_the_runner(self):
        printed = self._runner_output()
        text = Path(RESULTS_DOC).read_text(encoding="utf-8")
        # A date is not a measurement; everything else that looks like a figure is.
        # A date is not a measurement. Note: no \b before the year -- an
        # underscore is a word character, so "ANALYSIS_2026-10-28.md" has no
        # boundary before the year and \b would miss it.
        without_dates = re.sub(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)", " ", text)
        numbers = set(re.findall(r"\d+(?:\.\d+)?", without_dates))
        missing = sorted(n for n in numbers if n not in printed)
        self.assertEqual(missing, [],
                         "these figures appear in the results doc but the runner never "
                         f"printed them: {missing}")


if __name__ == "__main__":
    unittest.main()
