from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import unittest

from knowledge.evidence import History
from knowledge.query import answer_member
from knowledge.resolve import discover_conflicts
from knowledge.schema import PageRecord


def rates_page(url, value):
    body = (
        "# Deposit rates\n\nShare Savings\n\n"
        "| Balance | Dividend rate | APY |\n| --- | --- | --- |\n"
        f"| $0 to $999.99 | 1.10% | {value} |\n"
        "| $1,000 or more | 2.04% | 2.06% |\n"
    )
    return PageRecord(url, "Rates", body, "2025-01-01")


def snapshot(stamp, *pages):
    return SimpleNamespace(snapshot_id=stamp, taken_on=stamp, pages=pages)


class MemberIntegrationTests(unittest.TestCase):
    def test_paraphrases_preserve_value_and_qualifier_contrasts(self):
        history = History()
        history.add(snapshot("2025-04-15", rates_page("https://union.test/rates", "1.12%")))
        questions = (
            "What is the Share Savings APY at $250?",
            "How much APY do I earn on $250 in Share Savings?",
            "Which annual percentage yield applies to a $250 Share Savings balance?",
            "Share Savings APY, balance $250?",
            "With $250 in share savings, what is my APY?",
            "Tell me the current APY for my Share Savings account with $250.",
            "Can you check the APY for $250 in Share Savings?",
        )
        for question in questions:
            with self.subTest(question=question):
                answer = answer_member(history, question)
                self.assertTrue(answer.confident)
                self.assertIn("1.12%", answer.text)
                self.assertEqual(answer.sources, answer_member(history, questions[0]).sources)
        for query, value in (("Share Savings dividend rate on $250?", "1.10%"),
                             ("Share Savings APY on $1,250?", "2.06%")):
            with self.subTest(query=query):
                self.assertIn(value, answer_member(history, query).text)
        self.assertFalse(answer_member(history, "Unlisted Panther Savings APY on $250?").confident)

    def test_removed_page_new_url_replay_and_threaded_read(self):
        first_page = rates_page("https://union.test/rates", "1.12%")
        last_page = rates_page("https://union.test/deposits/rates", "1.71%")
        jan = snapshot("2025-01-02", first_page)
        mar = snapshot("2025-03-01", last_page)
        history = History()
        for item in (jan, snapshot("2025-02-01"), mar, mar):
            history.add(item)
        prompt = "What is the Share Savings APY on a $250 balance?"
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(lambda t: answer_member(history, prompt, t),
                                   (None, "2025-02-15", "2025-01-18", None)))
        self.assertEqual(result[0], result[3])
        self.assertFalse(result[1].confident)
        for answer, page, obs, value in ((result[2], first_page, jan, "1.12%"),
                                         (result[0], last_page, mar, "1.71%")):
            self.assertTrue(answer.confident)
            self.assertIn(value, answer.text)
            self.assertNotIn("2.06%", answer.text)
            self.assertTrue(answer.sources)
            for source in answer.sources:
                self.assertEqual((source.snapshot_id, source.url), (obs.snapshot_id, page.url))
                self.assertIn(source.quote, page.markdown)
        self.assertEqual(len(history.views), 3)

    def test_two_peers_keep_value_to_source_association(self):
        a = rates_page("https://union.test/one/rates", "1.12%")
        b = rates_page("https://union.test/two/rates", "1.44%")
        history = History()
        history.add(snapshot("2025-01-02", a, b))
        result = answer_member(history, "What is the share savings APY on $250?")
        self.assertFalse(result.confident)
        self.assertEqual({s.url for s in result.sources}, {a.url, b.url})
        conflicts = discover_conflicts(history)
        self.assertEqual(len(conflicts), 1)
        self.assertIsNone(conflicts[0].resolution)
        for value, source in zip(conflicts[0].values, conflicts[0].sources, strict=True):
            self.assertIn(value, source.quote)

    def test_foreign_issuer_uses_no_domestic_rate(self):
        history = History()
        history.add(snapshot("2025-04-15", rates_page("https://river.test/rates", "1.12%")))
        for q in ("What is OtherBank's Share Savings APY?", "What's Foxtail Bank's Share Savings APY?"):
            reply = answer_member(history, q)
            self.assertFalse(reply.confident)
            self.assertFalse(reply.sources)

    def test_postdated_release_cannot_supply_an_earlier_rate_or_conflict(self):
        history = History()
        future = PageRecord("https://river.test/news/spring", "Certificate news",
                            "March 15, 2025\n# Certificate news\n6-month certificate APY: 6.00%",
                            "2025-01-01")
        history.add(snapshot("2025-01-01", future))
        reply = answer_member(history, "What is the 6-month certificate APY?")
        self.assertFalse(reply.confident)
        self.assertFalse(discover_conflicts(history))
