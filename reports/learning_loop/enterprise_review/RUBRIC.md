# Enterprise decision-quality review (blind)

Five pairs in `blind_pairs.json`. Each pair is one company's strategic-context
text in two versions, A and B, in random order, with the evidence the text
rests on. The texts name the company, as the page does; nothing in the file
says which version is old or new. Both versions come from the same renderer
and differ only in the content under review.

Score each version from 1 (poor) to 5 (excellent) in `REVIEW_SHEET.csv`:

| Criterion | Question |
|---|---|
| factual_accuracy | Is every claim supported by the evidence shown? |
| economic_reasoning | Does it name what actually moved: demand, price, margin, cost, or expectations? |
| company_relevance | Is it about this company, not a customer, competitor or the market? |
| strategic_insight | Does it surface a tension or question an executive would care about? |
| evidence_quality | Is the claim proportionate to the evidence's strength and independence? |
| actionability | Could an executive act on it? |
| executive_usefulness | Would you put it in front of the CEO? |
| uncertainty_handling | Is confidence stated honestly, with limits? |

Then give an overall preference (A, B or tie) and one sentence on why, on
row A of each pair.

Do not open `KEY_do_not_show_reviewers.json` until every pair is scored.
Scope: this is the strategic-context block only. The founder's
recommendation is composed elsewhere and does not read these beliefs.
**This package is the input to commercial validation, not a substitute
for it.**
