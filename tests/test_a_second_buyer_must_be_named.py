"""Serving regulated industries is not the same claim as serving two buyers.

THE THIRD PATTERN, FOUND BY MEASUREMENT RATHER THAN BY A LIVE RUN. After
`tool_to_system_of_record` was gated, four corpora of ordinary B2B copy —
generic SaaS, an enterprise vendor, a devtool and a data platform — were run
through the reasoning layer to see which readings still asserted themselves.
Exactly one did: `single_to_multi_segment`, on the enterprise-vendor corpus,
from `regulated_buyer + pricing_gated`. In plain terms, "we serve regulated
industries" plus "contact sales for pricing" was enough to tell a founder they
are "selling to a second kind of buyer that behaves nothing like the first",
and to raise "whether to run one roadmap or two".

Two defects, one reading:

1. THE SUBJECT WAS OPTIONAL. `when_it_applies` says "the company names two
   clearly different buyer groups", `segment_split` IS that signal, and the
   pattern qualified on any two of three — so the subject could be absent.

2. THE SUBJECT SIGNAL DID NOT MEAN WHAT IT SAID. Half of `segment_split`'s
   phrases named only ONE group ("public sector", "commercial customers",
   "government customers") and one named none at all ("business units", which
   is an org chart). Requiring a signal that fires on a single buyer would
   have been a gate in name only.
"""
from __future__ import annotations

import pytest

from intent_engine.strategic_intelligence.observations import (
    _NEUTRAL_SIGNAL_KEYWORDS, _detect_signals, derive_observations,
)
from intent_engine.strategic_intelligence.patterns import (
    HYPOTHESIS_SCAFFOLDS, PATTERN_LIBRARY,
)
from intent_engine.strategic_intelligence.reasoning import _hypothesis_for

PATTERNS = {p.pattern_id: p for p in PATTERN_LIBRARY}
SMS = PATTERNS["single_to_multi_segment"]
SCAFFOLD = HYPOTHESIS_SCAFFOLDS["single_to_multi_segment"]

# The exact input that produced the false positive.
ENTERPRISE_BOILERPLATE = (
    "Enterprise-grade security and compliance. SOC 2 and ISO 27001. We serve "
    "regulated industries including financial services and healthcare. "
    "Contact sales for pricing."
)


def _doc(sid, text):
    return {"source_id": sid, "source_type": "product",
            "final_url": f"https://acme.example/{sid}", "title": "Acme",
            "meta_description": "", "text_content": text,
            "retrieval_status": "OK", "freshness": "CURRENT",
            "content_hash": sid, "retrieved_at": "2026-08-06",
            "parser_version": "p1"}


def _fires(text, company="Acme"):
    obs = derive_observations([_doc("s1", text)], company=company)
    return _hypothesis_for(SMS, SCAFFOLD, obs, company)


# --- the pattern declares what it needs -------------------------------------

def test_the_subject_of_the_reading_is_required():
    assert SMS.required_signals == ("segment_split",), \
        "the second buyer must be named, not inferred from a threshold"


def test_the_pattern_says_what_would_argue_against_it():
    """It previously declared nothing at all."""
    assert SMS.disconfirming_signals


def test_the_gate_restates_the_pattern_s_own_applicability():
    """The gate is not a new rule — it is the sentence already in the record,
    enforced. If these drift apart, one of them is lying to a reader."""
    assert "two clearly different buyer" in SMS.when_it_applies
    assert "Only one buyer group" in SMS.when_it_does_not_apply


# --- the subject signal means two groups ------------------------------------

@pytest.mark.parametrize("phrase", ["business units", "public sector",
                                    "commercial customers",
                                    "government customers"])
def test_a_single_group_phrase_is_not_a_split(phrase):
    """Each of these used to qualify the signal on its own."""
    assert phrase not in _NEUTRAL_SIGNAL_KEYWORDS["segment_split"]


@pytest.mark.parametrize("text", [
    "We sell to public sector customers and government agencies.",
    "Our business units report separately each quarter.",
    "Commercial customers get a dedicated success manager.",
])
def test_naming_one_buyer_is_not_naming_two(text):
    assert "segment_split" not in _detect_signals(text)


@pytest.mark.parametrize("text", [
    "We serve government and commercial customers.",
    "Trusted across the public and private sector.",
    "Built for enterprise and small business buyers alike.",
    "Plans for individuals and teams, and a separate enterprise tier.",
])
def test_naming_two_buyers_still_detects(text):
    assert "segment_split" in _detect_signals(text)


# --- end to end through the reasoning layer ---------------------------------

def test_the_measured_false_positive_no_longer_fires():
    """The exact enterprise-vendor copy that produced this reading."""
    assert _fires(ENTERPRISE_BOILERPLATE) is None


def test_a_compliance_page_alone_is_not_a_second_buyer():
    assert _fires("We serve regulated industries and hold the "
                  "accreditations our customers require.") is None


def test_gated_pricing_alone_is_not_a_second_buyer():
    assert _fires("Contact sales for a custom quote. Request a demo.") is None


@pytest.mark.parametrize("text", [
    ENTERPRISE_BOILERPLATE + " We serve government and commercial customers, "
    "with separate procurement paths for each.",
    "Plans for individuals and teams, plus an enterprise tier. We sell to "
    "enterprise and small business buyers. Contact sales for custom pricing.",
])
def test_a_genuinely_split_buyer_base_still_qualifies(text):
    """The gate must not be a mute button."""
    assert _fires(text) is not None


def test_the_reading_still_names_the_company():
    fired = _fires(ENTERPRISE_BOILERPLATE + " We serve government and "
                   "commercial customers.", company="Northwind")
    assert fired is not None
    text = " ".join(str(v) for v in vars(fired).values())
    assert "Northwind" in text


# --- the property that made this worth fixing -------------------------------

def test_two_ordinary_enterprise_vendors_no_longer_share_the_reading():
    """The defect, reduced: two companies whose only common feature is a
    compliance page and a sales-gated price."""
    a = ("SOC 2 compliant and built for regulated industries. Talk to sales.")
    b = ("We work with regulated environments across the sector. "
         "Custom pricing is quoted per deal.")
    assert _fires(a, company="A") is None
    assert _fires(b, company="B") is None


def test_no_ungated_pattern_fires_on_ordinary_enterprise_copy():
    """The measurement that selected this pattern, kept as a test.

    Generic B2B copy must not produce a strategic reading from ANY pattern. A
    new pattern that fires here is the next instance of this defect, and this
    catches it without another twenty-company matrix run.
    """
    obs = derive_observations([_doc("s1", ENTERPRISE_BOILERPLATE)],
                              company="Acme")
    fired = [pid for pid, pattern in PATTERNS.items()
             if HYPOTHESIS_SCAFFOLDS.get(pid)
             and _hypothesis_for(pattern, HYPOTHESIS_SCAFFOLDS[pid], obs,
                                 "Acme") is not None]
    assert not fired, f"ordinary enterprise copy still asserts: {fired}"
