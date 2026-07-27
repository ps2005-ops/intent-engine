#!/usr/bin/env python
"""Deterministic release checklist for the Executive Intelligence subsystem.

Every item is GREEN only on runtime evidence. None of these count as evidence:
code existing, tests existing, configuration existing, a file existing, a
workflow existing. An item that cannot be proven right now reports UNPROVEN,
never PASS — UNPROVEN is not a failure, it is an honest gap, and it is listed
in the summary so it cannot be mistaken for success.

The local half proves the build; the deployed half proves the deployment.
Neither substitutes for the other: CI installs requirements.txt while the
deployment builds with `pip install -e .`, which is exactly how pypdf came to
be "tested" everywhere and absent in production.

Usage:
    python scripts/release_checklist.py                       # local only
    python scripts/release_checklist.py --base-url URL --expect-commit SHA
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

PASS, FAIL, UNPROVEN = "PASS", "FAIL", "UNPROVEN"


class Checklist:
    def __init__(self):
        self.items: list = []

    def record(self, name, state, detail=""):
        self.items.append({"item": name, "state": state, "detail": detail})
        mark = {PASS: "[x]", FAIL: "[!]", UNPROVEN: "[ ]"}[state]
        print(f"  {mark} {name:<34} {state:<9} {detail}", flush=True)
        return state == PASS

    @property
    def failed(self):
        return [i for i in self.items if i["state"] == FAIL]

    @property
    def unproven(self):
        return [i for i in self.items if i["state"] == UNPROVEN]


def _run(cmd, cwd=REPO, timeout=1800):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout)


def _get(url, timeout=60):
    req = urllib.request.Request(
        url, headers={"User-Agent": "intent-engine-release-checklist/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                                  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


# --- local: does the thing we are about to deploy actually build? -----------

def check_production_parity_build(cl: Checklist, python="python3"):
    """Install EXACTLY as the deployment does — `pip install -e .`, no
    requirements.txt — then import what the deployed process imports.

    This is the check that would have caught pypdf. CI installs
    requirements.txt, so CI can never catch it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        venv = Path(tmp) / "venv"
        r = _run([python, "-m", "venv", str(venv)])
        if r.returncode != 0:
            return cl.record("dependencies install", FAIL,
                             "could not create venv")
        pip, py = venv / "bin" / "pip", venv / "bin" / "python"
        # Modern pip first: a PEP 660 editable install needs it, and the
        # deployment image already has one. Without this the check fails on
        # the local interpreter's bundled pip rather than on the project.
        _run([str(py), "-m", "pip", "install", "--upgrade", "-q", "pip"])
        r = _run([str(pip), "install", "-e", "."])
        if r.returncode != 0:
            # Report the real cause. pip writes an upgrade notice to stderr on
            # success too, so the last stderr line is routinely a red herring.
            err = [ln for ln in (r.stderr + r.stdout).splitlines()
                   if "ERROR" in ln or "error:" in ln]
            return cl.record("dependencies install", FAIL,
                             err[-1] if err else f"pip exit {r.returncode}")
        cl.record("dependencies install", PASS, "pip install -e . (no requirements.txt)")

        probe = (
            "import json;"
            "import intent_engine.webapp.app;"
            "import intent_engine.company_ingestion.service;"
            "import intent_engine.company_ingestion.pdf;"
            "import pypdf;"
            "from intent_engine.company_ingestion.rendering import rendering_enabled;"
            "print(json.dumps({'pypdf': pypdf.__version__,"
            " 'rendering': rendering_enabled()}))"
        )
        r = _run([str(py), "-c", probe])
        if r.returncode != 0:
            last = (r.stderr.strip().splitlines() or ["import failed"])[-1]
            return cl.record("production build succeeds", FAIL, last)
        info = json.loads(r.stdout.strip().splitlines()[-1])
        if info["rendering"]:
            return cl.record("production build succeeds", FAIL,
                             "browser rendering defaults ON")
        return cl.record("production build succeeds", PASS,
                         f"pypdf {info['pypdf']}, rendering off")


def check_declared_deps_pinned(cl: Checklist):
    """A frozen release must build the same way twice. An unpinned range means
    two deploys of one commit can ship different libraries."""
    text = (REPO / "pyproject.toml").read_text()
    block = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.S)
    if not block:
        return cl.record("declared deps pinned", FAIL,
                         "no [project] dependencies declared")
    deps = re.findall(r'"([^"]+)"', block.group(1))
    unpinned = [d for d in deps if "==" not in d]
    if unpinned:
        return cl.record("declared deps pinned", FAIL,
                         f"unpinned: {', '.join(unpinned)}")
    return cl.record("declared deps pinned", PASS, ", ".join(deps))


def check_quality_gate(cl: Checklist):
    suites = ["tests/test_golden_demo_companies.py", "tests/test_golden_baselines.py",
              "tests/test_report_quality_gate.py", "tests/test_evidence_coverage.py",
              "tests/test_pdf_extraction.py", "tests/test_rendering_provider.py"]
    r = _run([sys.executable, "-m", "pytest", *suites, "-q", "-p", "no:cacheprovider"])
    tail = (r.stdout.strip().splitlines() or ["no output"])[-1]
    return cl.record("quality gate passes",
                     PASS if r.returncode == 0 else FAIL, tail)


