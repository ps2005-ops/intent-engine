"""A filing names categories, not firms — and that is the competitive read.

WHAT THIS PINS
--------------
`company_specificity` sat at 8.0 on five of seven golden companies, and the
recorded reason was that the subject's own annual filing had not been mined
for competitors. That premise was measured and is false: the filing IS mined,
its Competition section IS located, and it names no company at all.

    Cloudflare:      "on-premises network hardware vendors", "point solution
                      vendors", "content delivery network (CDN) vendors"
    Bank of America: "banks, thrifts, credit unions, investment banking firms
                      ... hedge funds, private equity firms"

Fifteen categories, zero names. The extractor accepted only capitalised proper
nouns, so it discarded the company's own account of its market and fell back
to structural peers.

These tests pin the rule that replaced it — a competitor is whatever the
customer could do instead — and, just as importantly, the two things it must
NOT do: invent a firm to represent a category, and accept any noun phrase that
happens to sit after "replaced".
"""
from __future__ import annotations

import pytest

from intent_engine.executive import competitive_ground as CG
from intent_engine.executive import competitive_ladder as CL


CLOUDFLARE = (
    "Competition. We compete in the market for network services primarily "
    "across three categories:\n"
    "•On-premises network hardware vendors. We compete with companies in this "
    "category to provide security, performance, and reliability services.\n"
    "•Point solution vendors, which provide cloud-based products and services "
    "to address a single use case or challenge, in various categories "
    "including application and network security vendors, content delivery "
    "network (CDN) vendors, and email security vendors."
)

BANK = (
    "Competition. We operate in a highly competitive environment. Our "
    "competitors include banks, thrifts, credit unions, investment banking "
    "firms, brokerage firms, insurance companies, credit card issuers, hedge "
    "funds, private equity firms, and e-commerce and other internet-based "
    "companies."
)

FACTORS_ONLY = (
    "Competition. Our market is transforming, competitive and highly "
    "fragmented. We believe the principal competitive factors in our market "
    "are: •vision for commerce and product strategy; •simplicity and ease of "
    "use for merchants; •pace of innovation."
)


def _categories(text):
    return [r["category"] for r in CL.contested_categories(text, limit=12)]


class TestTheCompanysOwnCategories:
    def test_a_filing_that_names_no_firm_still_names_its_market(self):
        found = _categories(CLOUDFLARE)
        assert "On-premises network hardware vendors" in found
        assert "Point solution vendors" in found

    def test_the_enumeration_inside_a_bullet_is_read_too(self):
        # "...in various categories including application and network
        # security vendors, content delivery network (CDN) vendors..." is
        # where Cloudflare's actual market is named. Reading only the head of
        # the bullet found one category and dropped five.
        assert "content delivery network (CDN) vendors" in _categories(CLOUDFLARE)

    def test_single_word_categories_survive(self):
        # Half of Bank of America's list is single words. Requiring two words
        # discarded the most company-specific competitive statement in the
        # golden set.
        found = _categories(BANK)
        assert "banks" in found and "thrifts" in found
        assert "credit unions" in found

    def test_the_filings_own_order_is_preserved(self):
        found = _categories(BANK)
        assert found.index("banks") < found.index("hedge funds")

    def test_competitive_factors_are_not_competitors(self):
        # A section headed Competition that lists what the company competes
        # ON rather than WHO it competes with must yield nothing. Returning
        # "pace of innovation" as a rival is the fabrication this whole
        # module is bounded against.
        assert _categories(FACTORS_ONLY) == []

    def test_a_price_is_not_a_competitor(self):
        # ISOLATES THE HEAD-NOUN TEST. "Competitive factors" is blocked by the
        # lead-in gate rather than by this one, so mutating the head test left
        # that case passing. Here the lead-in DOES match, and only the head
        # noun stops a price being carried as a rival.
        text = "Competition. We compete with lower prices."
        assert CL.contested_categories(text) == ()

    def test_a_fragment_is_not_a_category(self):
        # "...to provide security, performance, and reliability services"
        # describes what the SUBJECT sells. It reached the Cloudflare table
        # as "and reliability services".
        assert "and reliability services" not in _categories(CLOUDFLARE)

    def test_the_kind_is_decided_by_the_phrase_not_the_sentence(self):
        rows = {r["category"]: r["kind"]
                for r in CL.contested_categories(CLOUDFLARE, limit=12)}
        # Reading the whole sentence made this a platform bundle, because the
        # same sentence mentioned public cloud vendors further along.
        assert rows["Point solution vendors"] == CL.ADJACENT


class TestOnlyTheSubjectsOwnWords:
    def test_a_third_partys_filing_is_not_this_companys_market(self):
        # A run legitimately holds filings that merely MENTION the subject,
        # and their Competition sections describe their own market. One of
        # those put "Online Platforms" — out of a sentiment-trading company's
        # 10-K — into Cloudflare's competitor list.
        documents = [{"source_class": "competitor", "text": BANK}]
        assert CL.competition_text(documents, "Cloudflare") == ""

    def test_the_subjects_own_filing_is_read(self):
        documents = [{"source_class": "investor_material", "text": CLOUDFLARE}]
        assert "Point solution vendors" in CL.competition_text(
            documents, "Cloudflare")


