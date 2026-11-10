# Evidence acquisition — architecture, measured

Written 2026-09-03 during the PRE-STRATEGIC-100 hardening pass. Every number
here was measured locally against the production call sites, not estimated.

## 1. The flow, as it actually runs

```
company (name or domain or CIK)
  └─ identity resolution ......... entities.py, name_entry.py, registry
  └─ DISCOVERY ................... discovery.py (known paths + homepage links)
                                   sitemap.py (publisher-attested URLs)
                                   edgar.py (subject's own filings, by CIK)
                                   third_party_filings.py (EDGAR full-text:
                                        filings by OTHER registrants naming
                                        the subject — the independent family)
                                   external_discovery.py (review-site templates)
                                   snapshot.py (a warm run REUSES the source
                                        list instead of rediscovering it)
  └─ SELECTION ................... webapp.app._recommended_candidate_ids
                                   14 slots (MAX_APPROVED_SOURCES), allocated
                                   round-robin across evidence families with
                                   quotas {product 5, customers 2, investor 2}
  └─ SCHEDULING .................. service._prefetch: 6 workers global,
                                   per-host semaphore, dead-host breaker at 2
                                   host-level failures, Deadline bounds both
                                   discovery and retrieval
  └─ RETRIEVAL ................... fetch.safe_fetch (SSRF wall, manual redirect
                                   revalidation, size/MIME/redirect caps)
                                   transient.call_with_retry (429/5xx only,
                                   per-host AND per-run second budgets)
                                   httppool (keep-alive connections)
                                   filing_cache (EDGAR bodies, keyed on
                                   CIK/accession/document — immutable by
                                   construction)
                                   acquisition_memory (NEW — see §3)
  └─ PARSING ..................... filing_text.parse_filing_html for filings,
                                   parsing.parse_html for web pages, pdf.py
  └─ ACCEPTANCE .................. records.retrieved_record + credential guard
  └─ JUDGEMENT ................... coverage.family_of  → which ROLE a document
                                        fills
                                   readiness.assess_readiness → may a report
                                        exist (5 states)
                                   sufficiency.evaluate → may CORE stop
                                        BLOCKING (same contract, consulted
                                        twice, deliberately)
                                   quality.evidence_gaps + retry.plan_retry →
                                        up to 2 bounded rediscovery passes
  └─ report │ bounded abstention
```

## 2. What the baseline actually was

20 companies from the frozen `QUALIFY_50`, concurrency 1, production call
sites, no model:

| | |
|---|---|
| READY_FOR_FULL_REPORT | 19/20 |
| approved slots | 266 |
| documents retrieved | 189 |
| **slot yield** | **71%** |
| failures | 148 (48× 404, 62× 403) |

Slot success by how the URL was found:

| discovery method | succeeded |
|---|---|
| `third_party_filing` | **41/41 (100%)** |
| `entered` | 7/8 (88%) |
| `homepage_link` | 26/33 (79%) |
| `external_proposed` | 50/66 (76%) |
| `known_path` (guessed) | **33/80 (41%)** |

**The slot is the scarce resource, not the request.** A run gets 14. One clean
Johnson & Johnson run spent NINE of them on `/api`, `/docs`, `/developers`,
`/plans`, `/business`, `/case-studies`, `/documentation` — SaaS-shaped path
guesses against a pharmaceutical company, every one a 404 — and every future
run bought the same nine answers again.

## 3. What was added

**`acquisition_memory.py`** — the third cache. `FilingCache` remembers
CONTENT; `SnapshotStore` remembers WHERE TO LOOK; nothing remembered WHAT
HAPPENED LAST TIME WE ASKED.

- Per-URL verdicts for outcomes that are a property of the ADDRESS: `gone`
  (404/410, 14d), `refused` (401/403/451, 3d), and URL-decided failures
  (`blocked`, `unsafe_redirect`, `parse_error`, 14d).
- **`too_large` and `bad_mime` are deliberately NOT remembered**: both depend
  on arguments the CALL SITE chooses (`max_bytes`, `accept_truncated`,
  `extra_mime_prefixes`). The first cold run recorded thirteen SEC filings as
  permanently too large, including Netflix's own 10-K, and would have refused
  to request it for a fortnight.
