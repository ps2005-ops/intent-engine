"""Macro evidence as it was known on the decision date, and the engine's reading of it.

EVERY VALUE IS READ THROUGH THE VINTAGE WALL
-------------------------------------------
Features come from `econ.panel.Panel.history(as_of=d)`, which returns, for
each period, the latest revision whose `vintage_at <= d` (see
[[two-dates-per-fact]]: a figure for June published in September is not
knowable in July). Each feature carries the evidence id of every cell it
read, `panel:<series>:<period>@<vintage>`, so the leak checker can re-read
the vintage of every input instead of trusting this module.

THE ENGINE IS CALLED, NOT RE-IMPLEMENTED
----------------------------------------
* regime: `econ.regime.classify(panel, d)`;
* economic state: `scripts/publish_econ_state.build_state(panel, as_of=d)`,
  loaded by path because it lives in a script, so the replay and the
  publisher can never drift into two definitions of the state;
* company reading: `external_intel.econ_context.relevant_to` then
  `external_intel.econ_decision.transmissions`, with the profile from
  `executive.company_profile.profile_for` on the validation manifest.

ONE REPLAY ASSUMPTION, STATED
-----------------------------
In the product, a company's exposures come from its own retrieved documents
(`econ.company.MacroExposure`). Point-in-time filings are not acquired here,
so the replay gives each company every condition whose channel has a
transmission for its business-model class. That is the engine's maximal
reading. It can only make the arm flag MORE often than the product would,
and the flag-permutation control is there to measure what that costs.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import importlib.util
import pathlib
from typing import Dict, List, Optional, Sequence, Tuple

from intent_engine.econ import panel as PN
from intent_engine.econ import regime as RG

PANEL_PATH = pathlib.Path("reports/panel/historical_panel.jsonl")
FORWARD_DIR = pathlib.Path("reports/paper_validation/forward_macro")

#: (feature name, series, transform, lookback days). Fixed before results.
MACRO_FEATURES: Tuple[Tuple[str, str, str, int], ...] = (
    ("slope_10y3m", "T10Y3M", "level", 0),
    ("d_slope_10y3m_91d", "T10Y3M", "diff", 91),
    ("baa_spread", "BAA10Y", "level", 0),
    ("d_baa_spread_91d", "BAA10Y", "diff", 91),
    ("d_dgs10_91d", "DGS10", "diff", 91),
    ("d_dff_365d", "DFF", "diff", 365),
    ("d_unrate_365d", "UNRATE", "diff", 365),
    ("cpi_yoy", "CPIAUCSL", "yoy", 365),
    ("indpro_yoy", "INDPRO", "yoy", 365),
)
MACRO_NAMES = tuple(f[0] for f in MACRO_FEATURES)
REGIME_NAMES = tuple(f"regime_{r.lower()}" for r in RG.REGIMES)

STRESS = (RG.CREDIT_STRESS, RG.LIQUIDITY_STRESS, RG.LABOUR_DETERIORATION,
          RG.INFLATION_SHOCK)


def _sha_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_panel(path=PANEL_PATH, *, forward_snapshot: Optional[pathlib.Path]
               = None) -> Tuple[PN.Panel, dict]:
    """The panel, optionally extended by a forward snapshot, and its vintage."""
    path = pathlib.Path(path)
    p = PN.Panel.read(path)
    vint = {"panel": str(path), "panel_sha256": _sha_file(path)[:16]}
    if forward_snapshot is not None:
        snap = PN.Panel.read(forward_snapshot)
        for sid in snap.series_ids:
            for c in snap.cells[sid]:
                p.add(c)
        vint["forward_snapshot"] = str(forward_snapshot)
        vint["forward_snapshot_sha256"] = _sha_file(forward_snapshot)[:16]
    p.finalise()
    return p, vint


def _latest(panel: PN.Panel, sid: str, as_of: str):
    """The most recent knowable cell of `sid` at `as_of`, with its vintage."""
    hist = panel.history(sid, as_of=as_of)
    if not hist:
        return None, hist
    period = hist[-1][0]
    cell = panel.latest_vintage_of(sid, period, as_of)
    return cell, hist


def _prior(hist, latest_period: str, days: int):
    target = (_dt.date.fromisoformat(latest_period)
              - _dt.timedelta(days=days)).isoformat()
    found = None
    for period, value in hist[:-1]:
        if period <= target:
            found = (period, value)
        else:
            break
    return found


def macro_features(panel: PN.Panel, as_of: str
                   ) -> Tuple[Dict[str, float], List[str], List[str]]:
    """(features, evidence ids, missing feature names) at `as_of`."""
    feats: Dict[str, float] = {}
    ev: List[str] = []
    missing: List[str] = []
    cache = {}
    for name, sid, transform, days in MACRO_FEATURES:
        if sid not in cache:
            cache[sid] = _latest(panel, sid, as_of)
        cell, hist = cache[sid]
        if cell is None:
            missing.append(name)
            continue
        ev.append(f"panel:{sid}:{cell.observed_at}@{cell.vintage_at}")
        now = float(cell.value)
        if transform == "level":
            feats[name] = now
            continue
        prior = _prior(hist, cell.observed_at, days)
        if prior is None:
            missing.append(name)
            continue
        pcell = panel.latest_vintage_of(sid, prior[0], as_of)
        ev.append(f"panel:{sid}:{pcell.observed_at}@{pcell.vintage_at}")
        then = float(prior[1])
        if transform == "diff":
            feats[name] = now - then
        else:
            feats[name] = (now / then - 1.0) if then else 0.0
            if not then:
                missing.append(name)
    return feats, sorted(set(ev)), missing


def regime(panel: PN.Panel, as_of: str) -> RG.RegimeReading:
    """Classified under the protocol version in force at `as_of` (amendment
    A1 is prospective: earlier decisions keep econ_regime.v1)."""
    from intent_engine.paper_validation.protocol import regime_version_for
    return RG.classify(panel, as_of, version=regime_version_for(as_of))


def regime_features(reading: RG.RegimeReading) -> Dict[str, float]:
    return {f"regime_{r.lower()}": (1.0 if reading.holds(r) else 0.0)
            for r in RG.REGIMES}


def regime_label(reading: RG.RegimeReading) -> str:
    if set(reading.regimes) & set(STRESS):
        return "STRESS"
    if reading.holds(RG.LOW_VOL_EXPANSION):
        return "CALM"
    return "MIXED"


# --- the economic engine's company reading ---------------------------------

_PUBLISHER = None


def _publisher():
    """`scripts/publish_econ_state.py`, loaded by path (it is a script)."""
    global _PUBLISHER
    if _PUBLISHER is None:
        # The repository's own script, found beside this package or, when the
        # package is imported from elsewhere (an install, a test mirror), from
        # the repository root the process runs in. Never a second copy.
        rel = pathlib.Path("scripts/publish_econ_state.py")
        candidates = [pathlib.Path(__file__).resolve().parents[3] / rel,
                      pathlib.Path.cwd() / rel]
        path = next((c for c in candidates if c.exists()), None)
        if path is None:
            raise FileNotFoundError(
                f"scripts/publish_econ_state.py not found at {candidates}; "
                "the econ arm cannot rebuild the engine's state without it")
        spec = importlib.util.spec_from_file_location(
            "_pv_publish_econ_state", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _PUBLISHER = mod
    return _PUBLISHER


class EconReader:
    """The engine's economic state at `as_of`, read once, for many companies."""

    def __init__(self, panel: PN.Panel, as_of: str):
        from intent_engine.external_intel import econ_context as EC
        self.as_of = as_of
        state = _publisher().build_state(panel, as_of=as_of)
        payload = state.as_dict()
        self.state_as_of = str(payload.get("as_of", ""))
        self.context = EC.EconContext(
            available=True, as_of=self.state_as_of,
            area=str(payload.get("area", "")),
            conditions=dict(payload.get("conditions") or {}))

    def company(self, profile) -> dict:
        from intent_engine.external_intel import econ_context as EC
        from intent_engine.external_intel import econ_decision as ED
        kinds = []
        for k in self.context.known_kinds():
            ch = ED.CHANNEL_OF.get(k, "")
            if not ch:
                continue
            if profile.transmission_for(ch) or (
                    ch == "POLICY_RATE" and profile.transmission_for(
                        "MARKET_RATE")):
                kinds.append(k)
        readings = EC.relevant_to(self.context, exposures=kinds)
        rows, unmapped = ED.transmissions(readings=readings, profile=profile)
        adverse = [r for r in rows if r["adverse"]]
        # The engine only ever names ADVERSE moves. The mirror image --
        # a material move OPPOSITE the adverse sign -- is derived here, for
        # the logit_D feature only, and is never presented as engine output.
        favourable = [r for r in rows
                      if r["adverse_when"] and not r["adverse"]
                      and r["direction"] in ("UP", "DOWN")
                      and r["direction"] != r["adverse_when"]
                      and r["move"] is not None
                      and abs(r["move"]) >= ED.MATERIAL_MOVE]
        signed = [r for r in rows if r["adverse_when"]]
        ev = sorted({str(r.get("node_id") or "") for r in rows
                     if r.get("node_id")})
        return {"adverse": adverse, "favourable": favourable,
                "signed": len(signed), "rows": rows, "unmapped": unmapped,
                # The CUTOFF the state was built at, not its latest period:
                # the cutoff is what the vintage wall was applied at, so it
                # is the date a leak would move.
                "evidence_ids": [f"econ_state:{self.as_of}:{n}"
                                 for n in ev],
                "lead": ED.lead_row(rows)}


