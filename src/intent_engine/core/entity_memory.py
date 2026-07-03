"""Stage A: entity memory. A structured, append-only store that both simulator/
and voice/ write into, per docs/weekly/intent-engine-v2-entity-memory.md.

Deliberately minimal for this pass: plain records, JSON Lines storage, full-scan
reads. Get writing and retrieval working before adding any reasoning sophistication
(Stage D+). Out of scope here: SQLite, grants persistence, PersonalContext, voice/,
Stage C/D — see the plan doc.
"""

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Protocol, Union

from pydantic import BaseModel, Field

try:
    from typing import Literal
except ImportError:  # pragma: no cover - py<3.8 fallback, not expected here
    from typing_extensions import Literal

DEFAULT_PATH = Path("data/entity_memory.jsonl")

_PUNCTUATION_EXCEPT_HYPHEN = re.compile(r"[^\w\s-]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize_entity_id(raw: str) -> str:
    """Normalize an entity identifier so the same entity always maps to the same id.

    Lowercase, strip leading/trailing whitespace, collapse internal whitespace,
    strip punctuation except hyphens. Without this, "Sarah's Startup", "sarahs
    startup", and "  Sarah's Startup  " would each become a distinct entity_id,
    silently orphaning records across what should be one accumulating history --
    memory would never actually accumulate, it would just fragment into
    near-duplicate entities per input variation (capitalization, punctuation,
    stray whitespace) of what a human typed for the same real person or company.
    """
    normalized = raw.strip().lower()
    normalized = _PUNCTUATION_EXCEPT_HYPHEN.sub("", normalized)
    normalized = _WHITESPACE.sub(" ", normalized)
    return normalized.strip()


def _new_record_id() -> str:
    return str(uuid.uuid4())


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class EntityMemoryRecord(BaseModel):
    # record_id/timestamp are generated at construction time via default_factory
    # (practically "write time," since callers build a record immediately before
    # writing it) -- unlike entity_id, these are fresh-generated values, not a
    # transformation of caller input, so there's nothing for the writer to do to
    # them. entity_id normalization is different: it transforms whatever raw
    # string the caller passed in, and is deliberately NOT done here (see
    # normalize_entity_id's docstring and JsonlEntityMemoryWriter.write below) --
    # it happens in the writer so every write path normalizes consistently,
    # rather than trusting every caller to remember to do it themselves.
    record_id: str = Field(default_factory=_new_record_id)
    entity_id: str
    source: Literal["simulator", "voice"]
    timestamp: str = Field(default_factory=_current_timestamp)

    decision_text: str
    goals: List[str]
    constraints: List[str]
    risk_tolerance: Optional[str] = None
    primary_priority: Optional[str] = None  # simulator-only; None from voice writes

    outcome: Optional[str] = None  # reserved for Stage D+, always None for now


class EntityMemoryWriter(Protocol):
    """Deliberately not a Stage. Stage.run() (core/pipeline.py) models
    compute-and-return-a-value -- every existing Stage (IntentClassifier,
    PremortemAnalyzer, RiskAuditGenerator) takes input and produces a result
    consumers use. A memory writer's job is a side effect (persist a record), not
    a computed value; forcing it into run()->value would mean either returning
    None (misleading -- implies "this Stage doesn't compute anything") or
    inventing a fake return value just to satisfy an abstraction it doesn't fit.
    Own small contract instead, using structural typing (Protocol) rather than
    another ABC subclass, so it doesn't read as "a kind of Stage" at all."""

    def write(self, record: EntityMemoryRecord) -> None: ...


class JsonlEntityMemoryWriter:
    """Appends one JSON record per line to a local file.

    No locking/concurrency control -- fine for a single-process CLI, would need
    revisiting (e.g. file locking, or a real database) for concurrent writers.
    """

    def __init__(self, path: Union[str, Path] = DEFAULT_PATH):
        self.path = Path(path)

    def write(self, record: EntityMemoryRecord) -> None:
        normalized = record.model_copy(update={"entity_id": normalize_entity_id(record.entity_id)})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(normalized.model_dump_json() + "\n")


def read_records(entity_id: str, path: Union[str, Path] = DEFAULT_PATH) -> List[EntityMemoryRecord]:
    """Full scan of the JSONL file, filtered by normalized entity_id.

    O(n) in total record count per read -- fine while entity memory is small and
    single-user; revisit (e.g. an index, or a real database) if the file grows
    large enough that a full scan per read becomes a real cost. Same kind of
    scaling note as simulator/retrieval.py's TF-IDF corpus size.
    """
    target = normalize_entity_id(entity_id)
    path = Path(path)
    if not path.exists():
        return []

    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = EntityMemoryRecord.model_validate_json(line)
            if record.entity_id == target:
                records.append(record)
    return records
