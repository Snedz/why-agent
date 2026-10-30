"""Nemotron Court: the reviewer tiers cross-examined, the gate presiding.

why-agent's lanes have always been advisory: each tier reads the claims and
returns a verdict, and the deterministic reconciler decides. The Court is
the round the demo never had — the tiers are made to ANSWER for their
verdicts. Two layers, and they are labelled differently because they are
different kinds of thing:

  * Citation audit (deterministic, always available). For every lane
    verdict, code — not a model — lists the evidence that verdict fails to
    account for: the conflicting rows a CORROBORATED drove past, the
    aspects a PARTIAL claims are missing when none are, the rows a
    NO EVIDENCE pretends do not exist. A verdict that matches the gate and
    answers everything is "supported". Anything else is preserved, cited,
    and never averaged into agreement.

  * Cross-examination (live, needs a provider key). Each tier is shown the
    claims and every Round 1 verdict, and must answer in a strict shape:
    a POSITION, the CITES it relies on, and a REBUT line per opposing lane
    naming the citation it challenges and why. Unparseable answers are
    recorded as UNPARSEABLE, never coerced. The gate does not move: the
    reconciler's verdict is the verdict before, during, and after the
    argument. The Court produces a transcript, not a decision.

Modes:

  python3 court.py --replay [--out court/debate-replay.json]
      Offline. Round 1 is the RECORDED 2026-10-28 benchmark run
      (benchmark/eval-benchmark-2026-10-28.json); the citation audit is
      computed tonight from the committed corpus. The rebuttal round is
      marked NOT RUN, with the reason, because no key is present — a
      transcript that invented rebuttals would be a narration that fails
      its own check.

  NEBIUS_API_KEY=... python3 court.py --live \
      [--evidence claimcourt/cases.jsonl] [--budget 0.50] \
      [--out court/debate-live.json]
      Round 1 runs the tiers now; the cross-examination round runs on
      every contested item (a tier disagrees with the gate, or the tiers
      disagree with each other). Works over any evidence file in the
      repository's format, the benchmark corpus included.

The reviewer call reuses review.py's chat/parse/price helpers by import —
the same deliberate coupling as batch_eval.py. The reconciler imports
neither, so the kernel stays clean if the Court is deleted.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence as ev  # noqa: E402
import providers  # noqa: E402
import review  # noqa: E402

HERE = Path(__file__).resolve().parent
BENCH_CASES = HERE / "benchmark" / "cases.jsonl"
BENCH_TRUTH = HERE / "benchmark" / "truth.json"
BENCH_EVAL = HERE / "benchmark" / "eval-benchmark-2026-10-28.json"

TIER_LANE = {"fast": "nemotron-fast", "deep": "nemotron-deep"}
EXHIBIT_LANES = {"tavily": "live-evidence", "nemotron-vl": "vision"}

CROSS_EXAM_PROMPT = """You are the {tier} reviewer lane ({model}) in a cross-examination round. In Round 1 every lane judged the same claims; the verdicts are listed below. Defend or revise your position using ONLY the claims listed. The deterministic gate's verdict is also listed — it is not a lane and cannot be rebutted, but your citations should answer the conflicts and missing aspects it found.

Answer in exactly this shape, nothing else:
POSITION: <one of CORROBORATED, PARTIAL, CONFLICTED, NO EVIDENCE>
CITES: <semicolon-separated citations you rely on, each written as: source — locator>
REBUT <lane>: <one sentence naming the citation you challenge and why it does not carry their verdict>
(One REBUT line per opposing lane you challenge; omit REBUT lines entirely if you challenge none.)

Item: {title} ({item_id})
Claims:
{claims}

