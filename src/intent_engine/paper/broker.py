"""Alpaca PAPER broker — simulated execution surface.

PAPER TRADING — SIMULATED — NO REAL MONEY. This module talks ONLY to Alpaca's
paper endpoint. It has no live-trading host, no live toggle, and refuses to
initialise against any non-paper hostname (`assert_paper_only`). The live host
name appears exactly once below — as the thing we reject.

Idempotency is the whole point of `deterministic_client_order_id`: GitHub
Actions may fire the submit job twice (a retry, an overlapping run). A submit
keyed by a client_order_id derived from (prediction, strategy_version,
instrument, trading_date, action) collapses to ONE order — Alpaca dedupes on
client_order_id, and so do we.

Two implementations share one Protocol:
  * AlpacaPaperBroker   — real HTTP (requests) to paper-api.alpaca.markets.
  * FakeAlpacaPaperBroker — in-memory, deterministic; the injected integration
    fake the acceptance test and CI use so NO real network call is ever made.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

try:
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover - py<3.8
    from typing_extensions import Protocol, runtime_checkable  # type: ignore

PAPER_HOST = "paper-api.alpaca.markets"
_LIVE_HOST = "api.alpaca.markets"  # named ONLY so we can hard-reject it
PAPER_BASE_URL = f"https://{PAPER_HOST}"

# Alpaca order statuses we treat as "the order is done, one way or another".
_TERMINAL = {"filled", "canceled", "expired", "rejected", "done_for_day",
             "replaced", "stopped"}
_FILLED = {"filled"}


class LiveTradingRejected(RuntimeError):
    """Raised when anything points at a non-paper (live) endpoint. This wall
    is unconditional: there is no flag, env var, or argument that opens it."""


def assert_paper_only(base_url: str) -> None:
    """Allow ONLY the exact Alpaca paper host. Every other host — the live host
    most of all — is refused. There is no argument or env var that opens this."""
    host = (urlparse(base_url).hostname or "").lower()
    if host == PAPER_HOST:
        return
    hint = " (that is the LIVE endpoint)" if host == _LIVE_HOST else ""
    raise LiveTradingRejected(
        f"refusing host {host!r}{hint}; this platform is PAPER ONLY — "
        f"ALPACA_PAPER_BASE_URL must be {PAPER_BASE_URL}")


def deterministic_client_order_id(
    *, prediction_id: str, strategy_version: str, instrument: str,
    trading_date: str, action: str,
) -> str:
    """A stable, unique-per-(prediction,strategy,instrument,date,action) id.

    Human-readable prefix for dashboard scanning + a 16-hex digest for
    uniqueness, capped well under Alpaca's 128-char client_order_id limit.
    """
    seed = "|".join([prediction_id, strategy_version, instrument.upper(),
                     trading_date, action.lower()])
    digest = sha256(seed.encode("utf-8")).hexdigest()[:16]
    inst = "".join(c for c in instrument.upper() if c.isalnum())[:8]
    return f"ie-{action.lower()}-{inst}-{trading_date}-{digest}"


@dataclass
class BrokerOrder:
    """Normalised order state (backend-agnostic view of an Alpaca order)."""
    client_order_id: str
    symbol: str
    side: str                     # "buy" | "sell"
    qty: float
    status: str                   # raw Alpaca status
    broker_order_id: Optional[str] = None
    filled_qty: float = 0.0
    filled_avg_price: Optional[float] = None
    submitted_at: Optional[str] = None
    reject_reason: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL

    @property
    def is_filled(self) -> bool:
        return self.status in _FILLED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_order_id": self.client_order_id,
            "broker_order_id": self.broker_order_id,
            "symbol": self.symbol, "side": self.side, "qty": self.qty,
            "status": self.status, "filled_qty": self.filled_qty,
            "filled_avg_price": self.filled_avg_price,
            "submitted_at": self.submitted_at,
            "reject_reason": self.reject_reason,
        }


@dataclass
class BrokerPosition:
    symbol: str
    qty: float
    avg_entry_price: float
    market_value: Optional[float] = None
    unrealized_pl: Optional[float] = None


@runtime_checkable
class Broker(Protocol):
    """The narrow surface the execution + reconciliation jobs depend on."""

    def submit_order(self, *, symbol: str, qty: float, side: str,
                     client_order_id: str) -> BrokerOrder: ...

    def get_order_by_client_id(self, client_order_id: str
                               ) -> Optional[BrokerOrder]: ...

    def list_orders(self) -> List[BrokerOrder]: ...

    def list_positions(self) -> List[BrokerPosition]: ...

    def get_account(self) -> Dict[str, Any]: ...


# --- config ------------------------------------------------------------------
@dataclass(frozen=True)
class AlpacaConfig:
    api_key: str
    secret_key: str
    base_url: str = PAPER_BASE_URL

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "AlpacaConfig":
        env = env if env is not None else os.environ
        base = env.get("ALPACA_PAPER_BASE_URL", PAPER_BASE_URL) or PAPER_BASE_URL
        assert_paper_only(base)               # refuse a live host, always
        key = env.get("ALPACA_PAPER_API_KEY", "")
        secret = env.get("ALPACA_PAPER_SECRET_KEY", "")
        if not key or not secret:
            raise RuntimeError(
                "Alpaca paper credentials missing: set ALPACA_PAPER_API_KEY and "
                "ALPACA_PAPER_SECRET_KEY (paper keys only)")
        return cls(api_key=key, secret_key=secret, base_url=base)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- real broker -------------------------------------------------------------
class AlpacaPaperBroker:
    """Real HTTP client for Alpaca's PAPER endpoint (requests-based)."""

    def __init__(self, config: AlpacaConfig, *, timeout: float = 15.0):
        assert_paper_only(config.base_url)    # belt-and-braces
        self.config = config
        self.timeout = timeout
        self._base = config.base_url.rstrip("/")

    def _headers(self) -> Dict[str, str]:
        return {"APCA-API-KEY-ID": self.config.api_key,
                "APCA-API-SECRET-KEY": self.config.secret_key}

    def _request(self, method: str, path: str, *, params=None, json_body=None):
        import requests
        url = self._base + path
        resp = requests.request(method, url, headers=self._headers(),
                                 params=params, json=json_body,
                                 timeout=self.timeout)
        return resp

    @staticmethod
    def _to_order(d: Dict[str, Any]) -> BrokerOrder:
        avg = d.get("filled_avg_price")
        return BrokerOrder(
            client_order_id=d.get("client_order_id", ""),
            symbol=d.get("symbol", ""), side=d.get("side", ""),
            qty=float(d.get("qty") or 0), status=d.get("status", "unknown"),
            broker_order_id=d.get("id"),
            filled_qty=float(d.get("filled_qty") or 0),
            filled_avg_price=float(avg) if avg not in (None, "") else None,
            submitted_at=d.get("submitted_at"), raw=d)

    def submit_order(self, *, symbol: str, qty: float, side: str,
                     client_order_id: str) -> BrokerOrder:
        body = {"symbol": symbol, "qty": str(qty), "side": side,
                "type": "market", "time_in_force": "day",
                "client_order_id": client_order_id}
        resp = self._request("POST", "/v2/orders", json_body=body)
        if resp.status_code in (200, 201):
            return self._to_order(resp.json())
        # Duplicate client_order_id -> the order already exists; fetch + return
        # it (idempotent submit, exactly what a twice-fired job needs).
        if resp.status_code in (403, 422):
            existing = self.get_order_by_client_id(client_order_id)
            if existing is not None:
                return existing
        raise RuntimeError(
            f"Alpaca paper order submit failed (HTTP {resp.status_code})")

    def get_order_by_client_id(self, client_order_id: str
                               ) -> Optional[BrokerOrder]:
        resp = self._request("GET", "/v2/orders:by_client_order_id",
                             params={"client_order_id": client_order_id})
        if resp.status_code == 200:
            return self._to_order(resp.json())
        return None

    def list_orders(self) -> List[BrokerOrder]:
        resp = self._request("GET", "/v2/orders",
                             params={"status": "all", "limit": 500})
        resp.raise_for_status()
        return [self._to_order(d) for d in resp.json()]

    def list_positions(self) -> List[BrokerPosition]:
        resp = self._request("GET", "/v2/positions")
        resp.raise_for_status()
        out = []
        for d in resp.json():
            out.append(BrokerPosition(
                symbol=d.get("symbol", ""), qty=float(d.get("qty") or 0),
                avg_entry_price=float(d.get("avg_entry_price") or 0),
                market_value=float(d["market_value"]) if d.get("market_value")
                else None,
                unrealized_pl=float(d["unrealized_pl"]) if d.get("unrealized_pl")
                else None))
        return out

    def get_account(self) -> Dict[str, Any]:
        resp = self._request("GET", "/v2/account")
        resp.raise_for_status()
        return resp.json()


