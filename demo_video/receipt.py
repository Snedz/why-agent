#!/usr/bin/env python3
"""Print the Nebius Token Factory receipt for one item.

Every figure is read from the committed run outputs — the endpoint and the
model ids from the provider profile, the tier costs from the tier ledger's own
functions, the verdicts from the eval output. Nothing here is typed in, so the
receipt cannot drift from the run it describes.

    python3 demo_video/receipt.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tier_ledger  # noqa: E402
import providers  # noqa: E402

ITEM = "why-alpha"


def main() -> int:
    profile = providers.PROFILES["nebius"]
    models = profile["models"]

    print("NEB IUS TOKEN FACTORY — recorded run receipt".replace("NEB IUS", "NEBIUS"))
    print("=" * 72)
    print(f"endpoint    {profile['base_url']}")
    print(f"run date    {tier_ledger.date_of(tier_ledger.DEMO_RESULTS)}        "
          f"committed in this repository")
    print()
    print("model ids pinned on this account:")
    for tier, label in (("standard", "narration     "),
                        ("fast", "reviewer fast "),
                        ("deep", "reviewer deep "),
                        ("vision", "vision        ")):
        print(f"  {label}  {models[tier]}")

    print()
    print("measured reviewer-lane cost (tier_ledger.py reads the run outputs):")
    rendered = tier_ledger.render()
    for line in rendered.splitlines():
        if line.startswith("| deep ") or line.startswith("| fast "):
            cols = [c.strip() for c in line.strip("|").split("|")]
            tier, model, calls, tin, tout, cost, agree = cols
            print(f"  {tier:5} {model:44} {tin:>6} in /{tout:>6} out  {cost:>7}"
                  f"  agrees {agree}")

    print()
    print("one item, three verdicts:")
    demo = json.loads(tier_ledger.DEMO_RESULTS.read_text(encoding="utf-8"))
    for entry in demo.get("results", []):
        if entry.get("item") != ITEM:
            continue
        print(f"  {ITEM}: gate {entry['deterministic']}")
        for tier, out in entry.get("tiers", {}).items():
            tokens = out.get("tokens") or [0, 0]
            print(f"    {tier:5} {out['verdict']:12} {tokens[0]:>4} in /{tokens[1]:>4} out"
                  f"   ${out['cost_usd']:.6f}")
        narr = entry.get("narration") or {}
        flags = ", ".join(narr.get("unsupported_values") or []) or "none"
        print(f"    narration check {narr.get('check')} — unsupported value(s): {flags}")

    print()
    bench = json.loads(tier_ledger.BENCH_RESULTS.read_text(encoding="utf-8"))
    summary = bench.get("summary") or {}
    rows = sum(1 for line in tier_ledger.CASES.read_text(encoding="utf-8").splitlines()
               if line.strip())
    print(f"corpus: {len(tier_ledger.load_json(tier_ledger.TRUTH))} items, {rows} claim rows · "
          f"reviewer-lane cost ${float(summary.get('total_cost_usd') or 0.0):.3f} · "
          f"{summary.get('retries', 0)} retries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
