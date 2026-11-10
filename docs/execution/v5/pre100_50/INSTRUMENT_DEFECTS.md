# Instrument defects found this session (measurement wrong, not the product)

## I-1. `business_model` cannot tell a right economic engine from a wrong one

CONTROL, and it is decisive. The same company, same dimension, two builds:

* `02f4644`: "Meta Platforms, Inc. is a software platform business that runs on
  **competitive compensation and a wide range of benefits, including many
  learning and development resources**" — its 10-K's Human Capital section.
* `b0ec8cb`: "…runs on **revenue by displaying ad products on Facebook,
  Instagram, Messenger, and third-party mobile applications**."

Both scored **10, "company-specific and substantiated"**.

The specificity instrument asks whether the passage names this company. It
does not ask whether the ECONOMIC CLAIM is true — which is precisely what §15
demands ("a beautifully written wrong economic model is a failure"). So the
quality gate as instrumented CANNOT detect a wrong economic engine, and a
matrix of `core_mean >= 9` would not prove §15.

Smallest repair: the business-model passage's engine clause must pass the same
vetoes the producer now applies — not an employment offer, not a hypothetical,
not an accounting policy. That would have caught this one.

## I-2. `economic_reasoning` is scored with words the product never writes

MEASURED across **210** captured `/full` pages. The nine cue phrases:

| cue phrase | pages containing it |
|---|---|
| revenue engine | **0** / 210 |
| margin engine | **0** / 210 |
| cost of revenue | **0** / 210 |
| unit economics | **0** / 210 |
| how the money | **0** / 210 |
| capital intensity | **0** / 210 |
| capital structure | **0** / 210 |
| operating leverage | 29 / 210 |
| what it costs to serve | 5 / 210 |

Seven of nine never occur anywhere. Total cue coverage is 31/210 (14%), so 86%
of pages score 0 on a CORE dimension — and a single 0 sets `core_min = 0`,
which fails §13's `core_min >= 7` for every company on the matrix.

It is not a product absence. Meta's `/full` on `b0ec8cb` scored 0 while
containing:

> "A substrate that carries several first-party businesses can usually carry
> third-party ones at **close to zero marginal cost**, and the economics of the
> two are not the same."

> "…whether the slowdown is arriving through **volume or through price, because
> only one of those recovers with the cycle**."

> "Owning both what is sold and the channel it reaches people through lets each
> business **subsidise the other's acquisition cost**."

The file's own comment records this exact lesson being learned for
`market_belief` — "the cue wording had to come from what the product actually
writes rather than from the rubric's vocabulary". `economic_reasoning` never
got the same treatment.

Vocabulary the product does write: `cost of credit` 85, `cost of raising money`
83, `growth slowing` 54, `operating leverage` 29, `fully-loaded cost` 28,
`acquisition cost` 27, `margin narrowing` 27, `subsidise` 26, `volume or
through price` 25, `fixed cost` 16, `pricing power` 10, `marginal cost` 4.

A mechanism-based cue raises real detection from 14% to 37%.

DELIBERATELY NOT FIXED YET. Two reasons, both about not repeating a mistake
this programme has already made:

1. Tuning a cue on ONE current-build capture is how an instrument gets fitted
   to its sample. The batch produces 50; the repair is made against those.
2. `cost of credit` (85) and `cost of raising money` (83) are MACRO BOILERPLATE
   repeated across companies. 16 pages carry that boilerplate and no mechanism
   language at all — those must not start scoring. A cue that swept them in
   would make the dimension unable to fail, which is the defect it is meant to
   detect.

**Consequence for reading intermediate numbers: every `core_min` reported
before the rescore is an instrument artifact, not a product failure.** All 50
captures get rescored offline once the cue is repaired; scoring needs no
deployment.
