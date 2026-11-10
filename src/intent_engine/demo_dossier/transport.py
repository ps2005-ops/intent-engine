"""Transport adapters. One of several, and never the contract.

WHY THIS FILE IS SMALL AND SEPARATE
------------------------------------
`read_market_snapshot` and `read_founder_snapshot` take a mapping. Getting the
mapping is somebody's job, but it is not the join's job, and keeping it in its
own module is what makes the ADR's OPTION D rejection checkable: if dossier
logic ever needed a path, the import would have to appear somewhere outside
this file, and a test asserts it does not.

`market.dossier_transport` already ships these payloads over HTTP, so the
filesystem was never the only transport in this program — only the only one
anybody had written down.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Optional

#: Where the market engine publishes demo snapshots when the transport is a
#: shared disk. A DEFAULT, not a requirement — pass any directory, or skip
#: this module entirely and hand a dict straight to the reader.
MARKET_SNAPSHOT_DIR = ("reports", "market", "demo_snapshots")


def payload_from_bytes(raw: Any) -> Optional[dict]:
    """Deserialize one snapshot from bytes or text. Returns None on anything
    unreadable — the caller turns that into a stated absence with a reason,
    which is the only reading a corrupt payload is entitled to."""
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, dict):
        return raw
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def payload_from_file(path) -> Optional[dict]:
    """Read one snapshot off a disk. A missing file returns None; it is not
    an error, because a company the market engine has never published is the
    normal case and always will be."""
    p = pathlib.Path(path)
    if not p.exists():
        return None
    try:
        return payload_from_bytes(p.read_text(encoding="utf-8"))
    except OSError:
        return None


def market_snapshot_path(root, company_key: str):
    """The conventional location under a shared root."""
    return pathlib.Path(root).joinpath(*MARKET_SNAPSHOT_DIR) / \
        f"{company_key}.json"