class TestMigrationSentences:
    def test_a_customer_story_names_the_incumbent(self):
        text = ("VIA VAI, a Dutch family footwear brand, migrated from "
                "Magento to Shopify in under three months.")
        rows = CL.migrations(text, "Shopify")
        assert [r["left_behind"] for r in rows] == ["Magento"]

    def test_marketing_prose_is_not_a_competitor(self):
        # Same grammar, no incumbent: "replaced traditional fashion markups
        # with Shopify" reached the table as a named rival.
        text = "The brand replaced traditional fashion markups with Shopify."
        assert CL.migrations(text, "Shopify") == ()

    def test_the_subject_must_be_the_destination(self):
        # The same sentence pointing the other way files the subject's
        # DEPARTURES as its wins.
        text = "The retailer migrated from Shopify to BigCommerce last year."
        assert CL.migrations(text, "Shopify") == ()

    def test_a_migration_between_two_other_companies_is_not_ours(self):
        # ISOLATES THE DESTINATION GUARD. The case above is blocked twice --
        # once because the subject is not the destination, and again because
        # the thing left behind IS the subject -- so removing either guard
        # left it passing and the break proof reported NOT_CAUGHT. This
        # sentence is about two other companies entirely, and only the
        # destination guard stops "Magento" being filed as Shopify's rival.
        text = "The retailer migrated from Magento to BigCommerce last year."
        assert CL.migrations(text, "Shopify") == ()

    def test_a_way_of_working_is_a_rung_of_its_own(self):
        text = ("The team switched from spreadsheets to Acme in a single "
                "quarter.")
        rows = CL.migrations(text, "Acme")
        assert rows and rows[0]["kind"] == CL.MANUAL_WORKFLOW
        assert rows[0]["rung"] == CL.WORKFLOW_SUBSTITUTE


class TestEveryRowIsAClaim:
    def test_a_rival_without_a_mechanism_is_refused(self):
        with pytest.raises(CL.RivalRefused):
            CL.Rival(identity="Acme", kind=CL.DIRECT, rung=CL.STRUCTURAL_PEER,
                     mechanism="", disproof="something observable")

    def test_a_rival_that_cannot_be_wrong_is_refused(self):
        with pytest.raises(CL.RivalRefused):
            CL.Rival(identity="Acme", kind=CL.DIRECT, rung=CL.STRUCTURAL_PEER,
                     mechanism="takes the deal", disproof="")

    def test_an_attributed_rung_must_quote(self):
        # Rungs 1-4 assert that somebody SAID this. An attribution with no
        # span behind it is the claim without the evidence.
        with pytest.raises(CL.RivalRefused):
            CL.Rival(identity="Acme", kind=CL.DIRECT,
                     rung=CL.NAMED_BY_SUBJECT, mechanism="takes the deal",
                     disproof="win rates hold", evidence="")


class _Profile:
    business_model_class = "SUBSCRIPTION_SOFTWARE"
    strategic_competitors = ()


class TestTheLadderCoversGroundRatherThanEnumerating:
    def _ground(self, text):
        return CG.build("Bank of America", _Profile(),
                        [{"source_class": "investor_material", "text": text}])

    def test_one_kind_may_not_take_the_whole_table(self):
        ground = self._ground(BANK)
        kinds = [r.kind for r in ground.rivals]
        assert max(kinds.count(k) for k in set(kinds)) <= CG._MAX_PER_KIND

    def test_the_note_describes_the_table_under_it(self):
        # "No competitive statement was retrieved" printed directly above a
        # row reading "Magento — named by a customer" is a contradiction on
        # one screen.
        ground = self._ground(BANK)
        assert ground.subject_grounded
        assert "no competitive statement" not in ground.basis_note.lower()

    def test_the_company_name_survives_its_own_note(self):
        # `str.capitalize` lower-cases the remainder of the string, which
        # turned "Bank of America" into "bank of america" in its own note.
        assert "Bank of America" in self._ground(BANK).basis_note

    def test_a_run_with_no_competitive_statement_names_the_measurement(self):
        ground = CG.build("Quiet Co", _Profile(), [])
        assert not ground.subject_grounded
        assert ground.next_measurement
        assert "annual filing" in ground.next_measurement

    def test_every_row_carries_a_reaction(self):
        # §9. The projection into `CompetitorRead` carried the level-k fields
        # and the ladder row did not, so a detector reading the ladder
        # reported no rival carried a response while the page showed one.
        for rival in self._ground(BANK).rivals:
            assert rival.likely_response
            assert rival.counter_move
            assert rival.signal_to_watch
            assert rival.response_likelihood
