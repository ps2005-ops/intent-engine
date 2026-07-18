# T005 — Wire mechanisms into premortem output (overnight Task 4) — SPEC FOR APPROVAL

*Status: PROPOSED (2026-07-18). Enters ROADMAP's runnable queue only on
your written approval, unchanged or as amended by you. Task 3 was
unparked on the v2 gate's evidence 2026-07-18; this is the build it
gated. Protocol discipline copied from Task 3/T003/T004: deterministic
bars, hard budget, explicit park conditions, one commit, suite green.*

## Goal

A separate, **additive** section in the premortem rendering:

    Structural mechanisms possibly in play:
    - <name> (<confidence_tier>) -- matched on: <conditions>. Historical instance: <case> (<year>).

Pipeline: one isolated extraction call (the exact prompt/schema design the
v2 reliability gate just re-verified, honest-ambiguity behavior included)
on the premortem's `decision_text` → the existing deterministic matcher
(`mechanism_library.match_mechanisms`) → rendered list. The
`PremortemAnalyzer` combined-call prompt is **UNTOUCHED** (hard wall A3 —
LuckTest isolation pattern: a separate analyzer, never a prompt merge).

## Files in scope

- `src/intent_engine/simulator/mechanism_section.py` (new): the isolated
  extraction call (decision-text flavor of the gate-verified design — the
  closed TriggerCondition enum schema, no free-text mechanism naming) +
  `render_mechanism_section(ranked) -> str`.
- `src/intent_engine/simulator/pipeline.py`: `PremortemResult` gains an
  additive optional field (`ranked_mechanisms`); `run_premortem` calls the
  new module when a client is available. No existing field changes.
- `src/intent_engine/simulator/cli.py`: append the rendered section to
  output when non-empty.
- `tests/test_mechanism_section.py` (new).
- Explicitly NOT in scope: `core/analysis.py` (combined prompt),
  `core/data/mechanisms.json` (library data), any ledger wiring (that is
  Task 5), any probability/prediction wording.

## Deterministic bars (all must pass)

- (a) **Real matched run**: one live end-to-end premortem on the
  supply-shock-flavored fixture decision
  (`tests/fixtures/business_decisions.json`) renders the section with >=1
  genuinely matched mechanism; every rendered line carries its
  matched-condition provenance AND a historical instance with year —
  asserted by string checks on the real output, recorded in the trace.
- (b) **Real silence run**: one live run on a neutral fixture decision
  renders NO section at all (assert absence of the header string). No
  forced match; correct silence is the pass.
- (c) **Schema wall (mocked, structural)**: the extraction tool schema's
  enum == the closed `TriggerCondition` set exactly; the schema contains
  no free-text field through which the model could name a mechanism;
  assert the drafting/record pattern has no include/record field.
- (d) **Language wall (grep bars)**: the rendered section passes
  `assert_language_walls` and additionally greps 0 hits for `P=`,
  `probability`, `% chance`, `will ` in the section text — "possibly in
  play" phrasing only.
- (e) **Suite green, zero regressions**; mocked tests cover rendering
  from injected extraction results, empty-match silence, provenance
  formatting, and the additive-field default (old callers of
  `PremortemResult` unaffected).

## Budget ceiling

**<=8 live calls total** (2 required runs = 2 extraction calls; the
remainder is retry headroom for transient failures ONLY — never for
prompt iteration). Live runs happen on the Mac (sandbox has no Anthropic
egress). Spend logged in the trace entry per house convention.

## Park conditions (explicit)

1. Bar (a) or (b) fails twice within budget → **PARK** with the real
   outputs in the trace. The extraction prompt is gate-verified property
   of Task 3 — tuning it here is out of scope; any prompt change
   re-opens the Task 3 gate (full 5x3 protocol) first.
2. Implementation turns out to require touching the combined premortem
   prompt in any way → **PARK immediately** (hard wall A3).
3. Budget exhausted → PARK, no exceptions.
4. Any bar can't be made deterministic in practice → PARK and say so,
   rather than shipping a judgment-call bar.

## Marketing wall (inherited from the business-phase constraints)

This task produces capability ("gate-passed mechanism extraction rendered
with provenance and honest silence") — it produces **zero evidence of
predictive accuracy** and no downstream artifact may cite it as such.
