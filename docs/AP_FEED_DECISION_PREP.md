# AP Business feed — verification + replacement candidates — FOR YOUR ALLOWLIST DECISION

*2026-07-19/20 overnight loop 2. NO allowlist change made — the approved
allowlist (Reuters Business, AP Business, Yahoo Finance) is unchanged in
code. This is decision-prep only.*

## AP verification result

`https://apnews.com/hub/business?output=rss` — **blocked, not dead**: the
web-fetch tool returns HTTP 403 `cowork_web_fetch_url_blocked` (a
tool-side blocklist, same category as the Reuters block). Per the standing
web-content rules I did NOT route around it. So AP's feed cannot be
fetched or used through this system's tooling, exactly like Reuters —
which means **2 of the 3 approved feeds (Reuters, AP) are unusable from
the sandbox**, and only Yahoo Finance remains verified-working. The
dead-feed degradation path keeps this SAFE (unusable feeds warn and are
skipped, numeric-only fallback holds), but it leaves the allowlist thin.

## Replacement candidates (verified this session)

### Candidate 1 — NPR Business (RECOMMENDED) ✓ verified working
`https://feeds.npr.org/1006/rss.xml` — returned clean `text/xml` with
RFC-822 `pubDate`s the existing parser handles. Real sample items
(fetched this session):

    "Oil prices drop to cheapest level since early days of Middle East conflict"  (2026-06-14)
    "Paramount-Warner Brothers merger gets Justice Department approval"           (2026-06-12)
    "SpaceX IPO makes history as largest ever. Stock gains 19% on first day"      (2026-06-12)

Ran through the module's real scorer: markets items score on the regime
vocab, soft-news items score 0 — the recency+score filter behaves
correctly on this feed. Stable, free, no key.

### Candidate 2 — MarketWatch MarketPulse ✓ exists, markets-focused
`https://feeds.content.dowjones.io/public/rss/mw_marketpulse` — returned
`application/xml` 200 (Dow Jones public feed; rendered as binary in the
sandbox so I couldn't display sample items, but it's a real, markets-only
feed and the most topically on-target of the candidates). Recommend you
eyeball it in a browser before adopting, since I couldn't read its items
here.

### Candidate 3 — CNBC (NOT recommended)
`https://www.cnbc.com/id/10001147/device/rss/rss.html` — returned an
empty body from the sandbox; same failure class as the LTCM speech.
Skip unless it verifies on your machine.

## Secondary finding worth your attention (separate from the feed decision)

The regime vocabulary is narrow enough to MISS some clearly-markets
headlines: in the NPR sample, "SpaceX **IPO** ... **Stock** gains 19%" and
"Paramount-Warner **merger**" both scored 0, because the vocab has
"stocks" (plural) but not "stock"/"ipo"/"merger". This isn't an AP-feed
issue — it's a `REGIME_VOCAB` coverage question in
`core/headline_feed.py`. I did NOT touch the vocab (it's shared,
tested surface). Flagging it as a candidate follow-up: adding
{ipo, merger, acquisition, stock, buyback, guidance} would catch these.
Your call whether that's worth a small tuning task.

## Your decision (nothing changes until you pick)

1. **Replace AP with NPR Business** (recommended — verified working) —
   one-line allowlist edit in `core/headline_feed.py` + its test's
   allowlist assertion, on your say-so.
2. Add MarketWatch too (after you eyeball it) for markets-specific depth.
3. Leave the allowlist as-is (Yahoo-only effective) and accept thinner
   sourcing.
4. Optionally: a separate small task to widen `REGIME_VOCAB` per the
   secondary finding.

No allowlist or vocab change will be made without your explicit pick.
