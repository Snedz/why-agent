# Claim Court corpus — sources and honesty labels

`cases.jsonl` holds 18 claim items in the repository's evidence format
(see `evidence.py`). The deterministic reconciler computes every verdict;
`truth.json` records what it computed when the corpus was frozen, and
`score.py` fails if the two ever drift apart.

## The split: 7 recorded, 11 synthetic

**Recorded items (`cc-shenail-*`)** state facts fetched from public pages on
2026-10-30 (04:36–04:37 UTC) about one real business: Shenail Hair Salon &
Nail Bar, Niagara Falls — the SiteBefore pilot client, our own family's
business. Every row names its artefact in `locator`:

- the salon's own site — https://shenailhairlounge.ca/ and
  https://shenailhairlounge.ca/hair/ (hours, phone, address, the "premiere"
  line, the 2007 line, the `Shenail-20-Off.png` promo asset)
- the Google places record (place_id 942693713797309): hours, phone,
  address, rating 4.1 from 28 reviews
- Birdeye — https://reviews.birdeye.com/shenail-hair-lounge-170031239435949
  (rating 4.5 from 251 reviews; the profile states it is not claimed by the
  business owner)
- Fresha —
  https://www.fresha.com/a/she-nail-hair-lounge-niagara-falls-8043-lundys-lane-dccczyh5
  (a different phone number, the same address)
- Yellow Pages —
  https://www.yellowpages.ca/bus/Ontario/Niagara-Falls/Shenail-Hair-Lounge/6656388.html
  (longer hours than the site shows, the same address)
- BestProsInTown —
  https://www.bestprosintown.com/on/niagara-falls/shenail-hair-lounge-/
  (rating 4.7 from 110 reviews)

The conflicts in these items are real: the directories genuinely disagree
with the salon's own site and with each other. Nothing was edited to make a
verdict come out — where sources agree (the address), the rows say so, and
the verdict is the honest PARTIAL the gate returns when no source speaks to
cause.

Two own-property sources could **not** be used, and the corpus says so
rather than working around it:

- `sitebefore.com` did not resolve from this network at build time
  (2026-10-30 fetch failed), so no SiteBefore site copy is quoted.
- BeforeChristmas's Etsy listing copy lives in Printify/Etsy, not in this
  workspace; no listing text could be sourced verbatim, so no
  BeforeChristmas item is included. The synthetic fixtures cover the
  listing patterns instead.

**Synthetic items (`cc-syn-*`)** are planted fixtures modelled on real
listing patterns (a "100% handmade" machine-printed mug, a was/now price
with no history at the higher price, a booking price that drifted from the
price list). Every synthetic row carries `"fixture": "synthetic"`, every
synthetic source name says so, and every synthetic item title begins
"SYNTHETIC FIXTURE". No synthetic row names or depicts a real third-party
seller — the court points at our own pilot business and at invented
listings, never at a stranger's shop.

## Aspect mapping for commerce

The kernel's aspects are properties of the item, and commerce claims map
onto them like this:

- **state** — what the item *is*: the assertion as published, and anything
  that directly tests the same assertion (a photo read of the same product,
  the same business's policy page, a directory's hours for the same shop).
  Two different values on state are a contradiction, stated as one.
- **outcome** — what independent records show a customer gets: aggregator
  ratings, supplier documents, the booking listing itself.
- **cause** — documentation that explains or certifies: an unclaimed-profile
  note that explains stale directory data, an invoice that matches a
  listing's materials.

A verdict of CORROBORATED therefore means: the claim, the independent
record, and the documentation all speak and none disagree. Most marketing
claims cannot say that, and the corpus shows the gate saying so — 12
CONFLICTED, 5 PARTIAL, 1 CORROBORATED out of 18, computed, not arranged:
the rows were written from the sources first and the verdicts read off the
reconciler afterwards.

## What is NOT in this corpus

No model lane has run over these items yet: there is no NEBIUS_API_KEY on
the build machine (see RUN_PACK.md). The gate verdicts above are
deterministic and were computed tonight; the reviewer-lane verdicts join
them when the live pipeline runs, and the Case Lab labels will say which
is which. Nothing in this directory quotes a lane verdict that does not
exist.
