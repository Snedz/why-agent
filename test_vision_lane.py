"""Offline tests for the vision (Nemotron VL) evidence lane.

    python3 -m unittest test_vision_lane -v

No network, no third-party package, no real API key: the HTTP call is
behind a transport seam, and every test stubs it with canned VL JSON.
The image fixture is a real file on disk — a 1x1 PNG — because the lane
reads and base64-encodes the file itself, and that read is part of what
is being tested.
"""
import base64
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import providers  # noqa: E402
import vision_lane as vl  # noqa: E402

OBSERVED_AT = "2026-10-28T18:30:00Z"
ENVIRON = {"NEBIUS_API_KEY": "test-key"}
VISION_MODEL = "nvidia/Nemotron-3.5-Super-VL"

# A 1x1 transparent PNG: the smallest real image file the lane can read.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

FULL_EXTRACTION = {
    "amount": "$42.50",
    "date": "2026-10-27",
    "counterparty": "Printify",
    "status_word": "PAID",
    "summary": "Payment receipt from Printify, marked PAID.",
}


def stub_transport(captured, content):
    """A transport that records what it was sent and answers canned VL JSON."""
    def send(base_url, api_key, payload):
        captured["base_url"] = base_url
        captured["api_key"] = api_key
        captured["payload"] = payload
        return {"choices": [{"message": {"content": content}}]}
    return send


class VisionLaneTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.image_path = os.path.join(self._tmp.name, "receipt.png")
        with open(self.image_path, "wb") as fh:
            fh.write(PNG_1X1)

    def extract(self, content, **kwargs):
        captured = kwargs.pop("captured", {})
        rows = vl.extract_receipt_claims(
            self.image_path, "why-vision",
            observed_at=OBSERVED_AT, environ=ENVIRON,
            transport=stub_transport(captured, content), **kwargs)
        return rows, captured

    def test_a_full_extraction_yields_the_expected_rows(self):
        rows, captured = self.extract(json.dumps(FULL_EXTRACTION))
        self.assertEqual(len(rows), 3)
        by_value = {row.value: row for row in rows}

        amount = by_value["$42.50"]
        # The counterparty is a detail about the source, so it rides on
        # the amount row's statement rather than claiming a row itself.
        self.assertEqual(amount.statement,
                         "receipt shows amount $42.50 from Printify")

        date = by_value["2026-10-27"]
        self.assertEqual(date.statement, "receipt is dated 2026-10-27")

        status = by_value["PAID"]
        # The status word is carried literally, as the model returned it;
        # the summary is its statement.
        self.assertEqual(status.statement, FULL_EXTRACTION["summary"])

        for row in rows:
            self.assertEqual(row.item_id, "why-vision")
            self.assertEqual(row.kind, "receipt")
            self.assertEqual(row.source, "nemotron-vl")
            # The citation names the image AND the model that read it, so
            # a reader can re-check the claim against both.
            self.assertEqual(row.locator,
                             f"{self.image_path} via {VISION_MODEL}")
            self.assertEqual(row.observed_at, OBSERVED_AT)
            # The lane sets no aspect: receipt rows take the receipt
            # default (outcome), like every other receipt source.
            self.assertEqual(row.aspect_name, "outcome")

        # The request itself: the profile's vision model, the key from the
        # environment, and the image as a base64 data URI.
        payload = captured["payload"]
        self.assertEqual(payload["model"], VISION_MODEL)
        self.assertEqual(captured["api_key"], "test-key")
        parts = payload["messages"][0]["content"]
        image_part = next(p for p in parts if p["type"] == "image_url")
        self.assertTrue(
            image_part["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_null_fields_yield_no_rows(self):
        # Every field absent: the model saw nothing it could claim, so
        # the lane says nothing either. Absence is not a claim.
        empty = {key: None for key in
                 ("amount", "date", "counterparty", "status_word", "summary")}
        rows, _ = self.extract(json.dumps(empty))
        self.assertEqual(rows, [])

        # A summary on its own states no checkable value, so it still
        # produces no row.
        summary_only = dict(empty, summary="A receipt, otherwise illegible.")
        rows, _ = self.extract(json.dumps(summary_only))
        self.assertEqual(rows, [])

        # Present fields still claim, one row each, and a counterparty
        # with no amount has nothing to ride on.
        partial = dict(empty, amount="18.00", counterparty="Gelato")
        rows, _ = self.extract(json.dumps(partial))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].value, "18.00")
        self.assertEqual(rows[0].statement, "receipt shows amount 18.00 from Gelato")

    def test_a_non_json_response_raises_instead_of_fabricating_rows(self):
        # Prose that merely MENTIONS the fields is not an extraction. The
        # lane raises rather than scraping numbers out of it.
        with self.assertRaises(vl.VisionLaneError):
            self.extract("The receipt shows a total of $42.50 and is PAID.")

    def test_a_fenced_json_response_is_accepted(self):
        # A code fence is packaging, not content: unwrapping it does not
        # change what the model committed to.
        fenced = "```json\n" + json.dumps(FULL_EXTRACTION) + "\n```"
        rows, _ = self.extract(fenced)
        self.assertEqual(len(rows), 3)

    def test_a_missing_api_key_raises_before_any_transport_call(self):
        def forbidden_transport(base_url, api_key, payload):
            raise AssertionError("no request may be sent without a key")

        with self.assertRaises(providers.ProviderError):
            vl.extract_receipt_claims(
                self.image_path, "why-vision",
                observed_at=OBSERVED_AT, environ={},
                transport=forbidden_transport)


if __name__ == "__main__":
    unittest.main()
