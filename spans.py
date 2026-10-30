"""spans.py — an opt-in GenAI span hook. No dependency, no disk, no content.

**Disabled by default.** With the environment switch unset, `record()` returns
immediately and every caller behaves exactly as it did before — that is what
makes it safe to leave the calls in the lanes.

A span carries the **facts** of a model call and never its **content**: the
model, the provider, the tier, the latency, the token counts, the cost, the
verdict, the retry count. It carries **no prompt text and no claim content**,
because a span is the kind of artefact that ends up in a log somebody else can
read, and because the evidence in this repo is exactly the thing that must not
leak sideways. `record()`'s signature admits no free-form fields, so content
cannot be recorded even by accident.

Enabled with `WHY_AGENT_SPANS=1`. The spans are kept **in memory**; nothing is
written to disk and nothing is sent anywhere. Hosting a collector and sending
the spans are both out of scope for now — the mechanism exists so that the day
somebody wants them, nothing has to be rewritten.

The attribute names follow the OpenTelemetry GenAI conventions where a name
exists (`gen_ai.request.model`, `gen_ai.usage.input_tokens`) and stay in the
same namespace where one does not (`gen_ai.tier`, `gen_ai.cost_usd`).
"""
from __future__ import annotations

import os
from typing import Any

#: The switch. Set it to any non-empty value to record spans.
SPAN_ENV = "WHY_AGENT_SPANS"

_SPANS: list[dict[str, Any]] = []


def enabled(environ: Any = None) -> bool:
    """Is the hook switched on? Off unless the environment says otherwise."""
    env = os.environ if environ is None else environ
    return bool((env.get(SPAN_ENV) or "").strip())


def record(*, operation: str, model: str, provider: str, tier: str,
           latency_ms: float = 0.0, input_tokens: int = 0,
           output_tokens: int = 0, cost_usd: float = 0.0, verdict: str = "",
           retry_count: int = 0) -> dict[str, Any] | None:
    """Record one span. Returns it, or None when the hook is switched off.

    There is no **kwargs on purpose: the only things a caller can record are
    the facts, so a prompt or a claim cannot be recorded by accident.
    """
    if not enabled():
        return None
    span = {
        "name": operation,
        "attributes": {
            "gen_ai.operation.name": operation,
            "gen_ai.request.model": model,
            "gen_ai.system": provider,
            "gen_ai.tier": tier,
            "gen_ai.usage.input_tokens": int(input_tokens),
            "gen_ai.usage.output_tokens": int(output_tokens),
            "gen_ai.cost_usd": round(float(cost_usd), 6),
            "gen_ai.response.verdict": verdict,
            "gen_ai.retry_count": int(retry_count),
            "gen_ai.response.latency_ms": round(float(latency_ms), 3),
        },
    }
    _SPANS.append(span)
    return span


def recorded() -> list[dict[str, Any]]:
    """The spans recorded so far, in order."""
    return list(_SPANS)


def clear() -> None:
    """Forget the recorded spans. For tests, and for a long-lived process."""
    _SPANS.clear()
