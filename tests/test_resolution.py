import unittest
from dataclasses import replace
from types import SimpleNamespace

from knowledge.rates import answer_rates
from knowledge.resolve import discover_conflicts, resolve
from knowledge.schema import Bound, Claim, Evidence, FactKey, Inventory


JAN = "2024-01-15"
FEB = "2024-02-15"
KEY = FactKey("example.test", "harbor savings", "personal", "apy")


def observed(value, key=KEY, *, source="rate_sheet", date=JAN, url="rates", **dates):
    evidence = Evidence(date, date, f"https://example.test/{url}", "Rate information",
                        source, (), f"Published value {value}", **dates)
    return Claim(key, value, evidence)


def inventory(*claims, date=JAN):
    return Inventory(date, date, (), claims, ())


class ResolutionTests(unittest.TestCase):
    def test_only_applicable_tier_at_boundary(self):
        low = replace(KEY, bounds=(Bound("balance", "dollars", None, 750, high_inclusive=False),))
        high = replace(KEY, bounds=(Bound("balance", "dollars", 750),))
        claims = (observed("1.3%", low), observed("2.1%", high), observed("11%", high, source="calculator"),
                  observed("13%", high, effective_until="2024-01-01"))
        boundary = replace(KEY, bounds=(Bound("balance", "dollars", 750, 750),))
        result = resolve(claims, boundary, JAN)
        self.assertEqual([c.value for c in result.winners], ["2.1%"])
        self.assertEqual([c.value for c in result.competitors], ["11%"])
        result = answer_rates(inventory(*claims), "What APY does Harbor Savings pay on $749?", JAN)
        self.assertTrue(result.confident)
        self.assertIn("1.3%", result.text)
        self.assertNotIn("2.1%", result.text)

    def test_range_must_support_both_endpoints(self):
        tier = replace(KEY, bounds=(Bound("balance", "dollars", 100, 200),))
        claim = observed("3.7%", tier)
        result = answer_rates(inventory(claim), "Harbor Savings APY between $150 and $250?", JAN)
        self.assertFalse(result.confident)

    def test_purchase_amount_selects_narrowest_published_ceiling(self):
        key = FactKey("example.test", "mortgage", "personal", "interest rate", (("purpose", "purchase"),))
        tiers = [observed(x, replace(key, bounds=(Bound("amount", "dollars", None, ceil),)))
                 for ceil, x in [(150000, "2.7%"), (300000, "3.7%")]]
        result = answer_rates(inventory(*tiers), "What mortgage rate for $150k?", JAN)
        self.assertIn("2.7%", result.text)
        self.assertNotIn("3.7%", result.text)
        note = answer_rates(inventory(*tiers), "What is the 5/1 ARM rate for $150k?", JAN)
        self.assertFalse(note.confident)

    def test_peers_dispute_keeps_sources_and_never_guesses(self):
        a, b = observed("2%", url="north"), observed("3%", url="south")
        result = resolve([a, b], KEY, JAN)
        self.assertEqual(result.status, "disputed")
        result = answer_rates(inventory(a, b), "What is the Harbor Savings APY?", JAN)
        self.assertFalse(result.confident)
        self.assertEqual(set(result.sources), {a.evidence, b.evidence})
        april = replace(KEY, measure="interest rate")
        report = discover_conflicts(SimpleNamespace(views=[inventory(a, b, observed("5%", april))]))
        self.assertEqual(len(report), 1)
        self.assertEqual(set(report[0].values), {"2%", "3%"})
        self.assertIsNone(report[0].resolution)

    def test_intersecting_rate_bands_are_a_conflict_only_where_they_overlap(self):
        a = observed("1.31%", replace(KEY, bounds=(Bound("balance", "dollars", 0, 200),)), url="schedule-one")
        b = observed("1.73%", replace(KEY, bounds=(Bound("balance", "dollars", 170, 300),)), url="schedule-two")
        report = discover_conflicts(SimpleNamespace(views=[inventory(a, b)]))
        self.assertEqual(len(report), 1)
        self.assertIn("$170 to $200", report[0].topic)
        self.assertIsNone(report[0].resolution)
        below = answer_rates(inventory(a, b), "Harbor Savings APY with $150?", JAN)
        inside = answer_rates(inventory(a, b), "Harbor Savings APY with $190?", JAN)
        self.assertIn("1.31%", below.text)
        self.assertFalse(inside.confident)

    def test_examples_only_count_with_a_same_scope_published_fact(self):
        short = replace(KEY, bounds=(Bound("term", "months", 9, 9),))
        official = observed("4%", short)
        stale = observed("3%", short, source="calculator", url="calculator")
        sample = replace(observed("5%", short, source="product", url="illustration"),
                         evidence=replace(stale.evidence, source_class="product", url="illustration",
                                          quote="For illustrative purposes only: the example earns 5%."))
        report = discover_conflicts(SimpleNamespace(views=[inventory(official, stale)]))
        self.assertEqual(len(report), 1)
        self.assertEqual(set(report[0].sources), {official.evidence, stale.evidence})
        self.assertEqual(report[0].resolution, "4%")
        self.assertFalse(discover_conflicts(SimpleNamespace(views=[inventory(stale, sample)])))
        self.assertFalse(discover_conflicts(SimpleNamespace(views=[inventory(stale, observed("4%"))])))
        self.assertEqual(resolve([sample, stale], short, JAN).status, "insufficient")

    def test_only_comparable_changes_and_active_reasons(self):
        a = observed("2.30%")
        same = observed("2.3 %", url="also")
        b = observed("2.65%", date=FEB)
        history = SimpleNamespace(views=[inventory(a, same), inventory(b, date=FEB)])
        report = discover_conflicts(history)
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0].resolution, "2.65%")
        self.assertEqual({e.taken_on for e in report[0].sources}, {JAN, FEB})
        history.views.insert(1, inventory(date="2024-02-01"))
        self.assertFalse(discover_conflicts(history))

    def test_new_member_offer_is_conditional_and_qualifier_sensitive(self):
        base = observed("2%")
        new_key = replace(KEY, qualifiers=(("eligibility", "new members"),))
        offer = observed("5%", new_key)
        current = resolve([base, offer], replace(KEY, qualifiers=(("eligibility", "existing members"),)), JAN)
        self.assertEqual(current.winners, (base,))
        self.assertEqual(resolve([base, offer], new_key, JAN).winners, (offer,))
        self.assertEqual(resolve([base, offer], KEY, JAN).status, "insufficient")
        answer = answer_rates(inventory(base, offer), "Harbor Savings APY for existing members?", JAN)
        self.assertNotIn("5%", answer.text)
        answer = answer_rates(inventory(base, offer), "Harbor Savings APY for new members?", JAN)
        self.assertNotIn("2%", answer.text)

    def test_scope_values_dates_and_sources_follow_mutations(self):
        key = replace(KEY, bounds=(Bound("balance", "dollars", 0),))
        for value, url, day in [("3.41%", "lantern", JAN), ("2.82%", "lighthouse", FEB)]:
            claim = observed(value, key, url=url, date=day)
            got = answer_rates(inventory(claim, date=day), "Harbor Savings interest rates?", day)
            self.assertIn(value, got.text)
            self.assertEqual(got.sources, (claim.evidence,))
            missing = answer_rates(inventory(claim), "What rate on Panther Savings?", day)
            self.assertFalse(missing.confident)

    def test_explicit_dates_control_corrections(self):
        original = observed("4.2%")
        correction = observed("4.8%", date=FEB, effective_from="2024-01-01", url="errata")
        before = resolve([original], KEY, JAN)
        after = resolve([original, correction], KEY, JAN)
        self.assertEqual(before.winners, (original,))
        self.assertEqual(after.winners, (correction,))

    def test_explicit_dividend_and_yield_select_their_own_columns(self):
        dividend = observed("2.43%", replace(KEY, measure="dividend rate"))
        apy = observed("2.46%")
        view = inventory(dividend, apy)
        for q, expected in [("What dividend does Harbor Savings pay?", dividend),
                            ("What is the dividend rate for Harbor Savings?", dividend),
                            ("I need the dividend rate, not the APY, for Harbor Savings.", dividend),
                            ("What is the annual percentage yield for Harbor Savings?", apy)]:
            with self.subTest(q=q):
                result = answer_rates(view, q, JAN)
                self.assertEqual(result.sources, (expected.evidence,))
                self.assertIn(expected.value, result.text)
        both = answer_rates(view, "What are the APY and dividend rate for Harbor Savings?", JAN)
        self.assertEqual(set(both.sources), {apy.evidence, dividend.evidence})

    def test_mortgage_amount_above_maximum_is_never_a_quoted_tier(self):
        key = FactKey("example.test", "mortgage", "personal", "interest rate", (("purpose", "purchase"),),
                      (Bound("amount", "dollars", None, 175000), Bound("term", "months", 360, 360)))
        view = inventory(observed("3.71%", key))
        for amount in ["$176,000", "above $175,000", "176,000 dollars"]:
            with self.subTest(amount=amount):
                result = answer_rates(view, f"What is the rate on a 30-year fixed mortgage for {amount}?", JAN)
                self.assertFalse(result.confident)
                self.assertNotIn("3.71%", result.text)

    def test_explanation_distinguishes_dissent_from_the_official_term(self):
        key = replace(KEY, product="certificate", bounds=(Bound("term", "months", 9, 9),))
        a, b = observed("2.47%", key), observed("2.37%", key, source="calculator", url="estimate")
        other = observed("1.43%", replace(key, bounds=(Bound("term", "months", 12, 12),)), url="annual")
        view = inventory(a, b, other)
        result = answer_rates(view, "Why do the sources disagree about the nine-month certificate APY?", JAN)
        self.assertTrue(result.confident)
        self.assertEqual(set(result.sources), {a.evidence, b.evidence})
        for value in (a.value, b.value, "calculator"):
            self.assertIn(value, result.text)
        self.assertNotIn(other.value, result.text)
        current = answer_rates(view, "What is the nine-month certificate APY?", JAN)
        self.assertNotIn(b.value, current.text)

    def test_fee_waiver_conditions_survive_value_normalization(self):
        key = replace(KEY, product="consumer overdraft fee", measure="fee")
        base = observed("$17 per item", key, source="fee_schedule")
        policy = "| Consumer overdraft fee | $17 per item. No fee is charged if the transaction is below $4.50. Maximum one fee per day. |"
        claim = replace(base, evidence=replace(base.evidence, quote=policy))
        view = inventory(claim)
        general = answer_rates(view, "What is the consumer overdraft fee?", JAN)
        self.assertIn("below $4.50", general.text)
        self.assertIn("one fee per day", general.text)
        specific = answer_rates(view, "Do you waive the consumer overdraft fee on a $3 transaction?", JAN)
        self.assertTrue(specific.confident)
        self.assertIn("no fee", specific.text.lower())
        self.assertEqual(specific.sources, (claim.evidence,))


if __name__ == "__main__":
    unittest.main()
