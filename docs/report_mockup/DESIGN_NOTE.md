# Founder-readable regime report — design note (mockup for approval)

*2026-07-19 overnight loop. Mockup:
`weekly_regime_report_founder_mockup.html`, built 1:1 from the real
2026-07-17 production report (`reports/weekly_regime_report_2026-07-17.txt`).
Every number, probability, date, and "unavailable" in the mockup is from
that run — nothing added or adjusted for presentation. NO pipeline wiring
has been done; that follows your approval.*

## Recommended format: single-file HTML (print-to-PDF built in)

- **Why HTML over Markdown**: honesty markers need visual weight — badges,
  cards, provenance columns. Markdown renders them as just more text, which
  is exactly how caveats get buried. HTML makes UNAVAILABLE amber and
  visible, makes "none matched" a featured card, and still opens anywhere.
- **Why HTML over direct PDF**: zero new dependencies (a PDF library is a
  new dependency = PARK per house rules); the browser's print-to-PDF
  produces the attachment/lead-magnet version on demand; HTML is also the
  natural email/web form later.
- **Single file, inline CSS**: cron-writable next to the existing .txt
  (`weekly_regime_report_<date>.html`), no build step, no assets.

## Honesty markers as designed features (the differentiator, per instruction)

1. **UNAVAILABLE badges** (amber): each missing series is a visible,
   labeled design element with its source name still shown — "no verified
   data, no claim" reads as method, not failure.
2. **"None matched — and that's the finding" card**: correct silence is
   presented as the product's spine, with one plain-language line on WHY
   (deterministic matching, gate-verified restraint).
3. **DATA GAPS section always renders**: "no gaps detected" when clean
   (true for this run), loud amber listing when not — mirrors the
   code-level `render_data_gaps_section` behavior.
4. **Track-record card leads with "0 resolved — no accuracy claimed"**:
   the ≥30-resolved wall and baseline comparison are stated as standing
   method. This line only changes when the ledger actually resolves.
5. **Provenance column** on every regime row (source + observation date).

## Claim-tracing audit (business-phase wall)

Every sentence in the mockup traces to: the 2026-07-17 report text, the
gate-passed extraction/matcher behavior (reliability gate, v2 PASS
2026-07-18), the ledger's append-only/code-graded design (M5/M6), or the
A-M5 ≥30-resolved rule. Zero predictive-accuracy claims present.

## Wiring plan (AFTER your approval — not built)

A renderer `scripts/render_founder_report.py` consuming the same run data
the .txt renderer uses, emitting the HTML next to it; weekly cron line
gains one output. Bars: golden-file test from a fixture run; language
walls applied to rendered HTML text; "unavailable"/gaps/none-matched
rendering each asserted; suite green. Budget: 0 live calls (pure render).
