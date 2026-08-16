"""The Executive X-Ray: one screen, one decision, the rest one click away.

WHAT THIS IS FOR
----------------
The structured decision existed and no screen rendered it, so the only way
to read the product's actual answer was to fetch JSON. This is the screen.

THE FIRST SCREEN RULE
---------------------
Seven things, in this order, and nothing else above the fold:

    THE DECISION        what is actually being decided
    CURRENT READ        what we think, in the wording the evidence permits
    WHY                 the mechanism, not the pipeline
    WHAT CHANGED        movement only; an identical snapshot changed nothing
    KEY RISK            the thing that would make this wrong
    ACTION              what to do
    NEXT TEST           what would settle it

Everything else -- evidence, economics, history, causal work, competitors,
scenarios, learning, provenance -- is below, in disclosure elements that
start closed. Not because it matters less, but because a first screen that
shows everything communicates nothing, and this product's failure mode is
density rather than emptiness.

IT PROJECTS, IT DOES NOT DERIVE
-------------------------------
Every sentence comes from the one `FounderDecision`. This module holds no
opinion about the company: if it needed one, two surfaces would be able to
disagree about the same decision, which §34 exists to prevent. Where a field
is empty the screen says what that absence is, and never fills it in.
"""
from __future__ import annotations

from intent_engine.founder_brief import plain as P

#: Escapes AND fixes source punctuation. Bound once so no string can
#: reach a page through this module without passing both rules.
_e = P.escape

CONTRACT = "executive_xray.v1"

_CSS = """
<style>
.xr{--ink:#111827;--muted:#4b5563;--line:#d1d5db;--bg:#ffffff;
--panel:#f8fafc;--accent:#1d4ed8;--accent-ink:#ffffff;--warn:#9a3412;
font:17px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
color:var(--ink);background:var(--bg);max-width:44rem;margin:0 auto;
padding:10px 18px 56px}
.xr .eyebrow{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;
color:var(--muted);font-weight:700;margin:0 0 .2rem}
.xr h1{font-size:1.5rem;line-height:1.25;margin:.1rem 0 .5rem;
font-weight:650}
.xr h2{font-size:.8rem;text-transform:uppercase;letter-spacing:.07em;
color:var(--muted);margin:1.5rem 0 .3rem;font-weight:700}
.xr p{margin:0 0 .6rem}
.xr .stamp{color:var(--muted);font-size:.85rem;margin:0 0 1rem}
.xr .chip{display:inline-block;font-size:.76rem;font-weight:700;
padding:3px 9px;border-radius:999px;border:1px solid var(--line);
background:var(--panel);color:var(--muted);margin:0 .3rem .3rem 0;
text-transform:none;letter-spacing:0}
.xr .decide{background:var(--panel);border:1px solid var(--line);
border-left:3px solid var(--accent);border-radius:8px;padding:1rem 1.1rem;
margin:0 0 1.2rem}
.xr .decide .q{font-size:1.1rem;font-weight:640;margin:0 0 .5rem}
.xr .decide .read{margin:0 0 .4rem}
.xr .decide .why{color:var(--muted);font-size:.9rem;margin:0}
.xr .grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:0 0 1rem}
.xr .cell{border:1px solid var(--line);border-radius:8px;padding:.8rem .9rem;
background:var(--bg)}
.xr .cell .k{font-size:.74rem;text-transform:uppercase;letter-spacing:.07em;
color:var(--muted);font-weight:700;margin:0 0 .3rem}
.xr .cell p{margin:0;font-size:.95rem}
.xr .cell.risk{border-left:3px solid var(--warn)}
.xr .cell.act{border-left:3px solid var(--accent)}
.xr details{border-top:1px solid var(--line);padding:.7rem 0}
.xr details summary{cursor:pointer;font-weight:640;font-size:.98rem;
list-style:none;display:flex;justify-content:space-between;gap:12px}
.xr details summary::-webkit-details-marker{display:none}
.xr details summary::after{content:"+";color:var(--muted);font-weight:700}
.xr details[open] summary::after{content:"\\2212"}
.xr details summary .sub{color:var(--muted);font-weight:400;font-size:.86rem}
.xr details .body{padding:.6rem 0 .2rem}
.xr ul{margin:.3rem 0;padding-left:1.15rem}
.xr li{margin:0 0 .45rem}
.xr .rowlist{list-style:none;padding:0;margin:.4rem 0}
.xr .rowlist li{border:1px solid var(--line);border-radius:7px;
padding:.6rem .75rem;margin:0 0 .5rem;background:var(--panel)}
.xr .rowlist .h{font-weight:640;margin:0 0 .25rem}
.xr .rowlist .m{color:var(--muted);font-size:.88rem;margin:0}
.xr .chain{font-size:.9rem;margin:.3rem 0 0}
.xr .chain span{color:var(--muted)}
.xr .none{color:var(--muted);font-style:normal;font-size:.92rem}
.xr a{color:var(--accent)}
.xr .acts{display:flex;gap:10px;flex-wrap:wrap;margin:1.4rem 0 .4rem}
.xr .acts a{display:inline-block;padding:9px 16px;border-radius:9px;
border:1px solid var(--line);text-decoration:none;color:var(--ink);
font-weight:600;font-size:.94rem}
.xr .acts a.primary{background:var(--accent);color:var(--accent-ink);
border-color:var(--accent)}
.xr :focus-visible{outline:3px solid var(--accent);outline-offset:2px}
@media (max-width:640px){.xr{font-size:16px;padding:8px 14px 40px}
.xr h1{font-size:1.28rem}.xr .grid{grid-template-columns:1fr}}
@media (prefers-color-scheme:dark){
.xr{--ink:#f3f4f6;--muted:#c3cad6;--line:#3a4454;--bg:#0f141c;
--panel:#161c26;--accent:#7aa2ff;--accent-ink:#0b1220;--warn:#fca5a5}}
@media print{.xr .acts{display:none}.xr details{border:0}
.xr details .body{display:block}}
</style>
"""


