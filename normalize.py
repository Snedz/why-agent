"""Normalization: compare values the way a careful reader would.

Why this exists
---------------
The Tavily lane's first rule was verbatim appearance: a page supports a
claimed value only if the value literally appears in the page's text. That
rule is honest, and it stays the default. But a live run on 2026-10-30
measured its cost: over four of this repository's own planning claims,
verbatim matching credited 5 of 19 pages and flipped every verdict to
CONFLICTED — including claims that were true and officially documented.
The official page wrote "October 30" where our claim said "Oct 30". A
human reader calls that the same date. The string matcher cannot.

The opposite fix — fuzzy matching — is worse. A matcher that cannot say
WHY two strings count as the same value is a model opinion wearing a
deterministic costume, and this repository exists to refuse exactly that.

So this module is the middle path: a small set of canonicalizations, each
narrow enough to explain in one sentence, applied to BOTH the claimed
value and the page text before comparison.

  * dates    — month names and abbreviations, day-first or month-first,
               optional year, ISO form. "Oct 30", "October 30", "30 Oct"
               and "2026-10-30" canonicalize to the same (month, day).
  * numbers  — thousands separators and decimal trailing zeros are
               formatting, not value: "1,000" and "1000" and "1.50" and
               "1.5" canonicalize alike. On top of that, a token-sequence
               match tolerates ONE intervening non-numeric token between
               claim tokens, because "1,000 API credits" is how the web
               actually writes "1,000 credits".
  * phones   — digits only, with a leading country-code 1 dropped, so
               "+1 905-353-8889", "(905) 353-8889" and "905.353.8889"
               are the same number. One different digit is a different
               number; there is no near-match for phones.

Two conservative choices are load-bearing:

  * A claim that IS a date is certified only by the date rule, and a
    claim that IS a phone number only by the phone rule. Token adjacency
    never certifies them: a transcript that happens to place the word
    "November" near a stray "3" has not stated a November 3 deadline.
  * Every match reports its method — "verbatim", "normalized:date",
    "normalized:tokens", "normalized:number-gap", "normalized:phone" —
    or "none". A normalized match is a DIFFERENT, weaker kind of evidence
    than a verbatim one, and the label travels with the row so no reader
    has to guess which kind they are looking at.
"""
from __future__ import annotations

import dataclasses
import re
from decimal import Decimal, InvalidOperation

METHOD_NONE = "none"
METHOD_VERBATIM = "verbatim"


def contains_verbatim(claim: str, text: str) -> bool:
    """True when the claim appears in the text as a delimited string.

    "Verbatim" used to mean raw substring appearance, and that credited
    accidents: "November 3" is a substring of "November 30", and "1,000"
    of "10,000". A false credit is worse than a miss — it manufactures
    the very corroboration this module exists to check — so verbatim now
    requires the occurrence to be delimited on BOTH sides: the character
    immediately before the occurrence and the character immediately after
    it must not be alphanumeric (a letter or a digit, per str.isalnum),
    or the occurrence must run to the start or end of the text. The
    claim's interior is matched exactly as written (case-insensitively);
    only its two outer edges are boundary-checked, so a multi-word claim
    needs no delimiters between its own words, and a punctuation-bearing
    claim ("$25", "1:00 PM") is judged by the characters around the
    occurrence, whatever its own edge characters are. Punctuation in the
    text delimits: "(Oct 30)" and "close November 3, 2026" credit their
    claims, as does a hyphen ("Nemotron-based"). Any one delimited
    occurrence is enough.
    """
    if not claim or not text:
        return False
    folded_claim = claim.casefold()
    folded_text = text.casefold()
    start = 0
    while True:
        idx = folded_text.find(folded_claim, start)
        if idx < 0:
            return False
        end = idx + len(folded_claim)
        before_ok = idx == 0 or not folded_text[idx - 1].isalnum()
        after_ok = end == len(folded_text) or not folded_text[end].isalnum()
        if before_ok and after_ok:
            return True
        start = idx + 1


@dataclasses.dataclass(frozen=True)
class Match:
    """The outcome of comparing one claimed value against one page text.

    `method` names the rule that fired, or "none". `detail` carries the
    canonical form (or the skipped token) that explains the match — the
    audit trail a fuzzy matcher cannot produce.
    """

    method: str
    detail: str = ""

    @property
    def matched(self) -> bool:
        return self.method != METHOD_NONE


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_MONTH_NUMBER = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

