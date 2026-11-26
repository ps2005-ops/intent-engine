"""Run a FROZEN unseen universe through the same journey as prospect-100.

The universe is docs/engineering/prospect100/resume/UNSEEN_UNIVERSE.json, with
its SHA-256 beside it; this refuses to run if the file no longer matches, so a
list edited after seeing results cannot pass as unseen.

These companies are, by construction, not in the curated catalog, so the
product's search usually offers nothing for them. A real visitor then types
the website. Where the product's own autocomplete DOES offer a suggestion
carrying the company's domain, it is used unchanged; otherwise the
submission carries the name and the website's domain exactly as the form
would, and the miss is recorded (autocomplete_found=False) -- never hidden.

  JOURNEY_BASE=http://127.0.0.1:PORT PYTHONPATH=src python \
      scripts/prospect100/resume/unseen_pass.py --out reports/prospect100_resume/unseen/s1
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from urllib.parse import urlparse

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent.parent))

import next40_owner as OWNER  # noqa: E402
import next40_qualification as NQ  # noqa: E402
import public_journey_ten as PJT  # noqa: E402

UNIVERSE = ROOT / "docs/engineering/prospect100/resume/UNSEEN_UNIVERSE.json"


def _verified_universe() -> list:
    want = (UNIVERSE.with_suffix(".sha256").read_text().split()[0])
    got = hashlib.sha256(UNIVERSE.read_bytes()).hexdigest()
    if want != got:
        raise SystemExit("UNSEEN_UNIVERSE.json changed after it was frozen; "
                         "a list edited after seeing results is not unseen")
    return json.loads(UNIVERSE.read_text())["companies"]


def main() -> int:
    out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
    out = out if out.is_absolute() else ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    companies = _verified_universe()
    domains = {c["name"]: (urlparse(c["website"]).hostname or "")
               .removeprefix("www.") for c in companies}
    found = {}
    real = PJT.suggest_live

    def suggest(op, typed):
        rows, took, st = real(op, typed)
        for name, domain in domains.items():
            if typed.strip().lower() != name.lower():
                continue
            hit = [r for r in rows if domain and domain in
                   str(r.get("domain") or "")]
            found[name] = bool(hit)
            if not hit:
                rows = [{"legal_name": name, "common_name": name,
                         "domain": domain, "entity_id": "", "cik": "",
                         "ticker": "", "country": "",
                         "source": "typed website (no suggestion offered)"}]
            else:
                # Matched on the DOMAIN, so identity is already decided; the
                # journey compares catalog ids, which an unseen company has
                # none of by construction.
                rows = [dict(hit[0], entity_id="")]
        return rows, took, st

    PJT.suggest_live = suggest
    order = [(i + 1, c["name"], "", [c["name"]], "UNSEEN")
             for i, c in enumerate(companies)]
    for _n, name, _e, _p, _c in order:
        PJT.PREFIXES[name] = []
    NQ.FORTY = order
    NQ.COHORTS = {"ALL": [r[0] for r in order]}
    NQ.STATE = out / "state.json"
    NQ.ROOT = out
    OWNER.LOCK = out / "owner.json"
    sys.argv = [sys.argv[0], "--cohort", "ALL"]
    rc = NQ.main()
    (out / "autocomplete_found.json").write_text(json.dumps(found, indent=1))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
