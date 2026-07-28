"""Product evaluation — simulate customer review, deterministically.

WHY THIS EXISTS
---------------
The offline suite answers "did the code do what it was told". It cannot answer
"would a busy person find this useful", which is the only question that decides
whether the product is worth anything. Waiting for fifty real reviewers to find
out is too slow and too expensive to iterate against.

So this package encodes what reviewers actually complain about, as executable
checks. The complaints are not invented: they come from observed feedback —
the report was too long, the same evidence appeared under several hypotheses,
the strongest insight was buried, a follow-up question returned an internal
token, the product did not explain itself.

Three deliberate constraints:

  * DETERMINISTIC. No model calls in the gate. A judge that varies run to run
    cannot tell a regression from noise, and a threshold you can re-roll is not
    a threshold. Model-assisted critique is available behind an interface for
    diagnosis, never for the pass/fail decision.

  * PERSONA-WEIGHTED, not averaged. A change that delights investors and ruins
    small-business owners must not read as neutral progress. Every case names
    its persona, and regressions are reported per persona.

  * VERSIONED. Thresholds live in one place with a version string. Changing a
    threshold to make a failing build pass is a decision someone should have to
    make on purpose, in a diff, with a reason.
"""
from intent_engine.product_eval.scorecard import (           # noqa: F401
    DIMENSIONS, PRODUCT_OUTCOMES, ProductScore, score_report,
)
from intent_engine.product_eval.personas import (            # noqa: F401
    PERSONAS, SCENARIOS, Persona,
)
from intent_engine.product_eval.harness import (             # noqa: F401
    EVAL_SET_VERSION, build_cases, run_cases,
)
