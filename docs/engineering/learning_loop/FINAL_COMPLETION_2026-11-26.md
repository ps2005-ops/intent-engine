# Intelligence integrity: final completion and handover (2026-11-26)

## Status labels

| Label | Meaning |
|---|---|
| IMPL | implemented and tested |
| OPER | running in production |
| PROM | promising on held-out data |
| HIST | validated on an untouched historical holdout |
| PROSP | validated on forward outcomes |
| COMM | commercially validated |

**Nothing in this document is PROSP or COMM.** Evidence files are in
`reports/learning_loop/`.

## 1. Commits and runtimes

* **Final code:** f7690938 on `integration/unified-2026-11-25`, guard
  13,115 passed.
* **Market runtime:** `~/ie-market-runtime-v2` @ f7690938 (launchd
  day/night/health).
* **Learning runtime:** `~/ie-learning-runtime` @ f7690938.
* **Previous market runtime:** `~/ie-market-runtime` @ 92ce0f39, kept for
  rollback.

## 2. Backups and rollback

* `~/intent-engine-safety-backups/canonical-ledgers-20261125-222913`:
  790 files, 0 restore mismatches, July `integrity_check=ok`, taken before
  any write today.
* `plists-20261125-222913/`: plists and crontab.
* `prospect100-research-cache-20261125-231939`: 8,481 files, 925 MB,
  checksummed.
* Rollback scripts: see §16.

## 3. Grade invalidations (APPLIED, OPER through the store view)

* **How 33 were proposed.** The earlier figure of 27 covered only the demand
  families. The full audit adds 2 market_share_seeking and 3 pricing_power
  grades (5), plus Infosys: 78 days apart, but the same Q1 FY27 report.
* **30 applied.** Three proposals were withdrawn after rechecking, because
  they were graded by a genuinely later and different figure: Etsy (11 days,
  guidance then result), P&G (35 days) and Canadian National (31 days).
* **Applied safely.** Under the market cycle lock, append-only and
  idempotent: a rerun appended 0.
* **Downstream effect.** The store masks the reconciliation AND the
  belief_update it caused, so no consumer filtering on record type counts
  them. On a copy, 33 beliefs' posteriors change (mean |Δ| 0.067). The
  original lines are untouched.

### Before and after

| Measure | Before | After |
|---|---|---|
| Valid grades | 47 (28 confirmed / 19 contradicted) | 17 (9 / 8) |
| Hit rate | 0.60 | 0.53 |
| Probabilistic calibration | "Brier 0.2365 vs 0.2408, beats climatology" | **PRE_CALIBRATION**: n=17 < minimum 20. The skill claim is withdrawn |
| Mechanisms tested | 4 of 16 | 3 of 16 gradeable; demand_weakening still the most contradicted |

**Re-grading.** The binder no longer accepts another account of the
opener's report. The new rules come from the qualification cycle (§10).
The next production cycle will write 13 genuine later-quarter grades.

## 4. OLO (APPLIED, eligibility OPER after the switch)

* **Applied.** 104 corrections (UNRESOLVABLE → INELIGIBLE), idempotent.
  Outcomes now read: 359 resolved, 104 ineligible, 18 pending, 0
  unresolvable.
* **Point-in-time eligibility.** INELIGIBLE needs an issuer deregistration
  (15-12B/G) AND no price near the decision.
  * Form 25 alone does not count: it excluded NEE, PG and SHOP, all of which
    still trade.
  * A delisting inside a forecast window exits at the last tradable close,
    so the forecast is still evaluated.
  * Tests cover acquisition, deregistration-with-prices, an exchange
    transfer and a feed outage.
* **Ticker changes and other corporate actions** have no specific handling
  beyond these rules; an instrument whose price series ends is treated as
  above.
* **Isolated cycle.** It classified 41 newer OLO records INELIGIBLE on its
  own. OLO can no longer add evaluable decisions.

## 5. Bayesian dependence (IMPL, OPER after the switch; decisions stay in shadow)

