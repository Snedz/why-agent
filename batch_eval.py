"""Batch evaluation: run the lanes over every item and report what happened.

The demo proves the mechanism on one item. This harness produces the
numbers a judge (or an operator deciding whether to trust a lane) actually
needs: per item, the deterministic verdict, each reviewer tier's verdict,
whether the tiers agree with the reconciler and with each other, whether
the narration passed its own check, and what the whole run cost.

Two operational facts are baked in, because both were observed live on
2026-10-28: a cold model can stall for minutes on its first call, so every
call retries with backoff before it is allowed to fail; and a routed lane
that cannot stop itself is a liability, so a budget cap skips remaining
paid calls instead of discovering the bill afterwards.

The reviewer call reuses review.py's prompt and parser by import. That is
a deliberate coupling for a two-day build; the reconciler never imports
either module, so the kernel stays clean if the harness is deleted.

Usage:
  NEBIUS_API_KEY=... python batch_eval.py --provider nebius \
      --evidence evidence/items.jsonl --tiers fast,deep --narrate \
      --budget 0.25 --out eval-results.json
"""
from __future__ import annotations

import argparse
import json
import time
import os
import sys
import time
import urllib.error

import evidence as ev
import spans
import providers
import review
from narrate import narrate


def _with_retries(fn, attempts: int = 3, base_delay: float = 5.0):
    """Run fn, retrying transient failures. Returns (value, retries_used).

    A timeout or a 5xx from a cold model is weather, not a verdict; the
    third failure is reported as the failure it is.
    """
    last = None
    for i in range(attempts):
        try:
            return fn(), i
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last = exc
            if i < attempts - 1:
                time.sleep(base_delay * (3 ** i))
    raise last  # type: ignore[misc]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--provider", default="nebius")
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--tiers", default="fast,deep")
    ap.add_argument("--narrate", action="store_true",
                    help="also narrate each item on the standard tier and record the check")
    ap.add_argument("--budget", type=float, default=0.25,
                    help="USD cap; paid calls are skipped once exceeded (default 0.25)")
    ap.add_argument("--out", default=None, help="write the full results JSON here")
    args = ap.parse_args(argv)

    try:
        prof = providers.resolve(args.provider)
    except providers.ProviderError as exc:
        print(f"FAIL resolve: {exc}", file=sys.stderr)
        return 2

    items = ev.load_items(args.evidence)
    claims = ev.load_evidence(args.evidence)
    rows = review._load_rows(args.evidence)
    tiers = [t.strip() for t in args.tiers.split(",") if t.strip()]

    results = []
    spent = 0.0
    total_retries = 0
    for item_id in sorted(items):
        result = ev.explain(items, claims, item_id)
        deterministic = result.confidence()
        mine = [r for r in rows if r.get("item_id") == item_id]
        title = items[item_id].title or item_id
        claims_text = "\n".join(
            f"- [{r.get('kind')}/{r.get('aspect') or 'state'}] {r.get('source')}: "
            f"{r.get('statement')} (value: {r.get('value')})" for r in mine)
        entry = {"item": item_id, "deterministic": deterministic, "tiers": {}}

        for tier in tiers:
            if spent >= args.budget:
                entry["tiers"][tier] = {"verdict": "SKIPPED-BUDGET"}
                continue
            model = prof["models"][tier]
            prompt = review.PROMPT.format(title=title, item_id=item_id,
                                          claims=claims_text)
            started = time.time()
            try:
                (text, usage), used = _with_retries(
                    lambda: review._chat(prof["base_url"], prof["api_key"],
                                         model, prompt))
                total_retries += used
            except Exception as exc:  # a lane that fails is a result too
                entry["tiers"][tier] = {"verdict": "ERROR", "error": str(exc)[:120]}
                continue
            verdict, _reason = review._parse_verdict(text)
            pin, pout = review._price(tier, os.environ)
            cost = (usage.get("prompt_tokens", 0) * pin
                    + usage.get("completion_tokens", 0) * pout) / 1_000_000
            # The span carries the FACTS of the call, never its content.
            spans.record(operation="review", model=model, provider=prof["label"],
                         tier=tier, latency_ms=(time.time() - started) * 1000.0,
                         input_tokens=usage.get("prompt_tokens", 0),
                         output_tokens=usage.get("completion_tokens", 0),
                         cost_usd=cost, verdict=verdict, retry_count=used)
            spent += cost
            entry["tiers"][tier] = {
                "verdict": verdict,
                "agrees_with_deterministic": verdict == deterministic,
                "cost_usd": round(cost, 6),
                "tokens": [usage.get("prompt_tokens"), usage.get("completion_tokens")],
            }

        if args.narrate:
            if spent >= args.budget:
                entry["narration"] = {"check": "SKIPPED-BUDGET"}
            else:
                try:
                    bearer = prof["api_key"]
                    outcome, used = _with_retries(
                        lambda: narrate(result, base_url=prof["base_url"],
                                        model=prof["models"]["standard"],
                                        api_key=bearer))
                    total_retries += used
                    entry["narration"] = {
                        "check": "PASSED" if not outcome["unsupported_values"] else "FAILED",
                        "unsupported_values": outcome["unsupported_values"],
                    }
                except Exception as exc:
                    entry["narration"] = {"check": "ERROR", "error": str(exc)[:120]}
        results.append(entry)

    # Summary: agreement is reported per tier, never blended — a lane that
    # disagrees is information, and blending it away is the failure mode
    # this whole system exists to prevent.
    summary = {"items": len(results), "total_cost_usd": round(spent, 4),
               "retries": total_retries, "tier_agreement": {}}
    for tier in tiers:
        judged = [e for e in results
                  if e["tiers"].get(tier, {}).get("agrees_with_deterministic") is not None]
        agree = sum(1 for e in judged if e["tiers"][tier]["agrees_with_deterministic"])
        summary["tier_agreement"][tier] = f"{agree}/{len(judged)}"
    if args.narrate:
        checks = [e["narration"]["check"] for e in results if "narration" in e]
        summary["narration_checks"] = {c: checks.count(c) for c in sorted(set(checks))}

    for e in results:
        tier_str = "  ".join(
            f"{t}={e['tiers'][t]['verdict']}" for t in tiers)
        n_str = f"  narrate={e['narration']['check']}" if "narration" in e else ""
        print(f"{e['item']:12s} deterministic={e['deterministic']:12s} {tier_str}{n_str}")
    print(json.dumps(summary, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({"summary": summary, "results": results}, fh, indent=2)
        print(f"full results written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
