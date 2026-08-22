"""Database-health check (section 3) — feeds the dashboard's DB-health view.

Reports the effective backend, whether a real write+read round-trips, per-stream
row counts, and any error — WITHOUT ever printing the DATABASE_URL credentials.
A fresh GitHub-Actions runner or a just-woken Render free service calls this to
prove the durable store is reachable before doing real work.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from intent_engine.storage.durable import (
    DurableStore,
    resolve_database_url,
)


def _safe_target(url: str) -> str:
    """A credential-free description of where we're connected."""
    p = urlparse(url)
    scheme = p.scheme.lower()
    if scheme.startswith("sqlite"):
        return f"sqlite:{p.path or ':memory:'}"
    host = p.hostname or "?"
    db = (p.path or "/").lstrip("/") or "?"
    return f"{scheme}://{host}/{db}"  # no user, no password, ever


def check_health(url: Optional[str] = None, *, store: Optional[DurableStore] = None
                 ) -> Dict[str, Any]:
    resolved = resolve_database_url(url)
    report: Dict[str, Any] = {
        "ok": False,
        "backend": "postgres" if urlparse(resolved).scheme.lower().startswith(
            "postgres") else "sqlite",
        "target": _safe_target(resolved),
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "roundtrip": False,
        "streams": {},
        "error": None,
    }
    owns = store is None
    try:
        store = store or DurableStore(resolved)
        store.migrate()
        marker = datetime.now(timezone.utc).isoformat()
        rec = store.append("__health__", "probe", {"marker": marker},
                           idem_key=f"health:{marker}")
        report["roundtrip"] = (rec.payload.get("marker") == marker)
        report["streams"] = {s: store.count(s) for s in store.streams()
                             if s != "__health__"}
        report["ok"] = report["roundtrip"]
    except Exception as exc:  # noqa: BLE001 - health must never itself crash
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if owns and store is not None:
            store.close()
    return report
