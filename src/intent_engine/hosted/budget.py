"""Cost control (section 16) — explicit CAD/call budgets with safe-stop.

Budgets are read from the environment and enforced against a durable per-day
usage ledger. When a budget is reached the caller STOPS safely and persists the
skipped work (never an unbounded retry). The dashboard reads `usage()` to show
estimated and actual daily cost.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

USAGE_STREAM = "budget_usage"
SKIP_STREAM = "skipped_work"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _flag(env, key: str, default: bool) -> bool:
    v = env.get(key)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Budget:
    prediction_generation_enabled: bool = True
    daily_llm_budget_cad: float = 5.0
    max_daily_llm_calls: int = 200
    max_companies_per_daily_refresh: int = 25
    max_sources_per_company: int = 8
    synthetic_daily_budget_cad: float = 1.0
    synthetic_weekly_budget_cad: float = 3.0

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "Budget":
        env = env if env is not None else os.environ

        def num(key, default):
            try:
                return type(default)(env.get(key, default))
            except (TypeError, ValueError):
                return default

        return cls(
            prediction_generation_enabled=_flag(
                env, "PREDICTION_GENERATION_ENABLED", True),
            daily_llm_budget_cad=num("DAILY_LLM_BUDGET_CAD", 5.0),
            max_daily_llm_calls=num("MAX_DAILY_LLM_CALLS", 200),
            max_companies_per_daily_refresh=num(
                "MAX_COMPANIES_PER_DAILY_REFRESH", 25),
            max_sources_per_company=num("MAX_SOURCES_PER_COMPANY", 8),
            synthetic_daily_budget_cad=num("SYNTHETIC_DAILY_BUDGET_CAD", 1.0),
            synthetic_weekly_budget_cad=num("SYNTHETIC_WEEKLY_BUDGET_CAD", 3.0))


class BudgetLedger:
    def __init__(self, store, budget: Optional[Budget] = None):
        self.store = store
        self.budget = budget or Budget()

    def usage(self, as_of: str) -> Dict[str, float]:
        day = as_of[:10]
        rows = [r.payload for r in self.store.read(USAGE_STREAM, ref_id=day)]
        return {"calls": sum(int(r.get("calls", 0)) for r in rows),
                "cad": round(sum(float(r.get("cad", 0.0)) for r in rows), 4)}

    def can_spend(self, as_of: str, *, calls: int = 1, cad: float = 0.0
                  ) -> Tuple[bool, Optional[str]]:
        u = self.usage(as_of)
        if u["calls"] + calls > self.budget.max_daily_llm_calls:
            return False, (f"daily LLM call cap reached "
                           f"({u['calls']}/{self.budget.max_daily_llm_calls})")
        if u["cad"] + cad > self.budget.daily_llm_budget_cad:
            return False, (f"daily LLM CAD budget reached "
                           f"({u['cad']:.2f}/{self.budget.daily_llm_budget_cad} CAD)")
        return True, None

    def record(self, as_of: str, *, calls: int = 0, cad: float = 0.0,
               kind: str = "llm", company_id: Optional[str] = None) -> None:
        day = as_of[:10]
        rid = f"{day}:{kind}:{company_id or ''}:{_now()}"
        self.store.append(USAGE_STREAM, rid,
                          {"as_of": day, "calls": calls, "cad": cad,
                           "kind": kind, "company_id": company_id, "at": _now()},
                          status="spent", company_id=company_id, ref_id=day)

    def remaining(self, as_of: str) -> Dict[str, float]:
        u = self.usage(as_of)
        return {"calls": max(0, self.budget.max_daily_llm_calls - u["calls"]),
                "cad": round(max(0.0, self.budget.daily_llm_budget_cad - u["cad"]),
                             4)}


def record_skip(store, as_of: str, *, item: str, reason: str,
                company_id: Optional[str] = None) -> None:
    """Persist a piece of work skipped because a budget/limit was reached, so it
    can be prioritised next run and shown on the dashboard."""
    rid = f"{as_of[:10]}:{item}"
    store.append(SKIP_STREAM, rid,
                 {"as_of": as_of[:10], "item": item, "reason": reason,
                  "company_id": company_id, "at": _now()},
                 status="skipped", company_id=company_id, ref_id=as_of[:10],
                 idem_key=f"skip:{rid}")