_MONTH_ALT = (
    r"(?:january|jan\.?|february|feb\.?|march|mar\.?|april|apr\.?|may|"
    r"june|jun\.?|july|jul\.?|august|aug\.?|september|sept\.?|sep\.?|"
    r"october|oct\.?|november|nov\.?|december|dec\.?)"
)

_MONTH_FIRST = re.compile(
    rf"\b({_MONTH_ALT})\s+(\d{{1,2}})(?:st|nd|rd|th)?"
    rf"(?:\s*,?\s*(\d{{4}}))?",
    re.IGNORECASE,
)
_DAY_FIRST = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_ALT})"
    rf"(?:\s*,?\s*(\d{{4}}))?",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

_WEEKDAYS = {
    "mon", "monday", "tue", "tues", "tuesday", "wed", "wednesday",
    "thu", "thur", "thurs", "thursday", "fri", "friday",
    "sat", "saturday", "sun", "sunday",
}

# A canonical date: (month, day, year-or-None). The year is None when the
# text does not state one; an unstated year neither confirms nor
# contradicts a stated one, so agreement ignores it unless BOTH sides
# state a year and they differ.
CanonDate = tuple[int, int, "int | None"]


def _month_number(name: str) -> int:
    return _MONTH_NUMBER[name.lower().rstrip(".")]


def extract_dates(text: str) -> list[CanonDate]:
    """Every date expression in the text, canonicalized, in order found."""
    found: list[CanonDate] = []
    for m in _ISO_DATE.finditer(text):
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            found.append((month, day, year))
    for m in _MONTH_FIRST.finditer(text):
        month = _month_number(m.group(1))
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else None
        if 1 <= day <= 31:
            found.append((month, day, year))
    for m in _DAY_FIRST.finditer(text):
        day = int(m.group(1))
        month = _month_number(m.group(2))
        year = int(m.group(3)) if m.group(3) else None
        if 1 <= day <= 31:
            found.append((month, day, year))
    # The same expression can be found by two patterns; keep each once,
    # in the order the patterns above produced them.
    seen: set[CanonDate] = set()
    out: list[CanonDate] = []
    for d in found:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _dates_agree(a: CanonDate, b: CanonDate) -> bool:
    if a[0] != b[0] or a[1] != b[1]:
        return False
    if a[2] is not None and b[2] is not None and a[2] != b[2]:
        return False
    return True


def _date_detail(d: CanonDate) -> str:
    base = f"{d[0]:02d}-{d[1]:02d}"
    return f"{base}-{d[2]}" if d[2] is not None else base


def claim_is_date(claim: str) -> bool:
    """True when the claim is nothing but a date (plus a weekday, at most).

    "Oct 30" and "Tuesday November 3" qualify. "the deadline is Oct 30"
    does not — it is a sentence CONTAINING a date, and it falls through to
    the token rules, which is the weaker claim and gets the weaker rules.
    """
    if not extract_dates(claim):
        return False
    words = re.findall(r"[a-z]+", claim.lower())
    allowed = set(_MONTH_NUMBER) | _WEEKDAYS
    return all(w in allowed for w in words)


# ---------------------------------------------------------------------------
# Phones
# ---------------------------------------------------------------------------

# North-American shape: optional +1, area code optionally parenthesized,
# then 3 and 4 digits, separators space/dot/dash. The corpus this serves
# is Ontario numbers; a general international parser would be a bigger
# claim than this module wants to make.
_PHONE_RE = re.compile(
    r"\+?1?[\s.\-]?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}\b"
)


def canonical_phone(text: str) -> str | None:
    """The 10 digits of a North-American number, or None if there are none.

    A leading country-code 1 on an 11-digit number is dropped. Anything
    that is not exactly 10 digits after that is not a phone number this
    module will certify.
    """
    digits = re.sub(r"\D", "", text)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return digits
    return None


def claim_is_phone(claim: str) -> bool:
    """True when the claim is only a phone number and its punctuation."""
    if not re.fullmatch(r"[\d\s()+\-.]+", claim.strip()):
        return False
    return canonical_phone(claim) is not None


def phones_in(text: str) -> set[str]:
    """Every canonical phone number stated in the text."""
    out: set[str] = set()
    for m in _PHONE_RE.finditer(text):
        canon = canonical_phone(m.group(0))
        if canon is not None:
            out.add(canon)
    return out


