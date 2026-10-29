"""Offline tests for batch_eval.py — the tiered batch harness.

    python3 -m unittest test_batch_eval -v

No network, no third-party package, no real API key: the lane call is stubbed
at `review._chat`, and the provider profile is resolved from a fake key in the
environment. The fixture is the repo's own `evidence/items.jsonl`, so the
agreement counts the harness prints are computed from real rows rather than
from numbers written into a test.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import batch_eval  # noqa: E402
import evidence as ev  # noqa: E402
import review  # noqa: E402

FIXTURE = os.path.join(HERE, "evidence", "items.jsonl")

# A verdict that is never the item's own deterministic one, so "agrees" and
# "disagrees" mean what they say. No fixed point: every deterministic verdict
# in the fixture maps to a DIFFERENT verdict.
FLIP = {"CORROBORATED": "CONFLICTED", "PARTIAL": "CORROBORATED",
        "CONFLICTED": "PARTIAL", "NO EVIDENCE": "CORROBORATED"}


def deterministic_verdicts() -> dict:
    """The deterministic verdict per item, read from the fixture."""
    items = ev.load_items(FIXTURE)
    claims = ev.load_evidence(FIXTURE)
    return {i: ev.explain(items, claims, i).confidence() for i in sorted(items)}


class RetryPathTests(unittest.TestCase):
    """_with_retries: a timeout or a 5xx from a cold model is weather, not a verdict."""

    def test_a_timeout_then_success_proves_the_retry_path(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 2:
                raise TimeoutError("cold model load")
            return ("VERDICT: CORROBORATED - synthetic", {"prompt_tokens": 10,
                                                           "completion_tokens": 5})

        # base_delay=0 so the test does not wait out the real backoff.
        value, retries_used = batch_eval._with_retries(flaky, attempts=3, base_delay=0)
        self.assertEqual(value[0], "VERDICT: CORROBORATED - synthetic")
        self.assertEqual(retries_used, 1, "one failure, one retry")
        self.assertEqual(len(calls), 2, "the lane was called twice, not three times")

    def test_a_lane_that_keeps_failing_raises_the_last_failure(self):
        calls = []

        def always_bad():
            calls.append(1)
            raise OSError("endpoint unreachable")

        with self.assertRaises(OSError):
            batch_eval._with_retries(always_bad, attempts=3, base_delay=0)
        self.assertEqual(len(calls), 3, "it tried the number of attempts it was given")

    def test_a_url_error_is_retried_the_same_way(self):
        import urllib.error
        calls = []

        def url_bad():
            calls.append(1)
            if len(calls) < 2:
                raise urllib.error.URLError("connection reset")
            return "ok"

        value, retries_used = batch_eval._with_retries(url_bad, attempts=3, base_delay=0)
        self.assertEqual(value, "ok")
        self.assertEqual(retries_used, 1)


class BudgetCapTests(unittest.TestCase):
    """The budget cap is a STOP, not a note: no lane call may happen past it."""

    def test_the_budget_cap_stops_the_calls_and_marks_them_skipped(self):
        called = []

        def forbidden(*args, **kwargs):
            called.append(1)
            raise AssertionError("no lane call may happen once the budget is spent")

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "results.json")
            with mock.patch.dict(os.environ, {"NEBIUS_API_KEY": "test-key"}):
                with mock.patch.object(review, "_chat", forbidden):
                    rc = batch_eval.main(["--evidence", FIXTURE, "--budget", "0",
                                          "--out", out])
            self.assertEqual(rc, 0)
            self.assertEqual(called, [], "the lane must not be called once the cap is reached")
            payload = json.load(open(out, encoding="utf-8"))

        for entry in payload["results"]:
            for tier, outcome in entry["tiers"].items():
                self.assertEqual(outcome["verdict"], "SKIPPED-BUDGET",
                                 f"{entry['item']}/{tier} should be SKIPPED-BUDGET")
        self.assertTrue(payload["results"], "the fixture has items, so results are not empty")

    def test_the_narration_is_skipped_too_when_the_budget_is_spent(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "results.json")
            with mock.patch.dict(os.environ, {"NEBIUS_API_KEY": "test-key"}):
                with mock.patch.object(review, "_chat",
                                       side_effect=AssertionError("no lane call")):
                    rc = batch_eval.main(["--evidence", FIXTURE, "--budget", "0",
                                          "--narrate", "--out", out])
            self.assertEqual(rc, 0)
            payload = json.load(open(out, encoding="utf-8"))
        for entry in payload["results"]:
            self.assertEqual(entry["narration"]["check"], "SKIPPED-BUDGET")


class AgreementCountTests(unittest.TestCase):
    """The summary's agreement counts are computed from the rows, not typed in."""

    def _run_with_stub(self, stub):
        tmp = tempfile.mkdtemp()
        out = os.path.join(tmp, "results.json")
        with mock.patch.dict(os.environ, {"NEBIUS_API_KEY": "test-key"}):
            with mock.patch.object(review, "_chat", stub):
                rc = batch_eval.main(["--evidence", FIXTURE, "--budget", "1",
                                      "--out", out])
        self.assertEqual(rc, 0)
        with open(out, encoding="utf-8") as fh:
            return json.load(fh)

    def test_agreement_counts_are_computed_from_the_rows(self):
        det = deterministic_verdicts()
        agree_with = sorted(det)[0]  # the stub agrees for exactly one item

        def stub(base_url, api_key, model, prompt, timeout=180):
            item = next((i for i in sorted(det) if i in prompt), None)
            verdict = det[item] if item == agree_with else FLIP[det[item]]
            return (f"VERDICT: {verdict} - synthetic stub",
                    {"prompt_tokens": 1000, "completion_tokens": 500})

        payload = self._run_with_stub(stub)
        results = payload["results"]
        summary = payload["summary"]

        # Recount from the rows themselves.
        judged = [e for e in results
                  if e["tiers"].get("fast", {}).get("agrees_with_deterministic") is not None]
        agree = sum(1 for e in judged if e["tiers"]["fast"]["agrees_with_deterministic"])
        self.assertEqual(summary["tier_agreement"]["fast"], f"{agree}/{len(judged)}")
        self.assertEqual(len(judged), len(det), "every fixture item is judged on the fast tier")
        # The mix is real: a hardcoded count could not produce it.
        self.assertGreaterEqual(agree, 1)
        self.assertLess(agree, len(judged))

    def test_every_tier_gets_its_own_agreement_count(self):
        det = deterministic_verdicts()

        def stub(base_url, api_key, model, prompt, timeout=180):
            item = next((i for i in sorted(det) if i in prompt), None)
            return (f"VERDICT: {FLIP[det[item]]} - synthetic stub",
                    {"prompt_tokens": 1000, "completion_tokens": 500})

        payload = self._run_with_stub(stub)
        summary = payload["summary"]
        for tier in ("fast", "deep"):
            self.assertIn(tier, summary["tier_agreement"])
            agree, _, judged = summary["tier_agreement"][tier].partition("/")
            self.assertEqual(int(judged), len(det))
            self.assertEqual(int(agree), 0, "the stub contradicts every item on every tier")

    def test_the_cost_is_counted_and_the_tokens_are_recorded(self):
        det = deterministic_verdicts()

        def stub(base_url, api_key, model, prompt, timeout=180):
            item = next((i for i in sorted(det) if i in prompt), None)
            return (f"VERDICT: {FLIP[det[item]]} - synthetic stub",
                    {"prompt_tokens": 1234, "completion_tokens": 567})

        payload = self._run_with_stub(stub)
        entry = payload["results"][0]
        self.assertEqual(entry["tiers"]["fast"]["tokens"], [1234, 567])
        self.assertGreater(payload["summary"]["total_cost_usd"], 0.0,
                           "a run that spends tokens reports a cost")


if __name__ == "__main__":
    unittest.main()
