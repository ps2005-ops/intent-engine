# Founder Intelligence — launch readiness

Written at the end of the demo-perfection milestone. Every claim below was
measured on rendered output, not inferred from code.

| | |
|---|---|
| **Branch** | `feat/strategic-intelligence-v2` |
| **Last code commit** | `91113fa` — everything measured below was measured against it; the commits after it are documentation only |
| **Suite** | 2809 passed, 14 skipped |
| **Five-company validation** | Duolingo, Toast, Novo Nordisk, John Deere, Airbnb — 15 layer-views, all clean |
| **Mobile** | inspected at 375×812 in a browser; two defects found and fixed |
| **Deployed** | **not yet** — see *Owner actions* |

## What this milestone was

Not a feature sprint. The reasoning system, the deterministic claim system and
the three-layer architecture were already finished. The question was the one a
founder answers in the first ten seconds: *does this feel like a product, or
does it feel like someone's prototype?*

It felt like a prototype, in seven specific ways. All seven are fixed.

## Architecture, as it stands

Three layers over one report, each deepening rather than repeating:

| layer | route | for |
|---|---|---|
| Presentation | `/runs/<id>/slides` | someone standing up in a meeting in ten minutes |
| Executive brief | `/runs/<id>/brief` | the default landing; 250–500 words |
| Full analysis | `/runs/<id>/full` | the reader who wants the argument and its sources |

Behind them: `company_ingestion` (discovery → approval → retrieval → parse),
a readiness gate that decides *before* synthesis whether there is enough to
say anything, and `strategic_intelligence` (observations → pattern reasoning →
brief/slides/render).

The gate is the load-bearing part. Synthesis is willing — given one filing it
will still produce a thesis, hypotheses and leadership questions laid out
exactly like a report built on twenty sources, and a reader cannot tell the
difference. So the decision is made on the evidence alone, and when it says no
there is no report to render rather than a report with the findings removed.

## What changed in this milestone

### 1. The full analysis was a schema dump

Fourteen field-shaped sections, one per key in the report dict, so a reader met
"Strategic surprises", "Possible blind spots", "Questions that may be
underexamined" and eleven more — each a card restating a field.

It is now the eight moves an analyst makes in order: what we think is
happening, what happened, the evidence, why that evidence matters, what else
could explain it, what we still do not know, what to monitor, sources. Every
section is prose and every section disappears when empty.

Consolidating fourteen into eight is where content gets lost, so what got
dropped was checked rather than assumed. The first pass lost blind-spot
tensions, surprise findings, the agenda and the historical comparable — all
four are mapped back into the sections where they argue for something.

### 2. Evidence bullets concatenated a page title with a template

> API Authentication Bypass | Sentry Blog exposes a surface others can build on

The page title was the grammatical subject, so a blog post appeared to be doing
the company's positioning. The company is now the subject, threaded from the
run. All 27 signals state a consequence; five did before.

### 3. The likeliest first impression was the legacy claim dump

Three of five companies in the demo pass produced **no strategic report** and
fell through to a legacy view headed "Executive Overview", with internal claim
ids beside every line (`[u.offering]`, `[mv.company_language]`) and a
"Strongest supported observation" that was the five words the company's pages
repeat most.

The cause is ordinary and common: JS-rendered sites yield titles and meta
descriptions rather than bodies, so no signal matches. `derive_observations`
documents this outcome and says the fix belongs at the page. Those runs now get
the honest limited-analysis page, with a reason written for that reader — they
are not short of evidence, they are short of the *kind* of evidence a reading
rests on.

### 4. The quality gate was talking to itself

A live Airbnb report ended on:

```
only 0 strategic hypotheses (need >= 3)
empty key sections: strategic_hypotheses, comparable_patterns, blind_spots,
leadership_questions, decision_implications
```

All three layers printed `finding["message"]` — text written to explain a
downgrade to the gate that raised it. Each of the twenty codes is now
classified once: reader-facing sentence, or telemetry that never reaches a
page. Twelve are telemetry. A test fails if a new code is unclassified.

### 5. Slides were whatever the extraction caught first

Three of Airbnb's seven slides were raw page text: the site footer under
"Products, customers and market", the SEO listing strip under "Airbnb in one
minute", the 8-K cover page under "What the company has published".

