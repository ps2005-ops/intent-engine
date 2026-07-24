"""Append-only store of paper-trading eligibility rejections.

"Persist rejection reasons for ineligible predictions" (1C) — so a prediction
that did NOT become a trade is auditable, not silently dropped. Append-only
JSONL under the run root; idempotent per (prediction_id, as_of-day) so a
re-run of the daily job does not duplicate a rejection.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Union

from intent_engine.paper.eligibility import EligibilityResult

DEFAULT_REJECTIONS_PATH = Path("data/paper_rejections.jsonl")


class RejectionStore:
    def __init__(self, path: Union[str, Path] = DEFAULT_REJECTIONS_PATH):
        self.path = Path(path)

    def _key(self, prediction_id: str, as_of: str) -> str:
        return f"{prediction_id}:{as_of[:10]}"

    def _keys(self) -> set:
        return {r["key"] for r in self.read_all()}

    def record(self, result: EligibilityResult, *, as_of: str) -> bool:
        """Append a rejection. Returns False if an identical (prediction, day)
        rejection already exists (idempotent)."""
        if result.eligible:
            raise ValueError("only ineligible results are recorded here")
        key = self._key(result.prediction_id, as_of)
        if key in self._keys():
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {"key": key, "prediction_id": result.prediction_id,
               "reason": result.reason, "rule": result.rule,
               "as_of": as_of,
               "recorded_at": datetime.now(timezone.utc).isoformat(
                   timespec="seconds")}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
        return True

    def read_all(self) -> List[dict]:
        if not self.path.exists():
            return []
        out = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    out.append(json.loads(line))
        return out
