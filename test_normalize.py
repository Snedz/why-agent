"""Offline tests for the normalization module and its lane integration.

    python3 -m unittest test_normalize -v

The examiner must examine itself. These tests pin two things at once: the
cases from the live 2026-10-30 Tavily run that verbatim matching got
wrong ("October 30" for "Oct 30", "1,000 API credits" for "1,000
credits"), and the hard negatives a looser matcher would get wrong the
other way — a different day, a different number, a phone number off by
one digit. A normalization that matches everything is worse than
verbatim, so the negatives are the load-bearing half of this file.
"""
import dataclasses
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import evidence as ev  # noqa: E402
import normalize as nz  # noqa: E402
import tavily_lane as tl  # noqa: E402

RETRIEVED_AT = "2026-10-30T05:01:00Z"


def method(claim, text):
    return nz.explain_match(claim, text).method


class DateMatchTests(unittest.TestCase):
    def test_full_month_name_matches_abbreviated_claim(self):
        self.assertEqual(
            method("Oct 30", "Submissions close October 30 at 1:00 PM EDT."),
            "normalized:date")

    def test_day_first_order_matches(self):
        self.assertEqual(method("Oct 30", "Apply by 30 Oct to enter."),
                         "normalized:date")
        self.assertEqual(method("Oct 30", "Apply by 30 October 2026."),
                         "normalized:date")

    def test_abbreviated_month_with_dot_matches(self):
        self.assertEqual(method("November 3", "Entries close Nov. 3."),
                         "normalized:date")

    def test_iso_claim_matches_written_out_date(self):
        self.assertEqual(
            method("2026-10-30", "Submissions close October 30, 2026."),
            "normalized:date")

    def test_verbatim_still_wins_when_the_string_is_there(self):
        self.assertEqual(method("Oct 30", "Submissions close Oct 30."),
                         "verbatim")

    def test_a_different_day_does_not_match(self):
        self.assertEqual(method("Oct 30", "Submissions close October 31."),
                         "none")
        self.assertEqual(method("November 3", "Entries close November 13."),
                         "none")
        self.assertEqual(method("November 3", "Winners named Nov 30."),
                         "none")

    def test_november_3_does_not_match_november_30(self):
        # The substring wart, fixed deliberately: "November 3" is a
        # substring of "November 30", and the old verbatim rule credited
        # it. Verbatim is now the delimited-occurrence rule (see
        # VerbatimBoundaryTests), so this page is a miss in every mode:
        # the date it states is the 30th, not the 3rd.
        self.assertEqual(method("November 3", "Winners named November 30."),
                         "none")

    def test_a_different_single_digit_day_does_not_match(self):
        self.assertEqual(method("Oct 30", "The October 3 reading list."),
                         "none")

    def test_a_conflicting_year_does_not_match(self):
        self.assertEqual(
            method("Oct 30 2026", "Submissions close October 30, 2025."),
            "none")

    def test_month_and_day_as_separate_facts_do_not_match(self):
        # The Zetaris failure mode, guarded: a page that mentions November
        # and the number 3 in unrelated places has not stated a deadline.
        self.assertEqual(
            method("November 3",
                   "In November the judges reviewed 3 finalists "
                   "and 12 demos."),
            "none")
        self.assertEqual(
            method("November 3",
                   "Data Day with Zetaris: a November recap of the "
                   "agent hackathon."),
            "none")