def _first(rows, default: str = "") -> str:
    for row in rows or ():
        if row:
            return str(row)
    return default


def _absent(what: str) -> str:
    """State the absence. Never an empty box, never an invented sentence."""
    return f'<p class="none">{_e(what)}</p>'


def _bullets(rows, empty: str) -> str:
    rows = [str(r) for r in (rows or ()) if str(r).strip()]
    if not rows:
        return _absent(empty)
    return "<ul>" + "".join(f"<li>{_e(r)}</li>" for r in rows) + "</ul>"


def _section(title: str, sub: str, body: str, *, open_: bool = False) -> str:
    return (f'<details{" open" if open_ else ""}><summary>'
            f'<span>{_e(title)}</span>'
            f'<span class="sub">{_e(sub)}</span></summary>'
            f'<div class="body">{body}</div></details>')


# --- the expandable sections ------------------------------------------------

def _evidence_body(d: dict) -> str:
    supporting = list(d.get("supporting_evidence_ids") or ())
    contradicting = list(d.get("contradicting_evidence_ids") or ())
    origins = int(d.get("independent_origins") or 0)
    parts = []
    if supporting:
        # §17: never "8/14 independent". The sentence says what the number
        # means, and the independence count is stated as unmeasured rather
        # than shown as zero -- zero independent sources is a claim, and the
        # market snapshot does not carry the measurement to make it.
        parts.append(
            f"<p>{len(supporting)} published evidence row(s) sit under this "
            f"reading.</p>")
        parts.append(
            "<p>Source independence is not measured by the published market "
            "snapshot, so how many of these are separate accounts and how "
            "many repeat one underlying report is not known here.</p>"
            if not origins else
            f"<p>{origins} of them are separate accounts; the rest repeat "
            f"those underlying reports.</p>")
    else:
        parts.append(_absent("No evidence rows are cited for this company in "
                             "the published record."))
    if contradicting:
        parts.append(f"<p>{len(contradicting)} row(s) point the other way and "
                     f"are carried rather than dropped.</p>")
    signals = d.get("signals") or ()
    if signals:
        rows = "".join(
            f'<li><p class="h">{_e(s.get("name", ""))}</p>'
            f'<p class="m">{_e(s.get("why", ""))}</p></li>'
            for s in signals if s.get("name"))
        parts.append("<h2>What we watch, and why</h2>"
                     f'<ul class="rowlist">{rows}</ul>')
    return "".join(parts)


