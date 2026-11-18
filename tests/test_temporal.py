import unittest
from dataclasses import replace
from types import SimpleNamespace

from knowledge.evidence import History
from knowledge.query import answer_member
from knowledge.resolve import resolve
from knowledge.schema import Claim, Evidence, FactKey, Inventory, PageRecord, Reply
from knowledge.temporal import answer_dated


class DatedFixture:
    def __init__(self):
        key = FactKey("union", "savings", "personal", "apy")
        first = Evidence("jan", "2025-01-01", "https://example.test/rates", "Rates",
                         "rate_sheet", (), "The savings APY is 4%.")
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
    decision = resolve(view.claims, view.claims[0].key, effective_on)
    row = decision.winners[0]
    return Reply(row.value, (row.evidence,))


class TemporalTests(unittest.TestCase):
    def setUp(self):
        self.history = DatedFixture()

    def ask(self, question, cutoff=None):
        return answer_dated(self.history, question, cutoff, read_fixture)

    def restore_january_rate_in_march(self):
        jan = self.history.views[0]
        proof = replace(jan.claims[0].evidence, snapshot_id="mar", taken_on="2025-03-03")
        self.history.views += (replace(jan, taken_on=proof.taken_on, snapshot_id="mar",
                                       claims=(replace(jan.claims[0], evidence=proof),)),)

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
        self.restore_january_rate_in_march()
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

    def test_previous_and_first_capture_comparisons_respect_cutoff(self):
        self.restore_january_rate_in_march()
        for question, cutoff, snapshots in (
            ("How did the APY change since the previous capture?", None, ["feb", "mar"]),
            ("Compare the APYs between the prior and latest snapshots.", None, ["feb", "mar"]),
            ("What was the APY between the first and last captures?", None, ["jan", "mar"]),
            ("Has the APY changed?", None, ["jan", "mar"]),
            ("How did the APY change since the previous capture?", "2025-03-02", ["jan", "feb"]),
        ):
            with self.subTest(question=question, cutoff=cutoff):
                reply = self.ask(question, cutoff)
                self.assertTrue(reply.confident)
                self.assertEqual([s.snapshot_id for s in reply.sources], snapshots)
        self.assertFalse(self.ask("Compare the last two snapshots.", "2025-01-31").confident)

    def test_procedural_change_request_is_a_single_lookup(self):
        self.assertEqual(self.ask("How do I change my mailing address?").text, "5%")

    def test_before_is_exclusive_and_on_or_before_inclusive(self):
        self.restore_january_rate_in_march()
        for phrase, expected in (("immediately before March 3, 2025", "feb"),
                                 ("before 2025-03-03", "feb"),
                                 ("before March 2025", "feb"),
                                 ("on or before March 3, 2025", "mar")):
            with self.subTest(phrase=phrase):
                self.assertEqual(self.ask("What was the APY " + phrase + "?").sources[0].snapshot_id, expected)
        self.assertFalse(self.ask("What was the APY before January 1, 2025?").confident)

    def test_month_uses_the_evidence_available_within_it(self):
        self.restore_january_rate_in_march()
        reply = self.ask("How did APY change from January to March 2025?")
        self.assertTrue(reply.confident)
        self.assertIn("2025-03-03", reply.text)
        self.assertEqual([s.snapshot_id for s in reply.sources], ["jan", "mar"])
        cutoff = self.ask("What was the APY in March 2025?", "2025-03-02")
        self.assertTrue(cutoff.confident)
        self.assertEqual([s.snapshot_id for s in cutoff.sources], ["feb"])
        for question, limit in (("What was the APY on March 4, 2025?", None),
                                ("What was the APY at the end of March 2025?", None),
                                ("What was the APY in April 2025?", None),
                                ("What was the APY?", "2025-03-04")):
            with self.subTest(question=question, cutoff=limit):
                self.assertFalse(self.ask(question, limit).confident)

    def test_bare_interval_keeps_changes_between_its_endpoints(self):
        self.restore_january_rate_in_march()
        for question in ("What was the APY between January and March 2025?",
                         "What was the APY from 2025-01-01 to 2025-03-03?"):
            with self.subTest(question=question):
                reply = self.ask(question)
                self.assertTrue(reply.confident)
                self.assertEqual([s.snapshot_id for s in reply.sources], ["jan", "feb", "mar"])

    def test_year_at_end_of_comparison_applies_to_both_months(self):
        self.restore_january_rate_in_march()
        reply = self.ask("How did the APY change from January to February 2025?", "2026-01-01")
        self.assertTrue(reply.confident)
        self.assertEqual([s.snapshot_id for s in reply.sources], ["jan", "feb"])

    def test_retroactive_amendments_preserve_authority_and_first_publication(self):
        history = History()
        def schedule(path, title, apy):
            body = (f"# {title}\n\nLantern Savings\n\n| Balance | APY |\n"
                    f"| --- | --- |\n| $0 or more | {apy} |\n\nEffective January 1, 2025.")
            return PageRecord("https://ember.test/" + path, title, body, "")

        original = schedule("rates", "Savings rates", "4.23%")
        news = schedule("newsroom/notice", "Corrected rates", "8.91%")
        amendment = schedule("personal/rates", "Corrected rates", "4.67%")
        revision = schedule("member/rates", "Amended rates", "4.82%")
        for month, current in (("01", original), ("02", news), ("03", amendment),
                               ("04", news), ("05", revision), ("06", amendment)):
            day = f"2025-{month}-02"
            history.add(SimpleNamespace(snapshot_id=month, taken_on=day, pages=[current]))
        for cutoff, snapshot, expected in (("2025-01-20", "01", "4.23%"),
                                          ("2025-02-20", "01", "4.23%"),
                                          ("2025-03-20", "03", "4.67%"),
                                          ("2025-04-20", "03", "4.67%"),
                                          ("2025-05-20", "05", "4.82%"),
                                          ("2025-06-02", "05", "4.82%")):
            with self.subTest(cutoff=cutoff):
                reply = answer_member(history, "What Lantern Savings APY was effective January 15, 2025?", cutoff)
                self.assertTrue(reply.confident)
                self.assertIn(expected, reply.text)
                self.assertEqual({e.snapshot_id for e in reply.sources}, {snapshot})
        posted = answer_member(history, "What Lantern Savings APY was posted January 15, 2025?", "2025-06-02")
        self.assertEqual({e.snapshot_id for e in posted.sources}, {"01"})
