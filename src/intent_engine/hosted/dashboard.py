"""Hosted dashboard — section-17 views, assembled from the DURABLE store.

The Render FREE web service is a read-only UI over the durable database: it
builds a fresh DurableStore per request (so it recovers cleanly after the
service sleeps), reads the hosted state, and renders it. It runs NO scheduler
and does NO trading — GitHub Actions does that. Every trading view carries the
mandatory banner: PAPER TRADING — SIMULATED — NO REAL MONEY.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from intent_engine.hosted.budget import Budget, BudgetLedger
from intent_engine.hosted.candidates import CandidateStore
from intent_engine.hosted.records import latest_executions, recent_failures
from intent_engine.hosted.reports import latest_report
from intent_engine.paper.orders import OrderRepository
from intent_engine.paper.reconciliation import EQUITY_STREAM, POSITION_STREAM
from intent_engine.predictions.repository import PredictionRepository
from intent_engine.predictions.resolution import OUTCOME_STREAM
from intent_engine.storage.health import check_health
from intent_engine.universe.companies import default_universe
from intent_engine.universe.learning import CROSS_STREAM, CompanyLearningStore
from intent_engine.universe.research import company_state
from intent_engine.universe.store import UniverseStore

BANNER = "PAPER TRADING — SIMULATED — NO REAL MONEY"


def assemble(store, *, budget: Optional[Budget] = None,
             as_of: Optional[str] = None) -> Dict[str, Any]:
    universe = UniverseStore(store).load() or default_universe()
    preds = PredictionRepository(store)
    orders = OrderRepository(store)
    learning = CompanyLearningStore(store)
    ledger = BudgetLedger(store, budget or Budget())

    companies: List[dict] = []
    for c in universe.companies:
        st = company_state(store, c.company_id)
        cpreds = preds.by_company(c.company_id)
        latest_pred = cpreds[-1] if cpreds else None
        cl = learning.get(c.company_id)
        corders = orders.by_company(c.company_id)
        companies.append({
            "company_id": c.company_id, "name": c.canonical_name,
            "classification": c.classification.value,
            "ticker": c.tradable_instrument, "peer_group": c.peer_group,
            "may_trade": c.may_generate_order,
            "proxy_of": c.proxy_of,
            "research_freshness": st.last_refreshed if st else None,
            "thesis": (st.thesis if st else "") or c.inclusion_reason,
            "latest_prediction": ({
                "direction": latest_pred.direction,
                "probability": latest_pred.probability,
                "instrument": latest_pred.instrument,
                "outcome": latest_pred.outcome,
                "type": "strategic" if not latest_pred.instrument else "market",
            } if latest_pred else None),
            "orders": len(corders),
            "filled_orders": len([o for o in corders if o.is_filled]),
            "directional_accuracy": cl.directional_accuracy if cl else None,
            "brier": cl.brier if cl else None,
            "paper_pnl": cl.paper_pnl if cl else 0.0,
            "avg_market_return": cl.avg_market_return if cl else None,
            "sample_size": cl.sample_size if cl else 0,
            "calibration_error": cl.calibration_error if cl else None,
        })

    positions = [r.payload for r in store.latest(POSITION_STREAM)]
    equities = sorted((r.payload for r in store.latest(EQUITY_STREAM)),
                      key=lambda p: p.get("as_of", ""))
    cross = [r.payload for r in store.latest(CROSS_STREAM)]
    open_cands = [c.model_dump() for c in CandidateStore(store).open()]
    outcomes = [r.payload for r in store.latest(OUTCOME_STREAM)]

    return {
        "banner": BANNER,
        "generated_from": "durable database (read-only UI)",
        "universe": companies,
        "reconciliation": {
            "open_orders": len(orders.open_orders()),
            "filled_orders": len([o for o in orders.all_latest() if o.is_filled]),
            "positions": positions,
            "resolved_outcomes": len(outcomes),
            "latest_equity": equities[-1] if equities else None,
        },
        "cross_company": cross,
        "open_candidates": open_cands,
        "scheduler": {
            "latest": latest_executions(store),
            "recent_failures": recent_failures(store, limit=10),
        },
        "database_health": check_health(store=store),
        "budget": {"usage": ledger.usage(as_of or ""),
                   "remaining": ledger.remaining(as_of or "")}
        if as_of else {"note": "pass as_of for daily budget usage"},
        "latest_report": latest_report(store),
    }


def _fmt(v, nd=3):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def render_html(data: Dict[str, Any]) -> str:
    """A compact, self-contained, theme-neutral HTML fragment (no external
    assets). The mandatory PAPER banner is the first thing rendered."""
    rows = []
    for c in data["universe"]:
        badge = "TRADABLE" if c["may_trade"] else (
            "PROXY" if c["classification"] == "BENCHMARK_OR_PROXY"
            else ("PRIVATE" if c["classification"] == "PRIVATE_COMPANY"
                  else "NOT-ELIGIBLE"))
        lp = c["latest_prediction"]
        pred = (f'{lp["direction"]} @ {_fmt(lp["probability"],2)} '
                f'({lp["type"]})' if lp else "—")
        rows.append(
            "<tr>"
            f"<td>{c['name']}</td><td>{c['ticker'] or '—'}</td>"
            f"<td><span class='badge'>{badge}</span></td>"
            f"<td>{c['peer_group'] or '—'}</td>"
            f"<td>{pred}</td>"
            f"<td>{_fmt(c['directional_accuracy'],2)}</td>"
            f"<td>{_fmt(c['brier'])}</td>"
            f"<td>{_fmt(c['paper_pnl'],2)}</td>"
            f"<td>{c['sample_size']}</td>"
            f"<td>{c['research_freshness'] or '—'}</td>"
            "</tr>")
    recon = data["reconciliation"]
    db = data["database_health"]
    sched = data["scheduler"]["latest"]
    sched_rows = "".join(
        f"<tr><td>{j}</td><td>{v.get('status')}</td>"
        f"<td>{v.get('finished_at', v.get('started_at','—'))}</td></tr>"
        for j, v in sorted(sched.items())) or "<tr><td colspan=3>no runs recorded yet</td></tr>"
    cross_rows = "".join(
        f"<li>{x.get('peer_group')}: {x.get('pattern')} "
        f"(supporting: {', '.join(x.get('supporting_companies', []))})</li>"
        for x in data["cross_company"]) or "<li>none yet</li>"
    cand_rows = "".join(
        f"<li>{c.get('id')} — {c.get('statement')} [{c.get('status')}]</li>"
        for c in data["open_candidates"]) or "<li>none yet</li>"
    return f"""
