"""Synthetic questions test provenance and changing site content without the participant kit."""
import unittest

from knowledge.query import answer_view
from knowledge.schema import Inventory, PageRecord


def page(path, title, body):
    return PageRecord("https://www.river.test/" + path, title, body, "2026-07-01")


def capture(*pages):
    return Inventory("capture-july", "2026-07-01", pages, (), ())


def ask(view, question, on=None):
    answer = answer_view(view, question, on or view.taken_on)
    for source in answer.sources:
        original = next(p for p in view.pages if p.url == source.url)
        assert source.quote and source.quote in original.markdown
        assert source.snapshot_id == view.snapshot_id
    return answer


class TestProseAnswers(unittest.TestCase):
    def test_routing_replaced_and_foreign_number_excluded(self):
        partner = page("partners", "Partners", "Their routing number is 123654789.")
        for number in ("123456701", "123456799"):
            view = capture(partner, page("operations", "Operations", f"Use our routing number ({number}) for payroll."))
            for q in ("What is River's routing number?", "What is River Credit Union's routing number?",
                      "Can you repeat the routing number?"):
                self.assertEqual(ask(view, q).text, f"The published routing number is {number}.")
            self.assertFalse(ask(view, "What is Lake's routing number?").confident)

    def test_disagreeing_routing_numbers_abstain(self):
        view = capture(page("help", "Help", "Routing number: 123456701"),
                       page("deposit", "Deposit", "Use our routing number (321654987)."))
        result = ask(view, "What is your routing number?")
        self.assertFalse(result.confident)
        self.assertEqual({proof.url for proof in result.sources}, {p.url for p in view.pages})

    def test_routing_evidence_has_the_owner_of_that_occurrence(self):
        foreign = "Their routing number is 111111111."
        own = "Use our routing number (222222222) for payroll."
        for body in (foreign + " " + own, own + " " + foreign,
                     "Their routing number is 111111111, but our routing number is 222222222."):
            result = ask(capture(page("operations", "Payroll", body)), "Can you repeat our routing number?")
            self.assertTrue(result.confident)
            self.assertIn("222222222", result.text)
            self.assertNotIn("111111111", result.text)
            self.assertNotIn("111111111", result.sources[0].quote)

    def test_same_page_disagreeing_routing_numbers_cite_both_occurrences(self):
        view = capture(page("help", "Help", "Our routing number is 123456701. Our routing number is 321654987."))
        result = ask(view, "What is your routing number?")
        self.assertFalse(result.confident)
        self.assertEqual(len(result.sources), 2)
        self.assertTrue(all(any(n in proof.quote for proof in result.sources) for n in ("123456701","321654987")))

    def test_directory_is_scoped_and_not_a_census(self):
        view = capture(page("locations", "Location directory",
                            "# Locations\n### Alder Branch\n11 Elm Rd., River, MO 12345\n"
                            "### Cedar Branch\n92 Hill St., River, MO 12346\n"
                            "### Partner ATM\nSurcharge-Free ATM\n6 Ash St., River, MO 12347"))
        result = ask(view,"List all branches.")
        self.assertIn("Alder",result.text)
        self.assertIn("Cedar",result.text)
        self.assertIn("partial",result.text)
        self.assertNotIn("6 Ash",result.text)
        self.assertEqual(ask(view,"What is the address of Cedar branch?").text,"92 Hill St., River, MO 12346")
        self.assertFalse(ask(view,"What is the address of the Maple branch?").confident)

    def test_branch_schedule_qualifiers_and_local_heading(self):
        view = capture(page("offices", "Our offices",
                            "## Alder Branch\n**Lobby**\nMonday-Friday: 8 a.m.-5 p.m.\n"
                            "**Drive-up**\nMonday-Friday: 7 a.m.-6 p.m.\n"
                            "## Cedar Branch\n**Lobby**\nMonday-Friday: 9 a.m.-4 p.m.\n"
                            "Saturday: 10 a.m.-noon\n"))
        ask_cedar = ask(view,"What are the Saturday lobby hours for the Cedar branch?")
        self.assertIn("10 a.m.-noon",ask_cedar.text)
        self.assertNotIn("9 a.m.",ask_cedar.text)
        self.assertIn("7 a.m.-6 p.m.",ask(view,"What are the Alder drive-up hours on Wednesday?").text)
        self.assertFalse(ask(view,"What are the Cedar drive-up hours?").confident)

    def test_count_describes_the_credit_union_not_a_named_partner(self):
        own = page("about","About River","River now operates 14 branches.")
        partner = page("partners","Partners","Garden Bank has 25 branches.")
        history = page("bio","Director profile","In 1997, our director worked across River's 6 branches.")
        self.assertIn("14",ask(capture(own,partner,history),"How many branches does River have?").text)
        self.assertFalse(ask(capture(partner),"How many branches does River have?").confident)

    def test_announcement_keeps_its_publication_date(self):
        view = capture(page("news/north", "Alder branch opens",
                            "March 12, 2025\n# Alder branch opens\n**Lobby**\nMonday-Friday: 10 a.m.-4 p.m."))
        self.assertIn("announced 2025-03-12",ask(view,"What are the Alder branch lobby hours?").text)
        self.assertFalse(ask(view,"What are the Birch branch lobby hours?").confident)

    def test_closure_date_is_read_from_announcement(self):
        for when in ("August 31, 2026", "October 17, 2026"):
            view = capture(page("news/closure","Willow branch closure",
                                f"June 1, 2026\n# Willow branch closure\nThis location will close {when}."))
            self.assertIn(when,ask(view,"When does the Willow branch close?").text)
            self.assertFalse(ask(view,"When does the Cypress branch close?").confident)

    def test_two_closures_on_one_page_keep_their_branch(self):
        cedar = "Cedar branch will close February 3, 2026"
        birch = "Birch branch will close March 8, 2026"
        for separator in (". ", "\n", "; ", " and "):
            view = capture(page("news/closures", "Branch announcements", cedar + separator + birch + "."))
            result = ask(view, "When will the Birch branch close?")
            self.assertEqual(result, ask(view, "When does the Birch branch close?"))
            self.assertTrue(result.confident)
            self.assertIn("March 8, 2026",result.text)
            self.assertIn(birch,result.sources[0].quote)
            self.assertNotIn("Cedar",result.sources[0].quote)

    def test_rate_link_is_supported_by_its_product_section(self):
        mortgage = page("mortgages","Mortgage rates",
                        "# Mortgage rates\nCertificates are another product. [Mortgage rates](#rates)")
        certificates = page("deposits","Deposit products",
                            "## Certificates\n[View rates](#deposit-rates)")
        q = "What link should I use to see certificate rates?"
        self.assertFalse(ask(capture(mortgage), q).confident)
        result = ask(capture(mortgage, certificates), q)
        self.assertEqual(result.text, "https://www.river.test/deposits#deposit-rates")
        self.assertTrue(any("## Certificates" in proof.quote for proof in result.sources))

    def test_membership_application_link_is_resolved_from_page(self):
        view = capture(page("join","Join", "# Who can join\n## Eligible to join\n"
                            "- You live in North County.\n- Your parent belongs to the union.\n"
                            "[Become a member](/applications/enroll)"))
        self.assertIn("North County",ask(view,"Who is eligible to join?").text)
        self.assertIn("Your parent",ask(view,"Who is eligible to join?").text)
        self.assertIn("https://www.river.test/applications/enroll",ask(view,"How do I join River online?").text)

    def test_award_uses_dated_source_available_at_cutoff(self):
        old=page("news/old","Beacon honors River credit union",
                 "April 2, 2025\n# Beacon awards\nThis was the second time Beacon recognized River.")
        new=page("news/new","Beacon honors River credit union",
                 "June 8, 2026\n# Beacon awards\nThis was the third time Beacon recognized River.")
        view=capture(old,new)
        q="What recognition has River received from Beacon?"
        self.assertIn("third",ask(view,q).text)
        self.assertIn("second",ask(view,q,"2026-05-01").text)

    def test_missing_reporting_year_is_not_inferred(self):
        view=capture(page("news/service","Staff service",
                          "March 10, 2025\n25 River employees used Volunteer Time Off in 2024."),
                     page("news/newer","Community involvement",
                          "March 10, 2026\nIn 2025, our 130 employees volunteered 870 hours, with many using their VTO."))
        result=ask(view,"How many employees used volunteer time off last year?")
        self.assertFalse(result.confident)
        self.assertIn("2025",result.text)
        self.assertIn("25 employees in 2024",result.text)
        self.assertNotIn("130",result.text)
        self.assertNotIn("870",result.text)

    def test_unsupported_wallet_is_not_inferred(self):
        view=capture(page("mobile-payments","Mobile payments",
                          "Add your credit cards to Ember Pay or River Pay."))
        result=ask(view,"Can I add my credit card to a mobile wallet?")
        self.assertIn("Ember Pay",result.text)
        self.assertFalse(ask(view,"Can my credit card use Canyon Pay?").confident)


if __name__ == "__main__":
    unittest.main()
