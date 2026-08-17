"""§17. "Challenge the assumption" — the belief layer, on the page.

WHY THIS IS A COMPACT BLOCK AND NOT A NEW STEP
-----------------------------------------------
The demo is one story in six steps and the eight-link grid is gone (§16). A
seventh destination called "Belief challenge" would rebuild the sitemap this
product deliberately removed, and it would put the most interesting thing in
the analysis behind a click most readers never make.

So it renders INSIDE the Full analysis, in seven short movements, in the order
a chief executive argues:

    what the market currently believes
    why it may well be right
    what would break it
    the strongest competing explanation
    the possibility the current model excludes
    what we would watch next
    the decision this changes

WHAT IT REFUSES TO RENDER
-------------------------
Everything here is projected from the ONE belief object on the read. This
module composes no claim of its own: if the engine could not bind a
hypothesis to something the run holds, there is no hypothesis line, and if a
belief moved without evidence the engine never built it. A surface that
invents a challenge to fill a heading is exactly the fake contrarianism the
defect taxonomy names.
"""
from __future__ import annotations

from html import escape as _e
from typing import Optional

CSS = """
.challenge{border:1px solid var(--rule);border-radius:10px;padding:1rem 1.15rem;
  margin:1.5rem 0;background:var(--surface-2)}
.challenge h2{margin:0 0 .35rem;font-size:1.05rem}
.challenge .why{color:var(--muted);margin:0 0 .9rem;font-size:.92rem}
.challenge dl{margin:0;display:grid;grid-template-columns:minmax(9rem,14rem) 1fr;
  gap:.55rem 1.1rem}
.challenge dt{font-weight:600;color:var(--muted);font-size:.85rem;
  text-transform:uppercase;letter-spacing:.03em}
.challenge dd{margin:0}
.challenge .badge{display:inline-block;border:1px solid var(--rule);
  border-radius:999px;padding:.05rem .5rem;font-size:.75rem;color:var(--muted);
  margin-left:.4rem;vertical-align:middle}
@media (max-width:640px){.challenge dl{grid-template-columns:1fr;gap:.15rem .5rem}
  .challenge dt{margin-top:.6rem}}
"""


def _row(term: str, body: str) -> str:
    return f"<dt>{_e(term)}</dt><dd>{body}</dd>" if body else ""


def _sentence(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    return text if text[-1] in ".?!" else text + "."


def render(read, *, company: str = "") -> str:
    """The block, or an empty string when the run formed no belief.

    AN EMPTY STRING IS THE CORRECT OUTPUT for a company whose run established
    nothing to challenge. A heading over "no beliefs were formed" is the dead
    end this programme spent a cycle removing.
    """
    beliefs = tuple(getattr(read, "market_beliefs", ()) or ())
    challenges = tuple(getattr(read, "belief_challenges", ()) or ())
    if not beliefs or not challenges:
        return ""
    company = company or getattr(read, "company", "") or "this company"

    by_id = {c.belief_id: c for c in challenges}
    belief = next((b for b in beliefs if b.belief_id in by_id), None)
    if belief is None:
        return ""
    challenge = by_id[belief.belief_id]
    field = getattr(read, "explanation_field", None)
    graph = getattr(read, "assumption_chain", None)
    experiment = getattr(read, "belief_experiment", None)
    action = getattr(read, "level6_action", None)

    rows = []
    rows.append(_row(
        "The market's current belief",
        f"{_e(_sentence(belief.proposition))}"
        f'<span class="badge">{_e(belief.basis_label)}</span>'
        f'<br><span class="why">{_e(_sentence(belief.basis_detail))}</span>'))
    rows.append(_row("Why it may be right",
                     _e(_sentence(challenge.strongest_support))))
    rows.append(_row("What could break it",
                     _e(_sentence(challenge.falsifier))))

    if field is not None:
        best = field.most_dangerous or field.most_likely
        if best is not None:
            rows.append(_row(
                "The best competing explanation",
                f"{_e(_sentence(best.hypothesis))} "
                f'<span class="why">{_e(_sentence(_cap(best.mechanism)))} '
                f"{_e(_sentence(best.decision_implication))}</span>"))

    hypotheses = tuple(getattr(challenge, "unconventional_hypotheses", ()) or ())
    if hypotheses:
        first = hypotheses[0]
        rows.append(_row(
            "The possibility worth testing",
            f"{_e(_sentence(first.hypothesis))} "
            f'<span class="why">{_e(_sentence(_cap(first.why_plausible)))} '
            f"It would show up as "
            f"{_e(_strip_stop(_lower(first.expected_observations[0])))}, "
            f"and it is wrong if {_e(_lower(_sentence(first.falsifier)))}"
            f"</span>"))

    if graph is not None:
        weakest = graph.weakest_critical
        if weakest is not None:
            rows.append(_row(
                "The weakest link in our own argument",
                f"{_e(_sentence(weakest.link.to))} "
                f'<span class="badge">{_e(weakest.link.standing_label)}</span>'
                f'<br><span class="why">{_e(_sentence(weakest.reason))} '
                f"{_e(_sentence(weakest.what_would_settle_it))}</span>"))

    watch = challenge.expected_observation or (
        experiment.test if experiment is not None else "")
    rows.append(_row("What we would watch next", _e(_sentence(watch))))

    if experiment is not None:
        rows.append(_row(
            "The cheapest way to find out",
            f"{_e(_sentence(experiment.test))} "
            f'<span class="why">Stop rule: '
            f"{_e(_lower(_sentence(experiment.stopping_rule)))}</span>"))

    decision = ""
    if action is not None and getattr(action, "action_now", ""):
        decision = _sentence(action.action_now)
    elif experiment is not None:
        decision = _sentence(f"It decides {_lower(experiment.decision_unlocked)}")
    rows.append(_row("The decision this changes", _e(decision)))

    body = "".join(r for r in rows if r)
    if not body:
        return ""
    return (
        f'<section class="challenge" id="belief_challenge" '
        f'aria-label="Challenge the assumption">'
        f"<h2>Challenging the assumption</h2>"
        f'<p class="why">This is the reading {company} is most likely being '
        f"run on, and what it would take to show it is wrong. "
        f"{_e(_sentence(challenge.disposition_label))}</p>"
        f"<dl>{body}</dl></section>")


def _lower(text: str) -> str:
    text = (text or "").strip()
    return text[:1].lower() + text[1:] if text else text


def _cap(text: str) -> str:
    """Upper-case a fragment that is about to start a sentence.

    The mechanism and plausibility strings are written as clauses because
    every other consumer embeds them mid-sentence. Here they open one, and
    "Activation, not acquisition. customers are being won..." is what the
    deployed page showed when that was not handled.
    """
    text = (text or "").strip()
    return text[:1].upper() + text[1:] if text else text


def _strip_stop(text: str) -> str:
    """Drop a trailing full stop from a fragment used mid-sentence.

    "It would show up as X. and it is wrong if Y" -- the observation is
    authored as a sentence and is being embedded in a longer one.
    """
    return (text or "").strip().rstrip(".").strip()
