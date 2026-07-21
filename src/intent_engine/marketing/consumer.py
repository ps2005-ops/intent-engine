"""Marketing company-event consumer (T017) — C3's hook, as a proper
checkpointed consumer.

`prediction.recorded` fans a ledger fact into the full draft set (C3).
Everything else it handles is recorded as a marketing observation only.
Nothing publishes; nothing auto-approves.
"""
from __future__ import annotations

from pathlib import Path

_HANDLED = {"prediction.recorded", "report.generated"}


class MarketingCompanyEventConsumer:
    consumer_name = "marketing"

    def __init__(self, *, drafts_root, ledger_path=None):
        self.drafts_root = Path(drafts_root)
        self.ledger_path = ledger_path
        self.drafted = []
        self.skipped = 0

    def handles(self, event_type: str) -> bool:
        return event_type in _HANDLED

    def process(self, event) -> None:
        if event.event_type != "prediction.recorded":
            self.skipped += 1          # observed, no draft set defined yet
            return
        if self.ledger_path is None:
            self.skipped += 1
            return
        from intent_engine.core.prediction_ledger import list_predictions
        rows = [p for p in list_predictions(path=self.ledger_path)
                if p.id == event.prediction_id]
        if not rows:
            # No identity guessing: an event without a resolvable ledger row
            # is skipped and counted, never invented.
            self.skipped += 1
            return
        from intent_engine.marketing.generators import fan_out_prediction
        written = fan_out_prediction(rows[0], drafts_root=self.drafts_root,
                                     ledger_path=self.ledger_path)
        self.drafted.append(rows[0].id)
        # File writes are deterministic and byte-identical on replay, so
        # re-delivery cannot double-draft.
        return written