def _economics_body(d: dict) -> str:
    rows = d.get("economic_transmission") or ()
    state = str(d.get("economic_state") or "")
    if not rows:
        return _absent(P.say(state, P.ECONOMIC))
    out = [f"<p>{_e(P.say(state, P.ECONOMIC))}</p>"]
    items = []
    for row in rows:
        items.append(
            f'<li><p class="h">'
            f'{_e(P.humanise(row.get("channel", "")).capitalize())}</p>'
            f'<p class="m">{_e(row.get("mechanism", ""))}</p>'
            f'<p class="chain"><span>shows up in</span> '
            f'{_e(row.get("business_variable", ""))}<br>'
            f'<span>so</span> {_e(row.get("decision_implication", ""))}</p>'
            f'</li>')
    out.append(f'<ul class="rowlist">{"".join(items)}</ul>')
    return "".join(out)


def _causal_body(d: dict) -> str:
    parts = []
    question = str(d.get("causal_question") or "")
    if question:
        parts.append(f"<h2>The question</h2><p>{_e(question)}</p>")
        why = str(d.get("why_this_causal_question") or "")
        if why:
            parts.append(f'<p class="none">{_e(why)}</p>')
    parts.append("<h2>What we could establish</h2>")
    parts.append(f'<p>{_e(P.say(d.get("causal_status"), P.CAUSAL))}</p>')
    gaps = d.get("information_gaps") or ()
    if gaps:
        parts.append("<h2>What is missing</h2>" +
                     _bullets(gaps, "Nothing is recorded as missing."))
    mdrs = d.get("minimum_data_requests") or ()
    if mdrs:
        parts.append("<h2>What would resolve it</h2>" +
                     _bullets(mdrs, ""))
    vois = d.get("value_of_information") or ()
    if vois:
        parts.append("<h2>What that would be worth</h2>" + _bullets(vois, ""))
    return "".join(parts)


def _competitor_body(d: dict) -> str:
    parts = []
    peers = d.get("competitors") or ()
    if peers:
        rows = "".join(
            f'<li><p class="h">{_e(c.get("name", ""))}</p>'
            f'<p class="m">{_e(c.get("why", ""))}</p></li>' for c in peers)
        parts.append(f'<ul class="rowlist">{rows}</ul>')
    else:
        parts.append(_absent("No competitor set was selected: this company's "
                             "business model is not classified here, so peers "
                             "cannot be chosen by what they actually compete "
                             "on."))
    moves = d.get("adversary") or ()
    if moves:
        parts.append("<h2>If we move, what do they do</h2>")
        rows = []
        for move in moves:
            rows.append(
                f'<li><p class="h">{_e(move.get("level", ""))} &middot; '
                f'{_e(move.get("action", ""))}</p>'
                f'<p class="m">{_e(move.get("rationale", ""))}</p>'
                f'<p class="chain"><span>watch for</span> '
                f'{_e(move.get("observable_signal", ""))}<br>'
                f'<span>we would</span> {_e(move.get("countermeasure", ""))}'
                f'</p></li>')
        parts.append(f'<ul class="rowlist">{"".join(rows)}</ul>')
        parts.append('<p class="none">No probability is put on these '
                     'branches. The inputs a game-theoretic weighting would '
                     'need are not in the published record, and a number '
                     'invented for the look of it would be the least '
                     'trustworthy thing on this page.</p>')
    return "".join(parts)


