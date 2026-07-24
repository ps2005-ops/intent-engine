# V1.1 — Dependency gaps (honest register)

Format: capability · owning subsystem · closest existing contract ·
missing contract · honest degradation · smallest future implementation ·
blocks controlled real-company testing? · blocks public launch?

| Capability | Owner | Closest existing | Missing | Degrades honestly? | Smallest future impl | Blocks testing? | Blocks launch? |
|---|---|---|---|---|---|---|---|
| Third-party review sources (G2 etc.) | company_ingestion | user-pasted excerpts (labelled) | approved review-platform integration | YES — "no supported review source was retrieved" | per-platform approved fetch adapter | NO | NO |
| Search-engine discovery | company_ingestion | homepage-link + known-path discovery | none | YES — bounded same-domain discovery only | approved search API integration | NO | NO |
| Competitor intelligence | founder_intelligence | OUT_OF_SCOPE state + user-approved competitor URLs (future) | competitor comparison composer | YES — "no competitor evidence was approved" | user-supplied competitor URL approval + comparison view | NO | NO |
| JavaScript-rendered pages | company_ingestion | static HTML parsing | JS execution (deliberately excluded) | YES — page parses to little text; recorded as thin source | headless-browser fetch behind explicit approval | NO | NO |
| PDF/document upload parsing | company_ingestion | pasted text | safe document parser | YES — uploads refused, pasted text offered | bounded PDF-to-text with type checks | NO | NO |
| External URL fetch approval UI | webapp | pasted evidence in approval form | per-URL external candidate approval flow | YES — external evidence enters via paste | add external-URL field + individual approval + same fetch wall | NO | NO |
| Live in-sandbox retrieval | environment | recorded-real transport | unrestricted egress (sandbox policy) | YES — recorded real pages; documented | run acceptance on a host with ordinary egress | PARTIAL (live re-run pending) | NO |
| Auth-protected sources | company_ingestion | 401/403 recorded unavailable | none (deliberate) | YES — "unavailable", never evaded | out of scope by policy | NO | NO |
| Changed-sources comparison (refresh diff) | company_ingestion | content hashes + immutable snapshots | run-to-run diff view | YES — "Analyzed as of" shown; diff deferred | compare stored hashes across runs | NO | NO |
| Minimum corpus size for term claims | company_ingestion | stopword-curated term frequency | corpus-size threshold before language claims | YES — weak claims still cite their tiny corpus | suppress term claims under N words | NO | NO |
| Robots.txt parsing | company_ingestion | technical-failure honesty (401/403/429/anti-bot recorded unavailable, no evasion) | robots.txt pre-check | YES | fetch+parse robots.txt before retrieval | NO | NO — but do before large-scale public use |

Nothing here blocks controlled real-company testing on a normal host.
Nothing silently invents a substitute.
