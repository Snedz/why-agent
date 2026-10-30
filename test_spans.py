"""Tests for spans.py — the opt-in OTLP span hook.

    python3 -m unittest test_spans -v

Offline: no model, no network. The lane is stubbed, so the hook is exercised
without calling anything.

Every assertion about what a span carries is made against the **payload the
stub exporter received**, not against the module's own bookkeeping: the thing
under test is what leaves, so the test reads what left.
"""

import datetime as _dt
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

#: The attribute names the OpenTelemetry GenAI conventions define. A span may
#: carry these and no other `gen_ai.*` name — a name that is invented inside
#: somebody else's namespace is a lie about which conventions are followed.
CONVENTION_NAMES = {
    "gen_ai.operation.name",
    "gen_ai.request.model",
    "gen_ai.provider.name",
    "gen_ai.system",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.input.messages",
    "gen_ai.output.messages",
}


class StubExporter:
    """An exporter that keeps what it was given. The tests read this."""

    def __init__(self):
        self.payloads = []

    def __call__(self, payload):
        self.payloads.append(payload)

    @property
    def count(self):
        return len(self.payloads)

    @staticmethod
    def _decode(value):
        """Decode an OTLP AnyValue into a plain Python value.

        Written out here rather than borrowed from the module, so the test
        checks the wire format instead of trusting the code that wrote it.
        """
        if "stringValue" in value:
            return value["stringValue"]
        if "intValue" in value:
            return int(value["intValue"])
        if "doubleValue" in value:
            return value["doubleValue"]
        if "boolValue" in value:
            return value["boolValue"]
        if "arrayValue" in value:
            return [StubExporter._decode(v) for v in value["arrayValue"]["values"]]
        if "kvlistValue" in value:
            return {item["key"]: StubExporter._decode(item["value"]) for item in value["kvlistValue"]["values"]}
        raise AssertionError(f"unrecognised OTLP value: {value!r}")

    def attributes(self, index=0):
        """The attributes of one exported span, read out of the raw payload."""
        span = self.payloads[index]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        return {item["key"]: self._decode(item["value"]) for item in span["attributes"]}

    def span(self, index=0):
        return self.payloads[index]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]


class _FixedDatetime(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 30, 12, 0, 0, tzinfo=tz)


class _DatetimeShim:
    """A frozen clock, so two lane runs can be compared byte for byte."""

    datetime = _FixedDatetime
    timezone = _dt.timezone


class ExportConfigurationTests(unittest.TestCase):
    """Export is the explicit configuration. Without it, nothing happens."""

    def setUp(self):
        spans.reset()
        self.addCleanup(spans.reset)

    def test_export_is_unconfigured_by_default(self):
        self.assertIsNone(spans.exporter())
        self.assertIsNone(spans.record(lane="review", model="m", provider="p", tier="fast"))
        self.assertFalse(spans.content_capture_enabled({}))

    def test_an_unconfigured_export_is_a_complete_no_op(self):
        # Not "records nothing" — does nothing at all.
        self.assertIsNone(
            spans.record(
                lane="review",
                model="m",
                provider="p",
                tier="fast",
                item_id="why-alpha",
                aspect="outcome",
                verdict="CORROBORATED",
            )
        )
        self.assertIsNone(spans.record(lane="review", model="m", provider="p", tier="fast", prompt="secret"))

    def test_the_content_switch_is_separate_from_the_export_switch(self):
        # Content capture on, export off: still nothing at all.
        spans.set_content_capture(True)
        self.assertIsNone(spans.record(lane="review", model="m", provider="p", tier="fast", prompt="secret"))
        self.assertIsNone(spans.exporter())

    def test_a_broken_exporter_in_the_environment_leaves_the_lane_alone(self):
        # A configuration error is reported once, loudly, and the lane is not
        # taken down by it.
        with mock.patch.dict(os.environ, {spans.EXPORTER_ENV: "no.such.module:fn"}, clear=False):
            spans.reset()
            self.assertIsNone(spans.record(lane="review", model="m", provider="p", tier="fast"))


