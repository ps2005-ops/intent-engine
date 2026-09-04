# PRE-100 — 60-company generalization gauntlet

**Status: STARTED, NOT COMPLETE.** Batch A was not run. What follows is the
§1 first task — the Meta AT&T-class defect — traced to its root and repaired
as a class, plus the measurement that changes how batch A should be read.

Baseline: `4e3368c` (founder = deployed = both branches).

---

## §1 — the AT&T defect was two defects, and neither was AT&T

### Defect 1: a mention was stamped as a competitor

EDGAR full-text search returns filings by other registrants naming the
subject. `third_party_filings._emit` stamped every one
`source_class: "competitor"` — a constant, not a finding — and the relevance
grade beside it said `DIRECTLY_RELEVANT` because it **counted passages
rather than reading them**.

Measured live, Meta Platforms:

| filer | the span | truth |
|---|---|---|
| Oklo | *"prepayment agreement with Meta Platforms, Inc."* | **CUSTOMER** — Meta buys power |
| Network-1 | *"our case against Meta Platforms, Inc."* | **LITIGATION** — a patent suit |
| Enbridge | capital-allocation boilerplate that never names Meta | **INCIDENTAL** |
| RingCentral | *"…Meta Platforms, Inc., Microsoft Teams, Slack…"* | **COMPETITOR** |

Three of four wrong. A customer read that as Meta's competitive position.

**Fix (`executive/relationship.py`):** a mention becomes
`RelationshipEvidence(subject, counterparty, relationship_type, evidence,
confidence, date)` before anything may call it a rival. Twelve types;
**only `COMPETITOR` and `SUBSTITUTE` reach the ladder**. The classification is
decided by what the sentence *does* — "agreement with", "case against",
"compete with" — never by the company's name, because a stoplist keyed on
"AT&T" would have left Oklo, Network-1 and Enbridge exactly where they were.

Two contracts enforced at construction: a classification must quote the span
that produced it, and that span must be **the sentence that matched** (a
fixed character window quoted a revenue line under a litigation verdict).
A span that does not name the subject is `INCIDENTAL_MENTION` — the Enbridge
case, where the document matched but the selected excerpt did not.

### Defect 2: the peer list was alphabetical

The customer-visible sentence did not come from the third-party channel at
all. `_competitors` ranks same-sector-different-model peers by
`(0, 0, canonical_name)` — **dictionary order**. Meta's model class
(`ADVERTISING_PLATFORM`, added last cycle) has **no manifest peer**, so the
strong branch was empty and the sector's membership was presented
alphabetically: `37signals LLC, Adobe Inc., AgileBits Inc.` locally, and
`AT&T Inc, Alphabet Inc` on the deployed page.

Worse, `_position` printed them under **"Its position is contested most
directly by"** — while those rows' own stated basis is *"same sector but a
different business model: it competes for the same end demand **without the
same economics**"*.

**Fix:** weak peers now rank on the same two economic facts the strong branch
uses (geography, size class), with the name only as a deterministic
tie-break; and the strong sentence requires a strong basis. A sector-mate now
reads *"It sits in the same sector as X, which earn differently and so are a
weaker comparison than a direct rival."*

---

## The measurement that matters for batch A

With relationship classification live, third-party filings across three
industries yield **zero competitors**:

| subject | filers found | competitive |
|---|---|---|
| Meta | Oklo (customer), Enbridge (unknown), Network-1 (litigation), RingCentral (unknown) | 0 |
| JPMorgan | Wells Fargo, IAC, CSLM, Ribbon — all unknown | 0 |
| Eli Lilly | Nektar (**partner**), Foghorn (**partner**), VivoSim, Chimerix | 0 |

**This is the `NAMED_BY_RIVAL` yield measurement, and the answer is that the
channel is thin.** Filings that name another company overwhelmingly describe
partnerships, supply agreements, litigation and holdings — the relationships
that *get filed* — not competition. Nektar and Foghorn being collaboration
partners of Lilly is the rule, not an anomaly.

Consequence for the gauntlet: the competitive ladder cannot be closed by
finding more third-party filings. It has to lean on the subject's own
contested categories, substitutes, internal build and workflow alternatives —
the rungs that do not require a rival to volunteer the relationship.

This also raises a recall question that batch A must answer rather than
assume: Wells Fargo genuinely does compete with JPMorgan, and the classifier
returned `UNKNOWN` because the retrieved span never said so. The conservative
direction is correct — it cannot fabricate — but the cost is real and should
be measured per batch, not argued about.

---

## Not done

Batch A (Meta, Amazon, NVIDIA, JPMorgan, Walmart, Lilly, Caterpillar, Exxon)
was **not run**. No company in the 60-company corpus has been walked
end-to-end this cycle. The business-model ontology (§5) still has ten classes,
not the ~30 the corpus needs — every non-software company in batch A will
land on a coarse class, and that is the first thing batch A should measure.

`ADVERTISING_PLATFORM` still has no peer set, so Meta's sector sentence is
honest and thin. The durable fix is peers for the new classes, which the
corpus itself supplies.
