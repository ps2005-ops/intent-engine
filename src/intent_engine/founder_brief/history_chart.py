"""The three-line history chart: inline SVG, JS-free, and legible without colour.

WHY THE CHART IS DRAWN HERE AND NOT COMPUTED HERE
-------------------------------------------------
`executive.history_simulator` decides what the three lines ARE. This module
decides only how they look. The split matters because the epistemic state of a
line is the most important thing on the page and a renderer that could choose
its own would eventually render a counterfactual as an observation — the exact
failure the legend is supposed to prevent.

THREE WAYS TO TELL THE LINES APART (§86)
----------------------------------------
Colour, dash pattern AND marker shape. Any one of the three is enough:

    ACTUAL              solid, round markers
    MARKET EXPECTATION  long dashes, diamond markers, with a band
    BETTER STRATEGY     dotted, square markers

So the chart survives greyscale printing, a colour-blind reader, and a dark
theme that shifts every hue. The band belongs to the expectation and to
nothing else, because it is the only line whose uncertainty is modelled.

NO JAVASCRIPT
-------------
The date control is a radio group; `:checked ~` shows that vintage's overlay
group inside one SVG that carries all of them. A radio group is a real
keyboard control with real labels — arrow keys move it, a screen reader
announces it, and it works in a printed page. A range input would have needed
script to redraw and would have announced a number where a reader needs a year.
"""
from __future__ import annotations

from html import escape
from typing import List, Optional, Sequence, Tuple

from intent_engine.executive import history_simulator as HS
from intent_engine.executive import resolution as R


def _e(text) -> str:
    return escape(str(text or ""), quote=True)


#: Chart geometry, in user units. The SVG scales; these never change.
_W, _H = 1000.0, 430.0
# _PAD_T leaves room for the axis label ABOVE the plot area. At 26 the label
# sat on the same baseline as the topmost gridline value and the two printed
# over each other — measured live on Palantir, whose index reaches five
# figures so the top tick is at its widest.
_PAD_L, _PAD_R, _PAD_T, _PAD_B = 68.0, 22.0, 40.0, 52.0

