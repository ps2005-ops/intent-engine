"""Learning & Promotion Ledger — append-only storage.

Same storage discipline as `core/prediction_ledger.py`: one SQLite file,
each record persisted as a JSON blob in a `data` column, append-only, and
reads collapse to the latest row per id. No UPDATE, no DELETE — a status
change to a candidate appends a new row with the same id, exactly like the
prediction ledger resolving a prediction.

Three tables in one file (candidates, evaluations, promotions) because
their read shapes differ (a candidate has a folded latest-status; an
evaluation is immutable and many-per-candidate). This mirrors the
per-store-owns-its-schema convention db.py documents.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Union

from intent_engine.core.db import get_connection
from intent_engine.learning.records import (
    Candidate, Evaluation, PromotionDecision,
)

DEFAULT_LEARNING_PATH = Path("data/learning_ledger.db")


def _ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS candidates (
            id TEXT NOT NULL, created_at TEXT NOT NULL, source TEXT NOT NULL,
            status TEXT NOT NULL, data TEXT NOT NULL)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS evaluations (
            id TEXT NOT NULL, candidate_id TEXT NOT NULL,
            created_at TEXT NOT NULL, data TEXT NOT NULL)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS promotions (
            id TEXT NOT NULL, candidate_id TEXT NOT NULL,
            decided_at TEXT NOT NULL, data TEXT NOT NULL)"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cand_id ON candidates(id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_cand ON evaluations(candidate_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_promo_cand ON promotions(candidate_id)")
    conn.commit()


class LearningStore:
    def __init__(self, path: Union[str, Path] = DEFAULT_LEARNING_PATH):
        self.path = Path(path)

    # --- writes (append-only) ------------------------------------------------
    def append_candidate(self, candidate: Candidate) -> Candidate:
        conn = get_connection(self.path)
        try:
            _ensure_schema(conn)
            conn.execute(
                "INSERT INTO candidates (id, created_at, source, status, data) "
                "VALUES (?, ?, ?, ?, ?)",
                (candidate.id, candidate.created_at, candidate.source,
                 candidate.status, candidate.model_dump_json()),
            )
            conn.commit()
        finally:
            conn.close()
        return candidate

    def append_evaluation(self, evaluation: Evaluation) -> Evaluation:
        conn = get_connection(self.path)
        try:
            _ensure_schema(conn)
            conn.execute(
                "INSERT INTO evaluations (id, candidate_id, created_at, data) "
                "VALUES (?, ?, ?, ?)",
                (evaluation.id, evaluation.candidate_id, evaluation.created_at,
                 evaluation.model_dump_json()),
            )
            conn.commit()
        finally:
            conn.close()
        return evaluation

    def append_promotion(self, promotion: PromotionDecision) -> PromotionDecision:
        conn = get_connection(self.path)
        try:
            _ensure_schema(conn)
            conn.execute(
                "INSERT INTO promotions (id, candidate_id, decided_at, data) "
                "VALUES (?, ?, ?, ?)",
                (promotion.id, promotion.candidate_id, promotion.decided_at,
                 promotion.model_dump_json()),
            )
            conn.commit()
        finally:
            conn.close()
        return promotion

    # --- reads (collapse to latest per id) -----------------------------------
    def _rows(self, table: str, order: str) -> List[str]:
        if not self.path.exists():
            return []
        conn = get_connection(self.path)
        try:
            _ensure_schema(conn)
            rows = conn.execute(
                f"SELECT data FROM {table} ORDER BY {order}").fetchall()
        finally:
            conn.close()
        return [r[0] for r in rows]

    def get_candidate(self, candidate_id: str) -> Optional[Candidate]:
        latest: Optional[Candidate] = None
        for blob in self._rows("candidates", "rowid"):
            c = Candidate.model_validate_json(blob)
            if c.id == candidate_id:
                latest = c
        return latest

    def list_candidates(
        self, *, status: Optional[str] = None, source: Optional[str] = None,
    ) -> List[Candidate]:
        folded: Dict[str, Candidate] = {}
        for blob in self._rows("candidates", "rowid"):
            c = Candidate.model_validate_json(blob)
            folded[c.id] = c
        out = list(folded.values())
        if status is not None:
            out = [c for c in out if c.status == status]
        if source is not None:
            out = [c for c in out if c.source == source]
        return out

    def evaluations_for(self, candidate_id: str) -> List[Evaluation]:
        return [Evaluation.model_validate_json(b)
                for b in self._rows("evaluations", "rowid")
                if Evaluation.model_validate_json(b).candidate_id == candidate_id]

    def promotion_for(self, candidate_id: str) -> Optional[PromotionDecision]:
        latest: Optional[PromotionDecision] = None
        for blob in self._rows("promotions", "rowid"):
            p = PromotionDecision.model_validate_json(blob)
            if p.candidate_id == candidate_id:
                latest = p
        return latest