class ExportedSpanTests(unittest.TestCase):
    """What the exporter receives."""

    def setUp(self):
        spans.reset()
        self.addCleanup(spans.reset)
        self.exporter = StubExporter()
        spans.set_exporter(self.exporter)

    def test_the_payload_is_shaped_like_an_otlp_export_request(self):
        spans.record(lane="review", model="m", provider="p", tier="fast")
        self.assertEqual(self.exporter.count, 1)
        payload = self.exporter.payloads[0]
        self.assertEqual(list(payload), ["resourceSpans"])
        scope_spans = payload["resourceSpans"][0]["scopeSpans"]
        self.assertEqual(scope_spans[0]["scope"]["name"], "why-agent")
        span = self.exporter.span()
        self.assertEqual(len(span["traceId"]), 32)
        self.assertEqual(len(span["spanId"]), 16)
        int(span["traceId"], 16)
        int(span["spanId"], 16)
        self.assertEqual(span["kind"], 3)  # CLIENT
        self.assertEqual(span["status"], {"code": 1})
        self.assertLess(int(span["startTimeUnixNano"]), int(span["endTimeUnixNano"]) + 1)

    def test_the_span_carries_the_genai_attributes(self):
        spans.record(
            lane="review",
            model="nvidia/Nemotron-3-Nano-30B-A3B",
            provider="Nebius Token Factory",
            tier="fast",
            input_tokens=3833,
            output_tokens=10881,
        )
        attributes = self.exporter.attributes()
        self.assertEqual(attributes["gen_ai.operation.name"], "chat")
        self.assertEqual(attributes["gen_ai.request.model"], "nvidia/Nemotron-3-Nano-30B-A3B")
        self.assertEqual(attributes["gen_ai.system"], "Nebius Token Factory")
        self.assertEqual(attributes["gen_ai.provider.name"], "Nebius Token Factory")
        self.assertEqual(attributes["gen_ai.usage.input_tokens"], 3833)
        self.assertEqual(attributes["gen_ai.usage.output_tokens"], 10881)

    def test_the_span_carries_the_why_attributes(self):
        spans.record(
            lane="review",
            model="m",
            provider="p",
            tier="fast",
            item_id="why-alpha",
            aspect="outcome",
            verdict="CONFLICTED",
        )
        attributes = self.exporter.attributes()
        self.assertEqual(attributes["why.item_id"], "why-alpha")
        self.assertEqual(attributes["why.aspect"], "outcome")
        self.assertEqual(attributes["why.verdict"], "CONFLICTED")

    def test_the_house_facts_live_in_the_why_namespace(self):
        spans.record(
            lane="review", model="m", provider="p", tier="fast", cost_usd=0.0028, retry_count=2, latency_ms=1234.5
        )
        attributes = self.exporter.attributes()
        self.assertEqual(attributes["why.lane"], "review")
        self.assertEqual(attributes["why.tier"], "fast")
        self.assertEqual(attributes["why.cost_usd"], 0.0028)
        self.assertEqual(attributes["why.retry_count"], 2)
        self.assertEqual(attributes["why.latency_ms"], 1234.5)

    def test_no_genai_name_is_invented(self):
        # A name that is not in the conventions, inside the conventions'
        # namespace, would be a false claim about which conventions are met.
        spans.record(
            lane="review",
            model="m",
            provider="p",
            tier="fast",
            item_id="why-alpha",
            aspect="outcome",
            verdict="CORROBORATED",
        )
        names = {key for key in self.exporter.attributes() if key.startswith("gen_ai.")}
        self.assertTrue(names)
        self.assertEqual(names - CONVENTION_NAMES, set())

    def test_the_span_states_the_conventions_version_it_follows(self):
        spans.record(lane="review", model="m", provider="p", tier="fast")
        attributes = self.exporter.attributes()
        self.assertEqual(attributes["why.genai_conventions_version"], spans.CONVENTIONS_VERSION)
        self.assertEqual(spans.CONVENTIONS_VERSION, "1.41.0")
        self.assertIn("v1.41.0", spans.CONVENTIONS_SOURCE)

    def test_the_span_name_follows_the_convention(self):
        spans.record(lane="review", model="m", provider="p", tier="fast")
        self.assertEqual(self.exporter.span()["name"], "chat m")


