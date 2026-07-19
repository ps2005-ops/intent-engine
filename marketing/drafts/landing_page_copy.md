# Landing page copy — DRAFT, awaiting founder approval (deliverable a)

---

## Hero

**A structural read on your market — with the uncertainty left in.**

Most analysis tells you a confident story. Ours tells you which documented
structural mechanisms — supply shocks, price wars, credit contagion,
platform envelopment — genuinely match your situation [T:1], says so
plainly when none do [T:2], and shows its sources on every line [T:3].

**[Get a free structural analysis →]**

## How it works

1. **You describe the decision or market situation** — a paragraph is
   enough.
2. **We extract the structural conditions actually present** — against a
   fixed, closed taxonomy, tested for restraint: when your situation is
   genuinely ambiguous, the system selects little or nothing rather than
   forcing a match [T:1][T:2].
3. **Conditions are matched against a library of documented historical
   mechanisms** — each entry carries named sources and cited episodes
   (1907 to 2022), matched by deterministic rules, not vibes [T:3].
4. **You get a readable report** — mechanisms possibly in play with their
   historical precedents, what the data couldn't verify clearly labeled
   UNAVAILABLE, and any data gaps flagged loudly instead of papered over
   [T:4].

## Why the honesty markers are the product

- "None matched" is a real answer we actually give [T:2].
- "Unavailable" means we had no verified number — so we made no claim [T:4].
- Every probabilistic claim we make on the record goes into an append-only
  ledger and is graded automatically by code against real market data —
  we cannot quietly delete misses [T:5].
- **We do not claim predictive accuracy. Our ledger is young; its
  calibration will be public as it accumulates, compared against dumb
  baselines we have to beat honestly** [T:5][T:6].

## Who it's for

Founders making a bet — market entry, pricing response, expansion,
fundraise timing — who want structural precedent and honest uncertainty,
not a confident narrative.

---

## Claim-trace table (business-phase wall; not rendered on the page)

| Trace | Claim | Grounds (gate-passed capability / ledgered fact) |
|---|---|---|
| T:1 | extraction restraint, closed taxonomy | Task 3 reliability gate (5x3 protocol) + v2 rerun PASS 2026-07-18; closed TriggerCondition enum, schema-enforced |
| T:2 | "says so when none match" | deterministic matcher returns empty on no overlap (match_mechanisms, tested); "correct silence" bar in gate + T005 bar (b) |
| T:3 | documented library, named sources, deterministic match | mechanisms.json: every historical_instance carries a real citation; matcher is zero-LLM code |
| T:4 | UNAVAILABLE labels, loud DATA GAPS | regime_report rendering + 2026-07-18 gap-rule amendment (render_data_gaps_section), both tested |
| T:5 | append-only ledger, code-graded | prediction_ledger.py append-only convention; resolve_prediction computes Brier in code |
| T:6 | no accuracy claim, public-as-it-accumulates | A-M5 ≥30-resolved wall + founder calibration review; ledger currently 0 resolved (ledgered fact) |

*Rule check: zero accuracy claims present; the only performance statement
is the explicit disclaimer that none is made.*