CHART_CSS = """
<style>
.hsim{--c-actual:#0f5132;--c-expect:#1d4ed8;--c-counter:#8a4b00;
--c-grid:#e2e8f0;--c-axis:#64748b;--c-band:rgba(29,78,216,.10);
--c-after:#94a3b8;margin:1.2rem 0}
@media (prefers-color-scheme:dark){.hsim{--c-actual:#4ade80;--c-expect:#7aa2ff;
--c-counter:#fbbf24;--c-grid:#243044;--c-axis:#94a3b8;
--c-band:rgba(122,162,255,.14);--c-after:#5b6779}}
.hsim svg{width:100%;height:auto;display:block;overflow:visible}
.hsim .gridline{stroke:var(--c-grid);stroke-width:1}
.hsim .axis{stroke:var(--c-axis);stroke-width:1.2}
.hsim .tick{fill:var(--c-axis);font-size:15px;font-family:inherit}
.hsim .axlabel{fill:var(--c-axis);font-size:15px;font-family:inherit;
font-weight:600}
.hsim .ln-actual{fill:none;stroke:var(--c-actual);stroke-width:3.4;
stroke-linejoin:round;stroke-linecap:round}
.hsim .ln-actual-after{fill:none;stroke:var(--c-after);stroke-width:2.6;
stroke-dasharray:1 6;stroke-linecap:round}
.hsim .ln-expect{fill:none;stroke:var(--c-expect);stroke-width:3;
stroke-dasharray:13 7;stroke-linecap:round}
.hsim .ln-counter{fill:none;stroke:var(--c-counter);stroke-width:3;
stroke-dasharray:2 6;stroke-linecap:round}
.hsim .band{fill:var(--c-band);stroke:none}
.hsim .mk-actual{fill:var(--c-actual)}
.hsim .mk-expect{fill:var(--c-expect)}
.hsim .mk-counter{fill:var(--c-counter)}
.hsim .nowline{stroke:var(--c-axis);stroke-width:1.6;stroke-dasharray:4 4}
.hsim .nowtext{fill:var(--c-axis);font-size:14px;font-weight:700;
font-family:inherit}
.hsim-legend{display:flex;flex-wrap:wrap;gap:.5rem .9rem;margin:.7rem 0 .2rem;
padding:0;list-style:none}
.hsim-legend li{display:flex;align-items:flex-start;gap:.45rem;
font-size:.83rem;line-height:1.35;flex:1 1 15rem;min-width:0}
.hsim-legend svg{width:34px;height:14px;flex:0 0 34px;margin-top:.18rem}
.hsim-legend b{display:block;font-size:.85rem}
.hsim-legend .basis{display:inline-block;font-size:.64rem;font-weight:700;
text-transform:uppercase;letter-spacing:.07em;border:1px solid var(--line);
border-radius:999px;padding:.02rem .42rem;margin-left:.35rem;
color:var(--muted);white-space:nowrap;vertical-align:.06em}
.hsim-legend .m{color:var(--muted);font-size:.79rem}
.hsim-axis-note{font-size:.83rem;color:var(--muted);margin:.4rem 0 0}
.hsim-alt{margin:.8rem 0 0}
.hsim-alt summary{cursor:pointer;font-size:.82rem;color:var(--muted)}
.hsim-alt table{width:100%;border-collapse:collapse;margin-top:.6rem;
font-size:.82rem}
.hsim-alt th,.hsim-alt td{border:1px solid var(--line);padding:.28rem .5rem;
text-align:right}
.hsim-alt th:first-child,.hsim-alt td:first-child{text-align:left}
.hsim-alt .scroll{overflow-x:auto}
.hcards{display:grid;gap:.7rem;grid-template-columns:repeat(auto-fit,
minmax(15rem,1fr));margin:1.1rem 0}
.hcards article{border:1px solid var(--line);border-radius:10px;
padding:.75rem .9rem;background:var(--card);min-width:0}
.hcards h3{margin:0 0 .3rem;font-size:.72rem;text-transform:uppercase;
letter-spacing:.08em;color:var(--muted)}
.hcards p{margin:0;font-size:.92rem;line-height:1.5}
.hcards .basis{display:inline-block;font-size:.63rem;font-weight:700;
text-transform:uppercase;letter-spacing:.07em;border:1px solid var(--line);
border-radius:999px;padding:.02rem .42rem;margin-left:.35rem;color:var(--muted)}
.hcards .cf{border-left:3px solid var(--c-counter,#8a4b00)}
.hcards .obs{border-left:3px solid var(--c-actual,#0f5132)}
.hcards .mod{border-left:3px solid var(--c-expect,#1d4ed8)}
.drivers{margin:.9rem 0 0;padding:0 0 0 1.1rem;font-size:.86rem;
color:var(--muted)}
.drivers li{margin:.2rem 0}
/* --- the date control: radios, no script ------------------------------- */
.hrewind input[type=radio]{position:absolute;opacity:0;pointer-events:none}
.hrail{display:flex;gap:.25rem;align-items:stretch;margin:1.1rem 0 .2rem;
overflow-x:auto;padding-bottom:.4rem;-webkit-overflow-scrolling:touch}
.hrail label{flex:1 1 0;min-width:6rem;cursor:pointer;text-align:center;
border:1px solid var(--line);border-bottom-width:3px;border-radius:8px;
padding:.5rem .35rem;background:var(--card);font-size:.72rem;
color:var(--muted);line-height:1.25}
.hrail label b{display:block;font-size:1rem;color:var(--fg);font-weight:650}
.hpanel{display:none}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;
overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
@media (max-width:34rem){
.hcards{grid-template-columns:1fr}
.hrail label{min-width:5rem;font-size:.66rem}
.hsim svg{min-height:230px}
}
</style>
"""


# ===========================================================================
# geometry
# ===========================================================================
class _Scale:
    def __init__(self, years: Sequence[int], values: Sequence[float]):
        self.y0, self.y1 = min(years), max(years)
        lo, hi = min(values), max(values)
        span = hi - lo
        if span <= 0:
            span = max(abs(hi), 1.0)
        self.v0 = max(0.0, lo - span * 0.10)
        self.v1 = hi + span * 0.12

    def x(self, year: float) -> float:
        if self.y1 == self.y0:
            return _PAD_L
        return _PAD_L + (year - self.y0) / (self.y1 - self.y0) * (
            _W - _PAD_L - _PAD_R)

    def y(self, value: float) -> float:
        if self.v1 == self.v0:
            return _H - _PAD_B
        return (_H - _PAD_B) - (value - self.v0) / (self.v1 - self.v0) * (
            _H - _PAD_T - _PAD_B)


def _path(scale: _Scale, points: Sequence[Tuple[float, float]]) -> str:
    if not points:
        return ""
    return "M" + " L".join(f"{scale.x(a):.1f},{scale.y(b):.1f}"
                           for a, b in points)


