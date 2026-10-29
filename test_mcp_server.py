"""Tests for mcp_server.py — the MCP boundary.

    python3 -m unittest test_mcp_server -v

Offline: no model, no network, no key. The fixture is the repo's own
`evidence/items.jsonl`, and the fast/deep pattern the disagreements test
expects is read out of the repo's own `eval-results-2026-10-28.json` — the
run that actually happened — rather than typed in here.
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import evidence as ev  # noqa: E402
import mcp_server as ms  # noqa: E402

FIXTURE = os.path.join(HERE, "evidence", "items.jsonl")
EVAL_RESULTS = os.path.join(HERE, "eval-results-2026-10-28.json")


def repo_rows(item_id=None):
    """The repo's own rows, optionally for one item."""
    rows = []
    with open(FIXTURE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            row = json.loads(line)
            if item_id is None or row.get("item_id") == item_id:
                rows.append(row)
    return rows


def recorded_run(item_id):
    """What the repo's recorded run said about one item."""
    with open(EVAL_RESULTS, encoding="utf-8") as fh:
        payload = json.load(fh)
    for entry in payload["results"]:
        if entry["item"] == item_id:
            return entry
    raise AssertionError(f"no recorded run for {item_id}")


def write_fixture(rows):
    """A temp evidence file holding these rows; returns its path."""
    tmp = tempfile.mkdtemp(prefix="mcp-fixture-")
    path = os.path.join(tmp, "evidence.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return path


class ToolSurfaceTests(unittest.TestCase):
    """Three tools, and nothing else."""

    def test_there_are_exactly_three_tools(self):
        self.assertEqual([t["name"] for t in ms.TOOLS],
                         ["submit_claims", "get_verdict", "get_disagreements"])

    def test_every_tool_declares_an_input_schema(self):
        for tool in ms.TOOLS:
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertTrue(tool["description"].strip())
            for required in tool["inputSchema"].get("required", []):
                self.assertIn(required, tool["inputSchema"]["properties"])

    def test_the_server_calls_no_model(self):
        # The answer must not depend on a provider being up. A guard, so a
        # later edit that adds a model call cannot pass unnoticed.
        source = open(os.path.join(HERE, "mcp_server.py"), encoding="utf-8").read()
        for banned in ("urllib", "http.client", "requests", "openai", "anthropic",
                       "_chat", "batch_eval"):
            self.assertNotIn(banned, source,
                             f"the MCP server must not talk to a model ({banned})")


class EndToEndTests(unittest.TestCase):
    """The repo's synthetic claims for why-alpha, in and back out."""

    def setUp(self):
        self.store = ms.Store(FIXTURE)
        self.claims = [r for r in repo_rows("why-alpha") if r.get("kind") != "verdict"]

    def test_the_claims_are_submitted_and_the_verdict_reads_back_conflicted(self):
        submitted = ms.tool_submit_claims(self.store, {"claims": self.claims})
        self.assertEqual(submitted["submitted"], len(self.claims))

        verdict = ms.tool_get_verdict(self.store, {"item_id": "why-alpha"})
        self.assertEqual(verdict["verdict"], "CONFLICTED")
        self.assertEqual(verdict["source"], "evidence.explain")
        self.assertTrue(verdict["aspects"], "the verdict groups its claims by aspect")
        self.assertTrue(verdict["citations"], "every claim is cited")
        for citation in verdict["citations"]:
            self.assertIsInstance(citation, str)
            self.assertTrue(citation.strip())

    def test_every_claim_carries_its_citation(self):
        ms.tool_submit_claims(self.store, {"claims": self.claims})
        verdict = ms.tool_get_verdict(self.store, {"item_id": "why-alpha"})
        cited = sum(len(v) for v in verdict["aspects"].values())
        self.assertEqual(cited, len(verdict["citations"]),
                         "one citation per claim, no more and no fewer")

    def test_an_unknown_item_is_an_unknown_not_an_empty_answer(self):
        verdict = ms.tool_get_verdict(self.store, {"item_id": "why-nobody-said"})
        self.assertEqual(verdict["verdict"], "NO EVIDENCE")
        self.assertEqual(verdict["citations"], [])


class SchemaRuleTests(unittest.TestCase):
    """Integrations contribute claims, never verdicts."""

    def setUp(self):
        self.store = ms.Store(FIXTURE)

    def test_a_verdict_shaped_submission_is_refused(self):
        for field in ("verdict", "verdicts", "confidence", "deterministic",
                      "agrees_with_deterministic"):
            row = {"item_id": "why-alpha", "statement": "the card was marked DONE",
                   field: "CORROBORATED"}
            with self.assertRaises(ms.SchemaError) as caught:
                ms.tool_submit_claims(self.store, {"claims": [row]})
            self.assertIn(field, str(caught.exception))
            self.assertIn("claims", str(caught.exception))

    def test_a_verdict_row_is_refused(self):
        row = {"item_id": "why-alpha", "kind": "verdict", "statement": "the lane said so",
               "value": "PARTIAL"}
        with self.assertRaises(ms.SchemaError) as caught:
            ms.tool_submit_claims(self.store, {"claims": [row]})
        self.assertIn("verdict", str(caught.exception))

    def test_an_unknown_kind_is_refused(self):
        row = {"item_id": "why-alpha", "kind": "gossip", "statement": "someone said"}
        with self.assertRaises(ms.SchemaError):
            ms.tool_submit_claims(self.store, {"claims": [row]})

    def test_a_refused_submission_stores_nothing(self):
        before = len(self.store.claims)
        with self.assertRaises(ms.SchemaError):
            ms.tool_submit_claims(self.store, {"claims": [
                {"item_id": "why-alpha", "statement": "ok", "kind": "card"},
                {"item_id": "why-alpha", "statement": "no", "verdict": "CORROBORATED"},
            ]})
        self.assertEqual(len(self.store.claims), before,
                         "a batch with one bad row stores nothing")


class DisagreementTests(unittest.TestCase):
    """The fast/deep split, as the repo's own run recorded it."""

    def setUp(self):
        self.run = recorded_run("why-alpha")
        self.fast = self.run["tiers"]["fast"]["verdict"]
        self.deep = self.run["tiers"]["deep"]["verdict"]
        self.deterministic = self.run["deterministic"]

    def _store_with_lane_verdicts(self):
        rows = [r for r in repo_rows("why-alpha") if r.get("kind") != "verdict"]
        for tier, verdict in (("fast", self.fast), ("deep", self.deep)):
            rows.append({
                "item_id": "why-alpha", "kind": "verdict", "source": f"lane/{tier}",
                "locator": f"eval-results-2026-10-28.json#{tier}",
                "statement": f"the {tier} lane read the evidence",
                "value": verdict,
            })
        return ms.Store(write_fixture(rows))

    def test_the_fast_deep_split_comes_back_with_citations(self):
        store = self._store_with_lane_verdicts()
        out = ms.tool_get_disagreements(store, {"item_id": "why-alpha"})

        self.assertEqual(out["deterministic"], self.deterministic)
        lanes = {lane["lane"]: lane for lane in out["lanes"]}
        self.assertEqual(lanes["lane/fast"]["verdict"], self.fast)
        self.assertEqual(lanes["lane/deep"]["verdict"], self.deep)
        for lane in lanes.values():
            self.assertTrue(lane["citation"])

    def test_the_lane_that_disagrees_is_reported_and_the_one_that_agrees_is_not(self):
        store = self._store_with_lane_verdicts()
        out = ms.tool_get_disagreements(store, {"item_id": "why-alpha"})
        lanes = {lane["lane"]: lane for lane in out["lanes"]}
        self.assertFalse(lanes["lane/fast"]["agrees_with_deterministic"])
        self.assertTrue(lanes["lane/deep"]["agrees_with_deterministic"])
        self.assertEqual([d["lane"] for d in out["disagreements"]], ["lane/fast"])

    def test_the_two_lanes_are_reported_as_disagreeing_with_each_other(self):
        store = self._store_with_lane_verdicts()
        out = ms.tool_get_disagreements(store, {"item_id": "why-alpha"})
        pairs = out["lane_disagreements"]
        self.assertEqual(len(pairs), 1)
        self.assertEqual(sorted(pairs[0]["lanes"]), ["lane/deep", "lane/fast"])
        self.assertEqual(len(pairs[0]["citations"]), 2)

    def test_an_item_with_no_lane_verdicts_has_no_disagreements(self):
        # why-alpha in the repo's own fixture has no verdict rows; the lanes
        # live in the recorded run, not in the evidence file.
        out = ms.tool_get_disagreements(ms.Store(FIXTURE), {"item_id": "why-alpha"})
        self.assertEqual(out["lanes"], [])
        self.assertEqual(out["disagreements"], [])
        self.assertEqual(out["lane_disagreements"], [])


class WireTests(unittest.TestCase):
    """The MCP wire: JSON-RPC over stdio, protocol 2026-07-28."""

    def setUp(self):
        self.store = ms.Store(FIXTURE)

    def test_initialize_echoes_a_version_it_supports(self):
        for version in ms.PROTOCOL_VERSIONS:
            out = ms.handle(self.store, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                         "params": {"protocolVersion": version}})
            self.assertEqual(out["result"]["protocolVersion"], version)
            self.assertEqual(out["result"]["serverInfo"]["name"], ms.SERVER_NAME)
            self.assertIn("tools", out["result"]["capabilities"])

    def test_an_unsupported_version_is_an_error_that_names_the_supported_ones(self):
        out = ms.handle(self.store, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                     "params": {"protocolVersion": "1999-01-01"}})
        self.assertEqual(out["error"]["code"], -32602)
        self.assertIn("supported", out["error"]["data"])

    def test_tools_list_returns_the_three_tools(self):
        out = ms.handle(self.store, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(out["result"]["resultType"], "complete")
        self.assertEqual(len(out["result"]["tools"]), 3)

    def test_a_tool_call_returns_content_and_structured_content(self):
        out = ms.handle(self.store, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                     "params": {"name": "get_verdict",
                                                "arguments": {"item_id": "why-alpha"}}})
        result = out["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(result["content"][0]["type"], "text")
        self.assertIn("CONFLICTED", result["content"][0]["text"])
        self.assertEqual(result["structuredContent"]["verdict"], "CONFLICTED")

    def test_a_refused_call_is_a_tool_error_the_model_can_read(self):
        out = ms.handle(self.store, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                     "params": {"name": "submit_claims",
                                                "arguments": {"claims": [
                                                    {"item_id": "why-alpha", "statement": "x",
                                                     "verdict": "CORROBORATED"}]}}})
        self.assertTrue(out["result"]["isError"])
        self.assertIn("verdict", out["result"]["content"][0]["text"])

    def test_an_unknown_tool_is_a_protocol_error(self):
        out = ms.handle(self.store, {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                                     "params": {"name": "ask_the_model"}})
        self.assertEqual(out["error"]["code"], -32602)

    def test_a_notification_gets_no_answer(self):
        self.assertIsNone(ms.handle(self.store, {"jsonrpc": "2.0",
                                                 "method": "notifications/initialized"}))

    def test_serve_answers_one_json_line_per_request(self):
        import io
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": ms.PROTOCOL_VERSIONS[0]}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]
        stdin = io.StringIO("\n".join(json.dumps(r) for r in requests) + "\n")
        stdout = io.StringIO()
        ms.serve(self.store, stdin=stdin, stdout=stdout)
        answers = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual([a["id"] for a in answers], [1, 2])


class NoWriteTests(unittest.TestCase):
    """The card says no write path that mutates evidence files on disk."""

    def test_submitting_claims_does_not_touch_the_file(self):
        before = open(FIXTURE, "rb").read()
        store = ms.Store(FIXTURE)
        ms.tool_submit_claims(store, {"claims": [
            {"item_id": "why-alpha", "statement": "a new claim", "kind": "receipt"}]})
        after = open(FIXTURE, "rb").read()
        self.assertEqual(before, after, "the evidence file must not change")


if __name__ == "__main__":
    unittest.main()
