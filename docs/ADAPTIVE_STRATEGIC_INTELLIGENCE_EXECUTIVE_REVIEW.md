# Adaptive Strategic Intelligence — manual executive review

Frozen SHA: `807a414361b0fbc1999b4595e875c67e2a20524a`

## Development gate — manual executive review (be5fde12)

Read as a chief executive and as a chief strategy officer, on the live page.

### Highspot — run `01M26WYVT48B1EVQNJPC6DH8KH`

| # | question | verdict | note |
|---|---|---|---|
| 1 | Understands what the company does? | YES | quotes its own sentence: "the agentic platform that turns GTM signals into role-specific actions" |
| 2 | Understands how it creates value? | YES | "recurring software subscription: revenue is contracted and renews, so the installed base carries next period's revenue" |
| 3 | Customer job correct? | YES | sales enablement / revenue execution, in the company's own terms |
| 4 | Strategic asset correct? | PARTIAL | assets thin; specificity is reported as 18–24%, and the page says so rather than dressing it up |
| 5 | Lens defensible? | YES | Revenue & GTM, 41.5 against 21.5, with six named refusals and why each lost |
| 6 | Visibly company-specific? | YES | its own vocabulary is quoted and contrasted against the generic reading |
| 7 | Decision domain relevant? | YES | how revenue is produced / what the sales org is asked to do / which assumption the plan rests on |
| 8 | Causal or investigation reasoning defensible? | YES | investigation chain, each node tagged evidenced / inference / open_question |
| 9 | Evidence separated from inference? | YES | explicitly, per node |
| 10 | Contrary or limiting evidence visible? | YES | "the run did not retrieve enough independent material to test this company's own account of itself" |
| 11 | Useful "so what?" | PARTIAL | see the defect below |
| 12 | "What would change our mind?" useful? | YES | names the document class that would unlock a reading |
| 13 | Information priority useful? | YES | a dated third-party account of something it decided or changed |
| 14 | Q&A understands the company? | YES | 6/6 substantive, 6/6 name the company, follow-up retains context |
| 15 | **Safe to show Highspot's real executive?** | **NO** | one page makes two opposite claims — see below |

### The release-blocking finding

The adaptive block says, in the section built for exactly this:

> **WHAT WE CANNOT YET CONCLUDE** — What this management should actually do.

and roughly one screen further down, the founder layer says:

> **WHAT WE RECOMMEND** — Move on pricing and packaging at a size that can be
> reversed inside one planning cycle, and instrument it so the result is
> readable before…

Both are individually defensible. The founder layer reasons from the economics
of the business-model class and badges itself `BOUNDED` — "the reading follows
from how this kind of business works; no source outside the company's control
was read in this run, so it is held in direction only". The adaptive layer
refuses to name a decision grounded in evidence about *this* company.

To a reader they are a contradiction, and the contradiction lands on the claim
this whole phase rests on. `founder_brief/steps.py` renders the recommendation
whenever `read.level6_action.action_now` exists, with no reference to the
adaptive state; `webapp/app.py` composes them together and its own comment says
"The adaptive block reads that page. **What follows it is unchanged.**" — a
deliberate boundary that was never evaluated against an abstention.

Classified: **PRODUCT_DEFECT — systemic**, one run saying two things.

### Lesser findings, recorded and not fixed

- **Three domain cards, one sentence.** All three *Potential decision domains*
  open with the same self-description clause, varying only the trailing domain
  name. Honest (the same evidence does support all three) and repetitive.
- **A newsletter call-to-action quoted as evidence.** The lens block carries
  "Stay informed on our sales enablement innovation." — furniture the filter
  did not catch.
- **"reached through market rate, labor"** reads as internal channel tokens
  rather than a sentence, in the investigation chain's mechanism node.

### A third surface, and the same shape of defect

`/xray` — linked from the main page as "X-Ray · Full analysis · Presentation" —
opens with:

> **WHY THIS DECISION** — What kind of business this is has not been
> established: no regulator classifies this company, and the material that was
> read describes what it does without…

while `/intro`, for the same run, says:

> It is a **subscription software business**, read from its own account of how
> it is paid.

That "has not been established" sentence is the ORIGINAL defect this entire
phase exists to remove. It is still alive on the X-Ray surface.

**Cause, established by reproduction rather than by reading code.**
`profile_for` has three rungs, and rung 3 — the company's own published
account — only fires when the caller passes `published_text`:

| call site | what it feeds | passes `published_text` |
|---|---|---|
| `app.py:6186` | `/intro`, adaptive | **yes** |
| `strategic_read.compose` → `select` | the strategic read | **yes** |
| `app.py:5338` | founder economic context | **no** → *fixed* |
| `app.py:6469` | history surface selection | **no** |
| `app.py:6649` | timeline selection | **no** |
| `decision_synthesis:498` | **the X-Ray panel** | **no** (nor `evidence_text`) |

Run offline on Slalom's own subject-owned text, the two forms return
`known=True` / `PEOPLE_OR_ROUTE_BASED_SERVICES` and `known=False` / `UNKNOWN`,
and the `known=False` branch returns the exact sentence the live page prints.

