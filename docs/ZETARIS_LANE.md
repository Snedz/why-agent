# The Zetaris lane — status and first-live-run checklist

**Status (2026-10-28): adapter written and offline-tested; NOT yet run
against a live deployment.** `zetaris_lane.py` carries 7 offline tests
(envelope normalization, card-row skip, claim mapping, config errors) inside
the repo's 51-test suite. What a stub cannot verify is the deployment's real
REST envelope and query path — that is what the first live run below settles,
and until it happens, no document in this repository may describe Zetaris as
live. The Open Agent submission's wording (designed only) stays accurate
until this checklist completes.

## What the lane does

The evidence table lives in a Zetaris deployment. A SQL query runs against
it live; the returned rows pass through the repository's existing table path
(`evidence.evidence_from_rows()`) and become claims with their source and
locator intact. Zetaris contributes claims, never verdicts — the
deterministic reconciler still decides, and empty-value (non-match) rows are
preserved, not dropped.

## First live run

1. Deploy Zetaris Cloud (free single-node edition) via its CloudFormation
   template into the operator's own AWS account. There is no hosted SaaS;
   every edition runs on customer infrastructure.
2. In the Zetaris GUI, add the evidence export (CSV or JSON) as a file
   source and build a view over it (working name: `evidence_view`) with the
   columns `evidence_from_rows()` reads: item_id, kind, source, locator,
   statement, value, observed_at, aspect.
3. Run a SELECT in the GUI's SQL editor and confirm rows come back. This is
   the moment Zetaris is genuinely live; everything after is plumbing.
4. Confirm the REST endpoint against the deployment: base URL, the query
   path (`ZETARIS_QUERY_PATH`, adapter default `/query`), whether a bearer
   token is required, and which envelope the response uses. Adjust env vars
   only — the normalizer already tolerates the plausible envelopes; if the
   real one differs, extend `_normalize_rows()` and add the captured shape
   (redacted) as a test fixture.
5. Run the lane:
   `ZETARIS_BASE_URL=<deployment> python3 zetaris_lane.py --sql "SELECT * FROM evidence_view" --out evidence/zetaris-rows.jsonl`
   then reconcile the demo items and record the verdicts next to the
   local-file run: same rows, same verdicts is the expected result — the
   point is where the evidence lived when it was read.
6. Cost hygiene: the deployment idles at roughly $0.08–0.19/hr. Delete the
   CloudFormation stack when the work is done. (The AWS Marketplace
   "Zetaris LakeHouse" listing is a different, enterprise product at
   ~$6,132/mo — it is not this path and must never be subscribed to for it.)
