# Founder Product Learning Ledger

One row per defect found by reading the deployed product as a founder reads
it. A defect is closed only when the producer is fixed, the suite is green,
the build is deployed, and the improvement is measured live.

---

## Cycle 2026-08-07e — identity recovery (deferred cost paid back)

Priority 2 of a cycle whose Priority 1 was market learning health. Only one
Founder defect was worked, deliberately: it was the one the previous cycle
booked as a known cost rather than found by accident.

### Defect closed

| # | defect | severity | producer | fix |
|---|---|---|---|---|
| 5 | Valid product descriptions that never name the company fall back to a signal label — Brightledger, Shopify | medium, carried 1 cycle | `_is_about` was binary: first person **or** the company's name, nothing else | `founder_brief.identity.classify`, four states, PROBABLE reachable only via product ownership read from the company's own site taxonomy |

The previous cycle recorded this as "needs an identity-page detector" and
named the obstacle exactly: "Connectors read payout files…" is *structurally
identical* to "Figma democratizes design" as far as any sentence-level rule
can see. That is true, and it is why the signal is not in the sentence. It is
in the sitemap — `/docs/connectors` is a Brightledger page and `figma` is only
ever a customer-story path on stripe.com.

### Mistake made and measured out

The first draft listed `connectors` in the classifier's stopword list, as an
example of a common noun that only looks like a product name. That silently
blocked the single case the module was built to recover, and the recovery test
returned UNKNOWN. The rule that replaced it: **this module never decides
whether a word is a product name — it checks whether the company treats it as
one, and only the site's own taxonomy answers that.**

### Regression risk taken and bounded

`_is_about` is also the gate behind the "Company claim" provenance label fixed
last cycle. Callers that pass no vocabulary cannot reach PROBABLE, so
`narrative.py` is unchanged by construction rather than by inspection —
relaxing an attribution label is a different decision from relaxing which
sentence opens a page, and only the second was made.

### Measured live on the deployed preview (`51dcb7d`)

Two companies, not eight. The preview rate-limits per visitor (HTTP 429,
"this preview limits how much one visitor can run"), and it cut in after the
second run. That is the standing constraint on this matrix and it is not
going to be argued away by trying harder.

| company | live opening | verdict |
|---|---|---|
| Stripe | "Stripe is a financial services platform that helps all types of businesses accept payments, build flexible billing models, and manage money movement." | **correct.** No occurrence of "Figma" anywhere on the page. Provenance labels on the page: 1× "Company claim", 1× "From Stripe's own site" — both classes in use, so the venue label is not swallowing everything |
| Shopify | "Learn about Shopify and how it works. Explore its pricing plans and essential features for building and managing your business." | **partial — a NEW defect** |

Not validated live: Brightledger, Palantir, Microsoft, HubSpot, Caterpillar,
Canadian National Railway. Rate-limited before they ran. Brightledger's
recovery is proven in unit tests against the exact real strings and **is not
proven live**; that distinction is the whole point of this ledger and is not
being blurred here.

### New defect found by looking (Shopify)

Shopify no longer opens with the investor-update line — that part worked. But
the sentence it now opens with is the page's **SEO meta description**: "Learn
about Shopify and how it works" is copy about a *page*, not about a business.
It names Shopify, so the identity detector classifies it CONFIRMED, and that
classification is **correct** — it genuinely is Shopify writing about Shopify.

The identity gate is therefore doing its job and is not the remaining
constraint. The defect is upstream, in which text becomes an observation
excerpt at all: meta descriptions are being admitted as candidate
descriptions. Recorded as the next Founder target rather than patched here,
because a filter bolted onto the identity classifier would put a retrieval
fix in the wrong module — the same mistake as fixing a label at the surface
instead of the producer.

| defect | severity | producer (suspected) | why not this cycle |
|---|---|---|---|
| Opening sentence is an SEO meta description | medium | observation excerpt selection admits `meta_description` | found at the very end of the cycle, on the last quota available; fixing it unverified would be worse than booking it |

### Product learning velocity — cycle over cycle

| measure | 2026-08-07d | 2026-08-07e |
|---|---|---|
| defects found | 4 | 1 (Shopify meta description) |
| defects closed | 4 | 1 (carried) |
| companies verified live | 20 | 2 (rate-limited) |
| producer-level fixes | 4 | 1 |
| surface-level patches | 0 | 0 |
| defects this project introduced | 2 | 0 |
| repeat defects (same class reappearing) | 0 | 0 |
| break proofs held | — | 7/7 identity, 15/15 market |
| suite | 4491 | 4508 |

The reading: **the defect found this cycle is one layer deeper than last
cycle's.** Last cycle's Shopify defect was "opens with the wrong KIND of
sentence"; this cycle's is "opens with a sentence that is genuinely the
company's, correctly identified, and still not a description of a business."
That is the maturation signal worth tracking — not the count, which fell from
4 to 1 mostly because only two companies could be run.

The two rows that stayed at zero are the ones to keep watching: no defect was
patched at a surface, and no defect class came back.

**The honest limit on all of the above.** Two companies is not a matrix. The
velocity table says "1 defect found" and that number is bounded by quota, not
by product quality — with eight companies it would very likely be higher. No
claim about the product getting better should be read out of this row until
the matrix runs at breadth, and the rate limit means that needs to be spread
across windows rather than attempted in one sitting.

