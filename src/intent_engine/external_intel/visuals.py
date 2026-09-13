"""Charts, drawn only from observations that exist.

WHY INLINE SVG AND NOT A CHART LIBRARY
---------------------------------------
The deployed service installs from pyproject, and a charting dependency that
is absent in production renders a broken page rather than a missing one. SVG
in the response body has no runtime, no CDN (the pages must work offline and
under a strict CSP), scales at every viewport, and prints. The cost is that
every axis is computed here, which is also the benefit: there is no library
default that could invent a tick the data does not support.

THE RULES EVERY CHART OBEYS
----------------------------
1. NO CHART WITHOUT ENOUGH REAL OBSERVATIONS. Below `MIN_POINTS` the function
   returns "" and the surface prints the text instead. Three points joined by
   a line read as a trend; they are not one.
2. NO FABRICATED AXIS VALUES. Ticks come from the data's own range. A chart
   whose axis was chosen to make a line look steep is a lie told with true
   numbers.
3. EVERY CHART CARRIES ITS CONCLUSION. The headline states what the chart
   shows, not what it plots -- "the shares trail the market over the year"
   rather than "PLTR vs SPY". A reader who takes only the headline should not
   be misled by it.
4. EVERY CHART HAS A TEXT ALTERNATIVE. `<title>`, `<desc>` and `role="img"`,
   because these pages are read by screen readers and printed to PDF.
5. SOURCE AND FRESHNESS ARE IN THE FIGURE. A chart that travels without them
   -- screenshotted into a deck, say -- must still say where it came from and
   how old it is.
"""
from __future__ import annotations

import re

from html import escape as _e
from typing import List, Optional, Sequence

#: Below this a line chart is a shape, not a trend.
MIN_POINTS = 12

#: A viewBox with no fixed width, so the figure scales to its column at every
#: breakpoint rather than forcing a horizontal scroll on a phone.
_W, _H = 640, 240
_PAD_L, _PAD_R, _PAD_T, _PAD_B = 44, 12, 14, 30

CHART_CSS = """
<style>
figure.xchart{margin:.9rem 0 0;padding:0}
figure.xchart svg{width:100%;height:auto;display:block;overflow:visible}
figure.xchart .xc-hd{font-size:.95rem;font-weight:650;margin:0 0 .15rem;
line-height:1.35}
figure.xchart figcaption{font-size:.82rem;color:var(--muted);margin:.4rem 0 0}
figure.xchart .xc-src{font-size:.76rem;color:var(--muted);margin:.25rem 0 0}
.xc-grid{stroke:var(--line);stroke-width:1}
.xc-axis{fill:var(--muted);font-size:11px}
.xc-a{stroke:var(--accent);stroke-width:2.25;fill:none;
stroke-linejoin:round;stroke-linecap:round}
.xc-b{stroke:var(--muted);stroke-width:1.5;fill:none;stroke-dasharray:4 3}
.xc-key{font-size:11px;fill:var(--ink)}
.xc-bar{fill:var(--accent)}
.xc-bar-neg{fill:var(--warn)}
.xc-lbl{font-size:11px;fill:var(--ink)}
.xc-zero{stroke:var(--ink);stroke-width:1;opacity:.45}
@media print{figure.xchart{break-inside:avoid}}
</style>
"""


def _scale(values: Sequence[float], lo: float, hi: float,
           out_lo: float, out_hi: float) -> List[float]:
    span = (hi - lo) or 1.0
    return [out_lo + (v - lo) / span * (out_hi - out_lo) for v in values]


def _figure(body: str, *, headline: str, so_what: str, decision: str,
            source: str, freshness: str, alt: str, chart_id: str) -> str:
    """The wrapper every chart shares, so none can ship without its meaning."""
    caption = " ".join(x for x in (so_what, decision) if x)
    stamp = " · ".join(x for x in (source, freshness) if x)
    return (
        f'<figure class="xchart">'
        f'<p class="xc-hd">{_e(headline)}</p>'
        f'<svg viewBox="0 0 {_W} {_H}" role="img" '
        f'aria-labelledby="{chart_id}-t {chart_id}-d" '
        f'preserveAspectRatio="xMidYMid meet">'
        f'<title id="{chart_id}-t">{_e(headline)}</title>'
        f'<desc id="{chart_id}-d">{_e(alt)}</desc>'
        f'{body}</svg>'
        f'<figcaption>{_e(caption)}</figcaption>'
        f'<p class="xc-src">{_e(stamp)}</p>'
        f'</figure>')


