"""What kind of business this is, and therefore which analysis applies.

WHY THIS EXISTS
---------------
The executive read for Cloudflare, Shopify and Johnson & Johnson came back
0.94-0.96 similar. That was never a writing problem. `decision_synthesis`
asked every company the SAME question --

    "What should be concluded about {company} from the published market
     record, and what would change it?"

-- ranked no signals, named no competitors, chose no economic channel and
selected no causal question. Identical analytical inputs produce identical
prose no matter how the prose is written, so varying the wording would have
hidden the defect rather than fixed it.

This module is the layer underneath. It answers "what kind of business is
this" so the layers above can answer "therefore what is worth asking".

WHAT IT MAY AND MAY NOT CLAIM
-----------------------------
Everything here is derived from the company's CLASSIFICATION in the
validation manifest -- sector, business model class, capital intensity,
cyclicality, regulatory class, public/private, segment count. Those are
authored, reviewed, version-controlled facts about which KIND of business a
company is.

So the claims this module makes are definitional, not empirical:

    "a commodity producer sells an undifferentiated product at a price it
     does not set"

is true of commodity producers by construction. It is not a claim that this
company's realised price moved, and nothing here may become one. Concretely:

  * no numbers, ever -- not a margin, not a growth rate, not a share;
  * no claim about what this company DID, only about the economics of the
    model it operates under;
  * a company outside the manifest gets UNKNOWN across the board rather
    than the average company's profile, because "we do not know what this
    business is" is the honest state and it is the one that must degrade
    the analysis above it.

THE MANIFEST IS THE ONLY SOURCE
-------------------------------
`industry` is UNKNOWN for all 100 manifest rows, so nothing here reads it --
a table keyed on a field that is always UNKNOWN yields one bucket, which is
the collapse this module exists to end.
"""
from __future__ import annotations

import dataclasses
from typing import Optional, Tuple

CONTRACT = "company_intelligence_profile.v1"

UNKNOWN = "UNKNOWN"

#: The nine business model classes the manifest actually uses. Every table
#: below is keyed on these and nothing else, so a new class added to the
#: manifest surfaces as a missing key rather than silently taking a default.
MODEL_CLASSES = (
    "SUBSCRIPTION_SOFTWARE",
    "DESIGN_AND_MANUFACTURE",
    "COMMODITY_PRODUCER",
    "BRANDED_CONSUMER",
    "CONTRACTED_OR_RATE_BASE_ASSETS",
    "BALANCE_SHEET_OR_NETWORK",
    "MANUFACTURE_AND_AFTERMARKET",
    "PEOPLE_OR_ROUTE_BASED_SERVICES",
    "REGULATED_PRODUCT_OR_PROVIDER",
)

# --- how well this company is classified, stated rather than implied --------
#
# The manifest is a VALIDATION universe, not a knowledge base. Treating
# membership in it as the precondition for knowing what kind of business a
# company is meant that 16 of 26 companies with live market snapshots --
# Toyota, Vale, ASML among them -- read as UNKNOWN. Not "sparsely covered":
# unknown, as though the company had never been identified. It had been.
#
# So profile quality is now a stated three-value fact with a named source,
# and there is no fourth state reached by a failed join.

#: Classified by the validation manifest: authored, reviewed, per-company.
PROFILE_AVAILABLE = "PROFILE_AVAILABLE"
#: Classified by the registrant's own regulator-assigned SIC code. Correct
#: but coarser -- one code covers a major group, so the model class is right
#: and the within-class detail the manifest would have added is absent.
PROFILE_PARTIAL = "PROFILE_PARTIAL"
#: Not classified by either source. An explicit state that names what is
#: missing and what would resolve it -- never a silent fallback.
PROFILE_SPARSE = "PROFILE_SPARSE"

PROFILE_STATES = (PROFILE_AVAILABLE, PROFILE_PARTIAL, PROFILE_SPARSE)


#: SIC major group -> (business model class, sector). Keyed on the first two
#: digits, which is the division the SEC actually assigns; four-digit
#: overrides below handle the groups that genuinely contain two different
#: businesses (pharmaceutical preparations inside chemicals, construction
#: machinery inside industrial machinery).
#:
#: Codes whose definition is a residual -- "not elsewhere classified" -- are
#: deliberately ABSENT rather than guessed. 7389 covers Etsy, a marketplace,
#: and a payroll bureau equally well; inferring a business model from a
#: category defined by what it is not is the inference this whole module
#: exists to refuse. Those companies land on PROFILE_SPARSE and say so.
_SIC_MAJOR_GROUP = {
    "01": ("COMMODITY_PRODUCER", "MATERIALS_ENERGY"),
    "02": ("COMMODITY_PRODUCER", "MATERIALS_ENERGY"),
    "08": ("COMMODITY_PRODUCER", "MATERIALS_ENERGY"),
    "09": ("COMMODITY_PRODUCER", "MATERIALS_ENERGY"),
    "10": ("COMMODITY_PRODUCER", "MATERIALS_ENERGY"),
    "12": ("COMMODITY_PRODUCER", "MATERIALS_ENERGY"),
    "13": ("COMMODITY_PRODUCER", "MATERIALS_ENERGY"),
    "14": ("COMMODITY_PRODUCER", "MATERIALS_ENERGY"),
    "15": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "16": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "17": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "20": ("BRANDED_CONSUMER", "CONSUMER"),
    "21": ("BRANDED_CONSUMER", "CONSUMER"),
    "22": ("BRANDED_CONSUMER", "CONSUMER"),
    "23": ("BRANDED_CONSUMER", "CONSUMER"),
    "24": ("COMMODITY_PRODUCER", "MATERIALS_ENERGY"),
    "25": ("DESIGN_AND_MANUFACTURE", "INDUSTRIAL"),
    "26": ("COMMODITY_PRODUCER", "MATERIALS_ENERGY"),
    "27": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "28": ("COMMODITY_PRODUCER", "MATERIALS_ENERGY"),
    "29": ("COMMODITY_PRODUCER", "MATERIALS_ENERGY"),
    "30": ("COMMODITY_PRODUCER", "MATERIALS_ENERGY"),
    "31": ("BRANDED_CONSUMER", "CONSUMER"),
    "32": ("COMMODITY_PRODUCER", "MATERIALS_ENERGY"),
    "33": ("COMMODITY_PRODUCER", "MATERIALS_ENERGY"),
    "34": ("DESIGN_AND_MANUFACTURE", "INDUSTRIAL"),
    "35": ("DESIGN_AND_MANUFACTURE", "INDUSTRIAL"),
    "36": ("DESIGN_AND_MANUFACTURE", "SEMICONDUCTOR"),
    "37": ("MANUFACTURE_AND_AFTERMARKET", "INDUSTRIAL"),
    "38": ("DESIGN_AND_MANUFACTURE", "INDUSTRIAL"),
    "39": ("DESIGN_AND_MANUFACTURE", "INDUSTRIAL"),
    "40": ("CONTRACTED_OR_RATE_BASE_ASSETS", "INFRASTRUCTURE"),
    "41": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "42": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "44": ("CONTRACTED_OR_RATE_BASE_ASSETS", "INFRASTRUCTURE"),
    "45": ("CONTRACTED_OR_RATE_BASE_ASSETS", "INFRASTRUCTURE"),
    "46": ("CONTRACTED_OR_RATE_BASE_ASSETS", "INFRASTRUCTURE"),
    "47": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "48": ("CONTRACTED_OR_RATE_BASE_ASSETS", "INFRASTRUCTURE"),
    "49": ("CONTRACTED_OR_RATE_BASE_ASSETS", "INFRASTRUCTURE"),
    "50": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "51": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "52": ("BRANDED_CONSUMER", "CONSUMER"),
    "53": ("BRANDED_CONSUMER", "CONSUMER"),
    "54": ("BRANDED_CONSUMER", "CONSUMER"),
    "55": ("BRANDED_CONSUMER", "CONSUMER"),
    "56": ("BRANDED_CONSUMER", "CONSUMER"),
    "57": ("BRANDED_CONSUMER", "CONSUMER"),
    "58": ("BRANDED_CONSUMER", "CONSUMER"),
    "59": ("BRANDED_CONSUMER", "CONSUMER"),
    "60": ("BALANCE_SHEET_OR_NETWORK", "FINANCIAL_REGULATED"),
    "61": ("BALANCE_SHEET_OR_NETWORK", "FINANCIAL_REGULATED"),
    "62": ("BALANCE_SHEET_OR_NETWORK", "FINANCIAL_REGULATED"),
    "63": ("BALANCE_SHEET_OR_NETWORK", "FINANCIAL_REGULATED"),
    "64": ("BALANCE_SHEET_OR_NETWORK", "FINANCIAL_REGULATED"),
    "65": ("CONTRACTED_OR_RATE_BASE_ASSETS", "INFRASTRUCTURE"),
    "67": ("BALANCE_SHEET_OR_NETWORK", "FINANCIAL_REGULATED"),
    "70": ("BRANDED_CONSUMER", "CONSUMER"),
    "72": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "73": ("SUBSCRIPTION_SOFTWARE", "SOFTWARE_PLATFORM"),
    "75": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "76": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "78": ("BRANDED_CONSUMER", "CONSUMER"),
    "79": ("BRANDED_CONSUMER", "CONSUMER"),
    "80": ("REGULATED_PRODUCT_OR_PROVIDER", "HEALTHCARE"),
    "81": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "82": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "83": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "87": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
}

