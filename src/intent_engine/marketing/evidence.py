"""Evidence resolution (T017).

Marketing may cite the platform's authoritative artifacts — but only
within the honesty each one already carries. The rules below are the
Session-5 and Session-6 walls made load-bearing for outbound content:

    TOO FEW RESOLVED TO CLAIM CALIBRATION  cannot support a calibration claim
    NO OBSERVATION SOURCE                  cannot support an engagement claim
    UNAVAILABLE                            cannot support any positive claim
    retracted knowledge                    cannot support anything
    a narrow knowledge scope               cannot support a universal claim
    report.generated                       is generation, never engagement
"""
from __future__ import annotations

from intent_engine.marketing.records import MarketingError

EVIDENCE_TYPES = {"report", "decision", "analytics_metric", "knowledge_item",
                  "crm_fact", "feedback_record", "external_source"}

_NEGATIVE_METRIC_STATUSES = {"UNAVAILABLE",
                             "TOO FEW RESOLVED TO CLAIM CALIBRATION",
                             "NO OBSERVATION SOURCE"}


def resolve_evidence(evidence: dict, *, decision_service=None,
                     event_store=None, knowledge_service=None,
                     crm_service=None, metric_lookup=None) -> dict:
    """Return a normalized, provenance-preserving evidence snapshot, or
    raise MarketingError. The snapshot keeps status, scope, limitations,
    and version so a downstream brief cannot quietly drop them."""
    etype = evidence.get("evidence_type")
    sid = evidence.get("source_id")
    if etype not in EVIDENCE_TYPES:
        raise MarketingError(f"unknown evidence_type: {etype!r}")
    if not sid:
        raise MarketingError("evidence requires a stable source_id")

    snapshot = {"evidence_type": etype, "source_id": sid,
                "supports": evidence.get("supports", "")}

    if etype == "external_source":
        for fld in ("title", "url"):
            if not evidence.get(fld):
                raise MarketingError(
                    f"external evidence requires {fld!r} — nothing fabricated")
        snapshot.update({k: evidence[k] for k in ("title", "url")})
        if evidence.get("publisher"):
            snapshot["publisher"] = evidence["publisher"]
        if evidence.get("published_date"):
            snapshot["published_date"] = evidence["published_date"]
        return snapshot

    if etype == "report":
        if event_store is not None:
            hits = [e for e in event_store.read_all()
                    if e.event_type == "report.generated"
                    and (e.subject_id == sid or e.event_id == sid)]
            if not hits:
                raise MarketingError(f"report evidence {sid!r} not found")
            snapshot["decision_id"] = hits[-1].decision_id
            snapshot["limitations"] = (
                "report.generated records GENERATION only — it is not "
                "evidence that anyone read, shared, or acted on the report")
        return snapshot

    if etype == "decision":
        if decision_service is not None:
            if decision_service.get_decision(sid) is None:
                raise MarketingError(f"decision evidence {sid!r} not found")
            state = decision_service.get_current_state(sid)
            snapshot["decision_status"] = state.decision_status
            snapshot["limitations"] = ("decision state is owned by "
                                       "DecisionService and read as-of now")
        return snapshot

    if etype == "analytics_metric":
        if metric_lookup is None:
            raise MarketingError("analytics evidence requires a metric lookup")
        metric = metric_lookup(sid)
        if metric is None:
            raise MarketingError(f"analytics metric {sid!r} not found")
        status = (metric.get("status") if isinstance(metric, dict)
                  else getattr(metric, "status", "OK"))
        if status in _NEGATIVE_METRIC_STATUSES:
            raise MarketingError(
                f"analytics metric {sid!r} reads {status!r} — it cannot "
                "support a positive marketing claim")
        for field in ("metric_version", "computed_at", "window",
                      "annotations", "value"):
            value = (metric.get(field) if isinstance(metric, dict)
                     else getattr(metric, field, None))
            if value is not None:
                snapshot[field] = value
        snapshot["status"] = status
        return snapshot

    if etype == "knowledge_item":
        if knowledge_service is not None:
            item = knowledge_service.get_knowledge_item(sid)
            if item["status"] == "retracted":
                raise MarketingError(
                    f"knowledge item {sid!r} is retracted — it cannot "
                    "support any claim")
            snapshot.update({"knowledge_version": item["version"],
                             "scope": item["scope"],
                             "limitations": item["limitations"],
                             "citations": item["citations"],
                             "category": item["category"]})
        return snapshot

    if etype == "crm_fact":
        if crm_service is not None and not any(
                r.crm_event_id == sid for r in crm_service.store.read_all()):
            raise MarketingError(f"crm evidence {sid!r} not found")
        snapshot["limitations"] = ("CRM readiness bands are readiness, not "
                                   "purchase probability")
        return snapshot

    if etype == "feedback_record":
        if knowledge_service is not None and not any(
                r.row_id == sid for r in knowledge_service.feedback.read_all()):
            raise MarketingError(f"feedback evidence {sid!r} not found")
        snapshot["limitations"] = ("feedback is one observation; quoting it "
                                   "publicly requires exact consent")
        return snapshot

    return snapshot


def assert_scope_supports(snapshot: dict, claim_text: str) -> None:
    """A narrow knowledge scope cannot support a universal claim."""
    if snapshot.get("evidence_type") != "knowledge_item":
        return
    universal = ("every", "all customers", "any company", "universally",
                 "in all cases")
    lowered = (claim_text or "").lower()
    hits = [w for w in universal if w in lowered]
    if hits and snapshot.get("scope"):
        raise MarketingError(
            f"knowledge scope {snapshot['scope']!r} cannot support a "
            f"universal claim ({hits})")
