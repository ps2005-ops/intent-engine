# V1.1 — Source policy

## Approved source types (first version)

Homepage; product/solutions; pricing; about; customers/case studies;
blog/newsroom; careers; user-pasted evidence (labelled and authorized).
Uploads deferred (gap). External domains only by explicit individual
approval (currently via pasted evidence; per-URL flow is a gap).

## Bounded discovery (deterministic; no model chooses URLs)

1 entered homepage; ≤20 same-domain links from that homepage; ≤10
known-path candidates (`/`, /product(s), /solutions, /pricing, /about,
/customers, /case-studies, /blog, /news, /careers — proposed, never
assumed to exist); ≤20 candidates shown; ≤10 approved fetched per run.
No recursion. Ranking is a fixed order: homepage, product, pricing,
about, customers, blog, careers.

## Approval

Nothing is fetched before approval. The user sees URL, type, discovery
method, same-domain flag, and why it may be useful; confirms "I approve
retrieval and analysis of the selected public pages." The exact
approved and rejected sets persist immutably with a consent version.
Rejected candidates are never fetched (tested).

## Access honesty

401/403/429/anti-bot/unsupported content → UNAVAILABLE. Failed
retrieval is never treated as evidence of real-world absence ("No
supported review source was retrieved", never "the company has no
reviews"). No evasion of access controls, ever.

## Evidence labels

Company website · External public evidence (explicitly approved) ·
User-provided evidence ("Founder-provided evidence" / "User-provided
public excerpt" / internal) · Unavailable or failed. Pasted text is
never treated as independently verified public truth.

## Disclosure (shown at intake and source review)

Founder Intelligence analyzes only the pages and evidence you approve.
Public websites can be incomplete. The report does not represent
internal company knowledge. A retrieved page may be outdated. The
system does not automatically contact, publish to, or modify any
website. Synthetic demo runs keep their banner permanently; real runs
carry the real-analysis scope note instead.
