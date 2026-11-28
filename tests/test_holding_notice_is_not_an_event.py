"""A fund trading the shares is not the company acting.

Measured on the live learning ledger, 2026-11-26: 11 of 206 expectations
rested entirely on institutional-holding notices or executive unit grants,
including 7 of the 17 `margin_protection` beliefs. Every sentence below is
from that corpus.
"""
import pytest

from intent_engine.market import event_patterns as E
from intent_engine.market import micro_evidence as ME

NOT_EVENTS = [
    "Royal Fund Management LLC Cuts Position in Honda Motor Co., Ltd. $HMC - MarketBeat.",
    "Sumitomo Mitsui Trust Group Inc. Reduces Stock Position in JPMorgan Chase & Co. $JPM - MarketBeat.",
    "California State Teachers Retirement System Grows Stock Position in Duolingo, Inc. $DUOL - marketbeat.com.",
    "Exchange Traded Concepts LLC Trims Position in NextEra Energy, Inc. $NEE - MarketBeat.",
    "Plato Investment Management Ltd Purchases New Stake in Cloudflare, Inc. $NET - MarketBeat.",
    "California State Teachers Retirement System Raises Stake in Duolingo, Inc. $DUOL - MarketBeat.",
    "Caterpillar (CAT) CEO holds 11,234 share-linked units, settled in cash upon retirement or separation. - Stock Titan.",
    "Caterpillar (CAT) CFO acquires 13 and 8 stock-linked units, payable in cash at retirement or separation. - Stock Titan.",
]

# Positive controls: the refusal must not cost a real event of the same type.
STILL_EVENTS = [
    ("The Restructuring Plan will reduce the size of our workforce by approximately 220 employees, or approximately 12%.", ME.LAYOFF),
    ("ETSY Cuts 12% Of Workforce After Q2 Beat", ME.LAYOFF),
    ("Intel to cut 15% of its global workforce as turnaround stalls", ME.LAYOFF),
    ("Microsoft acquires a 49% stake in the joint venture from Sony", ME.MA_ACTIVITY),
    ("Caterpillar names Joe Creed chief executive officer, succeeding Jim Umpleby", ME.EXECUTIVE_CHANGE),
    # a competitive position is not a stock holding
    ("Acme cuts 500 jobs to defend its market share position in Europe", ME.LAYOFF),
]


@pytest.mark.parametrize("sentence", NOT_EVENTS)
def test_a_holding_notice_classifies_as_nothing(sentence):
    assert E.classify_sentence(sentence) is None


@pytest.mark.parametrize("sentence,etype", STILL_EVENTS)
def test_the_company_s_own_action_still_classifies(sentence, etype):
    assert E.classify_sentence(sentence) == etype
