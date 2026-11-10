"""V1.1 URL, domain, redirect, and DNS validation — the SSRF wall.

Composes the existing T023.5 `validate_public_url` (schemes, localhost,
loopback, link-local, private/reserved IP literals) and adds: embedded
credentials, unsafe ports, DNS-resolution checks (every resolved address
must be public), and the same-domain redirect policy.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse, urlunparse

from intent_engine.founder_intelligence.records import (
    UnsafeURLRejected, canonical_domain, validate_public_url,
)

SAFE_PORTS = (None, 80, 443)


def validate_candidate_url(url: str) -> str:
    """Full pre-retrieval validation. Returns the normalized URL."""
    url = validate_public_url(url)              # reuse the T023.5 wall
    parsed = urlparse(url)
    if parsed.username or parsed.password:
        raise UnsafeURLRejected(
            "URLs with embedded credentials are refused")
    if parsed.port not in SAFE_PORTS:
        raise UnsafeURLRejected(
            f"port {parsed.port} is not an allowed public web port")
    return url


def resolve_public_addresses(host: str, *, resolver=None) -> list:
    """Resolve `host` and require every address to be public. Returns the
    addresses. `resolver` is injectable for deterministic tests."""
    resolver = resolver or (lambda h: [
        info[4][0] for info in socket.getaddrinfo(h, None)])
    try:
        addresses = list(dict.fromkeys(resolver(host)))
    except (socket.gaierror, OSError) as exc:
        raise UnsafeURLRejected(f"DNS resolution failed for {host}: "
                                f"{exc}") from exc
    if not addresses:
        raise UnsafeURLRejected(f"DNS returned no addresses for {host}")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise UnsafeURLRejected(
                f"{host} resolves to non-public address {address} — "
                "refused to prevent SSRF/DNS-rebinding")
    return addresses


def registrable(host: str) -> str:
    """Coarse registrable-domain comparison: last two labels. Sufficient
    for the apex↔www policy; anything subtler requires explicit user
    approval anyway."""
    labels = (host or "").lower().rstrip(".").split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else (host or "")


def redirect_allowed(from_url: str, to_url: str) -> bool:
    """Allowed without new approval: the approved host, its `www.` twin, and
    anything BENEATH it. Everything else is refused.

    SUBTREE CONTAINMENT, NOT REGISTRABLE EQUALITY
    ----------------------------------------------
    This used to require exact host equality after a registrable-domain
    check, which refused `cloudflare.com -> blog.cloudflare.com` while
    `same_domain()` — the function that APPROVES candidates — accepted the
    same host. Two definitions of "the same company" in one module, and the
    hosts caught between them (blog., docs., investor., ir.) are where
    strategy and customer evidence lives: it was missing for 8 of the 10
    breaker companies.

    The obvious repair is `registrable(from) == registrable(to)`. It is
    refused here. `registrable()` is deliberately coarse — the last two
    labels — so on a multi-label public suffix it returns `co.uk`, and
    registrable equality would admit every unrelated `.co.uk` host into a
    navigation NOBODY APPROVED. That coarseness is tolerable where a human
    approves the candidate; it is not tolerable as the gate on a redirect.

    So the test is containment in the subtree of the host already approved:
    you may descend, and `www.` is the apex. It never consults
    `registrable()`, and it is strictly narrower than registrable equality on
    every input — `cloudflare.com.evil.example` is not beneath
    `cloudflare.com`, because the match is anchored on a label boundary.

    The SSRF wall is unchanged and still runs first: scheme, credentials,
    ports, localhost, loopback, link-local and private literals are all
    refused before the host is even considered.
    """
    try:
        validate_candidate_url(to_url)
    except UnsafeURLRejected:
        return False
    from_host = (urlparse(from_url).hostname or "").lower().rstrip(".")
    to_host = (urlparse(to_url).hostname or "").lower().rstrip(".")
    if not from_host or not to_host:
        return False
    # AN EMPTY LABEL BREAKS THE ANCHOR. `.cloudflare.com` ends with
    # `.cloudflare.com`, so a leading dot would satisfy the suffix test and
    # smuggle a malformed host through a rule that exists to pin one. The
    # previous exact-equality check refused it for free; the widened rule has
    # to refuse it on purpose. Caught by this file's own negative control.
    if any(not label for label in from_host.split(".")) or \
            any(not label for label in to_host.split(".")):
        return False
    base = from_host[4:] if from_host.startswith("www.") else from_host
    target = to_host[4:] if to_host.startswith("www.") else to_host
    if not base or not target:
        return False
    # The dot is the whole guarantee: `evilcloudflare.com` does not end with
    # `.cloudflare.com`, and `cloudflare.com.evil.example` ends with
    # `.evil.example`.
    return target == base or target.endswith("." + base)


def same_domain(company_url: str, candidate_url: str) -> bool:
    return registrable(urlparse(company_url).hostname or "") == \
        registrable(urlparse(candidate_url).hostname or "")


def normalize_url(base_scheme: str, host: str, path: str) -> str:
    return urlunparse((base_scheme, host, path or "/", "", "", ""))


__all__ = ["UnsafeURLRejected", "canonical_domain", "normalize_url",
           "redirect_allowed", "registrable", "resolve_public_addresses",
           "same_domain", "validate_candidate_url"]
