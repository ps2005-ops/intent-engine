"""V1.1 recorded-source fixture — static saved pages representing a real
retrieval workflow. The suite never touches the network. Contains, by
construction: homepage, product, about, pricing, case study, blog,
careers, one external excerpt (pasted at test time), one failed source,
one redirect, one stale page, one conflicting signal (homepage vs case
study emphasis)."""
import urllib.error

DOMAIN = "brightlake-example.com"
BASE = f"https://{DOMAIN}"

PAGES = {
    BASE: (200, {"content-type": "text/html"}, f"""
<html><head><title>Brightlake — customer onboarding platform</title>
<meta name="description" content="Brightlake helps B2B software companies automate customer onboarding and speed up time to value.">
<link rel="canonical" href="{BASE}/"></head><body>
<h1>Automate onboarding, accelerate revenue</h1>
<p>Brightlake is built for customer success teams at growing software companies.</p>
<p>Faster onboarding, less manual work, more automation.</p>
<a href="/product">Product</a><a href="/pricing">Pricing</a>
<a href="/about">About</a><a href="/customers">Customers</a>
<a href="/blog">Blog</a><a href="/careers">Careers</a>
<a href="/missing">Old page</a>
<script>analytics()</script></body></html>"""),
    f"{BASE}/product": (200, {"content-type": "text/html"}, """
<html><head><title>Product — Brightlake</title></head><body>
<h1>Onboarding workflows</h1>
<p>Checklists, automation rules, customer portals, and progress tracking.</p>
</body></html>"""),
    f"{BASE}/pricing": (200, {"content-type": "text/html"}, """
<html><head><title>Pricing — Brightlake</title></head><body>
<h1>Plans</h1><p>Growth and Scale plans, per seat, billed annually.</p>
</body></html>"""),
    f"{BASE}/about": (200, {"content-type": "text/html"}, """
<html><head><title>About — Brightlake</title></head><body>
<p>Founded in 2021 to make onboarding reliable for software teams.</p>
</body></html>"""),
    # conflicting signal: case study emphasizes retention/implementation,
    # not the homepage's speed/automation language
    f"{BASE}/customers": (200, {"content-type": "text/html"}, """
<html><head><title>Customer stories — Brightlake</title></head><body>
<h2>Meridian Software</h2>
<p>Meridian reduced churn and improved retention by giving implementation
teams accountability and visibility during handoffs.</p>
</body></html>"""),
    # stale page: modified long ago
    f"{BASE}/blog": (200, {"content-type": "text/html"}, """
<html><head><title>Blog — Brightlake</title>
<meta property="article:modified_time" content="2024-01-15T00:00:00+00:00">
</head><body><h2>Onboarding benchmarks</h2>
<p>Our 2024 survey of onboarding practices.</p></body></html>"""),
    f"{BASE}/careers": (200, {"content-type": "text/html"}, """
<html><head><title>Careers — Brightlake</title></head><body>
<p>Hiring customer success engineers and implementation specialists.</p>
</body></html>"""),
}

REDIRECTS = {f"{BASE}/product-old": f"{BASE}/product"}
FAILING = {f"{BASE}/missing": 404}

EXTERNAL_EXCERPT = ("Setup took an afternoon and the implementation team "
                    "loved the visibility; retention of new accounts "
                    "improved and support tickets dropped.")


def transport(url, timeout):
    """Deterministic fake transport with one redirect and one failure."""
    if url in REDIRECTS:
        raise urllib.error.HTTPError(
            url, 301, "moved",
            __import__("email").message_from_string(
                f"Location: {REDIRECTS[url]}\n"), None)
    if url in FAILING:
        raise urllib.error.HTTPError(url, FAILING[url], "not found",
                                     __import__("email")
                                     .message_from_string(""), None)
    if url in PAGES:
        status, headers, body = PAGES[url]
        return (status, headers, body.encode(), False)
    raise urllib.error.HTTPError(url, 404, "not found",
                                 __import__("email").message_from_string(""),
                                 None)
