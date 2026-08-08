# Cycle record — 2026-08-05

Branches: `feat/founder-decision-experience-v3` (founder),
`feat/market-learning-engine` (market). Production `main` untouched at
`119d345`. PR #14 still draft. `TRADING_MODE=PAPER` unchanged.

## What this cycle changed

**The strategic bridge now has both ends.** `strategic_market_intel.v1` was
specified, allowlisted and covered by tests, and had exactly one caller in the
repository: a test. Nothing produced a dossier and nothing consumed one.

- Producer: `market/strategic_publish.py` writes one sanitized dossier per
  company on **every** learning session, day and night.
- Consumer: `external_intel/strategic_contract.py`, reached from
  `webapp/app.py::_external_context`, surfaced as a fourth family on
  `ExternalContext` beside market / macro / competitive.

The allowlist is declared on **both** sides deliberately. `intent_engine.market`
does not exist on the founder branch and must not — the file on disk is
untrusted input, so the consumer re-derives the judgement instead of trusting
the producer's validation.

**Three founder-visible defects, each found on the deployed preview.**

1. *Large filings were discarded whole.* Caterpillar's 10-Q (3.46MB) came back
   `too large` and the run was bounded at 2 usable sources. Measured across
   twelve real primary documents, seven exceed the 2MB cap — including every
   filing of JPMorgan (12.9MB 10-K) and Berkshire. EDGAR now has its own
   budget; the general web keeps 2MB. Verified live: the 10-Q moved into
   *Pages read*, 2 → 3 sources, and the `too large` category disappeared.
2. *One page listed twice.* The failure list opened "www.caterpillar.com,
   www.caterpillar.com, www.caterpillar.com/api and 16 more". Readable names
   are deduplicated and the count follows distinct pages.
3. *A ballot box cited as evidence.* The top item under "What supports this"
   for Palantir was the 10-K statutory cover page. The rule lives in
   `editorial.is_filing_furniture` because six surfaces read `excerpt`
   independently.

## What was measured and deliberately NOT done

**The 10-Q is still not truncatable, and that is the finding.** Extending the
annual report's argument to it looked obvious and is wrong: an annual report
survives truncation because Item 1. Business is at the front, but a quarterly
report's MD&A sits at char 2,418,251 of 3,459,434 — 70% in. Tolerating
truncation there would have turned a visible failure into an invisible
half-document. Fixed by budget instead.

**Caterpillar's own site blocks automated access.** With our UA the host hangs
(18.6s, 30.3s); with a browser UA it returns HTTP 403 in 0.4s. Not a timeout,
not fixable by waiting longer, and not our defect. The page's "timed out"
wording is arguably a misdiagnosis, but the retry it offers is already gated
by `_has_untried_sources`, so it is not the dead end it looked like.

## The binding constraint for the next cycle

**Belief formation has no production caller.** The belief engine built last
cycle is real, tested, and structurally inert live:

- `declare_belief` / `B.create` — no caller in `src/` (only the definition).
- `EXP.preregister` / `record_expectation` — no caller in `src/`.
- `reports/market/learning_ledger.jsonl` — **has never been written**.

So `store.beliefs()` is empty, there are no open expectations to reconcile,
and `knowledge_gain` is structurally 0 in every real cycle. Micro-evidence is
translated and ingested, but no belief exists for it to update. This is the
same defect class as the `revisions=()` it replaced, one layer down.

Stop condition 18 (a zero-trade cycle producing a valid nonzero knowledge
update) is therefore met **in a test harness and not in production**.

Belief formation must be as disciplined as the revision path — earned by
evidence, carrying a falsifier — or it manufactures exactly the progress
`assets_step` refused to manufacture. Note `learning_cycle.run` looks beliefs
up by `r.hypothesis_id`, so belief identity should mirror the research
hypothesis, not a free-text thesis that changes between runs.

## Still open

- §24 Business Graph strategic projection — not started.
- §26 — the strategic material reaches `reasoning_pack` and is relevance
  gated, but is not yet rendered on narrative / dashboard / brief surfaces.
- §28 — validated on Caterpillar (industrial, and the bounded case) and
  Palantir. Not Shopify, Toyota, a semiconductor company, or a private one.