def _marker(scale: _Scale, year: float, value: float, shape: str,
            cls: str) -> str:
    cx, cy = scale.x(year), scale.y(value)
    if shape == "circle":
        return f'<circle class="{cls}" cx="{cx:.1f}" cy="{cy:.1f}" r="4.2"/>'
    if shape == "square":
        return (f'<rect class="{cls}" x="{cx - 3.8:.1f}" y="{cy - 3.8:.1f}" '
                f'width="7.6" height="7.6"/>')
    return (f'<polygon class="{cls}" points="'
            f'{cx:.1f},{cy - 5:.1f} {cx + 5:.1f},{cy:.1f} '
            f'{cx:.1f},{cy + 5:.1f} {cx - 5:.1f},{cy:.1f}"/>')


def _ticks(lo: float, hi: float, count: int = 4) -> List[float]:
    if hi <= lo:
        return [lo]
    raw = (hi - lo) / count
    magnitude = 10 ** int(max(0, len(str(int(raw))) - 1)) if raw >= 1 else 1
    step = max(1.0, round(raw / magnitude) * magnitude)
    out, value = [], (int(lo / step) + 1) * step
    while value < hi and len(out) < count + 2:
        out.append(value)
        value += step
    return out


# ===========================================================================
# the chart
# ===========================================================================
def chart_svg(sim: HS.Simulation, vintage: HS.SimVintage) -> str:
    """One SVG for one vintage, on its OWN vertical scale.

    A single shared scale was the first design and it was unreadable. The
    earliest vintage extrapolates the company's early growth across the whole
    span — for Cloudflare that reaches an index near 8000 — so every other
    vintage's three lines were compressed into the bottom eighth of the plot
    and the comparison the page exists for could not be seen. The scale
    belongs to the comparison being made, and the comparison changes with the
    date.
    """
    actual = vintage.actual
    years = [p.year for p in actual.points]
    values = [p.value for p in actual.points]
    for path in (vintage.expectation, vintage.counterfactual):
        if path is None:
            continue
        for point in path.points:
            years.append(point.year)
            values.append(point.value)
            if point.high is not None:
                values.append(point.high)
            if point.low is not None:
                values.append(point.low)
    scale = _Scale(years, values)
    out: List[str] = [
        f'<svg viewBox="0 0 {_W:.0f} {_H:.0f}" role="img" '
        f'preserveAspectRatio="xMidYMid meet" '
        f'aria-label="{_e(text_alternative(sim, vintage))}">']

    # grid + axes
    for value in _ticks(scale.v0, scale.v1):
        y = scale.y(value)
        out.append(f'<line class="gridline" x1="{_PAD_L}" y1="{y:.1f}" '
                   f'x2="{_W - _PAD_R}" y2="{y:.1f}"/>')
        out.append(f'<text class="tick" x="{_PAD_L - 9}" y="{y + 5:.1f}" '
                   f'text-anchor="end">{value:.0f}</text>')
    out.append(f'<line class="axis" x1="{_PAD_L}" y1="{_PAD_T}" '
               f'x2="{_PAD_L}" y2="{_H - _PAD_B}"/>')
    out.append(f'<line class="axis" x1="{_PAD_L}" y1="{_H - _PAD_B}" '
               f'x2="{_W - _PAD_R}" y2="{_H - _PAD_B}"/>')
    # Year ticks, thinned so labels never collide on a 19-year span.
    span = scale.y1 - scale.y0
    every = 1 if span <= 10 else (2 if span <= 20 else 5)
    for year in range(scale.y0, scale.y1 + 1):
        if year != scale.y1 and (year - scale.y0) % every:
            continue
        x = scale.x(year)
        out.append(f'<text class="tick" x="{x:.1f}" y="{_H - _PAD_B + 22:.0f}"'
                   f' text-anchor="middle">{year}</text>')
    out.append(f'<text class="axlabel" x="{_PAD_L - 52}" y="{_PAD_T - 16:.0f}" '
               f'text-anchor="start">Index</text>')

    expectation, counter = vintage.expectation, vintage.counterfactual
    if expectation is not None:
        band = [(p.year, p.high) for p in expectation.points
                if p.high is not None]
        band += [(p.year, p.low) for p in reversed(expectation.points)
                 if p.low is not None]
        if len(band) >= 4:
            pts = " ".join(f"{scale.x(a):.1f},{scale.y(b):.1f}"
                           for a, b in band)
            out.append(f'<polygon class="band" points="{pts}"/>')
    # THE ACTUAL LINE IS SPLIT AT THE WALL.
    #
    # Solid up to the selected date; a faint dotted continuation after it.
    # Drawing one unbroken line would put the outcome and the record at
    # the time in the same visual weight, which is precisely the hindsight
    # this page exists to separate — the reader could not see which part
    # of the line the expectation was allowed to know about.
    before = [(p.year, p.value) for p in actual.points
              if p.year <= vintage.year]
    after = [(p.year, p.value) for p in actual.points
             if p.year >= vintage.year]
    out.append(f'<path class="ln-actual" d="{_path(scale, before)}"/>')
    if len(after) > 1:
        out.append(f'<path class="ln-actual-after" '
                   f'd="{_path(scale, after)}"/>')
    for year, value in before:
        out.append(_marker(scale, year, value, "circle", "mk-actual"))
    if expectation is not None:
        out.append(f'<path class="ln-expect" d="'
                   f'{_path(scale, [(p.year, p.value) for p in expectation.points])}"/>')
        for point in expectation.points:
            out.append(_marker(scale, point.year, point.value, "diamond",
                               "mk-expect"))
    if counter is not None:
        out.append(f'<path class="ln-counter" d="'
                   f'{_path(scale, [(p.year, p.value) for p in counter.points])}"/>')
        for point in counter.points:
            out.append(_marker(scale, point.year, point.value, "square",
                               "mk-counter"))
    x = scale.x(vintage.year)
    out.append(f'<line class="nowline" x1="{x:.1f}" y1="{_PAD_T}" '
               f'x2="{x:.1f}" y2="{_H - _PAD_B}"/>')
    anchor = "start" if x < _W * 0.62 else "end"
    offset = 7 if anchor == "start" else -7
    out.append(f'<text class="nowtext" x="{x + offset:.1f}" '
               f'y="{_PAD_T + 13:.0f}" text-anchor="{anchor}">'
               f'{vintage.year} — decision point</text>')
    out.append('</svg>')
    return "".join(out)