#: Four-digit codes whose major group would classify them wrongly. Each is
#: here because the group contains two economically different businesses,
#: not to tune one company's answer.
_SIC_EXACT = {
    # Pharmaceuticals and biologics sit inside "chemicals", but they sell an
    # approved product under a regulator's licence, not a commodity.
    "2833": ("REGULATED_PRODUCT_OR_PROVIDER", "HEALTHCARE"),
    "2834": ("REGULATED_PRODUCT_OR_PROVIDER", "HEALTHCARE"),
    "2835": ("REGULATED_PRODUCT_OR_PROVIDER", "HEALTHCARE"),
    "2836": ("REGULATED_PRODUCT_OR_PROVIDER", "HEALTHCARE"),
    # Medical devices sit inside "instruments" and are licensed the same way.
    "3841": ("REGULATED_PRODUCT_OR_PROVIDER", "HEALTHCARE"),
    "3842": ("REGULATED_PRODUCT_OR_PROVIDER", "HEALTHCARE"),
    "3845": ("REGULATED_PRODUCT_OR_PROVIDER", "HEALTHCARE"),
    # Heavy machinery is sold once and serviced for decades; the aftermarket
    # is the business, which is not true of industrial machinery generally.
    "3531": ("MANUFACTURE_AND_AFTERMARKET", "INDUSTRIAL"),
    "3532": ("MANUFACTURE_AND_AFTERMARKET", "INDUSTRIAL"),
    "3533": ("MANUFACTURE_AND_AFTERMARKET", "INDUSTRIAL"),
    "3537": ("MANUFACTURE_AND_AFTERMARKET", "INDUSTRIAL"),
    # Semiconductors and their equipment are design-led, not aftermarket-led.
    "3674": ("DESIGN_AND_MANUFACTURE", "SEMICONDUCTOR"),
    "3559": ("DESIGN_AND_MANUFACTURE", "SEMICONDUCTOR"),
    # Custom programming and systems integration is a people business: it
    # bills for delivered hours, and has none of the renewal economics that
    # make packaged software a subscription.
    "7371": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "7373": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "7374": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
    "7363": ("PEOPLE_OR_ROUTE_BASED_SERVICES", "SERVICES"),
}

#: Residual SIC codes -- the ones whose official name ends "not elsewhere
#: classified" or "miscellaneous". Named explicitly so the refusal to
#: classify is a decision on the record rather than a table lookup that
#: happened to miss.
_SIC_RESIDUAL = frozenset({
    "7389",     # Services-Business Services, NEC
    "7380",     # Services-Miscellaneous Business Services
    "3990",     # Manufacturing Industries, NEC
    "5990",     # Retail Stores, NEC
    "8888",     # Foreign governments / unclassifiable filers
    "6770",     # Blank Checks
    "9995",     # Non-operating establishments
})


def classify_sic(sic: str) -> Optional[Tuple[str, str]]:
    """(business model class, sector) for a SIC code, or None.

    None means "this code does not determine a business model", which is a
    real answer for a residual category and is reported as PROFILE_SPARSE
    rather than filled in.
    """
    code = str(sic or "").strip()
    if not code:
        return None
    code = code.zfill(4) if code.isdigit() and len(code) < 4 else code
    if code in _SIC_RESIDUAL:
        return None
    if code in _SIC_EXACT:
        return _SIC_EXACT[code]
    return _SIC_MAJOR_GROUP.get(code[:2])


# --- the structural economics of each model class ---------------------------
#
# Read each row as: "for a business of this KIND, revenue moves with these,
# cost moves with these, demand arrives like this". None of it is a claim
# about a particular company's results.