class VerbatimBoundaryTests(unittest.TestCase):
    """Verbatim means a delimited occurrence, not a substring.

    The old rule was raw substring appearance, which credited accidents:
    "November 3" inside "November 30", "1,000 credits" inside "10,000
    credits". These tests pin the tightened rule in both directions —
    the accidents must miss, and the genuinely stated values, including
    punctuation-delimited ones, must still hit. The primitive under test
    is normalize.contains_verbatim; explain_match and the lane both
    delegate to it, so the definition lives in exactly one place.
    """

    cv = staticmethod(nz.contains_verbatim)

    # The four claim strings from tonight's live ablation set.

    def test_november_3_inside_november_30_does_not_credit(self):
        self.assertFalse(self.cv("November 3", "Winners named November 30."))
        self.assertFalse(self.cv("November 3", "It ends November 30, 2026."))

    def test_november_3_stated_plainly_credits(self):
        self.assertTrue(
            self.cv("November 3", "entries close November 3, 2026"))
        self.assertTrue(
            self.cv("November 3", "Entries close Tuesday November 3."))

    def test_oct_30_credits_and_digit_neighbours_block_it(self):
        self.assertTrue(self.cv("Oct 30", "Submissions close Oct 30 at 1 PM."))
        # A trailing digit makes it a different string entirely: the page
        # states "Oct 300", which is not the claimed value in any form.
        self.assertFalse(self.cv("Oct 30", "Submissions close Oct 300."))
        self.assertFalse(self.cv("Oct 30", "the Oct 305 panel"))

    def test_credits_inside_a_bigger_number_does_not_credit(self):
        # "1,000 credits" occurs inside "10,000 credits" starting at the
        # second character, preceded by a digit: not a delimited hit.
        self.assertFalse(
            self.cv("1,000 credits", "The plan includes 10,000 credits."))
        self.assertFalse(
            self.cv("1,000 credits", "Get 21,000 credits today."))
        self.assertTrue(
            self.cv("1,000 credits",
                    "The free plan includes 1,000 credits per month."))

    def test_nemotron_boundaries(self):
        self.assertTrue(
            self.cv("Nemotron", "Nemotron 3 Ultra is live on Token Factory."))
        # A hyphen delimits: a compound modifier still states the name.
        self.assertTrue(self.cv("Nemotron", "Runs Nemotron-based pipelines."))
        # A trailing letter does not: "Nemotrons" is a different string.
        self.assertFalse(self.cv("Nemotron", "Nemotrons are great."))

    def test_punctuation_delimits(self):
        # The decided punctuation rule: parentheses, colons, commas and
        # full stops are delimiters, so these credit their claims.
        self.assertTrue(self.cv("Oct 30", "Submissions close (Oct 30)."))
        self.assertTrue(self.cv("Oct 30", "Deadline: Oct 30."))
        self.assertTrue(
            self.cv("November 3", "entries close November 3, 2026"))

    def test_text_edges_count_as_boundaries(self):
        self.assertTrue(self.cv("Oct 30", "Oct 30"))
        self.assertTrue(self.cv("Oct 30", "Oct 30 is the deadline"))

    def test_an_undelimited_occurrence_does_not_mask_a_delimited_one(self):
        # The matcher keeps scanning: a bad occurrence first must not
        # hide a good one later in the same page.
        self.assertTrue(
            self.cv("November 3",
                    "Winners named November 30. Entries close November 3."))

    def test_explain_match_reports_the_tightened_verbatim(self):
        self.assertEqual(
            method("November 3", "entries close November 3, 2026"),
            "verbatim")
        self.assertEqual(method("Oct 30", "Submissions close (Oct 30)."),
                         "verbatim")
        self.assertEqual(method("Nemotron", "Runs Nemotron-based pipelines."),
                         "verbatim")
        # Blocked at the verbatim step; the token rules then see the
        # stemmed plural and call it what it is — a normalized match,
        # never a verbatim one.
        self.assertNotEqual(method("Nemotron", "Nemotrons are great."),
                            "verbatim")


class NumberMatchTests(unittest.TestCase):
    def test_thousands_separator_is_formatting(self):
        self.assertEqual(
            method("1,000 credits",
                   "The free plan includes 1000 credits per month."),
            "normalized:tokens")

    def test_one_intervening_qualifier_matches(self):
        match = nz.explain_match(
            "1,000 credits",
            "The Researcher plan gives 1,000 API credits per month.")
        self.assertEqual(match.method, "normalized:number-gap")
        self.assertIn("api", match.detail)

    def test_decimal_trailing_zero_is_formatting(self):
        self.assertEqual(method("2.50", "A score of 2.5 points."),
                         "normalized:tokens")

    def test_a_bigger_number_does_not_match(self):
        self.assertEqual(
            method("1,000 credits", "The plan includes 10,000 credits."),
            "none")

    def test_a_smaller_number_does_not_match(self):
        self.assertEqual(method("1,000 credits", "You get 100 credits."),
                         "none")

    def test_a_different_unit_does_not_match(self):
        self.assertEqual(
            method("1,000 credits", "The plan includes 1,000 debits."),
            "none")

    def test_two_intervening_tokens_do_not_match(self):
        # The gap is exactly one token. "API calls" between the number and
        # the unit means the page's 1,000 belongs to the calls, and the
        # credits it mentions carry no number at all.
        self.assertEqual(
            method("1,000 credits",
                   "Get 1,000 API calls; credits are sold separately."),
            "none")
        self.assertEqual(
            method("1,000 credits",
                   "Earn 1,000 reward points, not credits."),
            "none")


class PhoneMatchTests(unittest.TestCase):
    def test_parenthesized_area_code_matches(self):
        self.assertEqual(
            method("+1 905-353-8889", "Call us at (905) 353-8889 to book."),
            "normalized:phone")

    def test_country_code_and_dots_match(self):
        self.assertEqual(
            method("905-353-8889", "Reach the salon: +1 (905) 353-8889."),
            "normalized:phone")
        self.assertEqual(
            method("+1 905-353-8889", "Book online or call 905.353.8889."),
            "normalized:phone")

    def test_verbatim_phone_still_reports_verbatim(self):
        self.assertEqual(
            method("+1 905-353-8889", "Call +1 905-353-8889 today."),
            "verbatim")

    def test_the_corpus_conflict_pair_does_not_match(self):
        # The Claim Court corpus's real conflict: the site's number vs the
        # Fresha listing's number. Normalization must never reconcile them.
        self.assertEqual(
            method("+1 905-353-8889",
                   "The Fresha listing shows +1 905-341-6888."),
            "none")

    def test_one_digit_different_does_not_match(self):
        self.assertEqual(method("+1 905-353-8889", "Call 905-353-8880."),
                         "none")


