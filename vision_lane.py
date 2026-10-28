"""A vision evidence lane: read a receipt or screenshot, via Nemotron VL.

Why this exists
---------------
Some evidence is a picture: a payment receipt, a dashboard screenshot, a
photo of a delivery slip. The other lanes read text artefacts — cards,
commits, check runs, web pages. This lane is how an image becomes evidence
in the same shape as everything else: `Evidence` rows of kind "receipt",
cited to the image and to the model that read it, which reconciliation
then treats like any other source's claims.

The model here is a READER, not a judge, and the module is written so it
cannot drift into being one:

  * The extraction is a CLAIM, never a verdict. The lane writes rows; the
    deterministic reconciler in `evidence.py` decides what they mean,
    exactly as it does for a card or a commit. A status word the model
    reads off the image becomes a row's value as the literal string the
    model returned — the lane does not normalise it, translate it, or
    agree with it.
  * Absence is not a claim. A field the model returns as null (or does
    not return at all) produces NO row. A receipt that shows no date has
    not claimed anything about dates, and inventing an empty-value row
    would let silence masquerade as a statement — the same reason the
    Tavily lane records a non-match explicitly instead of guessing.
  * Unparseable output is an error, never material. If the model's reply
    is not the JSON object the prompt demanded, this module raises
    `VisionLaneError` and produces nothing. Scraping numbers out of
    prose with a regex would fabricate the appearance of an extraction
    the model never actually made.

Row design (deliberately small):

  * amount → one row, value = the amount string, statement "receipt
    shows amount X". The counterparty is a detail about the source, not
    a claim about the item, so it rides on this row's statement ("...
    from Y") instead of getting a row of its own; with no amount there
    is nothing for it to attach to, and it produces no row.
  * date → one row, value = the date string as shown.
  * status_word → one row, value = the literal word, statement = the
    model's one-sentence summary of the image (or "receipt shows status
    X" when no summary came back). A summary with no status word states
    no checkable value, so it produces no row either.
  * No row sets an aspect: receipt rows take `DEFAULT_ASPECT` ("outcome")
    like every other receipt source.

The API key comes from the provider profile (`providers.resolve`), which
reads it from the environment and nowhere else: never hardcoded, never
in a file this module writes.
"""
from __future__ import annotations

import base64
import datetime
import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable

import providers
from evidence import Evidence

PROVIDER_NAME = "nebius"
SOURCE = "nemotron-vl"
KIND = "receipt"
DEFAULT_TIMEOUT = 180

# A transport takes (base_url, api_key, payload) and returns the decoded
# chat-completion body. Tests substitute a stub; production uses the
# urllib one below. Keeping the socket behind this seam is what lets the
# lane be tested offline, like every other part of this repository.
Transport = Callable[[str, str, dict[str, Any]], dict[str, Any]]

_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

# JSON only, and null over invention: the model's easiest failure mode is
# helpfully filling in a field the image does not show, so the prompt
# makes "not visible" an explicit, respectable answer for every field.
PROMPT = (
    "You are reading a receipt or screenshot image as evidence. Extract "
    "only what is visibly shown in the image; never infer a value that "
    "is not there.\n\n"
    "Respond with ONLY a JSON object and no other text, with exactly "
    "these keys:\n"
    '  "amount": the total amount shown, as the literal string shown '
    "(including any currency symbol), or null\n"
    '  "date": the date shown, as the literal string shown, or null\n'
    '  "counterparty": the name of the business or person the receipt '
    "is from, or null\n"
    '  "status_word": a single status or verdict word shown in the '
    "image (for example PAID, DONE, FAILED), exactly as shown, or null\n"
    '  "summary": one sentence describing what the image shows, or null\n'
    "If a field is not visible in the image, its value must be null."
)


class VisionLaneError(RuntimeError):
    """The vision lane could not produce a trustworthy extraction."""


