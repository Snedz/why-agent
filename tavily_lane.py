"""A live-evidence lane: check a claim against the web, via Tavily.

Why this exists
---------------
Every other source in `evidence.py` is a local artefact — a card, a receipt, a
commit, a check run. Some claims are not about local artefacts at all: "the
deadline is Oct 30", "the price is $25", "the model is available". For those,
the honest move is to go and look, and to record what the looking found as
evidence like any other — a claim by a source, with a citation a reader can
check.

Two guards make web results safe to treat as evidence, and both are
deliberate:

  * A page only supports a claimed value if the value LITERALLY APPEARS in
    the page's text (case-insensitive), as a delimited occurrence: the
    characters immediately around it must not be letters or digits (see
    `normalize.contains_verbatim` for the precise rule). Raw substring
    appearance is not enough — "November 3" sits inside "November 30"
    without the page stating a November 3 anything, and crediting that
    would manufacture corroboration. A search engine's ranking is an
    opinion about relevance, not a verification; the deterministic gate is
    the same one `narrate.py` applies to prose — a value counts when it is
    there to be pointed at, not when a model says it is implied.
  * Tavily's own generated `answer` is NEVER evidence. It is a model's
    summary of the pages, which is exactly the kind of uncheckable assertion
    this repository exists to catch. Only the pages themselves are claims;
    the answer field is not even requested (`include_answer` is False).

A result whose page does not contain the claimed value is not dropped. It
becomes a row with an empty value and a statement saying the value was not
found there — an honest non-match, which reconciliation then treats as its
own claim about the item's state. Silence would be easier to fake than a
recorded miss.

A second, optional match mode (`normalize_matches=True`) softens the
literal rule with the canonicalizations in `normalize.py` — dates written
"October 30" for a claim of "Oct 30", "1,000 API credits" for a claim of
"1,000 credits". It exists because a live run on 2026-10-30 showed the
verbatim rule crediting only 5 of 19 pages on claims that were mostly
true. It is OFF by default, and it is never silent: every row records its
`match_method` ("verbatim", "normalized:<rule>", or "none"), a normalized
hit says so in its statement, and a normalized match is labelled as the
weaker evidence it is wherever rows are counted.

The API key comes from the TAVILY_API_KEY environment variable and nowhere
else: never hardcoded, never in a file this module writes.
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

import normalize
from evidence import Evidence

SEARCH_URL = "https://api.tavily.com/search"
API_KEY_ENV = "TAVILY_API_KEY"
DEFAULT_TIMEOUT = 60

# A transport takes (url, payload, timeout) and returns the decoded JSON body.
# Tests substitute a stub; production uses the urllib one below. Keeping the
# socket behind this seam is what lets the lane be tested offline, like every
# other part of this repository.
Transport = Callable[[str, dict[str, Any], int], dict[str, Any]]


class TavilyError(RuntimeError):
    """The Tavily lane could not run."""


class TavilyKeyError(TavilyError):
    """No API key was available in the environment."""


def _require_api_key() -> str:
    """The key, from the environment only. Missing is an error, not a default."""
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        raise TavilyKeyError(
            f"{API_KEY_ENV} is not set; the Tavily lane needs an API key in "
            "the environment and will not run without one"
        )
    return key


def _post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    """POST JSON and decode the JSON body. The only socket in this module."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise TavilyError(f"Tavily search returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise TavilyError("Tavily search endpoint unreachable") from exc
    except OSError as exc:
        raise TavilyError("Tavily search endpoint unreachable") from exc
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TavilyError("Tavily search returned malformed JSON") from exc
    if not isinstance(body, dict):
        raise TavilyError("Tavily search returned a response that is not an object")
    return body


def search_claims(query: str, max_results: int = 5, *,
                  transport: Transport | None = None,
                  timeout: int = DEFAULT_TIMEOUT) -> list[dict]:
    """Search Tavily for pages bearing on a claim; return the raw results.

    The results are returned uninterpreted: turning a page into a claim is
    `results_to_evidence`'s job, and the separation matters — a caller that
    only searches has asserted nothing yet.
    """
    payload = {
        "api_key": _require_api_key(),
        "query": query,
        "search_depth": "advanced",
        "include_answer": False,
        "max_results": max_results,
    }
    send = transport if transport is not None else _post_json
    body = send(SEARCH_URL, payload, timeout)
    results = body.get("results", [])
    if not isinstance(results, list):
        raise TavilyError("Tavily search returned results that are not a list")
    return results