Round 1:
{round1}
Deterministic gate: {gate}
"""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            rows.append(json.loads(line))
    return rows


def _as_evidence(rows: list[dict]) -> list[ev.Evidence]:
    return [
        ev.Evidence(
            item_id=r["item_id"], kind=r.get("kind") or "card",
            source=r.get("source") or r.get("kind") or "card",
            locator=r.get("locator", ""), statement=r.get("statement", ""),
            value=r.get("value", ""), observed_at=r.get("observed_at", ""),
            aspect=r.get("aspect", ""),
        )
        for r in rows
    ]


def gate_view(item_id: str, rows: list[dict]) -> dict:
    """The gate's ruling, with the citations it rests on."""
    rec = ev.reconcile(ev.Item(item_id=item_id), _as_evidence(rows))
    return {
        "verdict": rec.confidence(),
        "conflicts": [
            {"aspect": aspect,
             "values": sorted({c.value for c in group}),
             "citations": [c.citation() for c in group]}
            for aspect, group in rec.conflicts
        ],
        "agreements": [
            {"aspect": aspect, "value": group[0].value,
             "citations": [c.citation() for c in group]}
            for aspect, group in rec.agreements
        ],
        "unknown_aspects": rec.unknown_aspects,
    }


def citation_audit(verdict: str, gate: dict) -> dict:
    """What a lane verdict fails to account for — computed, never narrated.

    The rules are structural, and they are the whole audit:
      * CORROBORATED must answer every conflict and every missing aspect.
      * CONFLICTED must point at a conflict that exists.
      * PARTIAL claims something is missing or unresolved; if nothing is
        missing and nothing conflicts, the agreements are what it must
        answer.
      * NO EVIDENCE is answered by the rows themselves when rows exist.
    A verdict equal to the gate's, with nothing unanswered, is supported.
    """
    unanswered = []
    conflicts = gate["conflicts"]
    missing = gate["unknown_aspects"]
    agreements = gate["agreements"]
    if verdict == "CORROBORATED":
        for c in conflicts:
            unanswered.append({"kind": "conflict", "aspect": c["aspect"],
                               "citations": c["citations"]})
        for aspect in missing:
            unanswered.append({"kind": "missing", "aspect": aspect,
                               "citations": []})
    elif verdict == "CONFLICTED" and not conflicts:
        for a in agreements:
            unanswered.append({"kind": "agreement", "aspect": a["aspect"],
                               "citations": a["citations"]})
    elif verdict == "PARTIAL" and not conflicts and not missing:
        for a in agreements:
            unanswered.append({"kind": "agreement", "aspect": a["aspect"],
                               "citations": a["citations"]})
    elif verdict == "NO EVIDENCE" and (conflicts or agreements):
        for group in conflicts + agreements:
            unanswered.append({"kind": "rows", "aspect": group["aspect"],
                               "citations": group["citations"]})
    return {
        "matches_gate": verdict == gate["verdict"],
        "supported": verdict == gate["verdict"] and not unanswered,
        "unanswered": unanswered,
    }


def exhibits(rows: list[dict]) -> list[dict]:
    """The non-reviewer lanes' recorded exhibits (web fetches, vision reads)."""
    out = []
    for r in rows:
        source = r.get("source") or ""
        if source in EXHIBIT_LANES:
            out.append({
                "lane": EXHIBIT_LANES[source],
                "source": source,
                "locator": r.get("locator", ""),
                "statement": r.get("statement", ""),
                "value": r.get("value", ""),
            })
    return out