**Model:** a local-level Kalman filter per series, plus the proxy's SHARED
construct error, which cannot average out. q and the idiosyncratic noise
come from Var(Δy) = q + 2r, split evenly (a stated assumption, with
sensitivity reported).

Live, 24 monthly quits readings (FRED JTSQUR first releases):

| Method | Posterior sd | Effective n |
|---|---|---|
| Original: independent | 0.0204 | 24 |
| Interim: latest only | 0.1000 | 1 |
| **Corrected** | **0.1033** | **0.94** |

* Sensitivity to the split: 0.1018–0.1033.
* Tests cover repeated, independent, contradictory and missing observations
  and next-cycle re-reads.
* **Downstream:** collective_state publishing, then the founder dashboard
  panel. The founder contract REFUSES collective constructs in any decision
  (zero promoted), so this is operational and not validated.

## 6. The ten thesis movements

**Five JPMorgan movements: defect, fixed.**

* The CAPITAL_INTENSITY exposure pattern was the only one without an
  ownership requirement.
* When the canonical patterns broadened to the plural "capital
  expenditures", a 10-K sentence of economy-wide statistics became
  JPMorgan's own exposure: "the 1,000 largest U.S. public companies
  represent 70% of the $2.2 trillion in total capital expenditures". It was
  ingested Aug 5, line 35.
* So this was old information re-processed by a changed reader, with the
  wrong owner.
