"""V1.2 curated strategic pattern library.

Small, auditable, and sourced. These historical/market transition patterns are
authored here and reviewed — never generated ad hoc at report time. The
reasoning engine matches an approved run's observation signals against each
pattern's qualifying and disconfirming signals; it may reach OR reject any
pattern based on evidence. Nothing here is a conclusion about a specific
company.

Controlled signal vocabulary (the only tags observations and patterns share):

    infrastructure_positioning   storefront_creation
    checkout_identity_rails      product_breadth
    agentic_commerce             merchant_outcome_positioning
    distribution_shift           partner_ecosystem_enablement
    enterprise_expansion         platform_control
    smb_simplicity               data_network

and a domain-neutral set, so a company outside the commerce library is not
left with nothing to say:

    multi_product                pricing_published
    segment_split                pricing_gated
    named_customers              regulated_buyer
    developer_surface            consolidation
    services_motion
"""
from __future__ import annotations

from intent_engine.strategic_intelligence.records import ComparablePattern

SIGNAL_VOCABULARY = (
    # commerce-domain signals (read only from documents that are about
    # commerce at all — see the domain gate in observations.py)
    "infrastructure_positioning", "checkout_identity_rails", "agentic_commerce",
    "distribution_shift", "enterprise_expansion", "smb_simplicity",
    "product_breadth", "merchant_outcome_positioning",
    "partner_ecosystem_enablement", "platform_control", "storefront_creation",
    "data_network",
    # domain-neutral signals — shapes any company can exhibit, so a company
    # outside every domain library still gets a strategy rather than silence
    "multi_product", "segment_split", "named_customers", "developer_surface",
    "services_motion", "pricing_published", "pricing_gated",
    "regulated_buyer", "consolidation",
    # regulated-buyer CAUSAL mechanisms. `regulated_buyer` is what a company
    # SAYS; these are what it had to build, win, be bought through, or
    # disclose. Only these may carry a buyer-concentration reading.
    "gov_dedicated_delivery", "accreditation_gate",
    "public_procurement_vehicle", "disclosed_public_sector_exposure",
    # shapes a company with physical operations or formal disclosure exhibits.
    # The neutral set above is software-shaped; without these a manufacturer's
    # evidence matched one signal and produced no hypothesis.
    "capacity_investment", "customer_concentration", "segment_reporting",
    "disclosed_risk", "content_and_channel",
)


def patterns_for(model_class: str, library=None) -> list:
    """The patterns that can be TRUE of this kind of business.

    THE GATE SIGNALS COULD NOT PROVIDE. A signal records what a company's
    pages talk about; it cannot record what kind of business is talking.
    `capacity_ahead_of_demand` fired on Cloudflare -- whose filing genuinely
    discusses network capacity investment and genuinely names large customers
    -- and put "committing capital to capacity ahead of demand", "take-or-pay
    terms" and "replacing ageing lines" on the primary screen of a company
    that rents elastic compute.

    No threshold repairs that. The signals were present; the READING was
    about a different kind of business, and every pattern already documented
    which kinds in `when_it_does_not_apply`. This turns that prose into a
    filter.

    An UNKNOWN or unclassified company gets the whole library, unchanged.
    Withholding patterns from a company we could not classify would trade a
    wrong reading for no reading, and no reading is the failure this product
    was reopened to fix.
    """
    library = list(library if library is not None else PATTERN_LIBRARY)
    model = str(model_class or "").strip().upper()
    if not model or model == "UNKNOWN":
        return library
    return [p for p in library
            if model not in tuple(getattr(p, "excluded_model_classes", ()))]


def _p(**kw) -> ComparablePattern:
    p = ComparablePattern(**kw)
    p.validate()
    return p


