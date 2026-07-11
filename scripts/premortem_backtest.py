#!/usr/bin/env python
"""Part 4a: backtest PremortemAnalyzer against 18 real, cited historical
business decisions and report an honest correlation against known outcomes.

Zero production-code changes. This script calls run_premortem() /
PremortemAnalyzer completely unmodified -- same class, same prompt, same
schema used everywhere else in this codebase. The only new code is here:
the dataset, the yfinance macro-context fetch, the scoring/aggregation, and
the report.

NO-HINDSIGHT DISCIPLINE: each case's `decision_text` and `context` describe
only what would have been knowable AT THE TIME the real decision was made.
The real, cited, now-known outcome is stored separately in `real_outcome`
and is never passed into PremortemAnalyzer -- it's compared against the
model's output only after the fact, by this script.

DOMAIN-FIT CAVEAT, stated plainly, not smoothed over: PremortemAnalyzer's
own system prompt (simulator/analysis.py) scopes it explicitly to
"pre-seed/seed-stage SaaS founders." Most of the strongest, best-documented
real historical cases below are NOT pre-seed/seed-stage SaaS -- several are
post-IPO (Groupon, WeWork's attempted IPO, Webvan, Pets.com), several are
consumer/marketplace/hardware rather than SaaS (Airbnb, Instagram, Juicero,
MoviePass, Homejoy, Fab, Digg). This is a real mismatch between the tool's
designed scope and this backtest's dataset, kept in the dataset anyway
because these are the real, well-documented cases available with citable
outcomes -- the correlation result below must be read with this caveat
prominently in mind, not as a validation of PremortemAnalyzer for domains
it wasn't built for.

SAMPLE SIZE CAVEAT, stated plainly: n=18 is far too small to draw any
statistically valid conclusion. Any correlation coefficient below is
exploratory/directional only -- do not treat it as validating or
invalidating PremortemAnalyzer.

Usage: python scripts/premortem_backtest.py
"""

import sys
from pathlib import Path

import numpy as np
import yfinance as yf

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from intent_engine.simulator.context_schema import BusinessContext  # noqa: E402
from intent_engine.simulator.pipeline import run_premortem  # noqa: E402

# --- Likelihood -> numeric weighting -----------------------------------
# A stated judgment call, not empirically derived: tail_risk (low
# probability, high impact) is weighted ABOVE likely, because a pre-mortem
# risk audit's job is to flag exactly this kind of risk most loudly even
# though it's improbable -- collapsing it below "likely" would understate
# what the audit is designed to surface.
LIKELIHOOD_WEIGHT = {"unlikely": 1, "possible": 2, "likely": 3, "tail_risk": 4}


# --- Dataset: 18 real, cited historical decisions -----------------------
# Each decision_text/context describes ONLY what was knowable at the time.
# real_outcome is real, cited, and kept separate -- never fed to the model.