* The pattern now requires company ownership (first person, or a named
  actor's capex plan, boost or cut).
* The qualification cycle no longer moves those theses. A regression test
  pins the sentence.

**Five América Móvil movements: legitimate.** The company's own Nov-25
filing reports financing costs up to 22.6 billion pesos on FX losses. That
is new information about its own exposure.

## 7. Regime protocol amendment A1 (IMPL, OPER in the weekly report; paper cohorts from 2026-12-09)

* **Correction to an earlier finding of mine.** The historical panel's DFF is
  also daily (366 cells/year). There was no train/serve skew: replay and
  forward shared the defect.
* **The defect.** v1's "policy change over a year" was a 12-DAY change.
  Across 80 quarterly origins (2007–2026), v1 fired POLICY_TIGHTENING or
  POLICY_EASING **0 times**.
* **v2.** Compares completed calendar-month means a year apart, for any
  input frequency, excluding the incomplete current month.
  * v2 recovers 2008–09 and 2020–21 easing, 2017–19 and 2022–24
    tightening, and 2025–26 easing.
  * No other regime changed at any origin.
* **Registration.** In `paper_validation/protocol.py` "amendments", effective
  from 2026-11-26. Decisions before then keep v1 (the replay and the Nov 9
  cohort are untouched). The protocol hash for new registrations changes
  from d6483796 to 354e1bf9.
* **Weekly report.** It uses v2 and prints each label with its value,
  threshold, margin and a BORDERLINE flag.
* Not evaluated for forecasting value; the replay found regime features
  negative under v1.

## 8. Evidence reader v2.1 (PROM; used to admit and direct demand grades)

Two held-out samples, labelled before scoring, by a single annotator:

| | v1 | v2.1 |
|---|---|---|
| Sample 2 accuracy (fresh, n=61 clear) | 0.57 | **0.89** |
| Demand-claim precision | 0.35 | **0.73** |
| Recall | 0.80 | **0.87** |
| False demand claims | 22 | **4** |
| Surprises found | 3/9 | **8/9** |

* **Remaining failure class:** attribution (case studies, previews). This is
  now refused at grading time by explicit rules.
* **Status.** Not promoted to belief FORMATION; that needs independent human
  labels. Used only to admit demand grades and set their direction, where it
  is strictly more conservative than v1.

## 9. Human packages (ready; nothing invented)

* `reports/learning_loop/human_annotation/`:
  * 19 ambiguous examples with no model output;
  * `ANSWER_SHEET.csv`, `INSTRUCTIONS.md`;
  * `score_annotations.py`, which validates labels, records disagreements
    and scores both readers only on agreed, non-INSUFFICIENT labels.
* `reports/learning_loop/enterprise_review/`:
  * 5 blind pairs with ids and evidence;
  * 8-criterion `RUBRIC.md`, `REVIEW_SHEET.csv`;
  * the key in a separate file.

## 10. Grading admissibility (found during qualification, fixed)

Reopening the 30 invalidated expectations produced 21 immediate re-grades,
about 15 of them defective:

* previews ("Reports Next Week: Wall Street Expects…");
* analyst actions on other companies ("JPMorgan Has Lowered Expectations
  for Costco");
* customer case studies (FOOTDISTRICT on Shopify);
* supply and surprise accounts;
* recaps of the same quarter, 47–57 days later.

Fixed rules:

* the subject must be named;
* no preview, comparison, analyst action or case study;
* the grade must not name the same quarter (with or without the year), nor
  a quarter already reported by the basis date;
* no shared reported figure;
* at least 75 days after the opener, unless it names a later quarter;
* for demand families, a demand movement under v2.1, which also sets the
  direction.

Result on the production copy: 13 genuine later-quarter grades (Shopify Q3
revenue +32%, Sea Q3 +43%, Toyota Q3, Etsy Q3, …). Each rule has a
regression test, and a mutation of the admissibility guard is caught.

## 11. FX4 (OPER; 0 forward registrations, legitimately)

* **Zero because:** no guidance revision has occurred since registration
  began on 2026-11-25. Backdating is refused.
* **Defect fixed:** actor identification mapped only audited instruments
  (10 of 28 subjects unmappable). It now uses the runtime research universe.
* **Coverage limit:** quarterly revenue is only in SEC XBRL for US-GAAP
  filers. ASML, Infosys, HDFC and Sasol file annual IFRS 20-Fs.
* **End-to-end historical fixture** (never written to a ledger):
  * declared intention: "Caterpillar Raises Sales Outlook", Aug 4;
  * observed behaviour: Q1 acceleration +4.2%;
  * expectation: next-filed quarter accelerates;
  * rule: SEC XBRL, walled on the filing date;
  * resolved UP, correct.
  * Persistence also predicted UP, so this case does not discriminate.

## 12. Capability matrix (updated)

| Mechanism | Substantive computation | Inputs valid | Consumed downstream | Influences | Evaluated | State |
|---|---|---|---|---|---|---|
| Bayesian (collective) | YES | yes, after the FRED mirror and dependence fix | collective_state, dashboard | shadow only (contract refuses in decisions) | no | OPER, shadow |
| Hidden state | YES | evidence-dependent | dossiers | display | no | OPER, unevaluated |
| Econometric method checks | YES | yes | gates causal language | causal wording | built-in vs persistence | OPER |
| Research bandit | YES | yes | research allocation | which company is researched | not against a random policy | OPER, unevaluated |
| Causal-edge gating | YES | yes | thesis wording | display | no | OPER |
| Level-k | YES | — | state export | display | no | OPER, unevaluated |
| Strategic interaction | constructs and rejects | — | none | none | — | DISCONNECTED (FX6 BLOCKED) |
| Regime | YES (v2) | yes, after A1 | weekly report, paper D features | report; paper shadow | negative under v1 | OPER |
| Economic transmission | not in the cycle | no exposure map | paper policy only | paper shadow | Holm p=1 | BLOCKED (FX3) |
| Business graph | NOT CALLED | — | — | — | — | DISCONNECTED |
| Macro expectations | NOT CALLED | no historical consensus | — | — | — | BLOCKED by data |
| Calibration | YES | 17 valid grades | learning health | none | PRE_CALIBRATION | OPER |
| Evidence interpretation | YES (v2.1 for grading) | — | grading | expectation outcomes | 2 held-out samples | PROM |
| Outcome resolution | YES | yes | signal outcomes | learning reports | 33 tests, mutation-checked | OPER |
| Instrument eligibility | YES | SEC filings plus prices | resolver | INELIGIBLE state | tests | OPER after the switch |

## 13. Dossier corrections

* **19 audited:** 16 withdrawn and 3 qualified, through the append-only
  sidecar. Dossiers are unchanged.
* **Strategic block:** the claim was printed for 5 companies before and 0
  after.
* **Recommendations:** `reasoning._build_thesis` does not read these
  beliefs, so none changed.
* **Not done: browser screenshots and full surface sweep.** That covers
  Full Analysis, Strategic Answer, X-Ray, History Rewind and the dashboard.
  They read dossiers through the same `strategic_contract.load`, so they
  inherit the correction. It still needs the browser pass of the 100-company
  qualification program (§17).

## 14. Learning health after the corrections

* **Status:** still LEARNING_DEGRADING. Partly by construction: removing
  invalid grades lowers "validated knowledge per day".
* **The false DEGRADED health status** (stale lock since August) is fixed:
  the qualification cycle reports overall OK.
* **Root cause of "never tested", corrected.** 12 of 16 belief mechanisms
  are UNFALSIFIABLE_BY_OBSERVATION, with no observation channel at all. That
  is why 189 of 206 beliefs are untested, not just open windows. Testing
  them needs per-family observation rules, listed as the top engineering
  priority.
* **Evidence volume:** 1-day 356 accepted (a new-code cycle) against a
  7-day average of 107. More volume is not better learning, and none is
  claimed.

## 15. Forecast and scheduler contracts

* **The 977 forecasts:** Nov 9 cohort, exit Dec 10, resolvable Dec 11.
* **Econ:** 13 expectations, due Dec 25.
* **Next paper cohort:** about Dec 9, under amendment A1 with the new
  protocol hash.
* **Untouched:** all contract hashes are unchanged; no prediction was
  modified.
* **Retired:** the 06:00 July resolver, the 18:30 generator and the LLM
  regime report. All are commented out with their original lines.
* **Learning cycle:** runs with ANTHROPIC_API_KEY unset.

## 16. Runtime switch (OPER)

| Step | Result |
|---|---|
| Qualification 1 (9b4910a8, isolated copy) | 17/17 ok. It exposed the grading-admissibility defect (§10) and a stale-looking runtime sha (a history artifact, explained) |
| Qualification 2 (f7690938, isolated copy) | 17/17 ok. Behavioural 48 nodes; Bayes (local level) 24 readings worth 0.94, sd 0.103; health OK (lock held, not stale); learning health reports `f7690938`; 41 OLO INELIGIBLE; 13 genuine later-quarter re-grades; 5 thesis revisions (America Móvil only); shadow momentum recorded. Live runtime byte-identical |
| Pre-switch | No cycle, lock free. Backup `canonical-ledgers-20261126-004830` (790 files, 0 mismatches); plists and crontab saved |
| Secrets | `.env` symlink; FRED and Tiingo load under file and `-m` invocation (a `-c` probe is cwd-dependent and was misleading) |
| Switch | Only `PYTHONPATH` changed in the three plists, to `~/ie-market-runtime-v2/src`. Learning runtime re-pinned to f7690938 after a dry run of its steps against production (ledger hashes unchanged) |
| First production run (scheduled health, at load) | `git f7690938671a on HEAD clean`, exit 0, lock free |
| Controlled production verification | `night --dry-run --root ~/intent-engine-market` on the installed code: 17/17 ok, production ledgers byte-identical. This is CONTROLLED execution in rehearsal mode, not a scheduled cycle |
| First SCHEDULED cycles on f7690938 | day 06:30 and learning 19:15 on 2026-11-26, then night 20:30. Not yet observed at the time of writing |
| Rollback | `~/intent-engine-safety-backups/ROLLBACK_market_runtime_20261126-004830.sh` |

## 17. 100-company handover

See HANDOVER_MANIFEST.md.

## 18. Remaining blockers

See HANDOVER_MANIFEST.md, "Pending".
