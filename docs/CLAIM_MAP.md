# Claim-to-evidence map

Every claim this submission makes, and the artefact that proves it. A row
whose proof is a document rather than a runtime receipt does not belong
here and was cut. Reproduce any row by running its command in this repo.

| Claim | Proof (runtime receipt) |
|---|---|
| Narration runs on Nebius Token Factory, Nemotron 3 Super | `smoke.py` output, 2026-10-28: all tiers answered via `https://api.tokenfactory.nebius.com/v1/`; model pinned `nvidia/nemotron-3-super-120b-a12b` in `providers.py` |
| The checker catches values the evidence does not support | `eval-results-2026-10-28.json`: narration on why-alpha FAILED with unsupported values listed; analysis in `docs/NARRATION_CHECK_ANALYSIS_2026-10-28.md` |
| Reviewer tiers disagree and the disagreement is preserved | Same eval file: why-alpha fast=PARTIAL vs deep=CONFLICTED; reconciliation over the appended rows cites `nemotron-fast` and `nemotron-deep` as sources |
| The deterministic gate out-ranks the lanes | Benchmark run: both lanes over-approved why-beta against the reconciler's PARTIAL; `benchmark/score.py` scores lanes separately from the gate |
| Zero false approvals on the adversarial corpus | `python3 benchmark/score.py` → deterministic 14/14. With `--eval-results benchmark/eval-benchmark-2026-10-28.json`: lanes Ultra 9/14 (1 false approval), Nano 6/14 (2 false approvals) — full table in `docs/BENCHMARK_RESULTS_2026-10-28.md` |
| Tavily counts a page only on literal appearance | `tavily_lane.py` `results_to_evidence()` + `test_tavily_lane.py` (non-match yields an empty-value row); corpus case `bm-web-nonmatch` |
| A forged aspect cannot change a verdict | Corpus cases `bm-unexpected-aspect`, `bm-forged-aspect`; `evidence.reconcile()` routes unknown aspects to `unexpected`, cited and ignored |
| VL extraction becomes claims, never verdicts | `vision_lane.py` (null fields produce no rows; non-JSON raises); corpus case `bm-vl-receipt`; live probe 2026-10-28 read a report screenshot's verdict + reason in ~5s |
| The harness survives cold model loads and caps spend | `batch_eval.py` retry-with-backoff + `--budget` skip marking; 2026-10-28 cold-load stall (~3 min) recorded in the run notes |
| Costs are measured, not estimated from marketing | Per-lane token counts and USD in `eval-results-2026-10-28.json` (4 items, $0.0071 total) and the benchmark eval file; prices labelled as a dated snapshot in `review.py` |
| A client can ask the agent for its verdict over MCP | `mcp_server.py` (three tools; the server calls no model — a test forbids it) and `test_mcp_server.py`: the repo's synthetic why-alpha claims go in, CONFLICTED with a citation per claim comes out, and a verdict-shaped submission is refused at the boundary. Receipt: the test run — `python3 -m pytest -q test_mcp_server.py` |
| What pre-existed vs what is new | Git history: Open Agent build through commit `5bafca2`; Nebius build commit `b62c3ed8` (2026-10-28) adds providers, reviewer lanes, Tavily lane, vision lane, batch eval, benchmark |
