"""Break proofs for the Founder tenancy seam and the synthetic world.

Batch 2's lesson, restated: A-WIRE-001 rendered 25 causal refusals and
persisted none of them, every test was green, and only the live run found it.
The equivalent failure here would be a request path that establishes a scope,
renders an internal-impact panel, and leaks — or, more likely, one that reports
"no internal impact" when it means "I could not see your business".

So the mutations below fall into three families:

  A-D  AUTHORITY. Make something other than the authenticated session able to
       establish a scope, or make an anonymous visitor into a tenant.
  E-H  ISOLATION. Break the partition, the load-time authorization, or the
       filename that keeps a directory listing from enumerating tenants.
  I-L  HONESTY. Make a synthetic row look real, or make an unseeable business
       look like an unaffected one. These are the ones that survive review,
       because nothing about the page looks wrong.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

TEN = ROOT / "src/intent_engine/webapp/tenancy.py"
STORE = ROOT / "src/intent_engine/business_graph/private_store.py"
SYN = ROOT / "src/intent_engine/business_graph/synthetic_enterprise.py"
VIEW = ROOT / "src/intent_engine/webapp/internal_view.py"
IMPACT = ROOT / "src/intent_engine/external_intel/internal_impact.py"

WT = "tests/test_webapp_internal_impact.py"
ST = "tests/test_synthetic_enterprise.py"

PROOFS = [
    # -- AUTHORITY ----------------------------------------------------------
    ("A. an anonymous visitor becomes a tenant",
     TEN,
     "    if is_anonymous(session):\n        return None",
     "    if False:\n        return None",
     f"{WT}::test_an_anonymous_visitor_is_told_unavailable_not_no_impact"),

    ("B. a company id is accepted as authority",
     TEN,
     "    if company_id:\n        raise ScopeRefused(",
     "    if False:\n        raise ScopeRefused(",
     f"{WT}::test_establish_from_request_refuses_a_company_as_authority"),

    ("C. the demo prefix stops being recognised",
     TEN,
     '    return any(subject.startswith(p) for p in ANONYMOUS_PREFIXES)',
     '    return False',
     f"{WT}::test_an_anonymous_visitor_is_told_unavailable_not_no_impact"),

    ("D. the tenant directory stops being stable across requests",
     TEN,
     "        existing = self.lookup(subject)\n"
     "        if existing is not None:\n"
     "            return existing",
     "        existing = None\n"
     "        if existing is not None:\n"
     "            return existing",
     f"{WT}::test_beta_sees_its_own_business_not_alphas"),

    # -- ISOLATION ----------------------------------------------------------
    ("E. every tenant shares one partition file",
     STORE,
     "        digest = hashlib.sha256(\n"
     "            scope_cache_key(got).encode(\"utf-8\")).hexdigest()\n"
     "        return self.root / f\"{digest}.jsonl\"",
     "        return self.root / \"all.jsonl\"",
     f"{ST}::test_a_tenants_partition_contains_only_its_own_rows"),

    ("F. a foreign row can be written into a tenant's partition",
     STORE,
     "                if not scope.authorizes(item.tenant):",
     "                if False:",
     f"{ST}::test_a_row_owned_by_another_tenant_cannot_be_written_into_a_"
     "partition"),

    ("G. the partition filename enumerates tenants again",
     STORE,
     "        digest = hashlib.sha256(\n"
     "            scope_cache_key(got).encode(\"utf-8\")).hexdigest()",
     "        digest = scope_cache_key(got)",
     f"{ST}::test_two_tenants_get_two_partitions_and_neither_name_leaks_an_id"),

    ("H. a tampered row is loaded instead of refused",
     STORE,
     "            except (PrivateGraphRefused, ScopeRefused) as exc:",
     "            except (KeyboardInterrupt,) as exc:",
     f"{ST}::test_reload_refuses_rows_whose_binding_was_altered"),

    # -- HONESTY ------------------------------------------------------------
    ("I. a synthetic row is minted as real enterprise data",
     SYN,
     "    out = {POPULATION_KEY: SYNTHETIC_ENTERPRISE,",
     "    out = {POPULATION_KEY: \"REAL_ENTERPRISE\",",
     f"{ST}::test_every_node_carries_the_synthetic_population"),

    ("J. the surface stops declaring that the answer is synthetic",
     VIEW,
     "    if not impact.is_real_data_claim():",
     "    if False:",
     f"{WT}::test_the_answer_declares_that_it_rests_on_synthetic_rows"),

    ("K. an unseeable business is reported as an unaffected one",
     IMPACT,
     "    if not private:\n"
     "        if scope is None:",
     "    if False:\n"
     "        if scope is None:",
     f"{WT}::test_an_anonymous_visitor_is_told_unavailable_not_no_impact"),

    ("L. a data request is raised even though the data are sufficient",
     IMPACT,
     "    if impact.state not in NOT_A_NEGATIVE:\n        return None",
     "    if False:\n        return None",
     f"{WT}::test_sufficient_data_asks_for_nothing"),

    # -- the receipt --------------------------------------------------------
    ("M. refused requests stop being recorded",
     VIEW,
     "            receipt=receipt_for(\n"
     "                request_id=request_id, scope=None, company_id=subject_id,\n"
     "                operation=OPERATION, denial_reason=impact.reason,\n"
     "                runtime_sha=runtime_sha, occurred_at=when))",
     "            receipt=receipt_for(\n"
     "                request_id=request_id, scope=None, company_id=subject_id,\n"
     "                operation=OPERATION, denial_reason=\"\",\n"
     "                runtime_sha=runtime_sha, occurred_at=when))",
     f"{WT}::test_every_request_writes_a_receipt_including_the_refused_ones"),
]


if __name__ == "__main__":
    sys.exit(run_all(
        [Proof(*p) for p in PROOFS],
        title="D-SYN-001 / D-IBG-001 / F-TS-001 -- the Founder tenancy seam"))
