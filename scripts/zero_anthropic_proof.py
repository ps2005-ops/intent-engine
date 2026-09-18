#!/usr/bin/env python3
"""Prove the whole six-step product completes with NO hosted model available.

    python scripts/zero_anthropic_proof.py Cloudflare https://www.cloudflare.com

REQUIRED_ANTHROPIC_CALLS = 0 is not a configuration claim; it is a property
that has to be demonstrated against the code the deployment serves. So this
does two things at once, and both matter:

  1. removes every credential from the environment, so nothing can construct
     a client from a key it found lying around; and
  2. replaces the `anthropic` module with one whose every entry point RAISES,
     so a code path that tries anyway fails loudly rather than degrading
     quietly into a silent fallback nobody notices.

Then it drives the real guest journey and requires every step of the six to
render. A step that 500s under (2) is a step that needed a model.

The hosted preview cannot serve this half: its key is set and the Render CLI
has no way to unset an environment variable. So "absent" is proven here,
against the same code the preview serves, and "completes" is proven there.
"""
from __future__ import annotations

import argparse
import io
import os
import pathlib
import re
import sys
import time
import types
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

CALLS = []


def _forbid(*_args, **_kwargs):
    CALLS.append("".join(str(a)[:40] for a in _args))
    raise AssertionError(
        "a hosted model client was constructed on the required path")


def _poison() -> None:
    """Remove the credentials, then make the library itself unusable."""
    for key in list(os.environ):
        if "ANTHROPIC" in key.upper() or key.upper().endswith("_API_KEY"):
            os.environ.pop(key, None)
    module = types.ModuleType("anthropic")
    for name in ("Anthropic", "Client", "AsyncAnthropic", "AnthropicBedrock",
                 "AnthropicVertex"):
        setattr(module, name, _forbid)
    module.__getattr__ = lambda _n: _forbid          # type: ignore[attr-defined]
    sys.modules["anthropic"] = module


_poison()

from intent_engine.founder_brief import flow                    # noqa: E402
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

    def get(self, path, hops=5):
        status, body = 0, ""
        for _ in range(hops):
            status, headers, body = self.request("GET", path)
            if status // 100 != 3 or "Location" not in headers:
                break
            path = headers["Location"]
        return status, body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("company")
    parser.add_argument("website", nargs="?", default="")
    parser.add_argument("--wait", type=int, default=900)
    args = parser.parse_args()

    import tempfile
    runtime = pathlib.Path(tempfile.mkdtemp(prefix="zero-anthropic-"))
    record_boot(runtime, boot_id="previous-process-boot")
    app = WebApp(AppConfig(env="test", secret="s" * 40, demo_mode=True,
                           autorun_sources=True,
                           web_store_path=runtime / "web.jsonl",
                           fi_store_path=runtime / "fi.jsonl",
                           ci_store_path=runtime / "ci.jsonl"))
    client = Client(app)
    client.request("POST", "/demo")
    body = ("consent=on"
            f"&csrf={urllib.parse.quote_plus(client.csrf())}"
            f"&company_name={urllib.parse.quote_plus(args.company)}")
    if args.website:
        body += f"&website={urllib.parse.quote_plus(args.website)}"
    status, headers, payload = client.request("POST", "/analyze", body)
    if status != 303:
        print(f"FAIL: /analyze -> {status}")
        return 1
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    print(f"run {run_id} — no credential, and `anthropic` raises on import use")

    # WAIT FOR THE ANALYSIS, NOT FOR A 200. The progress page is a 200, and
    # following the redirect chain to it satisfied `code == 200` on the first
    # poll -- so this proof fetched six copies of "Reading the public
    # evidence…", called them rendered, and reported PASS on a run that had
    # not finished. The only honest signal is a DIRECT 200 at /intro.
    deadline = time.time() + args.wait
    while time.time() < deadline:
        code, _headers, _body = client.request("GET", f"/runs/{run_id}/intro")
        if code == 200:
            break
        time.sleep(4)
    else:
        print(f"FAIL: the run did not finish within {args.wait}s")
        return 1

    failures = []
    for step in flow.STEPS:
        code, _headers, html = client.request(
            "GET", f"/runs/{run_id}{step.suffix}")
        text = re.sub(r"(?s)<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        title = re.search(r"<title>(.*?)</title>", html)
        ok = (code == 200 and len(text) > 400
              and "Reading the public evidence" not in text)
        print(f"  {step.number}. {step.key:9s} {code} {len(text):7,d} chars"
              f"  {'ok' if ok else 'FAIL'}  "
              f"{title.group(1)[:46] if title else '?'}")
        if not ok:
            failures.append(step.key)
    for extra in ("xray", "evidence", "sources", "brief", "answer"):
        code, html = client.get(f"/runs/{run_id}/{extra}")
        if code != 200:
            failures.append(extra)
        print(f"  + {extra:9s} {code}")
    code, html = client.request(
        "POST", f"/runs/{run_id}/conversation",
        f"csrf={urllib.parse.quote_plus(client.csrf())}"
        f"&question={urllib.parse.quote_plus('What proves this wrong?')}")[0:2]
    print(f"  + Q&A       {code}")
    if code not in (200, 303):
        failures.append("qa")

    print()
    print(f"REQUIRED_ANTHROPIC_CALLS = {len(CALLS)}")
    if failures:
        print(f"FAIL: {failures}")
        return 1
    if CALLS:
        print(f"FAIL: a client was constructed: {CALLS[:3]}")
        return 1
    print("PASS — every required surface rendered with no hosted model "
          "available")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