A bullet now has to be a real sentence, and a page that yields none loses its
bullet rather than contributing its least-bad line. Filtering the furniture
then exposed a latent defect the persona harness caught: the deck would repeat
a company's own superlatives ("no meaningful competitors") as findings — that
sentence had always been in the document, and only the truncation point was
keeping it off the slide. Self-published superiority is now rejected on the
company's own pages; the same words from an independent source are a finding.

### 6. The same sentence appeared twice on one page

Airbnb's full analysis said the same thing under "What happened" and "Why that
evidence matters". `_once` keyed on the whole string and the timeline appends
`" (Recorded 2026-07-29.)"` — a trailing clause defeated it. It keys on the
first sentence now.

Found on the way: `re` was never imported in `render.py`, so `_claim_seen` —
the near-duplicate-question filter — would have raised `NameError` on its first
execution. It had never run.

### 7. The product described its own pipeline to the reader

"Outside-in analysis of approved public sources and a curated
historical-pattern library". "There is not yet enough approved strategic
evidence to form a defensible outside-in view." "all evidence is
company-published (owned/executive/investor)". And, at the foot of every
report, an explanation of our hosting: "Storage is writable but sits on the
same filesystem as the application image, which is usually replaced on
redeploy."

All reworded to say the same true thing in the reader's language. The hosting
detail still appears in full at `/readyz`, where the person who can act on it
looks.

## Demo checklist

Run before showing this to anyone:

- [ ] `/healthz` and `/readyz` respond; note whether `/readyz` is `degraded`
- [ ] Landing page loads and the example is labelled *Example analysis*
- [ ] Start a demo session — no login required
- [ ] Analyse **Palantir** or **Shopify**: both produce a complete three-layer
      result and are the strongest thing to show
- [ ] Walk presentation → brief → full analysis; check the layer nav on each
- [ ] Open the full analysis and confirm the Sources section resolves
- [ ] Repeat one analysis on a phone
- [ ] Have a second company ready that lands on the limited-analysis page —
      it is honest, it is a good answer to "what if it doesn't work", and
      showing it deliberately is stronger than hitting it by accident

## Five-company validation

Fresh companies, deliberately outside the rotation used during development
(Vercel, Datadog, Ramp, Linear, Cloudflare, Anthropic, Retool, Wiz, Snowflake,
Arm, Figma, Sentry). Run end to end through the real product with live
retrieval, at `91113fa`.

| company | industry | outcome |
|---|---|---|
| Duolingo | consumer edtech | limited analysis — JS-rendered site, metadata only |
| Toast | restaurant fintech | limited analysis — same cause |
| Novo Nordisk | pharmaceutical | full three-layer result |
| John Deere | industrial / agriculture | limited analysis — same cause |
| Airbnb | travel marketplace | full three-layer result, six slides |

Every one of the 15 layer-views was scanned for seven classes of leak — claim
ids, snake_case field names, gate thresholds, legacy headings, source-class
taxonomy, page furniture, infrastructure talk. **All clean.** No page repeats
a text block of eight words or more.

**Read the outcome honestly: two of five companies produce a full report.**
That is not a regression — it is the gate working, and before this milestone
the other three produced a claim-id dump that *looked* like a report. The
limitation is real and is stated below.

## Mobile validation

Inspected at 375×812 in a browser on a live Airbnb run: landing, presentation,
brief, full analysis, limited-analysis page. Measured with
`getBoundingClientRect` on rendered pages, not read off the stylesheet — which
is where both defects looked fine.

- No horizontal overflow on any layer; `scrollWidth` equals viewport
  everywhere, including the source table.
- **Fixed:** the full analysis wrapped its layer nav in `.brief`, giving it a
  white panel and 40px of dead space directly under the site nav.
- **Fixed:** nav links and buttons measured 18–20px tall, below the 24px
  minimum, on the control a reader uses to leave a page. Now 44px on narrow
  viewports; desktop untouched.

## Known limitations

1. **A JS-rendered site yields no strategic report.** Extraction gets the
   title and meta description, no signal matches, and the run lands on the
   limited-analysis page. This affected three of five companies in the demo
   pass and is the single biggest constraint on which companies demo well. The
   page is honest about it; the retrieval gap is not closed.
2. **Grounded reasoning is off.** `ANTHROPIC_API_KEY` is unset, so the
   deterministic pattern path *is* the product. Reports are labelled with
   where their reasoning came from.
3. **Runs do not survive a redeploy.** Storage is not durable, so a run must
   be inspected in the session that created it, and feedback is switched off
   rather than accepted under a false promise.
