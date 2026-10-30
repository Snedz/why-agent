"""Offline tests for the Zetaris live-evidence lane.

    python3 -m unittest test_zetaris_lane -v

No network, no deployment, no credentials: the HTTP call is behind a
transport seam, and every test stubs it with canned response envelopes.
What these tests prove is the adapter's contract — envelope normalization,
the card-row skip, claim mapping — NOT the live endpoint's shape. That is
verified by the first real query, and docs/ZETARIS_LANE.md says so.
"""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import zetaris_lane as zl  # noqa: E402

ENV = {zl.BASE_URL_ENV: "https://zetaris.example.invalid:8888"}

ROWS_BODY = {
    "rows": [
        {"item_id": "why-beta", "kind": "card", "statement": "beta shipped"},
        {"item_id": "why-beta", "kind": "check", "source": "zetaris-view",
         "locator": "zetaris://evidence_view/why-beta/check",
         "statement": "CI run passed", "value": "passed",
         "observed_at": "2026-10-28T12:00:00Z"},
        {"item_id": "why-beta", "kind": "receipt", "source": "zetaris-view",
         "locator": "zetaris://evidence_view/why-beta/receipt",
         "statement": "deploy receipt not found in the table", "value": "",
         "observed_at": "2026-10-28T12:00:00Z"},
    ]
}

COLUMNAR_BODY = {
    "columns": ["item_id", "kind", "source", "statement", "value"],
    "rows": [
        ["why-alpha", "commit", "zetaris-view", "commit abc landed", "abc"],
    ],
}


def stub_transport(body, captured):
    def send(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        return body
    return send


class RunQueryTests(unittest.TestCase):
    def test_rows_envelope_and_request_shape(self):
        captured = {}
        with mock.patch.dict(os.environ, ENV, clear=False):
            rows = zl.run_query("SELECT * FROM evidence_view",
                                transport=stub_transport(ROWS_BODY, captured))
        self.assertEqual(len(rows), 3)
        self.assertEqual(captured["url"],
                         "https://zetaris.example.invalid:8888/query")
        self.assertEqual(captured["payload"],
                         {"sql": "SELECT * FROM evidence_view"})
        self.assertNotIn("Authorization", captured["headers"])

    def test_bearer_header_only_when_key_set(self):
        captured = {}
        env = dict(ENV, **{zl.API_KEY_ENV: "test-key"})
        with mock.patch.dict(os.environ, env, clear=False):
            zl.run_query("SELECT 1", transport=stub_transport([], captured))
        self.assertEqual(captured["headers"].get("Authorization"),
                         "Bearer test-key")

    def test_columnar_envelope(self):
        with mock.patch.dict(os.environ, ENV, clear=False):
            rows = zl.run_query("SELECT 1",
                                transport=stub_transport(COLUMNAR_BODY, {}))
        self.assertEqual(rows, [{"item_id": "why-alpha", "kind": "commit",
                                 "source": "zetaris-view",
                                 "statement": "commit abc landed",
                                 "value": "abc"}])

    def test_unknown_envelope_is_an_error_not_empty(self):
        with mock.patch.dict(os.environ, ENV, clear=False):
            with self.assertRaises(zl.ZetarisError):
                zl.run_query("SELECT 1",
                             transport=stub_transport({"weird": True}, {}))

    def test_missing_base_url_is_a_config_error(self):
        env = {k: v for k, v in os.environ.items() if k != zl.BASE_URL_ENV}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(zl.ZetarisConfigError):
                zl.run_query("SELECT 1", transport=stub_transport([], {}))


class RowsToEvidenceTests(unittest.TestCase):
    def test_card_rows_skipped_and_claims_mapped(self):
        claims = zl.rows_to_evidence(ROWS_BODY["rows"])
        self.assertEqual(len(claims), 2)
        check, receipt = claims
        self.assertEqual(check.item_id, "why-beta")
        self.assertEqual(check.kind, "check")
        self.assertEqual(check.source, "zetaris-view")
        self.assertEqual(check.value, "passed")
        # The honest non-match survives: an empty value stays empty.
        self.assertEqual(receipt.value, "")
        self.assertIn("not found", receipt.statement)

    def test_fetch_evidence_end_to_end(self):
        with mock.patch.dict(os.environ, ENV, clear=False):
            claims = zl.fetch_evidence(
                "SELECT * FROM evidence_view",
                transport=stub_transport(ROWS_BODY, {}))
        self.assertEqual([c.kind for c in claims], ["check", "receipt"])


if __name__ == "__main__":
    unittest.main()