---

## Cycle 2026-08-07d — live product audit (CEO quality)

Method: twenty companies on the deployed preview through fresh guest
identities, plus two run in a real browser. Scored on what a founder sees, not
on code.

### What the audit found was ALREADY clean

Earlier cycles closed these and they stayed closed across 9 scored runs:

| class | instances |
|---|---|
| pattern taxonomy in the reader's text | 0 |
| page furniture (cookie banners, nav, ©) | 0 |
| shallow assertion ("this proves", "this shows") | 0 |
| falsifier present | 100% |
| counterargument present | 89% |

### Defects found, all fixed at the producer

| # | defect | frequency | severity | producer | fix | live before → after |
|---|---|---|---|---|---|---|
| 1 | Page opens with a signal label, not the business. Palantir and Microsoft opened with the **identical sentence**, name-substituted | **every page** (23 flat-label instances / 9 runs) | high — first thing read | `founder_brief.build._what_it_does` fell back to `obs["text"]`, the sentence the system GENERATES from a signal label, despite its docstring promising "the company's own description" | prefer own-account `excerpt`; `product_surface` then `messaging` | "Palantir sells several distinct products rather than one, so attention and engineering are split…" → "Palantir Technologies builds three platforms: Foundry for the commercial enterprise, Gotham for defence and intelligence, and AIP" |
| 2 | **Stripe's page described Figma** | 1/7 measured, but worst class | critical — wrong company | a customer story Stripe HOSTS about Figma; `observation_sentence` had pasted the subject's name onto it, masking the content | `_is_about`: first person **or** the subject named. Provenance alone was tried and failed live — the page is on stripe.com | "Figma democratizes design…" → rejected |
| 3 | Near-miss sentence rendered under **"What to watch"**, where nothing is watchable | every bounded run | high — reads as a malfunction | mine, previous cycle: inserted into `evidence_gaps`, which the watch section also consumes | extend `_NOT_OBSERVABLE`, the filter that already owns this class | Cloudflare's watch list carried "The public record argues against the reading that it holds the authoritative record…" |
| 4 | "The public record **argues against**" a reading, because the company publishes a price list | any company with a weak disconfirmer | high — false claim | `sufficiency.classify` treated ANY disconfirmer as contradiction; `pricing_published` is explicitly a weak one ("a company can publish prices and still hold the record") | contradiction needs a blocking signal **or** a second disconfirmer | Cloudflare no longer told the record argues against it |

### Ordering mistakes made and measured out

- `messaging` before `product_surface` opened Notion, Linear and Brightledger
  with their **price lists** — pricing pages carry that type.
- Requiring the excerpt to NAME the company rejected Brightledger's real
  description ("Connectors read payout files from payment processors"), which
  names nobody because a product page does not need to. Provenance settles
  what phrasing cannot.
- Requiring a BLOCKING signal for contradiction made the state unreachable for
  eleven of twelve patterns.

### Remaining, not fixed

| defect | severity | why not this cycle |
|---|---|---|
| Brightledger falls back to a signal label | medium | **cost of the strict subject rule.** Its page says "Connectors read payout files from payment processors" and never names the company; that is structurally identical to "Figma democratizes design". Needs an identity-page detector |
| Shopify opens with an investor-update line | medium | same cause: its product page never names Shopify |
| Sony opens with its segment-reporting cadence | medium | no product or positioning page was retrieved this run — a retrieval gap, not a reasoning one |
| NVIDIA returns a limited-evidence page | medium | retrieval; unchanged before and after |
| Adobe opens with a fiscal-year results sentence | low | own words, own page, just not a description |

### Measured live on the shipped build (`40920cd`)

| company | before | after |
|---|---|---|
| Palantir | "sells several distinct products rather than one, so attention and engineering are split…" | "At Palantir, we believe that with good data and the right software, institutions can solve hard problems…" |
| Microsoft | *the identical sentence* | "Microsoft is a technology company committed to making digital technology and artificial intelligence available…" |
| HubSpot | *the identical sentence* | "We provide an agentic customer platform that helps marketing, sales, and customer service teams drive business growth." |
| Stripe | "exposes a surface others can build on…" → then, mid-cycle, "Figma democratizes design…" | "Stripe is a financial services platform that helps all types of businesses accept payments, build flexible billing…" |

Signal-label openings: **4 of 4 → 0 of 4**. "The public record argues against"
gone. Near-miss explanation still visible.

### Still open, found while verifying

| defect | severity | note |
|---|---|---|
| Figma's self-description still appears in Stripe's EVIDENCE list, labelled "Company claim" | medium | attributed to "INFINITE GROUP INC — 10-K", so it is sourced rather than asserted, but "Company" reads as Stripe. Same class the `FS.subject_span` guard exists for on competitor filings; these are reaching the evidence list by another route. **Next cycle's first target.** |

### Learning velocity

Four producers fixed, none patched at a surface. Two of the four were defects
this project introduced in the previous cycle and only a live browser run
found them — the pattern this cycle repeats is that **internal correctness and
founder-visibility are different measurements**, and only the second one
counts.
