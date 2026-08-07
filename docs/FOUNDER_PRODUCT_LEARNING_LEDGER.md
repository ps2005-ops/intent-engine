# Founder Product Learning Ledger

One row per defect found by reading the deployed product as a founder reads
it. A defect is closed only when the producer is fixed, the suite is green,
the build is deployed, and the improvement is measured live.

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

### Learning velocity

Four producers fixed, none patched at a surface. Two of the four were defects
this project introduced in the previous cycle and only a live browser run
found them — the pattern this cycle repeats is that **internal correctness and
founder-visibility are different measurements**, and only the second one
counts.
