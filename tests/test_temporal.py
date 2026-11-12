import unittest
from dataclasses import replace

from knowledge.schema import Claim, Evidence, FactKey, Inventory, Reply
from knowledge.temporal import answer_dated


class DatedFixture:
    def __init__(self):
        key = FactKey("union", "savings", "personal", "apy")
        first = Evidence("jan", "2025-01-01", "https://example.test/rates", "Rates",
                         "rate sheet", (), "The savings APY is 4%.")
        corrected = replace(first, snapshot_id="feb", taken_on="2025-02-01",
                            quote="Correction effective January 1: the savings APY is 5%.",
                            effective_from="2025-01-01")
        self.views = (Inventory("jan", first.taken_on, (), (Claim(key, "4%", first),), ()),
                      Inventory("feb", corrected.taken_on, (), (Claim(key, "5%", corrected),), ()))

    def at(self, cutoff):
        return next((v for v in reversed(self.views) if v.taken_on <= cutoff), None)


def read_fixture(view, question, effective_on):
    if not view.claims:
        return Reply("No rate is listed.", confident=False)
    row = view.claims[0]
    return Reply(row.value, (row.evidence,))


class TemporalTests(unittest.TestCase):
    def setUp(self):
        self.history = DatedFixture()

    def ask(self, question, cutoff=None):
        return answer_dated(self.history, question, cutoff, read_fixture)

    def test_corrected_and_posted_values_have_distinct_sources(self):
        for question, cutoff, expected, source in (
            ("What was posted January 1, 2025?", "2025-02-01", "4%", "jan"),
            ("What was effective January 1, 2025?", "2025-02-01", "5%", "feb"),
            ("What was effective January 1, 2025?", "2025-01-15", "4%", "jan"),
            ("What was the rate as of January 2025?", None, "4%", "jan"),
        ):
            with self.subTest(question=question, cutoff=cutoff):
                answer = self.ask(question, cutoff)
                self.assertEqual((answer.text, answer.sources[0].snapshot_id), (expected, source))

    def test_comparison_cites_each_endpoint(self):
        answer = self.ask("How did the rate change between 2025-01-10 and 2025-02-01?")
        self.assertIn("4%", answer.text)
        self.assertIn("5%", answer.text)
        self.assertEqual([s.snapshot_id for s in answer.sources], ["jan", "feb"])

    def test_timeline_keeps_a_change_that_reverses(self):
        jan = self.history.views[0]
        proof = replace(jan.claims[0].evidence, snapshot_id="mar", taken_on="2025-03-01")
        self.history.views += (replace(jan, taken_on=proof.taken_on, snapshot_id="mar",
                                       claims=(replace(jan.claims[0], evidence=proof),)),)
        answer = self.ask("Show the timeline of the savings rate.")
        self.assertEqual([s.snapshot_id for s in answer.sources], ["jan", "feb", "mar"])
        self.assertIn("5%", answer.text)

    def test_missing_observation_does_not_resurrect_a_value(self):
        self.history.views = (self.history.views[0],
                              replace(self.history.views[1], claims=()))
        self.assertFalse(self.ask("Rate on February 1, 2025?").confident)
        self.assertFalse(self.ask("What changed from January 1 to February 1, 2025?").confident)

    def test_invalid_and_pre_observation_dates(self):
        for question, cutoff in (("Savings rate?", "bad"), ("Rate on 2025-02-30?", None),
                                 ("Savings rate?", "2024-12-31")):
            with self.subTest(question=question, cutoff=cutoff):
                self.assertFalse(self.ask(question, cutoff).confident)

    def test_modal_may_is_not_a_date(self):
        self.assertEqual(self.ask("May I ask the savings rate?").text, "5%")

    def test_future_subject_under_earlier_cutoff_is_not_a_confirmed_observation(self):
        reply = self.ask("What was posted on February 1, 2025?", "2025-01-15")
        self.assertFalse(reply.confident)
        self.assertEqual([p.snapshot_id for p in reply.sources], ["jan"])

    def test_capture_dates_do_not_become_vehicle_model_years(self):
        def capture_question(view, question, on):
            return Reply(question)
        answer = answer_dated(self.history, "What was the 2022 car APR in January 2025?",
                              None, capture_question)
        self.assertIn("2022", answer.text)
        self.assertNotIn("2025", answer.text)
