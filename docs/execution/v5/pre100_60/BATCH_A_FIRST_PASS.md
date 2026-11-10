# Batch A — first pass, all eight, live on `ef352ae`

Driven over HTTP with a cookie jar (`scripts/batch_live_journey.py`): landing
→ try demo → company entry → analyse → progress → the six steps. The browser
pane refused navigation across three tabs in two consecutive sessions while
the service answered 200 throughout, so the journey was moved to a transport
that cannot be blocked by one flaky tab. It walks the same customer path and
asserts the same things: that the run auto-advances rather than parking, that
no step is empty, and that no page claims failure while a result exists.

## Reliability — clean

| metric | result |
|---|---|
| auto-advance | **8/8** |
| false failures | **0** |
| manual recoveries | **0** |
| wrong company | **0** |
| broken routes | **0** |
| empty executive sections | **0** of 48 step-checks |

Median time to first result ~4–6 min; JPMorgan returned in 34s on a warm
path. Two runs (Lilly, Caterpillar) hit `Connection reset by peer` mid-wave
and succeeded on retry — the preview is a free instance with a 10-run hourly
demo quota, so this is an environment limit, not a product defect. Recorded
rather than hidden.

## Business-model classification

| company | class | verdict |
|---|---|---|
| Meta | `ADVERTISING_PLATFORM` | correct — *"attention resold to advertisers: revenue is an auction price per impression"* |
| Amazon | `MULTI_ENGINE_PLATFORM` | correct — *"the engine that carries the profit is not the one that carries the revenue"* |
| Walmart | `SCALE_RETAIL` | correct — *"thin margin… scale in buying and how fast inventory turns rather than price premium"* |
| NVIDIA | `DESIGN_AND_MANUFACTURE` | coarse |
| JPMorgan | `BALANCE_SHEET_OR_NETWORK` | coarse; bank/payment-network merge unresolved |
| Lilly | `REGULATED_PRODUCT_OR_PROVIDER` | coarse, works |
| Caterpillar | `MANUFACTURE_AND_AFTERMARKET` | coarse, works |
| Exxon | `COMMODITY_PRODUCER` | coarse |

The three classes repaired last session are **live and correct**. No company
was misdescribed by its class this pass.

## Competitive quality — the real spread

**Working well:**

* **Lilly** — *"generic competition to Verzenio, generic competition to
  Mounjaro, large number of multinational pharmaceutical companies"*. Named
  threats to named assets: the correct competitive model for pharma.
* **NVIDIA** — *"Huawei Technologies Co, Open-source AI, Keeping the existing
  fleet running longer"*. A real rival plus two real substitutes.
* **JPMorgan** — *"the customer's own treasury and banking desk, non-bank
  providers reaching the customer directly, automation"*. Correct substitutes
  for a bank.
* **Caterpillar** — *"Independent service and will-fit parts"* is exactly the
  aftermarket threat that class exists to find.

**Broken — `WRONG_COMPETITOR`, 5 of 8:**

| company | wrong entity | what it actually is |
|---|---|---|
| Meta | 37signals LLC | project-management tool |
| Exxon | Agnico Eagle Mines Limited | gold miner |
| Meta | S&P | an index / rating agency |
| Walmart | Medicare Part D | a government programme |
| Caterpillar | America Leasing | not an equipment OEM |

### Two distinct sub-causes

**(a) Rung 9 rendered as rung 1.** `STRUCTURAL_PEER` is defined as *"same
business model; not a stated rival"* — the ladder's honest bottom, reached
when nothing better was found. `_position` put it in **"contested most
directly by"**. That is 37signals and Agnico Eagle.

**Repaired this session**, with 4 tests (2 fail before). Rung 9 is now
excluded from the direct-contest sentence, falling through to the hedged
wording when nothing stronger exists.

**(b) Non-actors extracted from the subject's own filing.** S&P, Medicare
Part D and America Leasing are proper nouns in competitive-sounding sentences
that are not things a customer chooses instead. `names_a_contest` correctly
gates the SENTENCE; nothing gates whether the NAME is an economic actor.

**Not repaired.** The module's own history records three live rounds proving
stoplists cannot separate a heading from a name, and the same argument
applies here — a list of "S&P, Medicare, …" would be defeated within a
deploy. The general form is the relationship test already built in
`executive/relationship.py`: a candidate needs evidence that a customer could
choose it *instead*, which a payer programme and an index cannot satisfy.
That is the next repair wave and it needs its own measurement, not a patch.

## Defect clusters, ranked

| cluster | companies | status |
|---|---|---|
| `WRONG_COMPETITOR` (a) rung-9 promotion | 2 | **fixed** |
| `WRONG_COMPETITOR` (b) non-actor extraction | 3 | open, next wave |
| `ONTOLOGY_COARSE` bank vs payment network | 1 | needs Visa (Batch C) |
| `MODEL_SENTENCE_ABSENT` Caterpillar intro | 1 | unverified, low confidence |

## Not done

Second pass after the rung-9 repair. The twenty-dimension rubric was not
scored per company — reliability, classification and competitive quality were
measured directly instead, which is what this pass was for.

**NEXT_NOT_RUN**: rerun all eight on the new SHA; then cluster (b).
