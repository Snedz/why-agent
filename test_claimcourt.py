"""Offline tests for the Claim Court lane: corpus, court, lab.

Everything here runs without provider keys — that is the point. The lane
ships on recorded and computed artefacts tonight, so the tests pin exactly
those: the corpus loads and its computed verdicts match the frozen truth,
every synthetic fixture is labelled as synthetic in the data, the debate
transcript faithfully replays the recorded eval (nothing invented), and
the generated lab matches its committed output.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import evidence as ev  # noqa: E402

CC_CASES = ROOT / "claimcourt" / "cases.jsonl"
CC_TRUTH = ROOT / "claimcourt" / "truth.json"
DEBATE = ROOT / "court" / "debate-replay.json"
BENCH_EVAL = ROOT / "benchmark" / "eval-benchmark-2026-10-28.json"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


class CorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = _rows(CC_CASES)
        self.items = ev.load_items(str(CC_CASES))
        self.claims = ev.load_evidence(str(CC_CASES))
        self.truth = json.loads(CC_TRUTH.read_text(encoding="utf-8"))

    def test_corpus_size_and_split(self):
        self.assertEqual(len(self.items), 18)
        fixtures = {}
        for item_id, item_rows in self._by_item().items():
            card = next(r for r in item_rows if (r.get("kind") or "card") == "card")
            fixtures[item_id] = card.get("fixture")
        self.assertEqual(sum(1 for v in fixtures.values() if v == "recorded"), 7)
        self.assertEqual(sum(1 for v in fixtures.values() if v == "synthetic"), 11)

    def _by_item(self) -> dict[str, list[dict]]:
        by: dict[str, list[dict]] = {}
        for r in self.rows:
            by.setdefault(r["item_id"], []).append(r)
        return by

    def test_every_synthetic_row_is_labelled(self):
        for item_id, item_rows in self._by_item().items():
            card = next(r for r in item_rows if (r.get("kind") or "card") == "card")
            if card.get("fixture") != "synthetic":
                continue
            for row in item_rows:
                # The machine-readable label: every row of a synthetic item
                # carries the fixture field — that is what the lab builder
                # reads to badge the card, so it cannot silently drop.
                self.assertEqual(row.get("fixture"), "synthetic",
                                 f"{item_id}: unlabelled synthetic row")
            self.assertIn("SYNTHETIC FIXTURE", card.get("title", ""))

    def test_computed_verdicts_match_frozen_truth(self):
        for item_id, expected in sorted(self.truth.items()):
            verdict = ev.explain(self.items, self.claims, item_id).confidence()
            self.assertEqual(verdict, expected, item_id)

    def test_verdict_distribution(self):
        counts: dict[str, int] = {}
        for item_id in self.truth:
            v = ev.explain(self.items, self.claims, item_id).confidence()
            counts[v] = counts.get(v, 0) + 1
        self.assertEqual(counts, {"CONFLICTED": 12, "PARTIAL": 5,
                                  "CORROBORATED": 1})


class CourtReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.debate = json.loads(DEBATE.read_text(encoding="utf-8"))
        self.eval_data = json.loads(BENCH_EVAL.read_text(encoding="utf-8"))
        self.eval_by_item = {e["item"]: e for e in self.eval_data["results"]}
        self.by_item = {i["item"]: i for i in self.debate["items"]}

    def test_replay_is_labelled_and_covers_the_corpus(self):
        self.assertEqual(self.debate["mode"], "replay")
        self.assertEqual(len(self.debate["items"]), 14)
        self.assertIn("RECORDED", self.debate["labels"]["round1"])
        self.assertIn("NOT RUN", self.debate["labels"]["rebuttal_round"])

    def test_round1_verdicts_are_the_recorded_ones(self):
        for item_id, entry in self.by_item.items():
            recorded = self.eval_by_item.get(item_id)
            for position in entry["round1"]:
                if position.get("status") != "recorded":
                    continue
                expected = recorded["tiers"][position["tier"]]["verdict"]
                self.assertEqual(position["verdict"], expected,
                                 f"{item_id}/{position['tier']}")

    def test_item_without_claims_has_no_lane_verdicts(self):
        entry = self.by_item["bm-no-evidence"]
        self.assertEqual(entry["gate"]["verdict"], "NO EVIDENCE")
        for position in entry["round1"]:
            self.assertEqual(position["status"], "not run")

    def test_rebuttal_round_not_run_everywhere(self):
        for entry in self.debate["items"]:
            self.assertEqual(entry["rebuttal_round"]["status"], "NOT RUN")

    def test_citation_audit_flags_the_known_false_approval(self):
        # bm-card-lies: the fast lane approved a card its own rows refute.
        audits = {a["tier"]: a for a in self.by_item["bm-card-lies"]["citation_audit"]}
        self.assertFalse(audits["fast"]["supported"])
        self.assertTrue(audits["fast"]["unanswered"])
        self.assertTrue(audits["deep"]["supported"])

    def test_disagreements_preserved_not_averaged(self):
        self.assertEqual(self.debate["summary"]["items_with_disagreement"], 8)
        self.assertIn("fast", self.by_item["bm-card-lies"]["disagreements_preserved"])


class PublishedLabTests(unittest.TestCase):
    """The lab a judge can reach is the lab this repository generated.

    `pages.yml` serves `demo_lab/` recursively, so the reachable copy is
    `demo_lab/claimcourt/`. It was a hand-kept duplicate of `claimcourt_lab/`,
    and it had drifted: the published page linked to
    `demo_lab/demo_lab/index.html`, which is a 404. Nothing tested a link, so
    nothing noticed.
    """

    PUBLISHED = ROOT / "demo_lab" / "claimcourt" / "index.html"
    SOURCE = ROOT / "claimcourt_lab" / "index.html"

    def test_the_published_copy_is_the_generated_one(self):
        self.assertTrue(self.PUBLISHED.exists(), f"{self.PUBLISHED} is missing")
        self.assertEqual(self.PUBLISHED.read_text(encoding="utf-8"),
                         self.SOURCE.read_text(encoding="utf-8"),
                         "the published lab and the generated lab have drifted apart")

    def test_every_relative_link_on_the_published_page_resolves(self):
        import re
        page = self.PUBLISHED.read_text(encoding="utf-8")
        for href in re.findall(r'href="([^"#][^"]*)"', page):
            if href.startswith(("http://", "https://", "mailto:")):
                continue
            target = (self.PUBLISHED.parent / href).resolve()
            self.assertTrue(target.exists(),
                            f"the published lab links {href}, which resolves to "
                            f"{target} — nothing is there")

    def test_it_links_back_to_the_case_lab(self):
        page = self.PUBLISHED.read_text(encoding="utf-8")
        self.assertIn('href="../index.html"', page)


class LabBuildTests(unittest.TestCase):
    def test_generated_files_match_committed_output(self):
        sys.path.insert(0, str(ROOT / "claimcourt_lab"))
        import build as lab_build  # noqa: E402
        for path, body in lab_build.generate():
            self.assertTrue(path.exists(), f"missing generated file: {path}")
            self.assertEqual(path.read_text(encoding="utf-8"), body,
                             f"stale generated file: {path.name} "
                             "(run claimcourt_lab/build.py)")

    def test_lab_cases_carry_honest_lane_status(self):
        for path in sorted((ROOT / "claimcourt_lab" / "cases").glob("*.json")):
            case = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(case["verdict"], case["frozen_verdict"], path.name)
            self.assertEqual(case["lanes"]["status"], "NOT RUN", path.name)
            self.assertIn(case["fixture"], ("recorded", "synthetic"), path.name)


if __name__ == "__main__":
    unittest.main()
