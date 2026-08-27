"""Durable form of the canonical core: append-only JSONL under one root.

WHY A FILE AND NOT A DATABASE
-----------------------------
The two products already share exactly one thing in deployment: a runtime
root. `MARKET_SNAPSHOT_ROOT` is how the market engine's strategic dossiers
reach the founder service today, and putting the economic core anywhere else
would create a second, differently-configured seam to keep in sync.

APPEND-ONLY, AND WHY THAT IS ENFORCED HERE RATHER THAN PROMISED
----------------------------------------------------------------
`append` opens for append and never for write. There is no update, no delete
and no compaction. A belief that moved is a new revision row; a node that was
revised is a new node row carrying its predecessor. Reload folds the rows
forward in order, so the file IS the history and reading it at any prefix
gives the state at that point — which is what makes `replay` possible at all.

READS ARE VINTAGE-CAPABLE
-------------------------
`load(kind, upto=...)` stops at the first row whose `written_at` is after the
cutoff. That is deliberately a WRITE-ORDER cutoff, not a content-date filter:
the question replay asks is "what had this engine recorded by then", and
answering it from content dates would let a backfilled row appear in a past
vintage.
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

from .vocabulary import CONTRACT as CORE_CONTRACT, EconError, require

CONTRACT = "econ_store.v1"

#: Sub-directory of the runtime root. One place, named once.
ECON_DIR = "econ"

#: The record kinds this store holds. A kind not listed is refused, because
#: an unrecognised kind is how a store becomes a junk drawer nobody can
#: reload.
KINDS = ("node", "belief", "belief_revision", "expectation",
         "expectation_resolution", "causal_edge", "attack", "aggregate",
         "zero_trade", "cycle_counts", "candidate", "state_snapshot",
         "replay_verdict", "priority")


class StoreError(EconError):
    """A refusal by the durable store."""


def econ_root(runtime_root) -> pathlib.Path:
    return pathlib.Path(runtime_root) / ECON_DIR


def path_for(runtime_root, kind: str) -> pathlib.Path:
    require(kind in KINDS,
            f"{kind!r} is not a declared record kind; known: {list(KINDS)}")
    return econ_root(runtime_root) / f"{kind}.jsonl"


def append(runtime_root, kind: str, payload: dict, *,
           written_at: str) -> dict:
    """Write one row. Opens for append; there is no other mode.

    `written_at` is the WRITE time and is separate from anything inside the
    payload. A payload's own dates describe the world; this one describes the
    ledger, and vintage reads use it.
    """
    require(bool(written_at), "every row records when it was written")
    target = path_for(runtime_root, kind)
    target.parent.mkdir(parents=True, exist_ok=True)
    row = {"contract": CONTRACT, "kind": kind, "written_at": written_at,
           "payload": payload}
    line = json.dumps(row, sort_keys=True, default=str)
    # One write, one line, opened in append mode. Two processes appending
    # short lines to the same file will not interleave within a line on any
    # POSIX filesystem this runs on, which is the property the market
    # engine's own ledgers already rely on.
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return row


def append_many(runtime_root, kind: str, payloads: Sequence[dict], *,
                written_at: str) -> int:
    for payload in payloads:
        append(runtime_root, kind, payload, written_at=written_at)
    return len(payloads)


def load(runtime_root, kind: str, *, upto: str = "") -> List[dict]:
    """Every payload of one kind, in write order, optionally truncated.

    A malformed line is SKIPPED and counted rather than raising. A single
    truncated write -- a process killed mid-append -- must not make the whole
    ledger unreadable, because the ledger is the only copy of the history.
    `load_with_health` exposes the count for anything that needs to care.
    """
    return [row["payload"] for row in _rows(runtime_root, kind, upto=upto)]


def load_with_health(runtime_root, kind: str, *, upto: str = "") -> dict:
    rows, malformed = [], 0
    target = path_for(runtime_root, kind)
    if not target.exists():
        return {"payloads": [], "rows": 0, "malformed": 0, "exists": False}
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if upto and str(row.get("written_at", "")) > upto:
            break
        rows.append(row)
    return {"payloads": [r.get("payload") for r in rows], "rows": len(rows),
            "malformed": malformed, "exists": True}


def _rows(runtime_root, kind: str, *, upto: str = "") -> Iterator[dict]:
    health = load_with_health(runtime_root, kind, upto=upto)
    for i, payload in enumerate(health["payloads"]):
        yield {"payload": payload, "index": i}


def summary(runtime_root) -> dict:
    """What the core holds, by kind. What `/learning` opens with."""
    out: Dict[str, Any] = {"contract": CONTRACT,
                           "root": str(econ_root(runtime_root))}
    counts, malformed = {}, {}
    for kind in KINDS:
        health = load_with_health(runtime_root, kind)
        if not health["exists"]:
            continue
        counts[kind] = health["rows"]
        if health["malformed"]:
            malformed[kind] = health["malformed"]
    out["counts"] = counts
    out["total_rows"] = sum(counts.values())
    # Reported, never swallowed. A truncated row is a real event in the
    # history of the ledger and hiding it would make a partial reload look
    # like a quiet one.
    out["malformed_rows"] = malformed
    return out
