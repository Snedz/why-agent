"""Tests for spans.py — the opt-in GenAI span hook.

    python3 -m unittest test_spans -v

Offline: no model, no network. The lane is stubbed, so the hook is exercised
without calling anything.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import evidence as ev  # noqa: E402
import narrate  # noqa: E402
import review  # noqa: E402
import spans  # noqa: E402

FIXTURE = str(HERE / "evidence" / "items.jsonl")
VERDICT = "VERDICT: CONFLICTED — the card and the check disagree."


class SpanTests(unittest.TestCase):
    """What a span carries, and what it must not."""

    def setUp(self):
        spans.clear()
        self.addCleanup(spans.clear)

    def _switch_on(self):
        original = os.environ.get(spans.SPAN_ENV)
        os.environ[spans.SPAN_ENV] = "1"

        def restore():
            if original is None:
                os.environ.pop(spans.SPAN_ENV, None)
            else:
                os.environ[spans.SPAN_ENV] = original
        self.addCleanup(restore)

    def test_the_hook_is_off_by_default(self):
        self.assertFalse(spans.enabled({}))
        self.assertFalse(spans.enabled({"WHY_AGENT_SPANS": ""}))
        self.assertFalse(spans.enabled({"WHY_AGENT_SPANS": "  "}))
        self.assertIsNone(spans.record(operation="review", model="m", provider="p",
                                       tier="fast"))
        self.assertEqual(spans.recorded(), [])

    def test_a_recorded_span_carries_the_facts(self):
        self._switch_on()
        span = spans.record(operation="review", model="nvidia/Nemotron-3-Nano-30B-A3B",
                            provider="Nebius Token Factory", tier="fast",
                            latency_ms=1234.5, input_tokens=3833, output_tokens=10881,
                            cost_usd=0.0028, verdict="CONFLICTED", retry_count=1)
        self.assertIsNotNone(span)
        attributes = span["attributes"]
        self.assertEqual(attributes["gen_ai.request.model"],
                         "nvidia/Nemotron-3-Nano-30B-A3B")
        self.assertEqual(attributes["gen_ai.system"], "Nebius Token Factory")
        self.assertEqual(attributes["gen_ai.tier"], "fast")
        self.assertEqual(attributes["gen_ai.usage.input_tokens"], 3833)
        self.assertEqual(attributes["gen_ai.usage.output_tokens"], 10881)
        self.assertEqual(attributes["gen_ai.cost_usd"], 0.0028)
        self.assertEqual(attributes["gen_ai.response.verdict"], "CONFLICTED")
        self.assertEqual(attributes["gen_ai.retry_count"], 1)
        self.assertEqual(attributes["gen_ai.response.latency_ms"], 1234.5)
        self.assertEqual(len(spans.recorded()), 1)

    def test_a_span_carries_no_prompt_and_no_claim_content(self):
        self._switch_on()
        span = spans.record(operation="narration", model="m", provider="p",
                            tier="narration", verdict="FAILED")
        blob = json.dumps(span).lower()
        for banned in ("prompt", "message", "content", "claim", "statement",
                       "narrative", "unsupported"):
            self.assertNotIn(banned, blob,
                             f"a span must not carry {banned!r}")

    def test_the_hook_cannot_record_a_field_it_does_not_name(self):
        # The signature admits no free-form fields, so content cannot be
        # recorded even by accident.
        with self.assertRaises(TypeError):
            spans.record(operation="review", model="m", provider="p", tier="fast",
                         prompt="the claims of the item")
        with self.assertRaises(TypeError):
            spans.record(operation="review", model="m", provider="p", tier="fast",
                         extra={"claim": "the card was marked DONE"})

    def test_the_hook_writes_nothing_to_disk(self):
        self._switch_on()
        source = (HERE / "spans.py").read_text(encoding="utf-8")
        for banned in ("open(", "write_text", "os.remove", "Path("):
            self.assertNotIn(banned, source,
                             f"the span hook must not touch the disk ({banned})")
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                spans.record(operation="review", model="m", provider="p", tier="fast")
                self.assertEqual(os.listdir(tmp), [],
                                 "recording a span created a file")
            finally:
                os.chdir(cwd)


class LaneHookTests(unittest.TestCase):
    """The lanes record spans, and the hook changes nothing else."""

    def setUp(self):
        spans.clear()
        self.addCleanup(spans.clear)
        self.tmp = tempfile.mkdtemp(prefix="spans-")
        self.out = os.path.join(self.tmp, "verdicts.jsonl")

    def _run_lane(self, switch):
        env = {"NEBIUS_API_KEY": "test-key"}
        if switch:
            env["WHY_AGENT_SPANS"] = "1"
        original = dict(os.environ)
        os.environ.clear()
        os.environ.update(env)
        try:
            with mock.patch.object(review, "_chat",
                                           return_value=(VERDICT, {"prompt_tokens": 100,
                                                                  "completion_tokens": 20})):
                rc = review.main(["--evidence", FIXTURE, "--item", "why-alpha",
                                   "--tiers", "fast", "--out", self.out])
        finally:
            os.environ.clear()
            os.environ.update(original)
        return rc

    def test_a_disabled_hook_leaves_behaviour_identical(self):
        # The lane APPENDS its verdict rows, so each run gets its own file.
        self._run_lane(False)
        with_off = open(self.out, encoding="utf-8").read()
        spans.clear()
        other = os.path.join(self.tmp, "verdicts-on.jsonl")
        self.out = other
        self._run_lane(True)
        with_on = open(other, encoding="utf-8").read()
        self.assertEqual(with_off, with_on,
                         "the hook must not change what the lane writes")
        self.assertEqual(len(spans.recorded()), 1,
                         "with the hook on, the lane recorded a span")

    def test_the_lane_span_carries_the_model_the_tier_and_the_verdict(self):
        self._run_lane(True)
        self.assertEqual(len(spans.recorded()), 1)
        attributes = spans.recorded()[0]["attributes"]
        self.assertEqual(attributes["gen_ai.operation.name"], "review")
        self.assertEqual(attributes["gen_ai.tier"], "fast")
        self.assertEqual(attributes["gen_ai.system"], "Nebius Token Factory")
        self.assertEqual(attributes["gen_ai.response.verdict"], "CONFLICTED")
        self.assertIn("Nemotron", attributes["gen_ai.request.model"])

    def test_the_deterministic_verdict_is_the_same_either_way(self):
        items = ev.load_items(FIXTURE)
        claims = ev.load_evidence(FIXTURE)
        before = ev.explain(items, claims, "why-alpha").confidence()
        self._run_lane(True)
        after = ev.explain(items, claims, "why-alpha").confidence()
        self.assertEqual(before, after)


class NarrationHookTests(unittest.TestCase):
    """The narration lane records its own span, with the checker's outcome."""

    def test_a_failed_check_is_recorded_as_failed_and_the_text_is_not(self):
        spans.clear()
        original = os.environ.get(spans.SPAN_ENV)
        os.environ[spans.SPAN_ENV] = "1"
        self.addCleanup(lambda: os.environ.pop(spans.SPAN_ENV, None)
                        if original is None else None)
        self.addCleanup(spans.clear)
        items = ev.load_items(FIXTURE)
        claims = ev.load_evidence(FIXTURE)
        result = ev.reconcile(items["why-alpha"], claims)
        original = narrate.call_openai_compatible
        narrate.call_openai_compatible = lambda *a, **k: "The amount was 999999 dollars."
        try:
            outcome = narrate.narrate(result)
        finally:
            narrate.call_openai_compatible = original
        self.assertEqual(len(spans.recorded()), 1)
        attributes = spans.recorded()[0]["attributes"]
        self.assertEqual(attributes["gen_ai.operation.name"], "narration")
        self.assertEqual(attributes["gen_ai.tier"], "narration")
        self.assertEqual(attributes["gen_ai.response.verdict"], "FAILED")
        blob = json.dumps(spans.recorded()[0])
        self.assertNotIn("999999", blob,
                         "the narration TEXT is content, and must not be in a span")


if __name__ == "__main__":
    unittest.main()
