"""Research & Evidence Intelligence Platform (T019).

An agent here is a CONSTRAINED PRODUCER OF REVIEWABLE ARTIFACTS, not a
thing that answers questions. This package produces evidence packages the
founder can audit, disagree with, and act on.

    Request -> Plan -> Session -> Evidence Index -> Package -> Conclusion

The Evidence Index (`index.py`) is the research-memory backbone that
later agents read instead of rebuilding. It is never written by a model.

Load-bearing properties:
    a model may never emit a source, URL, citation, author, or date
    collection cannot begin before a HUMAN-approved research plan
    source quality never depends on whether the source agrees
    three outlets quoting one wire report are ONE independent source
    contradictions are the product, not a problem to smooth away
    NOT INVESTIGATED (never searched) differs from UNKNOWN (searched, found
        nothing) — and both differ from INSUFFICIENT
    quality outranks recency; freshness labels, it never promotes
    "we could not answer this" is a pre-authorized successful outcome
    the agent drafts; it never approves, validates, or promotes

Canonical research contract: `records.py`.
"""
from intent_engine.research.records import (  # noqa: F401
    EVIDENCE_CLASSES, SOURCE_CLASSES, STANCES, UNCERTAINTY_LABELS,
    ResearchError, ResearchEvent, scan_banned_language,
)
from intent_engine.research.state import (  # noqa: F401
    ResearchState, fold_research,
)
from intent_engine.research.sources import (  # noqa: F401
    canonicalize_locator, count_independent, freshness_of, grade_source,
    independence_group, outranks,
)
from intent_engine.research.index import (  # noqa: F401
    EvidenceIndex, build_index, claim_key, normalize_claim,
)
from intent_engine.research.extraction import (  # noqa: F401
    ExtractionRejected, extract_candidates, validate_candidate,
)
from intent_engine.research.graph import (  # noqa: F401
    rank_evidence, stance_for_claim,
)
from intent_engine.research.packages import (  # noqa: F401
    assemble_package, coverage_report, draft_conclusion, render_narrative,
    research_debt,
)
from intent_engine.research.service import (  # noqa: F401
    ResearchService, fingerprint_request,
)
from intent_engine.research.snapshots import (  # noqa: F401
    capture_graph_snapshot, capture_package_snapshot,
)
from intent_engine.research.consumer import (  # noqa: F401
    ResearchCompanyEventConsumer,
)
