"""Paper-trading validation of the economic engine. PAPER ONLY.

A controlled test of whether the engine's evidence and reasoning produce
better decisions than credible baselines, judged by risk-adjusted
performance, calibration and learning -- not by win rate.

What this package is NOT, stated where a reader starts:

  * no broker, no order surface, no credentials. It never imports
    `paper.broker` or `paper.execution` (a test asserts it);
  * no leverage: every book's gross exposure is at most 1;
  * no production store is written. Its records live under
    `reports/paper_validation/` and `data/paper_validation_*`, and the
    canonical market ledger is never opened for writing;
  * no scheduler. Forward registration runs when a human runs it.

Historical replay and forward paper results are different evidence and are
never pooled: the replay can have been fitted, however carefully; the
forward ledger cannot, because every record in it was hash-chained before
its outcome existed.

See docs/engineering/paper_validation/ for the system-of-record note, the
preregistration and the report.
"""
from intent_engine.paper_validation.protocol import (  # noqa: F401
    PROTOCOL, declaration_hash,
)