PATTERN_LIBRARY = [
    _p(
        pattern_id="product_to_platform",
        name="Product → platform / tool → infrastructure",
        description="A company that sold a self-contained product becomes the "
                    "layer other businesses build and transact on.",
        mechanism="As adoption scales, the product's surrounding services "
                  "(payments, identity, data, distribution) become more "
                  "valuable and stickier than the original product. The "
                  "company shifts from selling a tool to operating rails "
                  "others depend on, trading visibility for structural "
                  "leverage and switching costs.",
        historical_examples=[
            {"name": "Amazon → AWS", "note": "internal retail tooling became "
             "the infrastructure other companies run on",
             "source": "https://press.aboutamazon.com/"},
            {"name": "Stripe", "note": "a payments API became broad financial "
             "infrastructure (billing, treasury, identity)",
             "source": "https://stripe.com/newsroom"},
            {"name": "Twilio", "note": "a messaging API became a customer-"
             "engagement platform layer",
             "source": "https://www.twilio.com/en-us/press"},
        ],
        when_it_applies="The company's own messaging reframes it as "
                        "infrastructure, it is expanding ownership of "
                        "payments/identity/data rails, and third parties "
                        "increasingly build on it.",
        when_it_does_not_apply="The core value proposition is still the "
                               "end-user product experience, rails are "
                               "provided by others, and there is no third-"
                               "party build-on ecosystem.",
        source_refs=[{"title": "curated pattern: product→platform",
                      "origin": "strategic_pattern_library"}],
        excluded_model_classes=("COMMODITY_PRODUCER", "CONTRACTED_OR_RATE_BASE_ASSETS",),
        confidence="high",
        qualifying_signals=("infrastructure_positioning", "checkout_identity_rails",
                            "product_breadth", "platform_control",
                            "third_party_builds_on",
                            "external_operations_depend"),
        # THE PATTERN ALREADY REQUIRED THIS IN PROSE AND HAD NO SIGNAL FOR IT.
        #
        # `when_it_applies` names three conditions and the third is "third
        # parties increasingly build on it"; `when_it_does_not_apply` rules the
        # reading out when "there is no third-party build-on ecosystem".
        # Nothing in the qualifying set measured that, so the gate was two of
        # four attributes — and `product_breadth` is itself listed under
        # when_it_does_not_apply as the thing this pattern is NOT.
        #
        # Measured live at 037f805 on Shopify, reproducible from a single
        # ordinary sentence: "commerce platform" + "checkout" + "one platform
        # for" lights three of four against a threshold of two. Every commerce
        # company with a checkout was told it operates the rails its market
        # runs on.
        #
        # Owning rails is a capability. Outsiders whose own operations stop
        # working without you is the transition, and it is what raises the
        # switching cost this reading trades on.
        required_any_signals=("third_party_builds_on",
                              "external_operations_depend"),
        disconfirming_signals=("storefront_creation", "smb_simplicity"),
        # NO BLOCKER, DELIBERATELY, AND IT WAS TRIED.
        #
        # `blocking_signals=("smb_simplicity",)` looked right — a company
        # independently reported as a simple tool for small merchants should
        # not lead with "operating the rails its market runs on". Measured, it
        # demoted Shopify's most accurate reading and broke two tests: the
        # brief and the executive document opened on different theses, and a
        # counter-observation was printed twice.
        #
        # It is the same mistake `test_blocking_is_declared_per_pattern_never_
        # applied_globally` already records at global scope: the lead reading
        # is SUPPOSED to carry counter-evidence, because one nobody has argued
        # with is one nobody has tested. Simplicity for small merchants and
        # infrastructure for large ones are not mutually exclusive — Shopify
        # is both — so this argues with the reading rather than displacing it,
        # which is what `disconfirming_signals` is for.
        limitations="Infrastructure framing in marketing can precede real "
                    "infrastructure ownership; language alone is not proof of "
                    "the transition.",
    ),
    _p(
        pattern_id="smb_wedge_to_enterprise",
        name="SMB wedge → enterprise expansion",
        description="A company that won with small customers moves upmarket to "
                    "larger, more demanding buyers.",
        mechanism="SMB adoption builds a wedge and a brand; growth pressure "
                  "and larger contract values pull the roadmap toward "
                  "enterprise needs (control, compliance, services), which can "
                  "conflict with the simplicity that won the SMB base.",
        historical_examples=[
            {"name": "Slack", "note": "bottom-up teams → Enterprise Grid",
             "source": "https://slack.com/intl/en-gb/blog"},
            {"name": "Atlassian", "note": "self-serve dev tools → enterprise "
             "agreements", "source": "https://www.atlassian.com/blog"},
            {"name": "HubSpot", "note": "SMB marketing → upmarket CRM suite",
             "source": "https://www.hubspot.com/company-news"},
        ],
        when_it_applies="Explicit enterprise product tiers/sales motion appear "
                        "and messaging adds enterprise proof points while the "
                        "SMB simplicity story persists in parallel.",
        when_it_does_not_apply="The company stays deliberately SMB-only and "
                               "declines enterprise complexity.",
        source_refs=[{"title": "curated pattern: SMB→enterprise",
                      "origin": "strategic_pattern_library"}],
        excluded_model_classes=("COMMODITY_PRODUCER", "CONTRACTED_OR_RATE_BASE_ASSETS",
            "REGULATED_PRODUCT_OR_PROVIDER",),
        confidence="high",
        qualifying_signals=("enterprise_expansion", "product_breadth"),
        disconfirming_signals=("smb_simplicity",),
        limitations="Serving enterprises is not the same as an enterprise "
                    "pivot; many companies durably serve both.",
    ),
    _p(
        pattern_id="human_to_agent_workflow",
        name="Human workflow → agent-mediated workflow",
        description="A workflow performed by humans starts being mediated by "
                    "software agents, shifting where demand is captured.",
        mechanism="When an AI agent performs the task (search, compare, buy), "
                  "the interface that used to attract humans matters less than "
                  "the rails the agent transacts through. Value migrates from "
                  "the human-facing surface to machine-readable endpoints, "
                  "identity, and checkout the agent can call.",
        historical_examples=[
            {"name": "Web search → assistants", "note": "answer engines "
             "intermediate destination sites",
             "source": "https://blog.google/products/search/"},
            {"name": "Travel booking → agents/OTAs", "note": "aggregators "
             "captured demand ahead of supplier sites",
             "source": "https://www.expediagroup.com/media/"},
        ],
        when_it_applies="The company ships agent/AI-commerce endpoints and "
                        "talks about AI-mediated buying, and it owns the "
                        "checkout/identity an agent would call.",
        when_it_does_not_apply="Buying remains human-driven on first-party "
                               "surfaces with no agent endpoints.",
        source_refs=[{"title": "curated pattern: human→agent workflow",
                      "origin": "strategic_pattern_library"}],
        excluded_model_classes=("COMMODITY_PRODUCER", "MANUFACTURE_AND_AFTERMARKET",
            "DESIGN_AND_MANUFACTURE",
            "CONTRACTED_OR_RATE_BASE_ASSETS",),
        confidence="moderate",
        qualifying_signals=("agentic_commerce", "distribution_shift",
                            "checkout_identity_rails",
                            "agent_executes_actions",
                            "agent_callable_endpoint",
                            "human_intervention_reduced"),
        # THE HIGHEST-FREQUENCY UNGATED READING IN THE LIBRARY, and the one
        # with the least behind it. Live it fired for Amazon, HubSpot, Shopify
        # and Stripe with the identical sentence; reproduced from one line,
        # the bare word "agentic" plus "marketplace" was enough.
        #
        # `when_it_applies` names three clauses and the first is "ships
        # agent/AI-commerce ENDPOINTS". Nothing measured it.
        # `when_it_does_not_apply` says the reading fails where "buying
        # remains human-driven ... with no agent endpoints".
        #
        # An AI feature is a capability. A workflow a human used to run being
        # executed by software that ACTS is the transition — and it is what
        # moves where demand is captured, which is the consequence this
        # reading draws.
        required_any_signals=("agent_executes_actions",
                              "agent_callable_endpoint",
                              "human_intervention_reduced"),
        # The stated counter-case, which the pattern described and never
        # declared: if a person approves every step, the workflow has not
        # changed hands. Not a blocker — a company can ship both a supervised
        # assistant and an autonomous endpoint.
        disconfirming_signals=("storefront_creation", "human_in_the_loop"),
        limitations="Agentic-commerce timing is uncertain; announcements can "
                    "outrun real buyer behaviour by years.",
    ),
    _p(
        pattern_id="single_product_to_ecosystem",
        name="Single product → operating-system / ecosystem",
        description="One product expands into a suite plus a third-party "
                    "ecosystem, becoming an operating system for its domain.",
        mechanism="Breadth of first-party products plus a partner/app "
                  "ecosystem raises switching costs and makes the platform the "
                  "default place to operate, but concentrates dependence and "
                  "governance power in the platform owner.",
        historical_examples=[
            {"name": "Salesforce → AppExchange", "note": "CRM became a platform "
             "with an app economy",
             "source": "https://www.salesforce.com/news/"},
            {"name": "Apple → App Store", "note": "a device became a governed "
             "developer ecosystem",
             "source": "https://www.apple.com/newsroom/"},
        ],
        when_it_applies="First-party product breadth grows alongside an active "
                        "partner/app ecosystem the company governs.",
        when_it_does_not_apply="The company stays single-product with no "
                               "third-party build-on surface.",
        source_refs=[{"title": "curated pattern: product→ecosystem",
                      "origin": "strategic_pattern_library"}],
        excluded_model_classes=("COMMODITY_PRODUCER", "CONTRACTED_OR_RATE_BASE_ASSETS",),
        confidence="high",
        qualifying_signals=("product_breadth", "partner_ecosystem_enablement",
                            "platform_control"),
        disconfirming_signals=(),
        limitations="Ecosystem breadth can blur the top-level value "
                    "proposition and invite antitrust/governance scrutiny.",
    ),
    _p(
        pattern_id="ecosystem_control_vs_openness",
        name="Ecosystem control vs openness tension",
        description="A platform must both enable partners and control the "
                    "highest-value layers, and those goals pull apart.",
        mechanism="Openness grows the ecosystem and developer trust; control "
                  "of checkout, identity, and data captures the most value and "
                  "protects the platform. Leaning too far either way risks "
                  "either commoditizing the platform or alienating the "
                  "partners that make it valuable.",
        historical_examples=[
            {"name": "Apple App Store policy fights", "note": "control of "
             "payments/distribution vs developer openness",
             "source": "https://www.apple.com/newsroom/"},
            {"name": "Facebook Platform", "note": "opened, then restricted "
             "third-party access to protect the core",
             "source": "https://about.fb.com/news/"},
        ],
        when_it_applies="The company simultaneously courts partners AND is "
                        "consolidating ownership of checkout/identity/data.",
        when_it_does_not_apply="The platform is purely open (a neutral "
                               "utility) or purely closed (fully first-party).",
        source_refs=[{"title": "curated pattern: control vs openness",
                      "origin": "strategic_pattern_library"}],
        excluded_model_classes=("COMMODITY_PRODUCER", "CONTRACTED_OR_RATE_BASE_ASSETS",
            "REGULATED_PRODUCT_OR_PROVIDER",),
        confidence="moderate",
        qualifying_signals=("partner_ecosystem_enablement", "platform_control",
                            "checkout_identity_rails"),
        disconfirming_signals=(),
        limitations="The tension is often managed for years without a visible "
                    "break; its presence is not a prediction of rupture.",
    ),
    _p(
        pattern_id="differentiator_commoditization",
        name="Commoditization of the original differentiator",
        description="The capability that first differentiated the company "
                    "becomes table stakes, forcing the value to move elsewhere.",
        mechanism="As competitors and low-cost tools replicate the original "
                  "product, its standalone value falls. The company must move "
                  "value to adjacent, harder-to-copy layers (data, "
                  "distribution, rails) or compete on price.",
        historical_examples=[
            {"name": "Website builders", "note": "storefront creation became "
             "widely available and cheap",
             "source": "https://www.gartner.com/en/newsroom"},
            {"name": "Commodity cloud storage", "note": "raw storage "
             "commoditized; value moved to services",
             "source": "https://press.aboutamazon.com/"},
        ],
        when_it_applies="The original product surface is now widely available "
                        "while the company invests in adjacent rails/data.",
        when_it_does_not_apply="The original product remains a scarce, "
                               "defensible differentiator.",
        source_refs=[{"title": "curated pattern: commoditization",
                      "origin": "strategic_pattern_library"}],
        confidence="moderate",
        qualifying_signals=("storefront_creation", "product_breadth"),
        disconfirming_signals=("infrastructure_positioning",),
        limitations="Commoditization is gradual and contested; a strong brand "
                    "can sustain premium pricing well past technical parity.",
    ),

    # --- domain-neutral patterns ---------------------------------------------
    # Everything above is a COMMERCE library. Once the domain gate correctly
    # stopped those firing outside commerce, companies like Palantir, Linear
    # and Notion produced no thesis, no hypothesis and no slides — and nothing
    # downstream treats "no hypothesis" as an error, so the pipeline reported
    # success on an empty result. 26 of 32 failing evaluation cases were this.
    #
    # These four work from shapes any company exhibits. They are deliberately
    # modest: each says something a reader could check on the company's own
    # pages, and none pretends to know the industry.
    _p(
        pattern_id="services_to_product",
        name="Services motion → repeatable product",
        description="A company that delivers through people tries to turn "
                    "that delivery into software others can run themselves.",
        mechanism="Human-delivered implementation earns trust and reveals the "
                  "real workflow, but it scales linearly with headcount. The "
                  "company productises what it learned, trading margin per "
                  "engagement for reach — and risks the product being thinner "
                  "than the service it replaces.",
        historical_examples=[
            {"name": "Accenture → industry platforms",
             "note": "consulting engagements productised into repeatable "
                     "industry solutions",
             "source": "https://newsroom.accenture.com/"},
            {"name": "Palantir forward-deployed model",
             "note": "on-site engineering became Foundry and AIP as products",
             "source": "https://www.palantir.com/newsroom/"},
        ],
        when_it_applies="The company describes embedding alongside customers "
                        "AND ships named, separately-purchasable products.",
        when_it_does_not_apply="Delivery is entirely self-serve, or the "
                               "engagement model shows no product surface.",
        source_refs=[{"title": "curated pattern: services→product",
                      "origin": "strategic_pattern_library"}],
        excluded_model_classes=("COMMODITY_PRODUCER", "CONTRACTED_OR_RATE_BASE_ASSETS",),
        confidence="moderate",
        qualifying_signals=("services_motion", "multi_product",
                            "developer_surface", "productization"),
        # BOTH HALVES, OR IT IS NOT THIS READING.
        #
        # `services_motion` alone was not enough. Almost every large vendor
        # publishes a professional-services or implementation page, so
        # requiring it removed the reading from Visa and left it dominating
        # MongoDB, Cloudflare, HubSpot and Amazon — none of which claim that
        # engagements taught them something they now sell without the
        # engagement. That claim is `productization`, and it is the mechanism
        # the pattern is named for. Having services is a fact about delivery;
        # the transition is a fact about where the margin is going.
        required_signals=("services_motion", "productization"),
        # Published self-serve pricing is the plainest evidence that the
        # product is already sold without the engagement. It now costs the
        # reading its PLACE as well as its confidence — see `_demote_contested`.
        disconfirming_signals=("pricing_published",),
        blocking_signals=("pricing_published",),
        limitations="Public pages rarely disclose the revenue mix, so the "
                    "balance between services and product is not observable "
                    "from outside.",
    ),
    _p(
        pattern_id="single_to_multi_segment",
        name="One buyer → two different buyers",
        description="A company that served one kind of customer starts "
                    "selling to a materially different one.",
        mechanism="A second segment brings volume but different procurement, "
                  "compliance and support expectations. The organisation "
                  "gradually splits — pricing, roadmap and sales motion pull "
                  "apart — and the original segment's experience is usually "
                  "what degrades first.",
        historical_examples=[
            {"name": "Slack SMB → enterprise",
             "note": "self-serve teams alongside enterprise grid deployments",
             "source": "https://slack.com/blog"},
            {"name": "AWS startups → public sector",
             "note": "a separate accredited region and procurement path",
             "source": "https://aws.amazon.com/blogs/publicsector/"},
        ],
        when_it_applies="The company names two clearly different buyer "
                        "groups, and at least one is regulated or "
                        "enterprise-shaped.",
        when_it_does_not_apply="Only one buyer group is ever described, or "
                               "the second is an aspiration with no evidence.",
        source_refs=[{"title": "curated pattern: segment split",
                      "origin": "strategic_pattern_library"}],
        confidence="moderate",
        qualifying_signals=("segment_split", "regulated_buyer",
                            "pricing_gated", "smb_simplicity"),
        # THE SUBJECT WAS OPTIONAL. This qualified on any two of
        # `segment_split`, `regulated_buyer` and `pricing_gated`, so
        # `regulated_buyer + pricing_gated` was sufficient — "we serve
        # regulated industries" plus "contact sales for pricing", which
        # describes a very large share of enterprise software and names no
        # second buyer at all. Measured on ordinary enterprise-vendor copy
        # after the system-of-record repair, it was the ONLY ungated pattern
        # that still asserted itself on generic text.
        #
        # `when_it_applies` already said what is required — "the company names
        # two clearly different buyer groups" — and `segment_split` is exactly
        # that signal. It is now required rather than one of three ways to
        # reach a threshold, which makes the gate a restatement of the
        # pattern's own declared applicability rather than a new rule.
        required_signals=("segment_split",),
        # Outside evidence that the product is still chosen by one kind of
        # buyer, for the reason that buyer chooses it. Independent-vantage
        # only (see `_OUTSIDE_ONLY_PHRASES`): the company saying it is simple
        # is marketing, reviewers saying customers stay for the simplicity is
        # evidence about who the buyer actually is.
        disconfirming_signals=("smb_simplicity",),
        limitations="Segment language on marketing pages often runs ahead of "
                    "actual revenue mix.",
    ),
    _p(
        pattern_id="tool_to_system_of_record",
        name="Point tool → system of record",
        description="A focused tool absorbs adjacent jobs until it becomes "
                    "the place the work lives.",
        mechanism="Each adjacent feature is individually small, but together "
                  "they move the customer's source of truth. Switching cost "
                  "rises sharply once other systems read from it — and the "
                  "product's original sharpness is what pays for that "
                  "breadth.",
        historical_examples=[
            {"name": "Notion",
             "note": "notes tool absorbed wikis, projects and databases",
             "source": "https://www.notion.so/blog"},
            {"name": "Figma",
             "note": "a design tool became the place design work is stored "
                     "and reviewed",
             "source": "https://www.figma.com/blog/"},
        ],
        when_it_applies="The company shows a CAUSAL mechanism moving the "
                        "customer's record into it — an authoritative-record "
                        "claim, one data model beneath several products, or "
                        "customers retiring a system they already had.",
        when_it_does_not_apply="The breadth is a product list. Several "
                               "products, an API and consolidation copy are "
                               "things almost every B2B software company has, "
                               "and none of them says the source of truth "
                               "moved. Also: the product integrates rather "
                               "than absorbs, or its economics are self-serve "
                               "point-tool economics.",
        source_refs=[{"title": "curated pattern: tool→system of record",
                      "origin": "strategic_pattern_library"}],
        excluded_model_classes=("COMMODITY_PRODUCER", "MANUFACTURE_AND_AFTERMARKET",
            "DESIGN_AND_MANUFACTURE",
            "CONTRACTED_OR_RATE_BASE_ASSETS",),
        confidence="moderate",
        qualifying_signals=("consolidation", "multi_product",
                            "developer_surface", "system_of_record_claim",
                            "shared_data_model",
                            "replaces_incumbent_systems"),
        # THE MECHANISM, NOT THE ATTRIBUTES. This reading was gated only by
        # "any 2 of consolidation / multi_product / developer_surface", and the
        # last two are true of nearly every B2B software company — so it fired
        # on being a platform at all. Measured live at dad7d28: Palantir,
        # HubSpot and Snowflake each qualified that way and were handed the
        # same sentence with only the name changed.
        #
        # The pattern's own `mechanism` field says the customer's source of
        # truth moves and switching cost rises once other systems read from
        # it. These are the three ways that can be evidenced, and a run
        # showing none of them no longer gets to assert it.
        required_any_signals=("system_of_record_claim", "shared_data_model",
                              "replaces_incumbent_systems"),
        # Published self-serve pricing argues against the switching cost this
        # reading depends on: a record you can leave on a monthly plan is not
        # the record the mechanism describes. Secondary, not blocking — a
        # company can publish prices and still hold the record.
        disconfirming_signals=("pricing_published",),
        limitations="Consolidation claims are marketing language; whether the "
                    "source of truth actually moved is not visible publicly.",
    ),
    _p(
        pattern_id="buyer_concentration_exposure",
        name="Concentrated buyer exposure",
        description="A large share of the business appears to depend on one "
                    "buyer type whose budget moves for reasons outside the "
                    "company's control.",
        mechanism="Regulated and public-sector buyers are sticky and "
                  "high-value, which makes them attractive and then makes "
                  "them structural. Procurement cycles, political budgets and "
                  "accreditation regimes then set the growth rate, and "
                  "diversification takes years because the second segment "
                  "buys nothing like the first.",
        historical_examples=[
            {"name": "Public-sector-heavy software vendors",
             "note": "growth tracked appropriation cycles rather than product",
             "source": "https://www.gao.gov/"},
        ],
        when_it_applies="The company shows a CAUSAL mechanism tying it to "
                        "regulated or public-sector buyers — a dedicated "
                        "government estate, an accreditation that gates the "
                        "purchase, a procurement vehicle, or a disclosed "
                        "exposure.",
        when_it_does_not_apply="The only evidence is compliance badges, a "
                               "security page, one case study or 'serves "
                               "regulated industries' copy; or buyers are "
                               "diversified with no regulated concentration.",
        source_refs=[{"title": "curated pattern: buyer concentration",
                      "origin": "strategic_pattern_library"}],
        confidence="moderate",
        qualifying_signals=("regulated_buyer", "segment_split",
                            "named_customers", "gov_dedicated_delivery",
                            "accreditation_gate", "public_procurement_vehicle",
                            "disclosed_public_sector_exposure"),
        # Vocabulary is not a mechanism. Without one of these, this reading
        # fired on a compliance footer — see `required_any_signals`.
        required_any_signals=("gov_dedicated_delivery", "accreditation_gate",
                              "public_procurement_vehicle",
                              "disclosed_public_sector_exposure"),
        disconfirming_signals=("pricing_published",),
        limitations="Without disclosed revenue by segment, concentration is "
                    "inferred from emphasis, which can mislead.",
    ),
    # --- shapes outside software ---------------------------------------------
    # A conglomerate's evidence is segment reporting, capacity commitments and
    # disclosed risk, none of which the software-shaped neutral patterns above
    # can read. The result was a brief with no hypothesis: the reader was told
    # what the company said about itself and nothing about what it meant.
    _p(
        pattern_id="capacity_ahead_of_demand",
        name="Capacity committed ahead of the demand for it",
        description="A company commits capital to capacity now against demand "
                    "it expects later, from buyers it does not control.",
        mechanism="Capacity is bought in large, slow increments while demand "
                  "arrives in small, fast ones. Committing early wins share "
                  "when the forecast holds and strands fixed cost when it "
                  "does not — and the forecast usually rests on a handful of "
                  "large customers whose own product cycles set the timing.",
        historical_examples=[
            {"name": "Memory and sensor fabrication cycles",
             "note": "capacity added on forecast, then written down when "
                     "handset demand moved",
             "source": "https://www.sec.gov/"},
            {"name": "Contract manufacturing capacity build-outs",
             "note": "multi-year fab commitments against customer roadmaps",
             "source": "https://www.sec.gov/"},
        ],
        when_it_applies="The company describes committing capital to capacity "
                        "AND names a concentrated or cyclical set of buyers "
                        "for it.",
        when_it_does_not_apply="Capacity is rented or elastic, or demand is "
                               "spread across many independent buyers.",
        source_refs=[{"title": "curated pattern: capacity ahead of demand",
                      "origin": "strategic_pattern_library"}],
        excluded_model_classes=("SUBSCRIPTION_SOFTWARE", "BALANCE_SHEET_OR_NETWORK",
            "REGULATED_PRODUCT_OR_PROVIDER",
            "PEOPLE_OR_ROUTE_BASED_SERVICES", "BRANDED_CONSUMER",),
        confidence="moderate",
        qualifying_signals=("capacity_investment", "customer_concentration",
                            "segment_reporting"),
        disconfirming_signals=("pricing_published",),
        limitations="Utilisation and order books are not public, so whether "
                    "committed capacity is actually filled cannot be seen "
                    "from outside.",
    ),
    _p(
        pattern_id="portfolio_run_as_one",
        name="Separate businesses run as one portfolio",
        description="A company reports distinct segments while describing "
                    "them as a single, deliberately connected portfolio.",
        mechanism="Owning both what is sold and the channel it reaches people "
                  "through lets each business subsidise the other's "
                  "acquisition cost. The same coupling makes per-business "
                  "accountability harder to read from outside, and a weak "
                  "segment can be carried far longer than it would survive "
                  "alone.",
        historical_examples=[
            {"name": "Vertically integrated entertainment groups",
             "note": "content and the device it plays on managed together",
             "source": "https://www.sec.gov/"},
            {"name": "Platform holders with first-party content",
             "note": "hardware margin funded by content attach",
             "source": "https://www.sec.gov/"},
        ],
        when_it_applies="The company reports several segments AND describes "
                        "owning both the content or product and the channel "
                        "that distributes it.",
        when_it_does_not_apply="Segments are unrelated holdings with no "
                               "described operational connection.",
        source_refs=[{"title": "curated pattern: portfolio run as one",
                      "origin": "strategic_pattern_library"}],
        confidence="moderate",
        qualifying_signals=("segment_reporting", "content_and_channel",
                            "multi_product", "cross_product_coupling",
                            "shared_data_model", "independently_operated"),
        # THE COUPLING IS THE PATTERN, AND ANY TWO OF THREE DID NOT NEED IT.
        #
        # `when_it_applies` requires several segments AND "owning both the
        # content or product and the channel that distributes it". The gate
        # was any two of `segment_reporting`, `content_and_channel` and
        # `multi_product`, so "operating segments" plus "our product
        # portfolio" qualified — which is every multi-product filer.
        #
        # Measured live: HubSpot, Microsoft and Stripe all received this
        # reading, the highest live frequency of any ungated pattern that
        # declared no disconfirmers. On shaped corpora it fires on ordinary
        # multi-product-suite copy.
        #
        # Three ways the coupling can be evidenced. `content_and_channel` is
        # the media shape the mechanism was written from (owned titles plus
        # the box they play on); the other two are the same coupling in a
        # software company — shared identity/billing/contracts, or one data
        # model beneath the products. Reporting segments and listing products
        # are what a company DISCLOSES; the coupling is what makes them one
        # business.
        required_any_signals=("content_and_channel", "cross_product_coupling",
                              "shared_data_model"),
        # THE SUBJECT HALF, ADDED AFTER THE FIRST DEPLOY OF THIS GATE.
        #
        # `when_it_applies` is a conjunction: several segments AND the
        # coupling. Requiring only the coupling qualified Datadog live — it
        # genuinely runs "a common data model" across its products, but it
        # reports ONE segment, so "reports distinct segments while describing
        # them as one connected portfolio" is not true of it and neither is
        # the consequence the statement draws ("hard to read any single
        # business from outside"). Microsoft, which does both, is unaffected:
        # its evidence is "first-party content performance" against reported
        # segment results.
        #
        # A coupling without separate disclosure is a well-built product, not
        # a portfolio being run as one.
        required_signals=("segment_reporting",),
        # The disconfirmer the pattern already described in prose and never
        # declared: "segments are unrelated holdings with no described
        # operational connection". A company that says its businesses are run
        # separately is telling you the coupling is absent. Not a blocker —
        # a decentralised operator can still cross-subsidise, and this argues
        # with the reading rather than excluding it.
        disconfirming_signals=("independently_operated",),
        limitations="Transfers between segments are not disclosed publicly, "
                    "so which business subsidises which is inferred from "
                    "structure rather than observed.",
    ),
]

