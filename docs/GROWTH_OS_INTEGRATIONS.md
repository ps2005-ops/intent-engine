# Growth OS — External Integrations (honest status)

**Rule (§15):** before any real adapter is implemented we (1) verify a supported
current API/SDK exists, (2) document auth type, (3) permissions, (4) rate limits,
(5) whether posting *and* analytics are supported, (6) terms/restrictions, (7)
implement an **injected fake first**, (8) never place credentials in code, tests,
or logs. **No real adapter has been implemented yet — every provider below is
fake-only.** Capability claims marked *verify* must be confirmed against the
vendor's current docs at implementation time; this file is a map, not a promise.

Legend — **Support:** OFFICIAL_API / THIRD_PARTY / MANUAL_ONLY / UNVERIFIED ·
**Status here:** FAKE_ONLY (interface + injected fake), NOT_STARTED.

| Provider | Category | Auth | Post | Analytics | Support | Status | Notes / account-owner action |
|---|---|---|---|---|---|---|---|
| **Publer** | multi-platform publish | API key (plan-gated) *verify* | yes *verify* | partial *verify* | THIRD_PARTY | FAKE_ONLY | Preferred multi-channel connector. Verify current API scope + which channels it can post to on your plan. Create API key in Publer, place in env (not code). |
| **Higgsfield** | AI video/media | *verify* | n/a | n/a | UNVERIFIED | FAKE_ONLY | **Do not assume a public generation API exists.** Until a supported API is confirmed, media runs as `ACCOUNT_OWNER_MANUAL`: the system emits the full storyboard/prompts/shot-list/captions and you produce it in Higgsfield's own tool. A real adapter slots behind `MediaProvider` once confirmed. |
| **X (Twitter)** | social | OAuth 2.0 | yes | limited (paid tiers) | OFFICIAL_API | FAKE_ONLY | API v2 has paid tiers; posting + limited metrics. Strict rate limits. Confirm tier + cost before enabling. |
| **LinkedIn** | social | OAuth 2.0, **partner-gated** | approved apps only | limited | OFFICIAL_API (gated) | FAKE_ONLY | Share/Marketing APIs require approved app + specific scopes; personal auto-posting is restricted. Likely `REVIEW_REQUIRED`/manual for some actions. |
| **Reddit** | social/community | OAuth 2.0 | yes | limited | OFFICIAL_API | FAKE_ONLY | Official API, per-app rate limits; respect subreddit rules + self-promotion norms. |
| **Instagram / Meta** | social | OAuth (Graph API) | Business/Creator accts | yes (insights) | OFFICIAL_API (review) | FAKE_ONLY | Graph API via a linked Facebook Page + Business IG account; app review required. |
| **TikTok** | social/video | OAuth (Content Posting API) | business/dev, review | partial | OFFICIAL_API (review) | FAKE_ONLY | Content Posting API needs developer/business approval; audited scopes. |
| **YouTube** | video | OAuth 2.0 (Data API v3) | upload yes | yes | OFFICIAL_API | FAKE_ONLY | Upload quota-limited; analytics via YouTube Analytics API. |
| **Google Search Console** | SEO | OAuth 2.0 | n/a (read) | yes (Search Analytics) | OFFICIAL_API | FAKE_ONLY | Read-only search performance; used by SEO Intelligence. |
| **Google Analytics (GA4)** | web analytics | OAuth / service acct | n/a (read) | yes (Data API) | OFFICIAL_API | FAKE_ONLY | Read-only; feeds attribution + Content Intelligence. |
| **Hacker News** | community | none (read) | manual | read-only | OFFICIAL_API (read) | FAKE_ONLY | Firebase API is read-only; submissions are manual. |
| **GitHub** | dev | token / App | releases/issues | yes (traffic) | OFFICIAL_API | FAKE_ONLY | Post release notes/updates; repo traffic as a signal. |
| **Product Hunt** | launch | OAuth | limited | limited | OFFICIAL_API *verify* | FAKE_ONLY | Launch assets largely manual; verify current API scope. |
| **Email provider** | email | API key | send | opens/clicks | THIRD_PARTY | FAKE_ONLY | Behind an `EmailProvider` interface (e.g. Postmark/SES/SendGrid/Listmonk) — pick one at config; never bind logic to one vendor. Must support suppression + unsubscribe. |
| **CRM provider** | CRM | internal / API | n/a | n/a | REUSE | REUSE | Reuse `intent_engine.crm`; an external CRM (e.g. HubSpot) would sit behind a `CRMProvider` adapter, fake first. |

## Per-provider realistic path (implement fake → verify → real adapter)

1. **Publer (publishing hub) — priority.** Fake connector first (already the pattern in the Publishing framework). Verify: does your Publer plan expose the API, and which channels can it *post* to vs *draft* only? Then implement `PublerConnector(PublishConnector)` reading `PUBLER_API_KEY` from env.
2. **Higgsfield (media).** Keep `ManualExportProvider` as default. Only add `HiggsfieldProvider(MediaProvider)` after confirming a supported programmatic endpoint; otherwise the export package is the deliverable.
3. **Search Console + GA4 (measurement).** Highest-value, read-only, lowest-risk. OAuth read scopes; feed SEO + attribution.
4. **Reddit / HN / GitHub (technical audience).** Read for Trend Intelligence first; posting stays `REVIEW_REQUIRED`.
5. **X / LinkedIn / Instagram / TikTok / YouTube.** Publish behind Publer where possible; direct official adapters only where worthwhile and access is granted.

## Credentials & safety (account-owner)

- Every secret lives in an **environment variable**, never in code, tests, logs, or commits. The repo's existing secret-redaction discipline applies.
- **`PUBLISHING_ENABLED` defaults to false.** No channel auto-posts until you explicitly enable it, per channel.
- For each connector you enable, the final report will give the exact steps: which credential to create, scopes/permissions, callback URL, a test publish, a test delete (where supported), an analytics confirmation, the kill switch, and rotation. **Secret values are never requested in chat.**
