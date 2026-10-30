"""Tests for providers.py — the profiles, and the second one that proves they are
provider-general.

    python3 -m unittest test_providers -v

Offline: a fake environ, no network, no key. The point of the second profile
is that a profile is CONFIGURATION, not surgery: the same shape resolves for
any OpenAI-compatible endpoint. So the tests check the SHAPE, the citations,
and that the nebius profile did not move.
"""
import importlib.util
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

spec = importlib.util.spec_from_file_location("providers", HERE / "providers.py")
providers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(providers)


class NebiusProfileTests(unittest.TestCase):
    """The regression test: the nebius profile resolves exactly as it did."""

    def test_the_nebius_profile_resolves_byte_identically_to_before(self):
        resolved = providers.resolve("nebius", {"NEBIUS_API_KEY": "test-key"})
        self.assertEqual(resolved, {
            "label": "Nebius Token Factory",
            "base_url": "https://api.tokenfactory.nebius.com/v1/",
            "api_key": "test-key",
            "models": {
                "fast": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
                "standard": "nvidia/nemotron-3-super-120b-a12b",
                "deep": "nvidia/Nemotron-3-Ultra-550b-a55b",
                "vision": "nvidia/Nemotron-3.5-Super-VL",
            },
        })

    def test_the_nebius_profile_itself_did_not_change(self):
        self.assertEqual(providers.PROFILES["nebius"]["base_url"],
                         "https://api.tokenfactory.nebius.com/v1/")
        self.assertEqual(providers.PROFILES["nebius"]["key_env"], "NEBIUS_API_KEY")


class MinimaxGatewayProfileTests(unittest.TestCase):
    """The second profile: MiniMax through the Vercel AI Gateway."""

    def test_it_resolves_with_the_same_shape_as_the_nebius_one(self):
        resolved = providers.resolve("minimax-gateway",
                                     {"AI_GATEWAY_API_KEY": "test-key"})
        self.assertEqual(resolved["label"], "MiniMax via Vercel AI Gateway")
        self.assertEqual(resolved["base_url"], "https://ai-gateway.vercel.sh/v1")
        self.assertEqual(resolved["api_key"], "test-key")
        self.assertEqual(sorted(resolved["models"]), ["deep", "fast", "standard"])
        for tier, model in resolved["models"].items():
            self.assertTrue(model.startswith("minimax/"),
                            f"{tier} is not a gateway model id: {model}")

    def test_the_base_url_comes_from_the_gateways_own_docs(self):
        # The OpenAI-compatible surface the gateway documents, not a guess.
        self.assertEqual(providers.PROFILES["minimax-gateway"]["base_url"],
                         "https://ai-gateway.vercel.sh/v1")
        self.assertEqual(providers.PROFILES["minimax-gateway"]["key_env"],
                         "AI_GATEWAY_API_KEY")

    def test_every_tier_can_be_overridden_from_the_environment(self):
        env = {"AI_GATEWAY_API_KEY": "test-key",
               "WHY_AGENT_MINIMAX-GATEWAY_FAST_MODEL": "minimax/minimax-m2",
               "WHY_AGENT_MINIMAX-GATEWAY_DEEP_MODEL": "minimax/minimax-m2.7"}
        resolved = providers.resolve("minimax-gateway", env)
        self.assertEqual(resolved["models"]["fast"], "minimax/minimax-m2")
        self.assertEqual(resolved["models"]["deep"], "minimax/minimax-m2.7")
        self.assertEqual(resolved["models"]["standard"],
                         providers.PROFILES["minimax-gateway"]["models"]["standard"])

    def test_the_profile_cites_the_gateways_docs_and_the_pricing_date(self):
        source = (HERE / "providers.py").read_text(encoding="utf-8")
        block = source.split('"minimax-gateway": {', 1)[1]
        self.assertIn("vercel.com/docs/ai-gateway", block,
                      "the profile must cite the gateway's own documentation")
        self.assertIn("vercel.com/ai-gateway/models", block,
                      "the model ids must cite the gateway's model page")
        self.assertIn("2026-10-22", block,
                      "the free period's end date must be in the comment, dated")
        self.assertIn("STANDARD RATES", block,
                      "the comment must say that a pinned run bills at standard rates")
        self.assertIn("order", block, "the comment must name the pinning mechanism")

    def test_no_key_is_stored_in_the_repo(self):
        # The profile names the VARIABLE that holds the key; it never holds one.
        for name, profile in providers.PROFILES.items():
            for key, value in profile.items():
                self.assertNotIn("sk-", str(value),
                                 f"profile {name}.{key} looks like it holds a key")
                self.assertNotIn("api_key", key)

    def test_a_missing_key_names_the_variable_instead_of_saying_unreachable(self):
        with self.assertRaises(providers.ProviderError) as caught:
            providers.resolve("minimax-gateway", {})
        self.assertIn("AI_GATEWAY_API_KEY", str(caught.exception))
        self.assertNotIn("unreachable", str(caught.exception))

    def test_an_unknown_profile_lists_the_known_ones(self):
        with self.assertRaises(providers.ProviderError) as caught:
            providers.resolve("no-such-provider", {"AI_GATEWAY_API_KEY": "k"})
        message = str(caught.exception)
        self.assertIn("nebius", message)
        self.assertIn("minimax-gateway", message)


class ProfileGeneralTests(unittest.TestCase):
    """A profile is configuration, not surgery: every profile behaves the same."""

    def test_every_profile_has_the_same_shape(self):
        for name, profile in providers.PROFILES.items():
            self.assertEqual(sorted(profile), ["base_url", "key_env", "label", "models"],
                             f"profile {name} has a different shape")
            self.assertTrue(profile["base_url"].startswith("https://"))
            self.assertTrue(profile["key_env"].isupper())
            for tier, model in profile["models"].items():
                self.assertIn("/", model, f"{name}/{tier} is not a provider/model id")

    def test_every_profile_resolves_with_a_fake_key(self):
        for name, profile in providers.PROFILES.items():
            env = {profile["key_env"]: "test-key"}
            resolved = providers.resolve(name, env)
            self.assertEqual(resolved["api_key"], "test-key")
            self.assertEqual(sorted(resolved["models"]), sorted(profile["models"]))


if __name__ == "__main__":
    unittest.main()
