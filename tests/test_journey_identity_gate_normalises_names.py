"""The qualification harness's PROFILE_CONSISTENCY gate (scripts/public_journey_ten.py)
compares one identity on its tokens (prospect-98 untouched: Tonic.ai failed on
punctuation alone)."""
import importlib.util
import os
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pjt():
    os.environ.setdefault("JOURNEY_BASE", "http://127.0.0.1:1")
    spec = importlib.util.spec_from_file_location("pjt", ROOT / "scripts/public_journey_ten.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # the harness imports its own siblings
        pytest.skip(f"harness not importable here: {exc}")
    return mod


@pytest.mark.parametrize("names,head", [
    (("Tonic.ai", "Tonic AI, Inc."), "Tonic AI, Inc."),
    (("C3 AI", "C3.ai, Inc."), "C3.ai, Inc."),
    (("Veeam", "Veeam Software Group GmbH"), "Limited analysis of Veeam Software Group GmbH"),
    (("cfo.ai", "Runway Financial, Inc.", "Runway Financial"), "Runway Financial, Inc."),
])
def test_one_company_in_different_spellings(pjt, names, head):
    assert pjt.names_same_company(names, head)


@pytest.mark.parametrize("names,head", [
    (("Coupa", "Coupa Software Inc"), "Coupang, Inc."),
    (("Zip", "Zip"), "ZipRecruiter, Inc."),
    (("SAFE", "Safe Security, Inc."), "Safehold Inc."),
])
def test_a_prefix_namesake_is_still_a_different_company(pjt, names, head):
    assert not pjt.names_same_company(names, head)
