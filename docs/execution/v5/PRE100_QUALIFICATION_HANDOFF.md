# PRE-100 → Strategic-100 handoff

**PRE-100 evidence is frozen. Strategic-100 must not rewrite it.**

```
PRE100_QUALIFYING_SHA = cc79dc8e19014d2da2d7b7e279f0035398981034
local == origin(v6/unified) == origin(feat/founder-market-integration) == live /version
```

Every live result below was measured against that SHA on
`https://intent-engine-preview-bridge.onrender.com`.

## 1. How the tree was proven

The pre-commit hook runs pytest against the **working tree**, not the index,
so a green guard says nothing about what the commit then captures. Two live
sessions shared this worktree and one commit (`bbd442fe`) landed red because
of exactly that gap. From `a2ef6ef3` onward every commit records a working-tree
fingerprint before and after the guard and is only accepted when they match
and `git status` is empty — which makes committed content identical to guarded
content rather than merely adjacent to it.

| commit | guard | tree before == after |
|---|---|---|
| `a2ef6ef3` | 10785 passed | yes, 0 divergent |
| `dd1511f0` | 10786 passed | yes, 0 divergent |
| `4908ad99` | 10794 passed | yes, 0 divergent |
| `cc79dc8e` | 10803 passed | yes, 0 divergent |

Concurrency: the second session's last write was 07:33:57 and it made no
further change to any tracked file. It had pushed `78a32075`; every commit
here is a clean fast-forward descendant of it. Nothing of theirs was reset,
amended or discarded.

## 2. The defects this qualification found and repaired

Each was found by measuring, not by reading code.

1. **The pattern gate was never told who the company was.** `_registrant_for`
   resolved the filer from `meta["cik"]`, populated only when a filer is typed
   with no website. Every domain-entry run carried `""`, so no registrant was
   fetched, `profile_for` answered UNKNOWN, and UNKNOWN admits the whole
   12-pattern library. That is what put the identical
   "Whether a supply commitment should be treated as fixed or renegotiable"
   on Synopsys, Emerson and Lowe's.

2. **Document ownership read the same empty field** (`_strategic_report`), one
   producer upstream. With no subject, `subject_documents` skips its
   `/data/<cik>/` filter entirely, so a third party's 10-K could supply the
   signals that qualify a pattern. Ownership now resolves the subject the same
   way filing discovery does, so the two cannot disagree.

3. **An apostrophe cost a company every filing it has ever made.** `_tokens`
   split on it: "Lowe's Companies" → `{lowe, s, companies}` against the SEC's
   own `LOWES COMPANIES INC` → `{lowes, companies}`. Containment failed,
   `resolve_cik` returned None, and with no CIK there were **no EDGAR
   candidates at all**. Found by the no-pick live proof; the autocomplete had
   this repair and the server-side fallback did not.

4. **A follow-up answered a different question.** `_conversation_context` had
   been declared on the webapp since the dead second engine was removed and
   **nothing had ever written to it**. Asked "Why does that matter?", Synopsys
   returned question one's refusal verbatim and Emerson question two's answer
   verbatim — while both scored 6/6.

5. **A memo required `__init__`**, breaking a legitimate test double that calls
   `subject_cik` unbound.

6. **A tenant-leak assertion searched generated ULIDs** — `"CRM" not in
   json.dumps(req)` matched `01M1P271GA**CRM**YJZ9WTBCK9DJP`. A test that can
   fail without the defect can pass while the defect is present.

No evidence threshold was moved, no abstention removed, no model given more
freedom, and no company or sector is named in product code.

## 3. Instrument defects corrected (they produced false product findings)

- The harness posted **3 of the 7 fields** `confirm()` writes. Without
  `suggest_confirmed` the server never enters the confirmed-pick branch, so
  every analysis it had ever driven opened with `cik=""`. **The measured
  collapse was in part harness-made**; the product defect is real and is
  proven separately on the no-pick path.
- The counter-evidence detector read `/brief` for a heading produced only by
  the `/answer` narrative, reporting an absent section for every company.
