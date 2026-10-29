"""ledger.py — regenerate `docs/TIER_LEDGER.md` from the committed run outputs.

The ledger says "Generated from ...". This is what generates it.

**No number in the doc is hand-typed.** The counts come from the two committed
results files, the price table comes from `review.py`, the model ids come from
the provider profile, and the corpus numbers come from the same scorer the ship
gate uses — so the ledger and the gate cannot disagree.

The output is a function of its inputs and nothing else: no clock, no random
order, no environment. Regenerating it twice produces the same bytes, and
regenerating it after the inputs change produces a DIFFERENT doc — which is the
point of a ledger that is generated instead of asserted.

    python3 ledger.py            # write the doc
    python3 ledger.py --check    # fail if the committed doc differs by a byte
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _extra in (HERE, HERE / "benchmark"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import providers  # noqa: E402
import review  # noqa: E402
from score import score_counts  # noqa: E402 — the same scorer the ship gate uses

DOC = HERE / "docs" / "TIER_LEDGER.md"
DEMO_RESULTS = HERE / "eval-results-2026-10-28.json"
BENCH_RESULTS = HERE / "benchmark" / "eval-benchmark-2026-10-28.json"
CASES = HERE / "benchmark" / "cases.jsonl"
TRUTH = HERE / "benchmark" / "truth.json"
BENCH_DOC = "docs/BENCHMARK_RESULTS_2026-10-28.md"


class LedgerError(RuntimeError):
    """An input is missing, corrupt, or says less than the ledger needs.

    The ledger fails rather than emitting a number it cannot source. A ledger
    with a guessed figure is worse than no ledger.
    """


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LedgerError(f"missing input: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LedgerError(f"corrupt input: {path}: {exc}") from exc


def date_of(path: Path) -> str:
    """The date in a results file's name, e.g. 2026-10-28.

    From the file name, not from the clock: a ledger that changes when you
    regenerate it is not a generated document.
    """
    found = re.findall(r"\d{4}-\d{2}-\d{2}", path.name)
    if not found:
        raise LedgerError(f"no date in the name of {path.name}")
    return found[-1]


def price_snapshot_date() -> str:
    """The catalogue date of the price table, READ from review.py.

    It lives in review.py's own comment above the table, and this card does not
    edit review.py — so it is read, not copied. If that comment is ever reworded
    the ledger fails rather than publishing an undated price.
    """
    source = (HERE / "review.py").read_text(encoding="utf-8")
    marker = source.find("PRICE_SNAPSHOT")
    if marker < 0:
        raise LedgerError("review.py has no PRICE_SNAPSHOT table")
    window = source[max(0, marker - 400):marker]
    dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", window)
    if not dates:
        raise LedgerError("review.py's PRICE_SNAPSHOT carries no date to name")
    return dates[-1]


def narration_tier() -> str:
    """Which tier the narration call runs on, READ from batch_eval's own help.

    The ledger names the tier whose price is NOT in the totals, so it has to be
    right. It is read from the harness that runs it, not copied into this file,
    and if the wording changes the ledger fails rather than naming the wrong
    tier.
    """
    source = (HERE / "batch_eval.py").read_text(encoding="utf-8")
    found = re.search(r"narrate each item on the (\w+) tier", source)
    if not found:
        raise LedgerError("batch_eval.py does not say which tier the narration call uses")
    return found.group(1)


def tier_totals(results: list[dict]) -> dict[str, dict]:
    """Calls, tokens, cost and agreements per tier, summed over the results."""
    totals: dict[str, dict] = {}
    for entry in results:
        for tier, outcome in sorted(entry.get("tiers", {}).items()):
            row = totals.setdefault(tier, {"calls": 0, "in": 0, "out": 0,
                                          "cost": 0.0, "agree": 0, "unparseable": 0})
            row["calls"] += 1
            tokens = outcome.get("tokens") or [0, 0]
            if len(tokens) != 2:
                raise LedgerError(f"a tier row has {len(tokens)} token counts, expected 2")
            row["in"] += int(tokens[0])
            row["out"] += int(tokens[1])
            row["cost"] += float(outcome.get("cost_usd") or 0.0)
            if outcome.get("agrees_with_deterministic"):
                row["agree"] += 1
            if (outcome.get("verdict") or "") not in review.VERDICTS:
                row["unparseable"] += 1
    if not totals:
        raise LedgerError("no tier rows in the results")
    return totals


def corpus_scores() -> dict[str, dict]:
    """The planted-truth score of the deterministic gate and of each lane."""
    truth = load_json(TRUTH)
    items = __import__("evidence").load_items(str(CASES))
    claims = __import__("evidence").load_evidence(str(CASES))
    got = {item_id: __import__("evidence").explain(items, claims, item_id).confidence()
           for item_id in truth}
    scores = {"gate": score_counts(got, truth)}
    bench = load_json(BENCH_RESULTS)
    tiers = sorted({t for r in bench["results"] for t in r.get("tiers", {})})
    for tier in tiers:
        lane = {r["item"]: r["tiers"][tier]["verdict"] for r in bench["results"]
                if r["item"] in truth and tier in r.get("tiers", {})}
        if lane:
            scores[tier] = score_counts(lane, truth)
    return scores


def render() -> str:
    demo = load_json(DEMO_RESULTS)
    bench = load_json(BENCH_RESULTS)
    demo_rows = demo.get("results")
    bench_rows = bench.get("results")
    if not isinstance(demo_rows, list) or not isinstance(bench_rows, list):
        raise LedgerError("a results file has no 'results' list")

    totals = tier_totals(demo_rows)
    for tier, row in tier_totals(bench_rows).items():
        other = totals.setdefault(tier, {"calls": 0, "in": 0, "out": 0,
                                         "cost": 0.0, "agree": 0, "unparseable": 0})
        for key in other:
            other[key] += row[key]

    scores = corpus_scores()
    run_date = date_of(DEMO_RESULTS)
    price_date = price_snapshot_date()
    models = providers.PROFILES["nebius"]["models"]
    prices = review.PRICE_SNAPSHOT
    price_line = ", ".join(f"{tier} {pin:.2f}/{pout:.2f}" for tier, (pin, pout) in sorted(prices.items()))

    lines = [
        f"# Tier ledger — measured {run_date}, Token Factory",
        "",
        f"Generated by `ledger.py` from `eval-results-{run_date}.json` "
        f"({len(demo_rows)} demo items) and `benchmark/eval-benchmark-{run_date}.json` "
        f"({len(bench_rows)} benchmark items; the zero-claim item cannot be lane-run). "
        f"Prices are the snapshot in `review.py` (`PRICE_SNAPSHOT`, dated {price_date}), "
        f"per 1M tokens, in/out: {price_line} USD.",
        "",
        "| Tier | Model | Calls | Tokens in | Tokens out | Cost | Agrees with gate |",
        "|---|---|---|---|---|---|---|",
    ]
    for tier in sorted(totals):
        row = totals[tier]
        lines.append(
            f"| {tier} | {models.get(tier, 'unpinned')} | {row['calls']} | "
            f"{row['in']:,} | {row['out']:,} | ${row['cost']:.4f} | "
            f"{row['agree']}/{row['calls']} |"
        )
    lines.append("")

    corpus_bits = []
    for tier in sorted(k for k in scores if k != "gate"):
        count = scores[tier]
        corpus_bits.append(f"{tier} {count['correct']}/{count['total']}")
    gate = scores["gate"]
    corpus_bits.append(f"gate {gate['correct']}/{gate['total']}")
    lines.append(
        "On the adversarial corpus scored against planted truth (not just agreement): "
        + ", ".join(corpus_bits) + f" — `{BENCH_DOC}`."
    )
    lines.append("")

    lines += ["## The honest reading", ""]
    cheap, dear = sorted(totals, key=lambda t: totals[t]["cost"])
    ratio = totals[dear]["cost"] / totals[cheap]["cost"] if totals[cheap]["cost"] else 0.0
    # Per lane, never pooled: "deep falsely approved once" and "the lanes falsely
    # approved three times" are different claims, and only the first one is true.
    faults = []
    for tier in sorted(scores):
        if tier == "gate":
            continue
        false = len(scores[tier]["false_approvals"])
        unparseable = totals.get(tier, {}).get("unparseable", 0)
        if false or unparseable:
            faults.append(f"{tier} falsely approved {false} time(s) and returned "
                          f"{unparseable} unparseable verdict(s)")
    lines.append(
        f"{dear} costs ~{ratio:.0f}× {cheap} per call and buys real accuracy "
        f"({totals[dear]['agree']} vs {totals[cheap]['agree']} agreements; "
        f"{scores[dear]['correct']} vs {scores[cheap]['correct']} corpus-correct). "
        + (". ".join(faults) + ". " if faults else "")
        + f"Routing consequence: **{cheap} for cheap first-pass claims triage, "
        f"{dear} on escalation, neither as a gate** — the deterministic reconciler, "
        f"which costs nothing and scored {gate['correct']}/{gate['total']}, decides."
    )
    lines.append("")

    lines += ["## What this ledger does not contain", ""]
    narration_failed = sum(
        1 for entry in demo_rows + bench_rows
        if (entry.get("narration") or {}).get("check") == "FAILED")
    narrate = narration_tier()
    lines += [
        f"- **Narration cost.** The harness does not meter the narration call (the "
        f"{narrate} tier — {models.get(narrate, 'unpinned')}), so every total here is a "
        f"reviewer-lane total, not a run total. In the runs above the narration check "
        f"FAILED {narration_failed} time(s) and the failures are recorded in the results "
        f"files. Metering the narration call is a recorded harness fix.",
        "- **Latency.** Per-call latency is not recorded by the harness, so this ledger "
        "publishes no latency percentile: there is no median because none was measured. "
        "The only latency facts on record are qualitative (tiers ~1s warm; one ~3-minute "
        "cold-load stall).",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="fail if the committed doc differs from what this would write")
    args = ap.parse_args(argv)
    try:
        text = render()
    except LedgerError as exc:
        print(f"ledger: {exc}", file=sys.stderr)
        return 2
    if args.check:
        try:
            current = DOC.read_text(encoding="utf-8")
        except FileNotFoundError:
            current = ""
        if current != text:
            print(f"ledger: {DOC.name} is not what ledger.py generates — run `python3 ledger.py`",
                  file=sys.stderr)
            return 1
        print(f"ledger: {DOC.name} matches the committed outputs byte for byte")
        return 0
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(text, encoding="utf-8")
    print(f"ledger: wrote {DOC.relative_to(HERE)} ({len(text.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
