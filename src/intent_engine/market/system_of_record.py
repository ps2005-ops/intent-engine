"""Which pipeline IS the market intelligence system — read from the declaration.

WHY THIS IS CODE AND NOT A README
----------------------------------
On 2026-08-12 an exploration answering "what has the market intelligence
system learned this week?" read `data/prediction_ledger.db`, last written
twenty-three days earlier, and reported that the learning system had learned
nothing and its modules were dormant. The canonical ledger held 4,921 rows at
that moment and the canonical cycle had completed that morning.

Nothing was broken. The wrong store was read. A document saying which store is
correct would not have prevented it, because the exploration never read a
document — it read files. So the classification lives here, is loaded from
`docs/execution/MARKET_INTELLIGENCE_SYSTEM_OF_RECORD.yaml`, and is asserted
against by tests and by the legacy scripts themselves.

THE ONE RULE
------------
A pipeline may describe itself as the market intelligence system only if this
module says it is CANONICAL. `assert_canonical()` and `legacy_banner()` are the
two ways that rule is enforced, and a break proof drives both.
"""
from __future__ import annotations

import pathlib
from typing import Dict, List, Optional

CONTRACT = "market_intelligence_system_of_record.v1"

#: Resolved from THIS file, never from the working directory: an operator
#: running the command from their home directory must get the same answer as
#: launchd running it from the runtime root.
DECLARATION_PATH = (pathlib.Path(__file__).resolve().parents[3] / "docs"
                    / "execution"
                    / "MARKET_INTELLIGENCE_SYSTEM_OF_RECORD.yaml")

CANONICAL = "CANONICAL"
LEGACY = "LEGACY"
UNDECLARED = "UNDECLARED"

#: Printed by every legacy entrypoint, at the top of its output. Deliberately
#: unmissable and deliberately naming the replacement — a warning that does not
#: say where to go instead just gets ignored.
LEGACY_BANNER = (
    "=" * 72 + "\n"
    "LEGACY / AUXILIARY — NOT THE MARKET INTELLIGENCE SYSTEM OF RECORD\n"
    "This pipeline is retained for its July 2026 prediction history only.\n"
    "It does not represent current market learning and is not scheduled.\n"
    "\n"
    "  The system of record is:  python -m intent_engine.market\n"
    "  What has it learned:      python -m intent_engine.market "
    "learning-status --window 7d\n"
    + "=" * 72
)


class SystemOfRecordError(RuntimeError):
    """Raised when a pipeline claims an authority the declaration denies."""


def _load() -> dict:
    import yaml
    if not DECLARATION_PATH.exists():
        raise SystemOfRecordError(
            f"the system-of-record declaration is missing at "
            f"{DECLARATION_PATH}. Refusing to guess which pipeline is "
            f"canonical — guessing is the defect this file exists to "
            f"prevent.")
    return yaml.safe_load(DECLARATION_PATH.read_text(encoding="utf-8")) or {}


def declaration() -> dict:
    return _load()


def canonical() -> dict:
    return _load().get("system_of_record") or {}


def canonical_id() -> str:
    return str(canonical().get("id") or "")


def stores(root=None) -> Dict[str, pathlib.Path]:
    """Canonical store paths, resolved against a runtime root.

    Every consumer must resolve stores through here. A reader that hardcodes
    its own path is how two components end up disagreeing about what the
    system knows.
    """
    base = pathlib.Path(root) if root else pathlib.Path(
        canonical().get("scheduler", {}).get("runtime_root", "."))
    return {name: base / rel
            for name, rel in (canonical().get("stores") or {}).items()}


def legacy_pipelines() -> List[dict]:
    return list(_load().get("legacy_pipelines") or [])


def classify(pipeline_id: str) -> str:
    """CANONICAL, LEGACY, or UNDECLARED — never a guess."""
    if pipeline_id and pipeline_id == canonical_id():
        return CANONICAL
    for entry in legacy_pipelines():
        if entry.get("id") == pipeline_id:
            return str(entry.get("status") or LEGACY)
    return UNDECLARED


def is_canonical(pipeline_id: str) -> bool:
    return classify(pipeline_id) == CANONICAL


def assert_canonical(pipeline_id: str) -> None:
    """Refuse to let a non-canonical pipeline speak for the system.

    UNDECLARED fails too, and that is the point: a new script nobody
    classified is exactly the shape of the thing that caused the incident, so
    the default is refusal rather than silent acceptance.
    """
    verdict = classify(pipeline_id)
    if verdict != CANONICAL:
        raise SystemOfRecordError(
            f"{pipeline_id!r} is {verdict}, not the market intelligence "
            f"system of record ({canonical_id()!r}). See "
            f"{DECLARATION_PATH.name}.")


def legacy_banner(pipeline_id: str) -> Optional[str]:
    """The banner a legacy entrypoint must print, or None if it is canonical."""
    return None if is_canonical(pipeline_id) else LEGACY_BANNER