CASES = [
    dict(
        id="groupon_reject_google",
        decision_text=(
            "We run a daily-deals startup that has grown extremely fast over the past year, mostly "
            "through aggressive local sales-rep hiring and email-list growth. Google has just made an "
            "acquisition offer in the range of $5.3-6.0 billion, reportedly including an earnout. We are "
            "also in the middle of raising a large new private funding round at a multi-billion-dollar "
            "valuation, and several board members believe we could reach an IPO within the next year at "
            "an even higher valuation than Google's offer. Should we accept Google's offer or reject it "
            "and continue pursuing independent growth toward an IPO?"
        ),
        context=BusinessContext(
            revenue="~$760M run-rate (2010)",
            growth_rate="Extremely fast, quarter-over-quarter multiples through 2010",
            team_size=3000,
            runway_months=None,
            market="Daily deals / local e-commerce",
            competitive_position="Category leader, but LivingSocial and many local clones emerging fast",
            founder_goals="Build an independent, IPO-scale company rather than sell",
            stated_priorities=["growth", "independence", "market leadership"],
        ),
        decision_date="2010-12-03",
        ticker=None,
        real_outcome=(
            "Groupon rejected Google's offer, raised a new round at ~$4.75B valuation, and IPO'd in "
            "Nov 2011 at a ~$16.7B valuation. The stock fell sharply in the following years amid growth "
            "slowdown, deal-quality and accounting concerns -- by 2020 shares traded near $2 (from a $20 "
            "IPO price), a small fraction of the rejected acquisition price. Widely cited as one of the "
            "most consequential 'we said no' moments in startup history."
        ),
        outcome_failure=True,
        sources=["NBC News", "Bloomberg", "Forbes", "Harvard Program on Negotiation", "SEC filings"],
    ),
    dict(
        id="quibi_paid_launch",
        decision_text=(
            "We are launching a new short-form streaming service backed by ~$1.75B in funding, targeting "
            "mobile-first viewers with Hollywood-produced 'quick bite' episodes. We're deciding on launch "
            "positioning: charge a subscription from day one ($4.99/month with ads, $7.99 without), with "
            "no free tier, and deliberately exclude the ability to cast content to a TV screen (mobile-only "
            "viewing is core to the product thesis). We project several million subscribers within the "
            "first months based on our internal forecasts. Launch is set for April 2020."
        ),
        context=BusinessContext(
            revenue="Pre-launch (no revenue yet)",
            growth_rate=None,
            team_size=200,
            runway_months=None,
            market="Mobile short-form video streaming",
            competitive_position="First-mover in the specific 'quick bites' format; competing broadly with YouTube, TikTok, Netflix for attention",
            founder_goals="Rapidly build a large paid subscriber base and prove a new content format",
            stated_priorities=["growth", "premium content quality", "mobile-first differentiation"],
        ),
        decision_date="2020-04-06",
        ticker=None,
        real_outcome=(
            "Quibi launched April 6, 2020 (amid COVID-19 lockdowns) with a paid-only, no-cast-to-TV model. "
            "It badly missed its ~7M subscriber projection, reaching only ~500K paying subscribers, and "
            "shut down roughly six months later in October 2020, returning much of the remaining capital "
            "to investors -- one of the fastest, largest startup failures on record."
        ),
        outcome_failure=True,
        sources=["CNBC", "Crunchbase News", "CBS News"],
    ),
    dict(
        id="color_labs_launch",
        decision_text=(
            "We've raised $41M (including a large lead round plus venture debt) before launching our "
            "photo-sharing mobile app, which uses proximity-based sharing so nearby users automatically "
            "see each other's photos, even without a social connection. We are about to launch the app "
            "publicly with a large marketing push, betting that the novel proximity concept combined with "
            "our funding will let us scale to a mass consumer audience quickly, ahead of more conventional "
            "photo-sharing competitors."
        ),
        context=BusinessContext(
            revenue="Pre-revenue",
            growth_rate=None,
            team_size=25,
            runway_months=None,
            market="Consumer mobile photo-sharing",
            competitive_position="Novel proximity-based mechanic, unproven against Instagram and other photo apps",
            founder_goals="Rapid mass-consumer adoption",
            stated_priorities=["growth", "novel product mechanic", "large funding runway"],
        ),
        decision_date="2011-03-24",
        ticker=None,
        real_outcome=(
            "Color launched March 24, 2011 to widely negative reviews (the proximity mechanic confused "
            "users and required a large nearby userbase to be useful at all -- a cold-start problem). "
            "Usage never took off despite the funding. The company pivoted repeatedly and effectively "
            "shut down / stopped operating by the end of 2012, roughly 18 months after launch."
        ),
        outcome_failure=True,
        sources=["Wikipedia", "Fast Company", "TheStupidFounder"],
    ),
    dict(
        id="moviepass_995_pricing",
        decision_text=(
            "Under new ownership, we're relaunching our movie-theater subscription service at $9.95/month "
            "for unlimited one-movie-per-day theatrical admission, a steep cut from typical single-ticket "
            "prices in most markets. The bet is that this price will drive rapid subscriber growth and "
            "give us leverage to negotiate favorable revenue-sharing deals with theater chains and "
            "advertisers/data partners later, even though we will be paying theaters close to full price "
            "per ticket redeemed in the near term."
        ),
        context=BusinessContext(
            revenue="Small, ~20K subscribers pre-relaunch",
            growth_rate="Flat/slow before this pricing change",
            team_size=None,
            runway_months=None,
            market="Movie-theater subscription / ticketing",
            competitive_position="Small player vs. theater chains' own loyalty programs",
            founder_goals="Rapidly scale subscriber base to build negotiating leverage and a data business",
            stated_priorities=["growth", "market share", "future monetization via data/advertising"],
        ),
        decision_date="2017-08-15",
        ticker="HMNY",
        real_outcome=(
            "Subscribers grew from ~20K to over 3 million within about a year, but the company paid "
            "theaters close to full ticket price per redemption while charging $9.95, burning an "
            "estimated $20-40M/month. MoviePass shut down September 14, 2019; parent Helios and Matheson "
            "Analytics filed for Chapter 7 bankruptcy in January 2020."
        ),
        outcome_failure=True,
        sources=["Wikipedia", "The Hollywood Reporter", "TheStreet"],
    ),
    dict(
        id="wework_ipo_filing",
        decision_text=(
            "We operate a global co-working/flexible-office-space company. We are filing an S-1 to go "
            "public, seeking a valuation around $47 billion based on our last private funding round, "
            "despite being unprofitable with large ongoing losses tied to long-term real-estate lease "
            "commitments. Our governance structure gives our founder/CEO outsized voting control, and we "
            "plan to move forward with the public roadshow and listing on this timeline."
        ),
        context=BusinessContext(
            revenue="~$1.5B annualized run-rate, with comparably large net losses",
            growth_rate="Fast revenue growth, but losses growing alongside it",
            team_size=12000,
            runway_months=None,
            market="Commercial flexible office space / real estate",
            competitive_position="Largest player in flexible office space globally, but capital-intensive lease-based model",
            founder_goals="Public listing at a valuation consistent with prior private funding rounds, while retaining founder control",
            stated_priorities=["growth", "global expansion", "founder control"],
        ),
        decision_date="2019-08-14",
        ticker=None,
        real_outcome=(
            "Public and investor scrutiny of the S-1 (governance, related-party transactions, path to "
            "profitability) collapsed confidence in the offering. CEO Adam Neumann resigned Sept 24, 2019; "
            "the IPO was formally withdrawn Sept 30, 2019; SoftBank's subsequent rescue financing (Oct 23, "
            "2019) valued the company at under $8 billion -- an ~85% drop from the S-1 target valuation."
        ),
        outcome_failure=True,
        sources=["CNBC", "NPR", "SEC S-1 filing", "Wikipedia"],
    ),
    dict(
        id="airbnb_cereal_boxes",
        decision_text=(
            "Our home-sharing marketplace startup is nearly out of cash and has been rejected by most "
            "investors we've pitched. It's a U.S. presidential election year with heavy media coverage of "
            "the two candidates. As a way to generate cash and attention cheaply, we're considering "
            "designing and selling a small limited run (~500 boxes) of novelty election-themed breakfast "
            "cereal, branded around the two candidates, at $40/box, rather than spending our limited time "
            "purely on further fundraising outreach or product development."
        ),
        context=BusinessContext(
            revenue="Near zero",
            growth_rate=None,
            team_size=3,
            runway_months=1,
            market="Home-sharing / short-term rental marketplace",
            competitive_position="Unproven early-stage idea, struggling to get investor interest",
            founder_goals="Survive long enough to get real investor traction",
            stated_priorities=["survival", "cash generation", "attention/credibility"],
        ),
        decision_date="2008-09-01",
        ticker=None,
        real_outcome=(
            "The founders sold roughly $30,000 worth of the novelty cereal boxes, enough to keep the "
            "company alive. The stunt's press attention and demonstrated hustle is widely credited (per "
            "Paul Graham's own account) as a key factor in Y Combinator accepting and later investing in "
            "the company, which became Airbnb."
        ),
        outcome_failure=False,
        sources=["Yahoo Finance", "Benzinga"],
    ),
    dict(
        id="slack_pivot_from_glitch",
        decision_text=(
            "Our funded startup spent nearly two years building a browser-based MMORPG. Despite real "
            "engineering effort and some dedicated players, growth has stalled and we don't see a path to "
            "the scale needed to justify continued investment. Internally, though, the team has been using "
            "a real-time messaging/chat tool we built for our own coordination during development, and "
            "several people who've seen it think it could be useful well beyond our own team. We're "
            "deciding whether to shut down the game and pivot the company entirely around turning that "
            "internal chat tool into the actual product."
        ),
        context=BusinessContext(
            revenue="Small, from the game",
            growth_rate="Stalled",
            team_size=45,
            runway_months=8,
            market="Online gaming, pivoting toward workplace communication software",
            competitive_position="Weak in gaming; internal tool untested in the external market",
            founder_goals="Find a sustainable, scalable business before running out of capital",
            stated_priorities=["survival", "finding product-market fit", "capital efficiency"],
        ),
        decision_date="2012-08-01",
        ticker=None,
        real_outcome=(
            "The team shut down the game (Glitch) and rebuilt the company entirely around the internal "
            "chat tool, launched publicly in 2014 as Slack. Slack became one of the fastest-growing SaaS "
            "products of its era and was acquired by Salesforce in 2021 for approximately $27.7 billion."
        ),
        outcome_failure=False,
        sources=["TechCrunch (\"The Slack origin story\")", "buildingslack.com", "SitePoint"],
    ),
    dict(
        id="instagram_pivot_from_burbn",
        decision_text=(
            "We raised a $500K seed round for a location-based check-in app with many features: "
            "check-ins, plans-making, photo-sharing, points/gamification. Usage has stalled at a very "
            "small number of active users, but data shows the one feature people actually use heavily is "
            "photo posting with comments and likes. We're deciding whether to keep building out the "
            "full-featured check-in app or strip it down to just the photo-sharing feature, discard "
            "everything else, and relaunch as a much simpler product."
        ),
        context=BusinessContext(
            revenue="Pre-revenue",
            growth_rate="Stalled, ~100 active users on the full-featured app",
            team_size=2,
            runway_months=6,
            market="Consumer mobile social/photo apps",
            competitive_position="Crowded check-in app market (Foursquare, Gowalla); no differentiation yet",
            founder_goals="Find the one feature with real organic engagement and focus entirely on it",
            stated_priorities=["finding product-market fit", "simplicity", "growth"],
        ),
        decision_date="2010-07-01",
        ticker=None,
        real_outcome=(
            "The founders stripped the app down to just photo capture, filters, comments, and likes, "
            "relaunching Oct 6, 2010 as Instagram. It grew to over 1 million users within two months and "
            "was acquired by Facebook in April 2012 for approximately $1 billion."
        ),
        outcome_failure=False,
        sources=["TechCrunch (\"A Pivotal Pivot\")", "Wikipedia"],
    ),
    dict(
        id="juicero_400_hardware",
        decision_text=(
            "We've raised over $100M (including major VC backing) to build a connected juicing system: a "
            "$400 WiFi-enabled press that requires proprietary, subscription-delivered produce packs "
            "readable by a QR code, which the machine uses to precisely control the press for food-safety "
            "and quality reasons. We're launching the hardware and subscription pack business at this "
            "price point, betting that the precision, food-safety tracking, and convenience justify the "
            "premium over a standard blender or manual juicer."
        ),
        context=BusinessContext(
            revenue="Early, subscription-pack based",
            growth_rate="Early stage",
            team_size=None,
            runway_months=None,
            market="Connected kitchen hardware / fresh food subscription",
            competitive_position="Novel connected-hardware niche; competes indirectly with much cheaper blenders/juicers",
            founder_goals="Build a premium hardware + recurring consumables subscription business",
            stated_priorities=["premium positioning", "food safety/quality control", "recurring revenue"],
        ),
        decision_date="2016-03-01",
        ticker=None,
        real_outcome=(
            "In April 2017, Bloomberg demonstrated that the proprietary produce packs could be squeezed "
            "by hand to yield nearly identical juice output without the $400 machine at all, undermining "
            "the core value proposition publicly. The company suspended sales in September 2017 and shut "
            "down shortly after."
        ),
        outcome_failure=True,
        sources=["Bloomberg", "CBS News", "Wikipedia"],
    ),
    dict(
        id="homejoy_1099_model",
        decision_text=(
            "Our home-cleaning marketplace connects customers with independent cleaners, whom we classify "
            "as 1099 independent contractors rather than W-2 employees, to keep costs lower and scale "
            "faster across many cities. We're deciding whether to continue relying on this contractor "
            "classification as we expand, versus reclassifying workers as employees (which would raise "
            "costs and slow expansion but reduce legal exposure)."
        ),
        context=BusinessContext(
            revenue="Growing, multi-city",
            growth_rate="Fast city-by-city expansion",
            team_size=None,
            runway_months=None,
            market="On-demand home services marketplace",
            competitive_position="Multiple well-funded competitors in the same on-demand services space",
            founder_goals="Scale to as many cities as possible quickly and cost-efficiently",
            stated_priorities=["growth", "cost efficiency", "speed of expansion"],
        ),
        decision_date="2014-01-01",
        ticker=None,
        real_outcome=(
            "The company faced four separate lawsuits alleging worker misclassification. CEO Adora Cheung "
            "later cited the lawsuits as a 'deciding factor' making it much harder to raise a new funding "
            "round. Homejoy shut down at the end of July 2015."
        ),
        outcome_failure=True,
        sources=["Forbes", "SiliconBeat", "JD Supra"],
    ),
    dict(
        id="fab_over_expansion",
        decision_text=(
            "Our flash-sale design-goods e-commerce site (pivoted from an earlier failed social product) "
            "grew to over 2 million users and raised $50M within its first seven months. Riding that "
            "momentum, we're deciding whether to aggressively scale internationally -- acquiring three "
            "competing 'clone' companies in Europe for a combined $60-100M and pushing hard into new "
            "geographies and product categories -- versus growing more conservatively within our proven "
            "core market."
        ),
        context=BusinessContext(
            revenue="Fast-growing, early-stage e-commerce",
            growth_rate="Very fast (2M+ users, $50M raised within 7 months)",
            team_size=None,
            runway_months=None,
            market="Flash-sale e-commerce / design goods",
            competitive_position="Strong early momentum in the U.S.; several regional clone competitors in Europe",
            founder_goals="Become the dominant global player in design-focused flash-sale e-commerce",
            stated_priorities=["growth", "global market share", "speed of international expansion"],
        ),
        decision_date="2012-01-01",
        ticker=None,
        real_outcome=(
            "The aggressive international acquisitions and expansion strained the business; growth "
            "slowed and losses mounted. The company was sold to PCH International in February 2015 for a "
            "reported combined cash-and-stock value of roughly $15M -- a steep fall from a peak valuation "
            "reported above $200M."
        ),
        outcome_failure=True,
        sources=["Inc.", "VentureBeat", "TechCrunch", "Wikipedia"],
    ),
    dict(
        id="digg_v4_redesign",
        decision_text=(
            "Our social news aggregation site is redesigning its core product, moving away from a "
            "user-driven 'bury'/upvote ranking system toward a model with more editorial/publisher "
            "influence over the front page. The redesign will also remove several long-standing features "
            "(user favorites, friend-submitted-story feeds, subcategories) to simplify the product. We're "
            "planning to ship this redesign to our entire user base at once rather than a staged rollout, "
            "on a fixed launch date."
        ),
        context=BusinessContext(
            revenue="Ad-supported, established site",
            growth_rate="Flat to declining relative to newer competitor Reddit",
            team_size=None,
            runway_months=None,
            market="Social news aggregation",
            competitive_position="Long-time category leader, but Reddit growing quickly as an alternative",
            founder_goals="Modernize the product and improve content quality/monetization",
            stated_priorities=["product modernization", "monetization", "simplifying the codebase/features"],
        ),
        decision_date="2010-08-25",
        ticker=None,
        real_outcome=(
            "The v4 redesign launched buggy and stripped out features many core users relied on. "
            "Referral-traffic share versus Reddit, which had favored Digg roughly 56%/43% before launch, "
            "flipped to Reddit taking about 92% within a month. A prominent 'Quit Digg Day' user protest "
            "followed on Aug 30, 2010."
        ),
        outcome_failure=True,
        sources=["Know Your Meme", "Harvard Business School Technology and Operations Management blog", "Wikipedia"],
    ),
    dict(
        id="webvan_infra_scaling",
        decision_text=(
            "Our online grocery delivery startup has raised roughly $800M in venture funding from major "
            "investors. We're deciding whether to invest heavily upfront in building large, highly "
            "automated regional distribution warehouses ahead of proven demand in each new city, to "
            "achieve the operational efficiency needed at scale -- versus growing city-by-city more "
            "slowly and proving unit economics before each new large capital investment."
        ),
        context=BusinessContext(
            revenue="Early, single-city",
            growth_rate="Pre-scale",
            team_size=None,
            runway_months=None,
            market="Online grocery delivery",
            competitive_position="First-mover in automated grocery delivery infrastructure",
            founder_goals="Build a nationally dominant, highly efficient grocery delivery network",
            stated_priorities=["scale", "operational efficiency", "market dominance"],
        ),
        decision_date="1999-06-01",
        ticker=None,
        real_outcome=(
            "Webvan built expensive automated warehouses in multiple cities ahead of proven demand, "
            "raising a $375M IPO in Nov 1999 on top of its private funding (~$1.2B total raised). Demand "
            "never matched the built-out capacity; the company filed for Chapter 11 bankruptcy on July 9, "
            "2001, about 18 months after its IPO."
        ),
        outcome_failure=True,
        sources=["Wikipedia", "CNN Money"],
    ),
    dict(
        id="petscom_superbowl_ad",
        decision_text=(
            "Our online pet-supplies retailer is preparing for an IPO in the coming weeks. To build brand "
            "awareness quickly ahead of the offering and holiday/post-holiday shopping season, we're "
            "deciding whether to buy a 30-second national television ad during the Super Bowl, a "
            "high-visibility but very expensive placement, versus spending the equivalent budget on more "
            "targeted, measurable online/direct-response marketing."
        ),
        context=BusinessContext(
            revenue="Early-stage e-commerce, pre-IPO",
            growth_rate="Fast user growth, large losses",
            team_size=None,
            runway_months=None,
            market="Online pet supplies e-commerce",
            competitive_position="Early mover in online pet supplies, several direct competitors also well-funded",
            founder_goals="Build strong brand awareness ahead of IPO and holiday season",
            stated_priorities=["brand awareness", "growth", "market share ahead of IPO"],
        ),
        decision_date="2000-01-30",
        ticker=None,
        real_outcome=(
            "Pets.com ran the Super Bowl XXXIV ad (Jan 2000) and IPO'd Feb 11, 2000, raising $82.5M. The "
            "company lost $147M in the first nine months of 2000 and liquidated just 268 days after its "
            "IPO."
        ),
        outcome_failure=True,
        sources=["Wikipedia", "FourWeekMBA", "Fast Company"],
    ),
    dict(
        id="dropbox_demo_video_launch",
        decision_text=(
            "We're applying to a startup accelerator and preparing to launch a cloud file-sync product. "
            "Rather than relying only on a written application or a live demo, we're deciding whether to "
            "record and post a short screencast video showing the product working, then share it publicly "
            "on tech community sites (including audience-specific variations for each site) to try to "
            "build an early beta waitlist ahead of any paid marketing."
        ),
        context=BusinessContext(
            revenue="Pre-revenue",
            growth_rate=None,
            team_size=1,
            runway_months=None,
            market="Cloud file storage and sync",
            competitive_position="Crowded space with several existing sync tools, none with strong mainstream mindshare yet",
            founder_goals="Validate demand and build an early waitlist before wider launch",
            stated_priorities=["demand validation", "low-cost distribution", "signal for accelerator application"],
        ),
        decision_date="2007-04-05",
        ticker=None,
        real_outcome=(
            "The demo video, posted to Hacker News on April 5, 2007 and later to Digg with tailored "
            "references for that audience, drove the beta waitlist from roughly 5,000 to about 75,000 "
            "signups overnight. Dropbox went on to become a major cloud storage company."
        ),
        outcome_failure=False,
        sources=["\"How Dropbox got 75000 wait-list signups from Digg\"", "YourStory"],
    ),
    dict(
        id="zappos_free_shipping_returns",
        decision_text=(
            "Our online shoe retailer is deciding on a shipping and returns policy. Buying shoes without "
            "trying them on is a major source of customer hesitation. We're considering offering free "
            "shipping both ways plus a very long return window (up to 365 days), which will meaningfully "
            "raise our logistics costs and return rates, versus a more conventional paid-shipping, "
            "shorter-return-window policy that would protect margins more directly."
        ),
        context=BusinessContext(
            revenue="Early-stage online retail",
            growth_rate="Early growth phase",
            team_size=None,
            runway_months=None,
            market="Online footwear/apparel retail",
            competitive_position="Early online shoe retailer, competing against the risk-aversion of buying shoes sight-unseen",
            founder_goals="Build a trusted, customer-obsessed brand that overcomes online-shoe-buying hesitation",
            stated_priorities=["customer trust", "reducing purchase friction", "long-term loyalty over short-term margin"],
        ),
        decision_date="1999-06-01",
        ticker=None,
        real_outcome=(
            "Zappos adopted free two-way shipping and a 365-day return policy. Despite the higher direct "
            "cost, customers who returned items most often turned out to be among the most profitable "
            "long-term customers, and the policy became central to the brand. Zappos was acquired by "
            "Amazon in 2009 for about $1.2 billion."
        ),
        outcome_failure=False,
        sources=["FoundedLi", "Business Model Analyst", "Fast Company"],
    ),
    dict(
        id="buffer_salary_transparency",
        decision_text=(
            "Our small SaaS company (social-media scheduling tool) is deciding whether to make every "
            "individual employee's salary public -- name, team, role, location, and exact dollar amount "
            "-- alongside a published formula for how salaries are calculated, rather than keeping "
            "compensation private as is standard practice. This is a values-driven transparency "
            "experiment; we're aware it could affect hiring, morale, and how the company is perceived "
            "publicly, in either direction."
        ),
        context=BusinessContext(
            revenue="Small, early-stage SaaS",
            growth_rate="Early growth",
            team_size=12,
            runway_months=None,
            market="Social media management SaaS",
            competitive_position="Small player in a competitive social-media-tools market",
            founder_goals="Build a values-driven, transparent company culture that also aids recruiting",
            stated_priorities=["transparency", "culture/values alignment", "recruiting"],
        ),
        decision_date="2013-12-01",
        ticker=None,
        real_outcome=(
            "Buffer published all salaries and its formula publicly starting in 2013. Job applications "
            "increased significantly (over 50% more applicants, more than double applications within 30 "
            "days of publishing), and the move became widely cited as a positive example of radical "
            "transparency in hiring."
        ),
        outcome_failure=False,
        sources=["Buffer's own published resources", "Raconteur"],
    ),
    dict(
        id="basecamp_reject_vc",
        decision_text=(
            "Our small, profitable software company (originally a design consultancy, now building our "
            "own project-management product) regularly receives acquisition and investment offers from "
            "venture capital and private equity firms. We're deciding on our ongoing stance: continue "
            "rejecting outside investment and acquisition offers to preserve full control and avoid "
            "growth-at-all-costs pressure, versus accepting outside capital to fund faster growth and a "
            "larger team."
        ),
        context=BusinessContext(
            revenue="Profitable, self-funded",
            growth_rate="Steady, not venture-scale hypergrowth",
            team_size=None,
            runway_months=None,
            market="Project management / team collaboration SaaS",
            competitive_position="Small, profitable niche player against much larger venture-funded competitors",
            founder_goals="Stay independent, profitable, and in control rather than chase maximum growth",
            stated_priorities=["independence", "profitability", "sustainable pace over hypergrowth"],
        ),
        decision_date="2006-01-01",
        ticker=None,
        real_outcome=(
            "The company (37signals, later renamed Basecamp) has rejected over 100 VC/PE investment "
            "offers over roughly 25 years, accepting only a single minority, no-board-seat investment "
            "from Jeff Bezos early on. It has remained profitable every month for 25 years while staying "
            "small and independent."
        ),
        outcome_failure=False,
        sources=["Basecamp's own \"Bootstrapped\" page", "Practical Founders podcast"],
    ),
]


