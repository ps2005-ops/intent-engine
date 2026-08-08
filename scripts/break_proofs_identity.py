"""Break proofs for the self-description identity detector.

The five mutations below each re-create a failure that has actually shipped or
was actively risked by this change, and demand that a test notices.

Restore bumps mtime: a same-length restore leaves CPython running cached
bytecode whose size and hash still match, and the proof reports a false pass.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = "/Users/prathamsharma/intent-engine/.venv/bin/python"
IDENTITY = ROOT / "src/intent_engine/founder_brief/identity.py"
TESTS = "tests/test_founder_identity_detector.py"

PROOFS = [
    ("11. a Stripe customer story becomes Stripe's self-description",
     "    if _REJECT_PATH.search(path) or _REJECT_TITLE.search(title or \"\"):",
     "    if False:",
     "test_customer_story_is_never_the_focal_company_description"),

    ("12. Brightledger's valid product description is rejected",
     "    if identity_page and owns_subject:",
     "    if False:",
     "test_brightledger_product_sentence_is_recovered"),

    ("13. first-party host alone proves identity",
     "    if identity_page and owns_subject:",
     "    if first_party:",
     "test_first_party_host_alone_never_proves_self_description"),

    ("14. third-party integration docs become the company description",
     "r\"/(customers?|case[-_]stud(y|ies)|success[-_]stor(y|ies)|stories|\"\n"
     "    r\"partners?|integrations?|marketplace|directory|\"",
     "r\"/(customers?|case[-_]stud(y|ies)|success[-_]stor(y|ies)|stories|\"\n"
     "    r\"directory|\"",
     "test_third_party_and_boilerplate_page_classes_are_rejected"),

    ("15. a pricing page becomes the primary company description",
     "    if pricing_only:",
     "    if False:",
     "test_pricing_page_is_not_a_company_description"),

    ("16. a customer story feeds the owned vocabulary",
     "        if _REJECT_PATH.search(path):\n            continue",
     "        if False:\n            continue",
     "test_a_customer_story_never_enters_the_owned_vocabulary"),

    # The property here is the ORDER, not either check on its own. Mutating
    # the first-person test alone proves nothing, because the rejection above
    # it already catches the case — which is exactly the design. So the
    # mutation lifts the positive signal above the rejection, and that is what
    # a customer's "we cut our costs" would need in order to leak.
    ("17. a positive signal is read before the page class is rejected",
     "    if _REJECT_PATH.search(path) or _REJECT_TITLE.search(title or \"\"):",
     "    if _FIRST_PERSON.search(low):\n"
     "        return Identity(CONFIRMED, \"first person\", (\"first_person\",))\n"
     "    if _REJECT_PATH.search(path) or _REJECT_TITLE.search(title or \"\"):",
     "test_we_inside_a_customer_story_is_the_customers_voice"),
]


def run_test(name: str) -> bool:
    proc = subprocess.run(
        [PY, "-m", "pytest", f"{TESTS}::{name}", "-q", "--no-header"],
        cwd=ROOT, capture_output=True, text=True,
        env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"})
    return proc.returncode == 0


def main() -> int:
    failures = []
    for label, find, replace, test in PROOFS:
        original = IDENTITY.read_text(encoding="utf-8")
        if find not in original:
            print(f"  SKIP  {label}\n        anchor not found")
            failures.append(label)
            continue
        if not run_test(test):
            print(f"  FAIL  {label}\n        {test} was already red")
            failures.append(label)
            continue

        IDENTITY.write_text(original.replace(find, replace, 1),
                            encoding="utf-8")
        try:
            caught = not run_test(test)
        finally:
            IDENTITY.write_text(original, encoding="utf-8")
            now = time.time() + 1
            os.utime(IDENTITY, (now, now))

        if not run_test(test):
            print(f"  FAIL  {label}\n        did not go green after restore")
            failures.append(label)
        elif caught:
            print(f"  ok    {label}")
        else:
            print(f"  FAIL  {label}\n        mutation NOT caught by {test}")
            failures.append(label)

    print()
    print(f"{len(PROOFS) - len(failures)}/{len(PROOFS)} break proofs held")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
