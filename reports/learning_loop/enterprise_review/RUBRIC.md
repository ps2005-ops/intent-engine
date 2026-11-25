# Enterprise decision-quality review (blind)

For each item in `blind_pairs.json`, read the evidence, then versions A and B.
Do not open `KEY_do_not_show_reviewers.json` until all items are scored.

Score each version from 1 to 5 on each of the following:

1. **Factual correctness.** Is every claim supported by the evidence shown?
2. **Economic mechanism.** Does it say WHAT moved: demand, price, margin,
   cost, or expectations?
3. **Company relevance.** Is it about this company, not a customer or a
   competitor?
4. **Uncertainty handling.** Is the confidence proportionate, and are the
   limits stated?
5. **Decision usefulness.** Would an executive act differently, and should
   they?

Then answer: which version would you rather put in front of the company's
CEO, and why (one sentence)?

**Scope.** This package covers the strategic-context block only. The
founder's recommendation is composed elsewhere
(`strategic_intelligence/reasoning._build_thesis`) and does not read these
beliefs, so no recommendation changes. **No automated score here is
commercial validation.** It needs domain-expert reviewers.