# ---------------------------------------------------------------------------
# Tokens: numbers and number+unit phrases
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\d[\d,]*(?:\.\d+)?|[a-z]+")


def _canon_number(raw: str) -> str:
    """Canonicalize one numeric token: "1,000" -> "1000", "1.50" -> "1.5"."""
    try:
        value = Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return raw
    return format(value.normalize(), "f")


def _stem(word: str) -> str:
    """A plural 's' is formatting too: "credits" and "credit" are one token.

    Applied to both sides of every comparison, so it can only equate forms
    a reader would already read as the same word. Words of three letters
    or fewer, and words ending in a double 's', are left alone.
    """
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _tokenize(text: str) -> list[tuple[str, bool]]:
    """Normalized tokens as (value, is_number) pairs, in order."""
    out: list[tuple[str, bool]] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        if raw[0].isdigit():
            out.append((_canon_number(raw), True))
        else:
            out.append((_stem(raw), False))
    return out


def tokens(text: str) -> list[str]:
    """The normalized token values of a text, in order."""
    return [value for value, _ in _tokenize(text)]


def _contains_window(haystack: list[tuple[str, bool]],
                     needle: list[tuple[str, bool]]) -> bool:
    """True when the needle token sequence appears contiguously."""
    n = len(needle)
    if n == 0 or n > len(haystack):
        return False
    values = [v for v, _ in haystack]
    target = [v for v, _ in needle]
    return any(values[i:i + n] == target
               for i in range(len(values) - n + 1))


def _gap_match(haystack: list[tuple[str, bool]],
               needle: list[tuple[str, bool]]) -> str | None:
    """Match the needle allowing exactly one skipped non-numeric token.

    Returns the skipped token (the explanation), or None. The gap must sit
    BETWEEN two claim tokens — never before the first or after the last —
    and the skipped token may not be a number: skipping a number would let
    "1,000 credits" certify a page about 1,000 of something else entirely.
    """
    n = len(needle)
    if n < 2:
        return None
    for start in range(len(haystack)):
        if haystack[start][0] != needle[0][0]:
            continue
        i = start + 1          # position in haystack
        j = 1                  # position in needle
        skipped: str | None = None
        while j < n and i < len(haystack):
            if haystack[i][0] == needle[j][0]:
                i += 1
                j += 1
            elif skipped is None and not haystack[i][1]:
                skipped = haystack[i][0]
                i += 1
            else:
                break
        if j == n and skipped is not None:
            return skipped
    return None


# ---------------------------------------------------------------------------
# The comparison itself
# ---------------------------------------------------------------------------

def explain_match(claimed_value: str, text: str) -> Match:
    """Compare one claimed value against one page text, and say how it went.

    Rule order is deliberate, strongest first: verbatim appearance (the
    delimited-occurrence rule of `contains_verbatim`, not raw substring);
    then, for claims that are dates or phone numbers, ONLY their semantic
    rule; then contiguous normalized tokens; then the single-gap token
    match, reserved for claims that contain a number.
    """
    claim = (claimed_value or "").strip()
    if not claim or not text:
        return Match(METHOD_NONE)
    if contains_verbatim(claim, text):
        return Match(METHOD_VERBATIM, detail=claim)

    if claim_is_phone(claim):
        canon = canonical_phone(claim)
        if canon is not None and canon in phones_in(text):
            return Match("normalized:phone", detail=canon)
        return Match(METHOD_NONE)

    if claim_is_date(claim):
        text_dates = extract_dates(text)
        for claim_date in extract_dates(claim):
            for text_date in text_dates:
                if _dates_agree(claim_date, text_date):
                    return Match("normalized:date",
                                 detail=_date_detail(claim_date))
        return Match(METHOD_NONE)

    claim_tokens = _tokenize(claim)
    text_tokens = _tokenize(text)
    if claim_tokens and _contains_window(text_tokens, claim_tokens):
        return Match("normalized:tokens",
                     detail=" ".join(v for v, _ in claim_tokens))
    if any(is_number for _, is_number in claim_tokens):
        skipped = _gap_match(text_tokens, claim_tokens)
        if skipped is not None:
            return Match("normalized:number-gap",
                         detail=f"one intervening token: {skipped!r}")
    return Match(METHOD_NONE)
