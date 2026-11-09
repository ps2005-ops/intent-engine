"""Re-render every stored run's surfaces with the CURRENT code. No new analysis.

Pass 3's analyses were run once (reports/prospect100_pass3/s*/state.json, on
93aea2a8). Repairs made after that change how pages are composed and
rendered, not what was retrieved -- so the pages are re-rendered from the
stored runs instead of re-running 95 analyses ("reuse valid cached evidence,
rerun only invalidated analyses").

Works on a COPY of the local store (never the original), builds the app
in-process, and opens each run as its own owner: the anonymous session is
signed with this process's secret by the app's own `_sign_anonymous`, exactly
as a returning guest's cookie would be. Captures are written with the same
names the journey harness uses, so every audit runs on them unchanged.

Usage: PYTHONPATH=src python scripts/prospect100/rerender_pass.py \
    --store DIR --out reports/prospect100_pass3/captures_final
"""
from __future__ import annotations

import glob
import io
import json
import pathlib
import re
import shutil
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent

SURFACES = (("result", ""), ("intro", "/intro"), ("brief", "/brief"),
            ("full", "/full"), ("history", "/history"),
            ("evidence", "/evidence"), ("sources", "/sources"),
            ("story", "/story"), ("xray", "/xray"), ("connect", "/connect"))


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> int:
    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig

    store = pathlib.Path(sys.argv[sys.argv.index("--store") + 1])
    out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
    out.mkdir(parents=True, exist_ok=True)
    work = out.parent / (out.name + "_store")
    # The WHOLE store, minus locks: ownership lives in w.jsonl, the composed
    # state beside it. A copy, so the original run record is never written.
    shutil.copytree(store, work, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*.lock"))
    import os
    os.environ["RUNTIME_ROOT"] = str(work / "runtime")
    os.environ["ACQUISITION_MEMORY_DIR"] = str(work / "acq")
    os.environ["SEC_FILING_CACHE_DIR"] = str(work / "sec")
    owners = {}
    with open(work / "ci.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if '"ci.run_created"' in line:
                row = json.loads(line)
                owners[row["run_id"]] = row["payload"]["user_id"]
    cfg = AppConfig(env="development", secret="r" * 64, demo_mode=True,
                    web_store_path=work / "w.jsonl",
                    fi_store_path=work / "fi.jsonl",
                    ci_store_path=work / "ci.jsonl")
    app = WebApp(cfg)

    rows = []
    for f in sorted(glob.glob(str(ROOT / "reports/prospect100_pass3/s*/state.json"))):
        rows += [r for r in json.loads(pathlib.Path(f).read_text())["rows"].values()
                 if r.get("run_id")]
    index = {}
    for r in sorted(rows, key=lambda r: r.get("n") or 0):
        uid = owners.get(r["run_id"])
        if not uid:
            index[r["company"]] = {"error": "no owner recorded"}
            continue
        csrf = "c" * 43
        expires = time.time() + 3600
        token = app.auth._sign_anonymous(uid, csrf, expires)
        app.auth._sessions[token] = {"user_id": uid, "email": None,
                                     "anonymous": True, "expires": expires,
                                     "csrf": csrf, "analyses": []}
        status = {}
        for surface, suffix in SURFACES:
            environ = {"REQUEST_METHOD": "GET",
                       "PATH_INFO": f"/runs/{r['run_id']}{suffix}",
                       "QUERY_STRING": "", "SERVER_NAME": "127.0.0.1",
                       "SERVER_PORT": "8600", "HTTP_HOST": "127.0.0.1",
                       "wsgi.url_scheme": "http", "HTTP_COOKIE": f"sid={token}",
                       "wsgi.input": io.BytesIO(b"")}
            got = {}

            def start(st, headers, exc_info=None, _g=got):
                _g["status"] = st

            t = time.perf_counter()
            body = b"".join(app(environ, start))
            took = round((time.perf_counter() - t) * 1000)
            code = int(str(got.get("status", "0")).split()[0])
            status[surface] = {"status": code, "ms": took}
            if code == 200:
                (out / f"{_slug(r['company'])}-{surface}.html").write_bytes(body)
        index[r["company"]] = status
        bad = [s for s, v in status.items() if v["status"] != 200]
        print(f"{r['n']:>3} {r['company'][:22]:22s} "
              f"{'OK' if not bad else 'NON-200 ' + ','.join(bad)} "
              f"full={status['full']['ms']}ms", flush=True)
    (out / "index.json").write_text(json.dumps(index, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
