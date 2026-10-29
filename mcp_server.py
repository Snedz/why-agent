"""MCP server for why-agent — three tools, and no model in the loop.

The house rule this implements: **integrations contribute claims, never
verdicts.** A tool call may add evidence; the verdict is computed from the
evidence, every time, by `evidence.explain`. So the boundary enforces it:
a submission carrying a verdict-shaped field is refused with an error rather
than quietly stored, because a verdict that arrives from outside is a verdict
nobody can check.

Three tools, and only three:

  submit_claims       add evidence rows (claims only) for one or more items
  get_verdict         the deterministic verdict for an item, grouped by
                      aspect, every claim cited
  get_disagreements   the lane verdicts that disagree with the deterministic
                      verdict, or with each other, cited

**The server calls no model.** It reads rows and reconciles them. That is the
point: the answer does not depend on a provider being up, and the same input
always gives the same verdict.

Transport: MCP over stdio, JSON-RPC 2.0 (protocol 2026-07-28, with the
earlier versions accepted). The official MCP Python SDK is NOT a dependency
of this repo — it is not installed here, and the card says no other new
dependency — so the wire protocol is spoken directly. Everything a judge
needs to read is in the tool results, which are plain JSON.

Run it:
    python3 mcp_server.py --evidence evidence/items.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import evidence as ev  # noqa: E402 — the house's own reconciler, not a copy of it

SERVER_NAME = "why-agent"
SERVER_VERSION = "0.1.0"

# The MCP revisions this server speaks, newest first. A client that asks for
# one of these gets that one back; a client that asks for something else gets
# an error naming the ones it can have.
PROTOCOL_VERSIONS = ("2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26",
                     "2024-11-05")

# A claim is a row a source makes about an item. "verdict" is NOT one of them:
# a lane's verdict is reported, not submitted.
CLAIM_KINDS = ("card", "receipt", "commit", "check", "web")

# Field names that carry a verdict. A submission with any of them is refused.
VERDICT_FIELDS = ("verdict", "verdicts", "confidence", "deterministic",
                  "agrees_with_deterministic")

# The fields a claim may carry. The input schema says this too; the check
# below says it again in a message a model can act on.
CLAIM_FIELDS = ("item_id", "kind", "source", "locator", "statement", "value",
                "observed_at", "aspect")


class SchemaError(ValueError):
    """The call does not fit the schema.

    A tool execution error, not a crash and not a protocol error: the model
    that made the call can read the message and try again.
    """


class Store:
    """Items, claims and lane verdict rows — in memory, and read-only on disk.

    The store loads an evidence JSONL once and never writes to it. Submitted
    claims live in the process: a card says "no write path that mutates
    evidence files on disk", and this is how that is honoured.
    """

    def __init__(self, evidence_path: str | None = None) -> None:
        self.items: dict[str, ev.Item] = {}
        self.claims: list[ev.Evidence] = []
        self.verdict_rows: list[ev.Evidence] = []
        if evidence_path:
            self.load(evidence_path)

    def load(self, path: str) -> None:
        self.items = ev.load_items(path)
        self.claims = []
        self.verdict_rows = []
        for row in ev.load_evidence(path):
            if row.kind == "verdict":
                self.verdict_rows.append(row)
            else:
                self.claims.append(row)

    def submit(self, rows: list[dict[str, Any]]) -> int:
        for row in rows:
            self.claims.append(ev.Evidence(
                item_id=row["item_id"],
                kind=row.get("kind") or "card",
                source=row.get("source", row.get("kind") or "card"),
                locator=row.get("locator", ""),
                statement=row.get("statement", ""),
                value=row.get("value", ""),
                observed_at=row.get("observed_at", ""),
                aspect=row.get("aspect", ""),
            ))
        return len(rows)

    def reconciliation(self, item_id: str) -> ev.Reconciliation:
        """The deterministic reading. evidence.explain is the only source of it."""
        return ev.explain(self.items, self.claims, item_id)


def _claim(row: dict[str, Any], index: int) -> dict[str, Any]:
    """One submitted row, checked. Raises SchemaError with a message to act on."""
    if not isinstance(row, dict):
        raise SchemaError(f"claims[{index}] must be an object")
    for field in VERDICT_FIELDS:
        if field in row:
            raise SchemaError(
                f"claims[{index}] carries the verdict-shaped field {field!r}. "
                "Integrations contribute claims, never verdicts: the verdict is "
                "computed from the claims by evidence.explain, so a submitted "
                "one could not be checked by anyone.")
    kind = row.get("kind") or "card"
    if kind == "verdict":
        raise SchemaError(
            f"claims[{index}] is a verdict row. A lane's verdict is reported by "
            "get_disagreements, not submitted as a claim.")
    if kind not in CLAIM_KINDS:
        raise SchemaError(
            f"claims[{index}] has kind {kind!r}; a claim is one of "
            f"{', '.join(CLAIM_KINDS)}.")
    for field in ("item_id", "statement"):
        if not row.get(field):
            raise SchemaError(f"claims[{index}] has no {field}")
    return {field: row[field] for field in CLAIM_FIELDS if field in row}


def tool_submit_claims(store: Store, args: dict[str, Any]) -> dict[str, Any]:
    rows = args.get("claims")
    if not isinstance(rows, list):
        raise SchemaError("claims must be a list of claim objects")
    checked = [_claim(row, i) for i, row in enumerate(rows)]
    stored = store.submit(checked)
    return {"submitted": stored,
            "items": sorted({row["item_id"] for row in checked}),
            "note": "claims only; the verdict is computed from them"}


def tool_get_verdict(store: Store, args: dict[str, Any]) -> dict[str, Any]:
    item_id = args.get("item_id")
    if not item_id:
        raise SchemaError("item_id is required")
    rec = store.reconciliation(item_id)
    aspects: dict[str, list[dict[str, Any]]] = {}
    citations: list[str] = []
    for aspect, claims in sorted(rec.by_aspect.items()):
        aspects[aspect] = [
            {"kind": c.kind, "source": c.source, "locator": c.locator,
             "statement": c.statement, "value": c.value,
             "aspect": c.aspect_name, "citation": c.citation()}
            for c in claims
        ]
        citations.extend(c.citation() for c in claims)
    return {
        "item_id": item_id,
        "title": rec.item.title,
        "verdict": rec.confidence(),
        "aspects": aspects,
        "unknown_aspects": sorted(rec.unknown_aspects),
        "conflicts": [{"aspect": aspect, "citations": [c.citation() for c in claims]}
                      for aspect, claims in rec.conflicts],
        "citations": citations,
        "source": "evidence.explain",
    }


def tool_get_disagreements(store: Store, args: dict[str, Any]) -> dict[str, Any]:
    item_id = args.get("item_id")
    if not item_id:
        raise SchemaError("item_id is required")
    deterministic = store.reconciliation(item_id).confidence()
    rows = [r for r in store.verdict_rows if r.item_id == item_id]
    lanes = []
    for row in rows:
        lane_verdict = (row.value or "").strip().upper()
        lanes.append({
            "lane": row.source,
            "verdict": lane_verdict,
            "statement": row.statement,
            "citation": row.citation(),
            "agrees_with_deterministic": lane_verdict == deterministic,
        })
    pairs = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a = (rows[i].value or "").strip().upper()
            b = (rows[j].value or "").strip().upper()
            if a and b and a != b:
                pairs.append({
                    "lanes": [rows[i].source, rows[j].source],
                    "verdicts": [a, b],
                    "citations": [rows[i].citation(), rows[j].citation()],
                })
    return {
        "item_id": item_id,
        "deterministic": deterministic,
        "lanes": lanes,
        "disagreements": [l for l in lanes if not l["agrees_with_deterministic"]],
        "lane_disagreements": pairs,
    }


def _claim_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "The item the claim is about."},
            "kind": {"type": "string", "enum": list(CLAIM_KINDS),
                     "description": "What kind of source this claim is."},
            "source": {"type": "string", "description": "Who made the claim."},
            "locator": {"type": "string", "description": "Where to check it."},
            "statement": {"type": "string", "description": "What the source says."},
            "value": {"type": "string", "description": "The value the source reports."},
            "observed_at": {"type": "string", "description": "When the source saw it."},
            "aspect": {"type": "string", "description": "Which aspect of the item it is about."},
        },
        "required": ["item_id", "statement"],
        "additionalProperties": False,
    }


TOOLS: list[dict[str, Any]] = [
    {
        "name": "submit_claims",
        "title": "Submit claims",
        "description": "Submit evidence claims about items. Claims only — a submission "
                       "carrying a verdict-shaped field is refused, because integrations "
                       "contribute claims and the verdict is computed from them.",
        "inputSchema": {
            "type": "object",
            "properties": {"claims": {"type": "array", "items": _claim_schema()}},
            "required": ["claims"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_verdict",
        "title": "Get the deterministic verdict",
        "description": "The deterministic verdict for one item, the claims grouped by "
                       "aspect, and a citation for every claim. Computed by "
                       "evidence.explain; this server calls no model.",
        "inputSchema": {
            "type": "object",
            "properties": {"item_id": {"type": "string"}},
            "required": ["item_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_disagreements",
        "title": "Get the disagreements",
        "description": "The lane verdicts for one item that disagree with the "
                       "deterministic verdict, or with each other, each cited.",
        "inputSchema": {
            "type": "object",
            "properties": {"item_id": {"type": "string"}},
            "required": ["item_id"],
            "additionalProperties": False,
        },
    },
]

TOOL_FUNCS = {
    "submit_claims": tool_submit_claims,
    "get_verdict": tool_get_verdict,
    "get_disagreements": tool_get_disagreements,
}


def handle(store: Store, request: dict[str, Any]) -> dict[str, Any] | None:
    """One JSON-RPC request in, one response out (None for a notification)."""
    method = request.get("method")
    rid = request.get("id")
    params = request.get("params") or {}

    if method == "initialize":
        requested = params.get("protocolVersion")
        if requested not in PROTOCOL_VERSIONS:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32602, "message": "Unsupported protocol version",
                              "data": {"supported": list(PROTOCOL_VERSIONS),
                                       "requested": requested}}}
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"protocolVersion": requested,
                           "capabilities": {"tools": {"listChanged": False}},
                           "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"resultType": "complete", "tools": TOOLS}}

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in TOOL_FUNCS:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32602, "message": f"Unknown tool: {name}"}}
        try:
            payload = TOOL_FUNCS[name](store, arguments)
        except SchemaError as exc:
            # A tool execution error: the model that made the call can read this
            # and try again. Not a protocol error.
            return {"jsonrpc": "2.0", "id": rid,
                    "result": {"resultType": "complete",
                               "content": [{"type": "text", "text": str(exc)}],
                               "isError": True}}
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"resultType": "complete",
                           "content": [{"type": "text",
                                        "text": json.dumps(payload, indent=2, sort_keys=True)}],
                           "structuredContent": payload,
                           "isError": False}}

    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}

    if rid is None:
        return None  # a notification: nothing to answer
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"Method not found: {method}"}}


def serve(store: Store, stdin=None, stdout=None) -> int:
    """MCP over stdio: one JSON request per line in, one JSON response per line out."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": f"Parse error: {exc}"}}
        else:
            response = handle(store, request)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--evidence", default=os.path.join(HERE, "evidence", "items.jsonl"),
                    help="the evidence JSONL to read at startup (read-only)")
    args = ap.parse_args(argv)
    store = Store(args.evidence)
    return serve(store)


if __name__ == "__main__":
    raise SystemExit(main())