def _scenario_body(d: dict) -> str:
    rows = d.get("scenarios") or ()
    if not rows:
        return _absent("No scenarios were built: they start from a management "
                       "lever, and no lever was selected for this company.")
    items = []
    for s in rows:
        items.append(
            f'<li><p class="h">{_e(str(s.get("name", "")).title())} '
            f'&middot; {_e(s.get("lever", ""))}</p>'
            f'<p class="m">{_e(s.get("first_order", ""))}</p>'
            f'<p class="chain"><span>then</span> '
            f'{_e(s.get("second_order", ""))}<br>'
            f'<span>and then</span> {_e(s.get("third_order", ""))}<br>'
            f'<span>competitor</span> {_e(s.get("competitor_response", ""))}'
            f'<br><span>stop if</span> {_e(s.get("kill_switch", ""))}</p>'
            f'</li>')
    return (f'<ul class="rowlist">{"".join(items)}</ul>'
            '<p class="none">Every branch is a direction and a mechanism. No '
            'figure is put on any of them, because none is measurable from '
            'the published record.</p>')


def _history_body(d: dict) -> str:
    episodes = d.get("historical_playback") or ()
    dimensions = d.get("historical_dimensions") or ()
    if episodes:
        items = []
        for ep in episodes:
            items.append(
                f'<li><p class="h">{_e(ep.get("episode_date", ""))}</p>'
                f'<p class="m">{_e(ep.get("what_happened", ""))}</p></li>')
        return f'<ul class="rowlist">{"".join(items)}</ul>'
    # THE MEASURED STATE, not a constant. This paragraph was hardcoded and
    # therefore said the same thing whatever the archive held -- prose
    # asserting a fact about a producer that did not exist. When the run
    # carries an assessment, the surface renders WHAT WAS MEASURED and can
    # tell a blocked archive from a describable period.
    history = d.get("economic_history")
    history = history if isinstance(history, dict) else {}
    if history:
        from intent_engine.strategic_intelligence import economic_history as EH
        label = {EH.HISTORICAL_REPLAY_BLOCKED_DATA: "Replay not yet valid",
                 EH.DESCRIPTIVE_HISTORY_ONLY: "Descriptive history",
                 EH.HISTORICAL_REPLAY_AVAILABLE: "Historical replay"}.get(
                     str(history.get("state") or ""), "Replay not yet valid")
        return (f'<p class="none">{_e(label)}</p>'
                f'<p>{_e(EH.plain_statement(history))}</p>'
                f'<p class="none">We hold '
                f'{int(history.get("retrieval_months") or 0)} month(s) of our '
                f'own observations; a replay needs '
                f'{int(history.get("required_months") or 0)}.'
                + (f' That clears on '
                   f'{_e(str(history.get("next_eligible_date")))}.'
                   if history.get("next_eligible_date") else "")
                + '</p>')
    parts = [
        '<p>No historical episode is replayed for this company. Replay '
        'requires the company\'s own observations as they stood at an '
        'earlier date, and the published market snapshot carries the current '
        'reading only — there is no vintage to roll back to.</p>',
        '<p class="none">Publication time is not used as a substitute. Using '
        'when a document was published as when the fact was knowable is the '
        'error that makes a replay look right for the wrong reason.</p>']
    if dimensions:
        parts.append("<h2>What we would replay, once vintages exist</h2>" +
                     _bullets(dimensions, ""))
    return "".join(parts)


#: How each second-iteration state reads to a chief executive. The enum is a
#: diagnostic; this is the sentence. Held deliberately in one place so the
#: X-Ray, the deck and the Q&A cannot each invent their own translation --
#: which is exactly how two hardcoded history paragraphs drifted apart.
_ITERATION_COPY = {
    "FIRST_OBSERVATION":
        "This is the baseline reading. There is no earlier view to compare "
        "it against yet.",
    "NEW_INFORMATION_CHANGED_VIEW":
        "New evidence arrived and it changed the view.",
    "NEW_INFORMATION_CONFIRMED_VIEW":
        "New evidence arrived, tested the view, and it held. A position that "
        "has survived new evidence is stronger than one nothing has "
        "challenged.",
    "NEW_INFORMATION_NOT_DECISION_RELEVANT":
        "New information arrived and none of it bore on this decision.",
    "REOBSERVATION_TESTED_AND_HELD":
        "We re-read what we already had, tested the view against it, and it "
        "held.",
    "NO_NEW_INFORMATION":
        "Nothing arrived that we did not already hold, so no new learning "
        "was recorded.",
    "INCOMPARABLE":
        "These two readings cannot be compared, so any difference between "
        "them is not a change of mind.",
}


