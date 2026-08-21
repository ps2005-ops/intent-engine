# Wave-1 defect register — first pass, deployed 8397d67

## D-QA-REPR (systemic, every company, customer-facing)
Q&A renders raw dataclass `repr()` to the reader:
  marketbelief(belief_id='mb_f3a52cac10', subject_id=..., proposition=...)
  beliefchallenge(belief_id=..., strongest_support=...)
  link(frm=..., to=..., standing='observed', because=..., evidence='', settled_by='')

SEAM  src/intent_engine/founder_brief/qa.py:368
      items = [str(v) for v in value if str(v or "").strip()]
CAUSE the list branch only recognises dict rows. MarketBelief/BeliefChallenge/
      Link are dataclass INSTANCES, so `any(isinstance(v, dict) ...)` is False,
      `_render_rows` is skipped and str() falls through to repr(). The comment
      above the branch records the same defect being closed for dicts; objects
      were never taught. Only reachable since the router repair, because these
      are among the eight intents that previously fell to the catch-all.
SCOPE Q&A ONLY. 0 hits on intro/full/slides/story/connect/brief.

## D-QA-COMPETITOR (systemic; contradicts step 1)
Meta's "who's the real competitor?" answered "37signals llc ... adobe inc.",
justified as "operates the same business model (subscription software) in the
same sector (software platform)".
Meta is ad-funded, not subscription software. The INTRO on the same run is
correct and bounded: "contested less by a named firm than by the alternatives
its customers already have". Two producers disagree about the model class.
SCOPE Q&A only for the naming; the model-class error may be upstream.

## D-QA-MARKET-SNAPSHOT (top-two questions, customer-facing operational text)
"What should management do?" and "What would you tell the board?" both answer:
  "do not act on this reading. re-run once the market engine publishes a
   snapshot this side will read."
CORRECTED: not a lookup bug. Meta is genuinely absent from the 26 published
snapshots (they cover cloudflare, shopify, stripe, caterpillar, jpmorgan,
johnson-johnson, nextera and 19 others; not meta/alphabet/microsoft/amazon/
salesforce/adobe/servicenow). The retrieval is correct.

THE DEFECT IS WHAT ABSENCE IS ALLOWED TO DO TO THE ANSWER. §24: a core
section may not terminate in an absence. "Do not act on this reading. Re-run
once the market engine publishes a snapshot this side will read" is both a
dead end and internal vocabulary, on the two questions that matter most.
The ladder (OBSERVED -> INFERRED -> STRUCTURAL -> PROXY -> SCENARIO -> MVE)
exists for exactly this and is not being reached.

FREE CONTROL ALREADY IN THE DATA: of the four canaries, Cloudflare, JPMorgan
and Caterpillar HAVE snapshots and Meta does not. If only Meta refuses, the
absence path is confirmed as the cause and no further live run is needed.

## D-REPORT-RAW-ENUM (customer route /runs/<id>/report)
Renders internal field names as the whole page body:
  "company_understanding what_stood_out possible_blind_spots
   executive_confidence leadership_questions"
307 chars total.

## OBSERVED, NOT YET A DEFECT
- one empty progress poll at t=37.2s on Meta; run recovered and completed.
  Watch whether it recurs across the wave before treating it as real.
- /runs/<id>/sources returns the intro (identical bytes). Expected under
  autorun; recorded so it is not re-diagnosed.

## CONFIRMED ON CLOUDFLARE (2/2 companies)

D-QA-REPR reproduces identically: marketbelief(belief_id='mb_7939cefbda',...).
Systemic, as the seam predicted.

D-QA-MARKET-SNAPSHOT: control resolved. Cloudflare HAS a snapshot and answers
"hold this decision -- what to charge, and for what -- open for now. run the
smallest test that would settle it, and keep the current position in the
meantime." Meta has none and refuses. The refusal is the absence path, not a
retrieval fault. No further live run needed to establish this.

## D-BELIEF-TEMPLATE (new; cross-company collapse)
Meta and Cloudflare carry the SAME market-belief proposition, verbatim:
  "that <CO>'s current weakness is a cyclical trough rather than a structural
   reset, and the prior trajectory resumes."
Two companies with different economics, one sentence. A belief that is
identical for every subject is not a belief about any of them.

## D-DECISION-QUESTION-CONSTANT (new; cross-company collapse)
Meta and Cloudflare both hinge on "what to charge, and for what".
For an auction-priced ad business and a usage-priced network, the same
standing decision question is a selection defect, not a coincidence.

## D-QA-COMPETITOR widened
Meta      -> "37signals llc; adobe inc."
Cloudflare-> "adobe inc.; constellation software inc."
Both justified by the identical string "operates the same business model
(subscription software) in the same sector (software platform)".
Adobe is named for BOTH. Neither company is subscription software. So this is
not one bad pick -- the competitor answer is emitting a generic
same_model_and_sector peer set, with a model class that is wrong for both.