def _fetch_market_context(decision_date: str) -> str:
    """Real macro-context signal: % change in the S&P 500 over the 30
    calendar days ending on the decision date. Same mechanism for every
    case (most of these were private companies with no ticker of their own
    at decision time) -- simple, honest, and uniformly available, rather
    than mixing index data for some cases and company-specific data for
    others without a stated reason."""
    end = decision_date
    start_ts = np.datetime64(decision_date) - np.timedelta64(30, "D")
    try:
        data = yf.download("^GSPC", start=str(start_ts), end=end, progress=False)
        if data.empty or len(data) < 2:
            return "S&P 500 data unavailable for this window"
        closes = data["Close"].squeeze()
        pct_change = (float(closes.iloc[-1]) / float(closes.iloc[0]) - 1) * 100
        return f"S&P 500 {pct_change:+.1f}% over the 30 days before this decision"
    except Exception as e:
        return f"S&P 500 data fetch failed ({e})"


def _fetch_company_ticker_context(ticker: str, decision_date: str) -> str:
    end = decision_date
    start_ts = np.datetime64(decision_date) - np.timedelta64(30, "D")
    try:
        data = yf.download(ticker, start=str(start_ts), end=end, progress=False)
        if data.empty or len(data) < 2:
            return f"{ticker} data unavailable for this window"
        closes = data["Close"].squeeze()
        pct_change = (float(closes.iloc[-1]) / float(closes.iloc[0]) - 1) * 100
        return f"{ticker} {pct_change:+.1f}% over the 30 days before this decision"
    except Exception as e:
        return f"{ticker} data fetch failed ({e})"


