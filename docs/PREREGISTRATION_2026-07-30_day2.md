# Pre-registration — Day 2

Written **before any test was run**. Availability of inputs was checked first;
no outcome was observed.

Baseline comparator for every hypothesis: `momentum_persists.v1` = **0.500**
(n=66), same companies, same horizon, same replay.

---

## TESTABLE

### H4 · `event_drift.v1`

| field | |
|---|---|
| **Economic mechanism** | Investors under-react to material disclosures. A company files an 8-K (or 6-K for a foreign issuer) only when something material happened; the market's first-day reaction is incomplete and drift continues. This is post-announcement drift, a documented effect, and it is **conditioned on an information event** rather than on an arbitrary date — which is what makes it a different family from Day 1. |
| **Observable inputs** | SEC EDGAR submissions API: `form` ∈ {8-K, 6-K} and `filingDate`. Daily closes from the price feed. |
| **Decision rule** | Signal = sign of (close on filing date − prior close). Enter at the **next** close after the filing date. Direction = sign of that move. |
| **Expected direction** | Same direction as the filing-day move (drift, not reversal). |
| **Horizon** | 21 calendar days. |
| **Invalidation** | Accuracy ≤ 0.500, or inside the 2σ band around 0.500. |
| **Minimum sample** | n ≥ 30 (`A-M5`). Below that, report as unmeasurable rather than as a result. |
| **Retirement** | Retired same day if invalidated. No "promising, needs more data". |
| **Known lookahead risks** | (1) A filing published after the close is not tradable at that close — mitigated by entering at the **next** close. (2) EDGAR `filingDate` is the acceptance date, which is the public-availability date, so it does not encode future knowledge. (3) The price feed never returns a close after the date requested. |

### H5 · `report_drift.v1`

Identical to H4 except **periodic reports** — `form` ∈ {10-Q, 10-K, 20-F, 40-F}
— rather than material-event filings. Mechanism is the same under-reaction,
but scheduled reports are anticipated where 8-Ks are not, so the two are
separated rather than pooled: pooling them would hide a difference that is the
whole point of testing both.

---

## UNTESTABLE — recorded, not approximated

### H6 · Earnings surprise

**Requires** actual EPS versus the consensus estimate *as it stood before the
announcement*. Yahoo's `earningsHistory` and `earnings` modules both return
**HTTP 401** without authentication, and no keyless historical consensus source
is available here.

Approximating a "surprise" from price reaction would be circular — it would
define the surprise by the outcome it is meant to predict. **UNTESTABLE.**

### H7 · Management guidance change

The filing text *is* point-in-time and reachable through EDGAR archives, so
this is not blocked by data availability. It is blocked by extraction:
reliably detecting *"guidance was raised / lowered / withdrawn"* from raw
filing prose is a substantial NLP task, and a crude keyword rule would
manufacture a signal out of its own error rate. **UNTESTABLE TODAY**, and the
blocker is named precisely so it can be revisited: reliable guidance
extraction, not missing data.

### H8 · Disagreement between market movement and company evidence

The most tempting hypothesis available, and the one with the worst lookahead
risk. Company evidence comes from **live websites, which show today's
content**. Using it for a decision dated three months ago injects information
that did not exist then, and the resulting edge would be invisible and
entirely false.

**UNTESTABLE** until point-in-time company evidence exists — which means
archived snapshots, not the live site. Flagged here rather than quietly
approximated, because this is exactly the failure the directive warns about.

---

## Multiple comparisons

Two testable hypotheses. All results reported. With n near 30–60 the standard
error on a proportion near 0.5 is ~0.065–0.09, so a 2σ departure needs roughly
**≥0.63 or ≤0.37**. Anything inside that band is indistinguishable from the
baseline regardless of rank.