**The producer, traced rather than assumed.** The panel's text is
`AnalysisSelection.why_this_question`, which `analysis_selection.select` sets
to `profile.profile_limitation` whenever the profile is unknown.
`decision_synthesis._select()` calls `AS.select` with manifest and registrant
only — no `evidence_text`, no `published_text` — so that profile can never be
known for a private company.

Classified: **PRODUCT_DEFECT — systemic, DIAGNOSED AND NOT FIXED.** Six call
sites, four of them missing rung 3, and the one feeding this panel needs a
parameter threaded through `decision_synthesis.compose`. That is a
cross-module change immediately before a qualification freeze, which is how a
measurement becomes a guess, so it is recorded rather than rushed.

I first wrote that this was one argument at one call site. That was written
before the producer was traced, and it was wrong — the panel never reads the
profile the fix repairs.

---

# Final matrix — all ten

Eighteen of the twenty questions are derived from what the run recorded, each
naming the field it came from so a reader can disagree with the instrument
rather than with an unattributed verdict. Two need a reader and were answered
by reading the pages.

## Scores

| Company | derived | lens defensible (read) | "so what?" useful (read) | total |
|---|---|---|---|---|
| Highspot | 17/18 | YES | YES | **19/20** |
| BigID | 17/18 | YES | YES | **19/20** |
| Cyera | 17/18 | YES | PARTIAL | **18.5/20** |
| Monte Carlo Data | 11/18 † | N/A | N/A | **see note** |
| Veeam | 17/18 | YES | YES | **19/20** |
| Druva | 17/18 | YES | PARTIAL | **18.5/20** |
| Slalom | 17/18 | YES | YES | **19/20** |
| Sigma Computing | 17/18 | YES | YES | **19/20** |
| ZoomInfo | 16/18 | YES | YES | **18/20** |
| Point B | 13/18 | N/A (none selected) | NO | **13/20** |

† Monte Carlo Data is a retrieval-failure page. Seven of its derived NOs are
category errors — "lens block missing", "no investigation chain", "the two role
views do not differ" — asked of a page that is not a report. A failure notice
has no modules to reorder. Held to what it *does* owe (name the company, say
what happened, refuse to invent), it passes.

## The single recurring NO

**"20. Safe to show the company's real executive?"** is NO for nine of ten, and
for seven of them it is the *same* cause: `/intro` establishes the business
model from the company's own words and `/xray`, one click away, says
"what kind of business this is has not been established".

The correlation is exact — seven for seven:

| model source | companies | contradiction |
|---|---|---|
| `SUBJECT_PUBLISHED_EVIDENCE` (rung 3) | Highspot, BigID, Cyera, Veeam, Druva, Slalom, Sigma | **7/7 yes** |
| `REGULATOR_INDUSTRY_CODE` (rung 2) | ZoomInfo | no |
| `NOT_ESTABLISHED` | Monte Carlo, Point B | no (both surfaces agree) |

Rung 3 is the rung this phase added, and it is the only one the X-Ray path
cannot reach — so the defect lands on exactly the private companies the phase
exists to serve, and spares the one public company in the cohort. ZoomInfo's
NO is a different cause: one evidence quotation is an SEC bullet fragment.

## Lens defensibility, read rather than derived

All eight selected lenses fall inside their expected semantic family, and each
publishes its score, its runner-up and its refusals. Two worth naming:

- **Sigma Computing → Data Infrastructure & Decision Trust**, with
  `planning_assumption` and `data_security_governance` as secondaries. A
  spreadsheet-interface analytics company could defensibly have routed to
  enterprise data; the published reason cites its own vocabulary.
- **Druva → Enterprise Data & AI Strategy** over `data_security_governance`
  (23.5 against 10.5). Druva is a backup and resilience company, so data
  security was the plausible runner-up and is recorded as the secondary.

The refusal lists are genuinely reasoned rather than score dumps. Highspot's
sixth refusal reads: *"Enterprise Data & AI Strategy: scored 1.0 against 41.5,
and pipeline argues the match is about the product rather than the firm"* —
a distinction between a signal about what a company sells and a signal about
how it is run.

## "So what?" — the two PARTIALs, and the one NO

**Cyera and Druva** are marked PARTIAL for the same measured reason. They are
the only two report-producing companies whose bounded block carries **no
self-description**, so "What we know" falls back to the class prior plus the
lens. Their two blocks score **0.927** similarity — the cohort's single
genericity collapse — and the cause is not a template but a missing first-party
sentence.

**Point B** is NO. It retrieved eight of its own pages including
`pointb.com/About`, and still returned `UNKNOWN`: the classifier reads
observation EXCERPTS rather than whole documents, and Point B's excerpts do not
contain the sentence its About page leads with. Offline, its homepage
classifies `PEOPLE_OR_ROUTE_BASED_SERVICES` at **10.0 against 4.0**. The
reasoning is right and the corpus reaching it is wrong.

## What the reviews do NOT find

- no cross-company contamination in any answer (0/60)
- no invented findings — Monte Carlo, with nothing retrieved, answers "there is
  not enough public evidence to answer that confidently" and labels its own
  confidence "Low, by construction"
- no raw internals, no `None`, no unresolved entities on any page
- no role-dependent factual contradiction: the anchored facts are identical
  under CEO and Strategy for every company that produced a report