def _risk_score(failure_modes) -> float:
    return sum(LIKELIHOOD_WEIGHT[fm.likelihood] for fm in failure_modes) / len(failure_modes)


def main():
    print(f"Running PremortemAnalyzer (unmodified) against {len(CASES)} real historical decisions...")
    print()

    results = []
    for i, case in enumerate(CASES, 1):
        market_ctx = _fetch_market_context(case["decision_date"])
        ticker_ctx = _fetch_company_ticker_context(case["ticker"], case["decision_date"]) if case["ticker"] else None

        print(f"[{i}/{len(CASES)}] {case['id']} ({case['decision_date']})...", flush=True)

        result = run_premortem(case["decision_text"], case["context"])
        risk_score = _risk_score(result.risk_audit.failure_modes)

        results.append(dict(
            case=case,
            market_ctx=market_ctx,
            ticker_ctx=ticker_ctx,
            intent=result.intent,
            risk_audit=result.risk_audit,
            scenario_set=result.scenario_set,
            risk_score=risk_score,
            elapsed_seconds=result.elapsed_seconds,
        ))

    # --- Per-case report --------------------------------------------------
    print()
    print("=" * 90)
    print("PER-CASE RESULTS")
    print("=" * 90)
    for r in results:
        case = r["case"]
        print()
        print(f"--- {case['id']} ({case['decision_date']}) ---")
        print(f"Market context: {r['market_ctx']}" + (f" | {r['ticker_ctx']}" if r["ticker_ctx"] else ""))
        print(f"PremortemAnalyzer risk_tolerance: {r['intent'].risk_tolerance}")
        print("PremortemAnalyzer failure modes:")
        for fm in r["risk_audit"].failure_modes:
            print(f"  - [{fm.likelihood}] {fm.description}")
        print(f"PremortemAnalyzer risk_score (1=unlikely..4=tail_risk, avg of 3): {r['risk_score']:.2f}")
        print(f"PremortemAnalyzer scale_efficiency: {r['intent'].scale_efficiency}")
        print(f"PremortemAnalyzer primary_priority: {r['scenario_set'].primary_priority}")
        print(f"REAL OUTCOME (failure={case['outcome_failure']}): {case['real_outcome']}")
        print(f"Sources: {', '.join(case['sources'])}")

    # --- Correlation analysis ----------------------------------------------
    risk_scores = np.array([r["risk_score"] for r in results])
    outcome_failure = np.array([1.0 if r["case"]["outcome_failure"] else 0.0 for r in results])

    failed_scores = risk_scores[outcome_failure == 1]
    succeeded_scores = risk_scores[outcome_failure == 0]
    correlation = float(np.corrcoef(risk_scores, outcome_failure)[0, 1])

    print()
    print("=" * 90)
    print("CORRELATION ANALYSIS")
    print("=" * 90)
    print()
    print("*** SAMPLE SIZE CAVEAT: n=18 is far too small to draw any statistically ***")
    print("*** valid conclusion. The numbers below are exploratory/directional      ***")
    print("*** only -- do not treat this as validating or invalidating              ***")
    print("*** PremortemAnalyzer.                                                   ***")
    print()
    print("*** DOMAIN-FIT CAVEAT: PremortemAnalyzer's own system prompt scopes it   ***")
    print("*** to pre-seed/seed-stage SaaS founders. Most cases below are NOT that  ***")
    print("*** -- post-IPO companies, non-SaaS marketplaces/hardware/media. This    ***")
    print("*** backtest stresses the tool well outside its designed scope.         ***")
    print()
    print(f"n = {len(results)} ({int(outcome_failure.sum())} real-world failures, {int((1 - outcome_failure).sum())} real-world successes)")
    print(f"Mean risk_score | real-world FAILURE cases:  {failed_scores.mean():.2f} (n={len(failed_scores)})")
    print(f"Mean risk_score | real-world SUCCESS cases:  {succeeded_scores.mean():.2f} (n={len(succeeded_scores)})")
    print(f"Point-biserial correlation (risk_score vs. real-world failure): r = {correlation:+.2f}")
    print()
    print("A positive r means PremortemAnalyzer's risk_score tended to be higher for cases that")
    print("really did fail. This is a single, small, non-random, retrospectively-curated sample --")
    print("it is a directional signal for further investigation, not a validated result.")


if __name__ == "__main__":
    main()