#: A statement placeholder no caller has filled renders as a hole in the page,
#: and a caller that does not know a placeholder exists raises KeyError at
#: composition time. Both were live risks the moment `{mechanism}` was added:
#: production filled it and a second caller did not. So the substitution lives
#: HERE, once, beside the scaffolds that declare the placeholders.
def statement_for(scaffold: dict, *, company: str, mechanism: str = "") -> str:
    """Fill a scaffold's statement. The only place a statement is formatted."""
    return scaffold["statement"].format(company=company, mechanism=mechanism)


# Hypothesis scaffolds — the reasoning the engine instantiates when a pattern
# fires. Kept beside the library (auditable) but separate from the pattern
# facts. `threshold` = minimum qualifying signals that must be present.
HYPOTHESIS_SCAFFOLDS = {
    "product_to_platform": {
        "title": "moving from selling a product toward operating the "
                 "rails beneath it",
        "statement": "{company} appears to be repositioning from selling "
                     "software toward operating the payment, identity, data, "
                     "and distribution rails its market runs on.",
        "reasoning": "Infrastructure-level positioning, expanding ownership of "
                     "checkout/identity rails, and growing first-party product "
                     "breadth together match the product→platform mechanism: "
                     "value and lock-in migrate from the visible product to "
                     "the rails underneath it.",
        "alternatives": [
            "The infrastructure language is aspirational marketing while "
            "revenue and usage remain concentrated in the original product.",
            "Rails ownership is defensive (protecting the core product's "
            "economics) rather than a bid to become industry infrastructure.",
        ],
        "implications": [
            "Whether to invest ahead of demand in owning checkout/identity/"
            "data rails vs. deepening the core product.",
            "How to price and package rails vs. the product without "
            "cannibalizing either.",
        ],
        "falsification": [
            "Does a rising share of revenue and active usage come from rails "
            "(payments, identity, data) rather than the core product?",
            "Are third parties actually building on these rails, or only using "
            "the first-party product?",
        ],
        "gaps": [
            "Revenue mix between core product and rails is not public at the "
            "needed granularity.",
            "Third-party build-on adoption vs. first-party usage is unclear.",
        ],
        "threshold": 2,
    },
    "smb_wedge_to_enterprise": {
        "title": "expanding from a smaller-customer wedge toward "
                 "enterprise and platform",
        "statement": "{company} appears to be extending from its "
                     "smaller-customer base toward larger enterprise buyers and "
                     "a broader platform.",
        "reasoning": "An explicit enterprise motion alongside growing product "
                     "breadth matches the SMB-wedge→enterprise mechanism: "
                     "larger contracts pull the roadmap toward control and "
                     "complexity that can strain the original simplicity.",
        "alternatives": [
            "The company is durably serving both segments rather than shifting "
            "upmarket.",
            "Enterprise features are a brand/credibility play, not a center-of-"
            "gravity change.",
        ],
        "implications": [
            "How much roadmap and org focus to shift to enterprise without "
            "eroding the SMB self-serve motion.",
            "Whether to run one product or bifurcate SMB and enterprise.",
        ],
        "falsification": [
            "Is enterprise becoming a majority of net-new revenue and "
            "roadmap?",
            "Is SMB activation/retention degrading as enterprise focus grows?",
        ],
        "gaps": [
            "Segment revenue split and roadmap allocation are not public.",
        ],
        "threshold": 2,
    },
    "human_to_agent_workflow": {
        "title": "positioning for demand mediated by AI agents rather "
                 "than by people",
        "statement": "{company} appears to be positioning for buying that is "
                     "mediated by AI agents rather than by people directly, "
                     "shifting where demand is captured.",
        "reasoning": "Agent/AI-commerce endpoints plus a distribution shift "
                     "plus ownership of checkout/identity match the "
                     "human→agent-workflow mechanism: when agents transact, "
                     "the rails they call matter more than the human-facing "
                     "storefront.",
        "alternatives": [
            "Agentic-commerce work is R&D optionality, not a near-term "
            "distribution change.",
            "Human storefront browsing remains dominant for years and agent "
            "endpoints stay marginal.",
        ],
        "implications": [
            "Whether to invest now in agent-readable endpoints, identity, and "
            "checkout the agents will call.",
            "How to keep merchant demand capture as browsing intermediates.",
        ],
        "falsification": [
            "Is a measurable and growing share of orders originating from "
            "AI-agent surfaces rather than human browsing?",
            "Do merchants see agent-driven demand they cannot get elsewhere?",
        ],
        "gaps": [
            "Real agent-driven order volume vs. human browsing is not yet "
            "observable in public data.",
        ],
        "threshold": 2,
    },
    "single_product_to_ecosystem": {
        "title": "building a controlled ecosystem out of its product "
                 "breadth",
        "statement": "{company}'s expanding first-party product breadth plus a "
                     "partner ecosystem appears to be turning it into an "
                     "operating system for its domain.",
        "reasoning": "First-party breadth, an active partner/app ecosystem, "
                     "and platform control match the single-product→ecosystem "
                     "mechanism: breadth plus partners raise switching costs "
                     "and concentrate governance power.",
        "alternatives": [
            "Breadth is defensive bundling rather than a deliberate ecosystem "
            "strategy.",
            "The partner ecosystem is a distribution channel, not a platform "
            "in its own right.",
        ],
        "implications": [
            "How much to grow first-party breadth vs. cede surface to "
            "partners.",
            "Whether breadth is diluting the top-level value proposition.",
        ],
        "falsification": [
            "Is switching cost (multi-product adoption per customer) actually "
            "rising?",
            "Is partner-built value growing, or being absorbed first-party?",
        ],
        "gaps": [
            "Multi-product adoption per merchant and partner economics are not "
            "public.",
        ],
        "threshold": 2,
    },
    "ecosystem_control_vs_openness": {
        "title": "both enabling partners and consolidating the "
                 "highest-value layers for itself",
        "statement": "{company} appears to be both courting partners and "
                     "consolidating ownership of checkout, identity, and data "
                     "— goals that pull against each other.",
        "reasoning": "Simultaneous partner enablement and consolidation of "
                     "checkout/identity/data match the control-vs-openness "
                     "tension: the platform must stay open enough to grow the "
                     "ecosystem yet closed enough to capture the top-value "
                     "layers.",
        "alternatives": [
            "Control and openness are aimed at different layers and coexist "
            "comfortably.",
            "Consolidation is about reliability/UX, not value capture from "
            "partners.",
        ],
        "implications": [
            "Where to draw the line between partner-owned and company-owned "
            "layers.",
            "How to keep partner trust while owning checkout/identity/data.",
        ],
        "falsification": [
            "Have partners publicly objected to the company taking layers they "
            "previously owned?",
            "Is partner-sourced GMV/app revenue growing or shrinking as rails "
            "consolidate?",
        ],
        "gaps": [
            "Partner sentiment and the value split between first-party rails "
            "and partner apps are not fully public.",
        ],
        "threshold": 2,
    },
    # --- domain-neutral scaffolds --------------------------------------------
    "services_to_product": {
        "title": "turning a people-delivered service into a repeatable "
                 "product",
        "statement": "{company} appears to be converting what it learned "
                     "delivering work alongside customers into products those "
                     "customers can run themselves.",
        "reasoning": "An explicit embedded or forward-deployed delivery model "
                     "alongside several separately-named products matches the "
                     "services-to-product mechanism: the engagement teaches "
                     "the workflow, and the product is the attempt to sell it "
                     "without the engagement.",
        "alternatives": [
            "The products are packaging around what remains a services "
            "business.",
            "The delivery model is a go-to-market choice for a product that "
            "was always a product.",
        ],
        "implications": [
            "Whether to price the product independently of the engagement.",
            "How much implementation to keep as paid work versus absorb.",
        ],
        "gaps": [
            "Revenue split between services and product is not public.",
        ],
        "falsification": [
            "Published pricing that assumes no implementation engagement.",
        ],
        "threshold": 2,
        "decision_affected": "Whether the next hire is an engineer or an "
                             "implementation consultant.",
    },
    "single_to_multi_segment": {
        "title": "selling to a second kind of buyer that behaves nothing like "
                 "the first",
        "statement": "{company} appears to serve two clearly different buyer "
                     "groups whose procurement, compliance and support needs "
                     "pull the organisation in different directions.",
        "reasoning": "Distinct named segments plus regulated-buyer language "
                     "and gated pricing match the segment-split mechanism: "
                     "the second buyer arrives with requirements the first "
                     "never had.",
        "alternatives": [
            "One segment is aspirational marketing rather than real revenue.",
            "The segments share a single product and no real split exists.",
        ],
        "implications": [
            "Whether to run one roadmap or two.",
            "Which segment sets the support and compliance bar.",
        ],
        "gaps": [
            "Revenue by segment is not disclosed on public pages.",
        ],
        "falsification": [
            "Evidence that one named segment contributes negligible revenue.",
        ],
        "threshold": 2,
        "decision_affected": "Which buyer the roadmap is allowed to "
                             "disappoint.",
    },
    "tool_to_system_of_record": {
        "title": "absorbing adjacent tools until the work lives inside it",
        "statement": "{company} appears to be broadening from a focused tool "
                     "toward being the place a team's work is stored, which "
                     "raises switching cost and blunts the original product's "
                     "sharpness.",
        "reasoning": "Explicit consolidation language plus several product "
                     "surfaces and a build-on surface match the "
                     "tool-to-system-of-record mechanism.",
        "alternatives": [
            "The breadth is packaging; the source of truth still lives "
            "elsewhere.",
            "Integrations, not absorption, are doing the work.",
        ],
        "implications": [
            "Whether to keep investing in depth or in adjacency.",
            "How much integration surface to expose to would-be replacements.",
        ],
        "gaps": [
            "Whether customers actually moved their source of truth is not "
            "observable from outside.",
        ],
        "falsification": [
            "Customers describing it as a companion to a system of record "
            "rather than the record itself.",
        ],
        "threshold": 2,
        "decision_affected": "Whether the next release deepens the core or "
                             "adds another surface.",
    },
    "buyer_concentration_exposure": {
        "title": "leaning on a buyer type whose budget it does not control",
        # NAMES THE MECHANISM IT READ OFF. The old sentence was "public
        # emphasis suggests meaningful dependence on regulated or
        # public-sector buyers" — true of any company with a compliance
        # footer, and therefore identical for HubSpot and Snowflake. What
        # differs between two companies that genuinely qualify is WHY, so the
        # reading now says why. `{mechanism}` is filled from the causal
        # signals actually observed; a run with none of them never gets here.
        "statement": "{company} appears to depend on regulated or "
                     "public-sector buyers in a way that shapes the business: "
                     "{mechanism}. Purchasing of that kind moves on budget "
                     "and accreditation cycles the company cannot influence.",
        "reasoning": "A causal public-sector mechanism — not compliance "
                     "language alone — matches the buyer-concentration "
                     "pattern: the company has built, certified, or disclosed "
                     "something it would only have if these buyers mattered.",
        "alternatives": [
            "Regulated buyers are prominent in marketing but small in "
            "revenue.",
            "The commercial segment is already large enough to absorb a "
            "public-sector slowdown.",
        ],
        "implications": [
            "How much runway to hold against a procurement cycle.",
            "Whether diversification is a stated goal or an accident.",
        ],
        "gaps": [
            "Revenue concentration is not disclosed on public pages.",
        ],
        "falsification": [
            "Disclosed segment revenue showing no concentration.",
        ],
        "threshold": 2,
        "decision_affected": "How much of the plan may depend on one budget "
                             "cycle.",
    },
    "capacity_ahead_of_demand": {
        "title": "committing capital to capacity ahead of uncertain demand",
        "statement": "{company} appears to be committing capital to capacity "
                     "ahead of demand it does not control, concentrating the "
                     "outcome in a small number of buyers' product cycles.",
        "reasoning": "Stated capacity investment, a written-down dependence "
                     "on a few buyers, and formal segment reporting together "
                     "match the capacity-ahead-of-demand mechanism: fixed "
                     "cost is committed in large increments against demand "
                     "that arrives in small ones.",
        "alternatives": [
            "The capacity is pre-sold under long-term agreements, so the "
            "commitment carries far less risk than it appears to.",
            "Capacity is being added to replace ageing lines rather than to "
            "serve growth.",
        ],
        "implications": [
            "Whether a supply commitment should be treated as fixed or "
            "renegotiable.",
            "How exposed a plan is to one buyer's product cycle slipping.",
        ],
        "gaps": [
            "Utilisation, order books and take-or-pay terms are not public.",
        ],
        "falsification": [
            "Disclosed long-term purchase commitments covering the new "
            "capacity.",
            "Buyer diversification across many independent customers.",
        ],
        "threshold": 2,
        "decision_affected": "Whether to treat committed supply as a fixed "
                             "cost or a negotiable one.",
    },
    "portfolio_run_as_one": {
        "title": "running separately-reported businesses as a single "
                 "portfolio",
        "statement": "{company} reports distinct segments while describing "
                     "them as one connected portfolio, which makes the "
                     "performance of any single business hard to read from "
                     "outside.",
        "reasoning": "Formal segment reporting alongside language about "
                     "owning both the content and the channel matches the "
                     "portfolio mechanism: businesses that subsidise each "
                     "other are managed together and disclosed apart.",
        "alternatives": [
            "The segments are genuinely independent and the portfolio framing "
            "is investor-relations language rather than operating reality.",
            "Connections between segments are real but small enough not to "
            "affect how any one of them should be judged.",
        ],
        "implications": [
            "Which business a partnership or supply agreement actually "
            "depends on.",
            "Whether a weak segment is being carried by a strong one.",
        ],
        "gaps": [
            "Inter-segment transfers and shared cost allocations are not "
            "disclosed.",
        ],
        "falsification": [
            "Segment disclosure showing no material inter-segment revenue.",
            "A divestment that leaves the remaining segments unaffected.",
        ],
        "threshold": 2,
        "decision_affected": "Which business in the group a commercial "
                             "relationship actually rests on.",
    },
    "differentiator_commoditization": {
        "title": "watching its original differentiator commoditise",
        "statement": "{company}'s original core-product advantage may "
                     "be becoming table stakes, pushing value toward adjacent "
                     "rails and data.",
        "reasoning": "Widespread availability of the original product surface "
                     "alongside heavy investment in adjacent breadth matches "
                     "the commoditization mechanism: value moves to harder-to-"
                     "copy layers as the differentiator is replicated.",
        "alternatives": [
            "Brand, scale, and reliability keep the original product a durable "
            "differentiator.",
            "Adjacent investment is expansion, not a response to "
            "commoditization.",
        ],
        "implications": [
            "How fast to move value and pricing to rails/data before the core "
            "product's premium erodes.",
        ],
        "falsification": [
            "Is standalone pricing power on the core storefront product "
            "declining?",
            "Are new customers arriving primarily for adjacent rails rather "
            "than storefront creation?",
        ],
        "gaps": [
            "Standalone-product pricing power and attach reasons are not "
            "public.",
        ],
        "threshold": 2,
    },
}

