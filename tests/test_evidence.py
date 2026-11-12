import unittest
from types import SimpleNamespace

from knowledge.evidence import History
from knowledge.extract import extract_page
from knowledge.schema import PageRecord


def page(text, path="rates", title="Rates"):
    return PageRecord("https://example.test/" + path, title, text, "2026-01-01T10:00:00Z")


def capture(day, *pages):
    return SimpleNamespace(snapshot_id="capture-" + day, taken_on=day, pages=list(pages))


class EvidenceTests(unittest.TestCase):
    def test_inventory_membership_replay_and_atomicity(self):
        history = History()
        source = page("# Certificates\n6-month certificate APY: 3.12%")
        january = capture("2026-01-10", source)
        history.add(january)
        history.add(capture("2026-02-01"))
        history.add(capture("2026-03-01", page(source.markdown.replace("3.12", "4.44"), "deposits")))
        history.add(january)
        self.assertIsNone(history.at("2026-01-01"))
        self.assertIsNone(history.at("bad-date"))
        self.assertEqual(history.at("2026-02-20").claims, ())
        self.assertEqual(history.at("2026-01-15").claims[0].value, "3.12%")
        self.assertEqual(history.at().claims[0].value, "4.44%")
        self.assertTrue(history.at().claims[0].evidence.url.endswith("/deposits"))
        self.assertEqual(len(history.between("2026-01-10", "2026-03-01")), 3)
        with self.assertRaises(ValueError):
            history.add(capture("2026-01-10", page("Unrelated text")))
        with self.assertRaises(ValueError):
            history.add(capture("2026-04-01", source, source))
        self.assertEqual(history.at().taken_on, "2026-03-01")

    def test_provenance_rebound_for_identical_bytes_and_scope(self):
        h = History()
        text = ("# Rates\nElm Savings\n| Balance | Dividend Rate | APY |\n"
                "| --- | --- | --- |\n| $1,000+ | 3.10% | 3.15%1 |\n"
                "Effective as of 02/01/2026\n\nOak Savings\n"
                "| Balance | Dividend Rate | APY |\n| --- | --- | --- |\n"
                "| Under $1,000 | 1.10% | 1.15%2 |\nEffective as of 01/01/2026")
        first, second = page(text), page(text, "products/other", "Deposit accounts")
        h.add(capture("2026-02-10", first, second))
        h.add(capture("2026-02-20", first, second))
        for v in h.views:
            self.assertEqual(len(v.claims), 8)
            for c in v.claims:
                self.assertEqual(c.evidence.snapshot_id, v.snapshot_id)
                self.assertIn(c.evidence.quote, text)
                self.assertIn("APY", c.evidence.headings[-1])
                self.assertIn(c.evidence, v.passages)
                if c.key.product == "elm savings":
                    self.assertEqual(c.evidence.effective_from, "2026-02-01")
                    self.assertTrue(c.key.bounds[0].contains(1000))
                else:
                    self.assertEqual(c.key.product, "oak savings")
                    self.assertEqual(c.evidence.effective_from, "2026-01-01")
                    self.assertFalse(c.key.bounds[0].contains(1000))
            self.assertEqual({x.evidence.url for x in v.claims}, {first.url, second.url})

    def test_vehicle_range_and_certificate_variants(self):
        text = ("# Rates\nAuto and Motorcycle Loans\n| Loan Program | Term | APR |\n"
                "| --- | --- | --- |\n| 2027-24 Model Year | 3 Years | 6.24%1 |\n\n"
                "Special Certificates\n| Certificate | APY |\n| --- | --- |\n"
                "| 9 Month Jumbo Certificate Special | 4.00%2 |\n| 9 Month Certificate Special | 3.75%1 |")
        claims, _ = extract_page(page(text), "first", "2026-01-01")
        auto, jumbo, regular = claims
        self.assertEqual(auto.key.product, "auto loan")
        bounds = {bound.axis: bound for bound in auto.key.bounds}
        self.assertTrue(bounds["model year"].contains(2026))
        self.assertFalse(bounds["model year"].contains(2022))
        self.assertEqual(bounds["term"].low, 36)
        self.assertEqual(jumbo.key.product, "certificate")
        self.assertNotEqual(jumbo.key.qualifiers, regular.key.qualifiers)

    def test_promotional_period_and_ambiguous_columns(self):
        text = ("# Deposits\n| Account | Dividend Rate for 1st 4 Months | Dividend Rate After Promotional Period | APY | APY |\n"
                "|---|---|---|---|---|\n| Elm Savings | 3.00% | 2.00% | 3.10% | 2.10% |")
        claims, _ = extract_page(page(text), "first", "2026-01-01")
        self.assertEqual([(c.value, dict(c.key.qualifiers)) for c in claims],
                         [("3.00%", {"period": "first 4 months"}), ("2.00%", {"period": "after promotional period"})])

    def test_vehicle_year_columns_and_section_validity(self):
        text = ("## Auto Loan APR by Model Year\nEffective from January 25, 2026\n"
                "| Term | 2023-25 | 2026-27 |\n|---|---|---|\n| 48 months | 5.91% | 5.51% |")
        claims, _ = extract_page(page(text), "first", "2026-02-01")
        self.assertEqual(len(claims), 2)
        for c, year in zip(claims, (2024, 2027)):
            bounds = {b.axis: b for b in c.key.bounds}
            self.assertEqual(c.key.measure, "apr")
            self.assertTrue(bounds["model year"].contains(year))
            self.assertFalse(bounds["model year"].contains(2022))
            self.assertEqual(bounds["term"].low, 48)
            self.assertEqual(c.evidence.effective_from, "2026-01-25")

    def test_fee_unit_and_exemption(self):
        text = ("## Fee Schedule\n**Effective January 10, 2026**\n"
                "| Services | Cost |\n|---|---|\n"
                "| Paid overdraft | $12.00 per item. Waived on transactions under $4.00. |\n")
        claims, _ = extract_page(page(text, "fee-schedule", "Fee Schedule"), "a", "2026-02-01")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].value, "$12.00 per item")
        self.assertIn("Waived", claims[0].evidence.quote)
        self.assertEqual(claims[0].evidence.effective_from, "2026-01-10")

    def test_publication_and_expiry_are_not_fetch_dates(self):
        text = ("June 10, 2025\n# Summer promotion\n"
                "6-month certificate APY: 2.95% (offer ended 2025-09-30)")
        claims, _ = extract_page(page(text, "news/summer", "Promotion"), "first", "2026-01-10")
        self.assertEqual(claims[0].evidence.published_on, "2025-06-10")
        self.assertEqual(claims[0].evidence.effective_until, "2025-09-30")
        self.assertEqual(claims[0].evidence.source_class, "news")

    def test_promotion_eligibility_across_ingestion_and_member_answer(self):
        from knowledge.query import answer_member

        header = "| Balance | APY |\n|---|---|\n"
        standard = page("# Cedar Savings\n" + header + "| $100+ | 1.17% |")
        promo_text = ("# New member offer\nCedar Savings\n" + header + "| $100+ | 4.81% |\n"
                      "This offer is only available to new members.\n"
                      "\n## Everyday products\nAsh Savings\n" + header + "| $100+ | 1.04% |")
        promo = page(promo_text, "products/member-offer", "Member offer")
        h = History()
        h.add(capture("2026-03-01", standard, promo))
        base = "What is the Cedar Savings APY on $200"
        existing = answer_member(h, base + " for an existing member?")
        eligible = answer_member(h, base + " for a new member?")
        missing = answer_member(h, base + "?")
        self.assertTrue(existing.confident)
        self.assertIn("1.17%", existing.text)
        self.assertNotIn("4.81%", existing.text)
        self.assertTrue(eligible.confident)
        self.assertIn("4.81%", eligible.text)
        self.assertTrue(any("only available to new members" in e.quote for e in eligible.sources))
        self.assertFalse(missing.confident)
        self.assertIn("Are you a new or existing member?", missing.text)
        self.assertTrue(answer_member(h, "What is the Ash Savings APY on $200?").confident)

    def test_eligibility_note_stops_at_table_boundary(self):
        table = "| Balance | APY |\n|---|---|\n| $100+ | 2.03% |"
        body = "# Rates\nCedar Savings\n" + table + "\nOnly for new members\n\nAsh Savings\n" + table
        claims, _ = extract_page(page(body), "first", "2026-01-01")
        self.assertEqual(dict(claims[0].key.qualifiers).get("eligibility"), "new members")
        self.assertNotIn("eligibility", dict(claims[1].key.qualifiers))

    def test_fee_markup_and_generic_sentence_are_not_distinct_services(self):
        body = ("# Fee Schedule\n\n_Temporary checks $7.00_ each\n"
                "We will charge $20.00 per item for each scheduled transfer.\n")
        claims, spans = extract_page(page(body, "fee-schedule", "Fee Schedule"), "jan", "2025-01-01")
        self.assertEqual([(c.key.product, c.value) for c in claims], [("temporary checks", "$7.00 per item")])
        self.assertTrue(any(s.quote.startswith("We will charge") for s in spans))
