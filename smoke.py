"""Smoke test for a provider profile: can this account actually call it?

Run this before any work depends on a provider. It answers, in order:

  1. Does the account's key list models at all? (auth + billing state)
  2. Which Nemotron model IDs does the account actually see? (pin these)
  3. Does one tiny chat completion succeed per configured tier?

Exit code 0 only if every tier answers. A failure here is information,
not an outage to retry through: provider onboarding problems (a missing
billing country, an unprovisioned account) look exactly like this and
are fixed with the provider, not with retries.

Usage:  NEBIUS_API_KEY=... python smoke.py --provider nebius
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

import providers


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--provider", default="nebius")
    args = ap.parse_args(argv)

    try:
        prof = providers.resolve(args.provider)
    except providers.ProviderError as exc:
        print(f"FAIL resolve: {exc}", file=sys.stderr)
        return 2
    base = prof["base_url"]
    print(f"provider: {prof['label']}  base: {base}")

    try:
        catalogue = _get(base.rstrip("/") + "/models", prof["api_key"])
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        print(f"FAIL models list: {exc}", file=sys.stderr)
        return 1
    ids = [row.get("id", "") for row in catalogue.get("data", [])]
    nemotron = [i for i in ids if "nemotron" in i.lower()]
    print(f"models visible: {len(ids)} total, {len(nemotron)} Nemotron:")
    for mid in sorted(nemotron):
        print(f"  {mid}")

    ok = True
    for tier in ("fast", "standard", "deep"):
        model = prof["models"][tier]
        mark = "" if model in ids else "  (NOT in /v1/models list)"
        started = time.time()
        try:
            body = _chat(base, prof["api_key"], model)
            usage = body.get("usage") or {}
            secs = time.time() - started
            print(
                f"OK   {tier:8s} {model}  {secs:.1f}s  "
                f"usage={usage.get('prompt_tokens')}/{usage.get('completion_tokens')} tok{mark}"
            )
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            ok = False
            print(f"FAIL {tier:8s} {model}: {exc}{mark}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
