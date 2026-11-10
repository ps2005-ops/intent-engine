"""Adaptive strategic intelligence: one engine, a different reading per company.

WHAT THIS LAYER IS FOR
----------------------
The product could already analyse a company. What it could not do was explain
why THIS company should care about the analysis rather than a company like it.
The measured cause is structural, not editorial:

    every differentiating table in the product -- the pattern library, the
    per-class metrics, the macro transmission channels, the causal questions,
    the competitor set -- is keyed on `business_model_class`, and
    `company_profile.profile_for` can only produce one from a curated
    100-company manifest or from an SEC industry code.

A private company is in neither, so it resolves to UNKNOWN, and UNKNOWN
switches every one of those tables off at once. Measured on the ten companies
this phase qualifies against: 10 of 10 came back `PROFILE_SPARSE`,
`business_model_class=UNKNOWN`.

So the differentiation was never suppressed by the writing. It was never
reachable.

THE FOUR PRODUCERS
------------------
`classify`      what kind of business this is, read from the company's OWN
                published evidence when no manifest row and no industry code
                exists. A third classifier beside the two that already exist,
                with the same rule: it may not guess.

`profile`       `CompanyStrategicProfile` -- the canonical company object.
                Composed from the classification, the analyst's evidence-cited
                reconstruction, and the subject's own documents.

`opportunity`   `DecisionOpportunity` -- where better intelligence could
                change a decision here, ranked with its components exposed.

`lens`          which strategic lens this company's evidence selects, which
                it does not, and why. Routed on evidence and exposure rather
                than on industry.

WHAT IT MAY NOT DO
------------------
No company-specific output is hard-coded anywhere in this package. Every
company-facing sentence is composed from that company's own evidence or from
the structural economics of the class its own evidence selected, and a claim
that can be made about an unrelated company unchanged is a defect this package
detects (`differentiation.genericity`) rather than a result it ships.
"""
from intent_engine.adaptive.classify import (        # noqa: F401
    EvidenceClassification, classify_from_evidence,
)
from intent_engine.adaptive.composer import (        # noqa: F401
    MODULES, ComposedReport, compose_report,
)
from intent_engine.adaptive.differentiation import (  # noqa: F401
    Differentiation, build_differentiation, genericity,
)
from intent_engine.adaptive.causal import (          # noqa: F401
    CausalChain, CausalLink, build_causal_chain,
)
from intent_engine.adaptive.lens import (            # noqa: F401
    LENS_LIBRARY, LensSelection, select_lens,
)
from intent_engine.adaptive.opportunity import (     # noqa: F401
    DecisionOpportunity, DecisionOpportunityMap, build_opportunity_map,
)
from intent_engine.adaptive.profile import (         # noqa: F401
    CompanyStrategicProfile, build_profile,
)
from intent_engine.adaptive.roles import (           # noqa: F401
    ROLES, RoleLens, RoleView, role_view,
)

CONTRACT = "adaptive_strategic_intelligence.v1"
