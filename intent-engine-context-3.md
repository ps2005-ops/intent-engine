# Intent Engine — Full Project Context
*Last updated: after the data-foundation pass closed (SQLite migration,
two-tier summaries, quiet-observer digest built), the simulator's
evaluation-stage was designed (build-deferred), Part 5 (the iteration-loop
layer) was designed, and its first build step — the diagnosis-registry
replay — was issued. Paste this at the start of any new Claude chat (not
Claude Code) for full context. If this doc conflicts with what Claude Code
reports from the actual repo, trust the repo.*

---

## 1. The original vision, and how it evolved (read this to understand WHY)

**Original vision:** "The Intent Engine" — AI that infers *intent* (of a
founder, a person, a company) and acts on it. Three products on one
architectural pattern: a business-decision risk simulator (Pre-Mortem
Machine), a personal voice agent (Cognitive Delegate) for real family
users, and trading intent inference. A 26-week plan and Stage A-E ladder
originally structured the work.

**The major evolutions, in order, each with its reason:**

1. **Week/stage numbering was abandoned** — real work kept happening
   outside any planned stage because it was right at the time (the
   Scale/Leverage/Luck enrichment, the architecture audit, image
   verification). Tracking switched to "what's validated with real
   evidence."

2. **The simulator was declared the flagship** (user decision) — clearer
   input→output loop, no channel/multi-user complexity, faster feedback
   cycles, real positioning wedge (regret-avoidance framing). The Delegate
   remains the bigger vision.

3. **Live stock-price prediction was REJECTED, permanently** — market
   efficiency + no access to order-flow/consensus data. Reframed instead
   as *outcome calibration*: test the simulator's judgments against real
   historical and future outcomes and fix its rules against new cases.
   This is NOT RL (no weights train); it is the same loop shape as
   scrap-metal's weigh-in calibration.

