# PRE-100 baseline — the validation universe

*Canonical pointer. The measured record lives in
`docs/execution/v5/pre100_50/` and the manifest in `intent_engine.validation`.*

---

## The universe

One hundred companies, curated, with a business-model class assigned per
company. Cohorts are re-derivable rather than stored, so the universe cannot
drift by editing a cohort file.

The manifest is the source of the business-model classification that gates:

- the **pattern library** (which strategic readings a company may receive)
- the **tension library** (which blind spots a company may receive)
- the **transmission table** (how an economic condition reaches this business)
- the **adverse-direction table** (which way a condition has to move to hurt)

All four are keyed on the same vocabulary. A class that appears in one and not
the others is a coverage gap and is reported as one — `SCALE_RETAIL` had no
transmission mechanisms at all until closure, so a scale retailer could
receive no economic reading.

## Known coverage facts

- **transmission**: all ten manifest classes now have at least one mechanism.
- **tensions**: the library's three tensions describe one class. Widening it
  means writing tensions that are true of the others, which is research, not
  a filter change. `patterns.tension_model_coverage()` reports it.
- **vulnerability playbook**: fires only for a hypothesis whose pattern is in
  the playbook, so a company the pattern library does not match has none.
  Baseline A falls back to blind spots and then to the company's own stated
  exposures.
