"""The shared model boundary (T022).

Two things all three agents genuinely share, extracted; nothing more.

1. **The provenance shape.** Every agent stamps a model-produced row with
   `{prompt_version, model_version, ...}`. `model_provenance` builds that
   dict; each agent passes its own third key (research records the
   extraction module, product and executive record the authority note),
   so the output is byte-identical to each original.

2. **The recursive forbidden-field scan.** Product and executive held two
   byte-identical copies of `find_forbidden_fields` — a deep scan that
   finds a forbidden key at any nesting depth, used by both the model
   boundary and the score/readiness walls. That single implementation now
   lives here; each agent passes its own forbidden-field set, because the
   set is domain policy and the scan is infrastructure.

**Intentionally NOT extracted** (recorded, per the three-implementations
rule): the model-boundary EXCEPTION. Research raises
`ExtractionRejected(ResearchError)`; product and executive raise
`ModelOverreach` off their own error types. A caller catching a research
error must still catch a research model rejection, so each keeps its own
subclass — a shared base would force multiple inheritance and change the
catchability the agents rely on. And research's model WALL itself stays
local: it is a source-anchored, locatability-checked, flat-forbidden-set
check, which is a different and stricter operation than scanning a drafted
prose payload for leaked identifiers. Two different walls that share a
sub-idea are not one wall.
"""
from __future__ import annotations


def model_provenance(prompt_version: str, model_version: str, **extra) -> dict:
    """The provenance every model-produced row carries. `extra` is the
    agent's own third field (e.g. `authority=...` or
    `extraction_module=...`), so the result matches each original exactly."""
    return {"prompt_version": prompt_version,
            "model_version": model_version, **extra}


def find_forbidden_fields(value, forbidden, found=None) -> list:
    """Every forbidden field present in `value`, at any nesting depth.

    Nesting is not a loophole: a forbidden key inside a list of dicts is
    found. `forbidden` is the agent's own set of fields a model may never
    author. Byte-for-byte the recursive scan product and executive shared.
    """
    found = [] if found is None else found
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in forbidden:
                found.append(key)
            find_forbidden_fields(nested, forbidden, found)
    elif isinstance(value, (list, tuple)):
        for item in value:
            find_forbidden_fields(item, forbidden, found)
    return sorted(set(found))
