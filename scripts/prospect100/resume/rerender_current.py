"""Resume: re-render the stored Nov 9 runs with the CURRENT code, slides included.

This wraps `scripts/prospect100/rerender_pass.py` and changes only two things:

  * `/slides` is captured too. Round 4 graded presentation FAIL on eight
    companies because `/slides` answered 500, and the original surface list
    never requested it, so it could not have shown the repair.
  * the default states are the original worktree's pass-3 run states, read
    in place. The store itself is COPIED by rerender_pass before the app
    opens it, so the Nov 9 record is never written.

No analysis is run and no model is called: every surface is composed from the
stored evidence by the current code.

Usage (from the worktree root):
  PYTHONPATH=src python scripts/prospect100/resume/rerender_current.py \
      --store ~/ie-prospect100/reports/prospect100_pass3/captures_final_store \
      --states ~/ie-prospect100/reports/prospect100_pass3/s*/state.json \
      --out reports/prospect100_resume/r5_rerender
"""
from __future__ import annotations

import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import rerender_pass  # noqa: E402

rerender_pass.SURFACES = rerender_pass.SURFACES + (("slides", "/slides"),)

if "--states" in sys.argv:
    i = sys.argv.index("--states") + 1
    sys.argv[i] = os.path.expanduser(sys.argv[i])

if __name__ == "__main__":
    raise SystemExit(rerender_pass.main())