# --- fake broker (tests + acceptance; NO network) ----------------------------
class FakeAlpacaPaperBroker:
    """Deterministic in-memory Alpaca-paper stand-in.

    Dedupes on client_order_id exactly like Alpaca; supports simulating fills
    and cancellations from test code. Positions are derived from filled orders.
    This is the injected integration fake — the acceptance test drives the full
    submit -> fill -> reconcile flow through it with no real network call.
    """

    def __init__(self, *, equity: float = 100_000.0):
        self._orders: Dict[str, BrokerOrder] = {}
        self._equity = equity
        self._prices: Dict[str, float] = {}

    # -- Broker surface ------------------------------------------------------
    def submit_order(self, *, symbol: str, qty: float, side: str,
                     client_order_id: str) -> BrokerOrder:
        if client_order_id in self._orders:
            return self._orders[client_order_id]     # idempotent dedup
        order = BrokerOrder(
            client_order_id=client_order_id, symbol=symbol.upper(), side=side,
            qty=float(qty), status="accepted",
            broker_order_id=f"fake-{len(self._orders) + 1}",
            submitted_at=_now())
        self._orders[client_order_id] = order
        return order

    def get_order_by_client_id(self, client_order_id: str
                               ) -> Optional[BrokerOrder]:
        return self._orders.get(client_order_id)

    def list_orders(self) -> List[BrokerOrder]:
        return list(self._orders.values())

    def list_positions(self) -> List[BrokerPosition]:
        agg: Dict[str, List[float]] = {}
        for o in self._orders.values():
            if not o.is_filled:
                continue
            signed = o.filled_qty if o.side == "buy" else -o.filled_qty
            px = o.filled_avg_price or 0.0
            q, cost = agg.get(o.symbol, [0.0, 0.0])
            agg[o.symbol] = [q + signed, cost + signed * px]
        out = []
        for sym, (q, cost) in agg.items():
            if abs(q) < 1e-9:
                continue
            out.append(BrokerPosition(symbol=sym, qty=q,
                                      avg_entry_price=(cost / q) if q else 0.0))
        return out

    def get_account(self) -> Dict[str, Any]:
        return {"status": "ACTIVE", "buying_power": str(self._equity),
                "equity": str(self._equity), "account_type": "PAPER"}

    # -- test controls -------------------------------------------------------
    def simulate_fill(self, client_order_id: str, *, price: float,
                      qty: Optional[float] = None) -> BrokerOrder:
        o = self._orders[client_order_id]
        fq = o.qty if qty is None else float(qty)
        o.status = "filled" if fq >= o.qty else "partially_filled"
        o.filled_qty = fq
        o.filled_avg_price = float(price)
        self._prices[o.symbol] = float(price)
        return o

    def simulate_reject(self, client_order_id: str, reason: str = "rejected"
                        ) -> BrokerOrder:
        o = self._orders[client_order_id]
        o.status = "rejected"
        o.reject_reason = reason
        return o
