#!/usr/bin/env python3
"""Run a company through the whole six-step product and score what it says.

    python scripts/golden_cycle.py Cloudflare https://www.cloudflare.com \\
        --out reports/golden/cloudflare

WHAT THIS IS FOR
----------------
Five of the last six defects in this product were found by reading the
deployed page rather than by running the suite, and the suite was green
throughout. This closes that gap: it drives the REAL guest journey, captures
the VISIBLE TEXT of every step, runs the defect taxonomy over it and scores
the frozen rubric. What it reports is what a customer would see.

It is not a substitute for reading the pages. It is the thing that makes
reading them worthwhile, because it removes every defect a regular expression
can find before a person spends attention on the ones only a person can.

`--live <base-url>` drives a deployed service over HTTP instead of the local
WSGI app, so the same scoring runs against Render.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

from intent_engine.founder_brief import flow                    # noqa: E402
from intent_engine.product_eval import defect_taxonomy as DT     # noqa: E402
from intent_engine.product_eval import report_rubric as RR       # noqa: E402

STEPS = tuple(s.key for s in flow.STEPS)
EXTRA = ("xray", "evidence", "sources", "brief", "dashboard")


def visible(html: str) -> str:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    for a, b in (("&mdash;", "—"), ("&amp;", "&"), ("&#39;", "'"),
                 ("&#x27;", "'"), ("&quot;", '"'), ("&lt;", "<"),
                 ("&gt;", ">"), ("&nbsp;", " "), ("&hellip;", "…")):
        text = text.replace(a, b)
    return re.sub(r"[ \t]+", " ", text).strip()


class LocalClient:
    """The real WSGI app, in process."""

    def __init__(self, runtime: pathlib.Path):
        from intent_engine.webapp.app import WebApp
        from intent_engine.webapp.config import AppConfig
        from intent_engine.webapp.storage_state import record_boot
        runtime.mkdir(parents=True, exist_ok=True)
        record_boot(runtime, boot_id="previous-process-boot")
        self.app = WebApp(AppConfig(
            env="test", secret="s" * 40, demo_mode=True, autorun_sources=True,
            web_store_path=runtime / "web.jsonl",
            fi_store_path=runtime / "fi.jsonl",
            ci_store_path=runtime / "ci.jsonl"))
        self.cookie = ""

    def request(self, method, path, body=""):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": self.cookie,
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}

        def start(status, headers):
            out["status"], out["headers"] = status, headers
        payload = b"".join(self.app(env, start)).decode()
        for key, value in out["headers"]:
            if key == "Set-Cookie" and value.startswith("sid="):
                self.cookie = ("" if "Max-Age=0" in value
                               else value.split(";")[0])
        return int(out["status"].split()[0]), dict(out["headers"]), payload

    def csrf(self):
        sid = self.cookie.split("=", 1)[1] if self.cookie else None
        return self.app.auth.csrf_token(sid)

    def run_state(self, run_id):
        try:
            return self.app.ci.store.run_state(run_id) or ""
        except Exception:                                   # noqa: BLE001
            return ""


class LiveClient:
    """A deployed service, over HTTP."""

    def __init__(self, base: str, token: str = ""):
        self.base = base.rstrip("/")
        self.cookie = ""
        self.token = token

    def request(self, method, path, body=""):
        url = self.base + path
        data = body.encode() if body else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("User-Agent", "intent-engine-golden-cycle/1.0")
        if self.cookie:
            request.add_header("Cookie", self.cookie)
        if data is not None:
            request.add_header("Content-Type",
                               "application/x-www-form-urlencoded")
        if self.token:
            request.add_header("X-Founder-Intelligence-Smoke-Test", self.token)

        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(request, timeout=180) as response:
                status = response.status
                headers = dict(response.headers.items())
                payload = response.read().decode("utf-8", "replace")
                cookies = response.headers.get_all("Set-Cookie") or []
        except urllib.error.HTTPError as error:
            status = error.code
            headers = dict(error.headers.items())
            payload = error.read().decode("utf-8", "replace")
            cookies = error.headers.get_all("Set-Cookie") or []
        for value in cookies:
            if value.startswith("sid="):
                self.cookie = value.split(";")[0]
        return status, headers, payload

    def csrf(self):
        _s, _h, body = self.request("GET", "/")
        found = re.search(r'name="csrf" value="([^"]+)"', body)
        return found.group(1) if found else ""

    def run_state(self, run_id):
        return ""


def start_run(client, company, website, wait):
    client.request("POST", "/demo")
    # PROPERLY ENCODED. "Johnson & Johnson" with a bare ampersand ends the
    # company_name parameter at "Johnson", so the run analysed a company that
    # does not exist, failed to classify it, and was handed the whole pattern
    # library -- which then described a pharmaceutical company in take-or-pay
    # and order-book language. A browser form encodes this; this harness did
    # not, and the defect it produced looked exactly like a product defect.
    body = ("consent=on"
            f"&csrf={urllib.parse.quote_plus(client.csrf())}"
            f"&company_name={urllib.parse.quote_plus(company)}")
    if website:
        body += f"&website={urllib.parse.quote_plus(website)}"
    status, headers, payload = client.request("POST", "/analyze", body)
    if status != 303 or "Location" not in headers:
        print(f"  analyze -> {status}: {visible(payload)[:300]}")
        return None
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    deadline = time.time() + wait
    while time.time() < deadline:
        status, _h, _b = client.request("GET", f"/runs/{run_id}/intro")
        if status // 100 != 3:
            break
        if client.run_state(run_id) in ("FAILED", "REJECTED", "INTERRUPTED"):
            break
        time.sleep(4)
    return run_id


def fetch(client, run_id, suffix):
    path, chain = f"/runs/{run_id}{suffix}", []
    body, status = "", 0
    for _ in range(6):
        status, headers, body = client.request("GET", path)
        chain.append(f"{path} {status}")
        if status // 100 != 3 or "Location" not in headers:
            break
        path = headers["Location"]
    return status, body, chain


def ask(client, run_id, question):
    body = (f"csrf={client.csrf()}&question="
            + urllib.parse.quote_plus(question))
    status, headers, payload = client.request(
        "POST", f"/runs/{run_id}/conversation", body)
    if status == 303 and "Location" in headers:
        _s, _h, payload = client.request("GET", headers["Location"])
    return visible(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("company")
    parser.add_argument("website", nargs="?", default="")
    parser.add_argument("--out", required=True)
    parser.add_argument("--wait", type=int, default=900)
    parser.add_argument("--live", default="")
    parser.add_argument("--token", default=os.environ.get(
        "FOUNDER_SMOKE_TOKEN", ""))
    parser.add_argument("--model-class", default="")
    parser.add_argument("--ask", default="")
    args = parser.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    client = (LiveClient(args.live, args.token) if args.live
              else LocalClient(out / "_rt"))

    run_id = start_run(client, args.company, args.website, args.wait)
    if run_id is None:
        return 1
    print(f"  run {run_id}")

    pages, chains = {}, {}
    for step in flow.STEPS:
        status, html, chain = fetch(client, run_id, step.suffix)
        text = visible(html)
        pages[step.key] = text
        chains[step.key] = chain
        (out / f"{step.key}.txt").write_text(text)
        (out / f"{step.key}.html").write_text(html)
        print(f"  {step.number}. {step.key:9s} {status} "
              f"{len(text):7,d} chars")
    for extra in EXTRA:
        status, html, chain = fetch(client, run_id, f"/{extra}")
        chains[extra] = chain
        (out / f"{extra}.txt").write_text(visible(html))
        pages.setdefault(f"_{extra}", visible(html))

    if args.ask:
        pages["qa"] = ask(client, run_id, args.ask)
        (out / "qa.txt").write_text(pages["qa"])

    read = timeline = None
    if not args.live:
        try:
            read = client.app._strategic_read(run_id)
            timeline = client.app._history_timeline(
                run_id, read.company if read else args.company)
        except Exception as error:                          # noqa: BLE001
            print(f"  read/timeline unavailable: {error}")

    model_class = args.model_class
    if not model_class and read is not None:
        try:
            from intent_engine.executive.company_profile import profile_for
            model_class = profile_for(
                name=read.company,
                domain=args.website.replace("https://", "").replace(
                    "http://", "").strip("/")).business_model_class
        except Exception:                                   # noqa: BLE001
            model_class = ""

    scored = {k: v for k, v in pages.items() if not k.startswith("_")}
    result = RR.score(read=read or _EmptyRead(args.company), pages=scored,
                      timeline=timeline, company=args.company,
                      model_class=model_class)
    payload = result.as_dict()
    payload["run_id"] = run_id
    payload["chains"] = chains
    payload["model_class"] = model_class
    (out / "score.json").write_text(json.dumps(payload, indent=2))

    print(f"\n  OVERALL {result.overall}/10   MIN-CORE {result.min_core}/10"
          f"   model={model_class or '?'}")
    for row in sorted(result.scores, key=lambda s: s.score):
        flag = "  " if row.score >= 9 else ("!!" if row.score < 8 else " ~")
        print(f"  {flag} {row.dimension:30s} {row.score:4.1f}  {row.why[:70]}")
    if result.findings:
        print("\n  DEFECTS")
        for finding in result.findings:
            print(f"   {finding['severity']:8s} {finding['code']:28s} "
                  f"{finding['surface']:9s} {finding['evidence'][:60]}")
    for line in result.failures():
        print(f"  GATE FAIL: {line}")
    return 0


class _EmptyRead:
    def __init__(self, company):
        self.company = company
        self.puts_a_strategy_forward = False
        self.level1_facts = self.level2_business_model = ()
        self.level3_mechanism = self.level4_competition = ()
        self.macro = self.metrics = ()
        self.level6_action = None


if __name__ == "__main__":
    raise SystemExit(main())
