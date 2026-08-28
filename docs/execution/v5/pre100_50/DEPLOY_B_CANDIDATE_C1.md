# Deploy B candidate C1 — sentence-anchored `what_is_sold`

Measured offline on 11 real 10-Ks pulled from EDGAR. No live quota spent.

## Cause

`[Ww]e (?:sell|offer|provide|...)` is not anchored to a sentence start, so it
matches RELATIVE CLAUSES inside a larger sentence: "the machinery **we sell**
and the services **we provide**" yields the object "and the services we
provide". That is the fragment defect, and it is one character of grammar.

## Fix

Require the match to BEGIN a sentence (`^`, or after `.`/`;`/`:`), and keep
the vetoes for bullets/glossary, HR, hypotheticals and accounting policy.

## Measured effect (current -> anchored)

| Company | Current | Anchored |
|---|---|---|
| Caterpillar | "and the services we provide" | "reciprocating engines principally through the dealer network and to other manufacturers…" |
| Cloudflare | "to paying customers, and, for certain of our products, expand…" | "a broad range of services to businesses of all sizes and in all geographies…" |
| NVIDIA | "paid licenses to NVIDIA AI Enterprise…" | "a complete, end-to-end accelerated computing platform for AI, addressing both training and inferencing" |
| Adobe | "end-to-end professional creative and marketing solutions" | "an end-to-end, ideation-to-creation platform powered by our commercially safe Firefly models…" |
| Pfizer | "our financial guidance" (wrong) | (none) |
| Walmart | competition risk sentence | (none) |
| Coca-Cola | glossary entry with bullets | (none) |
| Costco | bulleted merchandise-category list | (none) |
| Microsoft | unchanged | unchanged |
| JPMorgan | (none) | (none) |
| Meta | (none, after Deploy A) | (none) |

4 repaired, 4 wrong answers replaced by an honest empty, 3 unchanged.

## Open risk to check before shipping

Five of eleven return empty. `describe()` falls back to `revenue_basis`
first and only then to the class prior — so the thing to verify is that
these five do NOT collapse onto identical class-prior sentences. That is a
known failure mode in this codebase ("class prior must not be the answer":
five software companies once rendered byte-identical). The 50-company
matrix gives 50 samples to check it against instead of 11.

## C1 is TWO fields, not one

Checking the fallback exposed the same defect one field over. `revenue_basis`
matches revenue-RECOGNITION policy out of the notes to the financial
statements, which is accounting, not economics:

| Company | `revenue_basis` today |
|---|---|
| Pfizer | "on bill-and-hold arrangements at the point in time when the customer obtains control…" |
| Walmart | "over the term of the membership, which are generally one year…" |
| Coca-Cola | "when performance obligations under the terms of the contracts with our customers…" |
| Meta | "from advertising on mobile devices" ✓ |

So the C1 repair is: anchor BOTH fields to a sentence start, veto policy
grammar in both, and prefer the Business/MD&A region over the notes. Meta is
the control that must not move.

Note the wrinkle that stops this being a one-line rule: Meta's BEST revenue
sentence ("by displaying ad products on Facebook, Instagram, Messenger and
third-party mobile applications") sits at offset 328,444 — inside the notes —
while the one it currently uses sits at 88,822. "Earlier is better" is
therefore false as a general rule, and the discriminator has to be the
grammar of the sentence, not only its position. Deferred to Deploy B with
50 companies of evidence rather than guessed at on 11.