- `meta_cik`/`subject_cik`/`registrant_sic` were fetched and not copied into
  the row, so the no-pick proof reported blanks for the fields it existed to
  establish.
- The matrix reporter compared a list against an integer, and compared thesis
  strings **including the company name** — which cannot see a template.

## 4. Live no-pick repair proof (the flow that was broken)

Typed name + website, no suggestion confirmed, on the qualifying SHA:

```
confirmed_pick   False          subject_cik      60667
submitted_cik    ""             registrant_sic   5211
meta_cik         ""             business_model   SCALE_RETAIL
capacity_ahead_of_demand        EXCLUDED
counterevidence  PRESENT        context_retained True
defects          []
```

Lowe's is **outside** the curated manifest, so `SCALE_RETAIL` is reachable
only through registrant SIC 5211, which requires a server-recovered CIK. The
classification is itself the proof that recovery worked.

Offline, on live SEC, with `meta["cik"]` empty throughout
(`scripts/thesis_chain_proof.py`): **0/5 UNKNOWN** — Synopsys
SUBSCRIPTION_SOFTWARE, Emerson DESIGN_AND_MANUFACTURE, Lowe's SCALE_RETAIL,
BlackRock BALANCE_SHEET_OR_NETWORK, SLB COMMODITY_PRODUCER.

## 5. Final ten, confirmed-pick path, frozen SHA

10/10 FULL_REPORT, 10/10 defect-free, 10/10 canonical identity.

| Company | AC ms | Business model | Pattern | Ack | CORE | QA-ready | Docs | Q&A | Ctx |
|---|---|---|---|---|---|---|---|---|---|
| Synopsys | 204 | SUBSCRIPTION_SOFTWARE | — | 0.81 | 58.3 | 88.4 | 15 | 6/6 | yes |
| Emerson Electric | 181 | *(starved, 3 docs)* | — | 0.79 | 25.3 | 37.6 | 3 | 6/6 | yes |
| Lowe's Companies | 214 | SCALE_RETAIL | — | 0.81 | 68.7 | 97.6 | 5 | 6/6 | yes |
| BlackRock | 223 | BALANCE_SHEET_OR_NETWORK | — | 0.67 | 55.6 | 77.8 | 6 | 6/6 | yes |
| Amgen | 231 | REGULATED_PRODUCT_OR_PROVIDER | — | 0.65 | 55.3 | 73.6 | 13 | 6/6 | yes |
| SLB | 185 | COMMODITY_PRODUCER | capacity_ahead_of_demand | 0.86 | 55.8 | 65.2 | 7 | 6/6 | yes |
| T-Mobile US | 307 | CONTRACTED_OR_RATE_BASE_ASSETS | capacity_ahead_of_demand | 1.45 | 94.3 | 121.8 | 5 | 6/6 | yes |
| Old Dominion | 193 | PEOPLE_OR_ROUTE_BASED_SERVICES | — | 0.72 | 84.0 | 119.8 | 12 | 6/6 | yes |
| Novartis | 316 | REGULATED_PRODUCT_OR_PROVIDER | — | 1.59 | 72.7 | 89.9 | 6 | 6/6 | yes |
| Sprouts Farmers Market | 193 | SCALE_RETAIL | — | 1.99 | 94.3 | 120.8 | 9 | 6/6 | yes |

**Aggregates.** CORE p50 58.3s, p90 94.3s, max 94.3s, ≤120s **10/10**.
Strategic-QA-ready p50 88.4s, p90 120.8s. Autocomplete median 204ms, p90
307ms (prefix proof 8/8, including `lowe`, `lowe's`, `Lowe's Companies`).
Median documents 7; all three evidence roles 8/10; counter-evidence present
10/10. Q&A 60/60 owned and leak-free. Terminal 10/10, identity 10/10, foreign
company 0, spinner-after-terminal 0, internal-vocabulary leaks 0.

Against the frozen preregistration gates (§6 of
`STRATEGIC_100_PREREGISTRATION.md`): terminal 100% ✓, within 120s ≥95% ✓
(100%), **CORE p90 ≤100s ✓ (94.3s)**, contamination 0 ✓.

