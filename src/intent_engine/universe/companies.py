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
    tradable_instrument: Optional[str] = None   # symbol Alpaca actually trades
    sector: Optional[str] = None
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
            company_id="shopify", canonical_name="Shopify Inc.",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
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
            company_id="cloudflare", canonical_name="Cloudflare, Inc.",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
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
            company_id="duolingo", canonical_name="Duolingo, Inc.",
            classification=CompanyClass.PUBLIC_AND_TRADABLE, is_public=True,
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
            company_id="stripe", canonical_name="Stripe, Inc.",
            classification=CompanyClass.PRIVATE_COMPANY, is_public=False,
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
            company_id="stripe_proxy_ipay", canonical_name="Fintech ETF (IPAY)",
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
    ]
    return CompanyPredictionUniverse(
        version=UNIVERSE_SCHEMA_VERSION, label="seed-3public-1private-1proxy",
        companies=companies).validate()