_ECONOMICS = {
    "SUBSCRIPTION_SOFTWARE": {
        "business_model": (
            "recurring software subscription: revenue is contracted and "
            "renews, so the installed base carries next period's revenue "
            "before any new sale"),
        "industry_structure": (
            "many differentiated vendors competing on capability and "
            "switching cost rather than on price alone"),
        "revenue_drivers": ("customer count", "seats or usage per customer",
                            "list and realised price", "renewal rate",
                            "expansion within existing accounts"),
        "cost_drivers": ("sales and marketing to acquire an account",
                         "engineering headcount",
                         "infrastructure and delivery cost per unit served",
                         "support cost per account"),
        "demand_model": (
            "budgeted and recurring; new bookings are discretionary, the "
            "renewal base is not"),
        "customer_structure": (
            "many accounts of uneven size; concentration risk sits in the "
            "largest contracts, not in the count"),
        "supplier_structure": (
            "compute and bandwidth from a small number of providers"),
        "pricing_model": (
            "list price with negotiated discount, per seat or per unit of "
            "usage"),
        "operating_leverage": (
            "HIGH: delivery cost rises far more slowly than contracted "
            "revenue, so incremental revenue is unusually valuable"),
        "levers": ("pricing and packaging", "sales motion and coverage",
                   "retention and expansion programmes", "productization",
                   "infrastructure cost per unit served"),
        "archetypes": ("PRICING", "RETENTION", "SALES_MOTION",
                       "PRODUCTIZATION", "CUSTOMER_SEGMENT"),
        "evidence": ("pricing and packaging changes", "product launches",
                     "customer wins and losses", "partnership announcements",
                     "platform or infrastructure changes"),
        "macro": ("MARKET_RATE", "LABOR", "CURRENCY"),
    },
    "DESIGN_AND_MANUFACTURE": {
        "business_model": (
            "design and manufacture of a physical product sold into a "
            "capacity-constrained supply chain"),
        "industry_structure": (
            "few credible suppliers; position turns on process capability "
            "and on access to manufacturing capacity"),
        "revenue_drivers": ("unit volume", "product and node mix",
                            "average selling price", "design wins",
                            "customer concentration"),
        "cost_drivers": ("manufacturing and foundry cost", "yield",
                         "capacity utilisation", "input and energy cost",
                         "R&D to hold the process roadmap"),
        "demand_model": (
            "cyclical and inventory-amplified: end demand is smoothed by "
            "channel inventory, so orders overshoot in both directions"),
        "customer_structure": (
            "concentrated -- a small number of large buyers can move a "
            "quarter on their own ordering decisions"),
        "supplier_structure": (
            "few qualified suppliers with long lead times; substitution is "
            "slow and expensive"),
        "pricing_model": (
            "negotiated contract price by product generation, with volume "
            "and long-term supply commitments"),
        "operating_leverage": (
            "HIGH and two-sided: fixed manufacturing cost rewards "
            "utilisation and punishes an idle line"),
        "levers": ("capacity commitment", "product roadmap and mix",
                   "pricing and supply agreements", "inventory position",
                   "customer diversification"),
        "archetypes": ("CAPACITY", "R&D_ROADMAP", "INVENTORY", "PRICING",
                       "SUPPLY_CHAIN"),
        "evidence": ("capacity and capital expenditure announcements",
                     "product and process generation launches",
                     "supply agreements", "export and trade restrictions",
                     "customer and design-win announcements"),
        "macro": ("INDUSTRIAL_DEMAND", "MARKET_RATE", "CURRENCY"),
    },
    "COMMODITY_PRODUCER": {
        "business_model": (
            "production of an undifferentiated output sold at a price the "
            "producer does not set"),
        "industry_structure": (
            "price-taking producers differentiated by cost position and by "
            "the quality and life of the resource base"),
        "revenue_drivers": ("produced volume", "realised commodity price",
                            "grade or quality of output", "sales mix"),
        "cost_drivers": ("energy and fuel", "labour",
                         "sustaining capital", "haulage and logistics",
                         "input and reagent cost"),
        "demand_model": (
            "externally set: the marginal buyer is the market, so volume "
            "sells and price is the variable"),
        "customer_structure": (
            "sold into a market or under offtake agreements rather than to "
            "a named customer base"),
        "supplier_structure": (
            "energy, equipment and specialised contractors"),
        "pricing_model": (
            "benchmark or spot price, sometimes hedged; the producer sets "
            "volume, not price"),
        "operating_leverage": (
            "HIGH: cost per unit is largely fixed against a price that is "
            "not, so margin swings by more than price does"),
        "levers": ("production plan", "capital allocation and project "
                   "sequencing", "hedging policy", "cost programme",
                   "jurisdictional exposure"),
        "archetypes": ("CAPITAL_ALLOCATION", "CAPACITY", "COST_STRUCTURE",
                       "M&A"),
        "evidence": ("production and operating results",
                     "reserve and resource statements",
                     "project and capital decisions",
                     "permitting and jurisdiction changes",
                     "offtake and hedging arrangements"),
        "macro": ("COMMODITY", "CURRENCY", "MARKET_RATE", "INDUSTRIAL_DEMAND"),
    },
    "BRANDED_CONSUMER": {
        "business_model": (
            "branded product sold through retail and direct channels, where "
            "the brand carries pricing power the product alone would not"),
        "industry_structure": (
            "brand-led competition for shelf and attention against private "
            "label and against other branded entrants"),
        "revenue_drivers": ("volume", "price and promotional depth",
                            "product and channel mix",
                            "distribution and shelf presence"),
        "cost_drivers": ("input and commodity cost", "freight and logistics",
                         "marketing and trade spend", "manufacturing cost"),
        "demand_model": (
            "household consumption: broad, repeat, and sensitive to price "
            "and to real income"),
        "customer_structure": (
            "concentrated retail buyers standing between the brand and many "
            "end consumers"),
        "supplier_structure": (
            "agricultural or industrial inputs exposed to commodity prices"),
        "pricing_model": (
            "list price net of trade promotion; realised price is a "
            "negotiation with the channel"),
        "operating_leverage": (
            "MODERATE: input cost is largely variable, brand investment is "
            "largely discretionary"),
        "levers": ("pricing and promotion", "product mix and innovation",
                   "channel and distribution strategy", "marketing spend",
                   "cost and productivity programmes"),
        "archetypes": ("PRICING", "COST_STRUCTURE", "CUSTOMER_SEGMENT",
                       "MARKET_ENTRY", "PRODUCTIZATION"),
        "evidence": ("pricing and promotional actions", "product launches",
                     "channel and retailer announcements",
                     "input cost commentary", "marketing investment changes"),
        "macro": ("INFLATION", "COMMODITY", "LABOR", "CURRENCY"),
    },
    "CONTRACTED_OR_RATE_BASE_ASSETS": {
        "business_model": (
            "long-lived physical assets earning under contracts or a "
            "regulated rate base, where the asset is the franchise"),
        "industry_structure": (
            "few operators, high barriers, and returns set as much by "
            "contract and regulation as by competition"),
        "revenue_drivers": ("contracted or regulated volume",
                            "tariff or rate", "asset base in service",
                            "contract renewals and escalators"),
        "cost_drivers": ("financing cost", "depreciation",
                         "operations and maintenance", "energy",
                         "construction and connection cost"),
        "demand_model": (
            "contracted or regulated: near-term volume is largely committed "
            "and the decision variable is what to build next"),
        "customer_structure": (
            "few large counterparties under long contracts, or a regulated "
            "customer base"),
        "supplier_structure": (
            "engineering, construction and equipment under multi-year "
            "programmes"),
        "pricing_model": (
            "tariff, regulated return, or long-term contract price -- rarely "
            "a price the operator sets alone"),
        "operating_leverage": (
            "HIGH and financed: the cost base is capital and interest, so "
            "the cost of money is an operating variable"),
        "levers": ("capital programme and sequencing", "financing structure",
                   "contract and tariff negotiation",
                   "operations and reliability", "asset acquisition"),
        "archetypes": ("CAPITAL_ALLOCATION", "CAPACITY",
                       "REGULATORY_RESPONSE", "M&A"),
        "evidence": ("capital projects and commissioning",
                     "contract awards and renewals",
                     "regulatory and tariff decisions", "financing actions",
                     "outage and reliability events"),
        "macro": ("MARKET_RATE", "INFLATION", "COMMODITY",
                  "INDUSTRIAL_DEMAND"),
    },
    "BALANCE_SHEET_OR_NETWORK": {
        "business_model": (
            "earnings from a balance sheet or from a transaction network -- "
            "spread and fees on volume the firm intermediates"),
        "industry_structure": (
            "regulated, scale-driven, and competitive on price of funds, "
            "distribution and trust"),
        "revenue_drivers": ("spread on assets and liabilities",
                            "transaction and fee volume",
                            "balance or asset growth", "take rate"),
        "cost_drivers": ("cost of funds", "credit and fraud losses",
                         "regulatory and compliance cost",
                         "technology and operations"),
        "demand_model": (
            "derived from credit and payments activity in the wider economy "
            "rather than from a product cycle"),
        "customer_structure": (
            "a broad base plus concentrated institutional relationships"),
        "supplier_structure": (
            "depositors, funding markets and network participants"),
        "pricing_model": (
            "rate, spread or take rate, bounded by competition and by "
            "regulation"),
        "operating_leverage": (
            "HIGH on volume and LEVERED on the balance sheet: the same "
            "movement reaches earnings through both margin and credit"),
        "levers": ("pricing of assets and liabilities",
                   "credit and underwriting policy", "funding mix",
                   "capital allocation and distribution",
                   "network and partnership expansion"),
        "archetypes": ("PRICING", "CAPITAL_ALLOCATION", "CUSTOMER_SEGMENT",
                       "REGULATORY_RESPONSE", "COMPETITIVE_RESPONSE"),
        "evidence": ("rate and pricing changes",
                     "credit quality and provisioning commentary",
                     "regulatory actions and capital requirements",
                     "partnership and network announcements",
                     "funding and capital markets activity"),
        "macro": ("MARKET_RATE", "UNEMPLOYMENT", "INFLATION",
                  "INDUSTRIAL_DEMAND"),
    },
    "MANUFACTURE_AND_AFTERMARKET": {
        "business_model": (
            "sale of a long-lived manufactured product followed by a "
            "higher-margin service and parts stream over its life"),
        "industry_structure": (
            "duopoly or oligopoly with certification and installed-base "
            "barriers that make entry slow and displacement rare"),
        "revenue_drivers": ("orders and backlog", "delivery or production "
                            "rate", "aftermarket and services on the "
                            "installed base", "product mix"),
        "cost_drivers": ("supply chain and component availability",
                         "labour and skills", "rework and quality cost",
                         "working capital tied up in production",
                         "development programmes"),
        "demand_model": (
            "long-cycle and order-driven: today's revenue was decided years "
            "ago and today's orders decide revenue years out"),
        "customer_structure": (
            "few large buyers -- operators, fleets or governments -- "
            "purchasing under multi-year agreements"),
        "supplier_structure": (
            "deep multi-tier supply chain where a single qualified supplier "
            "can constrain the whole rate"),
        "pricing_model": (
            "negotiated programme pricing, with aftermarket economics "
            "carrying the return"),
        "operating_leverage": (
            "HIGH against production rate: fixed cost is absorbed by rate, "
            "so a rate change moves margin more than revenue"),
        "levers": ("production rate", "supply chain qualification",
                   "programme and certification management",
                   "aftermarket and services strategy", "working capital"),
        "archetypes": ("CAPACITY", "SUPPLY_CHAIN", "R&D_ROADMAP",
                       "REGULATORY_RESPONSE", "CAPITAL_ALLOCATION"),
        "evidence": ("orders, backlog and deliveries",
                     "production rate decisions",
                     "certification and regulatory milestones",
                     "supplier and quality events",
                     "service and aftermarket agreements"),
        "macro": ("INDUSTRIAL_DEMAND", "MARKET_RATE", "LABOR", "CURRENCY"),
    },
    "PEOPLE_OR_ROUTE_BASED_SERVICES": {
        "business_model": (
            "service delivered by people or over a route network, where "
            "sold capacity is the product and unsold capacity expires"),
        "industry_structure": (
            "competition on capability, reputation and coverage; capacity "
            "is added by hiring or by adding routes"),
        "revenue_drivers": ("billable headcount or capacity",
                            "utilisation", "rate or yield", "engagement mix"),
        "cost_drivers": ("compensation", "recruiting and training",
                         "bench or idle capacity", "delivery and travel"),
        "demand_model": (
            "project or trip-driven and discretionary; demand can be "
            "deferred by the customer at short notice"),
        "customer_structure": (
            "concentrated in large clients or accounts whose own budgets "
            "set the cycle"),
        "supplier_structure": (
            "the labour market itself, plus subcontractors"),
        "pricing_model": (
            "rate per hour, per engagement or per unit of capacity sold"),
        "operating_leverage": (
            "LOW to MODERATE: cost scales with the people delivering, so "
            "margin comes from utilisation and rate, not from volume"),
        "levers": ("hiring and capacity plan", "utilisation management",
                   "pricing and rate card", "engagement and route mix",
                   "client concentration"),
        "archetypes": ("PRICING", "CAPACITY", "CUSTOMER_SEGMENT",
                       "COST_STRUCTURE", "MARKET_ENTRY"),
        "evidence": ("hiring and headcount actions",
                     "client and engagement announcements",
                     "capacity, route or office changes",
                     "pricing and rate commentary",
                     "leadership and practice changes"),
        "macro": ("LABOR", "UNEMPLOYMENT", "INFLATION", "MARKET_RATE"),
    },
    "REGULATED_PRODUCT_OR_PROVIDER": {
        "business_model": (
            "a product or service that may only be sold once a regulator "
            "permits it and a payer agrees to pay for it"),
        "industry_structure": (
            "protected positions of limited life: approval and exclusivity "
            "confer pricing power until they expire"),
        "revenue_drivers": ("approved products and indications",
                            "volume and prescriptions or procedures",
                            "net price after rebates", "exclusivity runway",
                            "geographic and product mix"),
        "cost_drivers": ("research and development",
                         "clinical and trial cost", "manufacturing and "
                         "quality", "commercial and market access",
                         "litigation and settlements"),
        "demand_model": (
            "clinically indicated and payer-mediated: the prescriber "
            "chooses, the payer funds, and the patient consumes"),
        "customer_structure": (
            "payers, systems and distributors rather than end patients"),
        "supplier_structure": (
            "qualified manufacturing and clinical supply under regulatory "
            "control"),
        "pricing_model": (
            "list price net of rebates and negotiated reimbursement; the "
            "net price is rarely the published one"),
        "operating_leverage": (
            "HIGH per approved product: development cost is sunk before the "
            "first sale and marginal supply cost is comparatively small"),
        "levers": ("pipeline and development priorities",
                   "regulatory and approval strategy",
                   "pricing and market access", "portfolio and geographic "
                   "mix", "litigation and settlement posture"),
        "archetypes": ("R&D_ROADMAP", "REGULATORY_RESPONSE", "PRICING",
                       "CAPITAL_ALLOCATION", "MARKET_ENTRY"),
        "evidence": ("regulatory decisions and submissions",
                     "clinical and trial results",
                     "reimbursement and pricing decisions",
                     "litigation and settlement developments",
                     "product launches and withdrawals"),
        "macro": ("INFLATION", "CURRENCY", "LABOR"),
    },
}

