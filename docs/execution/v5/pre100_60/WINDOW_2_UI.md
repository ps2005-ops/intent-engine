# Window 2 — deployed UI, `188da7c` → `31e6138`

Meta, Amazon, Caterpillar, Exxon, Lilly. **Four of five captured.**

## Reliability

| company | auto-advance | seconds | Q&A |
|---|---|---|---|
| Amazon | yes | 296 | 10/10 |
| Caterpillar | yes | 258 | 10/10 |
| Exxon | yes | 170 | 10/10 |
| Eli Lilly | yes | 18 | 10/10 |
| **Meta** | **no** | 556 | **0/10** |

Meta was **destroyed by a mid-window redeploy** — 404 on all thirteen routes.
Not a product failure; see `DEPLOY_DESTROYS_LIVE_RUNS.md`.

Lilly's 18 seconds is a real result, not a short-circuit: correct class,
correct rivals, and its own 10-K among the three pages read. The likely cause
is the `(CIK, accession)` filing cache serving documents fetched earlier.

## The three greps

| grep | result |
|---|---|
| **1 — step 1 names a rival AND Q&A denies one** | **PASS, 4/4.** No company both names and denies. *"Who's the real competitor?"* is now 5-distinct. |
| **2 — JPMorgan, "committing capital to capacity"** | **NOT_CAPTURED.** JPMorgan was not in this window. |
| **3 — raw dict repr in an answer** | **PASS.** No answer contains `'name'` or `{`. |

Case A is verified on a rendered page: Amazon answers *"publishers: This
absorbs the task into something the customer already pays for…"* where the
previous build denied having any competitor.

## Collapse: 0/10 across all five — and one pair at 8/10

`IDENTICAL ACROSS ALL COMPANIES: 0/10`. But pairwise:

    8/10   Caterpillar  ==  Exxon Mobil
    1/10   Amazon       ==  Caterpillar

### The successor defect

Caterpillar and Exxon are **different classes** and render **different
business models**:

> Caterpillar — *"an industrial business that runs on sale of a long-lived
> manufactured product followed by a higher-margin service and parts stream"*
> Exxon — *"a materials energy business that runs on production of an
> undifferentiated output sold at a price the producer does not set"*

and both answer eight of ten board questions with:

> *"committing capital to capacity ahead of uncertain demand"*

while Amazon, correctly, answers *"running separately-reported businesses as a
single portfolio"*.

**The class gate stopped the wrong pattern reaching Meta. It did not stop the
same pattern producing the same answers for two genuinely different
businesses.** `capacity_ahead_of_demand` legitimately applies to both — the
defect is not that either qualifies, it is that qualifying is sufficient to
determine the whole read.

This is the cross-class form of the same-class problem measured offline
(NVIDIA/AMD 8/12, Alphabet/Meta 10/12): wherever two companies share a top
pattern, they share the reading. Within a class that is structural; across
classes it is this.

**The wrong fix is another table row.** A per-company or per-pair exception
reproduces the original defect in a new shape. The differentiation has to come
from each run's own evidence — its ladder, its XBRL metrics, its competitive
ground — which is exactly where Caterpillar and Exxon DO differ today (their
intros, competitors and mechanisms are distinct) and exactly what the board
answers currently ignore.

## Evidence quality — one clean company

Lilly read **only its own SEC filings**. That contrasts with Walmart on
`58ac7ef` (Ranpak, Ibotta, a 2023 BitNile 10-K, no Walmart 10-K) and JPMorgan
on `0420fb0` (Wells Fargo, a blank-check SPAC). Whether that is the ownership
repair working or simply what discovery returned for Lilly is **not
established** — one company is not a measurement.

## Not scored

The twenty dimensions are **NOT_MEASURED**. Reliability, class, competitive
read and collapse were measured; the remaining dimensions were not scored from
these captures.
