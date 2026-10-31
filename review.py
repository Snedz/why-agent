"""Reviewer lanes: ask tiered models for a verdict, keep it as evidence.

In the kitchen, model reviewers never decide anything — they make CLAIMS,
and the deterministic reconciler decides. This module is that rule as
code: for one item, each configured model tier is shown the same claims
and asked for one verdict word plus one sentence of reason. Whatever it
answers is appended to the evidence file as a `verdict` row, cited to the
model that said it, where why-agent reconciles it against every other
source — disagreements included, never averaged away.

Token usage is read from the API response and priced from a snapshot
table, because a routed lane that cannot say what it cost is a lane
nobody can reason about. Prices are a dated catalogue snapshot, not a
bill; override per tier with WHY_AGENT_PRICE_<TIER>_IN / _OUT (USD per
million tokens) when the provider's page disagrees.

Usage:
  NEBIUS_API_KEY=... python review.py --provider nebius \
      --evidence evidence/items.jsonl --item why-alpha \
      --tiers fast,deep --out evidence/review-verdicts.jsonl
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

import spans
from typing import Mapping

import providers

VERDICTS = ("CORROBORATED", "PARTIAL", "CONFLICTED", "NO EVIDENCE")

# USD per 1M tokens (input, output) — catalogue snapshot, 2026-10-28.
PRICE_SNAPSHOT = {
    "fast": (0.06, 0.24),
    "standard": (0.30, 0.90),
    "deep": (1.00, 3.00),
}

PROMPT = """You are one reviewer lane. Below are the claims made about one item, grouped as they were recorded. Judge ONLY from these claims.

Answer in exactly this shape, nothing else:
VERDICT: <one of CORROBORATED, PARTIAL, CONFLICTED, NO EVIDENCE> — <one sentence reason>

Rules: agreement across sources on every aspect is CORROBORATED. Any direct disagreement is CONFLICTED. Missing aspects with no disagreement is PARTIAL. No claims at all is NO EVIDENCE.

Item: {title} ({item_id})
Claims:
{claims}
"""


def _load_rows(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                rows.append(json.loads(line))
    return rows


def _chat(base_url: str, api_key: str, model: str, prompt: str,
          timeout: int = 180) -> tuple[str, dict]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        # Reasoning models spend tokens thinking before they answer;
        # a small cap reads as an empty reply, not as a cheap one.
        "max_tokens": 4096,
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
        body = json.loads(resp.read().decode("utf-8"))
    text = body["choices"][0]["message"].get("content") or ""
    return text.strip(), body.get("usage") or {}


def _parse_verdict(text: str) -> tuple[str, str]:
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("VERDICT:"):
            rest = line.split(":", 1)[1].strip()
            for verdict in VERDICTS:
                if rest.upper().startswith(verdict):
                    reason = rest[len(verdict):].lstrip("—-: ").strip()
                    return verdict, reason or "(no reason given)"
            return "UNPARSEABLE", rest[:200]
    return "UNPARSEABLE", text[:200]


def _price(tier: str, environ: Mapping[str, str]) -> tuple[float, float]:
    pin = environ.get(f"WHY_AGENT_PRICE_{tier.upper()}_IN")
    pout = environ.get(f"WHY_AGENT_PRICE_{tier.upper()}_OUT")
    default = PRICE_SNAPSHOT.get(tier, (0.0, 0.0))
    return (
        float(pin) if pin else default[0],
        float(pout) if pout else default[1],
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--provider", default="nebius")
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--item", required=True)
    ap.add_argument("--tiers", default="fast,deep",
                    help="comma-separated tiers to run (default: fast,deep)")
    ap.add_argument("--out", required=True,
                    help="JSONL file to APPEND verdict rows to")
    args = ap.parse_args(argv)

    try:
        prof = providers.resolve(args.provider)
    except providers.ProviderError as exc:
        print(f"FAIL resolve: {exc}", file=sys.stderr)
        return 2

    rows = _load_rows(args.evidence)
    mine = [r for r in rows if r.get("item_id") == args.item]
    if not mine:
        print(f"no claims found for item {args.item!r}", file=sys.stderr)
        return 1
    title = next((r.get("title") for r in mine if r.get("title")), args.item)
    claims_text = "\n".join(
        f"- [{r.get('kind')}/{r.get('aspect') or 'state'}] {r.get('source')}: "
        f"{r.get('statement')} (value: {r.get('value')})"
        for r in mine
    )
    prompt = PROMPT.format(title=title, item_id=args.item, claims=claims_text)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    total_cost = 0.0
    with open(args.out, "a", encoding="utf-8") as out:
        for tier in [t.strip() for t in args.tiers.split(",") if t.strip()]:
            model = prof["models"][tier]
            started = time.time()
            try:
                text, usage = _chat(prof["base_url"], prof["api_key"], model, prompt)
            except (urllib.error.HTTPError, urllib.error.URLError, OSError,
                    KeyError, IndexError) as exc:
                print(f"FAIL {tier} ({model}): {exc}", file=sys.stderr)
                return 1
            verdict, reason = _parse_verdict(text)
            pin, pout = _price(tier, os.environ)
            cost = (usage.get("prompt_tokens", 0) * pin
                    + usage.get("completion_tokens", 0) * pout) / 1_000_000
            # The span carries the FACTS of the call. Its content is dropped
            # unless content capture was explicitly enabled.
            spans.record(lane="review", model=model, provider=prof["label"],
                         tier=tier, item_id=args.item, aspect="outcome",
                         latency_ms=(time.time() - started) * 1000.0,
                         input_tokens=usage.get("prompt_tokens", 0),
                         output_tokens=usage.get("completion_tokens", 0),
                         cost_usd=cost, verdict=verdict, retry_count=0,
                         prompt=prompt, completion=text)
            row = {
                "item_id": args.item,
                "kind": "verdict",
                "source": f"nemotron-{tier}",
                "locator": model,
                "statement": reason,
                "value": verdict,
                "observed_at": now,
                "aspect": "outcome",
            }
            out.write(json.dumps(row) + "\n")
            total_cost += cost
            print(f"{tier:8s} {model}: {verdict} — {reason} "
                  f"[{usage.get('prompt_tokens')}/{usage.get('completion_tokens')} tok, ~${cost:.4f}]")
    print(f"verdict rows appended to {args.out}; total est. cost ${total_cost:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