#: How each macro channel reaches a business of a given model class. The
#: mechanism is the point: §6 refuses a channel that cannot name one.
_TRANSMISSION = {
    ("MARKET_RATE", "SUBSCRIPTION_SOFTWARE"):
        "rates set the discount rate on customers' own investment cases, so "
        "higher rates lengthen procurement and slow new bookings without "
        "touching the contracted base",
    ("MARKET_RATE", "BALANCE_SHEET_OR_NETWORK"):
        "rates move the cost of funds and the yield on assets at different "
        "speeds, so the spread -- the primary revenue driver -- reprices "
        "directly",
    ("MARKET_RATE", "CONTRACTED_OR_RATE_BASE_ASSETS"):
        "the capital programme is debt-financed, so rates set the cost of "
        "the next asset and the hurdle every project must clear",
    ("MARKET_RATE", "COMMODITY_PRODUCER"):
        "rates set the hurdle for sustaining and expansion capital, and the "
        "carry on inventory and working capital",
    ("MARKET_RATE", "MANUFACTURE_AND_AFTERMARKET"):
        "rates raise the financing cost of customers' fleet purchases and "
        "the carry on the working capital tied up in production",
    ("MARKET_RATE", "DESIGN_AND_MANUFACTURE"):
        "rates set the hurdle on capacity commitments made years before the "
        "revenue they carry",
    ("MARKET_RATE", "PEOPLE_OR_ROUTE_BASED_SERVICES"):
        "rates compress clients' discretionary budgets, which is where "
        "project demand is funded from",
    ("MARKET_RATE", "BRANDED_CONSUMER"):
        "rates reach household discretionary spending and the cost of "
        "carrying inventory through the channel",
    ("CURRENCY", "COMMODITY_PRODUCER"):
        "output is priced in the global currency while cost is incurred in "
        "the local one, so the exchange rate moves realised margin without "
        "any operational change",
    ("CURRENCY", "DESIGN_AND_MANUFACTURE"):
        "manufacturing and sales sit in different currencies, so the rate "
        "moves both landed cost and competitiveness against local rivals",
    ("CURRENCY", "BRANDED_CONSUMER"):
        "overseas revenue translates back at the prevailing rate and "
        "imported inputs are paid at it",
    ("CURRENCY", "MANUFACTURE_AND_AFTERMARKET"):
        "programmes are priced in one currency and sourced across several, "
        "so the rate moves programme margin",
    ("CURRENCY", "SUBSCRIPTION_SOFTWARE"):
        "international contracts translate at the prevailing rate; the "
        "underlying subscription is unaffected",
    ("CURRENCY", "REGULATED_PRODUCT_OR_PROVIDER"):
        "product sold across jurisdictions translates back at the "
        "prevailing rate",
    ("COMMODITY", "COMMODITY_PRODUCER"):
        "the commodity price IS the realised price of output -- this is the "
        "revenue line, not an input to it",
    ("COMMODITY", "BRANDED_CONSUMER"):
        "commodity inputs are the largest variable cost, and passing them "
        "through requires a pricing action the channel must accept",
    ("COMMODITY", "CONTRACTED_OR_RATE_BASE_ASSETS"):
        "fuel and energy are a pass-through in some contracts and a "
        "margin exposure in others",
    ("COMMODITY", "DESIGN_AND_MANUFACTURE"):
        "energy and materials enter manufacturing cost at high utilisation",
    ("INFLATION", "BRANDED_CONSUMER"):
        "inflation raises input and wage cost and simultaneously tests how "
        "much price the brand can carry before volume responds",
    ("INFLATION", "CONTRACTED_OR_RATE_BASE_ASSETS"):
        "many contracts and tariffs escalate with inflation, so it reaches "
        "revenue as well as cost",
    ("INFLATION", "BALANCE_SHEET_OR_NETWORK"):
        "inflation drives the rate policy that sets the spread, and raises "
        "operating cost",
    ("INFLATION", "PEOPLE_OR_ROUTE_BASED_SERVICES"):
        "wages are the cost base, so inflation reaches cost immediately and "
        "reaches price only at the next rate negotiation",
    ("INFLATION", "REGULATED_PRODUCT_OR_PROVIDER"):
        "cost inflates while net price is constrained by payers, so the "
        "squeeze lands on margin",
    ("LABOR", "PEOPLE_OR_ROUTE_BASED_SERVICES"):
        "billable people ARE the capacity, so the labour market sets both "
        "what can be delivered and what it costs",
    ("LABOR", "SUBSCRIPTION_SOFTWARE"):
        "engineering and sales headcount is the dominant cost, so the "
        "labour market sets the cost of the roadmap",
    ("LABOR", "MANUFACTURE_AND_AFTERMARKET"):
        "skilled assembly labour constrains production rate directly",
    ("LABOR", "BRANDED_CONSUMER"):
        "manufacturing and distribution wages enter cost of goods",
    ("UNEMPLOYMENT", "BALANCE_SHEET_OR_NETWORK"):
        "employment is the strongest available proxy for household ability "
        "to repay, so it leads credit losses",
    ("UNEMPLOYMENT", "BRANDED_CONSUMER"):
        "employment sets household income and therefore volume",
    ("UNEMPLOYMENT", "PEOPLE_OR_ROUTE_BASED_SERVICES"):
        "a loose labour market lowers hiring cost and a tight one raises it",
    ("INDUSTRIAL_DEMAND", "DESIGN_AND_MANUFACTURE"):
        "industrial and end-market demand sets order rates, and channel "
        "inventory amplifies the swing on the way through",
    ("INDUSTRIAL_DEMAND", "MANUFACTURE_AND_AFTERMARKET"):
        "end-market activity sets orders now and therefore the production "
        "rate that carries revenue later",
    ("INDUSTRIAL_DEMAND", "COMMODITY_PRODUCER"):
        "industrial activity is the demand side of the price this producer "
        "receives",
    ("INDUSTRIAL_DEMAND", "CONTRACTED_OR_RATE_BASE_ASSETS"):
        "activity sets throughput on the assets and the case for the next "
        "one",
    ("INDUSTRIAL_DEMAND", "BALANCE_SHEET_OR_NETWORK"):
        "activity drives credit demand and transaction volume",
}