_LEGEND_SWATCH = {
    HS.ACTUAL: ('<svg viewBox="0 0 34 14" aria-hidden="true">'
                '<line x1="1" y1="7" x2="33" y2="7" stroke="var(--c-actual)" '
                'stroke-width="3.4" stroke-linecap="round"/>'
                '<circle cx="17" cy="7" r="4.2" fill="var(--c-actual)"/></svg>'),
    HS.EXPECTATION: ('<svg viewBox="0 0 34 14" aria-hidden="true">'
                     '<line x1="1" y1="7" x2="33" y2="7" '
                     'stroke="var(--c-expect)" stroke-width="3" '
                     'stroke-dasharray="9 5" stroke-linecap="round"/>'
                     '<polygon points="17,2 22,7 17,12 12,7" '
                     'fill="var(--c-expect)"/></svg>'),
    HS.COUNTERFACTUAL: ('<svg viewBox="0 0 34 14" aria-hidden="true">'
                        '<line x1="1" y1="7" x2="33" y2="7" '
                        'stroke="var(--c-counter)" stroke-width="3" '
                        'stroke-dasharray="2 5" stroke-linecap="round"/>'
                        '<rect x="13" y="3" width="8" height="8" '
                        'fill="var(--c-counter)"/></svg>'),
}


def legend(sim: HS.Simulation, vintage: Optional[HS.SimVintage] = None) -> str:
    """The legend, which is where the three epistemic states are declared."""
    vintage = vintage if vintage is not None else sim.vintages[0]
    rows = [
        (HS.ACTUAL, "Actual path", R.OBSERVED,
         "What the company filed. Solid up to the selected year; faint dots "
         "after it, because that part had not happened yet."),
    ]
    if vintage.expectation is not None:
        rows.append((HS.EXPECTATION, "Market expectation", R.MODELED,
                     "What the record published by that date implied, with a "
                     "band for the company's own volatility. Modelled here — "
                     "not a retrieved analyst consensus."))
    if vintage.counterfactual is not None:
        rows.append((HS.COUNTERFACTUAL, "Better strategy", R.COUNTERFACTUAL,
                     "Where a named alternative available on the same "
                     "information plausibly led. A bounded counterfactual, "
                     "never a record of what happened."))
    items = "".join(
        f'<li>{_LEGEND_SWATCH[kind]}<span><b>{_e(title)}'
        f'<span class="basis">{_e(R.LABEL[basis])}</span></b>'
        f'<span class="m">{_e(meaning)}</span></span></li>'
        for kind, title, basis, meaning in rows)
    return f'<ul class="hsim-legend">{items}</ul>'


