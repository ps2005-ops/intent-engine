"""V1.1 manual real-company acceptance runner.

Runs the complete pipeline (create run → discover → approve → fetch →
compose) for three real companies over RECORDED real pages. The page
content below is verbatim from the live sites (titles, meta
descriptions, and key visible sentences), retrieved 2026-07-23 via the
environment's permitted fetcher; the sandbox's egress policy blocks
arbitrary in-process HTTP, which is recorded honestly in
docs/V11_REAL_COMPANY_ACCEPTANCE.md.

Usage: PYTHONPATH=src python3 scripts/v11_real_company_acceptance.py
"""
import json
import sys
import tempfile
import urllib.error
from email import message_from_string

sys.path.insert(0, "src")

from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.founder_intelligence.service import (
    FounderIntelligenceService,
)


def page(title, meta, paragraphs, links=()):
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    nav = "".join(f'<a href="{l}">{l}</a>' for l in links)
    return (f"<html><head><title>{title}</title>"
            f'<meta name="description" content="{meta}"></head>'
            f"<body>{nav}{body}</body></html>")


COMPANIES = {
    "plausible.io": {
        "name": "Plausible Analytics",
        "website": "https://plausible.io",
        "pages": {
            "https://plausible.io": page(
                "Plausible Analytics | Simple, privacy-friendly Google Analytics alternative",
                "Plausible is a lightweight and open-source Google Analytics alternative. Your website data is 100% yours and the privacy of your visitors is respected.",
                ["Easy to use and privacy-friendly Google Analytics alternative",
                 "Plausible is powerful, lightweight analytics. No cookies, just insights. Made and hosted in the EU, powered by European-owned infrastructure.",
                 "Google Analytics is overkill for most site owners. Plausible gives you clear, useful insights without complexity, training or prior analytics experience.",
                 "Plausible is simple analytics. It is easy to understand and cuts through the noise.",
                 "Our script is 54 times smaller than Google Analytics.",
                 "Plausible is privacy-friendly analytics that doesn't process personal data or track individual users. No cookies, no persistent identifiers, no cross-site or cross-device tracking.",
                 "Traffic based plans that match your growth. Sign up for 30-day free trial. No credit card required.",
                 "Starter $9 /month. Growth $14 /month. Business $19 /month. Enterprise Custom.",
                 "Built with visitor privacy in mind. No cookie banner required."],
                links=["/about", "/simple-web-analytics", "/docs", "/blog"]),
            "https://plausible.io/about": page(
                "About | Plausible Analytics",
                "Plausible Analytics is an independent, open source web analytics company. We're a small, self-funded team building a privacy-friendly alternative to Google Analytics.",
                ["Plausible Analytics is an independent, open source analytics company based in the EU.",
                 "We do not use cookies and we do not collect personal data. No surveillance model, no data brokerage, no conflict of interest between what we sell and what our customers need.",
                 "We are self-funded and profitable, with no outside investors and no plans to sell.",
                 "We have never spent a cent on advertising, affiliates or paid endorsements. Plausible grows because people recommend it when they have no reason to other than that it works.",
                 "Plausible is open source under the GNU Affero General Public License Version 3 (AGPLv3).",
                 "Today Plausible is a team of 10."]),
        },
        "pasted": {
            "label": "DHH public post (X/Twitter, 2021)",
            "origin": "public X/Twitter post by 37signals CTO, quoted on plausible.io",
            "text": ("Been a very happy customer of Plausible at Basecamp. "
                     "Wonderful to see domains like web stats that were once "
                     "a wasteland due to monopoly weight spring new, better "
                     "options. Simple and reliable and respects privacy."),
        },
    },
    "usefathom.com": {
        "name": "Fathom Analytics",
        "website": "https://usefathom.com",
        "pages": {
            "https://usefathom.com": page(
                "Fathom Analytics: A Better Google Analytics Alternative",
                "Ditch complex, intrusive analytics for Fathom - a better Google analytics alternative. Experience ease of use, forever data retention & full legal compliance.",
                ["A Google Analytics alternative that's simple & privacy-first",
                 "Experience ease of use, forever data retention, and complete, worry-free GDPR compliance - all while protecting your time and your visitors' digital privacy.",
                 "At Fathom, we strongly believe that analytics tools should be insightful, not invasive.",
                 "Our script is a single line of code that works with any website, CMS or framework.",
                 "We've hired the best lawyers and legal minds worldwide to ensure our simple analytics software is fully compliant with GDPR, CCPA, ePrivacy, PECR and more.",
                 "Our real-time analytics blocks bots, scrapers and spam traffic—showing you only real, human visits.",
                 "Fathom anonymizes IP addresses and other visitor data without using cookies.",
                 "We're a small but mighty team and we don't need (or want) funding or investors."],
                links=["/pricing", "/features", "/about", "/blog"]),
            "https://usefathom.com/pricing": page(
                "Simple and sustainable pricing - Fathom Analytics",
                "Our pricing is simple, you pay for the number of pageviews that you use each month.",
                ["Simple and sustainable pricing",
                 "Start with a 7-day free trial of Fathom and then pay a fair and sustainable monthly price based on your average monthly page views.",
                 "Forever data retention. While you're a customer, your full analytics history stays available.",
                 "Privacy-first analytics that works under GDPR without consent popups.",
                 "Your data belongs to you. We never sell it or use it for advertising.",
                 "We've never done discounts, nor will we ever. We feel this is fair, because everyone pays the exact same price.",
                 "Our business model is selling software, not your data."]),
        },
        "pasted": {
            "label": "Huberman Lab quote (public, usefathom.com)",
            "origin": "public testimonial on usefathom.com homepage",
            "text": ("Analytics for Huberman Lab are solely powered by "
                     "Fathom. It's such a pleasure to use compared to Google "
                     "Analytics. There's just the right number of features, "
                     "and their platform is incredibly intuitive."),
        },
    },
    "transistor.fm": {
        "name": "Transistor.fm",
        "website": "https://transistor.fm",
        "pages": {
            "https://transistor.fm": page(
                "Host Unlimited Shows • Best Audio and Video Podcast Hosting • Transistor",
                "Upload once and distribute your video and audio podcast to Apple Podcasts, Spotify, YouTube, and more. Unlimited shows, detailed analytics, free podcast website, and real human support.",
                ["Publish your podcast everywhere",
                 "Get your podcast on Apple Podcasts, Spotify, YouTube, Overcast, Pocket Casts, and many more!",
                 "Host a members-only podcast for your company or online community.",
                 "We don't charge you for creating additional podcasts.",
                 "Choose a design and we'll automatically generate a website for your show.",
                 "See your average downloads per episode, popular podcast apps, number of subscribers, trends.",
                 "Try us free for 14 days.",
                 "Starter $19 mo. Professional $49 mo. Business $99 mo.",
                 "Transistor.fm provides podcast hosting and analytics for thousands of organizations, brands, and creatives around the world."],
                links=["/pricing", "/about", "/features", "/blog"]),
            "https://transistor.fm/about": page(
                "About Transistor: a simple, yet powerful podcast hosting platform",
                "You want to record your audio, and then get that audio onto platforms like Apple Podcasts and Spotify. We provide the hosting and analytics tools you'll need. Learn more about our company.",
                ["We make podcasting less confusing.",
                 "At Transistor, we guide you through the podcasting landscape. Record your audio and upload it to Transistor.",
                 "We're more than hosting and analytics. We'll help answer your questions with our live chat and guides.",
                 "We are a team of six people.",
                 "They signed a partnership document in February 2018 and officially launched on August 1, 2018.",
                 "Today, we serve over 30,000 podcasts of all types. Our customers include indie podcasters, small businesses, and enterprise companies."]),
        },
        "pasted": {
            "label": "Product Hunt review (public)",
            "origin": "public Product Hunt rating quoted on transistor.fm",
            "text": ("The best podcast hosting tool I've used. Simple to "
                     "publish, reliable, and the customer support is by "
                     "real humans who answer quickly."),
        },
    },
}


