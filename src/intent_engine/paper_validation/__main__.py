"""python -m intent_engine.paper_validation <command>

    fetch       refresh the price caches (keyless Yahoo) for the universe
    replay      historical walk-forward replay -> reports/paper_validation/replay
    register    register forward SHADOW forecasts dated now (no scheduler)
    resolve     resolve forward forecasts whose exit session has completed
    rehearse    build + resolve the backdated REHEARSAL ledger (machinery only)
    learn       run the shadow learning loop over a ledger
    status      ledger states and chain verification

Nothing here submits an order, reads a credential or writes a production
store. Run from the repository root with PYTHONPATH=src.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys

from intent_engine.paper_validation import bars as BR
from intent_engine.paper_validation import macro as M
from intent_engine.paper_validation import universe as U


def load_inputs(*, refresh: bool = False, forward_snapshot=None, log=print):
    etfs = U.etfs()
    companies, refused = U.companies()
    syms = [i.symbol for i in etfs] + [i.symbol for i in companies]
    bars, failed = BR.load(syms, refresh=refresh, log=log)
    if failed:
        log(f"price failures: {failed}")
    companies = [c for c in companies if c.symbol in bars]
    etfs = [e for e in etfs if e.symbol in bars]
    panel, pvint = M.load_panel(forward_snapshot=forward_snapshot)
    from intent_engine.executive import company_profile as CP
    from intent_engine.validation import load
    manifest = load()
    profiles = {c.symbol: CP.profile_for(company_id=c.company_id,
                                         manifest=manifest)
                for c in companies}
    unknown = [s for s, p in profiles.items() if not p.known]
    if unknown:
        raise SystemExit(f"profiles unknown for {unknown}; the manifest "
                         "should classify every company in the universe")
    return {"etfs": etfs, "companies": companies, "refused": refused,
            "bars": bars, "failed": failed, "panel": panel,
            "panel_vintage": pvint, "profiles": profiles}


def cmd_replay(args) -> int:
    from intent_engine.paper_validation import replay as RP
    from intent_engine.paper_validation.protocol import declaration_hash
    inp = load_inputs()
    res = RP.run(bars=inp["bars"], panel=inp["panel"], etfs=inp["etfs"],
                 companies=inp["companies"], profiles=inp["profiles"],
                 through=args.through)
    summ = RP.summarise(res)
    summ["diagnostics"] = RP.diagnose_specification(res)
    summ["inputs"] = {"panel": inp["panel_vintage"],
                      "prices": BR.vintage(inp["bars"]),
                      "refused_companies": inp["refused"],
                      "protocol_hash": declaration_hash()}
    paths = RP.write(res, summ)
    print(json.dumps(paths, indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m intent_engine.paper_validation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.set_defaults(fn=lambda a: (load_inputs(refresh=True), 0)[1])
    r = sub.add_parser("replay")
    r.add_argument("--through", default="")
    r.set_defaults(fn=cmd_replay)
    try:
        from intent_engine.paper_validation import forward as FW
        FW.add_commands(sub, load_inputs)
    except ImportError:                                 # pragma: no cover
        pass
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
