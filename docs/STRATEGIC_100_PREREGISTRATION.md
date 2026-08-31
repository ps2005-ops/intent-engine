# Strategic-100 preregistration — frozen before any of it runs

Written and frozen at the PRE-100 boundary. Nothing in this document may be
edited after the first Strategic-100 analysis is submitted; a cohort or a
threshold chosen after seeing results measures the chooser.

**Strategic-100 is NOT executed by this session.**

---

## 1. Cohort

`perf_progressive_matrix.QUALIFY_50` (50 companies, frozen and already run as
the PRE-100 qualification) plus a second frozen 50 drawn on the same rules:
filers and non-filers, sectors spread deliberately rather than by convenience,
and a deliberately thin tail. The cohort is stored in the repository, not in a
conversation, and its hash is recorded with the qualifying SHA.

Selection rules, applied before any company was analysed:

- the registrant, not the brand, wherever a holding company files under a
  different name;
- sector spread is load-bearing: a bank, a miner, an automaker and a SaaS
  vendor do not write the same filing;
- deliberately sparse companies are retained. A product that works only on
  mega-caps has memorised rather than generalised.

## 2. Evidence cutoff

Every analysis reads only sources retrievable at run time. `as_of` is the run
date. No backfill, no replay of documents published after the run.

## 3. Versions pinned at freeze

| component | pin |
|---|---|
| application SHA | `PRE100_QUALIFYING_SHA` |
| EconomicState | the version stamped in the dossier at run time |
| readiness contract | `ci_readiness.v1` |
| mechanism library | the manifest committed at the qualifying SHA |

## 4. What is scored, and how

**Evidence quality** — per company: usable documents, distinct families,
independent-origin count, provenance completeness (every claim carries a
source), and the share of retrieved text actually read.

**Reasoning quality** — per company: whether the thesis is entailed by cited
evidence, whether the decision implications name an action and a trigger,
and whether uncertainty is stated where evidence is thin.

**DecisionDamage** — the existing detector suite, every declared kind
exercised. A reported zero is only valid when every detector ran; a detector
that cannot fire is a finding about the instrument.

**Abstention** — a bounded, labelled refusal is a PASS outcome. A fabricated
report is a FAIL. These are counted separately and never merged.

**Latency** — CORE p50/p90/p95/max, terminal share within 120s, recorded from
the persisted lifecycle markers rather than from page polling.

## 5. Cross-company checks

- no company's evidence appears in another company's report;
- no shared-ledger counts identical across companies;
- identity resolved to one registrant per run, recorded with its CIK;
- Q&A answers name their own subject and no other cohort member.

## 6. Thresholds, frozen now

| | PASS | FAIL |
|---|---|---|
| usable or defensibly abstaining | ≥95% | <95% |
| terminal | 100% | any non-terminal |
| within 120s | ≥95% | <95% |
| CORE p90 | ≤100s | >100s |
| cross-company contamination | 0 | ≥1 |
| silent evidence loss | 0 | ≥1 |
| provenance intact | 100% of claims | any unsourced claim |

## 7. Declared limitations, recorded before the run

- **Calibration.** The cohort is one snapshot in time. Nothing here measures
  whether a recommendation was right, only whether it was defensible on the
  evidence available. Outcome calibration needs a horizon this run does not
  have.
- **Learning.** Belief formation reads fresh evidence only, so a second pass
  over the same cohort does not measure learning; it measures repetition.
- **Feedback and restart durability** remain `BLOCKED_INFRASTRUCTURE` and are
  not Strategic-100 blockers under the governing decision.
- **Concurrency** is bounded by the preview's CPU share and is recorded, not
  bought.
