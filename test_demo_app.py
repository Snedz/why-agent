"""Tests for the demo page's workbench — demo_page.py, reconciler.js, workbench.js.

    python3 -m unittest test_demo_app -v

Offline, no model, no network. The landing page is the URL the rules ask a
judge to open first, and it now runs the reconciler in the tab rather than
showing a screenshot of one. Two things have to be true for that to be honest:

1. **The page cannot drift from the corpus.** `demo_page.py --check` must pass,
   the committed bytes must equal what the generator writes, and the corpus
   embedded in the page must be the corpus on disk.

2. **The JavaScript must be a port, not a second implementation.**
   `demo_lab/reconciler.js` is run under node and `evidence.reconcile()` under
   Python over every item in both corpora, plus edge cases built to break a
   careless translation, and the two results must be identical — verdict,
   conflicts, agreements, gaps, unexpected aspects, aspect order, source count.

The second gate is the one that matters. A page that reimplements the
reconciler in the browser without proving the two agree is showing a judge a
verdict the repository does not return, which is exactly the confident-and-wrong
artefact this project exists to refuse.
"""
import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "benchmark"))

import demo_page  # noqa: E402
import evidence as ev  # noqa: E402

NODE = shutil.which("node")

CORPUS_PATHS = {
    "benchmark": demo_page.tier_ledger.CASES,
    "demo": HERE / "evidence" / "items.jsonl",
    "claimcourt": HERE / "claimcourt" / "cases.jsonl",
}

# What `.github/workflows/pages.yml` copies into the published site. A relative
# link outside this set is a 404 for the judge who clicks it.
PUBLISHED = {"demo_lab", "why-agent-nebius-demo.mp4", "why-agent-demo.mp4",
             "why-agent-nebius-poster.png", "why-agent-nebius-thumbnail.png",
             "why-agent-deck.pdf"}


def py_shape(item, claims):
    """The Python answer, in the same shape parity_runner.js emits."""
    r = ev.reconcile(item, claims)
    return {
        "item_id": item.item_id,
        "verdict": r.confidence(),
        "conflicts": [[a, [c.value for c in g]] for a, g in r.conflicts],
        "agreements": [[a, [c.value for c in g]] for a, g in r.agreements],
        "unknown_aspects": list(r.unknown_aspects),
        "unexpected": [[a, [c.value for c in g]] for a, g in r.unexpected],
        "aspects": list(r.by_aspect.keys()),
        "sources": r.sources,
    }