def text_alternative(sim: HS.Simulation, vintage: HS.SimVintage) -> str:
    """The SVG's accessible name: the three series AND what they show.

    Not "chart of the strategic value index" — that names the decoration and
    withholds the finding. A reader using a screen reader gets the comparison
    the sighted reader gets from the shape of the lines.
    """
    names = ["the actual filed path, observed"]
    if vintage.expectation is not None:
        names.append("a modelled market expectation from that date forward")
    if vintage.counterfactual is not None:
        names.append("a counterfactual better-strategy path")
    span = (f"{sim.index.points[0].year} to {sim.index.points[-1].year}"
            if sim.index.points else "the filed period")
    outcome = ""
    card = next((c for c in vintage.cards if c.key == "happened"), None)
    if card is not None:
        outcome = " " + card.body.split(". This card")[0] + "."
    return (f"Line chart of {sim.company}'s strategic value index, {span}, "
            f"rewound to {vintage.year}: {_join(names)}.{outcome} The same "
            f"figures are in the table below the chart.")


def data_table(sim: HS.Simulation, vintage: HS.SimVintage) -> str:
    """§86. The chart's numbers, for anyone who cannot see the chart."""
    years = sorted({p.year for p in vintage.actual.points}
                   | {p.year for p in (vintage.expectation.points
                                       if vintage.expectation else ())}
                   | {p.year for p in (vintage.counterfactual.points
                                       if vintage.counterfactual else ())})
    actual = {p.year: p.value for p in vintage.actual.points}
    expect = {p.year: p.value for p in (vintage.expectation.points
                                        if vintage.expectation else ())}
    counter = {p.year: p.value for p in (vintage.counterfactual.points
                                         if vintage.counterfactual else ())}

    def cell(table, year):
        value = table.get(year)
        return "—" if value is None else f"{value:.0f}"

    rows = "".join(
        f'<tr><th scope="row">{year}</th><td>{cell(actual, year)}</td>'
        f'<td>{cell(expect, year)}</td><td>{cell(counter, year)}</td></tr>'
        for year in years)
    return (
        f'<details class="hsim-alt"><summary>The same figures as a table'
        f'</summary><div class="scroll"><table><caption class="sr-only">'
        f'{_e(sim.company)} strategic value index by year</caption><thead><tr>'
        f'<th scope="col">Year</th><th scope="col">Actual (observed)</th>'
        f'<th scope="col">Expectation (modelled)</th>'
        f'<th scope="col">Better strategy (counterfactual)</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div></details>')


def cards(vintage: HS.SimVintage) -> str:
    """§28. The date panel — compact, and never a wall of text."""
    style = {R.OBSERVED: "obs", R.MODELED: "mod", R.COUNTERFACTUAL: "cf"}
    items = "".join(
        f'<article class="{style.get(card.basis, "obs")}">'
        f'<h3>{_e(card.title)}<span class="basis">{_e(card.label)}</span></h3>'
        f'<p>{_e(card.body)}</p></article>'
        for card in vintage.cards)
    return f'<div class="hcards">{items}</div>'


def drivers(vintage: HS.SimVintage) -> str:
    """What moved the two modelled lines — never hidden behind the chart."""
    blocks = []
    for path in (vintage.expectation, vintage.counterfactual):
        if path is None or not path.drivers:
            continue
        items = "".join(f"<li>{_e(driver)}</li>" for driver in path.drivers)
        blocks.append(
            f'<p class="hsim-axis-note"><strong>{_e(path.title)}</strong> — '
            f'{_e(path.label)}, built from {_e(path.derivation)}.</p>'
            f'<ul class="drivers">{items}</ul>')
    return "".join(blocks)


def rail_css(count: int) -> str:
    """One rule per date: check radio N, show overlay N and mark tab N."""
    rules = ['.hsim .vg{display:none}']
    for index in range(count):
        rules.append(f'.hrewind input#hv{index}:checked ~ .hrail '
                     f'label[for="hv{index}"]{{border-color:var(--accent);'
                     f'color:var(--fg);background:var(--soft)}}')
        rules.append(f'.hrewind input#hv{index}:checked ~ .hsim .vg{index}'
                     f'{{display:block}}')
        rules.append(f'.hrewind input#hv{index}:checked ~ .hpanel{index}'
                     f'{{display:block}}')
        rules.append(f'.hrewind input#hv{index}:focus-visible ~ .hrail '
                     f'label[for="hv{index}"]{{outline:2px solid '
                     f'var(--accent);outline-offset:2px}}')
    return "".join(rules)


def _join(items) -> str:
    items = [i for i in (items or ()) if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]
