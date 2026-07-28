#!/usr/bin/env python3
"""Drive the REAL WebApp guest journey over the REAL network and report what a
reader would actually see.

    python scripts/live_journey.py Sony https://www.sony.com

This is the check the offline suite cannot make: the fixtures decide what the
sites return, so they can prove the experience is right for the pages they
invented and nothing about the pages the deployed service actually gets. Here
the transport is real, so the page printed at the end is the page.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))

from intent_engine.webapp.app import WebApp                     # noqa: E402
from intent_engine.webapp.config import AppConfig               # noqa: E402
from intent_engine.webapp.storage_state import record_boot      # noqa: E402


class Client:
    def __init__(self, app):
        self.app, self.cookie = app, ""

    def request(self, method, path, body=""):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": self.cookie,
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}

        def sr(status, headers):
            out["status"], out["headers"] = status, headers
        payload = b"".join(self.app(env, sr)).decode()
        for key, value in out["headers"]:
            if key == "Set-Cookie" and value.startswith("sid="):
                self.cookie = ("" if "Max-Age=0" in value
                               else value.split(";")[0])
        return out["status"], dict(out["headers"]), payload

    def get(self, path, hops=5):
        status, headers, body = "", {}, ""
        for _ in range(hops):
            status, headers, body = self.request("GET", path)
            if not status.startswith("30") or "Location" not in headers:
                break
            path = headers["Location"]
        return status, body

    def csrf(self):
        sid = self.cookie.split("=", 1)[1] if self.cookie else None
        return self.app.auth.csrf_token(sid)


def visible(html: str) -> str:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("company")
    parser.add_argument("website")
    parser.add_argument("--save-html", default="")
    args = parser.parse_args()

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="live-journey-"))
    record_boot(tmp, boot_id="previous-process-boot")
    config = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                       autorun_sources=True,
                       web_store_path=tmp / "web.jsonl",
                       fi_store_path=tmp / "fi.jsonl",
                       ci_store_path=tmp / "ci.jsonl")
    app = WebApp(config)                       # no transport = REAL network
    client = Client(app)
    client.request("POST", "/demo")

    status, headers, _ = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={client.csrf()}&company_name={args.company}"
        f"&website={args.website}")
    print(f"POST /analyze -> {status}")
    if status.startswith("5"):
        print("HTTP 500 — the run crashed")
        return 1
    if not status.startswith("303"):
        print(visible(_)[:800])
        return 1
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    print(f"run_id = {run_id}")

    pages = {}
    for label, path in (("run", f"/runs/{run_id}"),
                        ("brief", f"/runs/{run_id}/brief"),
                        ("full", f"/runs/{run_id}/full"),
                        ("slides", f"/runs/{run_id}/slides")):
        code, html = client.get(path)
        pages[label] = (code, html)
        print(f"GET {path} -> {code}  ({len(html):,} bytes, "
              f"{len(visible(html)):,} chars visible)")

    report = pages["run"][1]
    text = visible(report)

    if args.save_html:
        pathlib.Path(args.save_html).write_text(report)
        for label, (_code, html) in pages.items():
            pathlib.Path(args.save_html).with_suffix(
                f".{label}.html").write_text(html)

    result = app._results.get(run_id) or {}
    quality = result.get("quality") or {}
    documents = app.ci.store.retrieved(run_id)
    failures = app.ci.store.failures(run_id)
    print(json.dumps({
        "documents": len(documents),
        "failures": len(failures),
        "extraction_modes": sorted({d.get("extraction_mode") or "?"
                                    for d in documents}),
        "quality_outcome": quality.get("outcome"),
        "ingestion_status": result.get("ingestion_status"),
        "may_synthesize": (result.get("readiness") or {}).get(
            "may_synthesize"),
        "has_strategic_report": bool(result.get("strategic_report")),
    }, indent=2))

    lowered = text.lower()
    verdict = {
        "reads as a total failure": any(
            phrase in lowered for phrase in
            ("we could not analyse", "analysis failed",
             "no approved source could be retrieved")),
        "names limited evidence": any(
            phrase in lowered for phrase in
            ("limited", "partial", "not enough evidence",
             "what we could not")),
        "offers next steps": any(
            phrase in lowered for phrase in
            ("you can", "try", "add", "paste", "next")),
    }
    print(json.dumps(verdict, indent=2))
    print("\n--- first 1200 visible characters ---")
    print(text[:1200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
