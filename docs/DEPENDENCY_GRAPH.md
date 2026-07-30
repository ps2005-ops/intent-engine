# Capability dependency graph

Maintained, not rederived. Every cycle updates it rather than rediscovering
which bottleneck sits behind which — that rediscovery cost three cycles.

**Read it top-down for "why does this matter", bottom-up for "what is blocked".**

```
MISSION
│
DECISION QUALITY                                    ← the capability
│   correct decisions · correct refusals · calibrated
│   confidence · robust across regimes · improves over time
│
├── Knowledge Quality                       [hypothesis-shaped]
│   ├── Hypothesis quality axis ............. MEASURABLE (cycle 6)
│   ├── Belief revision ..................... MEASURABLE (cycle 6)
│   ├── Expected information gain ........... MEASURABLE (cycle 6)
│   └── Knowledge graph ..................... DEFERRED, see below
│
├── Learning Value                    [infrastructure, not the goal]
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


## Deliberately deferred

Applied test: *will this be exercised within the next 5–10 development
cycles?* At roughly one gradable decision per cycle, three capabilities fail
it. They are recorded rather than built, so the architecture grows in response
to demonstrated need rather than anticipated need.

| capability | why deferred | what would unblock it |
|---|---|---|
| **Knowledge graph** — "held 17× under high inflation for mid-cap SaaS" | needs hundreds of resolutions across multiple regimes; ten cycles produce ~10 | sustained sample volume AND more than one observed regime |
| **Execution quality** | there are no fills in the market path — nothing to grade | paper orders actually filling from market decisions |
| **Calibration quality** | `A-M5` forbids accuracy claims below n≥30 | 30 resolved predictions plus a human calibration review |

The smallest version of each *is* built where it will be used: hypotheses
carry a confidence history (belief revision without a graph), and quality is
four axes rather than one — decision, outcome, hypothesis, and the two still
blocked.
