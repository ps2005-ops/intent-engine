"""CompanyPredictionUniverse — versioned, classified, safety-enforcing.

Four classes, and the class dictates what the engine may DO with a company:

  A. PUBLIC_AND_TRADABLE     research + market predictions + Alpaca paper orders
  B. PUBLIC_BUT_NOT_ELIGIBLE research + predictions, but NO order until liquidity
                             / data / risk / instrument requirements pass
  C. PRIVATE_COMPANY         strategic reasoning + Synthetic Worlds ONLY —
                             never converted into a stock order
  D. BENCHMARK_OR_PROXY      a sector ETF / index / public competitor used when
                             direct trading is unavailable; ALWAYS labelled a
                             proxy; never implies the private company's own
                             performance

`validate()` enforces these as invariants, not conventions — e.g. a private
company that is somehow flagged paper-trading-eligible is a hard error. The
whole point is that no configuration mistake can turn a private company into a
real (even simulated-real) trade.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

# Bump when the universe's SHAPE or seeded membership changes materially.
UNIVERSE_SCHEMA_VERSION = "universe.v1"


class CompanyClass(str, Enum):
    PUBLIC_AND_TRADABLE = "PUBLIC_AND_TRADABLE"
    PUBLIC_BUT_NOT_ELIGIBLE = "PUBLIC_BUT_NOT_ELIGIBLE"
    PRIVATE_COMPANY = "PRIVATE_COMPANY"
    BENCHMARK_OR_PROXY = "BENCHMARK_OR_PROXY"


class UniverseValidationError(ValueError):
    """A company profile violates a class invariant (e.g. a private tradable)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CompanyProfile(BaseModel):
    company_id: str
    canonical_name: str
    classification: CompanyClass
    is_public: bool
    ticker: Optional[str] = None
    exchange: Optional[str] = None
    # The company's own site. Required for research: the ingestion pipeline is
    # domain-driven (it discovers sources from a domain), and `evidence_sources`
    # below is a list of source KINDS ("10-Q", "shareholder letter") rather than
    # anywhere to fetch. Without this the autonomous research cycle has nothing
    # to point at, which is why it produced no evidence at all.
    website: Optional[str] = None
    tradable_instrument: Optional[str] = None   # symbol Alpaca actually trades
    sector: Optional[str] = None
    # Coverage measurement reported market_cap and region as 0 for the whole
    # universe -- not "we cover none", but "the engine cannot see these
    # dimensions at all". A lesson learned only on mega-cap North American
    # technology does not generalise, and nothing could detect that.
    market_cap: Optional[str] = None            # mega | large | mid | small | micro
    region: Optional[str] = None
    industry: Optional[str] = None
    business_model: Optional[str] = None
    competitors: List[str] = Field(default_factory=list)
    benchmarks: List[str] = Field(default_factory=list)   # ETFs / indices
    products: List[str] = Field(default_factory=list)
    strategic_priorities: List[str] = Field(default_factory=list)
    evidence_sources: List[str] = Field(default_factory=list)
    peer_group: Optional[str] = None            # for cross-company learning
    # eligibility (defaults are conservative; only A is trade-eligible)
    prediction_eligible: bool = True
    paper_trading_eligible: bool = False
    # proxy labelling (class D, or a private company's optional proxy)
    proxy_instrument: Optional[str] = None
    proxy_of: Optional[str] = None              # company_id this is a proxy for
    inclusion_reason: str = ""

    @property
    def may_generate_order(self) -> bool:
        """The single gate the execution service trusts. True ONLY for a public,
        tradable, paper-eligible company with a real instrument. Structurally
        False for every private company."""
        return bool(
            self.classification == CompanyClass.PUBLIC_AND_TRADABLE
            and self.is_public
            and self.paper_trading_eligible
            and self.tradable_instrument)

    def validate_consistency(self) -> None:
        c = self.classification
        if c == CompanyClass.PRIVATE_COMPANY:
            if self.is_public:
                raise UniverseValidationError(
                    f"{self.company_id}: PRIVATE_COMPANY marked is_public")
            if self.paper_trading_eligible or self.tradable_instrument:
                raise UniverseValidationError(
                    f"{self.company_id}: a PRIVATE_COMPANY can never be trade-"
                    "eligible or carry a tradable instrument")
        elif c == CompanyClass.PUBLIC_AND_TRADABLE:
            if not self.is_public:
                raise UniverseValidationError(
                    f"{self.company_id}: PUBLIC_AND_TRADABLE not is_public")
            if not self.tradable_instrument:
                raise UniverseValidationError(
                    f"{self.company_id}: PUBLIC_AND_TRADABLE needs a "
                    "tradable_instrument")
            if not self.paper_trading_eligible:
                raise UniverseValidationError(
                    f"{self.company_id}: PUBLIC_AND_TRADABLE must be paper-"
                    "trading-eligible (else classify as PUBLIC_BUT_NOT_ELIGIBLE)")
        elif c == CompanyClass.PUBLIC_BUT_NOT_ELIGIBLE:
            if not self.is_public:
                raise UniverseValidationError(
                    f"{self.company_id}: PUBLIC_BUT_NOT_ELIGIBLE not is_public")
            if self.paper_trading_eligible:
                raise UniverseValidationError(
                    f"{self.company_id}: PUBLIC_BUT_NOT_ELIGIBLE cannot be "
                    "paper-trading-eligible")
        elif c == CompanyClass.BENCHMARK_OR_PROXY:
            if not self.proxy_of:
                raise UniverseValidationError(
                    f"{self.company_id}: a BENCHMARK_OR_PROXY must name the "
                    "company_id it is a proxy_of (labelling requirement)")
            if not (self.tradable_instrument or self.proxy_instrument):
                raise UniverseValidationError(
                    f"{self.company_id}: proxy needs an instrument")


