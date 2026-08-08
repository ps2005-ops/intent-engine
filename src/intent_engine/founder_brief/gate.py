"""The release gate — the customer's complaints, expressed as failing checks.

Each rule here is one thing the customer said was wrong with the product. The
gate exists so those cannot silently return: a regression that reintroduces a
dead-end sparse page, or strips a "so what", fails a check with the customer's
own words attached rather than passing because the page still renders.

The gate runs against a RENDERED page plus the brief that produced it, because
several of the failures are only visible in the output — an internal term can
be absent from the data model and still be printed by a template.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from intent_engine.founder_brief.contract import INTERNAL_VOCABULARY

MAX_RECOMMENDATIONS = 3

# Seven questions a first-time reader must be able to answer in 60 seconds.
COMPREHENSION_QUESTIONS = (
    "What does the company do?",
    "What changed?",
    "Why does it matter?",
    "What is the biggest decision?",
    "What should be done or watched?",
    "How certain is this?",
    "What is missing?",
)


@dataclass(frozen=True)
class GateResult:
    passed: bool
    failures: tuple
    checked: int

    def as_dict(self) -> dict:
        return {"passed": self.passed, "failures": list(self.failures),
                "checked": self.checked}


def check(brief, html: str = "", *, qa=None,
          citations: Optional[dict] = None,
          executive: Optional[dict] = None) -> GateResult:
    """Every release rule, evaluated. Returns the failures, not just a bool."""
    failures: List[str] = []
    b = brief

    # 1. the first useful answer must be on this screen
    if not b.is_useful:
        failures.append(
            "the first screen does not answer the seven questions, so value "
            "requires reading the full report")

    # 2. every major insight answers "so what"
    if b.key_insight and not (b.key_insight.so_what or "").strip():
        failures.append("a major insight has no 'so what'")
    if b.key_insight and not (b.key_insight.decision or "").strip():
        failures.append("a major insight names no decision consequence")

    # 3. sparse companies must not dead-end
    if not b.key_insight and not (b.verified or b.unclear or b.public_proofs):
        failures.append(
            "a company with limited sources received only a refusal, with no "
            "verifiable findings, no diagnosis and nothing to act on")

    # 4. at most three primary recommendations
    if len(b.next_actions) > MAX_RECOMMENDATIONS:
        failures.append(
            f"{len(b.next_actions)} primary recommendations; a founder acts on "
            f"at most {MAX_RECOMMENDATIONS}")

    # 5. every rendered market module carries an interpretation
    for name, module in ((b.market_context or {}).get("modules") or {}).items():
        if not (module.get("so_what") or "").strip():
            failures.append(f"market module '{name}' is shown without an "
                            f"interpretation")

    # 6. missing values must not become zeroes
    ctx = b.market_context or {}
    if ctx.get("available") is False and "0%" in (html or ""):
        failures.append("an unavailable market value was rendered as a number")

    # 7. no internal vocabulary reaches the reader
    leaked = sorted({t for t in INTERNAL_VOCABULARY
                     if t in (html or "").lower()})
    if leaked:
        failures.append(f"internal vocabulary reached the page: {leaked}")

    # 8. no raw run identifiers on the first screen
    if html and re.search(r"\brun[_-]?id\b", html, re.I):
        failures.append("a raw run identifier is displayed")

    # 9. control results must never be presented as skill
    low = (html or "").lower()
    for banned in ("win rate", "sharpe", "alpha", "expectancy", "profit "
                                                               "factor"):
        if banned in low:
            failures.append(f"engine trading performance ('{banned}') is "
                            f"presented as founder intelligence")

    # 10. no recommendation to trade
    for banned in ("buy the stock", "sell the stock", "we recommend buying",
                   "price target", "undervalued", "overvalued"):
        if banned in low:
            failures.append(f"investment recommendation language: '{banned}'")

    # 11. one main, one h1
    if html:
        if html.count("<main") != 1:
            failures.append(f"{html.count('<main')} <main> landmarks; "
                            f"exactly one is required")
        if html.count("<h1") != 1:
            failures.append(f"{html.count('<h1')} <h1> elements; exactly one "
                            f"is required")

    # 12. action copy must not imply unapproved external execution
    for banned in ("we will email", "sending an email to", "we have contacted",
                   "published on your behalf", "we notified"):
        if banned in low:
            failures.append(f"action copy implies unapproved execution: "
                            f"'{banned}'")

    # --- v3 release gates ---------------------------------------------------
    # 13. a withheld reading may not reappear anywhere
    if getattr(b, "withheld_reason", "") and b.key_insight is not None:
        failures.append("a withheld strategic reading reached a "
                        "founder-facing layer")

    # 14. Q&A must not contradict the brief, and the executive brief must
    #     carry the depth its budget promises. The executive brief was built
    #     by every caller and passed to NOBODY, so its budget was computed on
    #     every request and never read -- a depth failure could not reach this
    #     gate at all.
    if qa is not None or executive is not None:
        from intent_engine.founder_brief import consistency as CO
        result = CO.check(brief=b, qa=qa, executive=executive)
        failures.extend(result.failures)

    # 15. every displayed citation must resolve
    for href, status in (citations or {}).items():
        if status != 200:
            failures.append(f"a displayed citation returned {status}: {href}")

    # 16. interface controls may not precede the intelligence
    if html:
        ctl = html.find("ui-controls")
        answer = html.find("Why this matters")
        if 0 <= ctl < answer:
            failures.append("follow-up controls appear before the founder "
                            "answer")
    return GateResult(not failures, tuple(failures), 17)


def comprehension(brief) -> dict:
    """Can a first-time reader answer all seven questions from this brief?

    Answerability is judged from the DATA, not from the prose, so a page that
    looks complete but carries an empty decision still fails.
    """
    b = brief
    answers = {
        COMPREHENSION_QUESTIONS[0]: bool(b.what_it_does),
        COMPREHENSION_QUESTIONS[1]: bool(b.what_changed or b.verified
                                         or b.customer_can_see),
        COMPREHENSION_QUESTIONS[2]: bool(
            (b.key_insight and b.key_insight.so_what) or b.unclear),
        COMPREHENSION_QUESTIONS[3]: bool(
            (b.key_insight and b.key_insight.decision)
            or b.internal_questions),
        COMPREHENSION_QUESTIONS[4]: bool(b.next_actions),
        COMPREHENSION_QUESTIONS[5]: bool(b.confidence and b.confidence_reason),
        COMPREHENSION_QUESTIONS[6]: bool(b.limitations or b.unclear
                                         or b.biggest_unknown),
    }
    unanswered = [q for q, ok in answers.items() if not ok]
    return {"answers": answers, "unanswered": unanswered,
            "passed": not unanswered,
            "answered": sum(1 for ok in answers.values() if ok),
            "of": len(answers)}
