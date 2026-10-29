"""Smoke test for a provider profile: can this account actually call it?

Run this before any work depends on a provider. It answers, in order:

  1. Does the account's key list models at all? (auth + billing state)
  2. Which Nemotron model IDs does the account actually see? (pin these)
  3. Does one tiny chat completion succeed per configured tier?

Exit code 0 only if every tier answers. A failure here is information,
not an outage to retry through: provider onboarding problems (a missing
billing country, an unprovisioned account) look exactly like this and
are fixed with the provider, not with retries.

--json prints ONE json document on stdout and nothing else, so a machine can
read the receipt: {provider, models_seen, tiers: {tier: {model, ok, seconds,
prompt_tokens, completion_tokens}}, exit_ok}. The text mode is unchanged.

A TIMEOUT is retried once per tier: a cold model load is not a failure, and
the retry is noted in the output. Nothing else is retried -- an auth or
onboarding error is information, and retrying it hides it.

The vision tier, when the profile defines one, is probed with a tiny image
payload and REPORTED, but it does not gate the exit code: a reader who
depends on the vision tier must say so themselves.

Usage:  NEBIUS_API_KEY=... python smoke.py --provider nebius
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.request

import providers

# One 1x1 transparent PNG. The smallest payload that is still an image.
TINY_IMAGE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


def _get(url: str, api_key: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {api_key}"}, method="GET"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _chat(base_url: str, api_key: str, model: str, timeout: int = 180) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
        "max_tokens": 512,
        "temperature": 0,
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _vision_chat(base_url: str, api_key: str, model: str, timeout: int = 180) -> dict:
    """One tiny image through the model, to see the vision tier answer."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Reply with the single word: ready"},
            {"type": "image_url", "image_url": {
                "url": "data:image/png;base64,"
                       + base64.b64encode(TINY_IMAGE).decode("ascii")}},
        ]}],
        "max_tokens": 512,
        "temperature": 0,
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _probe(call, base: str, key: str, model: str) -> tuple[bool, float, int, int, str]:
    """Call one tier once, with ONE retry on a timeout.

    Returns (ok, seconds, prompt_tokens, completion_tokens, note).
    """
    note = ""
    for attempt in (1, 2):
        started = time.time()
        try:
            body = call(base, key, model)
        except TimeoutError:
            if attempt == 1:
                note = " (timeout, retried once: cold load)"
                continue
            return False, time.time() - started, 0, 0, " (timeout, retried once)"
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            return False, time.time() - started, 0, 0, f": {exc}"
        usage = body.get("usage") or {}
        return (True, time.time() - started,
                int(usage.get("prompt_tokens") or 0),
                int(usage.get("completion_tokens") or 0), note)
    return False, 0.0, 0, 0, " (timeout, retried once)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--provider", default="nebius")
    ap.add_argument("--json", action="store_true",
                    help="print one machine-readable json receipt on stdout")
    args = ap.parse_args(argv)
    as_json = args.json

    try:
        prof = providers.resolve(args.provider)
    except providers.ProviderError as exc:
        if as_json:
            print(json.dumps({"provider": args.provider, "models_seen": [], "tiers": {},
                              "exit_ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"FAIL resolve: {exc}", file=sys.stderr)
        return 2
    base = prof["base_url"]
    if not as_json:
        print(f"provider: {prof['label']}  base: {base}")

    try:
        catalogue = _get(base.rstrip("/") + "/models", prof["api_key"])
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        if as_json:
            print(json.dumps({"provider": prof["label"], "models_seen": [], "tiers": {},
                              "exit_ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"FAIL models list: {exc}", file=sys.stderr)
        return 1
    ids = [row.get("id", "") for row in catalogue.get("data", [])]
    nemotron = [i for i in ids if "nemotron" in i.lower()]
    if not as_json:
        print(f"models visible: {len(ids)} total, {len(nemotron)} Nemotron:")
        for mid in sorted(nemotron):
            print(f"  {mid}")

    ok = True
    tiers: dict[str, dict] = {}
    for tier in ("fast", "standard", "deep"):
        model = prof["models"][tier]
        mark = "" if model in ids else "  (NOT in /v1/models list)"
        good, secs, pin, pout, note = _probe(_chat, base, prof["api_key"], model)
        if not good:
            ok = False
        tiers[tier] = {"model": model, "ok": good, "seconds": round(secs, 3),
                       "prompt_tokens": pin, "completion_tokens": pout}
        if not as_json:
            if good:
                print(f"OK   {tier:8s} {model}  {secs:.1f}s  usage={pin}/{pout} tok{note}{mark}")
            else:
                print(f"FAIL {tier:8s} {model}{note}{mark}")

    # The vision tier is probed and REPORTED. It does not gate the exit code:
    # a reader who depends on it has to say so themselves.
    if "vision" in prof["models"]:
        model = prof["models"]["vision"]
        good, secs, pin, pout, note = _probe(_vision_chat, base, prof["api_key"], model)
        tiers["vision"] = {"model": model, "ok": good, "seconds": round(secs, 3),
                           "prompt_tokens": pin, "completion_tokens": pout}
        if not as_json:
            state = "OK  " if good else "FAIL"
            print(f"{state} vision  {model}  {secs:.1f}s  usage={pin}/{pout} tok{note}"
                  "  (reported, does not gate)")

    if as_json:
        print(json.dumps({"provider": prof["label"], "models_seen": ids, "tiers": tiers,
                          "exit_ok": ok}, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
