"""A filing's prose must survive the parser, because that is where economics is.

THE DEFECT THESE PIN
--------------------
`handle_data` buffered text ONLY inside `_BLOCK`, and `_BLOCK` did not contain
`div`. SEC filings lay their narrative out in `<div>` and `<font>`, not `<p>`,
so on Caterpillar's Q2 2026 exhibit the parser kept 13,462 of the document's
64,547 characters: every numeric table cell survived and every sentence of
prose did not.

Measured downstream: `demand_chain` reported ORDERS, BACKLOG, SHIPMENTS,
END_DEMAND, CUSTOMER_INTENT and COMMITTED_DEMAND at ZERO companies across the
whole corpus. Not because companies do not state them — because the sentences
stating them were discarded three layers upstream, and `fragment` was the
largest rejection reason in production at 3,200 a cycle.

Separately, `COMMITTED_DEMAND` and `COST_SHOCK` were added to the pattern
library with documented signatures and never added to `EVIDENCE_TYPES`, so
the classifier produced a type the constructor refused.
"""
from __future__ import annotations

import pytest

from intent_engine.company_ingestion.parsing import parse_html
from intent_engine.market import event_patterns as EP
from intent_engine.market import micro_evidence as ME


# --- the parser -------------------------------------------------------------

FILING_SHAPE = (
    "<html><body>"
    "<div><font>Strong order rates and a growing backlog reflect broadening "
    "momentum across all three of our primary segments.</font></div>"
    "<table><tr><td>Sales</td><td>20,500</td></tr></table>"
    "<div>Sales increased due to higher international locomotive "
    "deliveries.</div>"
    "</body></html>")


def test_prose_laid_out_in_divs_survives():
    """The shape every SEC exhibit is written in."""
    text = parse_html(FILING_SHAPE)["text"]
    assert "growing backlog" in text
    assert "Sales increased due to higher international locomotive" in text


def test_the_table_cells_still_survive_too():
    """The fix adds prose; it must not cost the numbers."""
    text = parse_html(FILING_SHAPE)["text"]
    assert "20,500" in text


def test_text_before_a_nested_block_is_not_discarded():
    """`<div>A<p>B</p></div>` used to throw A away.

    A block STARTING reset the buffer, and with div a block that is exactly
    the filing shape: a paragraph of prose followed by a nested table.
    """
    text = parse_html("<html><body><div>Backlog grew to a record."
                      "<p>Sales were $20.5 billion.</p></div>"
                      "</body></html>")["text"]
    assert "Backlog grew to a record" in text
    assert "Sales were $20.5 billion" in text


def test_navigation_is_still_removed():
    """The regression the first version of this fix caused.

    Loose anchors inside <nav> were buffered, nothing flushed at </nav>, and
    the next <p> carried them across the boundary as main content. Text
    belongs to the region it was READ in.
    """
    text = parse_html(
        "<html><body>"
        "<nav><a href=/a>What to build</a><a href=/b>How to build</a></nav>"
        "<main><p>Acme builds routing software for logistics operators.</p>"
        "</main>"
        "<footer><p>Privacy policy</p></footer>"
        "</body></html>")["text"]
    assert "What to build" not in text
    assert "Acme builds routing software" in text


def test_loose_body_text_is_captured():
    text = parse_html("<html><body>Backlog rose to $37.5 billion."
                      "</body></html>")["text"]
    assert "Backlog rose to $37.5 billion" in text


def test_script_and_style_are_still_skipped():
    text = parse_html(
        "<html><body><script>var backlog = 1;</script>"
        "<style>.backlog{color:red}</style>"
        "<div>Backlog rose.</div></body></html>")["text"]
    assert "var backlog" not in text
    assert "color:red" not in text
    assert "Backlog rose" in text


# --- the vocabulary ---------------------------------------------------------

@pytest.mark.parametrize("sentence,expected", [
    ("Contract liabilities were $7,280 million.", ME.COMMITTED_DEMAND),
    ("Remaining performance obligations were $12,300 million at quarter end.",
     ME.COMMITTED_DEMAND),
    ("Order backlog was $37.5 billion, an increase of $6.4 billion.",
     ME.INVENTORY_CHANGE),
])
def test_the_classifier_produces_these_types(sentence, expected):
    assert EP.classify_sentence(sentence) == expected


def test_every_type_the_classifier_can_produce_is_constructible():
    """A vocabulary that disagrees with itself.

    `COMMITTED_DEMAND` and `COST_SHOCK` were added to the pattern library and
    never to `EVIDENCE_TYPES`, so `evidence()` raised on a type the
    classifier had just returned. This asserts the two sets agree, which is
    the invariant rather than the two names.
    """
    producible = {family[0] for family in EP._FAMILIES}
    missing = producible - ME.EVIDENCE_TYPES
    assert not missing, (
        f"the classifier can return {sorted(missing)} and evidence() "
        f"refuses them")


def test_a_committed_demand_row_can_actually_be_built():
    item = ME.build(
        subject_company="caterpillar", actor="caterpillar",
        evidence_type=ME.COMMITTED_DEMAND, observed_at="2026-08-01",
        available_at="2026-08-01", source="https://sec.gov/x",
        fact="Contract liabilities were $7,280 million.",
        source_author="Caterpillar Inc", source_role="regulatory_filing",
        reliability=0.85, relevance=0.6,
        contradiction_role=ME.NEUTRAL)
    assert item.evidence_type == ME.COMMITTED_DEMAND


def test_an_unknown_type_is_still_refused():
    """The gate still works; it was the membership that was wrong."""
    with pytest.raises(ME.EvidenceRejected, match="unknown evidence_type"):
        ME.build(
            subject_company="caterpillar", actor="caterpillar",
            evidence_type="DEMAND_VIBES", observed_at="2026-08-01",
            available_at="2026-08-01", source="https://sec.gov/x",
            fact="Backlog feels strong.", source_author="x",
            source_role="regulatory_filing", reliability=0.85,
            relevance=0.6, contradiction_role=ME.NEUTRAL)


def test_adjacent_divs_are_separate_blocks_not_one_run_on():
    """What `div` in the block set actually buys: SEGMENTATION.

    A break proof caught this. Removing `div` from `_BLOCK` still captured
    the text — `handle_data` buffers unconditionally now, and the document
    tail gets flushed — but the whole filing came back as ONE block. That
    merges the last sentence of one paragraph into the first of the next,
    and the candidate extractor then segments across a boundary that was
    real in the document.
    """
    parsed = parse_html(
        "<html><body>"
        "<div>Backlog rose to a record $37.5 billion.</div>"
        "<div>Sales increased due to higher locomotive deliveries.</div>"
        "</body></html>")
    blocks = [b for b in parsed["text"].split("\n") if b.strip()]
    assert len(blocks) >= 2, f"expected separate blocks, got {blocks!r}"
    assert any("Backlog rose" in b for b in blocks)
    assert any("Sales increased" in b for b in blocks)
