# T006 — Wire the premortem→ledger bridge into the live pipeline — SPEC FOR APPROVAL

*Status: PROPOSED (2026-07-19/20). Enters the runnable queue only on your
written approval. Same protocol discipline as the T005 spec: deterministic
bars, hard budget, explicit park conditions, one commit, suite green.*

## Verification first: the bridge SUBSTRATE is already DONE

Task 5 in `overnight-execution-plan.md` built
`core/premortem_prediction_bridge.py` —
`derive_predictions_from_premortem()`: one isolated drafting call over a
real `RiskAudit.failure_modes`, schema with ONLY
claim_text/probability/resolve_by (no record/include field the model can
set), code-side `record_prediction(source="premortem")`, future-date
backstop. 7 tests green (`test_premortem_prediction_bridge.py`). Its own
scope wall said "renders nothing new to the user — pure substrate," and
it is NOT invoked by the pipeline or CLI today. **So the substrate needs
no rebuild; the remaining, unbuilt step is the WIRING** — making a real
premortem run actually derive and record predictions. That is exactly
parallel to what T005 did for the mechanism section, so this spec mirrors
T005's shape.

## Goal

An **opt-in** path by which a real premortem run invokes the existing
bridge (one extra isolated call) and records source="premortem"
predictions to the ledger — additive, off by default, combined-call
analyzer prompt UNTOUCHED (A3 / LuckTest isolation, identical to T005).

## Files in scope

- `src/intent_engine/simulator/pipeline.py`: `run_premortem` gains an
  optional `bridge_client` kwarg (mirroring T005's `mechanism_client`);
  when provided, calls `derive_predictions_from_premortem` on the produced
  `RiskAudit` and returns the recorded predictions in a new additive
  `PremortemResult.ledgered_predictions` field (default None).
- `src/intent_engine/simulator/cli.py`: a `--record-predictions` flag
  (off by default, zero new calls otherwise); on use, prints a plain
  "recorded N predictions to the ledger (source=premortem)" line — no
  probabilities-as-forecasts framing, no accuracy language.
- `tests/test_premortem_ledger_wiring.py` (new).
- Explicitly NOT in scope: the bridge module itself (done), the
  combined-call prompt, the drafting prompt (frozen like T005's
  extraction prompt — editing it is a park), any auto-resolution or
  scoring display (the bridge's own scope wall stands).

## Deterministic bars (all must pass)

- (a) **Real run, recorded rows**: one live premortem on a fixture
  decision with `--record-predictions` records 1–3 predictions;
  verified by direct DB read — all source="premortem", 0<p<1, resolve_by
  strictly future, valid rows. (This is the plan's own Task-5 bar (b),
  now exercised through the live wiring rather than the module directly.)
- (b) **Schema wall (mocked, structural)**: assert the drafting tool
  schema exposes no record/include/id field — the model cannot self-record
  (Stage-2-citation style; reuses the bridge's existing assertion).
- (c) **Additive default**: `run_premortem` without `bridge_client` records
  NOTHING and returns `ledgered_predictions=None`; every existing caller
  and unpack site unaffected (mocked test).
- (d) **Append-only + no-backfill**: a mocked run asserts it only ever
  calls `record_prediction` (never mutates/deletes), and does not touch
  any prediction not created in that run.
- (e) **No accuracy/forecast language** in the CLI output line (grep bar:
  0 hits for "will", "forecast", "accurate", "P=" in the printed
  confirmation).
- (f) **Suite green, zero regressions.**

## Budget ceiling

**≤6 live calls** (matching the plan's own Task-5 budget: 1 drafting call
per run, remainder transient-retry headroom only — never prompt
iteration). Live runs on the Mac (no sandbox egress). Spend logged in the
trace.

## Park conditions

1. Bar (a) or (b) fails twice within budget → PARK with real outputs in
   the trace. The drafting prompt is frozen substrate; tuning it is out of
   scope.
2. Wiring would require touching the combined premortem prompt → PARK
   (A3).
3. Any pressure to add auto-resolution, scoring display, or backfill →
   PARK (the bridge's standing scope wall).
4. Budget exhausted → PARK.

## Relationship to standing walls

Recording predictions is NOT a prediction of accuracy — these rows join
the same append-only ledger, graded later by code, under the same A-M5
≥30-resolved wall before any calibration claim. No marketing artifact may
cite "the premortem now records predictions" as evidence of skill.
