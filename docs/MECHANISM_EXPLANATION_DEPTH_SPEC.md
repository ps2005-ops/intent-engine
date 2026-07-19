# T007 — Mechanism explanation depth — SPEC FOR APPROVAL

*Status: PROPOSED (2026-07-21/22). SPEC ONLY — enters the runnable queue
only on your written approval; no build tonight. Same protocol discipline
as the T005 spec: deterministic bars, budget, park conditions, one commit,
suite green (explicit exit-code check).*

## The honest edge this captures

When a mechanism matches, incumbents' "Analyst" agents give you a
confident narrative. This feature gives you the *why*, fully traceable:
the exact trigger conditions that fired, the documented historical
instance and its source, and the causal chain in business English —
**as an EXPLANATION of a deterministic match, never a prediction.** No
probability, no forecast, no accuracy claim. It is entirely inside the
existing walls because it renders data that already exists.

## Key design fact: this is DETERMINISTIC RENDERING, not a new model call

Every input already exists on the matched `Mechanism`:
- `matched_conditions` (from the deterministic matcher) — what fired;
- `causal_chain` — an ordered list of human-readable business-English
  steps, already stored per mechanism;
- `historical_instances[].case / .year / .source` — the cited precedent.

So v1 is a **pure, deterministic transform** of a `RankedMechanism` into a
prose explanation block. **Zero LLM calls. Zero live budget.** Fully
buildable and testable in-sandbox (unlike T005, whose bars needed the
Mac). Any future LLM prose-smoothing is an explicit NON-GOAL for v1 and
would be its own separately-gated proposal — sneaking a model call in
here is a park condition, not a stretch goal.

## Goal

A new renderer `render_mechanism_explanation(ranked) -> str` (in
`simulator/mechanism_section.py`, alongside the existing one-line
`render_mechanism_section`) that produces, per matched mechanism:

    Why this may be in play — <Mechanism name> (<confidence_tier>)
      Conditions present in your situation: <matched_conditions, each on its own line>
      How it unfolds (documented pattern):
        1. <causal_chain step 1>
        2. <causal_chain step 2>
        ...
      Historical precedent: <case> (<year>)
      Source: <source URL/citation>

An opt-in `--explain` CLI flag (off by default) selects this fuller block
in place of the one-liner. Additive; the existing one-line section and all
current callers are untouched.

## Deterministic bars (all must pass; all offline)

- (a) **Condition traceability**: for every mechanism rendered, every
  condition named in the explanation is a member of that mechanism's
  `matched_conditions` — asserted against all 20 (soon 22) real library
  mechanisms, not a fixture. No condition appears that didn't fire.
- (b) **Cited-instance presence**: every explanation block contains a real
  `case`, a 4-digit `year`, and the instance `source` string — asserted
  across the whole real library.
- (c) **Causal-chain fidelity**: every step of the matched mechanism's
  stored `causal_chain` appears verbatim in its explanation (no
  paraphrase, no invention, no dropped step) — the guarantee that this is
  rendering, not generation.
- (d) **Language walls (grep, 0 hits)**: the rendered explanation passes
  the existing `assert_section_language_walls` PLUS explicit 0-hit greps
  for `probability`, `P=`, `% chance`, `forecast`, `will happen`,
  `expected to`, `accuracy`, `predict` — checked against every library
  mechanism's rendered block.
- (e) **Correct silence**: no match → empty string; the CLI renders no
  explanation section at all (no "nothing to explain" placeholder).
- (f) **Additive / no-regression**: `render_mechanism_section` output is
  byte-identical before/after; existing tests unchanged; suite green.

## Budget ceiling

**0 live calls** (pure deterministic rendering). If a future version wants
LLM prose, that is a separate proposal with its own budget and its own
gate — not this one.

## Park conditions

1. If, during build, the stored `causal_chain` steps read too terse to be
   founder-readable and the temptation arises to LLM-smooth them → PARK
   the smoothing as a separate gated proposal; ship the deterministic v1
   as-is (the steps are already business English, per the data).
2. Any bar (a)–(f) can't be made deterministic → PARK and say so.
3. Any pressure to attach a probability/confidence number to an
   explanation → PARK (this is the whole point: explanation ≠ prediction).

## Relationship to standing walls

Renders only already-cited, already-deterministic data. Produces zero
predictive-accuracy claims — bar (d) enforces that in code. Marketing may
describe this as "traceable explanation of a deterministic structural
match with cited historical precedent" and nothing stronger.