# --- one normalisation, at the source --------------------------------------
#
# The tables above are written in this repository's comment style, which uses
# `--` for an aside. That is right in a source file and wrong everywhere the
# strings actually go: they are copied verbatim into `current_read`, into the
# JSON at /demo-dossiers/<c>, into the CEO answers and into the decks, where
# they render as two hyphens mid-sentence.
#
# Fixing it in the HTML renderers was the first attempt and it was the wrong
# layer -- it left the stored decision and the JSON API carrying the raw
# form, so an integrator reading the same field got different text from the
# page. Converted here, once, at import, so every consumer sees one thing.

def _dash(value):
    if isinstance(value, str):
        return value.replace(" -- ", " — ")
    if isinstance(value, tuple):
        return tuple(_dash(v) for v in value)
    if isinstance(value, list):
        return [_dash(v) for v in value]
    if isinstance(value, dict):
        return {k: _dash(v) for k, v in value.items()}
    return value


_ECONOMICS = _dash(_ECONOMICS)
_TRANSMISSION = _dash(_TRANSMISSION)


@dataclasses.dataclass(frozen=True)
class Competitor:
    """One competitor, and why THIS company competes with it."""
    name: str
    why: str
    basis: str          #: the classification that selected it

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class CompanyIntelligenceProfile:
    """What kind of business this is. Derived, never observed.

    `known` is False when the company is not in the validation manifest. A
    profile is then all-UNKNOWN, and the selection layer above degrades to
    the generic reading rather than borrowing another company's economics.
    """
    company_id: str
    company_name: str
    known: bool = False
    basis: str = ""                     #: what this was derived from
    #: PROFILE_AVAILABLE | PROFILE_PARTIAL | PROFILE_SPARSE. Always one of
    #: the three -- there is no state reached by a join quietly failing.
    profile_state: str = PROFILE_SPARSE
    #: Which classifier supplied it: VALIDATION_MANIFEST, SEC_SIC, or NONE.
    profile_source: str = "NONE"
    #: What is missing and what would resolve it. Non-empty whenever the
    #: state is not PROFILE_AVAILABLE, so no surface has to invent the
    #: caveat for itself.
    profile_limitation: str = ""
    sector: str = UNKNOWN
    business_model_class: str = UNKNOWN
    business_model: str = UNKNOWN
    industry_structure: str = UNKNOWN
    primary_revenue_drivers: Tuple[str, ...] = ()
    primary_cost_drivers: Tuple[str, ...] = ()
    capital_intensity: str = UNKNOWN
    demand_model: str = UNKNOWN
    customer_structure: str = UNKNOWN
    supplier_structure: str = UNKNOWN
    pricing_model: str = UNKNOWN
    operating_leverage: str = UNKNOWN
    regulatory_exposure: str = UNKNOWN
    cyclical_exposure: str = UNKNOWN
    relevant_macro_channels: Tuple[str, ...] = ()
    strategic_competitors: Tuple[Competitor, ...] = ()
    primary_management_levers: Tuple[str, ...] = ()
    decision_archetypes: Tuple[str, ...] = ()
    relevant_evidence_types: Tuple[str, ...] = ()
    relevant_causal_questions: Tuple[str, ...] = ()
    relevant_historical_dimensions: Tuple[str, ...] = ()
    public_private: str = UNKNOWN
    multi_segment: bool = False
    contract: str = CONTRACT

    def transmission_for(self, channel: str) -> str:
        """The mechanism by which `channel` reaches THIS kind of business.

        Empty when no mechanism is established -- §6's NO_RELEVANT_EXPOSURE.
        A channel with no mechanism is never shown as an exposure.
        """
        return _TRANSMISSION.get((str(channel).upper(),
                                  self.business_model_class), "")

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["strategic_competitors"] = [c.as_dict()
                                        for c in self.strategic_competitors]
        return out


