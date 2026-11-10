"""Break proofs for the private graph boundary and its first consumer.

Batch 1 added ZERO break proofs, which is how a suite of 140 green tests told
us nothing about whether any of them were load-bearing. These eleven mutations
each remove one specific protection and assert that a named test goes red for
the stated reason.

Proofs G through K are the ones to read. They do not attack the security
boundary at all -- they attack the DISTINCTION BETWEEN MISSING AND ZERO, by
making an unseeable internal world report itself as a measured absence of
impact. That substitution is invisible in every surface, survives review, and
tells a founder their exposure is nil when what the system means is that it
cannot see their business. It is the same defect class this program removed
from the trust metric and from the belief engine, arriving in a third module.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

M = ROOT / "src/intent_engine/business_graph/model.py"
I = ROOT / "src/intent_engine/business_graph/internal.py"
C = ROOT / "src/intent_engine/external_intel/internal_impact.py"

GT = "tests/test_business_graph_internal.py"
CT = "tests/test_internal_impact.py"

PROOFS = [
    # -- the tenant boundary ------------------------------------------------
    ("A. a scopeless reader is shown private nodes",
     M,
     "    if scope is None:\n"
     "        return WITHHELD",
     "    if scope is None:\n"
     "        return SHOWN",
     f"{GT}::test_a_scopeless_query_returns_public_only_and_never_a_private_node"),

    ("B. a private thing with no typed identity is treated as public",
     M,
     "    if not isinstance(tenant, TenantId):\n"
     "        return REFUSED",
     "    if not isinstance(tenant, TenantId):\n"
     "        return SHOWN",
     f"{GT}::test_a_thing_that_declares_privacy_without_an_identity_is_refused"),

    ("C. every scoped reader sees every tenant",
     M,
     "    return SHOWN if scope.authorizes(tenant) else WITHHELD",
     "    return SHOWN",
     f"{GT}::test_negative_control_tenant_b_cannot_read_a_node_tenant_a_wrote"),

    ("D. a bare string becomes authority",
     M,
     '    if isinstance(scope, (str, bytes)):\n'
     '        raise ScopeRefused(\n'
     '            STRING_REFUSED,',
     '    if False:\n'
     '        raise ScopeRefused(\n'
     '            STRING_REFUSED,',
     f"{GT}::test_read_scope_separates_none_from_a_bad_scope"),

    # -- persistence and export ---------------------------------------------
    ("E. an altered persisted row is read rather than refused",
     I,
     '    if _binding(row, unbound=unbound) != row["tenant_binding"]:',
     '    if False:',
     f"{GT}::test_negative_control_a_manually_altered_persisted_row_is_refused"),

    ("F. an export serializes every tenant's private rows",
     I,
     "    read = graph.read(scope=scope)\n"
     "    nodes, edges = [], []\n"
     "    for node in read.nodes:",
     "    read = graph.read(scope=scope)\n"
     "    nodes, edges = [], []\n"
     "    for node in graph._all_nodes():",
     f"{GT}::test_negative_control_an_export_cannot_serialize_another_tenants_node"),

    # -- MISSING versus ZERO, in the consumer -------------------------------
    ("G. an unseeable internal world falls through to a measured negative",
     C,
     "    if not private:\n"
     "        if scope is None:",
     "    if False:\n"
     "        if scope is None:",
     f"{CT}::test_an_empty_private_world_is_unavailable_and_never_a_negative"),

    ("H. 'no impact' is read off emptiness instead of off the state",
     C,
     "        return self.state == NO_INTERNAL_IMPACT",
     "        return not self.metrics",
     f"{CT}::test_an_empty_private_world_is_unavailable_and_never_a_negative"),

    ("I. the subject bridge becomes a substring match",
     C,
     '    return isinstance(declared, str) and declared != "" and declared == subject_id',
     '    return isinstance(declared, str) and declared != "" and subject_id in declared',
     f"{CT}::test_a_substring_of_the_declared_subject_does_not_match"),

    ("J. an untagged fixture row is reported as real enterprise data",
     C,
     "    return value if value in POPULATIONS else SYNTHETIC_ENTERPRISE",
     "    return value if value in POPULATIONS else REAL_ENTERPRISE",
     f"{CT}::test_an_untagged_row_is_treated_as_synthetic_not_as_real"),

    ("K. a data request is raised against an already-measured negative",
     C,
     "    if impact.state not in NOT_A_NEGATIVE:\n"
     "        return None",
     "    if False:\n"
     "        return None",
     f"{CT}::test_no_request_is_generated_for_a_measured_negative"),
]


if __name__ == "__main__":
    sys.exit(run_all(
        [Proof(*p) for p in PROOFS],
        title="D-IBG-001 -- the private graph boundary and its first consumer"))
