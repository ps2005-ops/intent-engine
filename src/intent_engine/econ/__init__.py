"""The canonical economic learning core — one substrate, two decision surfaces.

WHAT THIS PACKAGE IS FOR
------------------------
This repository holds two intelligence products. The company/founder engine
asks what is happening inside and around a company and what management should
do. The market-learning engine asks which economic mechanisms are changing,
what should happen next, and whether its expectations resolved. They shared a
codebase and did not share a learning substrate, so the intelligence one of
them acquired was structurally unavailable to the other: `/learning` could
know that real rates, AI capital intensity and enterprise consolidation were
interacting, and a Cloudflare analysis running in the same process could not
read a word of it.

This is not a connector between them. It is the thing both of them consume.

THE STRUCTURAL RULE, AND WHY IT SURVIVES UNIFICATION
-----------------------------------------------------
The founder packages may not import `intent_engine.market`. That wall is
real, it is tested, and it exists because "trading internals cannot reach a
founder's screen" should be a property of the import graph rather than a
promise about what people remember. Unification does not weaken it.

`econ` is NEUTRAL: it imports neither side, and neither side's internals can
reach it. The market engine writes economic state into it; the founder engine
reads economic state out of it; the two never touch. `tests/
test_econ_core_is_neutral.py` parses every module in this package and fails
on the import edge, in exactly the shape `demo_dossier` is already guarded.

WHAT LIVES HERE
---------------
    vocabulary    the words both sides must agree on
    evidence      the Economic Evidence Graph: one dated, sourced fact
    lineage       the double-counting wall
    causal        directed mechanisms with an EVIDENCE LADDER (L0-L5)
    seed          the transmission chains, entered at honest levels
    series        the cross-asset universe, availability stated not assumed
    shock         structural shock propagation with compounding confidence
    belief        beliefs and preregistered expectations, append-only
    attacks       the shared belief-attack / impossible-hypothesis engine
    levelk        market participant classes and their level-k responses
    reflexivity   belief -> positioning -> price -> forced flow -> belief
    execution     paper and shadow fills with real friction; live refuses
    calibration   forward scoring, and PRE_CALIBRATION until it is earned
    zero_trade    learning from what was declined and what was never seen
    voi           what to find out next, bounded
    replay        vintage-correct replay with a four-way verdict
    promotion     candidate -> knowledge, with the overfitting defences
    acceleration  is it learning faster, and is it learning as well
    state         EconomicState: the canonical object both products read
    company       CompanyEconomicState: one company, in that economy
    store         append-only durable form under the shared runtime root

WHAT THIS PACKAGE REFUSES
-------------------------
    - trading internals in shared state (allowlist, at every depth, plus a
      prose scan, because a win rate inside a sentence leaks like one inside
      a key)
    - tenant-private evidence in any public surface (a refusal, never a
      filter: an aggregate quietly built from private material and reported
      as smaller is a breach that also lies about its own sample)
    - a derived signal counted as independent evidence of its own input
    - causal language below evidence level 3
    - an accuracy figure before the declared minimum forward sample
    - live capital, at this stage, by construction
"""
from __future__ import annotations

from .vocabulary import (               # noqa: F401
    CONTRACT, EconError, LineageViolation, PUBLIC, PrivacyViolation,
    TENANT_PRIVATE,
)

__all__ = [
    "CONTRACT", "EconError", "PrivacyViolation", "LineageViolation",
    "PUBLIC", "TENANT_PRIVATE",
]