# --- causal questions, chosen by what this business actually turns on -------
#
# One question per (model class, decision archetype). The pair matters: a
# pricing decision at a bank and a pricing decision at a consumer brand are
# not the same question, and asking both "did the price change work" is the
# collapse in miniature.

_CAUSAL = {
    ("SUBSCRIPTION_SOFTWARE", "PRICING"):
        "Did the pricing or packaging change alter conversion and expansion, "
        "or did it only move realised price on the customers who renewed "
        "anyway?",
    ("SUBSCRIPTION_SOFTWARE", "RETENTION"):
        "Did the retention programme change renewal behaviour, or did it "
        "coincide with a cohort that was always going to renew?",
    ("SUBSCRIPTION_SOFTWARE", "SALES_MOTION"):
        "Did the change in sales motion improve acquisition efficiency "
        "relative to comparable vendors over the same window?",
    ("SUBSCRIPTION_SOFTWARE", "PRODUCTIZATION"):
        "Did the new product reach adoption in the installed base, and did "
        "adopting accounts expand more than comparable accounts that did "
        "not adopt?",
    ("SUBSCRIPTION_SOFTWARE", "CUSTOMER_SEGMENT"):
        "Did the shift toward this customer segment raise contract value "
        "without a matching rise in acquisition cost?",
    ("DESIGN_AND_MANUFACTURE", "CAPACITY"):
        "Did the capacity commitment convert into shipped volume, or into "
        "inventory that the channel had already stocked?",
    ("DESIGN_AND_MANUFACTURE", "R&D_ROADMAP"):
        "Did the new product generation win share at its introduction, "
        "relative to the prior generation's introduction?",
    ("DESIGN_AND_MANUFACTURE", "INVENTORY"):
        "Is the inventory movement a demand signal, or the channel "
        "correcting a position it built ahead of demand?",
    ("DESIGN_AND_MANUFACTURE", "PRICING"):
        "Did the price change hold through the cycle, or was it recovered "
        "by customers at the next contract negotiation?",
    ("DESIGN_AND_MANUFACTURE", "SUPPLY_CHAIN"):
        "Did the supply constraint bind output, or was demand the binding "
        "constraint over the same window?",
    ("COMMODITY_PRODUCER", "CAPITAL_ALLOCATION"):
        "Did the capital committed to this project earn a return "
        "distinguishable from what the commodity price alone delivered?",
    ("COMMODITY_PRODUCER", "CAPACITY"):
        "Did the production increase raise realised revenue, or did it "
        "arrive into a price that fell by as much?",
    ("COMMODITY_PRODUCER", "COST_STRUCTURE"):
        "Did the cost programme lower unit cost relative to comparable "
        "producers facing the same input prices?",
    ("COMMODITY_PRODUCER", "M&A"):
        "Did the acquired asset add production and reserve life at a cost "
        "below building or buying the equivalent elsewhere?",
    ("BRANDED_CONSUMER", "PRICING"):
        "Did the price increase stick in the channel, and how much volume "
        "did it cost relative to categories that did not price?",
    ("BRANDED_CONSUMER", "COST_STRUCTURE"):
        "Did the productivity programme reach gross margin, or was it "
        "absorbed by input cost moving the other way?",
    ("BRANDED_CONSUMER", "PRODUCTIZATION"):
        "Did the launch add incremental volume, or did it move volume from "
        "the company's own existing products?",
    ("BRANDED_CONSUMER", "CUSTOMER_SEGMENT"):
        "Did the segment or channel shift raise realised price per unit "
        "after trade spend?",
    ("BRANDED_CONSUMER", "MARKET_ENTRY"):
        "Did entering this market add volume at a contribution margin "
        "comparable to the established ones?",
    ("CONTRACTED_OR_RATE_BASE_ASSETS", "CAPITAL_ALLOCATION"):
        "Did the asset placed in service earn its contracted return, and "
        "did the financing cost assumed at sanction hold?",
    ("CONTRACTED_OR_RATE_BASE_ASSETS", "CAPACITY"):
        "Did the added capacity get contracted, or is it earning merchant "
        "rates it was not sanctioned against?",
    ("CONTRACTED_OR_RATE_BASE_ASSETS", "REGULATORY_RESPONSE"):
        "Did the regulatory decision change the allowed return in a way "
        "that reaches earnings, or only the timing of recovery?",
    ("CONTRACTED_OR_RATE_BASE_ASSETS", "M&A"):
        "Did the acquired asset add contracted cash flow at a price below "
        "the cost of building it?",
    ("BALANCE_SHEET_OR_NETWORK", "PRICING"):
        "Did the repricing widen the spread, or did the cost of funds "
        "follow it up within the same window?",
    ("BALANCE_SHEET_OR_NETWORK", "CAPITAL_ALLOCATION"):
        "Did the capital deployed into this book earn a return above its "
        "cost once credit losses are recognised?",
    ("BALANCE_SHEET_OR_NETWORK", "CUSTOMER_SEGMENT"):
        "Did growth in this segment come with credit performance "
        "comparable to the existing book?",
    ("BALANCE_SHEET_OR_NETWORK", "REGULATORY_RESPONSE"):
        "Did the regulatory change bind capital allocation, or was the "
        "constraint already slack?",
    ("BALANCE_SHEET_OR_NETWORK", "COMPETITIVE_RESPONSE"):
        "Did the competitor's pricing move take balances, or did the market "
        "reprice as a whole?",
    ("MANUFACTURE_AND_AFTERMARKET", "CAPACITY"):
        "Did the production rate increase convert backlog into deliveries, "
        "or did it accumulate work in progress the supply chain cannot "
        "finish?",
    ("MANUFACTURE_AND_AFTERMARKET", "SUPPLY_CHAIN"):
        "Was the supplier constraint the binding limit on deliveries, or "
        "was internal quality rework the limit over the same window?",
    ("MANUFACTURE_AND_AFTERMARKET", "R&D_ROADMAP"):
        "Did the programme investment convert into orders, and at what lag "
        "relative to comparable programmes?",
    ("MANUFACTURE_AND_AFTERMARKET", "REGULATORY_RESPONSE"):
        "Did the certification milestone change the delivery rate, or only "
        "the permission to deliver?",
    ("MANUFACTURE_AND_AFTERMARKET", "CAPITAL_ALLOCATION"):
        "Did capital committed to the programme earn a return once the "
        "aftermarket stream is counted over the product's life?",
    ("PEOPLE_OR_ROUTE_BASED_SERVICES", "PRICING"):
        "Did the rate increase hold on renewal, or was it conceded back "
        "through scope?",
    ("PEOPLE_OR_ROUTE_BASED_SERVICES", "CAPACITY"):
        "Did the hiring convert into billable utilisation, or into bench?",
    ("PEOPLE_OR_ROUTE_BASED_SERVICES", "CUSTOMER_SEGMENT"):
        "Did the shift in engagement mix raise realised rate per delivered "
        "hour?",
    ("PEOPLE_OR_ROUTE_BASED_SERVICES", "COST_STRUCTURE"):
        "Did the cost action lower delivery cost without lowering "
        "utilisation?",
    ("PEOPLE_OR_ROUTE_BASED_SERVICES", "MARKET_ENTRY"):
        "Did the new market or route reach utilisation comparable to the "
        "established ones, and how long did it take?",
    ("REGULATED_PRODUCT_OR_PROVIDER", "R&D_ROADMAP"):
        "Did the development decision change the probability-weighted value "
        "of the pipeline, or only its timing?",
    ("REGULATED_PRODUCT_OR_PROVIDER", "REGULATORY_RESPONSE"):
        "Did the regulatory decision change the addressable population, or "
        "only the label under which it is reached?",
    ("REGULATED_PRODUCT_OR_PROVIDER", "PRICING"):
        "Did the price action reach NET price after rebates, or was it "
        "absorbed by payers?",
    ("REGULATED_PRODUCT_OR_PROVIDER", "CAPITAL_ALLOCATION"):
        "Did capital moved into this therapeutic area earn a return "
        "distinguishable from the base rate for programmes at that stage?",
    ("REGULATED_PRODUCT_OR_PROVIDER", "MARKET_ENTRY"):
        "Did entering this geography add volume at the net price assumed "
        "when the launch was approved?",
}

