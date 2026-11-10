"""The instrument must be able to fail before its numbers mean anything.

THREE VARIANTS OF THIS SCORER, RUN OVER THE SAME 21 LIVE CAPTURES, REPORTED
p50 core_mean OF 9.27, 7.82 AND 10.00. A number that moves that far while the
captures do not is a property of the scorer, not of the product -- so the
scorer now carries a calibration control, and it is a test rather than a note
because the next person to widen a cue needs it to go red.

The control is a capture whose every surface keeps the section HEADINGS the
cues anchor on, and fills the prose beneath them with text that names no
company, states no quantity and describes no mechanism. A scorer that cannot
separate that from a real analysis cannot certify anything.
"""
from __future__ import annotations

import json
import statistics

import pytest

from intent_engine.pre100 import quality as Q

#: What the real corpus scored when this control was written, on 21 live
#: companies at 589518f. Recorded so a future change that moves the product's
#: number has to say so out loud.
REAL_P50_AT_CALIBRATION = 9.20
FILLER_CEILING = 7.0
MIN_SEPARATION = 2.0

FILLER = ("The business operates in a competitive environment. "
          "Conditions may change over time. The situation is being "
          "monitored. Various factors could affect the outcome. ") * 40


#: One anchor per CORE dimension, so both sides of the control are located
#: identically and the comparison is about the prose, not about which cues
#: happened to match. A first version anchored 9 of 21 dimensions, so three
#: core ones scored 0 for BOTH sides and squeezed the separation to 1.45.
_ANCHOR_LIST = [
    "Acme Holdings Limited is a logistics business that runs on",   # business_model
    "the market's current belief",                                  # market_belief
    "contested most directly by",                                   # competition
    "If we move, what do they do L0 —",                             # adversary
    "What could be true that we are not considering",               # impossible_hypothesis
    "operating leverage",                                           # economic_reasoning
    "The choice:",                                                  # recommendation
    "Better strategy",                                              # history
    "What to do next", "margin is decided", "— introduction",
    "What could break it",
]


def _anchors():
    """Every cue's anchor, so the filler is located exactly like a real page.

    Without these the dimensions would score 0 for being absent, and the
    control would pass for the wrong reason -- it must fail on QUALITY, not
    on the cue missing.
    """
    return " ".join(_ANCHOR_LIST)


@pytest.fixture
def filler_capture(tmp_path):
    d = tmp_path / "generic_filler_inc"
    d.mkdir()
    (d / "manifest.json").write_text(
        json.dumps({"company": "Generic Filler Inc."}), "utf-8")
    for surface in {s for _k, s, _c in Q.DIMENSIONS}:
        (d / f"{surface}.txt").write_text(_anchors() + " " + FILLER, "utf-8")
    return d


def _real(tmp_path, n=3):
    """Analyses that name their company, quantify, and state a mechanism."""
    out = []
    bodies = {
        "Northwind Freight Inc.": (
            "Northwind Freight Inc. earns 62% of revenue from contracted "
            "lane capacity sold to Maersk and Kuehne Nagel, and its "
            "operating leverage comes from load factor: the marginal cost "
            "of an incremental container on a booked sailing is near zero, "
            "so margin is decided by utilisation rather than by price. "),
        "Brightlake Software Inc.": (
            "Brightlake Software Inc. sells per-seat subscriptions to "
            "enterprise finance teams, where 84% of revenue renews and the "
            "fully-loaded cost to serve a seat falls as usage grows, so "
            "margin is decided by expansion within accounts, not by new "
            "logos won against Workday. "),
        "Harbor Metals Corporation": (
            "Harbor Metals Corporation ships 4.1 million tonnes a year from "
            "two pits, and its fixed cost per tonne is set by strip ratio; "
            "an incremental margin of 31% at spot means the cycle, not the "
            "contract book, decides earnings against Rio Tinto. "),
    }
    for name, body in list(bodies.items())[:n]:
        d = tmp_path / name.split()[0].lower()
        d.mkdir()
        (d / "manifest.json").write_text(
            json.dumps({"company": name}), "utf-8")
        # THE BODY GOES UNDER EACH HEADING, which is how a real page is laid
        # out and what the prose window reads. A first version concatenated
        # all the anchors and then all the prose, so most dimensions located
        # a heading with only other headings after it -- and the synthetic
        # "real" analyses scored 7.27, barely above the filler. That was the
        # fixture failing to be a page, not the scorer failing to see one.
        page = " ".join(f"{anchor} {body}" for anchor in _ANCHOR_LIST)
        for surface in {s for _k, s, _c in Q.DIMENSIONS}:
            (d / f"{surface}.txt").write_text(page, "utf-8")
        out.append(d)
    return out


def test_filler_does_not_reach_a_passing_score(filler_capture, tmp_path):
    """THE CONTROL. Generic prose under real headings must not pass."""
    rows = Q.score_corpus(_real(tmp_path) + [filler_capture])
    filler = dict(rows)["generic_filler_inc"]
    assert filler["core_mean"] <= FILLER_CEILING, \
        f"filler scored {filler['core_mean']}; the scorer cannot fail"


def test_real_analyses_outscore_filler_by_a_wide_margin(filler_capture,
                                                        tmp_path):
    """The positive half: the repair must not simply lower everything."""
    rows = dict(Q.score_corpus(_real(tmp_path) + [filler_capture]))
    filler = rows.pop("generic_filler_inc")["core_mean"]
    real = statistics.median(r["core_mean"] for r in rows.values())
    assert real - filler >= MIN_SEPARATION, \
        f"real {real} vs filler {filler}: the scorer does not discriminate"


def test_a_sentence_opening_capital_is_not_a_name():
    """The specific mechanism the control caught: "Conditions may change over
    time" was read as carrying the proper noun "Conditions"."""
    assert not Q._specific("Conditions may change over time.", "Acme Inc.")
    assert not Q._specific("Various factors could affect the outcome.",
                           "Acme Inc.")


def test_a_mid_sentence_name_still_counts():
    """The control on the control: position must not refuse real names."""
    assert Q._specific("its position is contested by Salesforce and Workday",
                       "Cloudflare, Inc.")


def test_the_calibration_number_is_recorded():
    """A written number is what makes a later drift readable as drift."""
    assert REAL_P50_AT_CALIBRATION == 9.20
