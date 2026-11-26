"""The economic block for a company the market engine does not follow.

WHY THIS EXISTS
---------------
Company-level economics reached a founder page ONLY through a market dossier,
the per-company snapshot the market engine publishes for its own subjects.
Measured on the prospect-100 round 7 (2026-11-26): the engine published 28
snapshots, none for any of the 100 prospects, so every private company's
X-Ray said "the economic layer did not run for this company" -- while the
published economic state was readable on the same deployment and the
company's own evidence named the exposures. Listing status decided whether a
company could receive economic intelligence. It should not.

WHAT IS AND IS NOT CLAIMED
--------------------------
A channel is live only when BOTH hold:
  * this company's own evidence establishes an exposure to the quantity
    (`economy_exposures`: macro factors bound to a retrieved observation, or
    a quantity its own filings say it depends on -- never its sector), and
  * the published economic state MEASURES that quantity (`known`).
Nothing is forecast, no ticker is implied, no company figure is invented,
and no causal edge is added. When the state is readable and no exposure
meets a measured condition, the answer is NO relevant exposure -- a finding,
reported as one -- not "did not run".
"""
from __future__ import annotations

from typing import Dict, Iterable, Optional

CONTRACT = "founder_economic_block.v1"
SOURCE = "FOUNDER_EVIDENCE_X_PUBLISHED_STATE"

#: The selector's channels (analysis_selection._CHANNEL_FAVOURS) for the
#: published state's condition kinds. A kind with no channel is measured but
#: has no decision it is known to bear on, so it never becomes a channel.
KIND_CHANNEL: Dict[str, str] = {
    "treasury_10y": "MARKET_RATE", "treasury_2y": "MARKET_RATE",
    "treasury_5y": "MARKET_RATE", "real_yield": "MARKET_RATE",
    "policy_rate": "POLICY_RATE", "sofr": "POLICY_RATE",
    "inflation": "INFLATION", "wages": "LABOR",
    "labour": "UNEMPLOYMENT", "fx_dxy": "CURRENCY",
    "commodity_oil": "COMMODITY", "commodity_gas": "COMMODITY",
    "commodity_copper": "COMMODITY",
    "industrial_production": "INDUSTRIAL_DEMAND",
}

#: An exposure is to a QUANTITY FAMILY, not to one series: a company exposed
#: to "interest rates" is reached by whichever rate the state measures.
_SAME_FAMILY = {
    "policy_rate": ("policy_rate", "treasury_2y", "treasury_5y",
                    "treasury_10y", "real_yield", "sofr"),
    "treasury_10y": ("treasury_10y", "treasury_5y", "real_yield"),
    "financial_conditions": ("treasury_10y", "real_yield"),
}


def block(economy, exposures: Iterable[str]) -> dict:
    """A market-dossier-shaped `economic_state` block, or {} when unread."""
    if economy is None or not getattr(economy, "available", False):
        return {}
    area = str(getattr(economy, "area", "") or "US")
    conditions = getattr(economy, "conditions", None) or {}
    measured = {k for k, v in conditions.items()
                if not isinstance(v, dict) or v.get("known")}
    ids, matched = [], []
    for exposure in dict.fromkeys(str(e) for e in exposures or () if e):
        for kind in _SAME_FAMILY.get(exposure, (exposure,)):
            channel = KIND_CHANNEL.get(kind)
            if kind in measured and channel:
                key = f"{area}:{channel}"
                if key not in ids:
                    ids.append(key)
                    matched.append(f"{exposure}->{kind}")
                break
    return {
        "state": "AVAILABLE", "ids": ids, "source": SOURCE,
        "contract": CONTRACT,
        "as_of": str(getattr(economy, "as_of", "") or ""),
        "matched": matched,
        "note": ("derived on the founder side: an exposure this company's "
                 "own evidence establishes, met by a condition the published "
                 "economic state measures; no market snapshot exists for it"),
    }


def prefer(market_block: Optional[dict], founder: Optional[dict]) -> dict:
    """The market engine's block when it ran; otherwise the founder's."""
    market_block = market_block or {}
    if market_block.get("state") == "AVAILABLE":
        return market_block
    return founder or market_block