#: Which historical regimes are worth replaying for this kind of business.
_HISTORY = {
    "SUBSCRIPTION_SOFTWARE": (
        "periods when the cost of capital rose and enterprise software "
        "budgets were re-approved rather than renewed automatically",
        "periods when a platform shift changed what customers bought"),
    "DESIGN_AND_MANUFACTURE": (
        "inventory correction cycles, where channel stock rather than end "
        "demand set orders",
        "capacity build-outs and the price behaviour when they completed",
        "periods when trade restrictions redrew the addressable market"),
    "COMMODITY_PRODUCER": (
        "commodity price regimes and the producer margin behaviour through "
        "them",
        "currency regimes where cost and revenue currencies diverged",
        "capital cycles when the industry sanctioned supply into strength"),
    "BRANDED_CONSUMER": (
        "input-cost inflation episodes and how much price the category "
        "carried",
        "periods of consumer trade-down toward private label"),
    "CONTRACTED_OR_RATE_BASE_ASSETS": (
        "rate regimes and their effect on the cost of the capital programme",
        "regulatory reset periods and the returns allowed through them"),
    "BALANCE_SHEET_OR_NETWORK": (
        "rate-change regimes and how quickly deposits repriced against "
        "assets",
        "credit cycles and the relationship between employment and losses"),
    "MANUFACTURE_AND_AFTERMARKET": (
        "demand shocks that turned backlog into deferral rather than "
        "cancellation",
        "production rate ramps and where the supply chain broke",
        "certification and grounding episodes and their delivery effect"),
    "PEOPLE_OR_ROUTE_BASED_SERVICES": (
        "periods when client budgets contracted and utilisation fell before "
        "headcount did",
        "tight labour markets and their effect on delivery cost"),
    "REGULATED_PRODUCT_OR_PROVIDER": (
        "exclusivity expiry episodes and the revenue path after them",
        "reimbursement and pricing reform periods",
        "litigation and settlement episodes and their cash effect"),
}


_CAUSAL = _dash(_CAUSAL)
_HISTORY = _dash(_HISTORY)


def _regulatory_exposure(regulatory_class: str, model: str) -> str:
    if regulatory_class == "HEAVILY_REGULATED":
        return ("HEAVY: a regulator can change what this business may sell, "
                "at what price, or how much capital it must hold -- so "
                "regulatory action is a first-order commercial variable, "
                "not a compliance cost")
    if regulatory_class == "REGULATED":
        return ("MATERIAL: licensed and supervised, so regulatory change "
                "reaches operations and cost before it reaches strategy")
    if regulatory_class == "LIGHTLY_REGULATED":
        return ("LIGHT: general commercial regulation applies; no regulator "
                "sets this company's price or permission to sell")
    return UNKNOWN


def _cyclical_exposure(cyclicality: str, model: str) -> str:
    if cyclicality == "CYCLICAL":
        return ("CYCLICAL: demand follows the wider economic cycle, so the "
                "same operating decision produces different outcomes at "
                "different points in it")
    if cyclicality == "DEFENSIVE":
        return ("DEFENSIVE: demand is comparatively insensitive to the "
                "cycle, so a demand change is more likely company-specific "
                "than macro")
    if cyclicality == "SECULAR":
        return ("SECULAR: demand is driven by adoption of the category "
                "rather than by the cycle, so cycle-based reasoning "
                "explains less here than category adoption does")
    return UNKNOWN


def _capital_intensity(level: str, model: str) -> str:
    if level == "HIGH":
        return ("HIGH: growth consumes capital before it produces revenue, "
                "so the cost of capital is an operating variable")
    if level == "MODERATE":
        return "MODERATE: growth requires capital but does not lead it"
    if level == "LOW":
        return ("LOW: growth is funded largely out of operating cost, so "
                "the binding constraint is people and time rather than "
                "capital")
    return UNKNOWN


def _competitors(company, manifest) -> Tuple[Competitor, ...]:
    """Peers selected by business model and sector, never by fame.

    WHY THE MANIFEST AND NOT A LIST OF LARGE COMPANIES. §5 refuses
    "arbitrary famous-company competitors", and a hand-written list is
    exactly that -- it would name the same four or five firms for every
    software company on the list. The manifest already classifies 100
    companies by the two things that decide whether two firms actually
    compete: what they sell and how they make money.

    Every row states its own basis, so a reader can reject one. The
    strongest tie is a shared business model AND sector; a shared sector
    alone is a weaker claim and says so.
    """
    if company is None or manifest is None:
        return ()
    strong, weak = [], []
    for other in manifest.companies:
        if other.company_id == company.company_id:
            continue
        if other.parent_company_id == company.company_id or \
                company.parent_company_id == other.company_id:
            continue
        same_model = other.business_model_class == company.business_model_class
        same_sector = other.sector == company.sector
        if same_model and same_sector:
            row = Competitor(
                name=other.canonical_name,
                why=(f"operates the same business model "
                     f"({_pretty(company.business_model_class)}) in the same "
                     f"sector ({_pretty(company.sector)}), so it competes "
                     f"for the same customers and is exposed to the same "
                     f"cost and demand drivers"),
                basis="SAME_MODEL_AND_SECTOR")
            # Same geography and size make the overlap tighter; used to
            # order, never to invent a claim.
            rank = (0 if other.primary_geography == company.primary_geography
                    else 1,
                    0 if other.company_size_class == company.company_size_class
                    else 1, other.canonical_name)
            strong.append((rank, row))
        elif same_sector:
            weak.append(((0, 0, other.canonical_name), Competitor(
                name=other.canonical_name,
                why=(f"same sector ({_pretty(company.sector)}) but a "
                     f"different business model "
                     f"({_pretty(other.business_model_class)}): it competes "
                     f"for the same end demand without the same economics"),
                basis="SAME_SECTOR_DIFFERENT_MODEL")))
    strong.sort(key=lambda r: r[0])
    weak.sort(key=lambda r: r[0])
    rows = [r for _, r in strong][:5]
    if len(rows) < 3:
        rows += [r for _, r in weak][:3 - len(rows)]
    return tuple(rows)


