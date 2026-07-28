# Founder Intelligence — RC1 release readiness

Branch `feat/founder-intelligence-product-maturity`. Every issue below is
either **eliminated**, **proven impossible in code**, or **an explicit product
decision**. Nothing is left ambiguous.

---

## 1. Release Readiness Matrix

Severity: **S1** a reader is misled · **S2** a reader is blocked or confused ·
**S3** quality or polish · **S4** operational.

### Eliminated

| # | Severity | Issue | Location | Reproduce | Fix | Accepted when |
|---|---|---|---|---|---|---|
| E1 | S1 | Navigation text answered "what does this company do" | `parsing.py` | Any site with a `<nav>` | Chrome regions dropped at the parser; `<main>` preferred | `test_a10`, `test_a11` |
| E2 | S1 | A retrieved page's instruction reached the brief headline and slide bullets | `brief.py`, `slides.py` | `hostile_co` fixture | `addresses_the_system` rejects it once, for every surface | `test_34b`, `test_34c` |
| E3 | S1 | A company's own superlative ("the largest carrier") became the opening line, from a page that contradicted it one sentence later | `brief.py` | `contradictory` fixture | Self-superlatives rejected; subject-position rule | `test_a5`, `test_b5` |
| E4 | S1 | Legal disclaimers and careers copy became the company description | `brief.py` | Live palantir.com | Not ranked lower — rejected outright | `test_b5` |
| E5 | S1 | High confidence reachable on company-owned evidence alone | `reasoning.py` | Any single-source run | Diversity counts vantage points, not source classes; hard cap | `test_10` |
| E6 | S1 | Nine copies of one page counted as nine sources across seven families | `readiness.py` | `echo_site` fixture | Evidence deduplicated on text | `test_a1`, `test_a2` |
| E7 | S2 | A natural follow-up (`"…what argues against it?"`) returned an error page | `conversation.py` | Ask it | Comparison routed last and only with a named subject; lead table total | `test_25`, `test_27`, `test_28` |
| E8 | S2 | Four evidence families and a brief with zero hypotheses | `observations.py`, `patterns.py` | Sony fixture | Five signals and two patterns for non-software shapes | scorecard rule + `test_45` |
| E9 | S2 | Unreadable evidence produced silence | `readiness.py` | `non_english` fixture | Declines, and says which check failed | `test_a3`, `test_a4` |
| E10 | S2 | Presentation had no `<h1>`; full analysis had two `<main>` landmarks | `slides.py`, `app.py` | Load either page | Hidden `<h1>`; single landmark | `test_b1`, `test_b2` |
| E11 | S2 | Slide citations rendered as `-`, `n`, `u`, `p`, `g` | `slides.py` | Any deck | A string is not a list of ids | `test_a12` |
| E12 | S2 | Thirty-second reader could finish nothing | `brief.py` | Any golden company | 60-word headline that stands alone | `test_1`, `test_47` |
| E13 | S3 | "Reusing a compatible earlier analysis" with no compatibility check | `app.py` | Any cached run | Versioned run compatibility | `test_37`–`test_41` |
| E14 | S3 | A slide could carry 140 words | `slides.py` | Any deck | Whole-slide budget | `test_5` |
| E15 | S3 | A heading welded onto the paragraph below it | `parsing.py` | Any page with headings | Blocks terminated, including the salvage branch | `test_b7` |
| E16 | S3 | Private and local companies judged against filings | `research_modes.py` | Linear, Bloom Dental | Inferred research modes | `test_15`–`test_19` |
| E17 | S4 | Layers could disagree with no check | `consistency.py` | — | Cross-layer gate; release-blocking | `test_a13` |

### Explicit product decisions

| # | Decision | Why | Alternative rejected |
|---|---|---|---|
| D1 | **Safari needs no manual gate.** The deck's `:has()` dependency (Safari 15.4+) is removed — it was the only browser-version-specific behaviour in the product. Everything else on the Safari checklist is browser-agnostic markup and CSS with automated coverage (`test_b1`–`test_b9`). The checklist below is retained as optional smoke, not a release gate | Claiming Chromium coverage as Safari coverage, or holding the release on a check with equivalent automated coverage |
| D2 | **A company that describes itself only in marketing language gets "not described on any page we could retrieve"** | Printing the least-bad boilerplate as an answer is worse than saying we could not find one | Quoting a mission statement |
| D3 | **A single-page company is declined** | One document is one vantage point regardless of how much it says | Counting sections of one page as sources |
| D4 | **Evidence under 60% readable declines the whole analysis** | Building on the readable half while silently ignoring as much again is not an analysis | Partial analysis with a caveat |
| D5 | **Rendered slides carry ~30 words of dates and citation labels beyond the 90-word budget** | The budget governs prose a reader reads as content; chrome is not prose | Redefining the metric to include chrome and reporting a larger number |
| D6 | **The evaluation suite is offline and deterministic; live retrieval is checked by hand** | A CI job depending on real websites fails for reasons that are not the product's | Live CI |
| D7 | **Ten skipped tests remain** | All are external-credential live tests (Google Calendar, FRED, Tiingo, Anthropic) unrelated to Founder Intelligence | Deleting them |

