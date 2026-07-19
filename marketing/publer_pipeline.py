#!/usr/bin/env python3
"""Publer publishing pipeline — DRY-RUN BY DESIGN (deliverable d).

Walls, enforced in code:
- DRY-RUN unless BOTH (a) --real is passed AND (b) the founder-created
  flag file marketing/PUBLISHING_ENABLED exists. The agent never creates
  that file; its absence is the founder's off switch.
- PUBLER_API_KEY is read from intent-engine/.env at call time, only in
  real mode, and is never printed, logged, or copied (docs/TOOLS.md
  decision 2026-07-17). Dry-run never touches the key and makes zero
  network calls.
- Every post payload must carry approval metadata (--approved-by) or the
  pipeline refuses even a dry-run render of it: per-item human approval
  is part of the payload's shape, not an afterthought.

Usage:
  python marketing/publer_pipeline.py --post-file draft.md --approved-by "founder 2026-07-20"
  (real mode additionally requires --real + the flag file; not usable tonight)
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

MARKETING_DIR = Path(__file__).resolve().parent
REPO_ROOT = MARKETING_DIR.parent
FLAG_FILE = MARKETING_DIR / "PUBLISHING_ENABLED"
PUBLER_API_BASE = "https://app.publer.com/api/v1"  # documented base; unused in dry-run
DISPATCH_LOG = MARKETING_DIR / "dispatch_log.jsonl"  # append-only


def build_payload(post_text: str, approved_by: str, networks=None) -> dict:
    if not approved_by or not approved_by.strip():
        raise ValueError("Refusing to build a payload without per-item founder approval (--approved-by).")
    return {
        "text": post_text,
        "networks": networks or [],
        "approved_by": approved_by,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }


def real_mode_permitted(cli_real: bool) -> bool:
    return bool(cli_real and FLAG_FILE.exists())


def dispatch(payload: dict, real: bool = False) -> dict:
    """Dry-run: render + append-only log, zero network, zero key access.
    Real mode: gated twice (flag file + --real); key loaded only here."""
    if not real_mode_permitted(real):
        record = {"mode": "DRY-RUN", "payload": payload}
        with open(DISPATCH_LOG, "a") as fh:
            fh.write(json.dumps(record) + "\n")
        print("DRY-RUN (nothing published; real mode requires --real AND the "
              "founder-created PUBLISHING_ENABLED flag file):")
        print(json.dumps(payload, indent=2))
        return record

    # --- real mode (unreachable until the founder flips the flag) ----------
    import os
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
    api_key = os.environ.get("PUBLER_API_KEY")
    if not api_key:
        raise RuntimeError("PUBLER_API_KEY not found in intent-engine/.env -- not proceeding.")
    # NOTE: intentionally NOT implemented past this point. Wiring the real
    # HTTP call is a founder-gated task that happens only after the flag
    # exists and a first supervised post is approved. Failing loudly here
    # is the wall working, not a bug.
    raise NotImplementedError(
        "Real publishing is not wired yet by design -- first supervised post "
        "is a founder-present task after PUBLISHING_ENABLED exists.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--post-file", required=True, help="Markdown/text file with the approved post content")
    ap.add_argument("--approved-by", required=True, help='Per-item approval stamp, e.g. "founder 2026-07-20"')
    ap.add_argument("--network", action="append", default=[], help="Target network label (repeatable)")
    ap.add_argument("--real", action="store_true", help="Real mode (also requires PUBLISHING_ENABLED flag file)")
    args = ap.parse_args(argv)
    payload = build_payload(Path(args.post_file).read_text(), args.approved_by, args.network)
    dispatch(payload, real=args.real)
    return 0


if __name__ == "__main__":
    sys.exit(main())