## D-PROGRESS-BLANK (OPEN — cause not yet established, 3/3 companies)
The polled progress page returns NO TEXT for most of the wait:
  Meta       blank 37.2s -> 220.2s   (183s of a 220s wait)
  JPMorgan   blank 37.4s -> 156.7s   (119s of a 157s wait)
  Cloudflare blank  9.4s ->  19.6s   ( 10s of a  20s wait)
`errors: []` on all three, so no request failed.

NOT REPRODUCIBLE LOCALLY. Driven through every non-terminal lifecycle state
over the WSGI app, `/runs/<id>/progress` renders 16,835 bytes / 740 characters
of text every time. So this is not the state machine.

TWO CANDIDATE OWNERS, AND THEY HAVE OPPOSITE SEVERITIES:
  the product   a guest watches a blank page for most of the analysis. SEV2.
  the harness   urllib reads an empty body the browser would render fine, and
                three live companies' progress data is worthless.

REFUSED TO GUESS. Instrumented instead: `Session` now exposes last_status /
last_headers / last_bytes, and any empty stage sample carries its status,
byte count, content-type, content-encoding and final URL.

DECIDING OBSERVATION: drive one live analysis in a real browser and look at
the progress page. A browser is not urllib; if it shows the stage text, the
harness owns this and the product is fine.

## ROOT CAUSE FOUND for D-QA-COMPETITOR: the taxonomy, not the engine
COMPANY_VALIDATION_MANIFEST classes Cloudflare as SUBSCRIPTION_SOFTWARE --
the same class as Adobe and Shopify. The competitor engine faithfully returns
"same model and sector" peers, so it returns Adobe for Cloudflare. It is not
picking badly; it is being told a usage-priced network and a seat-based
creative suite are the same kind of business.

SUBSCRIPTION_SOFTWARE is the largest bucket: 21 of 100 manifest entries.
Meta is NOT in the manifest and takes its class from SEC SIC 7370, landing in
the same bucket -- while Meta's own intro correctly reads it as "attention
resold to advertisers: revenue is an auction price per impression".

Where the class is right, the engine is right:
  JPMorgan   BALANCE_SHEET_OR_NETWORK   -> Bank of America   correct
  Caterpillar MANUFACTURE_AND_AFTERMARKET -> Deere            correct

## D-CENTRAL-QUESTION-CONTRADICTION (Meta/Alphabet shape, confirmed 1/4)
Same run, two surfaces, two different central decisions:
  Meta intro  "how much of the audience's attention to convert into
               inventory, and where"           (archetype ENGAGEMENT)
  Meta Q&A    "what to charge, and for what"   (model-class default PRICING)
Cloudflare, JPMorgan and Caterpillar AGREE across the two surfaces -- because
for them the archetype and the model-class default happen to coincide. The
disagreement is only visible where they differ, which is exactly the
ADVERTISING_PLATFORM companies the archetype table was extended for.
So `why_this_question` reads model class where the intro reads archetype.

## D-CENTRAL-QUESTION-COLLAPSE (2/4 canaries, measure across the wave)
Cloudflare and JPMorgan share one central question verbatim:
  "what to charge, and for what"
A CDN and a regulated bank do not have the same standing strategic decision.
Caterpillar differs (CAPACITY), so this is not universal. Quantify over
Wave 1 before attributing a cause.

## D-PROGRESS-BLANK — RESOLVED: it was a REDIRECT LOOP, and it is a SEV2
The instrumented sampler named it on the first live run after instrumenting:

    t=36.0  status=303  body empty  final_url .../runs/<id>/progress

A 303 whose final URL is the page it started from.

CAUSE. `_progress` redirects to the run page as soon as
`result_readiness(...)["opens_result"]`; five other surfaces redirected BACK
to progress whenever `_availability(...)["in_flight"]`. Both are true together
from the moment a readable result composes until the worker clears.

    Alphabet    36s -> 152s   76% of the run
    Meta        37s -> 220s   83%
    JPMorgan    37s -> 157s   76%
    Cloudflare   9s ->  20s   50%

Four of four. The customer watching their own analysis saw a page that never
resolved -- the ambiguous limbo the terminal-state invariant forbids.

Reproduced offline as a THREE-node cycle, /runs/<id> -> /intro -> /progress,
which is why repairing the first site only moved the loop one hop.

FIX. One predicate, `WebApp.only_watchable`, used by all five surfaces. The
rule was already written in `result_readiness`: "opens_result is True IF AND
ONLY IF a customer-readable result exists. When it is True the customer goes
to the analysis, whatever the worker's metadata says." Five callers asked the
question; one place now answers it.

GUARDS. tests/test_webapp_progress_never_loops.py follows redirects with a
budget and asserts the reader LANDS on the route they asked for -- both
weaker versions of that assertion let a break proof through.
5/5 mutations caught.

## D-LANGUAGE-DENSITY (fixed; live cause NOT fully established)
Cloudflare's 10-Q was listed under "Sources found but not used -- not
available in a language this analysis can read", leaving 2 usable sources
where 5 were needed, so the standing control rendered a Limited analysis.

NOT REPRODUCED: through this product's own extractor the filing measures
is_english=True. Truncation makes it MORE English, not less. So the exact
live trigger is unproven and is recorded as unproven.