<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;">
  <div style="background:#7a1f1f;color:#fff;padding:.6rem 1rem;border-radius:8px;
              font-weight:700;letter-spacing:.02em;">{data['banner']}</div>
  <p style="opacity:.7;margin:.5rem 0 1rem;">Source: {data['generated_from']} —
     this page runs no scheduler and places no trades.</p>

  <h3>Tracked company universe</h3>
  <div style="overflow-x:auto;"><table border="1" cellpadding="6"
       cellspacing="0" style="border-collapse:collapse;width:100%;">
    <thead><tr><th>Company</th><th>Ticker</th><th>Class</th><th>Peer</th>
      <th>Latest prediction</th><th>Dir.acc</th><th>Brier</th>
      <th>Paper P&amp;L</th><th>n</th><th>Research fresh</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table></div>

  <h3>Alpaca reconciliation</h3>
  <ul>
    <li>Open orders: {recon['open_orders']} · Filled: {recon['filled_orders']}
        · Positions: {len(recon['positions'])}
        · Resolved outcomes: {recon['resolved_outcomes']}</li>
    <li>Latest equity: {(_fmt((recon['latest_equity'] or {}).get('equity'),2))}
        · Daily return: {_fmt((recon['latest_equity'] or {}).get('daily_return'))}</li>
  </ul>

  <h3>Scheduler health (GitHub Actions runs)</h3>
  <div style="overflow-x:auto;"><table border="1" cellpadding="6"
       cellspacing="0" style="border-collapse:collapse;">
    <thead><tr><th>Job</th><th>Status</th><th>Finished</th></tr></thead>
    <tbody>{sched_rows}</tbody></table></div>

  <h3>Cross-company patterns (human-gated candidates)</h3><ul>{cross_rows}</ul>
  <h3>Open learning candidates</h3><ul>{cand_rows}</ul>

  <h3>Database health</h3>
  <p>Backend: <b>{db.get('backend')}</b> · target: {db.get('target')} ·
     ok: <b>{db.get('ok')}</b> · roundtrip: {db.get('roundtrip')}</p>

  <p style="opacity:.6;margin-top:1.5rem;">{data['banner']}</p>
</div>
"""
