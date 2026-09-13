"""Publish the shared economic state from the public panel.

WHY A SECOND PUBLISHER
----------------------
`market.econ_bridge.publish` writes the shared state from the market engine's
own ledger. That is the right producer on a deployment that runs a market
engine. The founder preview does not run one and cannot — Render persistent
disks attach to exactly one service — so on that deployment the state has
always been absent, and every economic surface has correctly reported
"unavailable" for intelligence the repository already holds.

This is not a fallback inside the reader. `econ_context.load` still reads one
store at one path and still says UNAVAILABLE when it is empty; the difference
between "wrong root" and "nothing published" stays legible, which is why the
reader has no fallback and must not grow one. This is a PRODUCER, run
deliberately, writing the same contract to the same store, and recording in
`provenance.producer` which of the two wrote it.

WHAT IT PUBLISHES
-----------------
The MACRO rows of `reports/panel/historical_panel.jsonl` — public series with
their observation date, their vintage date and their revision state. The panel
is revision-aware, so the reading published for a date is the value that was
in force then rather than today's restatement of it.

Two observations per condition, not one: `ConditionReading` computes DIRECTION
against the previous observation of the same quantity and refuses a direction
with no prior, so a one-row publish would produce a state where nothing has
ever moved.

FORWARD EXPECTATIONS: THE REAL LEDGER ONLY
------------------------------------------
`reports/real_forward_expectations.jsonl` and nothing else. The rehearsal
ledger is a different file and this script does not open it — §14. Records are
additionally filtered on `source`, so a rehearsal row written into the real
file by mistake still does not cross.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from intent_engine.econ import evidence as EV                 # noqa: E402
from intent_engine.econ import panel as PN                    # noqa: E402
from intent_engine.econ import state as ES                    # noqa: E402
from intent_engine.econ import store as EST                   # noqa: E402
from intent_engine.econ.founder_contract import REHEARSAL     # noqa: E402
from intent_engine.econ.vocabulary import MACRO, NODE_KINDS   # noqa: E402

PRODUCER = "econ_panel_publisher.v1"
PANEL = pathlib.Path("reports/panel/historical_panel.jsonl")
LEDGER = pathlib.Path("reports/real_forward_expectations.jsonl")

#: How the panel's own source field is reported to a reader. The panel rows
#: carry a FRED series id; the publisher of every one of them is the Federal
#: Reserve Bank of St. Louis's public database, and saying so is what makes
#: the provenance line checkable.
PUBLISHER = "FRED (Federal Reserve Bank of St. Louis)"
VENUE = "fred.stlouisfed.org"


def _macro_cells(panel: PN.Panel, as_of: str):
    """The two most recent knowable observations of each MACRO condition."""
    by_kind = {}
    for sid in list(panel.series_ids):
        cells = panel.cells.get(sid) or []
        if not cells or cells[0].node_class != MACRO:
            continue
        kind = cells[0].kind
        if kind not in NODE_KINDS[MACRO]:
            continue
        hist = panel.history(sid, as_of=as_of)
        if len(hist) < 2:
            continue
        # One series per kind: the one with the most recent observation. Two
        # series mapped to one kind would make the "prior" observation come
        # from a different instrument, and a direction computed across two
        # instruments is not a movement.
        prev = by_kind.get(kind)
        if prev is None or hist[-1][0] > prev[1][-1][0]:
            by_kind[kind] = (sid, hist, cells[0].unit or "")
    return by_kind


#: How far back the comparison reaches. A YEAR, chosen by date rather than by
#: counting observations back.
#:
#: THE FIRST VERSION PUBLISHED THE TWO MOST RECENT OBSERVATIONS, and the state
#: it produced was useless for a decision. `ConditionReading.direction` is
#: computed against the previous observation published for that quantity, so
#: two adjacent rows made every reading a one-day or one-month change: the
#: 10-year Treasury moved 0.0128 and the policy rate 0.0000, against a
#: materiality threshold of 0.03 that was declared for YEAR-ON-YEAR change.
#: Measured across all thirteen conditions, exactly one cleared it, and it was
#: moving the favourable way -- so the product would have abstained on every
#: company for a reason that was an artefact of the publisher.
#:
#: Chosen BY DATE and not by index: `_periods_for_year` counts observations,
#: and these series are irregular, so counting back gave a "year-ago" prior
#: sixteen days old for the high-yield spread.
LOOKBACK_DAYS = 365


def _year_ago(hist, latest_period: str):
    """The most recent observation at or before a year before `latest_period`.

    Returns None when the series does not reach back a year, and the caller
    publishes a single observation instead -- which reads NO_PRIOR and says so,
    rather than presenting a short comparison as a yearly one.
    """
    import datetime as _dt
    try:
        target = (_dt.date.fromisoformat(latest_period)
                  - _dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
    except ValueError:
        return None
    found = None
    for period, value in hist[:-1]:
        if period <= target:
            found = (period, value)
    return found


#: The unit that tells a consumer which change transform to use.
#:
#: A spread, a yield and an unemployment rate are PERCENTAGE POINTS, and a
#: relative change on them is undefined where they cross zero -- the 3-month /
#: 10-year slope inverts in every tightening cycle, and its year-ago value
#: here is -0.02, which turns a two-basis-point move into a 4,250% one. The
#: canonical list is `econ.release.PERCENTAGE_POINT_SERIES`, keyed by series;
#: this records the answer ON THE READING, because the consumer knows the
#: condition and never the series that measured it.
PERCENTAGE_POINT = "percentage_point"


def _unit_for(sid: str, panel_unit: str) -> str:
    from intent_engine.econ import release as RL
    return PERCENTAGE_POINT if RL.is_percentage_point(sid) else (panel_unit
                                                                 or "index")


def _published_pair(sid: str, hist):
    """The two observations that make one year-on-year reading."""
    latest = hist[-1]
    prior = _year_ago(hist, latest[0])
    return [prior, latest] if prior is not None else [latest]


def build_state(panel: PN.Panel, *, as_of: str) -> ES.EconomicState:
    by_kind = _macro_cells(panel, as_of)
    nodes = []
    for kind, (sid, hist, unit) in sorted(by_kind.items()):
        for period, value in _published_pair(sid, hist):
            nodes.append(EV.EconomicNode(
                node_id=f"panel:{sid}:{period}",
                node_class=MACRO, kind=kind, subject="US",
                standing="OBSERVED", occurred_at=period,
                available_at=as_of, value=float(value),
                unit=_unit_for(sid, unit),
                provenance=EV.Provenance(
                    publisher=PUBLISHER, venue=VENUE,
                    document_id=sid, producer=PRODUCER)))
    if not nodes:
        raise SystemExit("the panel yielded no MACRO observation; refusing to "
                         "publish an empty state, which would read as a calm "
                         "economy rather than as an absent one")
    described = max(n.occurred_at for n in nodes)
    return ES.build(as_of=described, area="US", nodes=nodes,
                    producer=PRODUCER,
                    graph_summary={"source": "public panel",
                                   "series": len(by_kind),
                                   "vintage_walled": True})


def real_expectations() -> list:
    if not LEDGER.exists():
        return []
    current = {}
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        current[row["expectation_id"]] = row
    out = []
    for row in current.values():
        if str(row.get("source", "")).upper() == REHEARSAL:
            continue
        if str(row.get("visibility", "PUBLIC")) != "PUBLIC":
            continue
        out.append(row)
    return sorted(out, key=lambda r: r["expectation_id"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True,
                    help="runtime root the founder service reads")
    ap.add_argument("--as-of", default="",
                    help="evidence cutoff; defaults to today")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    import datetime as dt
    as_of = args.as_of or dt.date.today().isoformat()

    panel = PN.Panel.read(PANEL)
    state = build_state(panel, as_of=as_of)
    payload = state.as_dict()          # validates against the allowlist
    exps = real_expectations()

    print(f"producer          {PRODUCER}")
    print(f"state as_of       {state.as_of}  (cutoff {as_of})")
    print(f"conditions        {state.known_conditions} known of "
          f"{state.uncertainty['vocabulary']} in the vocabulary")
    for kind, r in sorted(state.conditions.items()):
        print(f"  {kind:<24}{r.direction:<9}{r.value:<14g}{r.as_of}")
    print(f"real expectations {len(exps)} (rehearsal file never opened)")
    if args.dry_run:
        print("dry run; nothing written")
        return 0

    root = pathlib.Path(args.root)
    written = EST.append_many(root, "node",
                              [n.as_dict() for n in _nodes_of(state, panel,
                                                              as_of)],
                              written_at=as_of)
    EST.append(root, "state_snapshot", payload, written_at=as_of)
    EST.append_many(root, "expectation", exps, written_at=as_of)
    print(f"wrote             {written} node(s), 1 state_snapshot, "
          f"{len(exps)} expectation(s) under {EST.econ_root(root)}")
    return 0


def _nodes_of(state, panel, as_of):
    """The nodes the state was built from, for the durable node ledger."""
    by_kind = _macro_cells(panel, as_of)
    out = []
    for kind, (sid, hist, unit) in sorted(by_kind.items()):
        for period, value in _published_pair(sid, hist):
            out.append(EV.EconomicNode(
                node_id=f"panel:{sid}:{period}", node_class=MACRO, kind=kind,
                subject="US", standing="OBSERVED", occurred_at=period,
                available_at=as_of, value=float(value),
                unit=_unit_for(sid, unit),
                provenance=EV.Provenance(publisher=PUBLISHER, venue=VENUE,
                                         document_id=sid, producer=PRODUCER)))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
