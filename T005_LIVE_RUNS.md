# T005 live bars (a) and (b) — Mac one-liners + pass criteria

*Staged 2026-07-18 (overnight loop). The sandbox has no Anthropic egress,
so these two runs are yours. Implementation + mocked bars (c)(d)(e) are
committed and green; T005 stays "live-bars-pending-human" until BOTH runs
below pass and their outputs are recorded in reports/overnight_trace.md.
Total live budget: 2 calls of the <=8 ceiling (headroom is for transient
retry only, never prompt iteration).*

## Live bar (a) — genuinely matched mechanism renders with provenance

    cd ~/intent-engine && .venv/bin/python -m intent_engine.simulator.cli --entity-id "t005-live-a" --mechanisms --decision "We rely on a single overseas contract manufacturer for the specialized sensor chip in our product -- there is no qualified alternate supplier we could switch to within the next 6 months. A fire at their only fabrication plant last month has cut their output by 60%, and we have no inventory buffer left. Our only two real competitors sell functionally identical products."

PASS criteria (all must hold, read directly off the output):
1. Output contains the line header `Structural mechanisms possibly in play:`.
2. At least one mechanism line renders, and it names its matched
   conditions (expect `concentrated_supplier_base` given this text) and a
   historical instance with a year.
3. No occurrence of `will happen`, `buy`, `sell`, `position size`, `P=`,
   `probability`, `% chance` inside the mechanisms section (the section
   walls also enforce this at render time — a crash here is a FAIL to
   record, not to patch).

## Live bar (b) — neutral decision renders NO section (correct silence)

    cd ~/intent-engine && .venv/bin/python -m intent_engine.simulator.cli --entity-id "t005-live-b" --mechanisms --decision "We're considering refreshing our company's internal wiki and moving our documentation to a new tool over the next quarter. The team is comfortable with the current one but the new tool has better search."

PASS criteria:
1. The premortem itself renders normally.
2. The string `Structural mechanisms possibly in play` does NOT appear
   anywhere in the output — no section, no "none matched" placeholder.

## If either fails

Record the full real output in reports/overnight_trace.md and PARK per
the spec's park condition 1 (second attempt allowed for transient API
errors only). The extraction prompt is gate-verified surface — do not
tune it; a prompt change re-opens the Task 3 gate (full 5x3 protocol).

## On success

Tell the agent (or edit yourself): ROADMAP.md T005 status →
DONE with both outputs pasted into reports/overnight_trace.md, and the
premortem's user-facing docs may then mention the section.
