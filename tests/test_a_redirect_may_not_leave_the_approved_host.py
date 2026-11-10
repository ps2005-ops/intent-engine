"""BW10-004: the redirect policy, widened to subdomains without widening SSRF.

THE DEFECT. Candidate approval (`same_domain`) accepts any host under the same
registrable domain, so `blog.cloudflare.com` and `docs.stripe.com` are
approvable sources. `redirect_allowed` then refused a redirect to those same
hosts, because after checking the registrable domain it required exact host
equality. Two functions in one module disagreed about what "the same company"
means, and the hosts caught in between — blog., docs., investor., ir. — are
where strategy and customer evidence lives. Strategy evidence was missing for
8 of 10 breaker companies.

THE INVARIANT CHOSEN, AND WHY NOT THE OBVIOUS ONE.
The obvious repair is `registrable(from) == registrable(to)`. It is wrong
here. `registrable()` is documented as coarse — the last two labels — so for a
company on `example.co.uk` it returns `co.uk`, and registrable equality would
admit every unrelated `.co.uk` host into an AUTOMATIC, un-approved navigation.
The coarse function is tolerable where a human approves the candidate; it is
not tolerable as the gate on a redirect nobody reviewed.

So the rule is SUBTREE CONTAINMENT: a redirect may not leave the subtree of
the host already approved, with `www.` treated as the apex. You may descend
(`cloudflare.com` → `blog.cloudflare.com`), you may not move sideways or up.
It never consults `registrable()`, so the public-suffix weakness cannot reach
it, and it is strictly narrower than registrable equality on every input.
"""
from __future__ import annotations

import pytest

from intent_engine.company_ingestion.validation import (redirect_allowed,
                                                        same_domain)

APEX = "https://cloudflare.com/a"
WWW = "https://www.cloudflare.com/a"


# --- what the defect blocked, and the fix must allow ----------------------

@pytest.mark.parametrize("target", [
    "https://blog.cloudflare.com/x",
    "https://docs.stripe.com/x".replace("stripe", "cloudflare"),
    "https://investor.cloudflare.com/x",
    "https://ir.cloudflare.com/x",
    "https://www.cloudflare.com/x",
    "https://cloudflare.com/other",
])
def test_a_redirect_may_descend_into_the_companys_own_subdomains(target):
    assert redirect_allowed(APEX, target) is True


def test_www_is_equivalent_to_the_apex_in_both_directions():
    assert redirect_allowed(WWW, "https://blog.cloudflare.com/x") is True
    assert redirect_allowed(WWW, "https://cloudflare.com/x") is True
    assert redirect_allowed(APEX, "https://www.cloudflare.com/x") is True


def test_approval_and_redirect_now_agree_about_the_same_company():
    """The two sides of the original inconsistency, asserted together."""
    for target in ("https://blog.cloudflare.com/x",
                   "https://docs.cloudflare.com/x"):
        assert same_domain(APEX, target) is True
        assert redirect_allowed(APEX, target) is True


# --- the negative controls (§4) -------------------------------------------

@pytest.mark.parametrize("target", [
    # deceptive suffixes: the approved host appears, but not as the parent
    "https://cloudflare.com.evil.example/x",
    "https://evilcloudflare.com/x",
    "https://cloudflare.com.attacker.test/x",
    "https://notcloudflare.com/x",
    # userinfo trick: authority is evil.example, not cloudflare.com
    "https://cloudflare.com@evil.example/x",
    # unrelated
    "https://evil.example/x",
    "https://example.org/x",
])
def test_a_redirect_may_not_leave_the_approved_host(target):
    assert redirect_allowed(APEX, target) is False


@pytest.mark.parametrize("target", [
    "http://localhost/x",
    "http://127.0.0.1/x",
    "http://[::1]/x",
    "http://10.0.0.5/x",
    "http://192.168.1.1/x",
    "http://172.16.0.1/x",
    "http://169.254.169.254/latest/meta-data/",
    "http://169.254.169.254/x",
    "http://0.0.0.0/x",
])
def test_the_ssrf_wall_still_refuses_every_internal_target(target):
    assert redirect_allowed(APEX, target) is False


@pytest.mark.parametrize("target", [
    "file:///etc/passwd",
    "gopher://cloudflare.com/x",
    "ftp://cloudflare.com/x",
    "data:text/html,x",
    "javascript:alert(1)",
])
def test_a_non_http_scheme_is_refused_even_on_the_right_host(target):
    assert redirect_allowed(APEX, target) is False


@pytest.mark.parametrize("target", [
    "https://blog.cloudflare.com:8080/x",
    "https://blog.cloudflare.com:22/x",
    "https://cloudflare.com:3306/x",
])
def test_an_unusual_port_is_refused_even_on_a_legitimate_subdomain(target):
    """The port wall must not be bypassed by the widened host rule."""
    assert redirect_allowed(APEX, target) is False


@pytest.mark.parametrize("target", [
    "https://user:pass@blog.cloudflare.com/x",
])
def test_embedded_credentials_are_refused_on_a_legitimate_subdomain(target):
    assert redirect_allowed(APEX, target) is False


def test_a_sibling_subdomain_may_not_be_reached_from_a_deeper_host():
    """Containment is directional. From `blog.` you may descend, not move
    across to `docs.` — the approved navigation was into blog, not into the
    whole company."""
    frm = "https://blog.cloudflare.com/a"
    assert redirect_allowed(frm, "https://cdn.blog.cloudflare.com/x") is True
    assert redirect_allowed(frm, "https://docs.cloudflare.com/x") is False
    assert redirect_allowed(frm, "https://cloudflare.com/x") is False


def test_the_coarse_registrable_helper_cannot_widen_this_decision():
    """THE REASON THE OBVIOUS FIX WAS REJECTED.

    `registrable()` returns the last two labels, so two unrelated companies
    on a multi-label public suffix share one 'registrable domain'. Under
    registrable equality this redirect would be permitted; under subtree
    containment it is not.
    """
    from intent_engine.company_ingestion.validation import registrable
    assert registrable("example.co.uk") == registrable("victim.co.uk")
    assert redirect_allowed("https://example.co.uk/a",
                            "https://victim.co.uk/x") is False


@pytest.mark.parametrize("target", [
    "https://.cloudflare.com/x",
    "https:///x",
    "https://cloudflare..com/x",
    "not-a-url",
    "",
])
def test_a_malformed_target_is_refused_rather_than_guessed(target):
    assert redirect_allowed(APEX, target) is False


def test_an_idn_homograph_host_is_not_treated_as_the_company():
    """Cyrillic 'а' in 'clоudflare' is a different host entirely."""
    assert redirect_allowed(APEX, "https://blog.cloаudflare.com/x") \
        is False


def test_a_redirect_from_an_unrelated_host_does_not_gain_the_company():
    assert redirect_allowed("https://evil.example/a",
                            "https://blog.cloudflare.com/x") is False
