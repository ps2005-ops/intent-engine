"""The demo is one story, told in six steps, in one order.

THE DEFECT THIS CLOSES
----------------------
Every primary page ended with the same eight-link grid:

    Executive X-Ray · The full story · Intelligence · Executive brief ·
    Presentation · Evidence and sources · Why this reading exists ·
    Full analysis

Eight destinations, no order, no indication which one answers the question the
reader currently has. That is a sitemap. A reader who has just been told what
a company is does not want a menu; they want the next thing. Offered eight
equal doors, most people take none, and the ones who do arrive at a page
written as if they had read a different one first.

THE SIX STEPS, AND WHY THIS ORDER
---------------------------------
    1  Introduction     what this company is, and the question worth arguing
    2  Presentation     why that question matters, made vivid
    3  Full analysis    the reasoning, at board depth
    4  The full story   the same thing as narrative, so it can be retold
    5  History rewind   how it got here, and what could have gone differently
    6  Connect          what changes when the company's own context is added

Each step earns the next: you cannot be interested in a strategic tension you
have not been shown (1 → 2), you will not accept a recommendation whose
reasoning you have not seen (2 → 3), you cannot brief anyone from a document
you cannot retell (3 → 4), you cannot judge a strategy without knowing what
the company already tried (4 → 5), and only then is "what if it knew your
numbers too" a question rather than an advertisement (5 → 6).

WHAT HAPPENED TO THE OTHER SURFACES
-----------------------------------
Nothing. The X-Ray, the intelligence dashboard, the evidence drawer, the
source list and the learning ledger are all still served, still linked, and
still exactly as deep as they were. They are reached from INSIDE the step
that raises the question they answer -- "show the sources", "inspect the
intelligence" -- rather than competing with the story for the reader's
attention (§19). Depth is offered, never required; what changed is that it is
offered at the moment it is wanted.
"""
from __future__ import annotations

import dataclasses
from html import escape
from typing import Optional, Tuple

CONTRACT = "demo_flow.v1"


@dataclasses.dataclass(frozen=True)
class Step:
    key: str
    number: int
    title: str
    #: The URL suffix under /runs/<id>. Empty for the entry step.
    suffix: str
    #: What this step is for, in the reader's terms. Rendered as the
    #: forward-link label, so it has to say what they get, not what it is
    #: called internally.
    promise: str

    def path(self, run_id: str) -> str:
        return f"/runs/{run_id}{self.suffix}"


STEPS: Tuple[Step, ...] = (
    Step("intro", 1, "Introduction", "/intro",
         "what this company is, and the question worth arguing about"),
    Step("slides", 2, "Presentation", "/slides",
         "the case, in slides"),
    Step("full", 3, "Full analysis", "/full",
         "the reasoning, at board depth"),
    Step("story", 4, "The full story", "/story",
         "the same conclusion as a narrative you can retell"),
    Step("history", 5, "History rewind", "/history",
         "how it got here, and what could have gone differently"),
    Step("connect", 6, "Connect your company", "/connect",
         "what changes when it knows your own numbers"),
)

TOTAL = len(STEPS)

BY_KEY = {s.key: s for s in STEPS}

#: Surfaces that are NOT steps. They remain fully served and are reached from
#: inside the step that raises the question they answer.
SECONDARY = {
    "answer": ("The answer", "the sixty-second version, in one scroll"),
    "xray": ("Executive X-Ray", "the decision, on one screen"),
    "dashboard": ("Intelligence", "what the market engine currently holds"),
    # "Evidence" stays in the label. The drawer's own heading is "Why this
    # reading exists", which is the better question -- but a reader scanning
    # for where the sources are looks for the word "evidence", and so does
    # every gate that has ever checked an answer shows what it rests on.
    "evidence": ("Evidence — why this reading exists",
                 "every source, its author, and why it counted"),
    "sources": ("Sources", "what was retrieved, and what was not"),
    "brief": ("Executive brief", "the decision memo, at board length"),
}


def step_for(key: str) -> Optional[Step]:
    return BY_KEY.get(key)


def previous(key: str) -> Optional[Step]:
    step = BY_KEY.get(key)
    if step is None or step.number <= 1:
        return None
    return STEPS[step.number - 2]


def following(key: str) -> Optional[Step]:
    step = BY_KEY.get(key)
    if step is None or step.number >= TOTAL:
        return None
    return STEPS[step.number]


