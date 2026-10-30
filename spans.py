"""spans.py — an opt-in OTLP span hook for the lane calls.

What it is
----------
One span per model call, shaped like an OTLP export request, carrying the
**facts** of the call. The GenAI attribute names follow the OpenTelemetry
GenAI semantic conventions, pinned to the version named in
``CONVENTIONS_VERSION``. This repository's own facts live in the ``why.``
namespace, which is ours to extend and theirs to leave alone.

What it is not
--------------
It is not a platform, a dashboard, a collector or a backend. It emits OTLP
and nothing more. Whatever receives the payload is the operator's business.

Two gates, both closed by default
----------------------------------
1. **No exporter, no span.** ``record()`` is a complete no-op until an
   exporter is installed, so the lanes can call it unconditionally and write
   exactly the bytes they wrote before.
2. **No content, unless it is asked for separately.** Prompt and completion
   text is never captured by default. The claims in this repository are the
   product's evidence; they leave this machine only by explicit
   configuration, so the switch that captures content is *separate* from the
   switch that collects facts.

Content capture exists because an operator may genuinely want to read a
narration that failed its check. It is off by default because a span is the
kind of artefact that ends up in a log somebody else can read.
"""

from __future__ import annotations

import importlib
import os
import secrets
import sys
import time
from typing import Any, Callable, Mapping

#: The OpenTelemetry GenAI semantic conventions this module follows.
#:
#: v1.41.0 is the last released version of `open-telemetry/semantic-conventions`
#: that still published the GenAI conventions in-tree. From v1.42.0 the page
#: says "Moved", and the conventions now live in
#: `open-telemetry/semantic-conventions-genai`, which has no release yet.
#: Pinning to a released version is therefore the most honest choice, and the
#: move is recorded below rather than papered over.
CONVENTIONS_VERSION = "1.41.0"
CONVENTIONS_SOURCE = "https://github.com/open-telemetry/semantic-conventions/blob/v1.41.0/docs/gen-ai/gen-ai-spans.md"
CONVENTIONS_MOVED_TO = "https://github.com/open-telemetry/semantic-conventions-genai"

#: The explicit opt-in for content capture. Unset, empty or blank means off.
CONTENT_ENV = "WHY_AGENT_SPAN_CONTENT"

#: The explicit opt-in for export, as `module.path:callable`. With it unset
#: and no exporter installed, `record()` is a no-op.
EXPORTER_ENV = "WHY_AGENT_SPAN_EXPORTER"

#: The OTel well-known value for a chat completion. Every lane here chats.
OPERATION_CHAT = "chat"

#: OTel span kind 3 = CLIENT. These spans describe an outbound model call.
SPAN_KIND_CLIENT = 3

#: OTel status code 1 = OK. A completed call is OK; the *verdict* is an
#: attribute, not a span status.
STATUS_OK = 1

Exporter = Callable[[Mapping[str, Any]], None]

_EXPORTER: Exporter | None = None
_CONTENT: bool | None = None
_ENV_TRIED = False


def set_exporter(exporter: Exporter | None) -> None:
    """Install (or remove) the exporter. The export is the explicit
    configuration; with none installed, `record()` does nothing at all."""
    global _EXPORTER
    _EXPORTER = exporter


def exporter() -> Exporter | None:
    """The installed exporter, or None."""
    return _EXPORTER


def set_content_capture(enabled: bool | None) -> None:
    """Turn content capture on or off. `None` hands the decision back to the
    environment variable, which is off unless it is set."""
    global _CONTENT
    _CONTENT = None if enabled is None else bool(enabled)


def content_capture_enabled(environ: Any = None) -> bool:
    """Is prompt/completion content captured? Off unless explicitly asked."""
    env = os.environ if environ is None else environ
    if _CONTENT is not None:
        return _CONTENT
    return bool((env.get(CONTENT_ENV) or "").strip())


def reset() -> None:
    """Forget the exporter and the content policy. Tests use this."""
    global _EXPORTER, _CONTENT, _ENV_TRIED
    _EXPORTER = None
    _CONTENT = None
    _ENV_TRIED = False