- A host circuit (CLOSED/HALF_OPEN/OPEN) armed **only by silence and
  throttling** — timeouts, connection failures, 429 and 5xx. **A 403 never
  arms it**: seven 403s opened `oracle.com` in an early version and collapsed
  Oracle's evidence from five families to two. `service._HOST_LEVEL_FAILURES`
  had always been `("connection", "timeout")` for exactly this reason.
- Exactly one probe crosses a HALF_OPEN circuit; a success clears the history.
- A success FORGETS a stale failure, so a fixed page stops being skipped.
- Per-host minimum request spacing (SEC: 0.12s) so a cohort stops arriving as
  a burst.
- The key is a public URL and nothing else — no run, tenant, or company.

**Three definitions of "evidence family" were found, and they disagreed.**

| where | test | a 10-K reads as |
|---|---|---|
| `coverage.family_of` (readiness) | form | `identity` |
| `quality.evidence_gaps` (retry planner) | venue/`source_type` | identity MISSING |
| `webapp._EVIDENCE_FAMILIES` (selection) | venue/`source_type` | `investor` |

Consequences, measured: AMD's site timed out, the run fell back entirely to
EDGAR, `family_of` correctly read the 10-K as `identity` — and the retry
planner still spent its four-source budget guessing `/about` and `/products`
against the host that had just stopped answering, to fill a role the run
already held.

Repairs:
- `evidence_gaps` now reports **role**-missing (what readiness requires) for
  the retry planner, while the **stopping condition stays on the strict venue
  test** — so the run never makes FEWER acquisition passes than before.
- `retry.FAMILY_TARGETS["independent"]` was **unreachable**: `evidence_gaps`
  can only emit identity/product/customers/strategy/investor, so the only
  matcher able to select an attested third-party filing could never run. The
  matcher is now reachable from the `customers` role.
- `identity` and `product` can now be filled by the subject's own annual
  report (10-K/20-F/40-F). This adds no source and lowers no bar —
  `family_of` already read a 10-K as identity; it simply became selectable
  when the website is the thing that is broken.

**A pre-existing run-killer, exposed.** The credential detector is enforced
twice: `_build_record` raises `SecretRejected` (guarded) and
`records.validate()` raises `IngestionError` at append time (not guarded). An
NVIDIA run died outright — "raw credentials / auth headers must never be
persisted" — because SEC filings concatenate commission file numbers into
card-number shapes. It now costs one source, which is what the existing
guard's own comment always said it must.

## 4. Observability added

`retrieval_telemetry(run_id)` now returns, beside retry and filing-cache
counters: `acquisition_memory` (skips, open hosts), `sources` (discovered /
requested / retrieved / yield, by cause, by host), `evidence_roles`
(required / filled / missing) and `abstention` (one classified reason).

`abstention.py` replaces one generic "insufficient evidence" with a taxonomy —
`EXTERNAL_RATE_LIMIT`, `EXTERNAL_ACCESS_REFUSED`, `EXTERNAL_TIMEOUT`,
`BUDGET_EXCEEDED`, `DISCOVERY_INSUFFICIENT`, `SOURCE_DIVERSITY_INSUFFICIENT`,
`PRIMARY_EVIDENCE_MISSING`, `REASONING_FAILURE`, `MODEL_REFUSAL`,
`INTERNAL_FAILURE`, `CAPACITY_EXCEEDED`, `IDENTITY_UNRESOLVED`. Precedence is
the design: an external cause is only the reason when it actually removed
evidence — a run holding nine documents did not abstain because two sources
were rate limited. This is the machine-side label; the reader still gets prose
naming the hosts.

## 5. A harness defect that invalidated a whole measurement

`scripts/acquisition_probe.py` wrote every run into one shared store
directory. `create_run` is idempotent on (domain, user, as_of), so the second
probe of a company on the same day **rejoined the first run's event log**.
Oracle read `{investor: 5, independent: 4}` / RETRYABLE_EVIDENCE_GAP under the
shared directory and `{identity: 2, independent: 4, investor: 1, strategy: 1,
talent: 1}` / READY_FOR_FULL_REPORT with a fresh one — same code, same
company, minutes apart. Every measurement taken through it was void, including
a confident conclusion that the network had degraded mid-session. The probe
now uses one fresh store per run.

The lesson is the one this project keeps relearning: **an instrument that
names producer state wrongly invents uniform defects**, and the first thing to
suspect when a defect is suspiciously uniform is the instrument.
