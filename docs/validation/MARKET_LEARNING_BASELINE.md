# Market learning baseline — paper only, and what that bounds

*Canonical. See `docs/econ/FINAL_REPORT.md` for the engine's own record.*

---

## The wall

All market action is **PAPER or SHADOW**. There is no real-money execution,
no live broker activation, and no autonomous capital deployment. Nothing in
this repository may be read as a claim about realised returns.

## What paper learning is for

A signal that is rejected, and a period with no signal at all, are both
learning events. The zero-trade record captures the signal, the rejection,
the reason, the missing information and the rule by which it would later
resolve — so a quiet period is legible as a decision rather than as an
absence of activity.

## What is NOT claimed

- proven ROI
- proven revenue lift
- proven forecasting superiority
- proven market alpha
- calibrated forward accuracy

Each of those requires evidence that has not happened yet. The forward ledger
is preregistered and unresolved; see `FORWARD_EVIDENCE.md`.

## The company → economy bridge

Public corporate observations only. `econ_evidence.translate` refuses
anything tenant-private and anything with no stated direction, and reports
what it declined — a translator that returned only its output would make a
large loss invisible.

Aggregates carry lineage and `depends_on`, and the double-counting wall is
explicit: evidence that became an aggregate may not return as independent
corroboration of itself.
