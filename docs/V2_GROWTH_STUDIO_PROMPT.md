# Session Prompt — V2.0: Founder Growth Studio (execution-grade)

*Recorded 2026-07-23; upgraded to execution-grade 2026-07-23 by human
review. Status: NEEDS HUMAN START, after V1.0.1 and ideally after real
early-user activity establishes a product-event baseline. Without real
users the Studio can be built and proven on fixtures but must not claim
it is "continuously improving" the product yet.*

## Mission

**Continuously observe approved signals, assemble evidence-backed growth
proposals, and learn from disposed experiments — without executing any
external action.** ("Autonomously" is replaced by bounded continuous
planning: the Studio runs repeatedly but holds no external authority.)

The first and only client is **Founder Intelligence**. This is not
"build a marketing system": V2.0 **reuses** Marketing, Growth, Research,
Analytics, CRM, Personal AI, and AgentOS. The only truly new work is
**orchestration around one client**.

## Mandatory extraction and reuse audit (before coding)

Produce a table — Capability | Marketing surface | Growth surface |
Reuse directly | Adapter needed | Missing — covering at least:
campaigns; briefs; drafts; claims review; quote consent; audience
selection; events; growth experiments; analytics observations; CRM
lifecycle; feedback; existing CLIs; stores and snapshots. **No
replacement subsystem may be created because the existing one is
inconvenient.** Prefer `existing records → read adapters → Studio
portfolio/index`; V2 records store orchestration and learning
references, never duplicated campaigns.

## Single-client boundary

Every record carries: product ID (`founder_intelligence`), audience,
channel, objective, evidence window, hypothesis, approval state,
measurement state. No multi-tenant customer marketing.

## Creative Strategy Loop — explicit state machine

```text
OBSERVED → RESEARCHED → HYPOTHESIS_PROPOSED → STRATEGY_PROPOSED
→ CONCEPT_PROPOSED → DRAFTED → AWAITING_REVIEW
→ APPROVED_FOR_FUTURE_EXECUTION | REJECTED
→ PUBLISHED_EXTERNALLY_RECORDED (manual/approved source only)
→ MEASUREMENT_PENDING → MEASURED → LEARNING_PROPOSED
→ LEARNING_ACCEPTED → ARCHIVED
```

In V2.0 `APPROVED_FOR_FUTURE_EXECUTION` is **terminal** unless
publication is manually recorded or received from an existing approved
source. The Studio never publishes.

## Canonical types (facts ≠ hypotheses ≠ ideas)

`GrowthObservation`, `AudienceInsight`, `GrowthHypothesis`,
`StrategyProposal`, `CreativeConcept`, `ChannelDraft`,
`ExperimentPlan`, `PerformanceObservation`, `LearningCandidate`,
`AcceptedLearning`. A post idea never becomes an accepted market
insight merely because the model generated it.

## Learning acceptance (crucial)

A `LearningCandidate` requires: predefined success metric; baseline;
observation window; sample size/evidence sufficiency; confounders;
channel context; confidence; counterevidence; **human acceptance**.
Only `AcceptedLearning` enters durable growth memory (append-only, no
silent overwrites). One post never proves "posts about X work".

## Metric-gaming prohibitions (asserted by test)

No vanity-metric optimization without a declared business objective; no
changing the success metric after seeing results; no treating
impressions as conversions; no silently comparing unequal time windows;
no declaring a winner from unavailable data; no causal claim from
correlation alone; no attributing changes to a campaign without an
experiment design.

## Canonical product funnel

```text
landing viewed → analysis started → analysis completed → result viewed
→ evidence expanded → conversation started → report created
→ early-access/signup intent → retained return
```

Every hypothesis targets one measurable transition or explicitly
declares itself a brand/research experiment.

## Product vs. marketing analytics separation

T023.5 product instrumentation remains the source of product behavior;
the Studio reads it and never rewrites or reinterprets raw events.
`Product event → Analytics metric → Growth observation → Hypothesis` —
never `raw event → marketing model invents conclusion`.

## Channel policy walls (drafts must already comply)

Reddit: no disguised promotion, community context required. Hacker
News: technical substance, no manufactured engagement. LinkedIn/X:
claim and evidence integrity. Newsletter/email: consent + unsubscribe
before any future execution. Product Hunt: no fake votes or
manufactured reviews. SEO: no keyword stuffing, doorway pages, mass
low-quality content, or fabricated expertise.

## Brand and claim integrity

Reuse existing claim/quote gates. Every draft statement classified:
SUPPORTED PRODUCT FACT | SUPPORTED MARKET OBSERVATION | FOUNDER
OPINION | HYPOTHESIS | CUSTOMER QUOTE | UNSUPPORTED — REJECT. No fake
testimonials, fabricated results, invented adoption numbers, or
unsupported superiority/competitor claims.

## Daily briefing contract (structured, every statement with evidence, timeframe, confidence)

```text
What changed / What performed / What did not perform /
What remains inconclusive / Customer-audience signals /
Product-friction signals / Competitor-category signals /
Experiments awaiting review / Measurements due /
Learnings proposed / Decisions needed from the founder
```

## Experiment definition (full, no "try three posts")

`ExperimentPlan` requires: objective; funnel stage; audience; channel;
hypothesis; control/baseline; variable changed; success metric;
guardrail metric; start/end window; minimum evidence threshold; stop
condition; approval; measurement plan; known confounders.

## Scheduler boundaries

Deterministic daily planner; idempotent run ID; captured as-of
timestamp; no duplicate daily briefing; no external action; safe rerun;
missed-run handling; budget limit; maximum model calls; scheduling
configuration is human-started.

## Canonical fixture (proves resistance to false conclusions)

Synthetic 14-day product history with: two landing-page variants; three
channels; one apparent winner invalidated by unequal exposure; one
inconclusive experiment; one useful customer objection; one repeated
unsupported competitor request; one stale audience insight; one
rejected learning; one accepted learning; one proposed experiment
awaiting approval.

## Strict non-execution tests

Assert no surface exists for: publish, send, post, deploy, modify
website, schedule external post, email contacts, start paid campaign.
Approval-ready drafts and inert execution manifests for V2.5 are
allowed; the manifests must be proven inert.

## Completion gate

V2.0 is complete when it can: (1) read real or deterministic product
signals; (2) produce an evidence-backed daily growth brief; (3)
maintain a portfolio of hypotheses and experiments; (4) generate
compliant channel drafts; (5) measure manually recorded or
already-ingested outcomes; (6) propose — not auto-accept — learnings;
(7) reproduce every briefing and experiment; (8) expose no external
execution surface. A polished morning paragraph alone is not
completion. Full regression green; T019–T023.5 and V1.0.1 web layer
unchanged; docs updated honestly.
