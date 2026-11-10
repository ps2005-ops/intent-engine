"""What may be forecast, and what each instrument may be used to say.

TWO UNIVERSES, NEVER POOLED
---------------------------
* ETF: broad equity, the nine original sector SPDRs, Treasuries and credit,
  and commodities. Their signals are MACRO_PROXY or SECTOR_PROXY: a claim
  about an asset class, never about a company.
* COMPANY: the US-listed public companies of the curated validation
  manifest (`intent_engine.validation`), with the business-model class the
  manifest gives them. Their target is the stock MINUS SPY, so a company
  signal is a claim about that company relative to the market, not a beta
  bet wearing a company's name.

The two report in separate tables, and no metric averages across them.

A PRIVATE COMPANY HAS NO SECURITY
---------------------------------
`listed_security` refuses a private company outright. It does not map one
to a peer, a sector ETF or an index: a forecast about a proxy is a forecast
about the proxy, and labelling it with the private company's name would put
a claim on a company that no price can ever test.

THE SECTOR ETFs ARE NOT GIVEN A BUSINESS-MODEL CLASS
---------------------------------------------------
`econ_decision.transmissions` refuses a mechanism guessed from a sector
("a mechanism guessed from a sector is the generic paragraph in disguise").
So the economic engine's company arm runs on manifest companies only, and no
table here assigns XLF a model class to let the engine speak about it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

ETF, COMPANY = "etf", "company"
MACRO_PROXY, SECTOR_PROXY, COMPANY_SCOPE = (
    "MACRO_PROXY", "SECTOR_PROXY", "COMPANY")

EQUITY_BROAD, SECTOR, BOND, COMMODITY = (
    "equity_broad", "sector", "bond", "commodity")

BENCHMARK = "SPY"


@dataclass(frozen=True)
class Instrument:
    symbol: str
    universe: str
    family: str
    signal_scope: str
    label: str
    #: For econ_factor_credit: does a risk-off reading favour it?
    defensive: bool = False
    company_id: str = ""
    business_model_class: str = ""


_ETFS: Tuple[Tuple[str, str, str, str, bool], ...] = (
    ("SPY", EQUITY_BROAD, MACRO_PROXY, "S&P 500", False),
    ("QQQ", EQUITY_BROAD, MACRO_PROXY, "Nasdaq-100", False),
    ("IWM", EQUITY_BROAD, MACRO_PROXY, "Russell 2000", False),
    ("DIA", EQUITY_BROAD, MACRO_PROXY, "Dow 30", False),
    ("EFA", EQUITY_BROAD, MACRO_PROXY, "developed ex-US", False),
    ("EEM", EQUITY_BROAD, MACRO_PROXY, "emerging markets", False),
    ("XLB", SECTOR, SECTOR_PROXY, "materials", False),
    ("XLE", SECTOR, SECTOR_PROXY, "energy", False),
    ("XLF", SECTOR, SECTOR_PROXY, "financials", False),
    ("XLI", SECTOR, SECTOR_PROXY, "industrials", False),
    ("XLK", SECTOR, SECTOR_PROXY, "technology", False),
    ("XLP", SECTOR, SECTOR_PROXY, "consumer staples", False),
    ("XLU", SECTOR, SECTOR_PROXY, "utilities", False),
    ("XLV", SECTOR, SECTOR_PROXY, "health care", False),
    ("XLY", SECTOR, SECTOR_PROXY, "consumer discretionary", False),
    ("SHY", BOND, MACRO_PROXY, "1-3y Treasuries", True),
    ("IEF", BOND, MACRO_PROXY, "7-10y Treasuries", True),
    ("TLT", BOND, MACRO_PROXY, "20y+ Treasuries", True),
    ("TIP", BOND, MACRO_PROXY, "TIPS", True),
    ("LQD", BOND, MACRO_PROXY, "IG corporate credit", False),
    ("HYG", BOND, MACRO_PROXY, "HY corporate credit", False),
    ("GLD", COMMODITY, MACRO_PROXY, "gold", True),
    ("SLV", COMMODITY, MACRO_PROXY, "silver", False),
    ("USO", COMMODITY, MACRO_PROXY, "crude oil", False),
    ("DBC", COMMODITY, MACRO_PROXY, "broad commodities", False),
)


def etfs() -> List[Instrument]:
    return [Instrument(s, ETF, fam, scope, label, defensive)
            for s, fam, scope, label, defensive in _ETFS]


class PrivateCompanyRefused(ValueError):
    """A private company was asked for a security it does not have."""


def listed_security(company) -> str:
    """The company's own listed ticker, or a refusal. Never a proxy."""
    pp = str(getattr(company, "public_private", "") or "").upper()
    ticker = str(getattr(company, "ticker", "") or "").strip()
    if not pp.startswith("PUB") or not ticker:
        raise PrivateCompanyRefused(
            f"{getattr(company, 'company_id', '?')} is {pp or 'unclassified'} "
            "with no listed security. It is not mapped to a peer or an ETF: "
            "a forecast on a proxy says nothing about this company.")
    return ticker


def companies(manifest=None) -> Tuple[List[Instrument], List[dict]]:
    """(US-listed manifest companies, refusals with reasons)."""
    if manifest is None:
        from intent_engine.validation import load
        manifest = load()
    out, refused = [], []
    for c in manifest.companies:
        try:
            ticker = listed_security(c)
        except PrivateCompanyRefused as exc:
            refused.append({"company_id": c.company_id, "reason": str(exc)})
            continue
        if str(c.country).upper() != "USA":
            # Listed abroad: a different calendar, currency and benchmark.
            # Excluded rather than benchmarked against SPY in USD.
            refused.append({"company_id": c.company_id,
                            "reason": f"listed outside the US ({c.country}); "
                                      "SPY is not its benchmark"})
            continue
        out.append(Instrument(ticker.replace(".", "-"), COMPANY, COMPANY,
                              COMPANY_SCOPE, c.canonical_name,
                              company_id=c.company_id,
                              business_model_class=c.business_model_class))
    return sorted(out, key=lambda i: i.symbol), refused


def by_symbol(instruments: List[Instrument]) -> Dict[str, Instrument]:
    return {i.symbol: i for i in instruments}


def families(universe: str) -> Tuple[str, ...]:
    return (EQUITY_BROAD, SECTOR, BOND, COMMODITY) if universe == ETF \
        else (COMPANY,)