def _named(ids, labels) -> str:
    """Sources by the name of the page they cite, never by an internal id.

    D16. This card rendered "ev_1dccf2f4d0bd8562; ev_1fb641572cc55989" under
    "What it tested" -- opaque strings where a reader expects to see what was
    read. The map that turns those into readable titles already existed and
    already served the sources list on this same screen; this card simply
    never asked for it.

    AN ID WITH NO LABEL IS NOT GUESSED AT. Falling back to the raw id is the
    defect, and inventing a name for it would be worse: an unnamed source is
    counted and described as unnamed, which is true and leaks nothing.
    """
    labels = labels or {}
    seen = list(dict.fromkeys(str(i) for i in (ids or ()) if str(i or "").strip()))
    if not seen:
        return ""

    # PROSE IS NOT AN ID. `tested_claims` carries BOTH: sometimes evidence
    # ids, sometimes the claim itself in words ("pricing power is intact").
    # The first version of this ran every entry through the label map and
    # replaced the readable ones with "3 source(s) we cannot name" -- turning
    # a sentence a reader understood into a count, which is a worse defect
    # than the raw ids it was written to remove. A value with whitespace in it
    # was written to be read; it is passed through untouched.
    prose = [s for s in seen if " " in s.strip()]
    opaque = [s for s in seen if " " not in s.strip()]
    if prose and not opaque:
        return "; ".join(prose[:3])

    named = prose[:] + [labels[i] for i in opaque if labels.get(i)]
    unnamed = len(opaque) - sum(1 for i in opaque if labels.get(i))
    if named and not unnamed:
        return "; ".join(named[:3])
    if named:
        return (f"{'; '.join(named[:3])} and {unnamed} further source(s) we "
                f"cannot name on this card")
    return (f"{len(seen)} source(s) we already held, which this card cannot "
            f"name")


def _second_iteration_body(d: dict, *, labels=None) -> str:
    """What the second look changed, and what it merely confirmed.

    Renders the canonical delta -- it recomputes nothing. Absent when no
    comparison ran, because an empty card here would imply a comparison that
    found nothing, which is the opposite of not having looked.
    """
    delta = d.get("second_iteration")
    if not isinstance(delta, dict) or not delta:
        return ""
    from intent_engine.strategic_intelligence import second_iteration as SI
    card = SI.hero(delta)
    state = str(card.get("state") or "")
    tested = _named(delta.get("tested_claims") or (), labels)
    rows = [("New information", card.get("new_information", "")),
            ("What it tested",
             tested if tested else card.get("what_it_tested", "")),
            ("What held", card.get("what_held", "")),
            ("What changed", card.get("what_changed", "")),
            ("Effect on the decision", card.get("decision_effect", ""))]
    body = "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>"
                   for k, v in rows if str(v).strip())
    said = _ITERATION_COPY.get(state, card.get("statement", ""))
    # "DID NOT ADD" IS ITSELF A COMPARATIVE CLAIM. It belongs to a reading
    # that had something to add to; on a baseline there is no stock of
    # knowledge this run failed to increase, and rendering it there put a
    # third contradictory sentence on a card that already said "this is the
    # baseline" and "10 source(s) we had not seen before".
    gain = "" if (state in SI.REPRESENTS_LEARNING
                  or state in (SI.FIRST_OBSERVATION, SI.INCOMPARABLE)) else (
        '<p class="none">This did not add to what the system knows.</p>')
    return f'<p>{_e(said)}</p><dl class="kv">{body}</dl>{gain}'


