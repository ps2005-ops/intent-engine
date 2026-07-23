"""Append-only product store (T020): `data/product.jsonl`.

The append-only discipline — flock, fsync, fingerprint-checked
idempotency, loud corruption, no mutation API, and the (mtime_ns, size)
parse cache — now lives ONCE in `agentos.append_only.AppendOnlyStore`
(T022). This store subclasses it and adds only its domain query methods;
behaviour is unchanged.
"""
from __future__ import annotations

from pathlib import Path

from intent_engine.agentos.append_only import AppendOnlyStore, CorruptLogError
from intent_engine.product.records import ProductError, ProductEvent

DEFAULT_PRODUCT_PATH = Path("data/product.jsonl")


class ProductCorruptLogError(CorruptLogError):
    """The product log contains a line that cannot be parsed."""


class ProductStore(AppendOnlyStore):
    event_cls = ProductEvent
    record_error = ProductError
    corrupt_error = ProductCorruptLogError

    def __init__(self, path=DEFAULT_PRODUCT_PATH):
        super().__init__(path)

    def for_field(self, field_name: str, value: str) -> list[ProductEvent]:
        return [r for r in self.read_all() if getattr(r, field_name) == value]

    def for_proposal(self, proposal_id: str) -> list[ProductEvent]:
        return self.for_field("proposal_id", proposal_id)

    def for_problem(self, problem_id: str) -> list[ProductEvent]:
        return self.for_field("problem_id", problem_id)

    def for_opportunity(self, opportunity_id: str) -> list[ProductEvent]:
        return self.for_field("opportunity_id", opportunity_id)

    def ids(self, field_name: str) -> list[str]:
        return sorted({getattr(r, field_name) for r in self.read_all()
                       if getattr(r, field_name)})
