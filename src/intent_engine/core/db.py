"""Data-foundation pass, Stage 1: shared low-level SQLite connection helper.

Deliberately minimal, matching the ownership boundary each store already
had under the JSONL convention: this module only opens/creates a
connection. It does NOT own table schema -- each store (entity_memory.py,
suggestion.py, draft_generator.py, phase0_trial_log.py) already
independently implemented its own read/write logic against its own file;
this preserves that same per-store ownership, just swapping the file
format underneath. A shared generic ORM-style abstraction across all 4
stores was considered and rejected here: their record shapes (some have a
stable id and get "latest wins" collapsing on repeat appends, one has no
id at all) differ enough that forcing one shared table-schema abstraction
over them would fit none of them well.
"""

import sqlite3
from pathlib import Path
from typing import Union


def get_connection(path: Union[str, Path]) -> sqlite3.Connection:
    """Opens (creating if needed) a SQLite connection at path. WAL mode:
    readers don't block writers, matching this project's existing
    single-process-many-callers usage (a CLI run followed by a test
    reading the same file, etc.) better than the default rollback
    journal, at negligible cost for files this size."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