def build_replay() -> dict:
    """The transcript from the recorded run. Nothing here is generated text."""
    rows = _load_rows(BENCH_CASES)
    truth = json.loads(BENCH_TRUTH.read_text(encoding="utf-8"))
    eval_data = json.loads(BENCH_EVAL.read_text(encoding="utf-8"))
    eval_by_item = {e["item"]: e for e in eval_data["results"]}
    profile = providers.PROFILES["nebius"]
    models = profile["models"]
    endpoint = profile["base_url"]

    items_out = []
    disagreements = 0
    for item_id in sorted(truth):
        mine = [r for r in rows if r.get("item_id") == item_id]
        title = next((r.get("title") for r in mine if r.get("title")), "")
        gate = gate_view(item_id, mine)
        entry = eval_by_item.get(item_id)

        round1 = []
        audit = []
        preserved = []
        for tier in ("fast", "deep"):
            tier_out = (entry.get("tiers") or {}).get(tier) if entry else None
            if tier_out is None:
                round1.append({
                    "tier": tier, "lane": TIER_LANE[tier],
                    "model_id": models[tier], "status": "not run",
                    "reason": "the item has no claims; the harness does not "
                              "run lanes on an item with nothing to judge "
                              "(recorded 2026-10-28 behaviour)",
                })
                continue
            verdict = tier_out["verdict"]
            round1.append({
                "tier": tier, "lane": TIER_LANE[tier],
                "model_id": models[tier], "status": "recorded",
                "verdict": verdict,
                "agrees_with_gate": verdict == gate["verdict"],
                "cost_usd": tier_out.get("cost_usd"),
                "tokens": tier_out.get("tokens"),
                "receipt": "benchmark/eval-benchmark-2026-10-28.json",
            })
            a = citation_audit(verdict, gate)
            audit.append({"tier": tier, **a})
            if verdict != gate["verdict"]:
                preserved.append(tier)
        if preserved:
            disagreements += 1

        items_out.append({
            "item": item_id,
            "title": title,
            "planted_truth": truth[item_id],
            "gate": gate,
            "round1": round1,
            "exhibits": exhibits(mine),
            "citation_audit": audit,
            "disagreements_preserved": preserved,
            "rebuttal_round": {
                "status": "NOT RUN",
                "reason": "cross-examination is a live model round and no "
                          "provider key is present on the build machine; "
                          "run `NEBIUS_API_KEY=... python3 court.py --live` "
                          "to hold it. The citation audit above is the "
                          "deterministic layer and is complete.",
            },
        })

    return {
        "kind": "nemotron-court-debate",
        "mode": "replay",
        "generated_at": _now(),
        "corpus": "benchmark/cases.jsonl",
        "endpoint": endpoint,
        "labels": {
            "round1": "RECORDED — verdicts, costs and tokens from the "
                      "2026-10-28 live Token Factory run, committed as "
                      "benchmark/eval-benchmark-2026-10-28.json",
            "citation_audit": "COMPUTED — deterministic, run over the "
                              "committed corpus by court.py; no model text",
            "rebuttal_round": "NOT RUN — no provider key present; the "
                              "transcript does not invent one",
        },
        "summary": {
            "items": len(items_out),
            "items_with_disagreement": disagreements,
            "gate_verdicts": {
                v: sum(1 for i in items_out if i["gate"]["verdict"] == v)
                for v in ("CORROBORATED", "PARTIAL", "CONFLICTED", "NO EVIDENCE")
            },
        },
        "items": items_out,
    }


def _parse_cross_exam(text: str) -> dict:
    position = "UNPARSEABLE"
    cites: list[str] = []
    rebuts: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        upper = line.upper()
        if upper.startswith("POSITION:"):
            rest = line.split(":", 1)[1].strip()
            for verdict in review.VERDICTS:
                if rest.upper().startswith(verdict):
                    position = verdict
                    break
        elif upper.startswith("CITES:"):
            cites = [c.strip() for c in line.split(":", 1)[1].split(";")
                     if c.strip()]
        elif upper.startswith("REBUT "):
            lane, _, why = line[6:].partition(":")
            rebuts.append({"lane": lane.strip().lower(),
                           "challenge": why.strip()})
    return {"position": position, "cites": cites, "rebuts": rebuts,
            "raw": text if position == "UNPARSEABLE" else ""}