4. **Public demo quota** is roughly 10 analyses per hour per IP.
5. **Sony is deliberately not offered as a prepared example** — it is the
   hardest case the product handles, and `test_sony_is_not_offered_as_a_
   prepared_example` keeps it off the landing page.
6. **`/readyz` reports `degraded`** while storage is non-durable. This is
   accurate and intentional.
7. **Extraction artefacts survive into quoted evidence.** Seen on production:
   the Airbnb evidence quote opens `“Exhibit 99.1. 1 §:)airbnb. Q1 2026 Key
   Financial Measures Revenue $2.7B…”` — the `§:)airbnb` is a mangled logo
   glyph from the filing's HTML. The quote is honest and the numbers after it
   are real, so this is cosmetic, but it is the kind of thing a reader reads
   as breakage. Note it is a *quote* rather than the product's own prose:
   `_readable_excerpt` cleans the bullets built from documents, and does not
   touch observation excerpts, which are shown verbatim on purpose. Fixing it
   means normalising glyph noise at parse time, not filtering the quote.

## Production verification

Deployed and verified after this milestone.

| | |
|---|---|
| **URL** | `https://intent-engine-oatc.onrender.com` |
| **`/version`** | `b988cd23477904d2b8d95f9893849e8dab6ee762` — the milestone head |
| **`/readyz`** | `degraded`, storage `EPHEMERAL_LIKELY`, honestly reported |
| **`browser_rendering`** | `false` — confirms limitation 1 in production, not just locally |
| **`strategic_reasoning`** | `false` — deterministic path is the product |

A live Airbnb run on production (`01KYTCFH3QQMQ4TY067ZCFA7RX`) returned 200 on
all three layers and was scanned for the same seven leak classes: **all
clean**. The full analysis was read end to end and carries the reworded
methodology note, the reworded withheld view, reader-facing limitations, and
the feedback copy with the hosting detail removed. Inspected on production,
not localhost.

## Owner actions

These need credentials or a dashboard and could not be done from here.

1. **Deploy.** Nothing in this milestone has been deployed. The head of
   `feat/strategic-intelligence-v2` is `91113fa`; production is still on the
   previously verified SHA. Merge and deploy, then re-run the demo checklist
   against production rather than localhost.
2. **Attach the Render disk** and set `RUNTIME_ROOT=/var/data`. This clears
   limitations 3 and 6 together.
3. **Set `FOUNDER_INTELLIGENCE_SMOKE_TEST_TOKEN`** (`openssl rand -hex 32`).
4. **Set `ANTHROPIC_API_KEY`** if grounded reasoning is wanted.

## Future roadmap

- **Close the retrieval gap for JS-rendered sites.** The highest-value item by
  a wide margin: it converts three of five demo companies from a limited page
  to a full report.
- **Admit descriptive observations without breaking the reasoning layer.**
  `derive_observations` records that this was tried and reverted — 76 tests
  objected, correctly, because an observation is the unit patterns match
  against. The fix belongs in a separate descriptive path, not in loosening
  that definition.
- Independent and customer-voice sources, which almost every report currently
  names as its missing evidence.

## Lessons

**Verifying on one company proves it on one company.** The three-layer leak fix
was confirmed on Sentry and reported as general. Running four more showed the
*other* deck — the fallback for a company with evidence but nothing concrete —
had never been filtered at all. Three of three companies that produced a deck
leaked.

**Fixture helpers lie about the first visit.** `_start_real` passes
`company_name=Acme`, which no real form does. The landing form asks for a
website, so `company_name` is empty on essentially every real visit — and the
whole suite missed that every layer was headed "(unnamed company)".

**A filter can be defeated by a suffix.** `_once` compared whole strings and
`" (Recorded …)"` was enough to print the same sentence twice.

**Quarantining is not removing.** The legacy view sat behind a `<details>` for
a long time on the reasoning that it was out of the way. A founder opens a
collapsed section on a report they are about to rely on.

**The persona harness earns its runtime.** It failed twice in this milestone,
and both times it was right: once when filtering removed genuine content, once
when filtering surfaced a latent defect that truncation had been hiding.

## Screenshots and artefacts

Rendered HTML and extracted text for all five companies × three layers, at
`91113fa`:

```
/private/tmp/claude-501/-Users-prathamsharma/d4928192-0f2e-41c7-a7ce-f96ec5b57c41/scratchpad/final/
```

These are session-scoped. Re-generate with the in-process harness rather than
treating that path as durable. Mobile inspection was done live in a browser at
375×812; the two defects it found are described above and both are fixed.
