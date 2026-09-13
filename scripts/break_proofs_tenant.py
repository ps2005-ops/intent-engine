"""Break proofs for the tenant boundary.

Proof 1 is the one to read. It gives `from_evidence` a working body — the
thirty-second helper somebody writes when the obvious line ("the evidence says
which company, use that") lands on a missing function instead of a refusal.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from break_proof_harness import Proof, ROOT, run_all  # noqa: E402

M = ROOT / "src/intent_engine/market"
T = "tests"
TI = f"{T}/test_market_tenant_isolation.py"
IB = f"{T}/test_market_information_barrier.py"

PROOFS = [
    ("1. a company identity may be read out of a document",
     M / "tenant_scope.py",
     "    raise UntrustedScope(\n"
     '        "a company identity read out of evidence is chosen by whoever '
     'wrote "',
     "    return TenantScope(company_id=str(args[0] if args else\n"
     "                       kwargs.get('company_id', '')),\n"
     "                       authority=CONFIGURED)\n"
     "    raise UntrustedScope(\n"
     '        "a company identity read out of evidence is chosen by whoever '
     'wrote "',
     f"{TI}::test_a_company_name_from_evidence_cannot_open_records"),

    ("2. a bare string reaches the permitted-facts path again",
     M / "tenant_scope.py",
     "    if not isinstance(scope, TenantScope):\n"
     "        raise UntrustedScope(",
     "    if False:\n"
     "        raise UntrustedScope(",
     f"{TI}::test_a_bare_string_cannot_reach_the_permitted_facts_path"),

    ("3. an unnamed authority is accepted",
     M / "tenant_scope.py",
     "        if self.authority not in AUTHORITIES:\n"
     "            raise ScopeRejected(",
     "        if False:\n"
     "            raise ScopeRejected(",
     f"{TI}::test_an_unnamed_authority_is_refused"),

    ("4. an empty scope reads every company",
     M / "tenant_scope.py",
     "        if not str(self.company_id).strip():\n"
     "            raise ScopeRejected(",
     "        if False:\n"
     "            raise ScopeRejected(",
     f"{TI}::test_an_empty_scope_would_read_everything_and_is_refused"),

    ("5. a join may cross companies",
     M / "tenant_scope.py",
     "    if strangers:\n        raise ScopeRejected(",
     "    if False:\n        raise ScopeRejected(",
     f"{TI}::test_a_join_that_crosses_companies_is_refused"),

    ("6. the join guard goes blind to persisted rows",
     M / "tenant_scope.py",
     '        str(getattr(r, field, "") or (r.get(field) if isinstance(r, dict)\n'
     '                                      else ""))',
     '        str(getattr(r, field, ""))',
     f"{TI}::test_the_join_guard_reads_dicts_as_well_as_objects"),

    ("7. the demonstration company becomes a configured tenant",
     M / "tenant_scope.py",
     "    return TenantScope(company_id=company_id, authority=DEMONSTRATION)",
     "    return TenantScope(company_id=company_id, authority=CONFIGURED)",
     f"{TI}::test_the_demonstration_authority_is_distinct_from_a_configured_tenant"),

    ("8. the permission filter stops filtering",
     M / "internal_state.py",
     "    return tuple(f for f in facts if f.company_id == for_company)",
     "    return tuple(facts)",
     f"{TI}::test_the_canary_is_unreachable_for_another_tenant"),

    ("9. an unnamed reader is served everything",
     M / "internal_state.py",
     "    if not for_company:\n        raise PermissionRefused(",
     "    if False:\n        raise PermissionRefused(",
     f"{IB}::test_an_unnamed_reader_is_refused_rather_than_served_everything"),

    ("10. a fact may be stored with no owner",
     M / "internal_state.py",
     "        if not self.company_id:\n"
     "            raise InternalRejected(",
     "        if False:\n"
     "            raise InternalRejected(",
     f"{TI}::test_a_fact_without_an_owner_is_refused_rather_than_shared"),

    ("11. synthetic data joins a real conclusion",
     M / "internal_state.py",
     "    if bad:\n        raise SyntheticLeak(",
     "    if False:\n        raise SyntheticLeak(",
     f"{TI}::test_synthetic_facts_never_join_a_real_companys_conclusion"),
]


if __name__ == "__main__":
    sys.exit(run_all(
        [Proof(*p) for p in PROOFS],
        title=(f"tenant — the boundary a document may not cross: "
               f"{len(PROOFS)} proofs")))
