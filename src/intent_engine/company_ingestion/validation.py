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
    """Allowed without new approval: same host, apex↔www of the same
    registrable domain, and http→https upgrades. Everything else —
    unrelated domains, IP literals, scheme downgrades to non-HTTP —
    is refused."""
    try:
        validate_candidate_url(to_url)
    except UnsafeURLRejected:
        return False
    f, t = urlparse(from_url), urlparse(to_url)
    from_host = (f.hostname or "").lower()
    to_host = (t.hostname or "").lower()
    if registrable(from_host) != registrable(to_host):
        return False
    stripped_from = from_host[4:] if from_host.startswith("www.") else from_host
    stripped_to = to_host[4:] if to_host.startswith("www.") else to_host
    return stripped_from == stripped_to


def same_domain(company_url: str, candidate_url: str) -> bool:
    return registrable(urlparse(company_url).hostname or "") == \
        registrable(urlparse(candidate_url).hostname or "")


def normalize_url(base_scheme: str, host: str, path: str) -> str:
    return urlunparse((base_scheme, host, path or "/", "", "", ""))


__all__ = ["UnsafeURLRejected", "canonical_domain", "normalize_url",
           "redirect_allowed", "registrable", "resolve_public_addresses",
           "same_domain", "validate_candidate_url"]