class TokenMatchTests(unittest.TestCase):
    def test_hyphenated_compound_matches(self):
        self.assertEqual(
            method("Token Factory", "Runs on the token-factory platform."),
            "normalized:tokens")

    def test_an_absent_word_does_not_match(self):
        # The Nemotron miss shape: ranking is not evidence, and a page
        # about the platform that never names the model is a non-match in
        # every mode.
        self.assertEqual(
            method("Nemotron",
                   "Built on Nebius Token Factory with NVIDIA models."),
            "none")


class PrimitiveTests(unittest.TestCase):
    def test_extract_dates_canonicalizes_forms(self):
        self.assertEqual(nz.extract_dates("closes October 30, 2026"),
                         [(10, 30, 2026)])
        self.assertEqual(nz.extract_dates("by 30 Oct"), [(10, 30, None)])
        self.assertEqual(nz.extract_dates("on 2026-11-03"), [(11, 3, 2026)])
        self.assertEqual(nz.extract_dates("no dates here"), [])

    def test_canonical_phone(self):
        self.assertEqual(nz.canonical_phone("+1 905-353-8889"), "9053538889")
        self.assertEqual(nz.canonical_phone("905.353.8889"), "9053538889")
        self.assertIsNone(nz.canonical_phone("1,000 credits"))
        self.assertIsNone(nz.canonical_phone("905-353-889"))


class LaneIntegrationTests(unittest.TestCase):
    """results_to_evidence in both modes, over tonight's real page shapes."""

    RESULTS = [
        {"title": "Nebius x NVIDIA Global AI Hackathon - Devpost",
         "url": "https://nebiusglobalaihackathon.devpost.com/",
         "content": "Submissions close October 30 at 1:00 PM EDT."},
        {"title": "Tavily pricing roundup",
         "url": "https://example.invalid/pricing",
         "content": "The Researcher plan gives 1,000 API credits "
                    "per month."},
        {"title": "Nemotron on Token Factory",
         "url": "https://example.invalid/nemotron",
         "content": "Nemotron 3 Ultra is live on Token Factory."},
    ]

    def test_default_mode_is_the_recorded_verbatim_behaviour(self):
        rows = tl.results_to_evidence("it", self.RESULTS, "Oct 30",
                                      RETRIEVED_AT)
        self.assertEqual([r.value for r in rows], ["", "", ""])
        self.assertEqual([r.match_method for r in rows],
                         ["none", "none", "none"])
        rows = tl.results_to_evidence("it", self.RESULTS, "Nemotron",
                                      RETRIEVED_AT)
        self.assertEqual(rows[2].value, "Nemotron")
        self.assertEqual(rows[2].match_method, "verbatim")

    def test_normalized_mode_credits_the_rewritten_values(self):
        rows = tl.results_to_evidence("it", self.RESULTS, "Oct 30",
                                      RETRIEVED_AT, normalize_matches=True)
        hit = rows[0]
        self.assertEqual(hit.value, "Oct 30")
        self.assertEqual(hit.match_method, "normalized:date")
        # The weaker evidence is labelled in the statement, not just the
        # metadata: a reader of the row alone can see what kind it is.
        self.assertIn("normalized:date", hit.statement)

        rows = tl.results_to_evidence("it", self.RESULTS, "1,000 credits",
                                      RETRIEVED_AT, normalize_matches=True)
        hit = rows[1]
        self.assertEqual(hit.value, "1,000 credits")
        self.assertEqual(hit.match_method, "normalized:number-gap")

    def test_normalized_mode_leaves_verbatim_rows_untouched(self):
        rows = tl.results_to_evidence("it", self.RESULTS, "Nemotron",
                                      RETRIEVED_AT, normalize_matches=True)
        hit = rows[2]
        self.assertEqual(hit.match_method, "verbatim")
        # A verbatim hit's statement is the page title, exactly as the
        # lane has always written it — the new mode adds nothing to it.
        self.assertEqual(hit.statement, "Nemotron on Token Factory")

    def test_match_method_survives_the_jsonl_round_trip(self):
        rows = tl.results_to_evidence("it", self.RESULTS, "Oct 30",
                                      RETRIEVED_AT, normalize_matches=True)
        card = {"item_id": "it", "kind": "card", "title": "t",
                "value": "Oct 30"}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "items.jsonl")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(card) + "\n")
                for row in rows:
                    fh.write(json.dumps(dataclasses.asdict(row)) + "\n")
            loaded = ev.load_evidence(path)
        web = [c for c in loaded if c.kind == "web"]
        self.assertEqual(web, rows)


if __name__ == "__main__":
    unittest.main()
