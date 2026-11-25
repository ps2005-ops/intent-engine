"""Is Founder CURRENT, or has it merely not changed?

THE DISTINCTION THIS EXISTS FOR
--------------------------------
An old file on disk proves nothing. Before this module the Market -> export ->
Founder seam could not mechanically separate:

    Founder is current because the latest relevant Market state was consumed

from:

    Founder simply has not been touched.

Both look identical from outside — an export that exists and a revision record
that exists — and only the first is a working product.

SEMANTIC DIGEST, NOT FILE TIME
-------------------------------
Freshness is decided by `semantic_digest`, computed over the MEANING fields of
an export and deliberately excluding `generated_at` and the `freshness` block.
A cycle that re-derives identical intelligence produces a byte-different file
(new timestamp) and the SAME digest, so it correctly yields EXPORT_NOT_NEEDED
rather than a new Founder revision. Keying on mtime would append an empty
revision every night and make "the founder received new intelligence" a
statement about the clock.

WHAT THE TRANSPORT ACTUALLY IS
-------------------------------
`dossier_transport` posts over HTTP when `DOSSIER_TRANSPORT_URL` is set, and
otherwise the handoff is the shared filesystem: Market writes
`reports/market/strategic/<company>.json` and the Founder side reads it. Both
are supported here and the state says which one is in play, because
"transport not configured" and "transport failed" are different facts.
"""
from __future__ import annotations

import collections
import datetime
import hashlib
import json
import pathlib
from typing import Dict, List, Optional

from . import system_of_record as SOR

CONTRACT = "founder_freshness.v1"

# --- states (closed, §5) ------------------------------------------------------
MARKET_NOT_RUN = "MARKET_NOT_RUN"
MARKET_NO_CHANGE = "MARKET_NO_CHANGE"
EXPORT_NOT_CHECKED = "EXPORT_NOT_CHECKED"
EXPORT_NOT_NEEDED = "EXPORT_NOT_NEEDED"
EXPORT_CREATED = "EXPORT_CREATED"
EXPORT_FAILED = "EXPORT_FAILED"
TRANSPORT_NOT_CONFIGURED = "TRANSPORT_NOT_CONFIGURED"
TRANSPORT_STALE = "TRANSPORT_STALE"
TRANSPORT_FAILED = "TRANSPORT_FAILED"
RECEIVED = "RECEIVED"
VALIDATION_FAILED = "VALIDATION_FAILED"
VALIDATED = "VALIDATED"
NOT_CONSUMED = "NOT_CONSUMED"
USED = "USED"
RENDERED = "RENDERED"
DOSSIER_REFRESHED = "DOSSIER_REFRESHED"
CURRENT_NO_NEW_REVISION_REQUIRED = "CURRENT_NO_NEW_REVISION_REQUIRED"
STALE_MARKET_INTELLIGENCE = "STALE_MARKET_INTELLIGENCE"
MARKET_UNAVAILABLE = "MARKET_UNAVAILABLE"

STATES = (MARKET_NOT_RUN, MARKET_NO_CHANGE, EXPORT_NOT_CHECKED,
          EXPORT_NOT_NEEDED, EXPORT_CREATED, EXPORT_FAILED,
          TRANSPORT_NOT_CONFIGURED, TRANSPORT_STALE, TRANSPORT_FAILED,
          RECEIVED, VALIDATION_FAILED, VALIDATED, NOT_CONSUMED, USED,
          RENDERED, DOSSIER_REFRESHED, CURRENT_NO_NEW_REVISION_REQUIRED,
          STALE_MARKET_INTELLIGENCE, MARKET_UNAVAILABLE)

#: The only two states that mean "the product is showing current thinking".
CURRENT_STATES = frozenset({DOSSIER_REFRESHED,
                            CURRENT_NO_NEW_REVISION_REQUIRED})

#: Fields excluded from the semantic digest. They change every run without the
#: intelligence changing, and including them would make every night a
#: "material change".
_NON_SEMANTIC = frozenset({"generated_at", "freshness", "as_of",
                           "export_version", "disclaimer"})

EXPORT_DIR = "reports/market/strategic"
CONSUMPTION_LEDGER = "reports/market/dossier_revisions.jsonl"


def semantic_digest(payload: dict) -> str:
    """A digest of what the export MEANS, not of the file it arrived in."""
    meaningful = {k: v for k, v in sorted(payload.items())
                  if k not in _NON_SEMANTIC}
    blob = json.dumps(meaningful, sort_keys=True, default=str)
    return "sem_" + hashlib.blake2b(blob.encode(), digest_size=8).hexdigest()


def _read_exports(root) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    directory = pathlib.Path(root) / EXPORT_DIR
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        company = str(payload.get("company_id") or path.stem)
        out[company] = {
            "company_id": company,
            "path": str(path),
            "as_of": str(payload.get("as_of") or ""),
            "generated_at": str(payload.get("generated_at") or ""),
            "semantic_digest": semantic_digest(payload),
        }
    return out


