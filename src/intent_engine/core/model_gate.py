"""The one place a hosted model can be refused, and the one place calls are counted.

WHY A GATE RATHER THAN "UNSET THE KEY"
--------------------------------------
Removing `ANTHROPIC_API_KEY` from the environment was the only way to reach a
zero-Anthropic run, and it is not a deployment control:

  * `analyst/runner.default_client` calls `load_dotenv()` BEFORE it checks the
    variable, so a `.env` file on disk resupplies a key the operator thought
    they had removed;
  * the Render CLI cannot unset an environment variable at all, which is
    recorded in `scripts/zero_anthropic_proof.py` as the reason the hosted
    preview could never serve that half of the proof;
  * "the key happens to be absent" is a property of an environment, not a
    property an operator can assert, test, or hand to a security reviewer.

So the refusal is explicit and positive: `ZERO_ANTHROPIC=1` means no hosted
Anthropic client may be constructed and no hosted Anthropic call may be made,
whatever credentials are lying around.

WHY BOTH CONSTRUCTION AND INVOCATION ARE GUARDED
------------------------------------------------
Guarding construction alone is not sufficient and the reason is ordinary: a
client constructed while the gate was open is an ordinary Python object that
outlives the flag. A long-lived `WebApp` builds its analyst client once, in
`__init__`, and holds it for the process lifetime — so a gate consulted only at
construction would be consulted once, at boot, and never again. `call_tool`
therefore re-checks immediately before the SDK call, which is the last
instruction under this repository's control before the network.

WHY THE COUNTER IS HERE AND NOT IN A TEST
-----------------------------------------
"Zero calls" has to be a MEASUREMENT, not an observation. A test that asserts
"no exception was raised" proves only that the paths it happened to drive did
not call; it cannot distinguish a path that did not call from a path that was
never reached. A counter incremented at the SDK boundary answers the question
directly, in both modes, and lets the ASSISTED run state its real call count
rather than an assumed one.

The counter is deliberately process-global and unsynchronised-but-atomic
(a single `+=` on a module-level int under CPython's GIL, and every writer is
the analysis worker or a test). It counts INVOCATIONS THAT REACHED THE SDK, not
attempts, not cache hits, and not retries the caller decided against — a cached
analysis makes no call and must not be counted as one, which is exactly the
distinction the A/B comparison needs.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-----------------------------------------
It does not decide what a caller should do when refused. `default_client`
returns `None` and the product reports an honest `EVIDENCE_LIMITED` state;
a direct `LLMClient(...)` construction raises. Those are different callers with
different contracts, and a gate that picked one for them would be making a
product decision inside an infrastructure guard.
"""
from __future__ import annotations

import os
import threading

#: The operator-facing switch. Positive rather than negative on purpose: an
#: absent variable means "ordinary behaviour", and the only way to reach a
#: zero-Anthropic runtime is to say so.
ZERO_ANTHROPIC_ENV = "ZERO_ANTHROPIC"

_TRUTHY = ("1", "true", "yes", "on")

_lock = threading.Lock()
_calls = 0


class AnthropicDisabled(RuntimeError):
    """A hosted Anthropic client was reached for while the gate is closed.

    Raised rather than returned so a caller that ignores it cannot proceed on
    a client it does not have. Callers that have an honest degraded path --
    `analyst.runner.default_client` is the one on the product path -- consult
    `anthropic_disabled()` first and never see this.
    """


def anthropic_disabled(env=None) -> bool:
    """True when this process may not construct or call a hosted Anthropic model.

    Read at CALL TIME, never cached, so a test or an operator can change the
    mode of a running process and the next call obeys it. Caching it would
    reintroduce exactly the staleness the `call_tool` guard exists to close.
    """
    env = os.environ if env is None else env
    return str(env.get(ZERO_ANTHROPIC_ENV, "")).strip().lower() in _TRUTHY


def require_anthropic_allowed(where: str) -> None:
    """Raise if the gate is closed. `where` names the boundary for the message."""
    if anthropic_disabled():
        raise AnthropicDisabled(
            f"{ZERO_ANTHROPIC_ENV} is set, so {where} is refused. No hosted "
            "Anthropic client may be constructed and no hosted Anthropic call "
            "may be made in this process.")


def record_call() -> None:
    """One invocation reached the Anthropic SDK."""
    global _calls
    with _lock:
        _calls += 1


def calls() -> int:
    """Invocations that reached the SDK since the last `reset_calls()`."""
    return _calls


def reset_calls() -> None:
    """Zero the counter. For a test or a measured run, never for production."""
    global _calls
    with _lock:
        _calls = 0