class ContentCaptureTests(unittest.TestCase):
    """Content is off by default, and only content leaves when asked for."""

    def setUp(self):
        spans.reset()
        self.addCleanup(spans.reset)
        self.exporter = StubExporter()
        spans.set_exporter(self.exporter)

    def test_content_is_not_captured_by_default(self):
        spans.record(
            lane="narration",
            model="m",
            provider="p",
            tier="narration",
            prompt="the claims of the item",
            completion="the narration",
        )
        attributes = self.exporter.attributes()
        self.assertNotIn("gen_ai.input.messages", attributes)
        self.assertNotIn("gen_ai.output.messages", attributes)
        blob = json.dumps(self.exporter.payloads[0])
        self.assertNotIn("the claims of the item", blob)
        self.assertNotIn("the narration", blob)

    def test_content_is_captured_only_when_it_is_explicitly_enabled(self):
        spans.set_content_capture(True)
        spans.record(
            lane="narration",
            model="m",
            provider="p",
            tier="narration",
            prompt="the claims of the item",
            completion="the narration",
        )
        attributes = self.exporter.attributes()
        self.assertIn("gen_ai.input.messages", attributes)
        self.assertIn("gen_ai.output.messages", attributes)
        blob = json.dumps(self.exporter.payloads[0])
        self.assertIn("the claims of the item", blob)
        self.assertIn("the narration", blob)

    def test_the_environment_turns_content_capture_on(self):
        with mock.patch.dict(os.environ, {spans.CONTENT_ENV: "1"}, clear=False):
            self.assertTrue(spans.content_capture_enabled())
        with mock.patch.dict(os.environ, {spans.CONTENT_ENV: "  "}, clear=False):
            self.assertFalse(spans.content_capture_enabled())

    def test_a_span_carries_no_content_leaked_through_a_fact(self):
        # The facts are facts. A claim's text is not a fact about the call.
        spans.record(
            lane="review",
            model="m",
            provider="p",
            tier="fast",
            item_id="why-alpha",
            aspect="outcome",
            verdict="CORROBORATED",
        )
        blob = json.dumps(self.exporter.payloads[0]).lower()
        for banned in ("prompt", "message", "content", "claim", "statement", "narrative", "unsupported"):
            self.assertNotIn(banned, blob, f"a span must not carry {banned!r}")

    def test_the_hook_writes_nothing_to_disk(self):
        source = (HERE / "spans.py").read_text(encoding="utf-8")
        for banned in ("open(", "write_text", "os.remove", "Path("):
            self.assertNotIn(banned, source, f"the span hook must not touch the disk ({banned})")
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                spans.record(lane="review", model="m", provider="p", tier="fast")
                self.assertEqual(os.listdir(tmp), [], "recording a span created a file")
            finally:
                os.chdir(cwd)