def _beliefs_body(d: dict) -> str:
    parts = [f'<p>{_e(P.say(d.get("hidden_state"), P.HIDDEN, default=""))}</p>'
             if str(d.get("hidden_state") or "") in P.HIDDEN else
             f'<p>This company\'s leading operating posture reads '
             f'{_e(P.humanise(d.get("hidden_state")))}.</p>']
    monitoring = d.get("monitoring") or ()
    parts.append("<h2>What is open</h2>" +
                 _bullets(monitoring,
                          "Nothing is currently preregistered for this "
                          "company."))
    changed = d.get("what_changed") or ()
    parts.append("<h2>What changed</h2>" +
                 _bullets(changed, "Nothing changed since the last reading."))
    mind = d.get("what_changed_mind") or ()
    parts.append("<h2>What changed our mind</h2>" +
                 _bullets(mind,
                          "Nothing has changed our mind. That is different "
                          "from nothing changing: the record moved or it did "
                          "not, and separately our position on it held."))
    return "".join(parts)


def _profile_body(d: dict) -> str:
    profile = d.get("company_profile") or {}
    if not profile or not profile.get("known"):
        return _absent(
            str(profile.get("basis") or
                "This company is not classified in the validation universe, "
                "so the analysis above was selected from the published record "
                "alone rather than from its economics."))
    rows = [
        ("What this business is", profile.get("business_model")),
        ("How the industry is structured", profile.get("industry_structure")),
        ("How demand arrives", profile.get("demand_model")),
        ("Who the customers are", profile.get("customer_structure")),
        ("How it prices", profile.get("pricing_model")),
        ("Operating leverage", profile.get("operating_leverage")),
        ("Capital intensity", profile.get("capital_intensity")),
        ("Regulatory exposure", profile.get("regulatory_exposure")),
        ("Exposure to the cycle", profile.get("cyclical_exposure")),
    ]
    items = "".join(
        f'<li><p class="h">{_e(k)}</p><p class="m">{_e(v)}</p></li>'
        for k, v in rows if v and v != "UNKNOWN")
    drivers = profile.get("primary_revenue_drivers") or ()
    costs = profile.get("primary_cost_drivers") or ()
    tail = ""
    if drivers:
        tail += ("<h2>Revenue moves with</h2>" + _bullets(drivers, ""))
    if costs:
        tail += ("<h2>Cost moves with</h2>" + _bullets(costs, ""))
    # A PARTIAL profile shows fewer rows above, because the fields the
    # manifest would have added are genuinely absent. Without this note the
    # reader sees a shorter list and no reason for it, which reads as the
    # company being less interesting rather than less classified.
    limitation = str(profile.get("profile_limitation") or "")
    note = f'<p class="none">{_e(limitation)}</p>' if limitation else ""
    return (f'<ul class="rowlist">{items}</ul>{tail}{note}'
            f'<p class="none">{_e(profile.get("basis", ""))}</p>')


def _provenance_body(d: dict) -> str:
    parts = [_bullets(d.get("provenance") or (),
                      "No provenance was recorded for this reading.")]
    considered = d.get("archetypes_considered") or ()
    if considered:
        rows = "".join(
            f'<li><p class="h">'
            f'{_e(P.ARCHETYPE.get(r.get("archetype"), r.get("archetype", "")))}'
            f'</p><p class="m">{_e(r.get("why", ""))}</p></li>'
            for r in considered)
        parts.append("<h2>Decisions we considered and did not select</h2>"
                     f'<ul class="rowlist">{rows}</ul>')
    parts.append(
        '<p class="none">This reading was computed from the published record '
        'with no language model involved at any step, so every sentence above '
        'traces to a field rather than to a generation.</p>')
    return "".join(parts)


# --- the screen -------------------------------------------------------------