def market_trajectory(payload: dict, *, headline: str, so_what: str,
                      decision: str, source: str, freshness: str,
                      alt: str, chart_id: str = "xc1") -> str:
    """Company against benchmark, both indexed to 100 on a shared session."""
    series = (payload or {}).get("series") or {}
    dates = series.get("dates") or []
    company = series.get("company_indexed") or []
    bench = series.get("benchmark_indexed") or []
    if len(dates) < MIN_POINTS or len(company) != len(dates) \
            or len(bench) != len(dates):
        return ""

    lo = min(min(company), min(bench))
    hi = max(max(company), max(bench))
    # Pad the range so neither line sits on the frame, but never beyond what
    # the data supports -- the ticks below are real values from this range.
    pad = (hi - lo) * 0.08 or 1.0
    lo, hi = lo - pad, hi + pad

    xs = _scale(range(len(dates)), 0, len(dates) - 1, _PAD_L, _W - _PAD_R)
    ys_a = _scale(company, lo, hi, _H - _PAD_B, _PAD_T)
    ys_b = _scale(bench, lo, hi, _H - _PAD_B, _PAD_T)

    def path(ys):
        return " ".join(f"{'M' if i == 0 else 'L'}{x:.1f} {y:.1f}"
                        for i, (x, y) in enumerate(zip(xs, ys)))

    grid = []
    for tick in (lo, (lo + hi) / 2, hi):
        y = _scale([tick], lo, hi, _H - _PAD_B, _PAD_T)[0]
        grid.append(f'<line class="xc-grid" x1="{_PAD_L}" y1="{y:.1f}" '
                    f'x2="{_W - _PAD_R}" y2="{y:.1f}"/>')
        grid.append(f'<text class="xc-axis" x="{_PAD_L - 6}" y="{y + 4:.1f}" '
                    f'text-anchor="end">{tick:.0f}</text>')
    grid.append(f'<text class="xc-axis" x="{_PAD_L}" y="{_H - 8}">'
                f'{_e(dates[0])}</text>')
    grid.append(f'<text class="xc-axis" x="{_W - _PAD_R}" y="{_H - 8}" '
                f'text-anchor="end">{_e(dates[-1])}</text>')

    key = (f'<line class="xc-a" x1="{_W - 172}" y1="{_PAD_T}" '
           f'x2="{_W - 152}" y2="{_PAD_T}"/>'
           f'<text class="xc-key" x="{_W - 147}" y="{_PAD_T + 4}">'
           f'This company</text>'
           f'<line class="xc-b" x1="{_W - 172}" y1="{_PAD_T + 15}" '
           f'x2="{_W - 152}" y2="{_PAD_T + 15}"/>'
           f'<text class="xc-key" x="{_W - 147}" y="{_PAD_T + 19}">'
           f'Benchmark</text>')

    body = ("".join(grid)
            + f'<path class="xc-b" d="{path(ys_b)}"/>'
            + f'<path class="xc-a" d="{path(ys_a)}"/>' + key)
    return _figure(body, headline=headline, so_what=so_what,
                   decision=decision, source=source, freshness=freshness,
                   alt=alt, chart_id=chart_id)


def risk_context(payload: dict, *, headline: str, so_what: str,
                 decision: str, source: str, freshness: str, alt: str,
                 chart_id: str = "xc2") -> str:
    """Drawdown, distance from high and volatility as one comparable bar set.

    All three are percentages, so they share an axis honestly. Mixing units on
    one axis is the chart error that makes an unremarkable number look alarming.
    """
    rows = []
    dd = (payload or {}).get("period_drawdown") or {}
    high = (payload or {}).get("distance_from_period_high") or {}
    vol = (payload or {}).get("annualized_volatility") or {}
    if dd.get("value") is not None:
        rows.append(("Deepest fall from peak", dd["value"]))
    if high.get("value") is not None:
        rows.append(("Below the period high", high["value"]))
    if vol.get("value") is not None:
        rows.append(("Annualised volatility", vol["value"]))
    if len(rows) < 2:
        return ""

    limit = max(abs(v) for _, v in rows) or 1.0
    zero_x = _PAD_L + 118
    span = _W - _PAD_R - zero_x - 46
    height, gap = 26, 14
    top = _PAD_T + 6
    body = [f'<line class="xc-zero" x1="{zero_x}" y1="{top - 4}" '
            f'x2="{zero_x}" y2="{top + len(rows) * (height + gap)}"/>']
    for i, (label, value) in enumerate(rows):
        y = top + i * (height + gap)
        width = abs(value) / limit * span
        x = zero_x if value >= 0 else zero_x - width
        css = "xc-bar" if value >= 0 else "xc-bar-neg"
        body.append(f'<text class="xc-lbl" x="{zero_x - 10}" '
                    f'y="{y + height * 0.68:.0f}" text-anchor="end">'
                    f'{_e(label)}</text>')
        body.append(f'<rect class="{css}" x="{x:.1f}" y="{y}" '
                    f'width="{width:.1f}" height="{height}" rx="3"/>')
        body.append(f'<text class="xc-lbl" x="{x + width + 6:.1f}" '
                    f'y="{y + height * 0.68:.0f}">{value:+.0f}%</text>')
    return _figure("".join(body), headline=headline, so_what=so_what,
                   decision=decision, source=source, freshness=freshness,
                   alt=alt, chart_id=chart_id)