class LaneHookTests(unittest.TestCase):
    """The lanes record spans, and the hook changes nothing else."""

    def setUp(self):
        spans.reset()
        self.addCleanup(spans.reset)
        self.tmp = tempfile.mkdtemp(prefix="spans-")
        self.out = os.path.join(self.tmp, "verdicts.jsonl")

    def _run_lane(self, out):
        env = {"NEBIUS_API_KEY": "test-key"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(review, "datetime", _DatetimeShim):
                with mock.patch.object(
                    review, "_chat", return_value=(VERDICT, {"prompt_tokens": 100, "completion_tokens": 20})
                ):
                    return review.main(["--evidence", FIXTURE, "--item", "why-alpha", "--tiers", "fast", "--out", out])

    def test_an_unconfigured_export_leaves_the_lane_byte_for_byte_identical(self):
        # The lane APPENDS its verdict rows, so each run gets its own file.
        # The first run has NO exporter; the second has one. If the hook
        # changed what the lane writes, the two files would differ.
        with_export = os.path.join(self.tmp, "verdicts-on.jsonl")
        self.assertEqual(self._run_lane(self.out), 0)
        exporter = StubExporter()
        spans.set_exporter(exporter)
        self.assertEqual(self._run_lane(with_export), 0)
        with open(self.out, encoding="utf-8") as fh:
            without = fh.read()
        with open(with_export, encoding="utf-8") as fh:
            with_span = fh.read()
        self.assertNotEqual(without, "")
        self.assertEqual(without, with_span, "the hook must not change what the lane writes")
        # Not vacuous: the second run really did have an exporter, and the
        # hook really did record into it.
        self.assertEqual(exporter.count, 1, "with an exporter configured, the lane recorded a span")

    def test_the_lane_span_carries_the_item_the_aspect_and_the_verdict(self):
        exporter = StubExporter()
        spans.set_exporter(exporter)
        self.assertEqual(self._run_lane(self.out), 0)
        self.assertEqual(exporter.count, 1)
        attributes = exporter.attributes()
        self.assertEqual(attributes["why.item_id"], "why-alpha")
        self.assertEqual(attributes["why.aspect"], "outcome")
        self.assertEqual(attributes["why.verdict"], "CONFLICTED")
        self.assertEqual(attributes["why.lane"], "review")
        self.assertEqual(attributes["why.tier"], "fast")
        self.assertEqual(attributes["gen_ai.system"], "Nebius Token Factory")
        self.assertIn("Nemotron", attributes["gen_ai.request.model"])

    def test_the_deterministic_verdict_is_the_same_either_way(self):
        items = ev.load_items(FIXTURE)
        claims = ev.load_evidence(FIXTURE)
        before = ev.explain(items, claims, "why-alpha").confidence()
        self._run_lane(self.out)
        after = ev.explain(items, claims, "why-alpha").confidence()
        self.assertEqual(before, after)


class NarrationHookTests(unittest.TestCase):
    """The narration lane records its own span, with the checker's outcome."""

    def setUp(self):
        spans.reset()
        self.addCleanup(spans.reset)
        self.exporter = StubExporter()
        spans.set_exporter(self.exporter)

    def _narrate(self, text):
        items = ev.load_items(FIXTURE)
        claims = ev.load_evidence(FIXTURE)
        result = ev.reconcile(items["why-alpha"], claims)
        with mock.patch.object(narrate, "call_openai_compatible", return_value=text):
            return narrate.narrate(result)

    def test_a_failed_check_is_recorded_as_failed_and_the_text_is_not(self):
        self._narrate("The amount was 999999 dollars.")
        self.assertEqual(self.exporter.count, 1)
        attributes = self.exporter.attributes()
        self.assertEqual(attributes["why.verdict"], "FAILED")
        self.assertEqual(attributes["why.lane"], "narration")
        self.assertEqual(attributes["why.aspect"], "outcome")
        self.assertEqual(attributes["why.item_id"], "why-alpha")
        blob = json.dumps(self.exporter.payloads[0])
        self.assertNotIn("999999", blob, "the narration TEXT is content, and must not be in a span")


class DocumentationTests(unittest.TestCase):
    """The doc says what the code does, and no more than that."""

    #: Observability platforms the doc must not claim. The card says the doc
    #: says "emits OTLP" and nothing more.
    PLATFORMS = (
        "langfuse",
        "phoenix",
        "datadog",
        "grafana",
        "honeycomb",
        "signoz",
        "newrelic",
        "dynatrace",
        "splunk",
    )

    def _section(self):
        """The BODY of the spans section — everything after its heading line.

        The heading is excluded on purpose. A heading that repeats a phrase
        the body also uses would let a body check pass for the wrong reason.
        """
        text = (HERE / "INTEGRATION.md").read_text(encoding="utf-8")
        start = text.index("## GenAI spans")
        rest = text[start + 1 :]
        end = rest.find("\n## ")
        section = rest if end == -1 else rest[:end]
        lines = section.splitlines()
        return "\n".join(lines[1:]) if lines else ""

    def _heading(self):
        text = (HERE / "INTEGRATION.md").read_text(encoding="utf-8")
        return text[text.index("## GenAI spans") :].splitlines()[0]

    def test_the_doc_states_the_version_the_code_pins(self):
        # The exact sentence, not just the number: the version also appears
        # in the attribute table, so a bare "1.41.0" check would pass even if
        # the sentence naming the followed version were changed.
        self.assertIn(f"version `{spans.CONVENTIONS_VERSION}`", self._section())

    def test_the_doc_names_no_other_conventions_version(self):
        # The one other version the doc may name is the one it moved at.
        section = self._section()
        self.assertIn("v1.42.0", section)
        self.assertNotIn("version `1.40.0`", section)
        self.assertNotIn("version `1.42.0`", section)

    def test_the_doc_says_it_emits_otlp(self):
        self.assertIn("emits OTLP", self._section())

    def test_the_doc_claims_no_observability_platform(self):
        section = self._section().lower()
        for banned in self.PLATFORMS:
            self.assertNotIn(banned, section, f"the doc must not claim a platform ({banned})")

    def test_the_heading_claims_no_observability_platform(self):
        heading = self._heading().lower()
        for banned in self.PLATFORMS:
            self.assertNotIn(banned, heading, f"the heading must not claim a platform ({banned})")

    def test_the_doc_says_why_content_is_off_by_default(self):
        section = self._section().lower()
        self.assertIn("content", section)
        self.assertIn("off by default", section)


if __name__ == "__main__":
    unittest.main()
