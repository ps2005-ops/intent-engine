"""Score the pre-registered strengthened economic standard
(docs/engineering/prospect98/ECONOMIC_INTELLIGENCE_STANDARD.md) from rendered X-Rays.

  python3 scripts/prospect98/econ_standard98.py CAPTURE_DIR OUT.json
"""
import collections, glob, json, re, sys

CH = {"market rate": "MARKET_RATE", "policy rate": "POLICY_RATE", "labor": "LABOR", "currency": "CURRENCY",
      "inflation": "INFLATION", "unemployment": "UNEMPLOYMENT", "industrial demand": "INDUSTRIAL_DEMAND",
      "commodity": "COMMODITY"}
SIZE = re.compile(r"\d+(\.\d+)?\s?%|coefficient|elasticity|probability", re.I)


def score(html):
    sec = html[html.find('class="card exposure-map"'):] if 'class="card exposure-map"' in html else ""
    sec = sec[:sec.find("</section>") + 10] if sec else ""
    rows = re.findall(r'<div class="xm-row" data-channel="([A-Z_]*)" data-measured="([01])">(.*?)</div>', sec, re.S)
    why = re.search(r'<p class="k">Why this decision</p>\s*<p[^>]*>(.*?)</p>', html, re.S)
    why = re.sub("<[^>]+>", "", why.group(1)) if why else ""
    named = {CH.get(m) for m in re.findall(r"measured ([a-z ]+?) conditions reach", why)} - {None}
    e1 = bool(rows) and all("<blockquote>" in r[2] or "distinct terms" in r[2] for r in rows)
    measured = {c for c, m, _ in rows if m == "1" and c}
    e2 = bool(measured)
    e3 = bool(named & measured)
    e4 = bool(rows) and all(all(k in r[2] for k in ("Transmission.", "Direction:", "horizon:", "It holds only if",
                                                         "What would show this is wrong.", "Missing to size it:"))
                            for r in rows)
    # Quoted company text is the company's own statement, not a size this
    # system claims (Rapid7's 10-K: "...at 18% of our revenue").
    ours = re.sub(r"<blockquote>.*?</blockquote>", " ", sec, flags=re.S)
    e5 = bool(sec) and not SIZE.search(re.sub("<[^>]+>", " ", ours)) and all(
        ("not measured by this engine" in r[2]) == (r[1] == "0") for r in rows)
    grade = ("PASS" if all((e1, e2, e3, e4, e5)) else "BOUNDED" if (e1 and e4 and e5) else "FAIL")
    return {"grade": grade, "E1": e1, "E2": e2, "E3": e3, "E4": e4, "E5": e5,
            "exposures": len(rows), "measured_channels": sorted(measured), "decision_channels": sorted(named)}


def main():
    out = {}
    for f in sorted(glob.glob(sys.argv[1] + "/*-xray.html")):
        out[f.split("/")[-1][:-10]] = score(open(f).read())
    summ = {"companies": len(out), "grades": dict(collections.Counter(v["grade"] for v in out.values())),
            "criteria_pass": {k: sum(v[k] for v in out.values()) for k in ("E1", "E2", "E3", "E4", "E5")}}
    json.dump({"standard": "docs/engineering/prospect98/ECONOMIC_INTELLIGENCE_STANDARD.md", "summary": summ,
               "companies": out}, open(sys.argv[2], "w"), indent=1)
    print(json.dumps(summ))


if __name__ == "__main__":
    main()