def node_period(node_id: str) -> str:
    """`panel:SID:YYYY-MM-DD` -> the period. Used by the leak checker."""
    parts = str(node_id).split(":")
    return parts[-1] if len(parts) >= 3 else ""


# --- the forward snapshot (current FRED values, for forward use only) -------

def build_forward_snapshot(panel: PN.Panel, *, retrieved: _dt.datetime,
                           fetcher=None, series: Sequence[str] = (),
                           lookback_days: int = 450,
                           log=lambda s: None) -> PN.Panel:
    """Current-vintage FRED observations, stamped with the retrieval date.

    Only for FORWARD registrations: the vintage of a value retrieved today is
    today, which is true and conservative (the real release was earlier). The
    historical replay never reads this.
    """
    from intent_engine.market import alfred as AL
    # The NEW YORK date: a Monday-evening retrieval is Tuesday in UTC, and a
    # vintage stamped with tomorrow's date is invisible to today's decision.
    from intent_engine.paper_validation.ledger import ny_date
    stamp = ny_date(retrieved)
    cutoff = (retrieved.date() - _dt.timedelta(days=lookback_days)).isoformat()
    snap = PN.Panel()
    for sid in (series or panel.series_ids):
        cells = panel.cells.get(sid) or []
        if not cells:
            continue
        proto = cells[0]
        try:
            _col, rows = AL.fetch_series(sid, fetcher=fetcher)
        except Exception as exc:                        # noqa: BLE001
            log(f"forward macro {sid}: FAILED {type(exc).__name__}")
            continue
        added = 0
        for period, value in rows:
            if period < cutoff or period > stamp:
                continue
            snap.add(PN.Cell(series_id=sid, observed_at=period,
                             vintage_at=stamp, value=float(value),
                             unit=proto.unit, kind=proto.kind,
                             node_class=proto.node_class, released_at="",
                             frequency=proto.frequency,
                             source=f"FRED current, retrieved {stamp} "
                                    "(forward snapshot)",
                             revision_state=""))
            added += 1
        log(f"forward macro {sid}: {added} cells")
    snap.finalise()
    return snap