def render(decision: dict, *, company: str = "", stamp: str = "",
           crossing: str = "", links=None, labels=None) -> str:
    """One decision, as the screen an executive reads. Returns a body."""
    d = decision or {}
    company = company or str(d.get("company") or "")
    standing = str(d.get("standing") or "")
    archetype = str(d.get("decision_archetype") or "")

    chips = [f'<span class="chip">{_e(P.label(standing))}</span>']
    if archetype and archetype != "UNKNOWN":
        chips.append(f'<span class="chip">'
                     f'{_e(P.ARCHETYPE.get(archetype, archetype))} '
                     f'decision</span>')
    if crossing:
        chips.append(f'<span class="chip">'
                     f'{"Market + analysis" if crossing == "MARKET_AND_FOUNDER" else P.humanise(crossing)}'
                     f'</span>')

    risk = P.key_risk(d) or ("No risk is recorded for this reading, which is "
                             "itself worth checking.")
    action = str(d.get("recommended_next_move") or
                 "No action is put forward for this company.")
    reason = str(d.get("recommendation_reason") or "")
    test = _first([_first(d.get("minimum_viable_experiments") or ()),
                   _first(d.get("minimum_data_requests") or ())],
                  "No next test is recorded.")

    head = (
        f'<p class="eyebrow">Executive X-Ray</p>'
        f'<h1>{_e(company)}</h1>'
        f'<p class="stamp">{"".join(chips)}</p>'
        f'<div class="decide">'
        f'<p class="q">{_e(d.get("decision_question", ""))}</p>'
        f'<p class="read">{_e(d.get("current_read", ""))}</p>'
        f'<p class="why">{_e(P.say(standing, P.STANDING))}</p>'
        f'</div>')

    why_q = str(d.get("why_this_question") or "") or (
        "The decision was not selected from this company's economics, "
        "because this company is not classified here.")
    grid = (
        f'<div class="grid">'
        f'<div class="cell"><p class="k">Why this decision</p>'
        f'<p>{_e(why_q)}</p></div>'
        f'<div class="cell"><p class="k">What changed</p>'
        f'<p>{_e(_first(d.get("what_changed") or (), "Nothing changed."))}'
        f'</p></div>'
        f'<div class="cell risk"><p class="k">Key risk</p>'
        f'<p>{_e(risk)}</p></div>'
        f'<div class="cell act"><p class="k">Action</p>'
        f'<p>{_e(action)}</p></div>'
        f'</div>'
        f'<div class="cell act" style="margin-bottom:1rem">'
        f'<p class="k">Next test</p><p>{_e(test)}</p></div>')
    if reason:
        grid += f'<p class="none">{_e(reason)}</p>'

    sections = "".join([
        _section("The evidence under this",
                 f'{len(d.get("supporting_evidence_ids") or ())} row(s)',
                 _evidence_body(d)),
        _section("What kind of business this is",
                 "the economics the analysis was selected from",
                 _profile_body(d)),
        _section("How the economy reaches it",
                 f'{len(d.get("economic_transmission") or ())} channel(s)',
                 _economics_body(d)),
        _section("What we could and could not establish",
                 "the causal question", _causal_body(d)),
        _section("What history says", "comparable periods", _history_body(d)),
        _section("What changed since last time", "the second look",
                 _second_iteration_body(d, labels=labels)),
        _section("Competitors, and what they would do",
                 f'{len(d.get("competitors") or ())} selected',
                 _competitor_body(d)),
        _section("If we act, what follows",
                 f'{len(d.get("scenarios") or ())} branches',
                 _scenario_body(d)),
        _section("What we believe and what is open",
                 "positions, expectations, movement", _beliefs_body(d)),
        _section("Where this came from", "provenance",
                 _provenance_body(d)),
    ])

    acts = ""
    if links:
        buttons = []
        for i, (text, url) in enumerate(links):
            cls = ' class="primary"' if i == 0 else ""
            buttons.append(f'<a href="{_e(url)}"{cls}>{_e(text)}</a>')
        acts = '<div class="acts">' + "".join(buttons) + "</div>"

    foot = f'<p class="stamp">{_e(stamp)}</p>' if stamp else ""
    return (f'{_CSS}<main class="xr">{head}{grid}{sections}{acts}{foot}'
            f'</main>')
