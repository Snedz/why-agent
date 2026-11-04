"""A Zetaris evidence lane: claims served live from a Zetaris deployment.

Why this exists
---------------
`evidence.py` was designed with a filestore path from the start: claims read
out of a table, via `evidence_from_rows()`. Until now that path was only ever
exercised against local DuckDB files. This lane makes it real over the wire:
the evidence table lives in a Zetaris deployment (their networked data
platform), a SQL query runs against it live, and the returned rows become
claims exactly like any other source's.

The integration rule is the repository's standing one, and it does not bend
for a sponsor: Zetaris contributes CLAIMS, never verdicts. Rows arrive as
evidence with their source and locator intact; the deterministic reconciler
decides what they mean, and a value counts only when it is literally there
in the row. A row whose value is empty — an honest non-match recorded
upstream — is preserved as a claim with an empty value, never dropped and
never filled in.

Configuration is environment-only, like every other lane:

  ZETARIS_BASE_URL    base URL of the deployment's REST endpoint
                      (e.g. https://<host>:8888). Required; there is no
                      default, because there is no hosted Zetaris SaaS to
                      default to — every deployment runs on the operator's
                      own infrastructure.
  ZETARIS_QUERY_PATH  path the SQL is POSTed to. Default "/query". This
                      MUST be confirmed against the live deployment before
                      first use (see docs/ZETARIS_LANE.md): the adapter was
                      written and offline-tested before any deployment
                      existed to check against, and the exact REST envelope
                      is the one thing a stub cannot verify.
  ZETARIS_API_KEY     optional bearer token, only if the deployment
                      requires one. Never hardcoded, never written to a file
                      this module produces.

The response normalizer accepts the plausible result envelopes — a bare
list of row objects, or an object carrying `rows` / `results` / `data` as a
list of row objects, or a columnar `columns` + `rows` pair — because the
envelope is part of what the first live run verifies. Whatever the shape,
what reaches `evidence_from_rows()` is a list of plain dicts, and nothing
else in the repository needs to change.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Callable

from evidence import Evidence, evidence_from_rows

BASE_URL_ENV = "ZETARIS_BASE_URL"
QUERY_PATH_ENV = "ZETARIS_QUERY_PATH"
API_KEY_ENV = "ZETARIS_API_KEY"
DEFAULT_QUERY_PATH = "/query"
DEFAULT_TIMEOUT = 60

# A transport takes (url, payload, headers, timeout) and returns the decoded
# JSON body. Tests substitute a stub; production uses the urllib one below.
Transport = Callable[[str, dict[str, Any], dict[str, str], int], Any]


class ZetarisError(RuntimeError):
    """The Zetaris lane could not run."""


class ZetarisConfigError(ZetarisError):
    """The lane is not configured (no deployment to talk to)."""


def _base_url() -> str:
    url = os.environ.get(BASE_URL_ENV, "").strip().rstrip("/")
    if not url:
        raise ZetarisConfigError(
            f"{BASE_URL_ENV} is not set; the Zetaris lane needs the base URL "
            "of a live deployment and will not guess one"
        )
    return url


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = os.environ.get(API_KEY_ENV, "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str],
               timeout: int) -> Any:
    """POST JSON and decode the JSON body. The only socket in this module."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise ZetarisError(f"Zetaris query returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ZetarisError("Zetaris endpoint unreachable") from exc
    except OSError as exc:
        raise ZetarisError("Zetaris endpoint unreachable") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ZetarisError("Zetaris query returned malformed JSON") from exc


def _normalize_rows(body: Any) -> list[dict[str, Any]]:
    """Reduce a response envelope to a list of row dicts.

    Accepts a bare list, an object with a `rows` / `results` / `data` list,
    or a columnar `columns` + `rows` pair. Anything else is an error the
    caller must see, not a silent empty result — an empty evidence set and
    an unparseable one are very different claims about the world.
    """
    if isinstance(body, list):
        rows = body
    elif isinstance(body, dict):
        # Columnar first: it also uses the key "rows", but for value lists.
        if isinstance(body.get("columns"), list) \
                and isinstance(body.get("rows"), list) \
                and all(isinstance(r, (list, tuple)) for r in body["rows"]):
            columns = [str(c) for c in body["columns"]]
            return [dict(zip(columns, r)) for r in body["rows"]]
        rows = None
        for key in ("rows", "results", "data"):
            if isinstance(body.get(key), list):
                rows = body[key]
                break
        if rows is None:
            raise ZetarisError(
                "Zetaris response carried no row list under "
                "rows/results/data and no columns+rows pair")
    else:
        raise ZetarisError("Zetaris response is not a list or an object")
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ZetarisError("Zetaris returned a row that is not an object")
        out.append(row)
    return out


def run_query(sql: str, *,
              transport: Transport | None = None,
              timeout: int = DEFAULT_TIMEOUT) -> list[dict[str, Any]]:
    """Run one SQL query against the deployment; return raw row dicts.

    The rows are returned uninterpreted: turning rows into claims is
    `rows_to_evidence`'s job, and a caller that only queries has asserted
    nothing yet.
    """
    path = os.environ.get(QUERY_PATH_ENV, DEFAULT_QUERY_PATH).strip()
    if not path.startswith("/"):
        path = "/" + path
    url = _base_url() + path
    send = transport if transport is not None else _post_json
    body = send(url, {"sql": sql}, _headers(), timeout)
    return _normalize_rows(body)


def rows_to_evidence(rows: list[dict[str, Any]]) -> list[Evidence]:
    """Turn Zetaris rows into claims via the repository's table path.

    Delegates to `evidence_from_rows()` unchanged: card rows are skipped,
    every other row becomes a claim with its own source and locator. Rows
    are NOT re-stamped — where a claim came from is part of the claim.
    """
    return evidence_from_rows(rows)


def fetch_evidence(sql: str, *,
                   transport: Transport | None = None,
                   timeout: int = DEFAULT_TIMEOUT) -> list[Evidence]:
    """Query Zetaris and return the rows as claims, in one call."""
    return rows_to_evidence(run_query(sql, transport=transport,
                                      timeout=timeout))


def main(argv: list[str] | None = None) -> int:
    """CLI: run a query against live Zetaris and append the claim rows.

Usage:
        ZETARIS_BASE_URL=https://<host>:8888 \\
          python3 zetaris_lane.py --sql \"SELECT * FROM evidence_view\" \\
          --out evidence/zetaris-rows.jsonl
    """
    ap = argparse.ArgumentParser(description="Zetaris live-evidence lane")
    ap.add_argument("--sql", required=True, help="SQL to run against the deployment")
    ap.add_argument("--out", required=True, help="JSONL file to append rows to")
    args = ap.parse_args(argv)

    try:
        claims = fetch_evidence(args.sql)
    except ZetarisError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    with open(args.out, "a", encoding="utf-8") as fh:
        for row in claims:
            fh.write(json.dumps(dataclasses.asdict(row)) + "\n")
    print(f"{len(claims)} claim row(s) appended to {args.out} "
          f"(queried {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%dT%H:%M:%SZ})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