class CompanyPredictionUniverse(BaseModel):
    version: str = UNIVERSE_SCHEMA_VERSION
    label: str = "default"
    created_at: str = Field(default_factory=_now)
    companies: List[CompanyProfile] = Field(default_factory=list)

    def validate(self) -> "CompanyPredictionUniverse":
        seen = set()
        for c in self.companies:
            if c.company_id in seen:
                raise UniverseValidationError(f"duplicate company_id {c.company_id!r}")
            seen.add(c.company_id)
            c.validate_consistency()
        # every proxy must point at a company that exists in the universe
        for c in self.companies:
            if c.classification == CompanyClass.BENCHMARK_OR_PROXY and \
                    c.proxy_of not in seen:
                raise UniverseValidationError(
                    f"{c.company_id}: proxy_of {c.proxy_of!r} not in universe")
        return self

    # -- lookups -------------------------------------------------------------
    def by_id(self, company_id: str) -> Optional[CompanyProfile]:
        return next((c for c in self.companies if c.company_id == company_id), None)

    def by_instrument(self, symbol: str) -> Optional[CompanyProfile]:
        sym = (symbol or "").upper()
        return next((c for c in self.companies
                     if (c.tradable_instrument or "").upper() == sym), None)

    def tradable(self) -> List[CompanyProfile]:
        return [c for c in self.companies if c.may_generate_order]

    def prediction_companies(self) -> List[CompanyProfile]:
        return [c for c in self.companies if c.prediction_eligible
                and c.classification != CompanyClass.BENCHMARK_OR_PROXY]

    def private(self) -> List[CompanyProfile]:
        return [c for c in self.companies
                if c.classification == CompanyClass.PRIVATE_COMPANY]

    def proxies(self) -> List[CompanyProfile]:
        return [c for c in self.companies
                if c.classification == CompanyClass.BENCHMARK_OR_PROXY]

    def peer_groups(self) -> Dict[str, List[str]]:
        groups: Dict[str, List[str]] = {}
        for c in self.companies:
            if c.peer_group:
                groups.setdefault(c.peer_group, []).append(c.company_id)
        return groups