def _pretty(token: str) -> str:
    """An enum, as English. §17 forbids a raw enum reaching a reader."""
    return str(token or "").replace("_", " ").lower()


def _causal_questions(model: str, archetypes) -> Tuple[str, ...]:
    out = []
    for archetype in archetypes:
        question = _CAUSAL.get((model, archetype))
        if question and question not in out:
            out.append(question)
    return tuple(out)


@dataclasses.dataclass(frozen=True)
class _Classified:
    """A company classified by the regulator rather than by the manifest.

    Carries exactly the fields the tables below key on, so the SIC-derived
    path runs the SAME selection code as a manifest company instead of a
    parallel one that could drift. The fields the manifest would have added
    per company -- capital intensity, cyclicality, regulatory class -- stay
    UNKNOWN, which is why the state is PARTIAL.
    """
    company_id: str
    canonical_name: str
    sector: str
    business_model_class: str
    parent_company_id: Optional[str] = None
    primary_geography: str = UNKNOWN
    company_size_class: str = UNKNOWN
    capital_intensity_class: str = UNKNOWN
    cyclicality_class: str = UNKNOWN
    regulatory_class: str = UNKNOWN
    public_private: str = UNKNOWN
    multi_segment: bool = False


def profile_for(company_id: str = "", *, name: str = "", domain: str = "",
                manifest=None, registrant=None) -> CompanyIntelligenceProfile:
    """The profile for one company, with its quality stated.

    Three outcomes, always one of them explicitly:

      * in the validation manifest -> PROFILE_AVAILABLE;
      * not in it, but the SEC has classified the registrant -> the model
        class the regulator's SIC code implies, PROFILE_PARTIAL;
      * neither -> PROFILE_SPARSE, naming what is missing.

    `registrant` is `edgar.registrant_classification()`'s result, passed in
    rather than fetched here so this module makes no network call.

    Never raises: a manifest that cannot be loaded produces a sparse
    profile. Failing the analysis because a classification file is missing
    would be worse than analysing without it.
    """
    company = None
    if manifest is None:
        try:
            from intent_engine.validation import load
            manifest = load()
        except Exception:                                   # noqa: BLE001
            manifest = None
    if manifest is not None:
        try:
            company = manifest.resolve(domain=domain, name=name,
                                       company_id=company_id)
        except Exception:                                   # noqa: BLE001
            company = None
    display = name or company_id
    state = PROFILE_AVAILABLE
    source = "VALIDATION_MANIFEST"
    limitation = ""
    if company is None:
        # The manifest does not contain this company. That is a statement
        # about the manifest -- a curated 100-company validation universe --
        # and not about whether the company is known.
        sic = str((registrant or {}).get("sic") or "").strip()
        sic_text = str((registrant or {}).get("sic_description") or "").strip()
        derived = classify_sic(sic)
        if derived is None:
            why = (f"the regulator's industry code for this filer "
                   f"({sic} {sic_text}) is a residual category that does not "
                   f"determine a business model"
                   if sic else
                   "this company is not in the validation manifest and no "
                   "regulator industry classification was found for it")
            return CompanyIntelligenceProfile(
                company_id=company_id, company_name=display, known=False,
                profile_state=PROFILE_SPARSE, profile_source="NONE",
                profile_limitation=(
                    f"What kind of business this is has not been "
                    f"established: {why}. The analysis below is selected "
                    f"from the published record alone, so it does not use "
                    f"this company's business model to decide what is worth "
                    f"asking. Adding this company to the validation manifest "
                    f"would resolve it."),
                basis=(f"business model not classified -- {why}"))
        model, sector = derived
        company = _Classified(
            company_id=company_id or display, canonical_name=display,
            sector=sector, business_model_class=model)
        state = PROFILE_PARTIAL
        source = "SEC_SIC"
        cited = f"{sic} {sic_text}".strip()
        limitation = (
            f"Classified from the regulator's own industry code for this "
            f"filer ({cited}) rather than from the validation "
            f"manifest. The business model is therefore established and the "
            f"analysis is selected for it; what is not established is the "
            f"within-industry detail the manifest records per company -- "
            f"capital intensity, demand cyclicality and regulatory regime "
            f"are not used below, and are shown as not established.")
    econ = _ECONOMICS.get(company.business_model_class)
    if econ is None:
        return CompanyIntelligenceProfile(
            company_id=company.company_id, company_name=company.canonical_name,
            known=False, sector=company.sector,
            profile_state=PROFILE_SPARSE, profile_source="NONE",
            profile_limitation=(
                f"This company is classified as "
                f"{_pretty(company.business_model_class)}, which this build "
                f"has no economic profile for, so the analysis below does "
                f"not use its business model."),
            business_model_class=company.business_model_class,
            basis=(f"business model class {company.business_model_class!r} "
                   f"has no economic profile in this build"))
    archetypes = tuple(econ["archetypes"])
    channels = tuple(c for c in econ["macro"]
                     if (c, company.business_model_class) in _TRANSMISSION)
    return CompanyIntelligenceProfile(
        company_id=company.company_id,
        company_name=company.canonical_name,
        known=True,
        profile_state=state,
        profile_source=source,
        profile_limitation=limitation,
        basis=(f"derived from the validation manifest classification: "
               f"{_pretty(company.sector)} sector, "
               f"{_pretty(company.business_model_class)} business model, "
               f"{_pretty(company.capital_intensity_class)} capital "
               f"intensity, {_pretty(company.cyclicality_class)} demand, "
               f"{_pretty(company.regulatory_class)}"
               if state == PROFILE_AVAILABLE else
               f"derived from the industry classification the regulator "
               f"assigns this filer: {_pretty(company.sector)} sector, "
               f"{_pretty(company.business_model_class)} business model"),
        sector=company.sector,
        business_model_class=company.business_model_class,
        business_model=econ["business_model"],
        industry_structure=econ["industry_structure"],
        primary_revenue_drivers=tuple(econ["revenue_drivers"]),
        primary_cost_drivers=tuple(econ["cost_drivers"]),
        capital_intensity=_capital_intensity(company.capital_intensity_class,
                                             company.business_model_class),
        demand_model=econ["demand_model"],
        customer_structure=econ["customer_structure"],
        supplier_structure=econ["supplier_structure"],
        pricing_model=econ["pricing_model"],
        operating_leverage=econ["operating_leverage"],
        regulatory_exposure=_regulatory_exposure(company.regulatory_class,
                                                 company.business_model_class),
        cyclical_exposure=_cyclical_exposure(company.cyclicality_class,
                                             company.business_model_class),
        relevant_macro_channels=channels,
        strategic_competitors=_competitors(company, manifest),
        primary_management_levers=tuple(econ["levers"]),
        decision_archetypes=archetypes,
        relevant_evidence_types=tuple(econ["evidence"]),
        relevant_causal_questions=_causal_questions(
            company.business_model_class, archetypes),
        relevant_historical_dimensions=tuple(
            _HISTORY.get(company.business_model_class, ())),
        public_private=company.public_private,
        multi_segment=company.multi_segment,
    )