def _read_consumption(root) -> Dict[str, dict]:
    """Latest Founder-side revision per company, from the canonical ledger."""
    path = pathlib.Path(root) / CONSUMPTION_LEDGER
    latest: Dict[str, dict] = {}
    if not path.exists():
        return latest
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            company = str(row.get("company_id") or "")
            if not company:
                continue
            when = str(row.get("recorded_at") or "")
            if company not in latest or when >= str(
                    latest[company].get("recorded_at") or ""):
                latest[company] = row
    return latest


def _company_state(export: Optional[dict], consumed: Optional[dict],
                   transport_configured: bool) -> dict:
    """One company's position in the lifecycle. Missing is never CURRENT."""
    if export is None:
        # Nothing was exported for this company. That is NOT the same as an
        # export that was correctly skipped — nobody checked.
        return {"state": EXPORT_NOT_CHECKED,
                "reason": ("no strategic export exists for this company; "
                           "absence of a file is not a decision not to "
                           "publish one")}
    if consumed is None:
        return {"state": NOT_CONSUMED,
                "reason": ("an export exists and no Founder revision "
                           "references it; received is not consumed")}

    consumed_digest = str(consumed.get("semantic_digest") or "")
    if not consumed_digest:
        # The Founder ledger predates digest recording. It cannot be compared,
        # and guessing CURRENT here is exactly the false all-clear this module
        # exists to prevent.
        return {"state": STALE_MARKET_INTELLIGENCE,
                "reason": ("the Founder revision records no semantic digest, "
                           "so it cannot be shown to correspond to the "
                           "current export"),
                "consumed_at": str(consumed.get("recorded_at") or "")}

    if consumed_digest == export["semantic_digest"]:
        return {"state": CURRENT_NO_NEW_REVISION_REQUIRED,
                "reason": ("the current export is semantically identical to "
                           "the one Founder consumed; no new revision is "
                           "required and none was appended"),
                "consumed_at": str(consumed.get("recorded_at") or "")}

    return {"state": (TRANSPORT_STALE if transport_configured
                      else STALE_MARKET_INTELLIGENCE),
            "reason": ("the current export differs semantically from the one "
                       "Founder last consumed"),
            "consumed_at": str(consumed.get("recorded_at") or ""),
            "consumed_digest": consumed_digest,
            "current_digest": export["semantic_digest"]}


def assess(root=None, *, transport_configured: Optional[bool] = None) -> dict:
    """Market -> Founder freshness, per company and in aggregate."""
    base = pathlib.Path(root) if root else pathlib.Path(
        SOR.canonical().get("scheduler", {}).get("runtime_root", "."))
    if transport_configured is None:
        try:
            from . import dossier_transport as DT
            transport_configured = bool(DT.configured())
        except Exception:                          # noqa: BLE001
            transport_configured = False

    exports = _read_exports(base)
    consumed = _read_consumption(base)

    companies = sorted(set(exports) | set(consumed))
    per_company = {}
    for company in companies:
        per_company[company] = _company_state(
            exports.get(company), consumed.get(company), transport_configured)

    tally = collections.Counter(v["state"] for v in per_company.values())
    current = sum(tally[s] for s in CURRENT_STATES)

    newest_export = max((e["generated_at"] for e in exports.values()),
                        default="")
    newest_consumption = max((str(c.get("recorded_at") or "")
                              for c in consumed.values()), default="")

    return {
        "contract": CONTRACT,
        "state": "MEASURED",
        "transport": (("HTTP" if transport_configured else
                       TRANSPORT_NOT_CONFIGURED)),
        "transport_note": (
            "" if transport_configured else
            "DOSSIER_TRANSPORT_URL is unset, so the handoff is the shared "
            "filesystem under reports/market/strategic; this is a "
            "configuration fact, not a failure"),
        "exports": len(exports),
        "companies_with_consumption": len(consumed),
        "companies": len(companies),
        "current": current,
        # Both populations are COMPANIES, so this is a true share.
        "current_share": (round(current / len(companies), 4)
                          if companies else None),
        "by_state": dict(sorted(tally.items())),
        "market_last_export_at": newest_export,
        "founder_last_consumed_at": newest_consumption,
        "per_company": per_company,
    }


def render(report: dict) -> str:
    out = ["=" * 72,
           "MARKET -> FOUNDER FRESHNESS",
           "=" * 72,
           f"  transport   {report['transport']}",
           f"  exports     {report['exports']}   "
           f"consumption records {report['companies_with_consumption']}",
           f"  current     {report['current']} of {report['companies']}"
           + (f"  ({report['current_share']:.0%})"
              if report["current_share"] is not None else ""),
           f"  last export {report['market_last_export_at']}",
           f"  last consumed {report['founder_last_consumed_at']}",
           "",
           "BY STATE"]
    for state, count in report["by_state"].items():
        out.append(f"  {state:<38}{count}")
    if report["transport_note"]:
        out += ["", f"  note: {report['transport_note']}"]
    out.append("=" * 72)
    return "\n".join(out)
