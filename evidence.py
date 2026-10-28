"""Evidence model for the "why" agent.

The answer to "why did this happen?" is scattered across places that
do not talk to each other: a card body, a receipt, a commit message, a check
run, a model verdict. An agent that reads one of them will sound confident and
be wrong.

So every source here makes a CLAIM about an item, and the agent reconciles the
claims instead of merging them. Three outcomes, and they are different:

  * agreement   — two or more sources say the same thing
  * conflict    — two sources say different things (stated, never smoothed)
  * unknown     — nobody said (UNKNOWN is never 0)

The evidence is deliberately small and explicit: this module reads rows, it
does not guess. The rows come from a JSONL file (no dependency, legible in a
terminal) or from a DuckDB file (the production path, and the Zetaris path —
the same rows a filestore table would hold).
"""
from __future__ import annotations

import dataclasses
import json
import os
from typing import Any, Iterable, Sequence

# The kinds of source that can make a claim. Order matters: the report prints
# them in this order so the same question always reads the same way.
KINDS = ("card", "receipt", "commit", "check", "verdict", "web")

# An ASPECT is a property of the item, not of the source. Two sources that
# speak about different aspects never contradict each other: a receipt about
# what was claimed does not contradict a commit about what changed. Two claims
# about the SAME aspect with different values DO contradict each other, and
# that is the case worth surfacing.
#
# The default aspect for each kind of source, used when a row does not name
# one. A row may override it — the synthetic dataset does, so the demo can
# show a source disagreeing with another of a different kind.
DEFAULT_ASPECT = {
    "card": "state",
    "commit": "state",
    "check": "state",
    "receipt": "outcome",
    "verdict": "outcome",
    "web": "state",
}

# The aspects a reader expects to be covered. An aspect nobody spoke about is
# an UNKNOWN, not a pass.
EXPECTED_ASPECTS = ("state", "outcome", "cause")

UNKNOWN = "UNKNOWN"


@dataclasses.dataclass(frozen=True)
class Evidence:
    """One claim, by one source, with the citation needed to check it."""

    item_id: str
    kind: str
    source: str
    locator: str
    statement: str
    value: str
    observed_at: str = ""
    aspect: str = ""

    @property
    def aspect_name(self) -> str:
        return self.aspect or DEFAULT_ASPECT.get(self.kind, self.kind)

    def citation(self) -> str:
        """How a reader checks this claim. Never a bare assertion."""
        if self.locator:
            return f"{self.source} — {self.locator}"
        return self.source


@dataclasses.dataclass
class Item:
    item_id: str
    title: str = ""
    declared_status: str = ""


@dataclasses.dataclass
class Reconciliation:
    """The result of reading every claim about one item."""

    item: Item
    by_aspect: dict[str, list[Evidence]]
    conflicts: list[tuple[str, list[Evidence]]]
    agreements: list[tuple[str, list[Evidence]]]
    unknown_aspects: list[str]
    # Aspects outside state/outcome/cause. Cited, never an agreement, and
    # never something that fills an unknown.
    unexpected: list[tuple[str, list[Evidence]]] = dataclasses.field(
        default_factory=list)

    @property
    def sources(self) -> int:
        return sum(len(v) for v in self.by_aspect.values())

    def confidence(self) -> str:
        """A word, not a number. A number here would be a number we did not measure."""
        if self.conflicts:
            return "CONFLICTED"
        if not self.by_aspect:
            return "NO EVIDENCE"
        if self.unknown_aspects:
            return "PARTIAL"
        return "CORROBORATED"


def load_items(path: str) -> dict[str, Item]:
    """Read the synthetic (or real) evidence file.

    The file is JSON Lines, one object per row, with an optional header line
    naming the fields. It is deliberately a format a person can read and a
    program can parse — a demo must be legible.
    """
    items: dict[str, Item] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            row = json.loads(line)
            kind = row.get("kind") or "card"
            if kind == "card":
                item_id = row["item_id"]
                items[item_id] = Item(
                    item_id=item_id,
                    title=row.get("title", ""),
                    declared_status=row.get("value", ""),
                )
    return items