def check_offline_suite(cl: Checklist):
    r = _run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    tail = (r.stdout.strip().splitlines() or ["no output"])[-1]
    return cl.record("full offline suite", PASS if r.returncode == 0 else FAIL, tail)


# --- deployed: is the running service the thing we just proved? -------------

def check_deployment(cl: Checklist, base_url: str, expect_commit: str | None):
    base = base_url.rstrip("/")

    status, body = _get(f"{base}/healthz")
    cl.record("health endpoint", PASS if status == 200 else FAIL,
              f"HTTP {status}")

    status, body = _get(f"{base}/version")
    if status != 200:
        cl.record("version matches commit", FAIL, f"HTTP {status}")
        live = None
    else:
        info = json.loads(body)
        live = info.get("commit")
        if not expect_commit:
            cl.record("version matches commit", UNPROVEN,
                      f"live {live[:8] if live else '?'}, nothing to compare")
        elif live == expect_commit:
            cl.record("version matches commit", PASS, f"{live[:8]}")
        else:
            cl.record("version matches commit", FAIL,
                      f"live {str(live)[:8]} != expected {expect_commit[:8]}")

    status, body = _get(f"{base}/readyz")
    if status != 200:
        cl.record("readiness + config loaded", FAIL, f"HTTP {status}")
        cl.record("capabilities observed", FAIL, "readyz unavailable")
        return
    ready = json.loads(body)
    cl.record("readiness + config loaded", PASS,
              f"env={ready.get('env')} root={ready.get('runtime_root')}")

    caps = ready.get("capabilities")
    if caps is None:
        cl.record("capabilities observed", UNPROVEN,
                  "deployed build predates capability reporting")
    elif caps.get("pdf_extraction") and caps.get("browser_rendering") is False:
        cl.record("capabilities observed", PASS,
                  "pdf_extraction=true, browser_rendering=false")
    else:
        cl.record("capabilities observed", FAIL, json.dumps(caps))


def check_smoke(cl: Checklist, base_url: str, companies: str, timeout: float):
    sys.path.insert(0, str(REPO / "scripts"))
    from prod_smoke_check import check as smoke_check      # noqa: E402

    results = []
    for domain in [d.strip() for d in companies.split(",") if d.strip()]:
        results.append(smoke_check(base_url, domain, timeout))

    ok = [r for r in results if r["outcome"] == "PASS"]
    detail = "; ".join(f"{r['company']}={r['outcome']}" for r in results)
    cl.record("production smoke test", PASS if len(ok) == len(results) else FAIL,
              detail)

    # A report is not "generated" because a page returned 200 — it must name
    # the company and carry citations that actually resolve.
    generated = [r for r in results
                 if r.get("company_named") and r.get("citation_count")]
    cl.record("production report generated",
              PASS if len(generated) == len(results) else FAIL,
              "; ".join(f"{r['company']}:{r.get('citation_count', 0)} citations"
                        for r in results))

    sampled = sum(r.get("citations_sampled", 0) for r in results)
    resolved = sum(r.get("citations_resolved", 0) for r in results)
    cl.record("citations resolve",
              PASS if sampled and resolved == sampled else FAIL,
              f"{resolved}/{sampled} sampled citations returned 200")

    # PDFs are opportunistic: no golden company has served one. Never green
    # on absence.
    pdfs = sum(1 for r in results if r.get("pdf_seen"))
    cl.record("pdf path exercised in production",
              PASS if pdfs else UNPROVEN,
              "no golden company served a PDF" if not pdfs else f"{pdfs} seen")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url")
    ap.add_argument("--expect-commit")
    ap.add_argument("--companies", default="shopify.com")
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--skip-local", action="store_true")
    ap.add_argument("--skip-suite", action="store_true",
                    help="skip the full offline suite (the slow item)")
    args = ap.parse_args()

    cl = Checklist()
    print("RELEASE CHECKLIST — Executive Intelligence\n")

    if not args.skip_local:
        print("Build (proves what we are about to deploy):")
        check_declared_deps_pinned(cl)
        check_production_parity_build(cl)
        check_quality_gate(cl)
        if not args.skip_suite:
            check_offline_suite(cl)
        print()

    if args.base_url:
        print("Deployment (proves the running service):")
        check_deployment(cl, args.base_url, args.expect_commit)
        check_smoke(cl, args.base_url, args.companies, args.timeout)
        print()
    else:
        cl.record("deployment verified", UNPROVEN, "no --base-url given")
        print()

    print(f"SUMMARY: {len(cl.items) - len(cl.failed) - len(cl.unproven)} pass, "
          f"{len(cl.failed)} fail, {len(cl.unproven)} unproven")
    for i in cl.unproven:
        print(f"  UNPROVEN  {i['item']}: {i['detail']}")
    for i in cl.failed:
        print(f"  FAILED    {i['item']}: {i['detail']}")

    print("\nRELEASE: " + ("BLOCKED" if cl.failed else "CLEAR"))
    return 1 if cl.failed else 0


if __name__ == "__main__":
    sys.exit(main())