FLOW_CSS = """
<style>
.flownav{display:flex;align-items:center;justify-content:space-between;
gap:1rem;margin:2.6rem 0 .6rem;padding:1.1rem 0 0;
border-top:1px solid var(--line);flex-wrap:wrap}
.flownav .side{flex:1 1 12rem;min-width:0}
.flownav .side.next{text-align:right}
.flownav a{display:inline-block;max-width:100%;text-decoration:none;
color:inherit;border:1px solid var(--line);border-radius:10px;
padding:.6rem .9rem;background:var(--card)}
.flownav a:hover{border-color:var(--accent)}
.flownav .lab{display:block;font-size:.7rem;text-transform:uppercase;
letter-spacing:.08em;color:var(--muted);font-weight:700}
.flownav .ttl{display:block;font-weight:650;margin-top:.1rem}
.flownav .pro{display:block;font-size:.82rem;color:var(--muted);
margin-top:.15rem}
.flownav a.primary{border-color:var(--accent);background:var(--soft)}
.flownav .count{flex:0 0 auto;font-size:.8rem;color:var(--muted);
text-align:center;padding:0 .4rem}
.flownav .count b{display:block;font-size:.95rem;color:var(--fg);
font-weight:650}
.steps{display:flex;gap:.3rem;justify-content:center;margin:.5rem 0 0;
padding:0;list-style:none;flex-wrap:wrap}
.steps li{width:1.9rem;height:.28rem;border-radius:2px;background:var(--line)}
/* The per-step name is for assistive technology only. Without this rule the
   six titles printed as a run-on line under the progress bar -- "Introduction
   Presentation Full analysis The full story History rewind Connect your
   company" -- which is the tab grid, reborn as text. */
.steps .sr{position:absolute;width:1px;height:1px;margin:-1px;padding:0;
overflow:hidden;clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap;
border:0}
.steps li.done{background:var(--muted)}
.steps li.here{background:var(--accent)}
.aside{border:1px solid var(--line);border-left:3px solid var(--accent);
border-radius:8px;padding:.7rem .95rem;margin:1.1rem 0;background:var(--card);
font-size:.92rem}
/* A LABEL, NOT A HEADING. This was an <h4> under pages whose last heading is
   an <h2>, which is a two-level jump and a real accessibility defect -- the
   heading outline is how a screen-reader user navigates, and a skipped level
   reads as a missing section. It is styling, so it is now a <p>. */
.aside .lab{margin:0 0 .25rem;font-size:.72rem;text-transform:uppercase;
letter-spacing:.07em;color:var(--muted);font-weight:700}
.aside a{margin-right:.9rem}
@media(max-width:640px){
  .flownav{flex-direction:column;align-items:stretch}
  .flownav .side.next{text-align:left}
  .flownav .count{order:-1;text-align:left}
}
@media print{.flownav,.steps{display:none}}
</style>
"""


def _e(text) -> str:
    return escape(str(text or ""), quote=True)


def nav(run_id: str, key: str) -> str:
    """← Back · Step X of 6 · Next → and nothing else (§18).

    Rendered on every primary page. The forward link carries the NEXT step's
    promise rather than its name, because "Full analysis" tells a reader what
    a page is called and "the reasoning, at board depth" tells them whether
    they want it.
    """
    step = BY_KEY.get(key)
    if step is None:
        return ""
    rid = _e(run_id)
    back, fwd = previous(key), following(key)
    out = [FLOW_CSS, '<nav class="flownav" aria-label="Where you are in this '
                     'analysis">']
    out.append('<div class="side back">')
    if back is not None:
        out.append(f'<a href="/runs/{rid}{_e(back.suffix)}" rel="prev">'
                   f'<span class="lab">← Back</span>'
                   f'<span class="ttl">{_e(back.title)}</span></a>')
    else:
        # Step 1 has no back inside the story. It gets the way OUT, which is
        # not the same thing and must not be dressed as one.
        out.append('<a href="/analyses"><span class="lab">← Leave</span>'
                   '<span class="ttl">Your analyses</span></a>')
    out.append('</div>')
    out.append(f'<div class="count"><b>Step {step.number} of {TOTAL}</b>'
               f'{_steps_bar(step.number)}</div>')
    out.append('<div class="side next">')
    if fwd is not None:
        out.append(f'<a class="primary" href="/runs/{rid}{_e(fwd.suffix)}" '
                   f'rel="next"><span class="lab">Next →</span>'
                   f'<span class="ttl">{_e(fwd.title)}</span>'
                   f'<span class="pro">{_e(fwd.promise)}</span></a>')
    else:
        out.append(f'<a href="/runs/{rid}{_e(STEPS[0].suffix)}">'
                   f'<span class="lab">Start again</span>'
                   f'<span class="ttl">{_e(STEPS[0].title)}</span></a>')
    out.append('</div></nav>')
    return "".join(out)


def _steps_bar(current: int) -> str:
    cells = []
    for step in STEPS:
        state = ("here" if step.number == current
                 else "done" if step.number < current else "")
        cells.append(f'<li class="{state}"><span class="sr">'
                     f'{_e(step.title)}</span></li>')
    return f'<ul class="steps">{"".join(cells)}</ul>'


def drawer(run_id: str, keys, *, title: str = "Look underneath this") -> str:
    """A contextual link into the secondary surfaces (§19).

    Placed inside the step that raises the question, never as a competing
    destination at the foot of the page.
    """
    rid = _e(run_id)
    links = []
    for key in keys:
        label = SECONDARY.get(key)
        if label is None:
            continue
        links.append(f'<a href="/runs/{rid}/{_e(key)}">{_e(label[0])} — '
                     f'{_e(label[1])}</a>')
    if not links:
        return ""
    return (f'<aside class="aside" aria-label="{_e(title)}">'
            f'<p class="lab">{_e(title)}</p>{"".join(links)}</aside>')
