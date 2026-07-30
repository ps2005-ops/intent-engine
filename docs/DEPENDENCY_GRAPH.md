# Capability dependency graph

Maintained, not rederived. Every cycle updates it rather than rediscovering
which bottleneck sits behind which — that rediscovery cost three cycles.

**Read it top-down for "why does this matter", bottom-up for "what is blocked".**

```
DECISION QUALITY                                    ← the capability
│   correct decisions · correct refusals · calibrated
│   confidence · robust across regimes · improves over time
│
├── Learning Value                          [partially measurable]
│   ├── Resolution Quality .................. MEASURABLE (cycle 5)
│   ├── Novelty ............................. MEASURABLE (cycle 4)
│   ├── Information Gain .................... blocked: no knowledge base
│   └── Calibration Impact .................. blocked: A-M5, needs n≥30
│
├── Evidence Quality                                 [measurable]
│   ├── Outside sources ..................... 1/11  (cycle 2 fix)
│   ├── Source diversity .................... round-robin selection
│   └── Freshness ........................... dated evidence enforced
│
├── Universe Quality                        [partially measurable]
│   ├── Sectors ............................. 3 of 10
│   ├── Market caps ......................... FIELD DOES NOT EXIST
│   └── Regions ............................. FIELD DOES NOT EXIST
│
└── Prediction Quality                               [n=1, low conf]
    ├── Market signal ....................... baseline_momentum.v1
    └── Sample size ......................... 1 per cycle vs 30 needed
```

## Edges that have actually bitten

| if this is fixed | this becomes binding | learned in |
|---|---|---|
| evidence collection | outside-source approval | cycle 2 |
| outside-source approval | market evidence (nothing gradable) | cycle 3 |
| market evidence | grading — and grading refusals, not just positions | cycle 5 |
| grading | sample size (1/cycle vs 30 for A-M5) | predicted |
| sample size | universe breadth, and the missing cap/region fields | predicted |

The last two rows are predictions. They are written down so the next cycle
tests them instead of rediscovering them.

## Standing rule

A node is not "done" when its code exists. It is done when the node **above**
it moved, measured the same way before and after.
