#!/usr/bin/env python3
"""why-agent — explain why, with the citation attached to every sentence.

Usage:
    python3 why_agent.py items --evidence evidence/items.jsonl
    python3 why_agent.py explain ITEM-ID --evidence evidence/items.jsonl
    python3 why_agent.py explain ITEM-ID --duckdb evidence/work.duckdb --json

What it does
------------
Given a work item, it gathers the claims that sources have made about it —
from a card body, a receipt, a commit, a check run, a model verdict — and
reconciles them. Where sources agree, it says so and cites them. Where they
disagree, it says THAT, with both sides cited. Where nobody said anything, it
says UNKNOWN.

That last one is the point. An agent that answers "why" from the first source
it reads sounds confident and is wrong more often than not; the interesting
cases are the ones where the sources contradict each other, and those are
exactly the cases a reader cannot resolve by eye because they live in five
different places.

The output is Markdown with a citation on every line, so a reader can check
each claim without trusting the agent.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from narrate import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    NarrateTokenError,
    NarrationOutage,
    format_narrative,
    narrate,
    resolve_narrate_token,
)
from evidence import (  # noqa: E402
    EXPECTED_ASPECTS,
    UNKNOWN,
    Evidence,
    Item,
    as_iterable,
    duckdb_rows,
    evidence_from_rows,
    explain,
    load_evidence,
    load_items,
)

DEFAULT_EVIDENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "evidence", "items.jsonl")


def _load(args: argparse.Namespace) -> tuple[dict[str, Item], list[Evidence]]:
    """Items and claims, from JSONL and/or a DuckDB file."""
    items: dict[str, Item] = {}
    claims: list[Evidence] = []

    if args.evidence:
        items = load_items(args.evidence)
        claims.extend(load_evidence(args.evidence))
    if args.duckdb:
        for row in duckdb_rows(args.duckdb, "items"):
            items[row["item_id"]] = Item(
                item_id=row["item_id"],
                title=row.get("title", ""),
                declared_status=row.get("declared_status", ""),
            )
        claims.extend(evidence_from_rows(duckdb_rows(args.duckdb, "evidence")))
    return items, claims


def _fmt_value(value: str) -> str:
    return f"`{value}`" if value else f"`{UNKNOWN}`"


def render(result) -> str:
    """The Markdown report. Every line that asserts something cites something."""
    item = result.item
    lines: list[str] = []
    title = item.title or item.item_id
    lines.append(f"# Why: {title}")
    lines.append("")
    lines.append(f"**Item:** `{item.item_id}`")
    lines.append(f"**Verdict:** {result.confidence()}")
    lines.append(f"**Sources read:** {result.sources}")
    lines.append("")

    if result.conflicts:
        lines.append("The sources disagree. That is the finding.")
    elif not result.by_aspect:
        lines.append("**No source has anything to say about this item.**")
    elif result.unknown_aspects:
        lines.append("The sources agree where they speak — and they do not cover "
                     "everything. The gaps are listed below.")
    else:
        lines.append("The sources agree, and they cover the ground.")
    lines.append("")

    lines.append("## What the sources say")
    lines.append("")
    any_claim = False
    for aspect in sorted(result.by_aspect):
        lines.append(f"### {aspect}")
        lines.append("")
        if aspect not in EXPECTED_ASPECTS:
            lines.append("Outside the vocabulary (not state, outcome, or cause). "
                         "Cited, not an agreement, and it does not fill an unknown.")
            lines.append("")
        for claim in result.by_aspect[aspect]:
            any_claim = True
            statement = f" — {claim.statement}" if claim.statement else ""
            lines.append(f"- **{claim.kind}**{statement} → {_fmt_value(claim.value)}"
                         f"  ·  `{claim.citation()}`")
        lines.append("")
    if not any_claim:
        lines.append("- *(no source made any claim about this item)*")
        lines.append("")

    if result.conflicts:
        lines.append("## Conflicts")
        lines.append("")
        for aspect, group in result.conflicts:
            lines.append(f"### {aspect}")
            lines.append("")
            for claim in group:
                lines.append(f"- {_fmt_value(claim.value)} — {claim.statement or claim.kind}"
                             f"  ·  `{claim.citation()}`")
            lines.append("")
        lines.append("**A single answer here would be a guess.** Each side is cited; "
                     "the reader decides which source is authoritative for that aspect.")
        lines.append("")

    if result.unknown_aspects:
        lines.append("## Unknowns")
        lines.append("")
        for aspect in result.unknown_aspects:
            lines.append(f"- **{aspect}** — no source says anything about this.")
        lines.append("")
        lines.append("These are UNKNOWN, not passes. An aspect nobody reported is a gap "
                     "in the evidence, and it is recorded as one.")
        lines.append("")

    lines.append("## What to check next")
    lines.append("")
    checks = _next_checks(result)
    for check in checks:
        lines.append(f"- {check}")
    if not checks:
        lines.append("- Nothing to chase: the sources agree and cover the ground.")
    lines.append("")
    return "\n".join(lines)


def _next_checks(result) -> list[str]:
    """What a human should look at next, derived from the gaps and conflicts."""
    out: list[str] = []
    for aspect, group in result.conflicts:
        locators = ", ".join(f"`{c.citation()}`" for c in group)
        out.append(f"Resolve the {aspect} conflict between {locators} — one of them "
                   f"is out of date, and which one is a decision, not a lookup.")
    for aspect in result.unknown_aspects:
        out.append(f"Find a source for {aspect}: nobody reported it, so it is "
                   f"UNKNOWN rather than fine.")
    if not out:
        out.append("Re-read the citations above if the answer stops making sense; "
                   "every line is checkable.")
    return out


def to_json(result) -> dict:
    return {
        "item_id": result.item.item_id,
        "title": result.item.title,
        "verdict": result.confidence(),
        "sources": result.sources,
        "claims": [
            {"aspect": aspect, "kind": c.kind, "source": c.source, "locator": c.locator,
             "statement": c.statement, "value": c.value, "citation": c.citation()}
            for aspect, group in sorted(result.by_aspect.items())
            for c in group
        ],
        "conflicts": [
            {"aspect": aspect,
             "values": sorted({c.value for c in group}),
             "citations": [c.citation() for c in group]}
            for aspect, group in result.conflicts
        ],
        "unknowns": result.unknown_aspects,
        "unexpected": [aspect for aspect, _ in result.unexpected],
    }


def cmd_items(args: argparse.Namespace) -> int:
    items, claims = _load(args)
    if not items:
        print("no items found", file=sys.stderr)
        return 1
    for item_id in sorted(items):
        mine = [c for c in claims if c.item_id == item_id]
        result = explain(items, claims, item_id)
        print(f"{item_id}\t{result.confidence()}\t{len(mine)} claim(s)\t{items[item_id].title}")
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    items, claims = _load(args)
    result = explain(items, claims, args.item_id)
    if getattr(args, "narrate", False):
        try:
            api_key, source = resolve_narrate_token(args.narrate_key)
        except NarrateTokenError as exc:
            print(f"narrate token source: {exc.source}", file=sys.stderr)
            print(f"narrate token rejected: {exc}", file=sys.stderr)
            return 2
        print(f"narrate token source: {source}", file=sys.stderr)
        try:
            outcome = narrate(result,
                              base_url=args.narrate_base,
                              model=args.narrate_model,
                              api_key=api_key,
                              app_id=args.narrate_app)
        except NarrationOutage as exc:
            print(f"narration outage: {exc}", file=sys.stderr)
            return 1
        except NarrateTokenError as exc:
            print(f"narrate token source: {exc.source}", file=sys.stderr)
            print(f"narrate token rejected: {exc}", file=sys.stderr)
            return 2
        if args.json:
            payload = to_json(result)
            payload["narrative"] = outcome
            print(json.dumps(payload, indent=2))
        else:
            print(format_narrative(result, outcome))
        return 0
    if args.json:
        print(json.dumps(to_json(result), indent=2))
    else:
        print(render(result))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    # The same two flags are accepted before and after the subcommand, because
    # a tool that only works one way is a tool people get wrong.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--evidence", default=argparse.SUPPRESS,
                        help="JSONL evidence file")
    common.add_argument("--duckdb", default=argparse.SUPPRESS,
                        help="DuckDB file with items/evidence tables")

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--evidence", default=DEFAULT_EVIDENCE,
                    help="JSONL evidence file (default: %(default)s)")
    ap.add_argument("--duckdb", default=None,
                    help="DuckDB file with items/evidence tables (the production path)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("items", help="list the items and their verdicts",
                       parents=[common])
    p.set_defaults(func=cmd_items)

    p = sub.add_parser("explain", help="explain one item", parents=[common])
    p.add_argument("item_id")
    p.add_argument("--json", action="store_true")
    p.add_argument("--narrate", action="store_true",
                   help="write the prose with a model, then CHECK it against the evidence")
    p.add_argument("--narrate-base", default=DEFAULT_BASE_URL,
                   help="OpenAI-compatible base URL (default: the local Meterless runtime)")
    p.add_argument("--narrate-model", default=DEFAULT_MODEL,
                   help="model id (default: %(default)s)")
    p.add_argument("--narrate-key", default=None,
                   help="bearer token, if the endpoint wants one")
    p.add_argument("--narrate-app", default="why-agent",
                   help="stable app id sent with every request (default: %(default)s)")
    p.set_defaults(func=cmd_explain)

    args = ap.parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
