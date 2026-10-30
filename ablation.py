"""Tavily ablation: what does the live-web lane actually change?

The claim made for the Tavily lane is narrow and testable: some claims are
about the outside world, and checking them against live pages changes what
the reconciler can honestly say. This harness measures that claim instead
of asserting it. For every item in a base evidence file it computes the
verdict twice — once with web rows excluded, once with them included —
and reports the differences item by item.

A changed verdict is a fact, not a trophy. The web lane can move a verdict
toward the truth (a deadline confirmed from the official page) or expose a
conflict the local record had smoothed over (the page says a different
date). Both directions are reported in the same table, and the summary
counts them without adjectives.

Two modes:

  Offline (rows already fetched):
    python3 ablation.py --base evidence/items.jsonl \
        --web evidence/web-rows.jsonl --out docs/ablation.json

  Live (fetch first, then ablate; needs TAVILY_API_KEY):
    python3 ablation.py --base evidence/items.jsonl \
        --claims ablation_claims.json --fetch \
        --web evidence/web-rows.jsonl --out docs/ablation.json

In live mode each claims-spec entry names an item, a search query, and the
claimed value; the lane's literal-appearance rule applies unchanged — a
page counts only if the value literally appears in its content, and
non-matches are recorded as empty-value rows, so the ablation sees the
misses too.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import sys
from typing import Any

from evidence import Evidence, Item, load_evidence, load_items, reconcile


def _verdicts(items: dict[str, Item], claims: list[Evidence],
              include_web: bool) -> dict[str, str]:
    """One verdict word per item, with or without the web rows."""
    by_item: dict[str, list[Evidence]] = {}
    for claim in claims:
        if not include_web and claim.kind == "web":
            continue
        by_item.setdefault(claim.item_id, []).append(claim)
    out: dict[str, str] = {}
    for item_id, item in items.items():
        out[item_id] = reconcile(item, by_item.get(item_id, [])).confidence()
    return out


def ablate(items: dict[str, Item], claims: list[Evidence]) -> dict[str, Any]:
    """Compare verdicts with and without web rows, per item."""
    without = _verdicts(items, claims, include_web=False)
    with_web = _verdicts(items, claims, include_web=True)
    rows = []
    for item_id in items:
        rows.append({
            "item_id": item_id,
            "verdict_without_web": without[item_id],
            "verdict_with_web": with_web[item_id],
            "changed": without[item_id] != with_web[item_id],
            "web_rows": sum(1 for c in claims
                            if c.item_id == item_id and c.kind == "web"),
            "web_rows_with_value": sum(
                1 for c in claims
                if c.item_id == item_id and c.kind == "web" and c.value),
        })
    changed = [r for r in rows if r["changed"]]
    return {
        "items": rows,
        "summary": {
            "items_total": len(rows),
            "items_with_web_rows": sum(1 for r in rows if r["web_rows"]),
            "verdicts_changed": len(changed),
            "changed_item_ids": [r["item_id"] for r in changed],
        },
    }


def fetch_web_rows(spec_path: str, retrieved_at: str) -> list[Evidence]:
    """Run the Tavily lane for each claims-spec entry. Live mode only."""
    import tavily_lane  # deferred: offline mode must not require the lane

    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    rows: list[Evidence] = []
    for entry in spec:
        results = tavily_lane.search_claims(entry["query"])
        rows.extend(tavily_lane.results_to_evidence(
            entry["item"], results, entry["claim"], retrieved_at))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Tavily on/off ablation")
    ap.add_argument("--base", required=True,
                    help="base evidence JSONL (items + local claims)")
    ap.add_argument("--web", required=True,
                    help="web-rows JSONL (read in offline mode, written in live mode)")
    ap.add_argument("--claims", help="claims spec JSON for --fetch")
    ap.add_argument("--fetch", action="store_true",
                    help="fetch web rows live before ablating (needs TAVILY_API_KEY)")
    ap.add_argument("--out", help="write the JSON report here")
    args = ap.parse_args(argv)

    items = load_items(args.base)
    claims = load_evidence(args.base)

    if args.fetch:
        if not args.claims:
            print("FAIL: --fetch needs --claims", file=sys.stderr)
            return 1
        retrieved_at = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        try:
            web_rows = fetch_web_rows(args.claims, retrieved_at)
        except Exception as exc:  # the lane's errors are RuntimeErrors
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        with open(args.web, "w", encoding="utf-8") as fh:
            for row in web_rows:
                fh.write(json.dumps(dataclasses.asdict(row)) + "\n")
        claims = claims + web_rows
        print(f"fetched {len(web_rows)} web row(s) into {args.web}")
    else:
        claims = claims + load_evidence(args.web)

    report = ablate(items, claims)
    text = json.dumps(report, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    s = report["summary"]
    print(f"items: {s['items_total']} | with web rows: "
          f"{s['items_with_web_rows']} | verdicts changed: "
          f"{s['verdicts_changed']} {s['changed_item_ids']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
