"""Decision identity — opaque ULID + human-readable key (Slice 1 / T010).

Terminology is locked (architecture review, 2026-07-20):

    decision_id   = opaque ULID. Internal primary key and every foreign key.
    decision_key  = DEC-YYYY-NNNNNN. Human-facing display / search ONLY;
                    never carries referential load, so its per-year counter
                    needs no cross-agent coordination and a collision there
                    can never corrupt storage.

Stdlib only (no new dependency, A3). A ULID is a 48-bit millisecond
timestamp + 80 bits of randomness, Crockford-base32 encoded to 26 chars,
lexicographically sortable. Event *ordering* does not rely on ULID sort —
`decision_events.sequence_number` is the authority — so this stays simple.
"""
from __future__ import annotations

import os
import re
import time

# Crockford base32 alphabet (excludes I, L, O, U to avoid ambiguity).
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_MASK80 = (1 << 80) - 1
_MASK48 = (1 << 48) - 1


def _b32(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        value, rem = divmod(value, 32)
        chars.append(_CROCKFORD[rem])
    return "".join(reversed(chars))


def new_ulid(ts_ms: int | None = None) -> str:
    """A 26-char Crockford-base32 ULID. 80 bits of randomness make a
    collision negligible; the DB also enforces UNIQUE as a backstop."""
    ms = int(time.time() * 1000) if ts_ms is None else int(ts_ms)
    rand = int.from_bytes(os.urandom(10), "big")
    return _b32(ms & _MASK48, 10) + _b32(rand & _MASK80, 16)


def is_ulid(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 26
            and all(c in _CROCKFORD for c in value))


_KEY_RE = re.compile(r"^DEC-(\d{4})-(\d{6})$")


def format_decision_key(year: int, seq: int) -> str:
    """DEC-YYYY-NNNNNN. `seq` is a per-year counter allocated inside the
    same transaction that writes the record (see DecisionService)."""
    if not (0 <= seq <= 999999):
        raise ValueError(f"decision_key sequence out of range: {seq}")
    return f"DEC-{year:04d}-{seq:06d}"


def is_decision_key(value: object) -> bool:
    return bool(isinstance(value, str) and _KEY_RE.match(value))
