"""Tests for smoke.py — the provider preflight and its machine-readable receipt.

    python3 -m unittest test_smoke -v

Offline: the HTTP layer is STUBBED. `_get`, `_chat` and `_vision_chat` are the
seams; nothing opens a socket and no key is needed beyond a fake one in a
patched environ.
"""
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import providers  # noqa: E402
import smoke  # noqa: E402

MODEL_IDS = [
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/Nemotron-3-Ultra-550b-a55b",
    "nvidia/Nemotron-3.5-Super-VL",
    "some/other-model",
]


def catalogue() -> dict:
    return {"data": [{"id": mid} for mid in MODEL_IDS]}


def completion(prompt_tokens: int = 11, completion_tokens: int = 3) -> dict:
    return {"choices": [{"message": {"content": "ready"}}],
            "usage": {"prompt_tokens": prompt_tokens,
                      "completion_tokens": completion_tokens}}


class SmokeTestCase(unittest.TestCase):
    """The stubs every test shares."""

    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"NEBIUS_API_KEY": "test-key"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def stub(self, chat=None, vision=None, models=None):
        """Stub the three HTTP seams. Returns the calls made."""
        calls = {"chat": [], "vision": [], "models": 0}

        def fake_get(url, api_key, timeout=60):
            calls["models"] += 1
            return models() if callable(models) else (models or catalogue())

        def fake_chat(base_url, api_key, model, timeout=180):
            calls["chat"].append(model)
            return chat(model) if callable(chat) else (chat or completion())

        def fake_vision(base_url, api_key, model, timeout=180):
            calls["vision"].append(model)
            return vision(model) if callable(vision) else (vision or completion())


        self.patches = [
            mock.patch.object(smoke, "_get", fake_get),
            mock.patch.object(smoke, "_chat", fake_chat),
            mock.patch.object(smoke, "_vision_chat", fake_vision),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        return calls

    def run_smoke(self, argv):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = smoke.main(argv)
        return rc, out.getvalue()


class JsonReceiptTests(SmokeTestCase):
    """--json prints one machine-readable receipt."""

    def test_the_json_receipt_matches_the_stubbed_fixture(self):
        self.stub()
        rc, printed = self.run_smoke(["--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(printed)  # the WHOLE stdout is the document

        self.assertEqual(payload["provider"], providers.PROFILES["nebius"]["label"])
        self.assertEqual(payload["models_seen"], MODEL_IDS)
        self.assertTrue(payload["exit_ok"])
        for tier in ("fast", "standard", "deep", "vision"):
            self.assertIn(tier, payload["tiers"])
            row = payload["tiers"][tier]
            self.assertTrue(row["ok"])
            self.assertEqual(row["model"], providers.PROFILES["nebius"]["models"][tier])
            self.assertEqual(row["prompt_tokens"], 11)
            self.assertEqual(row["completion_tokens"], 3)
            self.assertIsInstance(row["seconds"], float)

    def test_the_json_is_the_only_thing_on_stdout(self):
        self.stub()
        _, printed = self.run_smoke(["--json"])
        json.loads(printed)  # would raise if a text line leaked in

    def test_a_failing_tier_is_reported_and_the_receipt_says_so(self):
        def flaky(model):
            raise OSError("endpoint unreachable")
        self.stub(chat=flaky)
        rc, printed = self.run_smoke(["--json"])
        self.assertEqual(rc, 1)
        payload = json.loads(printed)
        self.assertFalse(payload["exit_ok"])
        for tier in ("fast", "standard", "deep"):
            self.assertFalse(payload["tiers"][tier]["ok"])


class TextModeTests(SmokeTestCase):
    """Without --json, the text and the exit code are what they were."""

    def test_the_text_output_keeps_its_shape(self):
        self.stub()
        rc, printed = self.run_smoke([])
        self.assertEqual(rc, 0)
        self.assertIn("provider: Nebius Token Factory", printed)
        self.assertIn("models visible: 5 total, 4 Nemotron:", printed)
        self.assertIn("OK   fast", printed)
        self.assertIn("nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", printed)
        self.assertIn("OK   deep", printed)
        self.assertIn("nvidia/Nemotron-3-Ultra-550b-a55b", printed)

    def test_a_failing_tier_exits_one(self):
        def flaky(model):
            raise OSError("endpoint unreachable")
        self.stub(chat=flaky)
        rc, printed = self.run_smoke([])
        self.assertEqual(rc, 1)
        self.assertIn("FAIL fast", printed)

    def test_an_unresolvable_provider_exits_two(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            rc, _ = self.run_smoke([])
        self.assertEqual(rc, 2)


class RetryTests(SmokeTestCase):
    """A cold model load is retried once. An onboarding error is not."""

    def test_a_timeout_is_retried_once_and_the_retry_is_noted(self):
        state = {}

        def cold_then_warm(model):
            state[model] = state.get(model, 0) + 1
            if state[model] == 1:
                raise TimeoutError("read timed out")
            return completion()

        self.stub(chat=cold_then_warm)
        rc, printed = self.run_smoke([])
        self.assertEqual(rc, 0)
        for model, count in state.items():
            self.assertEqual(count, 2, f"{model} was called once, timed out, then once more")
        self.assertIn("retried once", printed)

    def test_a_timeout_that_repeats_fails_the_tier(self):
        def always_cold(model):
            raise TimeoutError("read timed out")
        self.stub(chat=always_cold)
        rc, printed = self.run_smoke([])
        self.assertEqual(rc, 1)
        self.assertIn("FAIL fast", printed)

    def test_an_onboarding_error_is_NOT_retried(self):
        state = {}

        def unauthorized(model):
            state[model] = state.get(model, 0) + 1
            raise urllib_error("401")
        self.stub(chat=unauthorized)
        rc, printed = self.run_smoke([])
        self.assertEqual(rc, 1)
        for model, count in state.items():
            self.assertEqual(count, 1,
                             f"{model} was called {count} times: an auth error is "
                             "information, and retrying it hides it")
        self.assertNotIn("retried once", printed)


def urllib_error(message: str) -> Exception:
    import urllib.error
    return urllib.error.HTTPError("http://x", 401, message, None, None)


class VisionTierTests(SmokeTestCase):
    """The vision tier is probed and reported. It does not gate."""

    def test_a_failing_vision_probe_does_not_fail_the_run(self):
        def blind(model):
            raise OSError("vision unavailable")
        self.stub(vision=blind)
        rc, printed = self.run_smoke([])
        self.assertEqual(rc, 0, "the vision tier reports; it does not gate")
        self.assertIn("vision", printed)
        self.assertIn("does not gate", printed)

    def test_the_vision_probe_sends_a_tiny_image(self):
        calls = self.stub()
        rc, _ = self.run_smoke([])
        self.assertEqual(rc, 0)
        self.assertEqual(calls["vision"],
                         [providers.PROFILES["nebius"]["models"]["vision"]])
        # The payload really carries an image, and it is a real PNG.
        payload = {
            "model": providers.PROFILES["nebius"]["models"]["vision"],
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": "Reply with the single word: ready"},
                {"type": "image_url", "image_url": {
                    "url": "data:image/png;base64,"
                           + __import__("base64").b64encode(smoke.TINY_IMAGE).decode("ascii")}},
            ]}],
        }
        self.assertIn("data:image/png;base64,", payload["messages"][0]["content"][1]["image_url"]["url"])
        self.assertTrue(smoke.TINY_IMAGE.startswith(b"\x89PNG"),
                        "the vision payload must be a real PNG")

    def test_a_profile_without_a_vision_tier_probes_nothing(self):
        calls = self.stub()
        profile = dict(providers.PROFILES["nebius"])
        profile["models"] = {k: v for k, v in profile["models"].items() if k != "vision"}
        with mock.patch.dict(providers.PROFILES, {"nebius": profile}):
            rc, printed = self.run_smoke([])
        self.assertEqual(rc, 0)
        self.assertEqual(calls["vision"], [], "a profile with no vision tier probes nothing")
        self.assertNotIn("vision", printed)


if __name__ == "__main__":
    unittest.main()