# Live tensions used to build responsible blind-spot hypotheses: a tension is
# "live" when observations present signals from BOTH sides.
TENSIONS = [
    {
        "tension_id": "enterprise_vs_smb_simplicity",
        "left": ("enterprise_expansion", "product_breadth"),
        "right": ("smb_simplicity",),
        "observed_tension": "An enterprise/platform push is growing at the "
                            "same time the brand still promises small-merchant "
                            "simplicity and autonomy.",
        "why_it_may_matter": "The complexity that wins enterprise deals can "
                             "erode the ease that won the SMB base — the "
                             "original growth engine.",
        "counter_explanation": "Tiering and packaging may let the company "
                               "serve both without forcing the SMB experience "
                               "to absorb enterprise complexity.",
        "evidence_needed": [
            "SMB activation/retention trend as enterprise focus grows",
            "Whether SMB-facing surfaces are gaining enterprise complexity",
        ],
        "decision_affected": "How to segment product and roadmap so enterprise "
                             "expansion does not degrade the SMB motion.",
    },
    {
        "tension_id": "breadth_vs_clear_value_prop",
        "left": ("product_breadth",),
        "right": ("merchant_outcome_positioning", "storefront_creation"),
        "observed_tension": "Expanding product breadth strengthens lock-in but "
                            "makes the single top-level value proposition "
                            "harder to state.",
        "why_it_may_matter": "A diffuse value proposition raises acquisition "
                             "cost and lets focused competitors win specific "
                             "outcomes.",
        "counter_explanation": "An outcome-led narrative ('grow your "
                               "business') can unify breadth under one "
                               "promise.",
        "evidence_needed": [
            "Whether messaging resolves to one outcome or lists many products",
            "Acquisition efficiency trend as breadth grows",
        ],
        "decision_affected": "Whether to lead with an outcome narrative or a "
                             "product-suite narrative.",
    },
    {
        "tension_id": "control_vs_partner_openness",
        "left": ("platform_control", "checkout_identity_rails"),
        "right": ("partner_ecosystem_enablement",),
        "observed_tension": "Consolidating checkout/identity/data rails may "
                            "encroach on layers partners currently monetize.",
        "why_it_may_matter": "Partners build much of the ecosystem's value; "
                             "taking their layers can shrink the ecosystem the "
                             "platform depends on.",
        "counter_explanation": "Owning rails can raise reliability and "
                               "conversion that benefits partners too.",
        "evidence_needed": [
            "Partner sentiment about the company entering their layers",
            "Trend in partner-sourced value vs first-party rails",
        ],
        "decision_affected": "Where to draw the first-party vs partner line to "
                             "keep the ecosystem growing.",
    },
]
