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
)


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
        confidence="high",
        qualifying_signals=("infrastructure_positioning", "checkout_identity_rails",
                            "product_breadth", "platform_control"),
        disconfirming_signals=("storefront_creation", "smb_simplicity"),
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
        confidence="moderate",
        qualifying_signals=("agentic_commerce", "distribution_shift",
                            "checkout_identity_rails"),
        disconfirming_signals=("storefront_creation",),
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
        confidence="moderate",
        qualifying_signals=("services_motion", "multi_product",
                            "developer_surface"),
        disconfirming_signals=("pricing_published",),
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
                            "pricing_gated"),
        disconfirming_signals=(),
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
        when_it_applies="The company positions itself as replacing several "
                        "separate tools AND ships multiple product surfaces.",
        when_it_does_not_apply="The product stays deliberately narrow and "
                               "integrates rather than absorbs.",
        source_refs=[{"title": "curated pattern: tool→system of record",
                      "origin": "strategic_pattern_library"}],
        confidence="moderate",
        qualifying_signals=("consolidation", "multi_product",
                            "developer_surface"),
        disconfirming_signals=(),
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
        when_it_applies="Regulated or government buyers are named prominently "
                        "AND the company describes distinct segments.",
        when_it_does_not_apply="Buyers are diversified across many unrelated "
                               "industries with no regulated concentration.",
        source_refs=[{"title": "curated pattern: buyer concentration",
                      "origin": "strategic_pattern_library"}],
        confidence="moderate",
        qualifying_signals=("regulated_buyer", "segment_split",
                            "named_customers"),
        disconfirming_signals=("pricing_published",),
        limitations="Without disclosed revenue by segment, concentration is "
                    "inferred from emphasis, which can mislead.",
    ),
]

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
        "statement": "{company}'s public emphasis suggests meaningful "
                     "dependence on regulated or public-sector buyers, whose "
                     "purchasing moves on cycles the company cannot "
                     "influence.",
        "reasoning": "Prominent regulated-buyer language, named deployments "
                     "in those environments and an explicit segment split "
                     "match the buyer-concentration mechanism.",
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
