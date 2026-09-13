"""The paper-trading boundary — enforced, not promised.

For sixteen days "paper only" was true because nothing had been built that
could place an order. Unattended operation changes the risk: the system now
runs without a human watching, so the guarantee has to be structural rather
than circumstantial.

FAIL CLOSED
-----------
The only supported mode is PAPER.

  * unset or empty  -> PAPER, recorded as `default`. Absent configuration
    resolves to the SAFE state, never to a permissive one.
  * "PAPER"         -> PAPER, recorded as `env`.
  * anything else   -> TradingModeError, and the cycle refuses to start.

That last branch is the one that matters. A typo, a half-finished experiment or
a copied config that says LIVE does not degrade to a warning and does not fall
back to paper silently -- it stops the run. A configuration the system does not
understand is not a configuration it may interpret generously.

WHY REFUSE RATHER THAN COERCE
-----------------------------
Coercing an unknown value to PAPER would be safe today and would hide the fact
that someone believes this system trades live. The error is the useful output:
it says the operator's intent and the system's capability disagree, which is
exactly the moment a human should be involved.

There is no live path to enable. This module has no branch that returns
anything but PAPER, and `assert_paper_only` is called by every cycle before any
position work happens.
"""
from __future__ import annotations

import os
from typing import Mapping, Optional

PAPER = "PAPER"
ENV_VAR = "TRADING_MODE"

# Deliberately a one-element set. Adding to it is the change a reviewer must
# see; a mode that is "supported" only by being spelled correctly somewhere in
# a config file is not supported.
SUPPORTED = frozenset({PAPER})


class TradingModeError(RuntimeError):
    """The configured trading mode is not one this system implements."""


def resolve(env: Optional[Mapping[str, str]] = None) -> dict:
    """Resolve the trading mode, or refuse.

    Returns {"mode", "source"}. Raises TradingModeError for any value outside
    SUPPORTED -- including values that merely LOOK like a live mode, which get
    an explicit message rather than a generic one, because that is the case
    where a human most needs to understand what just happened.
    """
    env = os.environ if env is None else env
    raw = (env.get(ENV_VAR) or "").strip()
    if not raw:
        return {"mode": PAPER, "source": "default"}
    value = raw.upper()
    if value in SUPPORTED:
        return {"mode": PAPER, "source": "env"}
    raise TradingModeError(
        f"{ENV_VAR}={raw!r} is not supported. This engine implements paper "
        f"trading only: it has no broker integration, no order-submission "
        f"path and no capital. Supported values: {sorted(SUPPORTED)}. "
        f"Refusing to start rather than assuming what was meant.")


def assert_paper_only(env: Optional[Mapping[str, str]] = None) -> str:
    """Called before any position work. Raises unless the mode is PAPER."""
    resolved = resolve(env)
    if resolved["mode"] != PAPER:  # pragma: no cover - unreachable by design
        raise TradingModeError("only paper trading is implemented")
    return resolved["mode"]