# --- default seed (illustrative; Pratham configures the real universe) -------
def default_universe() -> CompanyPredictionUniverse:
    """Three structurally different public companies (the section-18 acceptance
    set) + one private company + one labelled proxy. This is a STARTING seed;
    the real universe is chosen by the founder (see MANUAL ACTIONS)."""
    companies = [
        CompanyProfile(
            company_id="shopify",
            market_cap="large", region="North America", canonical_name="Shopify Inc.",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.shopify.com",
            ticker="SHOP", exchange="NYSE", tradable_instrument="SHOP",
            sector="Technology", industry="E-commerce platform",
            business_model="commerce platform + merchant services",
            competitors=["amazon", "bigcommerce", "square"],
            benchmarks=["XLK", "IGV"], products=["Shopify Payments", "Shop App"],
            strategic_priorities=["enterprise (Plus)", "payments attach",
                                  "international"],
            evidence_sources=["10-Q", "shareholder letter", "GMV disclosures"],
            peer_group="ecommerce_platform",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="liquid large-cap commerce platform; rich filings"),
        CompanyProfile(
            company_id="cloudflare",
            market_cap="large", region="North America", canonical_name="Cloudflare, Inc.",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.cloudflare.com",
            ticker="NET", exchange="NYSE", tradable_instrument="NET",
            sector="Technology", industry="Internet infrastructure / security",
            business_model="usage + subscription infrastructure",
            competitors=["akamai", "fastly", "aws"],
            benchmarks=["WCLD", "IGV"], products=["Workers", "Zero Trust", "CDN"],
            strategic_priorities=["developer platform (Workers)",
                                  "enterprise Zero Trust", "AI inference"],
            evidence_sources=["10-Q", "product changelog", "status incidents"],
            peer_group="infrastructure",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="structurally different (infra/usage) vs Shopify"),
        CompanyProfile(
            company_id="duolingo",
            market_cap="mid", region="North America", canonical_name="Duolingo, Inc.",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.duolingo.com",
            ticker="DUOL", exchange="NASDAQ", tradable_instrument="DUOL",
            sector="Consumer", industry="Consumer subscription / edtech",
            business_model="freemium consumer subscription + ads",
            competitors=["babbel", "busuu", "rosetta_stone"],
            benchmarks=["XLC"], products=["Duolingo App", "Super", "Duolingo Max"],
            strategic_priorities=["Max (AI) attach", "DAU growth",
                                  "subscription conversion"],
            evidence_sources=["10-Q", "shareholder letter", "app-store ranks"],
            peer_group="consumer_subscription",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="third structural model: consumer subscription"),
        # -- one PRIVATE company: researched + strategic reasoning only -------
        CompanyProfile(
            company_id="stripe",
            market_cap="large", region="North America", canonical_name="Stripe, Inc.",
            classification=CompanyClass.PRIVATE_COMPANY, is_public=False,
            website="https://stripe.com",
            ticker=None, exchange=None, tradable_instrument=None,
            sector="Fintech", industry="Payments infrastructure",
            business_model="payments take-rate + platform",
            competitors=["adyen", "paypal", "block"],
            benchmarks=["IPAY"], products=["Payments", "Billing", "Connect"],
            strategic_priorities=["enterprise expansion", "platform breadth"],
            evidence_sources=["press", "developer changelog", "hiring signals"],
            peer_group="fintech",
            prediction_eligible=True,          # strategic predictions allowed...
            paper_trading_eligible=False,      # ...but NEVER a stock order
            inclusion_reason="private; strategic reasoning + Synthetic Worlds "
                             "only — no direct instrument exists"),
        # -- one labelled PROXY for the private company (class D) -------------
        CompanyProfile(
            company_id="stripe_proxy_ipay",
            market_cap="large", region="North America", canonical_name="Fintech ETF (IPAY)",
            classification=CompanyClass.BENCHMARK_OR_PROXY, is_public=True,
            ticker="IPAY", exchange="NYSE ARCA", tradable_instrument="IPAY",
            sector="Fintech", industry="Payments ETF",
            business_model="ETF (basket)",
            benchmarks=["IPAY"], peer_group="fintech",
            prediction_eligible=False,         # proxy: not a company prediction
            paper_trading_eligible=True,       # tradable, but explicitly a proxy
            proxy_instrument="IPAY", proxy_of="stripe",
            inclusion_reason="LABELLED PROXY for Stripe exposure — proxy "
                             "performance is NOT Stripe's own performance"),
        # -- BREADTH (cycle 7) ------------------------------------------------
        # Chosen to close the coverage gaps measurement actually found: eight
        # missing sectors, every market-cap bucket, every region outside North
        # America. Deliberately NOT more technology large-caps -- the engine
        # already had three, and a fourth would add samples without adding a
        # dimension it could learn along.
        #
        # Each is public, liquid and files publicly, so the evidence pipeline
        # has something real to read. Paper-trading eligible: no capital is at
        # risk anywhere in this system.
        CompanyProfile(
            company_id="johnson_johnson", canonical_name="Johnson & Johnson",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.jnj.com",
            ticker="JNJ", exchange="NYSE", tradable_instrument="JNJ",
            sector="Healthcare", industry="Pharmaceuticals and medical devices",
            market_cap="mega", region="North America",
            peer_group="pharma_large",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="defensive healthcare mega-cap; the engine had no healthcare at all"),
        CompanyProfile(
            company_id="jpmorgan", canonical_name="JPMorgan Chase & Co.",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.jpmorganchase.com",
            ticker="JPM", exchange="NYSE", tradable_instrument="JPM",
            sector="Financials", industry="Diversified banking",
            market_cap="mega", region="North America",
            peer_group="money_center_bank",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="financials are absent, and banks respond to macro unlike any current holding"),
        CompanyProfile(
            company_id="exxon_mobil", canonical_name="Exxon Mobil Corporation",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://corporate.exxonmobil.com",
            ticker="XOM", exchange="NYSE", tradable_instrument="XOM",
            sector="Energy", industry="Integrated oil and gas",
            market_cap="mega", region="North America",
            peer_group="integrated_energy",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="energy is absent and is the clearest cyclical in the market"),
        CompanyProfile(
            company_id="caterpillar", canonical_name="Caterpillar Inc.",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.caterpillar.com",
            ticker="CAT", exchange="NYSE", tradable_instrument="CAT",
            sector="Industrials", industry="Heavy machinery",
            market_cap="large", region="North America",
            peer_group="capital_goods",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="industrials absent; a classic early-cycle bellwether"),
        CompanyProfile(
            company_id="nextera", canonical_name="NextEra Energy, Inc.",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.nexteraenergy.com",
            ticker="NEE", exchange="NYSE", tradable_instrument="NEE",
            sector="Utilities", industry="Regulated and renewable utility",
            market_cap="large", region="North America",
            peer_group="regulated_utility",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="utilities absent; rate-sensitive in a way nothing else here is"),
        CompanyProfile(
            company_id="procter_gamble", canonical_name="The Procter & Gamble Company",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://us.pg.com",
            ticker="PG", exchange="NYSE", tradable_instrument="PG",
            sector="Consumer Staples", industry="Household and personal products",
            market_cap="mega", region="North America",
            peer_group="consumer_staples",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="staples absent; the defensive counterweight to every growth name held"),
        CompanyProfile(
            company_id="linde", canonical_name="Linde plc",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.linde.com",
            ticker="LIN", exchange="NASDAQ", tradable_instrument="LIN",
            sector="Materials", industry="Industrial gases",
            market_cap="large", region="Europe",
            peer_group="industrial_gases",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="materials absent, and the first European domicile in the universe"),
        CompanyProfile(
            company_id="asml", canonical_name="ASML Holding N.V.",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.asml.com",
            ticker="ASML", exchange="NASDAQ", tradable_instrument="ASML",
            sector="Technology", industry="Semiconductor lithography",
            market_cap="mega", region="Europe",
            peer_group="semiconductor_equipment",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="European technology with a monopoly structure unlike any US holding"),
        CompanyProfile(
            company_id="toyota", canonical_name="Toyota Motor Corporation",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://global.toyota",
            ticker="TM", exchange="NYSE", tradable_instrument="TM",
            sector="Consumer Discretionary", industry="Automobiles",
            market_cap="mega", region="Asia",
            peer_group="automotive",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="first Asian domicile; a manufacturer, which the universe had none of"),
        CompanyProfile(
            company_id="infosys", canonical_name="Infosys Limited",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.infosys.com",
            ticker="INFY", exchange="NYSE", tradable_instrument="INFY",
            sector="Technology", industry="IT services and consulting",
            market_cap="large", region="Emerging",
            peer_group="it_services",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="first emerging-market domicile; a services model, not a product one"),
        CompanyProfile(
            company_id="etsy", canonical_name="Etsy, Inc.",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.etsy.com",
            ticker="ETSY", exchange="NASDAQ", tradable_instrument="ETSY",
            sector="Consumer Discretionary", industry="Online marketplace",
            market_cap="mid", region="North America",
            peer_group="ecommerce_marketplace",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="mid-cap; the universe was entirely large and mega outside Duolingo"),
        CompanyProfile(
            company_id="olo", canonical_name="Olo Inc.",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.olo.com",
            ticker="OLO", exchange="NYSE", tradable_instrument="OLO",
            sector="Technology", industry="Restaurant commerce software",
            market_cap="small", region="North America",
            peer_group="vertical_saas",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="first small-cap; small-caps behave differently enough to be their own test"),
        # -- CROSS-SECTIONAL BREADTH (cycle/day 5) ----------------------------
        # Chosen for DATE, REGION, VENUE and REGIME diversity -- not for ease of
        # retrieval, which is the pseudo-breadth failure: a universe that looks
        # diverse while every filing lands in the same US earnings weeks under
        # the same macro regime.
        #
        # The falsification that justified this is in the operating log: each
        # added company still contributes ~87 genuinely NEW event dates, and
        # 14 companies cover only 29% of calendar days against a 3-day window
        # ceiling with 816 windows of headroom.
        #
        # Regions deliberately outside North America and Western Europe, and
        # the Communication Services / micro-cap gaps closed.
        CompanyProfile(
            company_id="comcast", canonical_name="Comcast Corporation",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://corporate.comcast.com",
            ticker="CMCSA", exchange="NASDAQ", tradable_instrument="CMCSA",
            sector="Communication Services", industry="Cable and media",
            market_cap="mega", region="North America",
            peer_group="cable_media",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="closes the last missing sector"),
        CompanyProfile(
            company_id="mercadolibre", canonical_name="MercadoLibre, Inc.",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://investor.mercadolibre.com",
            ticker="MELI", exchange="NASDAQ", tradable_instrument="MELI",
            sector="Consumer Discretionary", industry="Latin American e-commerce",
            market_cap="large", region="Latin America",
            peer_group="ecommerce_marketplace",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="first Latin American exposure; a different macro cycle entirely"),
        CompanyProfile(
            company_id="vale", canonical_name="Vale S.A.",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://vale.com",
            ticker="VALE", exchange="NYSE", tradable_instrument="VALE",
            sector="Materials", industry="Iron ore and nickel mining",
            market_cap="large", region="Latin America",
            peer_group="mining",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="Brazilian commodity cycle -- macro exposure unlike anything held"),
        CompanyProfile(
            company_id="bhp", canonical_name="BHP Group Limited",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.bhp.com",
            ticker="BHP", exchange="NYSE", tradable_instrument="BHP",
            sector="Materials", industry="Diversified mining",
            market_cap="mega", region="Australia",
            peer_group="mining",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="first Australian domicile and reporting calendar"),
        CompanyProfile(
            company_id="honda", canonical_name="Honda Motor Co., Ltd.",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://global.honda",
            ticker="HMC", exchange="NYSE", tradable_instrument="HMC",
            sector="Consumer Discretionary", industry="Automobiles and motorcycles",
            market_cap="large", region="Asia",
            peer_group="automotive",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="second Japanese issuer; 6-K cadence differs from Toyota's"),
        CompanyProfile(
            company_id="hdfc_bank", canonical_name="HDFC Bank Limited",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.hdfcbank.com",
            ticker="HDB", exchange="NYSE", tradable_instrument="HDB",
            sector="Financials", industry="Indian retail banking",
            market_cap="large", region="Emerging",
            peer_group="retail_bank",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="Indian rate cycle; emerging-market financials absent"),
        CompanyProfile(
            company_id="checkpoint", canonical_name="Check Point Software",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.checkpoint.com",
            ticker="CHKP", exchange="NASDAQ", tradable_instrument="CHKP",
            sector="Technology", industry="Cybersecurity software",
            market_cap="mid", region="Middle East",
            peer_group="security_software",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="first Israeli issuer and Middle East region"),
        CompanyProfile(
            company_id="canadian_national", canonical_name="Canadian National Railway",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.cn.ca",
            ticker="CNI", exchange="NYSE", tradable_instrument="CNI",
            sector="Industrials", industry="Freight rail",
            market_cap="large", region="North America",
            peer_group="rail",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="Canadian venue and reporting regime; rail is a distinct cycle"),
        CompanyProfile(
            company_id="america_movil", canonical_name="America Movil",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.americamovil.com",
            ticker="AMX", exchange="NYSE", tradable_instrument="AMX",
            sector="Communication Services", industry="Latin American telecom",
            market_cap="large", region="Latin America",
            peer_group="telecom",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="Mexican telecom; regulated LatAm exposure"),
        CompanyProfile(
            company_id="sea_limited", canonical_name="Sea Limited",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.sea.com",
            ticker="SE", exchange="NYSE", tradable_instrument="SE",
            sector="Consumer Discretionary", industry="Southeast Asian internet",
            market_cap="large", region="Asia",
            peer_group="internet_platform",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="Singapore domicile; SE Asian consumer cycle"),
        CompanyProfile(
            company_id="sasol", canonical_name="Sasol Limited",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.sasol.com",
            ticker="SSL", exchange="NYSE", tradable_instrument="SSL",
            sector="Energy", industry="Integrated chemicals and energy",
            market_cap="small", region="Africa",
            peer_group="chemicals",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="first African domicile; small-cap energy"),
        CompanyProfile(
            company_id="grifols", canonical_name="Grifols S.A.",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
            website="https://www.grifols.com",
            ticker="GRFS", exchange="NASDAQ", tradable_instrument="GRFS",
            sector="Healthcare", industry="Plasma-derived medicines",
            market_cap="small", region="Europe",
            peer_group="biopharma",
            prediction_eligible=True, paper_trading_eligible=True,
            inclusion_reason="small-cap European healthcare; a filing calendar unlike the US majors"),
    ]
    return CompanyPredictionUniverse(
        version=UNIVERSE_SCHEMA_VERSION, label="breadth-v2-27public-1private-1proxy",
        companies=companies).validate()