def build_live(evidence_path: Path, budget: float, provider: str) -> dict:
    """Hold the Court live. Round 1 verdicts are this run's, cited as such."""
    prof = providers.resolve(provider)  # raises with the env var named
    rows = _load_rows(evidence_path)
    items = ev.load_items(str(evidence_path))
    item_ids = sorted(items) or sorted({r["item_id"] for r in rows})

    spent = 0.0

    def call(tier: str, prompt: str) -> tuple[str, float]:
        nonlocal spent
        model = prof["models"][tier]
        text, usage = review._chat(prof["base_url"], prof["api_key"],
                                   model, prompt)
        pin, pout = review._price(tier, __import__("os").environ)
        cost = (usage.get("prompt_tokens", 0) * pin
                + usage.get("completion_tokens", 0) * pout) / 1_000_000
        spent += cost
        return text, cost

    items_out = []
    for item_id in item_ids:
        mine = [r for r in rows if r.get("item_id") == item_id]
        title = items[item_id].title if item_id in items else item_id
        gate = gate_view(item_id, mine)
        claims_text = "\n".join(
            f"- [{r.get('kind')}/{r.get('aspect') or 'state'}] {r.get('source')}: "
            f"{r.get('statement')} (value: {r.get('value')})" for r in mine)

        round1 = []
        verdicts: dict[str, str] = {}
        for tier in ("fast", "deep"):
            if spent >= budget:
                round1.append({"tier": tier, "status": "skipped-budget"})
                continue
            prompt = review.PROMPT.format(title=title, item_id=item_id,
                                          claims=claims_text)
            text, cost = call(tier, prompt)
            verdict, _reason = review._parse_verdict(text)
            verdicts[tier] = verdict
            round1.append({
                "tier": tier, "lane": TIER_LANE[tier],
                "model_id": prof["models"][tier], "status": "live",
                "verdict": verdict,
                "agrees_with_gate": verdict == gate["verdict"],
                "cost_usd": round(cost, 6),
            })

        contested = any(v != gate["verdict"] for v in verdicts.values()) or \
            len(set(verdicts.values())) > 1
        rebuttal: dict = {"status": "not contested",
                          "reason": "every lane agreed with the gate"}
        if contested and len(verdicts) == 2:
            round1_text = "\n".join(
                f"- {t} ({prof['models'][t]}): {v}"
                for t, v in verdicts.items())
            positions = []
            for tier in ("fast", "deep"):
                if spent >= budget:
                    positions.append({"tier": tier,
                                      "status": "skipped-budget"})
                    continue
                prompt = CROSS_EXAM_PROMPT.format(
                    tier=tier, model=prof["models"][tier], title=title,
                    item_id=item_id, claims=claims_text,
                    round1=round1_text, gate=gate["verdict"])
                text, cost = call(tier, prompt)
                parsed = _parse_cross_exam(text)
                positions.append({"tier": tier, "status": "live",
                                  "cost_usd": round(cost, 6), **parsed})
            rebuttal = {"status": "RECORDED", "positions": positions}

        audit = [ {"tier": p["tier"], **citation_audit(p["verdict"], gate)}
                  for p in round1 if p.get("verdict") ]
        items_out.append({
            "item": item_id, "title": title, "gate": gate,
            "round1": round1, "exhibits": exhibits(mine),
            "citation_audit": audit,
            "disagreements_preserved": [
                p["tier"] for p in round1
                if p.get("verdict") and p["verdict"] != gate["verdict"]],
            "rebuttal_round": rebuttal,
        })

    return {
        "kind": "nemotron-court-debate",
        "mode": "live",
        "generated_at": _now(),
        "corpus": str(evidence_path),
        "endpoint": prof["base_url"],
        "labels": {
            "round1": "LIVE — run by court.py at the time above",
            "citation_audit": "COMPUTED — deterministic; no model text",
            "rebuttal_round": "LIVE — model text in a strict shape, "
                              "parsed, unparseable answers kept as-is",
        },
        "summary": {
            "items": len(items_out),
            "total_cost_usd": round(spent, 4),
            "items_with_disagreement": sum(
                1 for i in items_out if i["disagreements_preserved"]),
        },
        "items": items_out,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true",
                    help="hold the Court live (needs the provider key)")
    ap.add_argument("--evidence", default=str(BENCH_CASES),
                    help="evidence file for --live (default: benchmark corpus)")
    ap.add_argument("--provider", default="nebius")
    ap.add_argument("--budget", type=float, default=0.50,
                    help="USD cap for --live paid calls (default 0.50)")
    ap.add_argument("--out", default=None,
                    help="where to write the transcript JSON")
    args = ap.parse_args(argv)

    if args.live:
        try:
            transcript = build_live(Path(args.evidence), args.budget,
                                    args.provider)
        except providers.ProviderError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            print("The Court cannot sit without its lanes. The replay "
                  "transcript (recorded Round 1 + computed audit) needs "
                  "no key: python3 court.py", file=sys.stderr)
            return 2
        out = Path(args.out) if args.out else HERE / "court" / "debate-live.json"
    else:
        transcript = build_replay()
        out = Path(args.out) if args.out else HERE / "court" / "debate-replay.json"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(transcript, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    s = transcript["summary"]
    print(f"mode={transcript['mode']} items={s['items']} "
          f"disagreements on {s['items_with_disagreement']} item(s) "
          f"-> {out.relative_to(HERE) if out.is_relative_to(HERE) else out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