def js_shape(entries):
    """Run reconciler.js under node over [(item, claims)] and return its answer."""
    payload = {"items": [{"item": dataclasses.asdict(i),
                          "claims": [dataclasses.asdict(c) for c in cl]}
                         for i, cl in entries]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(payload, fh)
        tmp = fh.name
    try:
        proc = subprocess.run(
            [NODE, str(HERE / "demo_lab" / "parity_runner.js"), tmp],
            capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise AssertionError("node failed:\n" + proc.stdout + proc.stderr)
        return json.loads(proc.stdout)
    finally:
        os.unlink(tmp)


def corpus_entries():
    """Every item in both corpora, with its claims, as the page loads them."""
    entries = []
    for corpus_id, _label, _name in demo_page.CORPORA:
        path = CORPUS_PATHS[corpus_id]
        rows = demo_page._jsonl(path)
        items = ev.load_items(str(path))
        by_item = {}
        for row in rows:
            by_item.setdefault(row["item_id"], []).append(ev.Evidence(
                item_id=row["item_id"], kind=row["kind"], source=row["source"],
                locator=row["locator"], statement=row["statement"],
                value=row["value"], aspect=row["aspect"]))
        for item_id, claims in by_item.items():
            item = items.get(item_id) or ev.Item(item_id=item_id)
            entries.append((item, claims))
    return entries


def claim(item_id, kind, value, aspect="", source=None, locator="x"):
    return ev.Evidence(item_id=item_id, kind=kind, source=source or kind,
                       locator=locator, statement="s", value=value, aspect=aspect)


def edge_entries():
    """Cases built to break a careless port. Each one names the trap."""
    return [
        # No claims at all: NO EVIDENCE, and all three aspects are gaps.
        (ev.Item("e-empty"), []),
        # Only an aspect outside state/outcome/cause: cited, ignored, PARTIAL.
        (ev.Item("e-only-unexpected"), [claim("e-only-unexpected", "web", "odd", "vibe")]),
        # A forged aspect must not stop a complete item being CORROBORATED.
        (ev.Item("e-forged"), [claim("e-forged", "card", "a"), claim("e-forged", "check", "a"),
                               claim("e-forged", "receipt", "b"),
                               claim("e-forged", "commit", "c", "cause"),
                               claim("e-forged", "web", "zzz", "vibe")]),
        # Same aspect, different values: CONFLICTED.
        (ev.Item("e-conflict"), [claim("e-conflict", "card", "done"),
                                 claim("e-conflict", "check", "red")]),
        # Same aspect, same value twice: an agreement with two sources.
        (ev.Item("e-agree"), [claim("e-agree", "card", "done"),
                              claim("e-agree", "check", "done")]),
        # An explicit aspect overrides the kind default (card would be "state").
        (ev.Item("e-override"), [claim("e-override", "card", "why", "cause")]),
        # An unknown kind with no aspect: the aspect becomes the kind itself.
        (ev.Item("e-kind"), [claim("e-kind", "mystery", "v")]),
        # The empty string is a value, not an absence: "" vs "x" is a conflict.
        (ev.Item("e-empty-value"), [claim("e-empty-value", "card", ""),
                                    claim("e-empty-value", "check", "x")]),
        # Values are compared exactly: DONE is not done.
        (ev.Item("e-case"), [claim("e-case", "card", "DONE"),
                             claim("e-case", "check", "done")]),
        # One aspect covered, two gaps: PARTIAL, and the gaps are in a fixed order.
        (ev.Item("e-gaps"), [claim("e-gaps", "commit", "c", "cause")]),
        # Two unexpected aspects: the order must be the sorted order in both.
        (ev.Item("e-two-unexpected"), [claim("e-two-unexpected", "web", "1", "zeta"),
                                       claim("e-two-unexpected", "web", "2", "alpha")]),
    ]


class GeneratedTests(unittest.TestCase):
    """The page is generated from the corpus, not typed."""

    def test_the_committed_page_is_exactly_what_the_generator_writes(self):
        self.assertEqual(demo_page.build(), demo_page.PAGE.read_text(encoding="utf-8"),
                         "demo.html is not what demo_page.py generates — run "
                         "`python3 demo_page.py`")

    def test_running_the_generator_twice_produces_the_same_bytes(self):
        self.assertEqual(demo_page.build(), demo_page.build())

    def test_the_check_mode_passes(self):
        proc = subprocess.run([sys.executable, str(HERE / "demo_page.py"), "--check"],
                              capture_output=True, text=True, cwd=str(HERE))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_the_page_inlines_both_scripts_verbatim(self):
        """No copy of either script in the generator: the files are the source."""
        page = demo_page.PAGE.read_text(encoding="utf-8")
        for name in ("reconciler.js", "workbench.js"):
            body = (HERE / "demo_lab" / name).read_text(encoding="utf-8")
            self.assertIn(body, page, f"{name} is not inlined verbatim")
        for placeholder in ("__WORKBENCH_DATA__", "__RECONCILER_JS__", "__WORKBENCH_JS__"):
            self.assertNotIn(placeholder, page)

    def test_the_page_carries_the_whole_corpus(self):
        payload = demo_page.workbench_payload()
        page = demo_page.PAGE.read_text(encoding="utf-8")
        self.assertGreaterEqual(payload["item_count"], 14)
        for item in payload["items"]:
            self.assertIn(f'"{item["id"]}"', page, f"{item['id']} is not in the page")

    def test_the_embedded_corpus_is_the_corpus_on_disk(self):
        """The blob in the page is the rows in the files, not a summary of them."""
        page = demo_page.PAGE.read_text(encoding="utf-8")
        blob = page.split("window.__WHY_AGENT__ = ", 1)[1].split(";</script>", 1)[0]
        embedded = json.loads(blob)
        on_disk = demo_page.workbench_payload()
        self.assertEqual(embedded["item_count"], on_disk["item_count"])
        for want, got in zip(on_disk["items"], embedded["items"]):
            self.assertEqual(got["id"], want["id"])
            self.assertEqual(got["rows"], want["rows"])

    def test_a_claim_value_cannot_close_the_script_tag(self):
        """A value containing </script> would break the page. Escape it."""
        page = demo_page.PAGE.read_text(encoding="utf-8")
        blob = page.split("window.__WHY_AGENT__ = ", 1)[1].split(";</script>", 1)[0]
        self.assertNotIn("</", blob)

    def test_every_relative_link_points_at_something_pages_publishes(self):
        page = demo_page.PAGE.read_text(encoding="utf-8")
        for href in re.findall(r'href="([^"#][^"]*)"', page):
            if href.startswith(("http://", "https://", "mailto:")):
                continue
            head = href.rstrip("/").split("/")[0]
            self.assertIn(head, PUBLISHED,
                          f"{href} is linked but pages.yml does not publish it")


@unittest.skipUnless(NODE, "node is not installed, so the JS port cannot be checked "
                           "against the Python — the port is UNVERIFIED on this machine")
class PortParityTests(unittest.TestCase):
    """reconciler.js must return what evidence.reconcile() returns. Exactly."""

    def test_the_port_matches_the_python_on_every_corpus_item(self):
        entries = corpus_entries()
        self.assertGreaterEqual(len(entries), 14)
        want = [py_shape(i, c) for i, c in entries]
        got = js_shape(entries)
        self.assertEqual(len(want), len(got))
        for w, g in zip(want, got):
            self.assertEqual(w, g, f"the port disagrees with the Python on {w['item_id']}")

    def test_the_port_matches_the_python_on_edge_cases(self):
        entries = edge_entries()
        want = [py_shape(i, c) for i, c in entries]
        got = js_shape(entries)
        for w, g in zip(want, got):
            self.assertEqual(w, g, f"the port disagrees with the Python on {w['item_id']}")

    def test_the_corpus_exercises_all_four_verdicts(self):
        """A parity test over four CORROBORATEDs proves very little."""
        verdicts = {py_shape(i, c)["verdict"] for i, c in corpus_entries() + edge_entries()}
        self.assertEqual(verdicts, {"CORROBORATED", "PARTIAL", "CONFLICTED", "NO EVIDENCE"})

    def test_the_port_reproduces_the_flip_the_page_advertises(self):
        """The workbench's headline interaction, checked outside the browser."""
        lanes = demo_page.workbench_payload()["lane_sources"]
        flipped = []
        for item, claims in corpus_entries():
            without = [c for c in claims if c.source not in lanes]
            if len(without) == len(claims):
                continue
            before = ev.reconcile(item, claims).confidence()
            after = ev.reconcile(item, without).confidence()
            if before != after:
                flipped.append((item.item_id, before, after))
                js = js_shape([(item, without)])[0]
                self.assertEqual(js["verdict"], after,
                                 f"the port does not reproduce the flip on {item.item_id}")
        self.assertGreaterEqual(len(flipped), 2,
                                "the lane flip the page advertises no longer happens")


if __name__ == "__main__":
    unittest.main(verbosity=2)
