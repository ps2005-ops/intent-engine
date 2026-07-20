# Synthetic-world reasoning eval — LIVE leg (extraction -> matcher)

*Run 2026-07-20, seed 20260719, 89 extraction calls (≈$1.78 estimated). Frozen prompt sha256 verified before the first call.*

SCOPE (recorded so it cannot be misquoted): this is a causal-reasoning diagnostic on constructed fictional worlds. It is NOT a forward-market accuracy measure, NOT calibration evidence, NOT a marketing claim, and it changes no prompt, enum, or library data. Fictional worlds cannot be memorized; that is the point of the design.

- single worlds: constructed truth recovered in 68/69
- mixed worlds: both mechanisms recovered in 12/12
- control worlds (healthy, condition-free): clean silence in 3/8 — hallucinated conditions on the rest are the key negative finding, listed in the JSON.

Per-world detail: synthetic_worlds_eval_live.json.

## Analysis of the v1.0 live run (loop 9, 2026-07-20 — generator now at v1.1)

- **Recovery**: 68/69 single worlds, 12/12 mixed. Condition-level recall
  **1.00** — across 89 fictional worlds the extractor never missed a
  planted causal symptom, on entities and industries it cannot have seen.
- **Precision 0.68, and it is one artifact, not diffuse noise**:
  `few_dominant_competitors` was extracted 67 times where it was not
  planted. Root cause is the GENERATOR's v1.0 opener ("its principal
  competitor is {rival}") appearing in every world — an accidental
  oligopoly cue. All other hallucinations were rare (≤3 each). 5/8
  controls lost clean silence, dominantly to the same cue.
- **The one identification miss** (`winners_curse_acquisition`, 1/3
  worlds): its single planted condition ties with `reflexive_bubble` by
  construction; the artifact condition tipped ranking. Expected to clear
  with the opener fix.
- **Generator v1.1** (same seed, walls unchanged, tests updated): the
  concentrated-competition opener now appears ONLY in worlds that plant
  `few_dominant_competitors`; every other world describes a broad
  competitive field, turning the named rival into deliberate
  counter-evidence bait. v1.0 results remain on record above; v1.1 live
  numbers require a fresh Mac run of the same command.
- Interpretation stays within scope: this is a reasoning diagnostic on
  constructed worlds — the recall result says the extraction leg reads
  causal structure well on unmemorizable inputs; the precision result
  taught us more about our base than about the model, which is what a
  first run of a new eval is for.