def load_evidence(path: str) -> list[Evidence]:
    """Every row is a claim by a source — INCLUDING the card row.

    The card is a source like any other: it says what state the item is in,
    and it is the source most likely to be stale. Leaving it out would make
    the agent unable to notice a card that disagrees with reality, which is
    the single most common way these systems go wrong.
    """
    rows: list[Evidence] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            row = json.loads(line)
            kind = row.get("kind") or "card"
            rows.append(Evidence(
                item_id=row["item_id"],
                kind=kind,
                source=row.get("source", kind),
                locator=row.get("locator", ""),
                statement=row.get("statement", ""),
                value=row.get("value", ""),
                observed_at=row.get("observed_at", ""),
                aspect=row.get("aspect", ""),
            ))
    return rows


def reconcile(item: Item, claims: Sequence[Evidence]) -> Reconciliation:
    """Group the claims by aspect, then say plainly where they disagree."""
    by_aspect: dict[str, list[Evidence]] = {}
    for claim in claims:
        by_aspect.setdefault(claim.aspect_name, []).append(claim)

    conflicts: list[tuple[str, list[Evidence]]] = []
    agreements: list[tuple[str, list[Evidence]]] = []
    unknown_aspects: list[str] = []
    unexpected: list[tuple[str, list[Evidence]]] = []

    for aspect in sorted(by_aspect):
        group = by_aspect[aspect]
        if aspect not in EXPECTED_ASPECTS:
            # A forged or unknown aspect is cited and then ignored by the
            # verdict. It cannot agree its way into CORROBORATED, and it
            # cannot stand in for state, outcome, or cause.
            unexpected.append((aspect, group))
            continue
        values = {claim.value for claim in group}
        if len(values) == 1:
            agreements.append((aspect, group))
        else:
            conflicts.append((aspect, group))

    # An aspect nobody spoke about is an unknown, not a pass. The aspects we
    # look for are the ones a reader would expect to be covered. An unexpected
    # aspect does not fill one of these.
    for aspect in EXPECTED_ASPECTS:
        if aspect not in by_aspect:
            unknown_aspects.append(aspect)

    return Reconciliation(item=item, by_aspect=by_aspect, conflicts=conflicts,
                          agreements=agreements, unknown_aspects=unknown_aspects,
                          unexpected=unexpected)


def explain(items: dict[str, Item], claims: Sequence[Evidence],
             item_id: str) -> Reconciliation:
    """Reconcile one item. An unknown item is an unknown, not an empty answer."""
    item = items.get(item_id)
    if item is None:
        item = Item(item_id=item_id)
    mine = [c for c in claims if c.item_id == item_id]
    return reconcile(item, mine)


# Table names that may be interpolated into SQL. Anything else is rejected
# before a connection is opened, so a caller cannot turn the table argument
# into a statement.
ALLOWED_DUCKDB_TABLES = frozenset({"items", "evidence"})


def duckdb_rows(path: str, table: str = "evidence") -> list[dict[str, Any]]:
    """Read one allowlisted table out of a DuckDB file, if the file is there.

    This is the production path and the Zetaris path: the same rows a filestore
    table would hold. DuckDB is imported here rather than at module scope so
    the demo runs with no third-party package.
    """
    if table not in ALLOWED_DUCKDB_TABLES:
        raise ValueError("duckdb table is not allowlisted")
    if not os.path.exists(path):
        return []
    try:
        import duckdb  # noqa: PLC0415 - optional dependency, imported on use
    except ImportError as exc:
        raise RuntimeError(
            f"reading {path} needs duckdb: pip install duckdb"
        ) from exc
    con = duckdb.connect(path, read_only=True)
    try:
        rows = con.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
        cols = [d[0] for d in con.description]
        return [dict(zip(cols, row)) for row in rows]
    finally:
        con.close()


def evidence_from_rows(rows: Iterable[dict[str, Any]]) -> list[Evidence]:
    """Turn table rows into claims, skipping the card rows (they are items)."""
    claims: list[Evidence] = []
    for row in rows:
        kind = row.get("kind") or "card"
        if kind == "card":
            continue
        claims.append(Evidence(
            item_id=str(row.get("item_id", "")),
            kind=kind,
            source=str(row.get("source", kind)),
            locator=str(row.get("locator", "") or ""),
            statement=str(row.get("statement", "") or ""),
            value=str(row.get("value", "") or ""),
            observed_at=str(row.get("observed_at", "") or ""),
            aspect=str(row.get("aspect", "") or ""),
        ))
    return claims


def as_iterable(value: Any) -> Iterable[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return value
    return [value]