def _post_chat(base_url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST to {base}/chat/completions; return the decoded body.

    The only socket in this module. The 180 s default timeout is not
    paranoia: a cold vision model can take minutes to load, and a short
    timeout reads as a false outage.
    """
    url = base_url.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:  # noqa: S310
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise VisionLaneError(f"vision endpoint returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise VisionLaneError("vision endpoint unreachable") from exc
    except OSError as exc:
        raise VisionLaneError("vision endpoint unreachable") from exc
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VisionLaneError("vision endpoint returned malformed JSON") from exc
    if not isinstance(body, dict):
        raise VisionLaneError("vision endpoint returned a response that is not an object")
    return body


def _completion_text(body: dict[str, Any]) -> str:
    """Pull the assistant string out of a chat-completion body, or raise."""
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise VisionLaneError(
            "vision endpoint returned a response that is not a chat completion"
        ) from exc
    if not isinstance(content, str):
        raise VisionLaneError(
            "vision endpoint returned a response that is not a chat completion"
        )
    return content


def _strip_fences(text: str) -> str:
    """Remove a Markdown code fence, if the model wrapped its JSON in one.

    A fence is packaging, not content, so unwrapping it is safe. Anything
    else around the JSON — prose before or after — is NOT stripped: the
    prompt demanded JSON only, and quietly hunting for an object inside
    prose would let the lane pretend an extraction happened when the
    model never committed to one.
    """
    text = text.strip()
    if not text.startswith("```"):
        return text
    text = text[3:].lstrip()
    if text.lower().startswith("json"):
        text = text[4:].lstrip()
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _parse_extraction(content: str) -> dict[str, Any]:
    """Parse the model's reply as the extraction object, or raise.

    Not valid JSON means no extraction: the caller gets an error, never
    a best-effort row set assembled from fragments of prose.
    """
    try:
        parsed = json.loads(_strip_fences(content))
    except json.JSONDecodeError as exc:
        raise VisionLaneError(
            "vision model did not return the JSON extraction it was asked for"
        ) from exc
    if not isinstance(parsed, dict):
        raise VisionLaneError("vision model returned JSON that is not an object")
    return parsed


def _field_text(extraction: dict[str, Any], key: str) -> str | None:
    """One extraction field as text, or None when the model reported absence.

    Null, missing, and empty-after-trimming all mean "not shown", and
    "not shown" produces no row. A field of any other shape (an object, a
    list, a boolean) means the model did not follow the extraction
    contract, which is an error rather than something to coerce quietly.
    """
    value = extraction.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise VisionLaneError(
            f"vision extraction field {key!r} is not a string or number: {value!r}"
        )
    text = str(value).strip()
    return text or None


def _image_data_uri(image_path: str) -> str:
    """Read an image file and encode it as a data URI for the request."""
    ext = os.path.splitext(image_path)[1].lower()
    mime = _MIME_BY_EXT.get(ext, "image/png")
    with open(image_path, "rb") as fh:
        encoded = base64.b64encode(fh.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _extraction_to_evidence(item_id: str, extraction: dict[str, Any], *,
                            locator: str, observed_at: str) -> list[Evidence]:
    """Turn one extraction into claims. See the module docstring for the
    row design; the short version is one row per PRESENT field, with the
    counterparty riding on the amount row's statement."""
    rows: list[Evidence] = []

    def row(statement: str, value: str) -> Evidence:
        return Evidence(
            item_id=item_id,
            kind=KIND,
            source=SOURCE,
            locator=locator,
            statement=statement,
            value=value,
            observed_at=observed_at,
        )

    amount = _field_text(extraction, "amount")
    if amount is not None:
        statement = f"receipt shows amount {amount}"
        counterparty = _field_text(extraction, "counterparty")
        if counterparty is not None:
            statement += f" from {counterparty}"
        rows.append(row(statement, amount))

    date = _field_text(extraction, "date")
    if date is not None:
        rows.append(row(f"receipt is dated {date}", date))

    status_word = _field_text(extraction, "status_word")
    if status_word is not None:
        summary = _field_text(extraction, "summary")
        statement = summary if summary is not None else f"receipt shows status {status_word}"
        rows.append(row(statement, status_word))

    return rows


def extract_receipt_claims(image_path: str, item_id: str,
                           observed_at: str | None = None,
                           environ: Any = None,
                           transport: Transport | None = None) -> list[Evidence]:
    """Read a receipt/screenshot image and return its claims about an item.

    The provider profile is resolved first, so a missing API key raises
    (`providers.ProviderError`) before any file is read or any request is
    sent. `observed_at` defaults to the current UTC time; tests and
    replays pass it explicitly so their rows carry the moment they mean.
    """
    prof = providers.resolve(PROVIDER_NAME, environ)
    model_id = prof["models"]["vision"]
    payload = {
        "model": model_id,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url",
                 "image_url": {"url": _image_data_uri(image_path)}},
            ],
        }],
        # A reasoning vision model spends tokens thinking before it
        # answers; a small cap reads as an empty reply, not a cheap one.
        "max_tokens": 4096,
        "temperature": 0,
    }
    send = transport if transport is not None else _post_chat
    body = send(prof["base_url"], prof["api_key"], payload)
    extraction = _parse_extraction(_completion_text(body))
    stamp = observed_at or datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return _extraction_to_evidence(
        item_id,
        extraction,
        locator=f"{image_path} via {model_id}",
        observed_at=stamp,
    )