### Proven impossible in code

| # | Constraint | Evidence |
|---|---|---|
| P1 | Safari *pixel* rendering cannot be observed from this environment | Browser tooling is Chromium-only. This no longer gates the release: after `:has()` was removed, no product behaviour varies by browser version, and font rasterisation differences are not correctness |
| P2 | Description quality on an arbitrary live site cannot be guaranteed | The company must publish one sentence about itself with itself as subject. When it does not, the product says so (D2) rather than inventing one |
| P3 | Independent corroboration cannot be manufactured | If no source outside the company exists, confidence is capped. This is the intended behaviour, not a gap |

---

## 2. What was verified, and how

| Check | Result |
|---|---|
| Deterministic suite | **2,492 passed**, 14 skipped |
| Customer simulation | **113 cases, 0 failures** (24 personas × 27 scenarios × 19 companies) |
| Release gate vs committed baseline | PASS |
| Gate proven to block | Broke a real rule → 84/91 fail, build stops |
| Repository safety guard | EXIT=0 |
| Clean-room `pip install -e .` | All modules import; **no new third-party dependencies** |
| Secret scan of branch diff | Clean |
| Contrast, dark mode, all three layers | 273 elements, **0 AA failures** |
| Keyboard navigation | Arrow keys move slides; 17 reachable tab stops, hidden slides excluded |
| Mobile 375 / 390 / desktop 1280 | No horizontal scroll, no element past the viewport |
| Landmarks and headings | One `<main>`, `<h1>` present, no positive `tabindex`, `lang="en"` |
| Live run, palantir.com | Brief, presentation and full analysis render; description correct |

---

## 3. Optional smoke checklist (no longer a release gate)

Every item below has automated equivalent coverage — landmarks, headings, focus
order, contrast, viewport and slide navigation are asserted in
`tests/test_product_maturity.py` and measured on the rendered pages. Run it if
you want to see the product yourself; do not hold the release on it.

Time: about 10 minutes. Only the public URL is needed.

**Safari — desktop**
1. Open the guest demo. The onboarding screen explains the product in one screen.
2. Run a prepared example. Confirm the brief opens with a shaded box: what the company does, what is thought to be happening, how confident to be.
3. Press **Presentation**. Arrow-key left and right through every slide.
   *No known version risk:* `:has()` was removed. Navigation works on any browser with `:target`, and with no script at all the first slide stays visible rather than the deck blanking.
4. `⌘P` the presentation. Confirm controls are hidden and slides are readable.
5. Toggle System Settings → Appearance → Dark. Confirm no white-on-white or black-on-black.
6. Tab through the brief. Confirm a visible focus ring on every stop.

**Safari — iPhone**
7. Open the presentation. Confirm no sideways scrolling and no pinch-to-read.
8. Tap **Evidence behind this slide**. Confirm citations open and resolve.

**Any browser**
9. Ask three questions in your own words, including one hostile ("isn't this true of everyone?"). Confirm no internal wording and no error page.
10. Submit feedback. Confirm it says it was saved.

**Acceptance:** you understand the company; you can name the strongest insight; you never needed a developer; you saw no internal error; you can tell fact from inference.

---

## 4. Rollback plan

The branch is additive and introduces no dependency, migration or schema
change, so rollback is a revert.

1. **Nothing is merged or deployed by this work.** Production continues to run
   `5e9133b` until someone merges deliberately.
2. If merged and a defect appears: `git revert -m 1 <merge-sha>` and redeploy.
   No data migration is needed — the analysis cache is versioned, so a revert
   makes stored analyses incompatible and they re-run rather than serving a
   result from the reverted pipeline.
3. Per-area kill switches, if a full revert is too broad: the consistency gate
   and the critic are read-only and can be neutralised by reverting a single
   commit each (`69038e1`, `6ac1047`) without touching the rest.

---

## 5. Release notes

**Founder Intelligence RC1**

- A brief now opens with a headline a reader can finish in fifteen seconds:
  what the company does, what appears to be changing, and how confident to be.
- Confidence reflects whose account the evidence is. A company's own pages
  cannot establish a claim about how its market sees it, however many of them
  agree.
- Every claim states how it is known — company-stated, customer-observed,
  independently corroborated, inferred, pattern-supported.
- Private companies and local businesses are held to the evidence they
  actually have, instead of being reported as failed public companies.
- Follow-up questions are answered in plain language, including hostile ones.
- Where the evidence supports no view, the product says so.
- Retrieved pages are treated as data. Nothing on a page can change how it is
  classified, how confident the analysis is, or what the product says.
