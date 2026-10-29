"""Offline tests for the Tavily live-evidence lane.

    python3 -m unittest test_tavily_lane -v

No network, no third-party package, no real API key: the HTTP call is behind
a transport seam, and every test stubs it with canned Tavily JSON.
"""
import dataclasses
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import evidence as ev  # noqa: E402
import tavily_lane as tl  # noqa: E402

RETRIEVED_AT = "2026-10-28T18:00:00Z"

CANNED_BODY = {
    "query": "Nebius hackathon submission deadline",
    "results": [
        {
            "title": "Nebius x NVIDIA Global AI Hackathon",
            "url": "https://nebiusglobalaihackathon.devpost.com/",
            "content": "Submissions close Oct 30 at 1:00 PM EDT. Build on "
                       "Nebius Token Factory with NVIDIA Nemotron.",
            "score": 0.91,
        },
        {
            "title": "A roundup of October hackathons",
            "url": "https://example.invalid/roundup",
            "content": "Dozens of events this month, from game jams to "
                       "climate challenges, most of them online.",
            "score": 0.42,
        },
    ],
}


def stub_transport(captured):
    """A transport that records what it was sent and answers canned JSON."""
    def send(url, payload, timeout):
        captured["url"] = url
        captured["payload"] = payload
        return CANNED_BODY
    return send


class TavilyLaneTests(unittest.TestCase):
    def test_search_returns_the_raw_results(self):
        captured = {}
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
            results = tl.search_claims("when does it close?",
                                       transport=stub_transport(captured))
        self.assertEqual(results, CANNED_BODY["results"])
        # The lane asks for pages, never for Tavily's generated answer: the
        # answer is a model's summary, and a summary is not evidence.
        self.assertEqual(captured["payload"]["search_depth"], "advanced")
        self.assertIs(captured["payload"]["include_answer"], False)
        self.assertEqual(captured["payload"]["max_results"], 5)
        self.assertEqual(captured["url"], tl.SEARCH_URL)

    def test_a_page_containing_the_claimed_value_supports_it(self):
        rows = tl.results_to_evidence("why-tavily", CANNED_BODY["results"],
                                      "Oct 30", RETRIEVED_AT)
        hit = rows[0]
        # The value appears literally in the page text, so the row may carry
        # it, with the page itself as the citation.
        self.assertEqual(hit.value, "Oct 30")
        self.assertEqual(hit.locator,
                         "https://nebiusglobalaihackathon.devpost.com/")
        self.assertEqual(hit.kind, "web")
        self.assertEqual(hit.source, "tavily")
        self.assertEqual(hit.observed_at, RETRIEVED_AT)
        # A web row speaks about state unless a row says otherwise.
        self.assertEqual(hit.aspect_name, "state")

    def test_a_page_without_the_claimed_value_is_a_recorded_non_match(self):
        rows = tl.results_to_evidence("why-tavily", CANNED_BODY["results"],
                                      "Oct 30", RETRIEVED_AT)
        miss = rows[1]
        # Not dropped and not credited: an empty value, and a statement that
        # says plainly the value was not found on this page.
        self.assertEqual(miss.value, "")
        self.assertIn("not found", miss.statement)
        self.assertEqual(miss.locator, "https://example.invalid/roundup")

    def test_a_missing_api_key_is_an_error_not_a_default(self):
        def forbidden_transport(url, payload, timeout):
            raise AssertionError("no request may be sent without a key")

        # clear=True so a key in the real environment cannot leak into the
        # test and mask the missing-key path.
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(tl.TavilyKeyError):
                tl.search_claims("anything", transport=forbidden_transport)

    def test_web_rows_round_trip_through_the_jsonl_loaders(self):
        rows = tl.results_to_evidence("why-tavily", CANNED_BODY["results"],
                                      "Oct 30", RETRIEVED_AT)
        card = {"item_id": "why-tavily", "kind": "card",
                "title": "Is the deadline Oct 30?", "value": "OPEN"}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "items.jsonl")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(card) + "\n")
                for row in rows:
                    fh.write(json.dumps(dataclasses.asdict(row)) + "\n")
            items = ev.load_items(path)
            loaded = ev.load_evidence(path)
        self.assertIn("why-tavily", items)
        web = [c for c in loaded if c.kind == "web"]
        self.assertEqual(web, rows)


class TavilyCliTests(unittest.TestCase):
    """The CLI: main() against the stub transport, rows read back with the loader.

    The lane call is stubbed where the CLI reaches it — `search_claims` — so
    the CLI's own behaviour (argument handling, the append, the literal-
    appearance guard) is what is under test, and no socket is ever opened.
    """

    def _run_cli(self, tmp, claimed="Oct 30"):
        out = os.path.join(tmp, "web-rows.jsonl")
        with mock.patch.object(tl, "search_claims",
                               return_value=CANNED_BODY["results"]) as called:
            rc = tl.main(["--item", "why-tavily", "--query", "deadline",
                          "--claim", claimed, "--out", out])
        self.assertEqual(rc, 0)
        self.assertTrue(called.called, "the CLI must go through the lane")
        return out

    def test_the_cli_appends_web_rows_that_read_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._run_cli(tmp)
            loaded = ev.load_evidence(out)

        web = [r for r in loaded if r.kind == "web"]
        self.assertEqual(len(web), 2, "one row per page Tavily returned")
        for row in web:
            self.assertEqual(row.source, "tavily")
            self.assertEqual(row.item_id, "why-tavily")

    def test_the_literal_appearance_guard_holds_through_the_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._run_cli(tmp)
            loaded = ev.load_evidence(out)

        web = {r.locator: r for r in loaded if r.kind == "web"}
        hit = web["https://nebiusglobalaihackathon.devpost.com/"]
        # The value appears literally in the page text, so the row carries it.
        self.assertEqual(hit.value, "Oct 30")
        miss = web["https://example.invalid/roundup"]
        # The page does not contain the value: an EMPTY value and a statement
        # that says so. Not dropped, and not credited.
        self.assertEqual(miss.value, "")
        self.assertIn("not found", miss.statement)

    def test_a_claimed_value_no_page_contains_leaves_every_row_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._run_cli(tmp, claimed="a value on no page")
            loaded = ev.load_evidence(out)

        web = [r for r in loaded if r.kind == "web"]
        self.assertEqual(len(web), 2)
        for row in web:
            self.assertEqual(row.value, "", "no page carried the value")
            self.assertIn("not found", row.statement)

    def test_the_cli_appends_rather_than_truncating(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._run_cli(tmp)
            first = len(ev.load_evidence(out))
            self._run_cli(tmp)
            second = len(ev.load_evidence(out))
        self.assertEqual(first, 2)
        self.assertEqual(second, 4, "a second run appends; it does not overwrite")

    def test_a_failed_lane_writes_no_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "web-rows.jsonl")
            with mock.patch.object(tl, "search_claims",
                                   side_effect=tl.TavilyError("no key")):
                rc = tl.main(["--item", "why-tavily", "--query", "deadline",
                              "--claim", "Oct 30", "--out", out])
            self.assertEqual(rc, 1)
            self.assertFalse(os.path.exists(out),
                             "a lane that failed must not leave evidence rows behind")


if __name__ == "__main__":
    unittest.main()