def macro_exposure(factor: dict, *, headline: str, so_what: str,
                   decision: str, source: str, freshness: str, alt: str,
                   chart_id: str = "xc3") -> str:
    """Factor → mechanism → decision, as a chain rather than a quadrant.

    Deliberately not a positioning quadrant. A quadrant needs two measured
    axes, and there are none here -- an exposure is a chain of reasoning, so
    the picture is the chain.
    """
    steps = [("Factor", f"{factor.get('factor', '')}: "
                        f"{factor.get('change_text', '')}"),
             ("Reaches this company by",
              factor.get("company_exposure_mechanism", "")),
             ("Which changes", factor.get("business_consequence", "")),
             ("Decision", factor.get("affected_kpi_or_decision", ""))]
    steps = [(k, v) for k, v in steps if v]
    if len(steps) < 3:
        return ""

    # THE CHAIN IS THE ARGUMENT, SO IT HAS TO BE READABLE (§23, §30).
    #
    # Each step used to be clipped to 78 characters with an ellipsis, and
    # every step of every transmission chain is longer than that -- so the
    # one visual that carries the macro reasoning printed four sentences that
    # all trailed off. SVG does not wrap, so the wrapping is done here: two
    # lines per step, and the box grows to fit them.
    # THREE LINES, NOT TWO. A transmission step is a full causal sentence and
    # measured live they run 140-190 characters, so a two-line box at 74
    # ellipsized every one of the four steps -- the single visual that carries
    # the macro reasoning, trailing off four times.
    lines = [(label, _lines(text, 74, 3)) for label, text in steps]
    height = 46 + 17 * max(len(v) for _k, v in lines)
    total = len(lines) * height + 10
    body = []
    for i, (label, rows) in enumerate(lines):
        y = 6 + i * height
        body.append(f'<rect x="{_PAD_L}" y="{y}" width="{_W - _PAD_L - 12}" '
                    f'height="{height - 14}" rx="6" fill="var(--soft)" '
                    f'stroke="var(--line)"/>')
        body.append(f'<text class="xc-axis" x="{_PAD_L + 10}" y="{y + 16}">'
                    f'{_e(label.upper())}</text>')
        for j, row in enumerate(rows):
            body.append(f'<text class="xc-lbl" x="{_PAD_L + 10}" '
                        f'y="{y + 33 + j * 16}">{_e(row)}</text>')
        if i < len(lines) - 1:
            mid = _PAD_L + (_W - _PAD_L) / 2
            body.append(f'<path d="M{mid} {y + height - 13} L{mid} '
                        f'{y + height - 3}" stroke="var(--muted)" '
                        f'stroke-width="1.5"/>')
    svg = (f'<figure class="xchart"><p class="xc-hd">{_e(headline)}</p>'
           f'<svg viewBox="0 0 {_W} {total}" role="img" '
           f'aria-labelledby="{chart_id}-t {chart_id}-d" '
           f'preserveAspectRatio="xMidYMid meet">'
           f'<title id="{chart_id}-t">{_e(headline)}</title>'
           f'<desc id="{chart_id}-d">{_e(alt)}</desc>'
           f'{"".join(body)}</svg>'
           f'<figcaption>{_e(" ".join(x for x in (so_what, decision) if x))}'
           f'</figcaption>'
           f'<p class="xc-src">'
           f'{_e(" · ".join(x for x in (source, freshness) if x))}</p>'
           f'</figure>')
    return svg