def make_transport(pages):
    def transport(url, timeout):
        url = url.rstrip("/") if url.rstrip("/") in pages else url
        if url in pages:
            return (200, {"content-type": "text/html"},
                    pages[url].encode(), False)
        raise urllib.error.HTTPError(url, 404, "not found",
                                     message_from_string(""), None)
    return transport


def main():
    out = {}
    for domain, spec in COMPANIES.items():
        ci = CompanyIngestionService(tempfile.mktemp(suffix=".jsonl"),
                                     transport=make_transport(spec["pages"]),
                                     resolver=False)
        fi = FounderIntelligenceService(tempfile.mktemp(suffix=".jsonl"))
        run = ci.create_run(company_name=spec["name"],
                            website=spec["website"], user_id="manual-reviewer",
                            as_of="2026-07-23T00:00:00+00:00")
        candidates = ci.discover(run["run_id"])
        approved = [c["candidate_id"] for c in candidates
                    if c["url"].rstrip("/") in
                    {u.rstrip("/") for u in spec["pages"]}]
        ci.approve(run["run_id"], user_id="manual-reviewer",
                   approved_ids=approved,
                   rejected_ids=[c["candidate_id"] for c in candidates
                                 if c["candidate_id"] not in approved])
        fetched = ci.fetch_approved(run["run_id"])
        ci.add_pasted(run["run_id"], user_id="manual-reviewer",
                      **spec["pasted"], privacy="user_public_excerpt",
                      authorized=True)
        result = ci.compose(run["run_id"], fi_service=fi)
        claims = []
        for section in result["sections"]:
            for card in section.get("cards", []):
                for claim in card.get("claims", []):
                    claims.append({
                        "id": claim["claim_id"], "text": claim["text"],
                        "avail": claim["availability"],
                        "refs": [r["artifact_id"]
                                 for r in claim["source_refs"]],
                        "subsystems": sorted({r["subsystem"] for r in
                                              claim["source_refs"]})})
        out[domain] = {
            "run_id": run["run_id"],
            "candidates_shown": len(candidates),
            "approved": len(approved),
            "fetch_status": fetched["status"],
            "ok_sources": len(fetched["ok"]),
            "failed_sources": len(fetched["failed"]),
            "report_status": result["ingestion_status"],
            "overview": [s["text"] for s in result["overview"]],
            "claims": claims,
            "subsystems": sorted({s for c in claims
                                  for s in c["subsystems"]}),
        }
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
