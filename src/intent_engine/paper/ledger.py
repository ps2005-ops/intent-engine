"""Paper-Trading Shadow Loop — append-only position storage.

Same discipline as the prediction ledger: one SQLite file, each position a
JSON blob, append-only, reads collapse to the latest row per id (closing a
position appends a new row with the same id).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Union

from intent_engine.core.db import get_connection
from intent_engine.paper.records import PaperPosition

DEFAULT_PAPER_PATH = Path("data/paper_book.db")


def _ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS positions (
            id TEXT NOT NULL, opened_at TEXT NOT NULL,
            prediction_id TEXT NOT NULL, status TEXT NOT NULL,
            data TEXT NOT NULL)"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_id ON positions(id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_pred ON positions(prediction_id)")
    conn.commit()


class PaperStore:
    def __init__(self, path: Union[str, Path] = DEFAULT_PAPER_PATH):
        self.path = Path(path)

    def append(self, position: PaperPosition) -> PaperPosition:
        conn = get_connection(self.path)
        try:
            _ensure_schema(conn)
            conn.execute(
                "INSERT INTO positions (id, opened_at, prediction_id, status, data) "
                "VALUES (?, ?, ?, ?, ?)",
                (position.id, position.opened_at, position.prediction_id,
                 position.status, position.model_dump_json()),
            )
            conn.commit()
        finally:
            conn.close()
        return position

    def _all(self) -> List[PaperPosition]:
        if not self.path.exists():
            return []
        conn = get_connection(self.path)
        try:
            _ensure_schema(conn)
            rows = conn.execute("SELECT data FROM positions ORDER BY rowid").fetchall()
        finally:
            conn.close()
        return [PaperPosition.model_validate_json(r[0]) for r in rows]

    def latest(self) -> List[PaperPosition]:
        folded: Dict[str, PaperPosition] = {}
        for p in self._all():
            folded[p.id] = p
        return list(folded.values())

    def get(self, position_id: str) -> Optional[PaperPosition]:
        return next((p for p in self.latest() if p.id == position_id), None)

    def open_positions(self) -> List[PaperPosition]:
        return [p for p in self.latest() if p.status == "open"]

    def closed_positions(self) -> List[PaperPosition]:
        return [p for p in self.latest() if p.status == "closed"]

    def by_prediction(self, prediction_id: str) -> List[PaperPosition]:
        return [p for p in self.latest() if p.prediction_id == prediction_id]
