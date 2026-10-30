"""Provider profiles: named OpenAI-compatible endpoints with tiered models.

why-agent's narration was written against one local runtime (Meterless).
Other runtimes speak the same chat-completions shape, so moving is a matter
of configuration, not surgery — but the configuration has to live somewhere
explicit, because "which endpoint, which model, which key" is exactly the
kind of fact that otherwise ends up scattered across shell history.

A profile names a base URL, the environment variable holding its API key,
and three model tiers. Tiers exist because the kitchen's rule is to route:
a fast small model for cheap everyday calls, a standard model for the
narration a person reads, and a deep reasoning model for the claims that
are actually contested. The caller picks a tier; the profile says what
that tier means on this provider.

Model IDs are defaults, not scripture. Providers rename models; every
tier can be overridden from the environment (WHY_AGENT_<PROFILE>_<TIER>_MODEL)
and `smoke.py` lists what the account can actually see before a run
depends on a spelling.
"""
from __future__ import annotations

import os
from typing import Mapping


class ProviderError(Exception):
    """A profile cannot be resolved (unknown name, missing key)."""


PROFILES: dict[str, dict] = {
    "nebius": {
        "label": "Nebius Token Factory",
        "base_url": "https://api.tokenfactory.nebius.com/v1/",
        "key_env": "NEBIUS_API_KEY",
        # NVIDIA Nemotron tiers on Token Factory. Spellings follow the
        # provider's catalogue as of 2026-10-28; pin them with smoke.py
        # (GET /v1/models) on the actual account before relying on them.
        "models": {
            "fast": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
            "standard": "nvidia/nemotron-3-super-120b-a12b",
            "deep": "nvidia/Nemotron-3-Ultra-550b-a55b",
            # Vision tier (receipt/screenshot evidence), pinned the same day:
            "vision": "nvidia/Nemotron-3.5-Super-VL",
        },
    },
    "minimax-gateway": {
        "label": "MiniMax via Vercel AI Gateway",
        # Base URL, key variable and model ids come from the GATEWAY'S OWN
        # DOCUMENTATION, read 2026-10-29 — never from memory:
        #   base URL  https://vercel.com/docs/ai-gateway  (the OpenAI-compatible
        #              /v1 handlers)
        #   key       https://vercel.com/docs/ai-gateway/sdks-and-apis/
        #              openai-chat-completions/advanced  (AI_GATEWAY_API_KEY)
        #   models    https://vercel.com/ai-gateway/models/providers/minimax
        # The three MiniMax models the gateway serves with a 1M-token context,
        # ordered by the throughput the gateway publishes, because a tier name
        # is about speed and depth:
        #   fast      minimax/minimax-m3.1-flash  0.3s 213tps $0.10/$0.50 per M
        #   standard  minimax/minimax-m3           0.9s 181tps $0.30/$1.20 per M
        #                                              (at ≤512k input; $0.60/$2.40 above)
        #   deep      minimax/minimax-m2.5         0.8s  84tps $0.30/$1.20 per M
        # PRICING, dated: the free MiniMax period on the gateway ENDED
        # 2026-10-22, so a pinned gateway run bills at STANDARD RATES
        # (https://vercel.com/changelog/minimax-m3-1-flash-now-available-on-ai-gateway-for-free).
        # PINNING, dated 2026-10-29: the gateway routes a model across every
        # provider that serves it — minimax/minimax-m3 is served by minimax,
        # fireworks AND nebius — so the provider is pinned with the gateway's
        # own routing options (providerOptions.gateway.order / only, by
        # provider slug), not by hoping. A model id is a default, not scripture:
        # every tier can be overridden with WHY_AGENT_MINIMAX-GATEWAY_<TIER>_MODEL
        # (the variable name carries the profile name, so this one has a hyphen
        # and is set with `env`, not a plain shell assignment).
        # ACCOUNT, dated 2026-10-19: the Vercel team is PAUSED (the Pro plan
        # expired) and every gateway key is rejected, so this profile RESOLVES
        # but a call will not authenticate until the account is reactivated
        # (OS/BRAIN/CHATS/2026-10-19.md). No live call was made.
        "base_url": "https://ai-gateway.vercel.sh/v1",
        "key_env": "AI_GATEWAY_API_KEY",
        "models": {
            "fast": "minimax/minimax-m3.1-flash",
            "standard": "minimax/minimax-m3",
            "deep": "minimax/minimax-m2.5",
        },
    },
}


def resolve(name: str, environ: Mapping[str, str] | None = None) -> dict:
    """Resolve a profile name to {label, base_url, api_key, models}.

    The API key comes from the environment only. A missing key is an
    error with the variable's name in it, because "endpoint unreachable"
    is a lie when the real problem is a key nobody exported.
    """
    env = os.environ if environ is None else environ
    profile = PROFILES.get(name)
    if profile is None:
        known = ", ".join(sorted(PROFILES)) or "(none)"
        raise ProviderError(f"unknown provider {name!r}; known: {known}")
    key_env = profile["key_env"]
    api_key = (env.get(key_env) or "").strip()
    if not api_key:
        raise ProviderError(
            f"provider {name!r} needs its API key in ${key_env} (not set)"
        )
    models = {}
    for tier, default in profile["models"].items():
        override = env.get(f"WHY_AGENT_{name.upper()}_{tier.upper()}_MODEL")
        models[tier] = (override or default).strip()
    return {
        "label": profile["label"],
        "base_url": profile["base_url"],
        "api_key": api_key,
        "models": models,
    }