def results_to_evidence(item_id: str, results: list[dict], claimed_value: str,
                        retrieved_at: str, *,
                        normalize_matches: bool = False) -> list[Evidence]:
    """Turn Tavily results into claims about an item.

    A row carries the claimed value ONLY if that value literally appears in
    the page's content as a delimited occurrence (case-insensitive; the
    boundary rule is `normalize.contains_verbatim`). Otherwise the row's
    value is empty and its statement says the value was not found on the
    page — a recorded non-match, not a silent omission.

    With `normalize_matches=True`, a page whose text states the same value
    in a different written form also carries it — see `normalize.py` for the
    rules. Those rows are labelled twice: `match_method` records the rule
    that fired, and the statement says the match was normalized, so the
    weaker evidence never masquerades as the stronger kind.
    """
    rows: list[Evidence] = []
    for result in results:
        url = str(result.get("url", "") or "")
        title = str(result.get("title", "") or "").strip()
        content = str(result.get("content", "") or "")
        # What the row says the page is: its title when it has one, else the
        # start of its text. Never Tavily's generated answer — see the module
        # docstring.
        base = title or content[:200]
        if claimed_value and normalize.contains_verbatim(claimed_value,
                                                         content):
            statement = base
            value = claimed_value
            method = normalize.METHOD_VERBATIM
        elif normalize_matches:
            match = normalize.explain_match(claimed_value, content)
            if match.matched:
                statement = (
                    f"{base} — claimed value matched by {match.method}"
                    f" ({match.detail})"
                    if base else
                    f"claimed value matched by {match.method}"
                    f" ({match.detail})"
                )
                value = claimed_value
                method = match.method
            else:
                statement = (
                    f"claimed value {claimed_value!r} not found on this page: {base}"
                    if base else
                    f"claimed value {claimed_value!r} not found on this page"
                )
                value = ""
                method = normalize.METHOD_NONE
        else:
            statement = (
                f"claimed value {claimed_value!r} not found on this page: {base}"
                if base else
                f"claimed value {claimed_value!r} not found on this page"
            )
            value = ""
            method = normalize.METHOD_NONE
        rows.append(Evidence(
            item_id=item_id,
            kind="web",
            source="tavily",
            locator=url,
            statement=statement,
            value=value,
            observed_at=retrieved_at,
            match_method=method,
        ))
    return rows


def main(argv: list[str] | None = None) -> int:
    """CLI: check one claim against the live web and append the rows.

    Usage:
      TAVILY_API_KEY=... python tavily_lane.py --item why-alpha \
          --query "alpha release notes shipped" --claim "shipped" \
          --out evidence/web-rows.jsonl
    """
    ap = argparse.ArgumentParser(description="Tavily live-evidence lane")
    ap.add_argument("--item", required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--claim", required=True,
                    help="the claimed value; a page counts only if it appears verbatim")
    ap.add_argument("--out", required=True, help="JSONL file to append rows to")
    ap.add_argument("--max-results", type=int, default=5)
    ap.add_argument("--normalize", action="store_true",
                    help="also credit pages that state the same value in a "
                         "different written form (normalize.py); those rows "
                         "are labelled with their match_method")
    args = ap.parse_args(argv)

    try:
        results = search_claims(args.query, max_results=args.max_results)
    except TavilyError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    retrieved_at = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    rows = results_to_evidence(args.item, results, args.claim, retrieved_at,
                               normalize_matches=args.normalize)
    with open(args.out, "a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dataclasses.asdict(row)) + "\n")
    matched = sum(1 for r in rows if r.value)
    if args.normalize:
        verbatim = sum(1 for r in rows
                       if r.match_method == normalize.METHOD_VERBATIM)
        normalized = matched - verbatim
        print(f"{len(rows)} web row(s) appended to {args.out}; "
              f"{matched} page(s) contained the claimed value "
              f"({verbatim} verbatim, {normalized} normalized)")
    else:
        print(f"{len(rows)} web row(s) appended to {args.out}; "
              f"{matched} page(s) contained the claimed value verbatim")
    return 0


if __name__ == "__main__":
    sys.exit(main())
