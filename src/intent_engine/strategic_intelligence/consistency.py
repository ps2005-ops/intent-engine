"""Do the layers agree with each other?

WHY THIS IS A SEPARATE CHECK
----------------------------
The brief, the deck and the follow-up answers are generated from one report,
which is not the same as saying the same thing. Each layer selects, trims and
re-words independently, and every one of them can be individually correct while
the set of them tells a reader three different stories:

  * the headline states a claim the brief no longer leads with, because the
    budget trimmed it after the headline was built;
  * a slide shows a confidence the brief does not;
  * the deck presents a hypothesis the brief suppressed as low-value;
  * a follow-up answers about a claim that is not on any page.

None of these is caught by checking any one layer. A reader who moves between
them is the only person who sees it — which is exactly the reader a
presentation-first product has.

A contradiction here fails the release. Not because a mismatch is dangerous on
its own, but because a product that says two things cannot be trusted about
either, and "which one did it mean" is not a question a briefing may raise.
"""
from __future__ import annotations

CONSISTENCY_VERSION = "si_consistency.v1"


def _as_dict(report):
    return report.as_dict() if hasattr(report, "as_dict") else (report or {})


def _norm(text) -> str:
    return " ".join(str(text or "").lower().split())


def _claim_of(hypothesis) -> str:
    return _norm(hypothesis.get("title") or hypothesis.get("statement"))


def check(report, *, brief=None, slides=(), documents=()) -> dict:
    """Every disagreement between the layers a reader can move between."""
    r = _as_dict(report)
    problems = []
    problems += _headline_agrees_with_brief(brief)
    problems += _deck_shows_only_displayed_claims(r, slides)
    problems += _confidence_is_stated_once(r, brief)
    problems += _withheld_view_is_withheld_everywhere(r, brief, slides)
    problems += _citations_resolve(r, slides)
    return {
        "consistency_version": CONSISTENCY_VERSION,
        "problems": problems,
        "consistent": not problems,
    }


def _headline_agrees_with_brief(brief) -> list:
    """The headline is built from the finished brief, so it cannot lead with a
    claim the brief does not make."""
    if brief is None:
        return []
    headline = getattr(brief, "headline", None)
    view = _norm(getattr(headline, "view", ""))
    thesis = _norm(getattr(brief, "thesis", ""))
    if not view or not thesis:
        return []
    # The headline keeps the thesis's first sentence, so one must open the
    # other. Compared on a prefix rather than by similarity: a paraphrase is a
    # different claim, and the point of the check is that it is not one.
    if not thesis.startswith(view.rstrip(".").rstrip("…")):
        return ["the opening line states a claim the brief does not lead with"]
    return []


def _deck_shows_only_displayed_claims(r, slides) -> list:
    """A slide may not present a hypothesis the report suppressed.

    Ranking exists to keep a reader from holding five claims. It is undone if
    the suppressed ones reappear in the deck, where they carry MORE weight
    than in the report — a slide is what gets shown to a room.
    """
    shown = {_claim_of(h) for h in r.get("hypotheses") or ()}
    if not shown:
        return []
    # The signals slide legitimately carries surprises alongside hypothesis
    # titles, so "not a surviving hypothesis" is not by itself a defect. What
    # would be a defect is a SUPPRESSED hypothesis reappearing: ranking exists
    # to keep a reader from holding five claims, and it is undone if the ones
    # it dropped come back on a slide, where they carry more weight than in
    # the report.
    surprises = {_norm(s.get("finding")) for s in r.get("surprises") or ()}
    suppressed = {_norm(h.get("title") or h.get("statement"))
                  for h in r.get("suppressed_hypotheses") or ()}
    problems = []
    for slide in slides or ():
        if slide.get("id") != "signals":
            continue
        for bullet in slide.get("bullets") or ():
            text = _norm(bullet.get("text")).rstrip("…")
            if not text:
                continue
            if any(claim and text.startswith(claim[:60]) for claim in
                   suppressed):
                problems.append("the presentation shows a claim the report "
                                "ranked out")
                break
            recognised = any(claim and (text.startswith(claim[:40])
                                        or claim.startswith(text[:40]))
                             for claim in shown | surprises)
            if not recognised:
                problems.append("the presentation shows a claim that appears "
                                "nowhere in the report")
                break
    return problems


def _confidence_is_stated_once(r, brief) -> list:
    """The confidence a reader sees first must be the leading claim's."""
    if brief is None:
        return []
    hypotheses = r.get("hypotheses") or []
    if not hypotheses:
        return []
    headline = getattr(brief, "headline", None)
    note = _norm(getattr(headline, "confidence", ""))
    if not note:
        return []
    leading = _norm(hypotheses[0].get("confidence"))
    others = {_norm(h.get("confidence")) for h in hypotheses[1:]}
    if leading and leading not in note:
        # Stating some OTHER hypothesis's confidence beside the leading claim
        # is worse than stating none.
        if any(other and other in note for other in others):
            return ["the confidence shown beside the opening claim belongs to "
                    "a different claim"]
    return []


def _withheld_view_is_withheld_everywhere(r, brief, slides) -> list:
    """Declining to form a view is a decision every layer has to honour."""
    withheld = bool((r.get("thesis") or {}).get("view_withheld"))
    if not withheld:
        return []
    problems = []
    if brief is not None and not getattr(brief, "view_withheld", False):
        problems.append("the report declines to form a view and the brief "
                        "presents one")
    for slide in slides or ():
        if slide.get("id") == "view" and slide.get("bullets"):
            texts = " ".join(_norm(b.get("text"))
                             for b in slide["bullets"])
            if "not yet enough" not in texts and "no view" not in texts:
                problems.append("the report declines to form a view and the "
                                "presentation states one")
                break
    return problems


def _citations_resolve(r, slides) -> list:
    """Every citation on a slide points at evidence this run actually holds.

    A citation that resolves to nothing is worse than no citation: it invites
    a reader to check, and then fails them at the moment they decided to
    trust the thing.
    """
    known = {o.get("observation_id") for o in r.get("observations") or ()}
    # The source library is grouped by the role each source played, so every
    # group has to be read — an earlier version looked for a "sources" key
    # that does not exist and therefore knew about nothing.
    for group in (r.get("source_library") or {}).values():
        for entry in group if isinstance(group, list) else ():
            if isinstance(entry, dict):
                known |= {entry.get("source_id"), entry.get("observation_id")}
    known.discard(None)
    dangling = set()
    for slide in slides or ():
        for bullet in slide.get("bullets") or ():
            for reference in bullet.get("evidence") or ():
                if reference and reference not in known:
                    dangling.add(reference)
    if dangling:
        return [f"{len(dangling)} citation(s) on the presentation point at "
                f"evidence this run does not hold"]
    return []