def _wrap(text: str, limit: int) -> str:
    """One line, truncated at a word. SVG text does not wrap on its own, and
    a second tspan line would collide with the next box."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def _lines(text: str, width: int, limit: int) -> list:
    """`text` broken into at most `limit` lines of about `width` characters.

    An ellipsis appears only when the whole passage genuinely does not fit in
    the space allowed -- which, at two lines of 74, it almost never does.
    """
    words = " ".join(str(text or "").split()).split()
    rows, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
            continue
        rows.append(current)
        current = word
        if len(rows) == limit:
            break
    if current and len(rows) < limit:
        rows.append(current)
    if not rows:
        return [""]
    consumed = len(" ".join(rows).split())
    if consumed < len(words):
        rows[-1] = rows[-1].rstrip(",;: ") + "…"
    return rows


def competitor_positioning(competitors: Sequence[dict], *, headline: str,
                           so_what: str, decision: str, source: str,
                           freshness: str, alt: str,
                           chart_id: str = "xc4") -> str:
    """Alternatives by the KIND of choice they represent, not by rank.

    Ranking would need a measure of strength this product does not have, and
    inventing one is the decorative-quadrant failure. What IS known is what
    kind of alternative each is, which is the thing that changes how a founder
    sells against it.
    """
    rows = [c for c in (competitors or ()) if c.get("name")]
    if len(rows) < 2:
        return ""
    height, gap = 34, 10
    total = len(rows) * (height + gap) + 20
    body = []
    for i, row in enumerate(rows[:6]):
        y = 8 + i * (height + gap)
        body.append(f'<rect x="{_PAD_L}" y="{y}" width="{_W - _PAD_L - 12}" '
                    f'height="{height}" rx="6" fill="var(--soft)" '
                    f'stroke="var(--line)"/>')
        body.append(f'<text class="xc-lbl" x="{_PAD_L + 10}" y="{y + 15}" '
                    f'font-weight="650">{_e(_wrap(row["name"], 34))}</text>')
        body.append(f'<text class="xc-axis" x="{_PAD_L + 10}" y="{y + 28}">'
                    f'{_e(_wrap(row.get("relationship_meaning", ""), 74))}'
                    f'</text>')
    svg = (f'<figure class="xchart"><p class="xc-hd">{_e(headline)}</p>'
           f'<svg viewBox="0 0 {_W} {total}" role="img" '
           f'aria-labelledby="{chart_id}-t {chart_id}-d" '
           f'preserveAspectRatio="xMidYMid meet">'
           f'<title id="{chart_id}-t">{_e(headline)}</title>'
           f'<desc id="{chart_id}-d">{_e(alt)}</desc>'
           f'{"".join(body)}</svg>'
           f'<figcaption>{_e(" ".join(x for x in (so_what, decision) if x))}'
           f'</figcaption>'
           f'<p class="xc-src">'
           f'{_e(" · ".join(x for x in (source, freshness) if x))}</p>'
           f'</figure>')
    return svg


def render(block, context) -> str:
    """The chart for one presenter block, or "" when there is not enough data.

    A block naming a chart it cannot draw renders as prose, which is why every
    block carries a text alternative whether or not a chart appears.
    """
    if not block.chart:
        return ""
    payload = (context.market.payload or {}) if context.has_market else {}
    shared = dict(headline=_headline(block), so_what=block.so_what,
                  decision=block.decision, source=block.source,
                  freshness=block.freshness,
                  alt=block.text_alternative or block.fact,
                  chart_id=f"xc-{block.key}")
    if block.chart == "market_trajectory":
        return market_trajectory(payload, **shared)
    if block.chart == "market_risk":
        return risk_context(payload, **shared)
    if block.chart.startswith("macro_exposure_"):
        key = block.chart[len("macro_exposure_"):]
        factor = next((f.as_dict() for f in context.macro
                       if f.factor_key == key), None)
        return macro_exposure(factor, **shared) if factor else ""
    if block.chart == "competitor_positioning":
        from .competitor_contract import corroborating
        return competitor_positioning(
            [c.as_dict() for c in corroborating(context.competitors)],
            **shared)
    return ""  # pragma: no cover


def _headline(block) -> str:
    """The chart's conclusion, taken from the block's own fact sentence.

    Not the block title: "Market expectations" over a chart tells a reader
    what topic they are looking at, which they can already see. The first
    sentence of the fact is the conclusion.

    AND NOT THE SENTENCE DIRECTLY ABOVE IT. The block's `fact` is rendered as
    the passage prose, and the chart sits immediately under that prose, so
    taking the FIRST sentence printed "The alternatives this company's own
    evidence names are Alstom SA, America Leasing, BNP Paribas Leasing
    Solutions, Baker Hughes Co." twice in a row, five lines apart, on the
    full analysis. Where the fact has a second sentence, that is the one the
    chart carries -- it is the conclusion the list was building to, which is
    also the better caption.
    """
    fact = (block.fact or "").strip()
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", fact) if p.strip()]
    if len(parts) >= 2:
        return parts[1]
    return parts[0] if parts else fact
