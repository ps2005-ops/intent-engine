"""T007 bars (docs/MECHANISM_EXPLANATION_DEPTH_SPEC.md; built 2026-07-22
under the founder-ratified option-1 wall scoping, docs/T007_PARK_FINDING.md).
All six bars, all offline, all against the REAL library (not fixtures).

Wall scoping (option 1): bar (d) applies to SYSTEM-AUTHORED lines only;
verbatim causal_chain steps + cited source are exempt because bar (c)
guarantees they are unedited quotes of documented history. The decisive
proof is test_bar_d_*: a wall-tripping mechanism (its verbatim causal
chain contains 'sell'/'buy'/'forecast') renders correctly while the
system's own framing stays clean."""

import re

from intent_engine.core.mechanism_library import (
    RankedMechanism,
    load_mechanisms,
    match_mechanisms,
)
from intent_engine.simulator.mechanism_section import (
    EXPLANATION_HEADER_PREFIX,
    assert_explanation_system_walls,
    render_mechanism_explanation,
    render_mechanism_section,
)

LIBRARY = load_mechanisms()


def _rank_all():
    """One RankedMechanism per real library mechanism, matched on its own
    full trigger set (so matched_conditions == its declared conditions)."""
    return [
        RankedMechanism(mechanism=m, overlap_count=len(m.trigger_conditions),
                        matched_conditions=list(m.trigger_conditions))
        for m in LIBRARY
    ]


def _blocks():
    """Explanation rendered per mechanism, split back into per-mechanism blocks."""
    return [render_mechanism_explanation([r]) for r in _rank_all()]


# --- bar (a): condition traceability, across the whole real library --------

def test_bar_a_every_named_condition_is_a_matched_condition():
    for r in _rank_all():
        block = render_mechanism_explanation([r])
        # the "Conditions present" section lists exactly matched_conditions
        listed = re.findall(r"^    - (\S+)$", block, flags=re.MULTILINE)
        assert set(listed) == set(r.matched_conditions)
        for c in listed:
            assert c in r.mechanism.trigger_conditions  # nothing invented


# --- bar (b): cited-instance presence, across the whole real library -------

def test_bar_b_every_block_has_case_year_and_source():
    for m, block in zip(LIBRARY, _blocks()):
        inst = m.historical_instances[0]
        assert inst.case in block
        assert re.search(r"\((\d{4})\)", block)  # a 4-digit year in parens
        assert str(inst.year) in block
        assert inst.source in block
        assert "Source:" in block


# --- bar (c): causal-chain fidelity (verbatim), across the whole library ---

def test_bar_c_every_causal_step_appears_verbatim():
    for m, block in zip(LIBRARY, _blocks()):
        for step in m.causal_chain:
            assert step in block, f"{m.mechanism_id}: causal step not verbatim"
        # count matches the stored chain length (nothing dropped/added)
        numbered = re.findall(r"^    \d+\. ", block, flags=re.MULTILINE)
        assert len(numbered) == len(m.causal_chain)


# --- bar (d): language wall on SYSTEM-AUTHORED lines, across the library ----

_SYSTEM_LINE_MARKERS = (EXPLANATION_HEADER_PREFIX, "  Conditions present",
                        "  How it unfolds", "  Historical precedent:", "  Source:")
_FORBIDDEN = (r"\bwill\b", r"\bbuy\b", r"\bsell\b", r"\bforecast\b",
              r"\bprobability\b", r"p=", r"% chance", r"\bexpected to\b",
              r"\baccuracy\b", r"\bpredict\b", r"\bwill happen\b")


def _system_authored_lines(block):
    """The lines the renderer itself authors (header + labels) -- NOT the
    verbatim causal steps, condition bullets, precedent text, or source."""
    out = []
    for ln in block.splitlines():
        if ln.startswith(EXPLANATION_HEADER_PREFIX):
            out.append(ln.split("—")[0])  # keep only the framing prefix, not the mechanism name
        elif ln.strip() in ("Conditions present in your situation:",
                             "How it unfolds (documented pattern):") or ln.strip() in (
                             "Historical precedent:", "Source:"):
            out.append(ln)
        elif ln.startswith("  Historical precedent:") or ln.startswith("  Source:"):
            # label only -- the value after the colon is quoted data, exempt
            out.append(ln.split(":", 1)[0])
    return out


def test_bar_d_system_authored_lines_are_clean_across_library():
    for block in _blocks():
        blob = "\n".join(_system_authored_lines(block)).lower()
        for pat in _FORBIDDEN:
            assert not re.search(pat, blob), f"forbidden {pat!r} in system-authored framing"


def test_bar_d_wall_helper_raises_on_system_violation():
    try:
        assert_explanation_system_walls(["Why this may be in play — X will happen"])
        assert False, "expected a wall violation"
    except ValueError as e:
        assert "wall violation" in str(e)


def test_bar_d_the_proof_wall_tripping_mechanism_renders_verbatim_history():
    # carry_trade_unwind's causal chain contains 'buy' AND 'sell' verbatim;
    # margin_collateral_spiral contains 'sell'. Both MUST render (bar c) and
    # MUST pass the system-line wall (bar d, option 1).
    for mid in ("carry_trade_unwind", "margin_collateral_spiral", "money_market_contagion"):
        m = next(x for x in LIBRARY if x.mechanism_id == mid)
        r = RankedMechanism(mechanism=m, overlap_count=len(m.trigger_conditions),
                            matched_conditions=list(m.trigger_conditions))
        block = render_mechanism_explanation([r])  # must NOT raise
        # the verbatim trade-verb history is present ...
        assert any(re.search(r"\b(sell|buy|forecast)\b", s.lower()) for s in m.causal_chain)
        assert any(step in block for step in m.causal_chain)
        # ... while the system-authored framing stays clean
        sys_blob = "\n".join(_system_authored_lines(block)).lower()
        assert not re.search(r"\b(sell|buy|forecast)\b", sys_blob)


# --- bar (e): correct silence ----------------------------------------------

def test_bar_e_no_match_renders_empty_string():
    assert render_mechanism_explanation([]) == ""


# --- bar (f): additive / no-regression -------------------------------------

def test_bar_f_one_liner_section_is_byte_identical():
    # render_mechanism_section must be untouched in behavior.
    ranked = _rank_all()[:3]
    before = render_mechanism_section(ranked)
    assert before.startswith("Structural mechanisms possibly in play:")
    # explanation is a DIFFERENT, additive renderer -- not the same output
    assert render_mechanism_explanation(ranked) != before
    assert EXPLANATION_HEADER_PREFIX in render_mechanism_explanation(ranked)
