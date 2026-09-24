"""Versioned persistence for the materialized view.

WHY APPEND-ONLY
----------------
`DecisionImpact` needs a run PAIR (Batch 7 FINDING 2), and the 100-company
second pass needs to say what moved. An overwriting store makes both
impossible after the fact and — worse — makes them *look* answered, because a
single record reads exactly like a company that has never changed. So a
changed input appends a version and nothing is ever replaced.

WHY IDEMPOTENCE IS AGAINST THE LATEST, NOT THE WHOLE HISTORY
-------------------------------------------------------------
Re-assembling identical inputs must not manufacture a second record (§14). But
a company whose state returns to a value it held two versions ago has genuinely
moved twice, and deduplicating against the whole history would erase the second
move. So the check is against the latest record only: repeated assembly is
idempotent, oscillation stays visible.

THE FILE IS ONE TRANSPORT, NOT THE CONTRACT
--------------------------------------------
This store happens to use jsonl on a local disk. Nothing above it knows that:
`assemble()` never sees a path, and this module's public surface takes and
returns dossiers. Swapping it for object storage or a table changes this file
and no other (ADR, OPTION D).
"""
from __future__ import annotations

import json
import pathlib
import re
from typing import List, Optional

from intent_engine.demo_dossier.dossier import CompanyDemoDossier

STORE_DIR = "demo_dossiers"


def company_key(company_id: str) -> str:
    """Filename for a company. Mirrors `strategic_contract.company_key` in
    shape so the two artifacts for one company sort together on disk."""
    return re.sub(r"[^a-z0-9]+", "-", (company_id or "").strip().lower()
                  ).strip("-") or "unknown"


class DossierStore:
    """Append-only, versioned, one file per company."""

    def __init__(self, root=".") -> None:
        self.root = pathlib.Path(root)

    def _path(self, company_id: str) -> pathlib.Path:
        return self.root / STORE_DIR / f"{company_key(company_id)}.jsonl"

    def all_versions(self, company_id: str) -> List[CompanyDemoDossier]:
        """Every version, oldest first. A missing file is an empty history,
        not an error: a company nobody has assembled is a legitimate state."""
        path = self._path(company_id)
        if not path.exists():
            return []
        out = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                # A corrupt line is skipped rather than fatal, so one bad
                # record cannot hide a company's entire history.
                continue
            record = CompanyDemoDossier.from_dict(payload)
            if record is not None:
                out.append(record)
        return out

    def latest(self, company_id: str) -> Optional[CompanyDemoDossier]:
        versions = self.all_versions(company_id)
        return versions[-1] if versions else None

    def previous(self, company_id: str,
                 *, before: int) -> Optional[CompanyDemoDossier]:
        """The newest stored version strictly older than `before`.

        THIS METHOD DID NOT EXIST, and its absence was invisible. Its only
        caller guarded the call with `hasattr(store, "previous")`, so the
        guard answered False on every request and `previous` was always None
        -- which meant `_what_changed` took its "no earlier reading" branch
        for every company forever, including companies with a dozen stored
        versions. A page that says "this is the first reading" about the
        twelfth is not a missing feature, it is a false statement, and the
        `hasattr` is what kept it quiet.

        Ordering is by `dossier_version`, never by file position: versions are
        appended, but a comparison that trusts append order would silently
        compare the wrong pair the first time a line is rewritten or a file is
        merged. `before` is exclusive, so passing the current version returns
        the one genuinely before it rather than itself.
        """
        older = [d for d in self.all_versions(company_id)
                 if int(getattr(d, "dossier_version", 0) or 0) < int(before)]
        if not older:
            return None
        return max(older, key=lambda d: int(getattr(d, "dossier_version", 0)
                                            or 0))

    def save(self, dossier: CompanyDemoDossier) -> CompanyDemoDossier:
        """Persist, versioning on change and doing nothing on a repeat.

        Returns the stored record — which on a repeat is the EXISTING one,
        version and all, so a caller cannot mistake a no-op for a new
        observation.
        """
        previous = self.latest(dossier.company_id)
        if previous is not None and \
                previous.content_key() == dossier.content_key():
            return previous
        from dataclasses import replace
        stored = replace(dossier,
                         dossier_version=(previous.dossier_version + 1
                                          if previous else 1))
        path = self._path(dossier.company_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(stored.as_dict(), sort_keys=True) + "\n")
        return stored

    def companies(self) -> List[str]:
        """Every company with a persisted dossier. The 100-company runner's
        inventory surface."""
        directory = self.root / STORE_DIR
        if not directory.exists():
            return []
        return sorted(p.stem for p in directory.glob("*.jsonl"))
