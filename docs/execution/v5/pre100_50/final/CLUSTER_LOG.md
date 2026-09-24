# Defect candidates, logged during the run (§12) — not repaired mid-wave

| # | candidate | evidence | status |
|---|---|---|---|
| C1 | `economic_reasoning` absent | Meta `/full` is 27k chars and carries no revenue/margin-engine language; Alphabet's does (10) and Microsoft's partly (6). Same class, same build — so it is the producer, not the cue. | OPEN |
| C2 | `competition` generic | Meta 6, Microsoft 6, Alphabet 10. Substitute-based reads ("the customer's own engineering", "renewing nothing") score 6 for carrying no proper noun. Needs checking whether that is a scoring floor or a real genericity. | OPEN |
| C3 | `adversary` generic | Meta 6, Alphabet 6, Microsoft 10. The engine runs, so this is about the rival it picks, not about wiring. | OPEN |
| C4 | prose capitalisation | "the contest is most direct with The customer's own engineering, Renewing nothing" — row labels joined into a sentence. Cosmetic. | OPEN |
| C5 | CSS in extracted text | `margin:1.` appears in Meta's `full.txt`; a style block survives `text_of`. Harness-side, affects scoring only if a cue matches CSS. | OPEN |

Rank and repair after 50/50, by prevalence x quality loss x executive
importance. Not before: three of the last five "defects" this programme
chased turned out to be the instrument.
