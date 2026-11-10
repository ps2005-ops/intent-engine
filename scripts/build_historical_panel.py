"""RETIRED. This script wrote a LEAKED panel over the walled one.

WHAT IT DID
-----------
Two passes: a CURRENT pass fetching every series at today's vintage, and a
VINTAGE pass at a quarterly grid. The current pass stamped each observation
with `available_at = first-of-next-month + publication_lag_days` -- the date
the FIRST print appeared -- while carrying TODAY'S REVISED VALUE.

For a series that does not revise materially, that is correct and is what
`scripts/acquire_panel.py` still does, on the strength of a measured revision
probe. For a series that DOES revise it is the exact leak `market/alfred.py`
exists to prevent, and it is invisible: the cell has an early, plausible
vintage and a wrong value.

MEASURED, NOT ARGUED
--------------------
In the panel this script last wrote:

    PSAVERT 2008-06   vintage 2008-07-31   value 4.6
                      (the 2026 revision; the first print was 2.5)
    INDPRO  2007-12   vintage 2008-01-21   value 102.3803
                      (the 2026 revision; the 2008-02-15 vintage was 114.1268)

Because the stamped release date PRECEDES the first real grid vintage,
`Panel.latest_vintage_of` preferred the leaked cell at every origin between
the release and the next grid date -- a majority of origins.

WHY THE FILE IS KEPT
--------------------
Deleting it would remove the only record of how the walled panel came to be
overwritten by a leaked one, and the answer -- two scripts writing the same
path with different rules -- is the part worth keeping. Running it now
refuses.

THE REPLACEMENT
---------------
`scripts/acquire_panel.py`. It measures revision behaviour first
(`alfred_cache.probe_revisions`), uses a lag-assumed current fetch ONLY for
series measured to be stable, requires real publisher vintages for the rest,
and excludes series with no vintage history entirely rather than guessing.
"""
from __future__ import annotations

import sys

MESSAGE = (
    "scripts/build_historical_panel.py is retired: its current-vintage pass "
    "stamped today's revised values with their original release dates, which "
    "leaks revisions into every walled read of a series that revises. It "
    "overwrote the walled panel once already. Use "
    "scripts/acquire_panel.py, which measures revision behaviour before "
    "deciding whether a lag-assumed cell is legitimate."
)


def main() -> int:
    print(MESSAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
