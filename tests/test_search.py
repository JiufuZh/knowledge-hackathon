import unittest
from dataclasses import replace

from knowledge.schema import Evidence, Inventory
from knowledge.search import search_passages


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.proof = Evidence("spring", "2025-05-01", "https://example.test/transfer",
                              "Transfer services", "product", ("Transfer services",),
                              "A shuttle transfer requires a boarding pass.")
        self.view = Inventory("spring", "2025-05-01", (), (), (self.proof,))

    def test_answer_tracks_the_sentence_and_source(self):
        for proof in (self.proof, replace(self.proof, url="https://example.test/forms",
                                          quote="A shuttle transfer requires a transfer form.")):
            view = replace(self.view, passages=(proof,))
            answer = search_passages(view, "What does a shuttle transfer require?", view.taken_on)
            self.assertTrue(answer.confident)
            self.assertEqual(answer.sources, (proof,))
            self.assertEqual(answer.text, proof.quote)

    def test_wrong_entity_and_expired_support(self):
        answer = search_passages(self.view, "What does an airship transfer require?", self.view.taken_on)
        self.assertFalse(answer.confident)
        expired = replace(self.proof, effective_until="2025-04-29")
        view = replace(self.view, passages=(expired,))
        self.assertFalse(search_passages(view, "What does a shuttle transfer require?", view.taken_on).confident)