4. **The scrap-metal domain (dad's business) forced the project's biggest
   technical lesson** — a ~12-iteration supervised arc (naive attempt →
   structural diagnosis → fix library → problem reframing → honest floor)
   that produced the fix library (§3) and the realization in §2.

5. **The user's own reframes repeatedly beat further engineering** — the
   base-rate/deviation pivot (scrap) and the structured-priors framing
   came from the user, not iteration. Recorded because it defines the
   honest ceiling of automation (§6, Part 5).

6. **"The iteration loop is the product"** — the user named the real
   bottleneck: the supervised iteration process itself is what must become
   autonomous for day-one quality with new users. This reframed the whole
   roadmap (§6).

## 2. The single most important finding

The scrap arc took ~12 supervised iterations with a human supplying "not
good enough, iterate" at every gate. The product's day-one quality depends
on the agent running that loop itself — try → machine-checkable bars →
structured diagnosis → targeted retry → surface only on pass or proven
honest floor. This layer is now DESIGNED (Part 5, §6) with one crucial
honest boundary: **the loop automates convergence, not reframing.** The
base-rate pivot — the single best move of the whole project — fired while
every bar was passing; no failure-triggered mechanism can produce that
class of insight. The loop is a triage nurse, not a surgeon.

## 3. The proven fix library (apply BEFORE inventing new solutions)

- **Closed taxonomies over free text** — free-text extraction invents its
  own vocabulary every run (proven twice).
- **Information hiding beats instruction** — a judgment call receives ONLY
  inputs it should condition on; labels/baselines/history applied in code
  afterward. Three confirmed anchoring incidents, all fixed by structural
  withholding, never by "please ignore."
- **Deterministic code over model assertion** — scores, comparisons,
  citations, inclusion decisions: computed, never asked of the LLM. The
  strongest form (now house style): the model's schema physically lacks
  the field (Stage-2 citations, digest gating) — no channel to fabricate.
- **Voting over single calls** — 5-vote modal aggregation; within-range
  refinement only on unanimity.
- **Reliability-gate every new extraction** — 5+ runs, real distributions,
  before anything ships. Two builds were correctly stopped by failed gates.
- **Strengthened negative instruction** — the proven fix when a model
  fabricates rather than saying "none"/"unclear."
- **Base rates + deviation over regression** — deterministic base rate
  carries the number; the model only judges deviation from typical.
- **Structured/causal priors over statistical rediscovery** — bake known
  structure into schema/code; cross-field coherence checks exploit known
  dependencies.
- **Imitation-vs-criterion boundary** — the correction loop is an
  imitation-learner; criterion-shaped corrections (thresholds, verdicts)
  break it (confirmed empirically). No criterion mechanism exists yet.

## 4. What's built (all verified with real evidence)

**Simulator (flagship):** mature machinery — Scale/Leverage/Luck
extraction, Luck Test module, regret-avoidance narrative, length ceiling.
**BUT backtest v1 (18 real cited historical cases) found a degenerate
classifier**: 66.7% directional accuracy vs 61.1% always-predict-failure
baseline, achieved by flagging 17/18 as risky — 14.3% specificity on real
successes. Diagnosis: retrieval + mapping with NO EVALUATION stage (in
analogical-reasoning terms) — it never checks whether a retrieved
precedent structurally applies. The evaluation stage is now fully designed
(4 closed-taxonomy structural-match fields: bet magnitude relative to
resources, reversibility, feedback horizon, traction; tag-once-offline
corpus, deterministic matching; isolated extraction that never sees the
risk narrative) but BUILD-DEFERRED until held-out validation cases exist —
rule changes must never be tuned against the same 18 cases (overfitting
guard). Corpus circularity was checked: reference set ≠ backtest set.

**Cognitive Delegate:** all three family domains work in the CLI —
dad's scrap-metal analysis (see below), mom's fitness captions, brother's
music captions (both seeded cold-start on cited content frameworks;
prefix-leak and no-pillar-rotation limitations found live and tracked).
Voice pipeline: PersonalContext wired, real Calendar integration (blocked
on user's one-time local OAuth), Gmail stubs, STT (faster-whisper),
/verify, /scrap, /weighin, digest at session start. Pattern-Watcher +
suggestions + shadow-guess-and-correct loop (3 real bug fixes: recipient
blindness, position-recency bias masquerading as correction-following,
style/content separation; known gap: content doesn't survive a 2nd
correction).

**Scrap-metal (dad's) — complete, the reference arc:** isolated vision
judgment (zero prior-lot text) → 5-vote classification → cited base-rate
table (alternators 10-14% Cu, US Bureau of Mines dismantling study) →
within-range refinement on unanimous votes → deterministic deviation join
→ tail trim → ferrous as arithmetic complement → coherence check → honest
cited/uncited rendering. 4 of 8 real photos at ≤4pp copper width (best
1.1pp); the rest ship honest wider floors with reasons. The
compositional-estimation approach was RETIRED (performed worse than a
lookup table — hallucinated quantities, >100% bounds) — that retirement
IS the base-rate/deviation reframe. Weigh-in calibration
(/weighin) exists — the only path to <3pp — user chose not to require
real weigh-ins for day one. 9 real photos at tests/fixtures/scrap_metal/.

**Data foundation (just closed):** SQLite migration (4 stores, signatures
unchanged, 18 call sites untouched, row-counts verified);
EntityMemoryRecord.artifact_kind added (schema half of un-masquerading
caption records — consumption logic deliberately not built yet); Tier-2
summary layer (EntitySummaryRecord, citations computed-not-claimed —
model schema physically lacks the id field); quiet-observer digest BUILT
(deterministic quality bars: N≥3 evidence, M=2 trend persistence, novelty
via (entity, dimension, direction) identity, cap 3 ranked by evidence,
silence = no digest object at all, verified across 4 engineered cases +
silence run + live CLI demo).

**Backtest track:** the 18-case retrospective ran (results above);
forward paper-log (4b) designed conceptually, not built — it is how
held-out cases accumulate for the evaluation stage's validation.

**Suite: ~402+ passing, zero regressions maintained throughout.**

## 5. Honest gaps (do not let these disappear)

- **Almost nothing has real usage.** Phase-0 trial with dad: tooling built,
  NEVER STARTED. No WhatsApp bridge (proposal exists, gated on Phase 0).
  Every accuracy ceiling (sub-3pp scrap, simulator discrimination) is
  gated on real usage data only the family can generate.
- The marketing-agent vision (platform ingestion, video editing from
  long-form, posting, tracking) is ~90% unbuilt — caption generators are
  the only slice. Video-edit pipeline (transcribe → model selects segments
  → ffmpeg cuts deterministically) is the recommended next concrete slice
  when that track resumes; platform APIs (TikTok/Insta restricted) are a
  vendor decision.
- Criterion-shaped corrections unsupported. Content doesn't survive a 2nd
  correction. gmail_read triggering, recipient resolution, calendar OAuth
  (user-side), argparse coverage — all tracked.
- Comprehensive cleanup pass: deliberately deferred to end of build phase
  (audit-then-archive approach agreed).

## 6. THE PLAN — current state of every thread

- **In flight now:** Part 5's first build step — the diagnosis-registry
  replay: encode the 6-signature registry (failure signature → fix
  category) as data + matcher, replay it against the scrap arc's own
  documented failures (symptoms-as-presented, no hindsight), score
  match/miss per episode, distinguish registry-gaps from confirmed
  scope-boundaries. The replay's verdict decides whether Part 5 v1
  proceeds, revises its registry, or gets rethought.
- **Part 5 (designed):** try/bars/diagnose/retry loop. v1 scope:
  extraction/classification reliability only. Honest-floor exit requires
  human confirmation. Base-rate-pivot-class reframing explicitly outside
  scope. Budget with three exits.
- **Evaluation stage (designed, build-deferred):** waits on held-out cases
  (forward paper-log accumulation or a second sourcing pass).
- **Observer (built).** Foundation pass (closed).
- **Queued after Part 5's replay verdict:** the next build fork gets
  decided with everything on the table — candidates: forward paper-log
  (4b), video-edit pipeline slice, evaluation-stage build (if validation
  path exists), Phase-0 trial (needs no code, only the user).
- **The single highest-value non-code action remains:** real usage — dad's
  Phase-0 relay and/or 2-3 real weigh-in numbers.

## 7. How to engage with this project

- Tight process: propose → tradeoffs → flag deferred/unresolved → verify
  with real evidence. Checkpoints show real output; "looks done" is
  rejected. Claude Code has itself refused to record unverified numbers —
  hold that standard bidirectionally.
- Apply §3 before inventing solutions — most new failures are old ones in
  new costumes (proven repeatedly).
- Classify every new capability request: qualitative-judgment-from-text
  (prompting problem) vs needs-data/infrastructure-that-doesn't-exist
  (vendor decision or hard wall). Say which, plainly.
- Firm reasoned pushback is valued — but when the user reframes a problem
  well, rebuild around it (the two best moves of the project were user
  reframes).
- One domain at a time in the live system; isolated research scripts may
  run parallel. Design proposals resolve open questions explicitly or
  flag them — never silently default.
- Overfitting guard: rule/model changes are validated on NEW/held-out
  cases, never re-tuned against the data that exposed the failure.

---

*[Your question/request goes below this line.]*
