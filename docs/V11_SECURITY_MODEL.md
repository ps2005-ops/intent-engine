# V1.1 — Security model

## SSRF wall (validation.py, reused T023.5 wall + additions)

Rejected before any connection: non-HTTP(S) schemes (file, ftp, gopher,
data, javascript); localhost/loopback (v4+v6); private IPv4/IPv6;
link-local; multicast; reserved; unspecified; embedded credentials;
non-80/443 ports; malformed/dotless hosts. DNS resolution is checked
where available: every resolved address must be public (guards DNS
rebinding to private space); resolution failure is a loud rejection.

## Redirects

Never auto-followed. Each hop is re-validated: SSRF wall + policy.
Allowed without new approval: same host, apex↔www of the same
registrable domain, http→https. Refused: unrelated domains, IP
literals, >5 hops. Refusals are recorded failures, not silent skips.

## Retrieval

No cookies; no auth headers; no JS execution; descriptive User-Agent
(`FounderIntelligenceBot/1.1`); 8s connect / 12s read timeouts; 2MB per
source; 15MB per run; MIME allowlist (html/xhtml/plain/markdown); body
decode errors are failures, not text. 401/403/429/anti-bot are recorded
UNAVAILABLE — no evasion, no identity rotation, no CAPTCHA bypass.

## Persistence

Append-only stores; no raw Authorization/Set-Cookie/api-key material
may be persisted (validated at the record layer); pasted evidence is
secret-scanned (reuses T023.5 `assert_no_secret`); retrieved text is
secret-scanned on its first 20k chars.

## Isolation (extends V1.0.1)

A user sees only their own runs/candidates/sources (ownership checked
on every route); approval must come from the run's owner; a source
belongs to exactly one run/company; conversation uses only the current
run's ClaimSet; share views expose only the report subset — never raw
fetched HTML, pasted text, or session metadata. Real runs cannot
consume synthetic (`demo_fixture`) SourceRefs — hard failure, tested.

## Output

All user- and source-derived text is HTML-escaped at render
(`html.escape` throughout webapp); no fetched HTML is ever re-served.