def _env_exporter() -> Exporter | None:
    """The exporter named by the environment, if any. Loaded once per process."""
    global _EXPORTER, _ENV_TRIED
    if _ENV_TRIED:
        return _EXPORTER
    _ENV_TRIED = True
    spec = (os.environ.get(EXPORTER_ENV) or "").strip()
    if not spec:
        return None
    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        print(f"warning: {EXPORTER_ENV}={spec!r} is not 'module.path:callable'; spans stay off", file=sys.stderr)
        return None
    try:
        module = importlib.import_module(module_name)
        found = getattr(module, attr)
    except (ImportError, AttributeError) as exc:
        print(f"warning: {EXPORTER_ENV}={spec!r} could not be loaded ({exc}); spans stay off", file=sys.stderr)
        return None
    if not callable(found):
        print(f"warning: {EXPORTER_ENV}={spec!r} is not callable; spans stay off", file=sys.stderr)
        return None
    _EXPORTER = found
    return _EXPORTER


def _any_value(value: Any) -> dict[str, Any]:
    """Encode a Python value as an OTLP AnyValue."""
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, Mapping):
        return {"kvlistValue": {"values": [{"key": str(k), "value": _any_value(v)} for k, v in value.items()]}}
    if isinstance(value, (list, tuple)):
        return {"arrayValue": {"values": [_any_value(v) for v in value]}}
    return {"stringValue": str(value)}


def _attributes(facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The attribute list, in OTLP's key/value form."""
    return [{"key": str(k), "value": _any_value(v)} for k, v in facts.items()]


def _input_messages(prompt: Any) -> list[dict[str, Any]] | None:
    """Normalise a prompt into the GenAI input-message shape."""
    if prompt is None:
        return None
    if isinstance(prompt, str):
        return [{"role": "user", "parts": [{"type": "text", "content": prompt}]}]
    out = []
    for message in prompt:
        content = message.get("content", "")
        parts = [{"type": "text", "content": content}] if isinstance(content, str) else list(content)
        out.append({"role": message.get("role", "user"), "parts": parts})
    return out


def _output_messages(completion: Any) -> list[dict[str, Any]] | None:
    """Normalise a completion into the GenAI output-message shape."""
    if completion is None:
        return None
    if isinstance(completion, str):
        return [{"role": "assistant", "parts": [{"type": "text", "content": completion}], "finish_reason": "stop"}]
    return list(completion)


def record(
    *,
    lane: str,
    model: str,
    provider: str,
    tier: str,
    item_id: str = "",
    aspect: str = "",
    verdict: str = "",
    latency_ms: float = 0.0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0.0,
    retry_count: int = 0,
    prompt: Any = None,
    completion: Any = None,
) -> dict[str, Any] | None:
    """Record one span. Returns the OTLP payload, or None when export is not
    configured.

    With no exporter this returns None before doing any work at all, so a
    lane that calls it writes exactly the bytes it wrote before the hook
    existed.

    `prompt` and `completion` are accepted but **dropped** unless content
    capture has been explicitly enabled. A span carries the facts of a call;
    the content of a call is a different decision, made separately.
    """
    target = _EXPORTER if _EXPORTER is not None else _env_exporter()
    if target is None:
        return None

    facts: dict[str, Any] = {
        # --- the OpenTelemetry GenAI conventions (v1.41.0) ---
        "gen_ai.operation.name": OPERATION_CHAT,
        "gen_ai.request.model": model,
        "gen_ai.provider.name": provider,
        # `gen_ai.system` is deprecated at v1.41.0 in favour of
        # `gen_ai.provider.name`. Both are emitted: the newer name for a
        # collector that knows it, the older one for a collector that does not.
        "gen_ai.system": provider,
        "gen_ai.usage.input_tokens": int(input_tokens),
        "gen_ai.usage.output_tokens": int(output_tokens),
        # --- this repository's own namespace ---
        "why.lane": lane,
        "why.item_id": item_id,
        "why.aspect": aspect,
        "why.verdict": verdict,
        "why.tier": tier,
        "why.cost_usd": round(float(cost_usd), 6),
        "why.retry_count": int(retry_count),
        "why.latency_ms": round(float(latency_ms), 3),
        "why.genai_conventions_version": CONVENTIONS_VERSION,
    }
    if content_capture_enabled():
        messages = _input_messages(prompt)
        if messages is not None:
            facts["gen_ai.input.messages"] = messages
        answer = _output_messages(completion)
        if answer is not None:
            facts["gen_ai.output.messages"] = answer

    end_ns = time.time_ns()
    start_ns = end_ns - int(round(float(latency_ms) * 1_000_000))
    span = {
        "traceId": secrets.token_hex(16),
        "spanId": secrets.token_hex(8),
        "name": f"{OPERATION_CHAT} {model}",
        "kind": SPAN_KIND_CLIENT,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": _attributes(facts),
        "status": {"code": STATUS_OK},
    }
    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "why-agent"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "why-agent"},
                        "spans": [span],
                    }
                ],
            }
        ],
    }
    target(payload)
    return payload