WHAT IS PROVEN is the fragility, and it is structural: `foreign_words` counts
how many of ~40 markers appear AT LEAST ONCE, which can only rise with
length. Cloudflare's own 10-Q, by slice:

    5k chars -> 1 marker      200k -> 1      400k -> 2      466k -> 3

against a threshold of 4. English financial prose contains " per " (per
share), " de " (de minimis), " el " (El Paso), " la ", " il ", " lo ".

FIX. Density, in occurrences per thousand words, calibrated on measurement:

    Cloudflare 10-Q     0.50 markers/1k words
    Cloudflare 10-K     0.56
    German page       371.08
    French page       443.90

A 600x separation; the bar sits at 40. A first attempt scaled the thresholds
but kept counting DISTINCT markers -- which saturate at ~40 -- and a positive
control caught it reclassifying a 280,000-character GERMAN document as
English. Occurrences scale; distinct markers do not.

## THE TOP CLUSTER: MODEL CLASS IS THE UNIT OF PERSONALISATION
Three defects already recorded separately are one root cause. Measured on
8397d67 across 7 companies:

  competitor      Meta -> "37signals llc; adobe inc."     (both SUBSCRIPTION_SOFTWARE)
                  Cloudflare -> "adobe inc.; constellation software inc."
                  JPMorgan -> "bank of america" CORRECT   (BALANCE_SHEET_OR_NETWORK)
                  Caterpillar -> "deere" CORRECT          (MANUFACTURE_AND_AFTERMARKET)

  central question  Cloudflare and JPMorgan share "what to charge, and for
                    what" verbatim; Caterpillar differs (CAPACITY)

  step 6          Meta vs Alphabet  1.000 -- BYTE-IDENTICAL after name masking
                  Alphabet vs Amazon 0.810
                  Meta vs Microsoft  0.151

Step 6 is NOT generic -- Meta vs Caterpillar is 0.701 and the asks are
genuinely different (Caterpillar: order backlog, dealer inventory, pricing
realisation against input cost; Meta: impressions, ad load, engagement). The
copy says "a business of this kind", so class-keying is DELIBERATE.

THE DEFECT IS THE RESOLUTION OF THE CLASS, not the mechanism. Alphabet and
Meta share ADVERTISING_PLATFORM, so Alphabet is asked only about impressions
and auction clearing price -- for a company that reports Cloud as a material
segment with a different economic engine entirely.

The manifest already carries `multi_segment`, so the data to do better exists.

NOT REPAIRED IN THIS WAVE. It is a larger change than the five repairs that
are proven and staged, and shipping it half-done would be worse than the
coarse class. Top of the Wave-2 repair list.

## WHAT THE Q&A REPAIR ACHIEVED, MEASURED
  cross-company worst pair   9/10 identical (fdbfe77) -> 2/10 (8397d67)
  within-company distinct    5-6/10          -> 9/10 on all 7 companies

## INSTRUMENT CORRECTION (the fifth this session)
An ad-hoc §20 coverage grep reported "recommendation MISSING" and "revenue
driver MISSING" on 8 of 8 companies. Both were false. The cue list was built
from the Q&A's phrasings ("hold this decision", "revenue at a business of
this kind moves with") and run against the FULL ANALYSIS, which words the
same content differently:

    "Decision memo -- the reading, the choice and the recommended next move"
    "What to do now: One check separates them: segment disclosure showing
     no material inter-segment revenue"
    "should be fundable from operating cash rather than from a raise timed
     to a recovery in the price"

A uniform result across every company is the signature of a broken instrument,
not a uniform defect. `pre100.audit.audit_company` is the authoritative
mechanical check and reported with_flags=1 -- only Salesforce, and only
because it was mid-capture.

SURVIVING SIGNAL: Cloudflare alone is missing demand driver, supply
constraint, capital need and market belief, because it rendered the Limited
analysis off 2 usable sources. Already recorded under D-LANGUAGE-DENSITY.

## D-STANDING-ABSENCE-VS-REFUSAL — HELD OUT OF THIS DEPLOY
The diagnosis stands and the vocabulary supports it: UNAVAILABLE ("the
producer never sent this") was being answered with REFUSED's copy ("the
published snapshot was not in a readable state"), the only standing that
carries no falsifier and no next step, on the two questions a board asks
first. Meta got it; Cloudflare, which has a snapshot, gave a real
recommendation on the same build.

WHY IT DOES NOT SHIP YET. The full guard turned two existing tests red, and a
per-file bisect named decision_synthesis.py as the cause. The run they cover
still gets an honest Limited-analysis page, but it LOSES its reader-specific
reason -- "none carried the dated, checkable material" -- and keeps only the
generic sentence. Standing feeds page selection more widely than the market
block, which is the part I did not establish before changing it.

Adding a reason for Meta at the cost of removing one for somebody else is not
the repair I set out to make, and updating the two tests to match my change
would encode my change as the truth rather than test it.

Change reverted; the ten tests written for it are held at
scratchpad/held_test_decision_standing.py. Wave 2, scoped to the market block
rather than to standing globally.