## 6. Thesis gate

Comparing skeletons with the subject removed — comparing full strings would
count "X appears to be…" and "Y appears to be…" as two theses and miss a
template entirely:

- **7 companies across 5 model classes asserted no reading**, each with a
  *different* eligible set (11, 7, 11, 9, 11, 9, 7 patterns). The gate
  discriminated; no pattern met its evidence threshold. That is an
  abstention, not a collapse.
- **SLB and T-Mobile share `capacity_ahead_of_demand`** across two model
  classes. Judged: an oilfield-services company and a wireless carrier both
  commit capital to capacity against demand they do not control. The
  mechanism is genuinely shared, both are labelled low-confidence, and §4
  permits same thesis on same mechanism. **Explained.**

```
UNEXPLAINED_TEMPLATE_COLLAPSES = 0
```

Company-specific mechanism present 2/10 — the two that asserted a reading.

## 7. Known limitations, measured rather than assumed

1. **The verified-analyst layer did not run on any audited run.**
   `reasoning_provenance = pattern_library` on 9/9 runs carrying an audit, so
   the strategic reading is library scaffolding labelled as a low-confidence
   hypothesis, never analyst-verified prose. The product behaves correctly —
   it explicitly refuses to promote scaffolds to findings — but **the
   preregistration's "reasoning quality" axis would score the pattern library,
   not the reasoning.** This instrument did not capture whether the cause was
   `AnalystUnavailable` or critic rejection; `/runs/<id>/telemetry` →
   `reading` answers it in one run. **Resolve before Strategic-100.**
2. **Retrieval varies run to run.** Emerson returned 6 documents at 09:00 and
   3 at 09:59 on the same SHA, falling below `may_synthesize` and producing no
   audit. Now legible via `thesis_error` rather than an empty cell.
3. **`/runs/<id>/evidence` answered 404 once in ten** (SLB), on a run whose
   brief rendered normally with 7 documents across 5 families. Not
   reproduced; recorded.
4. **Monitoring answers are class priors** — "revenue at a business of this
   kind moves with produced volume". Model-appropriate, not company-specific.
5. **A follow-up is only as deep as the turn it follows.** Where the prior
   answer carries no `so_what`, the follow-up honestly reports that nothing
   further is established rather than inventing a reason.
6. Restart durability and feedback persistence remain accepted
   `BLOCKED_INFRASTRUCTURE` and are not Strategic-100 blockers.

## 8. UI approval (frozen SHA)

Entry and run surfaces at **375 / 390 / 768 / 1280 / 1440**, light and dark:
zero horizontal overflow, zero text below 3.0 contrast, zero raw enums, no
spinner after terminal. Progress page carries a server-seeded timer, truthful
ETA copy and an eight-stage ladder. Keyboard-only: `:focus-visible` rings on
both entry (3px) and run (2px) surfaces; autocomplete arrow-key selection
binds the canonical identity and announces the match count.

## 9. Strategic-100 preparation

```
FIRST FROZEN 50   perf_progressive_matrix.QUALIFY_50, hash 716ea020b2fecb35
SECOND FROZEN 50  MISSING
FULL COHORT       NOT READY
```

The preregistration describes the second 50 qualitatively — "drawn on the same
rules: filers and non-filers, sectors spread deliberately rather than by
convenience, and a deliberately thin tail" — and states the cohort "is stored
in the repository". It is not, and the rules given are **not sufficient to
select it deterministically**. Missing:

- the **source universe** to draw from;
- a **seed or ordering rule** making the draw reproducible;
- **counts per sector**, and the threshold that makes a company "sparse".

Selecting it here would mean making those choices inside the qualification
session that is about to be graded by them, which is what preregistration
exists to prevent.

```
STRATEGIC100_PREPARATION_BLOCKER = SECOND_COHORT_SELECTION_RULE_INCOMPLETE
```

**Required user decision:** the source universe and the deterministic
selection rule (or the explicit second-50 list) for the remaining cohort.
Once frozen and hashed beside `PRE100_QUALIFYING_SHA`, Strategic-100 may run.
