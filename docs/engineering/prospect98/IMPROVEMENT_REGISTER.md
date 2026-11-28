# Prospect-98: shared intelligence improvement register

Every entry is a change to a SHARED mechanism (no company-specific conclusion is
hard-coded anywhere). Each lists the measurement that found it, the change, the
regression test, and the break proof (the test was run against the reverted
code and failed). Trees are immutable `git archive` exports under
`~/ie-p98-trees/`, named by the git tree SHA they were exported from.

| # | Mechanism | Measured defect | Change | Test | Break proof |
|---|---|---|---|---|---|
| 1 | Identity registry (`company_ingestion/catalog_prospects98.py`) | Baseline: 83/98 companies invisible to search; Coupa → Coupang, Zip → ZipRecruiter, SAFE → Safehold, Runway → Runway Growth Finance | 98 verified identities (domains fetched by the product's own fetcher, SEC IDs from sec.gov, ownership changes cited), 85 attested official-source sets. Former filers carry no CIK (Domo's former CIK files as the shell Huckleberry.ai) | `test_company_catalog_identity.py` (1195 parametrised) | n/a (data) |
| 2 | Search: EXACT match (`suggest._match`) | "Click" ranked Click Holdings EXACT above ClickHouse; "Star" → Star Holdings over StarTree: `_words` drops "holdings"/"group" before the EXACT test | EXACT now means the whole name less its LEGAL form (`identity_key`, the merge's own rule); a descriptor-only equality is a whole-word LEADING match | suggest suite (2706 focused) | prospect-100 search 100/100 before and after |
| 3 | Search: typed website and typos | 87/98 domain queries and 92/98 one-edit typos returned nothing | a typed host matches a curated row's verified domain (EXACT); a one-edit (two for ≥10 chars) optimal-string-alignment match on CURATED names only, weakest rank, never under 5 letters | variant matrix `search98.py` | — |
| 4 | Approved-source selection: independent quota (`webapp/app.py`) | The per-family quotas summed to exactly 14 = the budget, so every run read at most ONE independent document; the rubric needs two origins | independent family up to 3 slots, each only for an origin not yet held, never a guessed review page | `test_independent_accounts_get_distinct_slots.py` | quota 3→1: CAUGHT |
| 5 | Selection: ordering inside the independent family | w1 (Alteryx): four other registrants' passing mentions (peer-group list, a biography) took the slots over two articles directly about Alteryx; origins 1 → 0 | ordered by the verifier's own subject-relevance verdict (`relevance` / `mention_relevance`), venue breaks ties | `…an_article_about_the_company_beats_a_passing_mention…` | venue-first ordering: CAUGHT |
| 6 | Publishers (`independent_reporting.PUBLISHERS`) | categories 2–4 had few verified trade voices | SD Times, Logistics Viewpoints, CyberScoop admitted by the channel's own probe; 12 refused/empty; 4 excluded unprobed as company-voice republishers (FinSMEs, AIthority, Security Boulevard, Unite.AI) | probe record `publisher_probe98.json` | — |
| 7 | Dossier publication after deferred evidence (`_run_analysis`) | w2 (ClickHouse): dossier written once from the CORE's 4 documents; 7 more (TechCrunch "triples annualized revenue to $250M", SiliconANGLE) recomposed 0.8 s later never reached the evidence page, X-Ray or independence count ("1 of 4 sources") | a recomposed answer republishes its dossier (`latest()` serves it) | `test_a_recomposed_answer_republishes_its_dossier` | republish removed: CAUGHT |
| 8 | `progress.json` settled signal | runs are terminal at CORE; the answer changed 1.6 s after COMPLETE; any reader (and the harness) graded a transient | `settled` = terminal and not in flight (computed from the in-flight registry); the harness reads surfaces once settled, still timing CORE | `test_the_poller_says_when_the_reading_is_final` | — |
| 9 | Research memory across rounds | fresh store per round wiped the product's verified-article memory; feed churn moved independence ±3/round on unchanged code (R8/R9) | development rounds share `reports/prospect98/research_memory_dev` (per company domain, re-fetched and re-verified on use); held-out rounds get a fresh one | — | — |
| 10 | Intro/result: say it once (`founder_brief/steps.render_intro`) | 57 baseline pages printed the standing reason in "The strategic read" and again as "What matters now" 01 | a statement the read box made is skipped; the list renumbers; an emptied list prints no heading | `test_intro_says_the_standing_reason_once.py` | dedupe removed: CAUGHT |
| 11 | Independent discovery query name (`service._independent_reporting_candidates`) | w4 (Prophix): a registry pick carries the legal name; the query became "Prophix Software" and found nothing where the website entry found four direct articles (2 → 0); "Eurasia Group" was searched as "Eurasia" | the run's domain resolves the curated entity and its common name is the query; aliases shorter than it are never search terms | `test_independent_discovery_uses_the_press_name.py` | old naming: CAUGHT (2 of 3) |
| 12 | Forecast registration (`paper_validation/forward.py`, branch `fix/forward-register-reliability`) | 2026-11-27 19:17 ET: one SPY timeout, no retry, `KeyError('SPY')`, rc=1 | bounded retry on transient network errors; explicit `BENCHMARK_UNAVAILABLE` rc=2 that writes nothing; no stale or alternate price | `test_forward_register_benchmark_unavailable.py` | guard removed: CAUGHT (`KeyError: 'SPY'`) |

| 13 | Identity anchor by hyperlink (`independent_reporting.links_to_domain`) | Wiz (a $32B acquisition) read as having no outside coverage: short names with real namesakes need an anchor and the press never prints "wiz.io" in running text | a publisher's link to the verified domain anchors the name; relevance still adjudicated on the text | `test_a_link_is_an_identity_anchor.py` | anchor wiring removed: CAUGHT |
| 14 | ONE press-name definition (`entities.press_names`) for discovery, the independence count and provenance | w6 (Wiz): discovery verified 3 articles; measurement then called all 3 "never names the company" (terms built from "Wiz, Inc.", bare 3-letter names dropped) | the curated entity resolved by DOMAIN supplies the common name and aliases to all three stages; aliases shorter than the common name never used | `test_one_definition_of_the_press_name.py`; replay: Wiz 0 -> 3 bearing, Zip unchanged | app wiring removed: CAUGHT |
| 15 | Narrative say-once (`webapp.app.say_once`, in `_with_ask`) | 52/70 companies repeated prose; producers differ per surface | page-level: a >= 60-char sentence already said is not said again; furniture exempt; evidence page and History Rewind exempt; links/controls never dropped | `test_a_narrative_page_says_a_thing_once.py` (5) | first version dropped a paragraph's link: caught by its own test, fixed |
| 16 | Mobile: definition lists wrap (`dd,dt{overflow-wrap:anywhere}`) | Deltek evidence page 2px past 320px (a hostname) | shared stylesheet rule | `test_a_source_hostname_wraps_on_a_phone`; browser re-measure 322 -> 320 | — |

## Measurement defects found in my own instruments (fixed, contaminated results kept)

* `qualify98` filled a re-render set with journey captures rendered by older code (surfaces answering 303 have no page of their own). Scorecards graded on those are kept as `*_contaminated.json`; clean re-renders: `baseline/rerender_clean`, `w4/rerender_w5_clean`.
* The browser matrix's widths (320,375,390,430,768,820,1024,1280,1440,1920) differ from the program's list; runs use the union of both (12 widths x 2 themes).

## Considered and NOT done

* **Widening the economic evidence phrase table** (e.g. "free tier", "per month",
  "credits" for PRICING). These are pricing-page furniture: they show a company
  HAS pricing, not that it FACES a pricing decision. Adding them would turn the
  class prior into "evidence-led" for every company with a pricing page --
  manufactured evidence. Economics stays BOUNDED where the record does not
  show the decision.
* **GDELT** (built, disabled since 2026-11-09). Answers 200 to a single paced
  request now; in-process it was rate-limited during the A/B and added nothing.
  Its first result for ClickHouse was a finanznachrichten.de copy of a Business
  Wire release, so wire-copy rejection must be proven on it before enabling.
* **Former-filer bounded history** (Alteryx, Coupa, OneStream, Domo). No consumer
  of `TAKEN_PRIVATE` exists; a bounded CIK relationship touches filing
  candidates, XBRL history and independence. Domo's former CIK is now a shell,
  so a bare CIK would attribute the shell's filings to Domo. Designed, deferred.
* **Customer-voice review pages** (G2, Trustpilot, Capterra). Guessed URLs;
  117 baseline candidates, 0 read. Demoted, never given an extra slot.
