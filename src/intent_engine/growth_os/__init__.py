"""Growth Operating System — an autonomous, continuously-learning marketing
intelligence platform on the trading engine's foundation.

Everything here is event-sourced, carries provenance and confidence, is
timestamped, replayable, measurable, produces learning candidates, and stays
human-gated where required. No black-box optimization; every recommendation
carries evidence.

This umbrella ORCHESTRATES and REUSES the existing mature stack
(`intent_engine.marketing`, `.growth`, `.growth_studio`, `.crm`, `.analytics`)
and the shared foundation (`.storage`, `.events`, `.knowledge`/`.learning`,
`.simulator.synthetic_worlds`); it never duplicates or modifies their write
paths. See docs/GROWTH_OS_ARCHITECTURE.md.

Submodules:
  foundation  — the shared event/provenance/confidence/learning contract + store
  research    — Growth Research (§1): world -> understood intent -> candidates
  brand       — Brand Memory (§6): versioned, human-approved brand model + the
                "never contradict approved messaging" gate
"""
