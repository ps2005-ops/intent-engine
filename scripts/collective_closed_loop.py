"""Section 57: the closed loop, run twice, showing behaviour changed.

WHAT THIS PROVES AND WHAT IT DOES NOT
-------------------------------------
It proves the LOOP CLOSES: a behavioural observation becomes a posterior,
which becomes a hypothesis, which becomes a preregistered expectation, which
resolves, which scores, which promotes or retires a construct, which changes
what a founder surface is allowed to say. Every arrow is a real function
call against the real modules, and the second iteration is run against the
register the first one wrote.

It does NOT prove the collective-state layer predicts anything about the real
economy. The outcomes here are generated, and generated outcomes cannot
establish an empirical claim -- Section 39 is explicit that a synthetic
trajectory is never empirical market learning. What the generator gives is
CONTROL: one construct is wired to carry real signal and one is wired to
carry none, so the run demonstrates that the machinery can tell them apart.
Whether any real construct carries signal is a question only forward
resolutions can answer, and the calibration status says so.

Run:  ./.venv/bin/python scripts/collective_closed_loop.py
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import random
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import (                            # noqa: E402
    bayes, bleed, collective as CO, construct as CK, dashboard as DB,
    episodes as EP, founder_view as FV, incremental as inc, store as ST,
    transmission_seed as TS, vocabulary as V,
)

ROOT = pathlib.Path("/private/tmp/claude-501/-Users-prathamsharma/"
                    "2116dbf1-e0c9-4d1e-b968-5976e78cb2a4/scratchpad/loop")

#: One construct wired to carry signal, one wired to carry none. The point of
#: the run is that the machinery separates them without being told which.
WIRED = {"financial_anxiety": True, "anger": False}

POP = CO.population("US_households", V.HOUSEHOLD)


def _stable_hash(text: str) -> int:
    """Deterministic across processes.

    Python's built-in `hash()` for strings is randomised per interpreter by
    PYTHONHASHSEED, so a script that used it produced DIFFERENT numbers on
    every run while looking seeded. A demonstration whose figures cannot be
    reproduced is not a demonstration, and Section 55 requires every learning
    metric to be reproducible.
    """
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def line(t=""):
    print(t)


def rule(t):
    line()
    line("=" * 74)
    line(t)
    line("=" * 74)


# ---------------------------------------------------------------------------
# 1. OBSERVE -> POSTERIOR
# ---------------------------------------------------------------------------
def observe(seed: int, drift: float, prior=None):
    """Behavioural observations arrive and move a posterior."""
    rng = random.Random(seed)
    dims, updates = [], []
    for dim in WIRED:
        start = (prior.dimension(dim) if prior is not None
                 else CO.unmeasured(dim, "no prior cycle"))
        obs = [bayes.Observation(
            node_id=f"beh/{dim}/{seed}/{i}",
            value=min(0.98, max(0.02, 0.55 + drift + rng.gauss(0, 0.05))),
            noise=0.09, as_of="2026-08-27", publisher="BLS")
            for i in range(3)]
        upd = bayes.update(start, obs, at="2026-08-27")
        updates.append(upd)
        dims.append(bayes.apply(start, upd))
    return (CO.build(population=POP, as_of="2026-08-27", dimensions=dims,
                     source_nodes=[n for u in updates
                                   for n in u.evidence_nodes]),
            updates)


# ---------------------------------------------------------------------------
# 2. POSTERIOR -> EXPECTATION -> OUTCOME -> COMPARISON
# ---------------------------------------------------------------------------
def experiment(dim: str, regime: str, seed: int, n: int = 300):
    """One preregistered base-vs-augmented experiment for one construct.

    Both models forecast the SAME targets from the SAME cutoffs; the only
    difference is whether the collective posterior is in the feature set.
    """
    informative = WIRED[dim]
    rng = random.Random(seed)
    base, aug, outs = [], [], []
    for i in range(n):
        latent = rng.random()
        occurred = rng.random() < latent
        b = min(0.95, max(0.05, latent + rng.gauss(0, 0.25)))
        extra = (latent - b) * 0.6 if informative else rng.gauss(0, 0.25)
        a = min(0.95, max(0.05, b + extra))
        tid = f"{dim}/{regime}/{i}"
        cut = f"2021-01-{(i % 27) + 1:02d}"
        occ = f"2021-06-{(i % 27) + 1:02d}"
        base.append(inc.Forecast(target_id=tid, probability=b,
                                 information_cutoff=cut, horizon_days=90,
                                 model="BASE_ECONOMIC", regime=regime))
        aug.append(inc.Forecast(target_id=tid, probability=a,
                                information_cutoff=cut, horizon_days=90,
                                model="BASE_PLUS_COLLECTIVE", regime=regime))
        outs.append(inc.Outcome(target_id=tid, occurred=occurred,
                                occurred_at=occ, published_at=occ,
                                regime=regime))
    return inc.compare(name=f"{dim}/{regime}", dimension=dim,
                       population=POP.key, base=base, augmented=aug,
                       outcomes=outs, regime=regime, horizon_days=90,
                       seed=seed)


def run_iteration(label: str, register, seed_base: int, drift: float,
                  prior=None):
    rule(label)

    # --- OBSERVE ----------------------------------------------------------
    state, updates = observe(seed_base, drift, prior=prior)
    line("1. OBSERVE -> POSTERIOR")
    for u in updates:
        line(f"     {u.dimension:<20} {u.effect:<18} "
             f"posterior={u.posterior_mean:.3f} "
             f"delta={'n/a' if u.delta is None else format(u.delta, '+.3f')}")
    s = bayes.summarise(updates)
    line(f"     informative={s['informative']}  "
         f"arrived-without-informing={s['arrived_without_informing']}")

    # --- EXPERIMENT (vintage-walled) --------------------------------------
    line()
    line("2. PREREGISTERED EXPERIMENT -> RESOLUTION -> SCORE")
    regimes = [e.regime for e in EP.training() + EP.validation()][:3]
    comparisons = []
    for dim in WIRED:
        for i, regime in enumerate(sorted(set(regimes))):
            comparisons.append(experiment(dim, regime, seed_base + i * 17 +
                                          _stable_hash(dim) % 991))
    comparisons = inc.adjust(comparisons)
    for c in comparisons:
        line(f"     {c.statement()[:112]}")

    r = inc.report(comparisons)
    line()
    line(f"     BASE_ECONOMIC_MODEL      = {r['base_economic_model_score']}")
    line(f"     BASE_PLUS_COLLECTIVE     = {r['base_plus_collective_score']}")
    line(f"     INCREMENTAL_DELTA        = {r['incremental_delta']}")
    line(f"     robust of tested         = "
         f"{r['robust_improvements']}/{r['tested']}  (FDR q={inc.FDR_Q})")

    # --- PROMOTE / RETIRE -------------------------------------------------
    line()
    line("3. PROMOTE / WEAKEN / RETIRE")
    register = CK.apply_report(register, comparisons, at="2026-08-27")
    for c in register:
        line(f"     {c.dimension:<20} {c.state:<12} passes={c.passes} "
             f"fails={c.failures} regimes={c.regimes_passed} "
             f"graph={c.usable_in_causal_graph}")

    # --- WHAT THE FOUNDER MAY NOW BE TOLD ---------------------------------
    line()
    line("4. WHAT A FOUNDER SURFACE IS NOW ALLOWED TO SAY")
    restamped = CO.build(
        population=POP, as_of=state.as_of,
        dimensions=[__import__("dataclasses").replace(
            d, promotion_state=next((c.state for c in register
                                     if c.dimension == n), V.CANDIDATE))
            for n, d in state.dimensions.items()],
        source_nodes=state.source_nodes)
    for cid in ("WMT", "JPM"):
        v = FV.for_company(company_id=cid, state=restamped,
                           registry=TS.registry(), register=register,
                           economy_note="Headline employment is unchanged.")
        if v["shown"]:
            for shown in v["shown"]:
                line(f"     {cid}: {shown['sentence'][:150]}")
        else:
            line(f"     {cid}: (nothing) {v['empty_reason'][:120]}")

    # --- CHAINS THE GATE NOW OPENS ----------------------------------------
    line()
    line("5. TRANSMISSION CHAINS THE GATE NOW OPENS")
    reg_t = TS.registry()
    usable = reg_t.chains(register=register, enforce=True)
    line(f"     usable: {len(usable)} of {len(reg_t.chains(enforce=False))}")
    for ch in usable:
        line(f"       {' -> '.join(ch.path)}")

    # --- A BLEED ----------------------------------------------------------
    line()
    line("6. CAUSAL BLEED, AND WHETHER IT MAY BE CORROBORATED")
    chain = reg_t._chains["rate_cuts_blocked_by_insecurity"]
    b = bleed.detect(chain=chain, expected_probability=0.80,
                     observed_probability=0.28, as_of="2026-08-27",
                     candidate_interruption="financial_anxiety",
                     impact=0.8, controllability=0.6, confidence=0.55)
    b = bleed.corroborate(b, state=restamped, register=register)
    line(f"     {b.statement()[:200]}")
    line(f"     level={b.level}  priority={b.priority}  "
         f"human_state_contribution={b.human_state_contribution}")

    # --- PERSIST ----------------------------------------------------------
    ST.append_many(ROOT, "construct", [c.as_dict() for c in register],
                   written_at="2026-08-27")
    ST.append(ROOT, "collective_state", restamped.as_dict(),
              written_at="2026-08-27")
    ST.append_many(ROOT, "comparison", [c.as_dict() for c in comparisons],
                   written_at="2026-08-27")
    return register, restamped, r


def main() -> int:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)

    register = [CK.observe(CK.propose(d, proposed_by="behavioural-economics"),
                           proxy=f"{d}_proxy", at="2026-08-26")
                for d in WIRED]

    reg1, state1, rep1 = run_iteration(
        "ITERATION 1 — the engine has never tested a construct",
        register, seed_base=1001, drift=0.10)

    rule("DASHBOARD AFTER ITERATION 1")
    p1 = DB.build(ROOT)
    print(json.dumps(p1["headline"]))
    print(p1["verdict"])

    reg2, state2, rep2 = run_iteration(
        "ITERATION 2 — same machinery, run against what iteration 1 learned",
        reg1, seed_base=2002, drift=0.16, prior=state1)

    rule("DASHBOARD AFTER ITERATION 2")
    p2 = DB.build(ROOT)
    print(json.dumps(p2["headline"]))
    print(p2["verdict"])

    rule("SECTION 57: DID BEHAVIOUR CHANGE BECAUSE IT LEARNED?")
    before = {c.dimension: c.state for c in register}
    after = {c.dimension: c.state for c in reg2}
    for d in sorted(WIRED):
        line(f"  {d:<20} {before.get(d, '-'):<12} -> {after.get(d, '-')}")

    reg_t = TS.registry()
    o1 = len(reg_t.chains(register=register, enforce=True))
    o2 = len(reg_t.chains(register=reg2, enforce=True))
    line(f"  transmission chains open      {o1} -> {o2}")

    v1 = FV.for_company(company_id="WMT", state=state1, registry=reg_t,
                        register=register)
    v2 = FV.for_company(company_id="WMT", state=state2, registry=reg_t,
                        register=reg2)
    line(f"  WMT readings shown            {v1['shown_count']} -> "
         f"{v2['shown_count']}")
    line(f"  delta measured                {rep1['incremental_delta']} -> "
         f"{rep2['incremental_delta']}")

    changed = (before != after or o1 != o2
               or v1["shown_count"] != v2["shown_count"])
    line()
    line("  VERDICT: " + ("SYSTEM BEHAVIOUR CHANGED BECAUSE IT LEARNED"
                          if changed else
                          "NO CHANGE — the loop did not close"))
    line()
    line("  What this run does NOT establish: the outcomes above are")
    line("  generated, so no claim is made that any real construct predicts")
    line("  any real economy. Section 39 forbids counting a synthetic")
    line("  trajectory as market learning, and CALIBRATION_STATUS is")
    line("  PRE_CALIBRATION at n=0 real forward resolutions.")
    return 0 if changed else 1


if __name__ == "__main__":
    raise SystemExit(main())
