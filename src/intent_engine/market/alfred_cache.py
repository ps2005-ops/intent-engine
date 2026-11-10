"""Resumable, key-addressed acquisition for ALFRED. §3/§4/§5.

WHY THIS EXISTS
---------------
The first acquisition attempt was 2,760 serial requests that wrote nothing
until the very end. It ran for 25 minutes, was interrupted, and every one of
those requests was thrown away. That is not a slow acquisition; it is an
acquisition that cannot be completed by anything that might be interrupted --
which includes every session.

Three fixes, in order of how much they matter:

1. CACHE. `(series_id, vintage_date)` is an IMMUTABLE key. ALFRED's answer to
   "what did PSAVERT look like as of 2008-09-15" does not change. So it is
   written to disk on arrival and never requested twice, across runs, across
   sessions, across crashes.

2. PLAN FROM REVISION BEHAVIOUR, NOT FROM A CALENDAR. Most of these series do
   not revise. UMCSENT, MICH, DFF, DGS2, DGS10, CIVPART and UNRATE returned
   IDENTICAL overlapping values at 2015 and 2024 vintages -- for those, the
   current series IS the vintage-correct history and one request replaces a
   hundred. Only the series that actually revise need a vintage grid.

3. BOUNDED CONCURRENCY. Three at a time, backing off on 429/5xx. Enough to
   finish in minutes, far short of hammering a public service.

WHAT WAS MEASURED, NOT ASSUMED
------------------------------
Revision behaviour is a MEASUREMENT here, not a guess: `probe_revisions`
fetches two distant vintages and compares the overlap. A series is only
declared stable because it was checked, and the check is re-runnable.

THE 404s ARE A FINDING
----------------------
Four series answer at the current vintage and 404 at historical ones:
BOGZ1FL153064486Q, BABATOTALSAUS, USACSCICP02STSAM, BAMLH0A0HYM2. They have
no ALFRED vintage history. Using them as model INPUTS in a replay would leak,
so they are excluded from the walled panel and the exclusion is recorded
rather than silently worked around.
"""
from __future__ import annotations

import concurrent.futures as _cf
import hashlib
import json
import pathlib
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

CONTRACT = "alfred_cache.v1"

_ALFRED = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
_FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_UA = {"User-Agent": "intent-engine research (github.com/intent-engine); "
                     "contact in repository"}

CACHE_DIR = pathlib.Path("reports/panel/cache")
MANIFEST = pathlib.Path("reports/panel/historical_acquisition_manifest.json")

TIMEOUT = 30
CONCURRENCY = 3
MAX_CONCURRENCY = 6
BACKOFF_BASE = 1.5
MAX_RETRIES = 3

# --- how a series behaves under revision -------------------------------------
STABLE = "STABLE"              # never revised; one current fetch is enough
REVISED = "REVISED"            # needs a vintage per forecast origin
NO_VINTAGE_HISTORY = "NO_VINTAGE_HISTORY"   # 404s at historical vintages

#: A series counts as materially revised when BOTH are true: a real share of
#: its overlapping observations changed, AND the largest change is big enough
#: to flip a directional forecast. Two thresholds because either alone is
#: misleading -- CPIAUCSL revises 6% of its points by 0.14%, which is a
#: rounding artefact, and HSN1F revises 4% of its points by 3%, which is a
#: handful of genuine corrections in a long stable series.
MIN_REVISED_FRACTION = 0.05
MIN_REVISED_MAGNITUDE = 0.01


#: THE SHORTCUT, AND WHEN IT IS ALLOWED
#: ------------------------------------
#: A STABLE series is read once at the current vintage and dated by its
#: publication lag. That saves one request per origin and it is a CLAIM: that
#: the value a model would have seen at the origin equals the value we hold
#: today.
#:
#: The claim was being verified over 2015 vs 2024 and then applied to origins
#: back to 1998, which does not follow. Measured:
#:
#:     REVOLSL   2015 vs 2024:   92% of points differ, by at most  0.91%
#:               current vs 1998: 100% of points differ, by at most 105016%
#:
#: The series was redefined between those vintages. Under the two-recent-
#: vintage rule it was STABLE, and every 1998-2010 origin read today's
#: revolving-credit numbers stamped with 1998 release dates. HOUST fails the
#: same check less dramatically (7.7% of points, by up to 4.4%) and is both a
#: base-model input and a forecast target.
#:
#: So the shortcut now needs the revision measurement to COVER the origin
#: window. `shortcut_allowed` takes the widest measurement available and the
#: earliest origin it will be used at, and says no when the two do not meet.
MAX_SHORTCUT_REVISION = 0.01


def shortcut_allowed(profile, *, earliest_origin: str,
                     verified_from: str = "",
                     early_max_relative_change: float = None) -> Tuple[bool, str]:
    """May this series be read from ONE current fetch, dated by its lag?

    `verified_from` is the earliest vintage the series was actually compared
    against; `early_max_relative_change` is what that comparison found.

    Three ways to qualify, in order of strength:

      1. NEVER REVISED -- zero differing observations over the probe span.
         A survey index or a published market rate is issued once. Nothing
         about the origin window can change that.
      2. VERIFIED ACROSS THE WINDOW -- compared against a vintage at or
         before the earliest origin, and the largest change was immaterial.
      3. Neither -> the shortcut is refused and real vintages are required.
    """
    if profile.behaviour == NO_VINTAGE_HISTORY:
        return False, "no vintage history; cannot be a walled input at all"
    if profile.differing == 0 and profile.overlap > 0:
        return True, (f"never revised: 0 of {profile.overlap} overlapping "
                      "observations differ across the probe span")
    if verified_from and verified_from <= earliest_origin:
        mx = (profile.max_relative_change if early_max_relative_change is None
              else early_max_relative_change)
        if mx < MAX_SHORTCUT_REVISION:
            return True, (f"verified against the {verified_from} vintage, "
                          f"which precedes the earliest origin "
                          f"{earliest_origin}; largest change {mx:.4%}")
        return False, (f"verified against {verified_from} and FAILED: "
                       f"largest change {mx:.4%} exceeds "
                       f"{MAX_SHORTCUT_REVISION:.2%}")
    # 2b. IMMATERIAL EVERYWHERE IT COULD BE MEASURED.
    #
    # DGS2 and DGS10 have no vintage before 2015, so clause 2 can never be
    # satisfied for them however long the origin window is. What CAN be
    # measured is that 2 of 9,735 and 1 of 13,327 observations ever differ,
    # by 0.27% and 0.25%. Refusing those would delete the entire rate block
    # from the base model to guard against a revision two orders of magnitude
    # below the threshold, on a series class that is published once and not
    # restated.
    #
    # This is an EXTRAPOLATION and is labelled as one: the reason string says
    # the measurement does not cover the window, so a reader of the manifest
    # can see which series rest on it. HSN1F is the series this clause
    # correctly refuses -- 4.5% of its points move by up to 3.07%.
    frac = profile.differing / max(1, profile.overlap)
    if (profile.overlap > 0 and frac < MIN_REVISED_FRACTION
            and profile.max_relative_change < MAX_SHORTCUT_REVISION):
        return True, (
            f"immaterial where measurable: {profile.differing} of "
            f"{profile.overlap} observations differ, by at most "
            f"{profile.max_relative_change:.4%}. EXTRAPOLATED -- no vintage "
            f"at or before {earliest_origin} exists to verify the window")
    return False, (
        f"revision behaviour was only measured over the probe span "
        f"({profile.differing}/{profile.overlap} differ, up to "
        f"{profile.max_relative_change:.4%}); the earliest origin is "
        f"{earliest_origin} and no vintage at or before it was compared, so "
        f"the shortcut would be an assumption")


class AcquisitionError(RuntimeError):
    """The publisher did not answer usefully after retries."""


class SeriesAbsent(AcquisitionError):
    """This (series, vintage) does not exist and never will.

    Kept distinct from a transport failure because they call for opposite
    responses: a failure should be retried, and an absence should be recorded
    and never requested again. Counting them together is how an acquisition
    reports a 32% failure rate that is actually a 0% failure rate against a
    series set that starts at different dates.
    """


# =============================================================================
# CACHE
# =============================================================================

def cache_key(series_id: str, vintage: str) -> str:
    return f"{series_id}__{vintage or 'current'}"


def cache_path(series_id: str, vintage: str, root: pathlib.Path = None
               ) -> pathlib.Path:
    root = root or CACHE_DIR
    return root / f"{cache_key(series_id, vintage)}.csv"


def absent_path(series_id: str, vintage: str, root: pathlib.Path = None
                ) -> pathlib.Path:
    """Where a KNOWN-ABSENT (series, vintage) is recorded."""
    root = root or CACHE_DIR
    return root / f"{cache_key(series_id, vintage)}.absent"


def known_absent(series_id: str, vintage: str, root: pathlib.Path = None
                 ) -> Optional[str]:
    """Has this exact (series, vintage) already been shown not to exist?

    A 404 is as IMMUTABLE as a 200 here: ALFRED will not start having a
    vintage of JTSQUR from 1998 tomorrow, because JOLTS did not exist in
    1998. Without this, every rerun re-requests hundreds of pairs that are
    permanently absent -- which is the same waste the positive cache exists
    to prevent, in the direction nobody thinks to cache.
    """
    p = absent_path(series_id, vintage, root)
    return p.read_text(encoding="utf-8") if p.exists() else None


def _write_absent(series_id: str, vintage: str, reason: str,
                  root: pathlib.Path = None) -> pathlib.Path:
    p = absent_path(series_id, vintage, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(reason, encoding="utf-8")
    return p


def cached(series_id: str, vintage: str, root: pathlib.Path = None
           ) -> Optional[str]:
    p = cache_path(series_id, vintage, root)
    if p.exists() and p.stat().st_size > 0:
        return p.read_text(encoding="utf-8")
    return None


def _write_cache(series_id: str, vintage: str, body: str,
                 root: pathlib.Path = None) -> pathlib.Path:
    """Atomic: write a temp file and rename.

    A half-written cache entry from an interrupted run would be indistinguish-
    able from a real one, and would poison every later run that trusted it.
    """
    p = cache_path(series_id, vintage, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".csv.part")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(p)
    return p


def content_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


# =============================================================================
# FETCH
# =============================================================================

_rate_lock = threading.Lock()
_last_call = [0.0]
MIN_INTERVAL = 0.12


def _http_get(url: str) -> str:  # pragma: no cover - the live path
    with _rate_lock:
        gap = time.time() - _last_call[0]
        if gap < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - gap)
        _last_call[0] = time.time()
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")


def fetch_one(series_id: str, vintage: str = "", *,
              fetcher: Optional[Callable[[str], str]] = None,
              root: pathlib.Path = None,
              force: bool = False) -> Tuple[str, str]:
    """Return (body, source) where source is 'cache' or 'network'.

    Retries on transient failures with exponential backoff, and gives up
    rather than looping: a 404 is a fact about the series, not a hiccup.
    """
    if not force:
        hit = cached(series_id, vintage, root)
        if hit is not None:
            return hit, "cache"
        gone = known_absent(series_id, vintage, root)
        if gone is not None:
            raise SeriesAbsent(
                f"{series_id}@{vintage or 'current'}: {gone}")
    get = fetcher or _http_get
    url = (f"{_ALFRED}?id={series_id}&vintage_date={vintage}" if vintage
           else f"{_FRED}?id={series_id}")
    last = None
    for attempt in range(MAX_RETRIES):
        try:
            body = get(url)
            if len(body.strip().splitlines()) < 2:
                raise AcquisitionError(f"{series_id}@{vintage or 'current'}: "
                                       "response had no observations")
            _write_cache(series_id, vintage, body, root)
            return body, "network"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                reason = ("HTTP 404 — this series has no vintage at that "
                          "date, which for a series that begins later is a "
                          "fact about the data rather than a failure")
                _write_absent(series_id, vintage, reason, root)
                raise SeriesAbsent(
                    f"{series_id}@{vintage or 'current'}: {reason}") from e
            last = e
        except Exception as e:                              # noqa: BLE001
            last = e
        time.sleep(BACKOFF_BASE ** attempt)
    raise AcquisitionError(
        f"{series_id}@{vintage or 'current'}: {type(last).__name__}: {last}")


# =============================================================================
# REVISION PROBE — the measurement the plan rests on
# =============================================================================

def _parse(body: str) -> Dict[str, float]:
    out = {}
    for line in body.strip().splitlines()[1:]:
        parts = line.split(",")
        if len(parts) >= 2:
            try:
                out[parts[0].strip()] = float(parts[1])
            except ValueError:
                continue
    return out


@dataclass(frozen=True)
class RevisionProfile:
    series_id: str
    behaviour: str
    overlap: int = 0
    differing: int = 0
    max_relative_change: float = 0.0
    note: str = ""

    @property
    def needs_vintages(self) -> bool:
        return self.behaviour == REVISED

    def as_dict(self) -> dict:
        return {"series_id": self.series_id, "behaviour": self.behaviour,
                "overlap": self.overlap, "differing": self.differing,
                "max_relative_change": round(self.max_relative_change, 6),
                "needs_vintages": self.needs_vintages, "note": self.note}


def probe_revisions(series_ids: Sequence[str], *, early: str, late: str,
                    fetcher: Optional[Callable[[str], str]] = None,
                    root: pathlib.Path = None) -> List[RevisionProfile]:
    """Does this series revise? Measured, by fetching two distant vintages.

    This is the whole basis for the request reduction, so it is a measurement
    with recorded numbers rather than a table someone typed from memory.
    """
    out = []
    for sid in series_ids:
        try:
            a = _parse(fetch_one(sid, early, fetcher=fetcher, root=root)[0])
            b = _parse(fetch_one(sid, late, fetcher=fetcher, root=root)[0])
        except AcquisitionError as e:
            out.append(RevisionProfile(
                series_id=sid, behaviour=NO_VINTAGE_HISTORY,
                note=(f"{e}. A series with no vintage history cannot be a "
                      "walled model INPUT: using its current values at a "
                      "historical origin would leak revisions published "
                      "later.")))
            continue
        common = [k for k in a if k in b]
        differing = [k for k in common if abs(a[k] - b[k]) > 1e-9]
        mx = max((abs(b[k] - a[k]) / max(1e-9, abs(a[k])) for k in differing),
                 default=0.0)
        frac = len(differing) / max(1, len(common))
        material = (frac >= MIN_REVISED_FRACTION
                    and mx >= MIN_REVISED_MAGNITUDE)
        out.append(RevisionProfile(
            series_id=sid, behaviour=REVISED if material else STABLE,
            overlap=len(common), differing=len(differing),
            max_relative_change=mx,
            note=("" if material else
                  f"{frac:.1%} of overlapping observations changed, by at "
                  f"most {mx:.2%}; below the thresholds "
                  f"({MIN_REVISED_FRACTION:.0%} / "
                  f"{MIN_REVISED_MAGNITUDE:.0%}), so the current series is "
                  "used as its own vintage history")))
    return out


# =============================================================================
# PLANNER
# =============================================================================

@dataclass(frozen=True)
class Request:
    series_id: str
    vintage: str          # "" means current
    reason: str

    @property
    def key(self) -> str:
        return cache_key(self.series_id, self.vintage)


def plan(profiles: Sequence[RevisionProfile], origins: Sequence[str]
         ) -> Tuple[List[Request], dict]:
    """Only the (series, vintage) pairs the experiment actually needs.

    A STABLE series gets ONE current request. A REVISED series gets one per
    forecast origin. A series with no vintage history gets none and is
    excluded from the walled panel with its reason recorded.
    """
    reqs: List[Request] = []
    excluded: Dict[str, str] = {}
    stable, revised = [], []
    for p in profiles:
        if p.behaviour == NO_VINTAGE_HISTORY:
            excluded[p.series_id] = p.note
            continue
        if p.behaviour == STABLE:
            stable.append(p.series_id)
            reqs.append(Request(p.series_id, "",
                                f"stable: {p.note or 'no revisions measured'}"))
        else:
            revised.append(p.series_id)
            for o in origins:
                reqs.append(Request(
                    p.series_id, o,
                    f"revised: {p.differing}/{p.overlap} observations "
                    f"changed by up to {p.max_relative_change:.2%}"))
    naive = len(profiles) * len(origins)
    return reqs, {
        "requests_planned": len(reqs),
        "requests_naive": naive,
        "reduction": (round(1 - len(reqs) / naive, 4) if naive else 0.0),
        "stable_series": sorted(stable),
        "revised_series": sorted(revised),
        "excluded_series": excluded,
        "origins": len(origins),
    }


# =============================================================================
# EXECUTE
# =============================================================================

def acquire(requests: Sequence[Request], *, concurrency: int = CONCURRENCY,
            fetcher: Optional[Callable[[str], str]] = None,
            root: pathlib.Path = None,
            progress: Optional[Callable[[int, int, int, int], None]] = None
            ) -> dict:
    """Fetch every planned request, skipping anything already cached.

    Resumable by construction: a cached key is never requested, so an
    interrupted run costs only the requests that were in flight.
    """
    concurrency = max(1, min(MAX_CONCURRENCY, concurrency))
    todo = [r for r in requests
            if cached(r.series_id, r.vintage, root) is None
            and known_absent(r.series_id, r.vintage, root) is None]
    already = len(requests) - len(todo)
    done, failed, absent = [], {}, {}
    lock = threading.Lock()

    def work(r: Request):
        try:
            body, source = fetch_one(r.series_id, r.vintage,
                                     fetcher=fetcher, root=root)
            with lock:
                done.append((r, content_hash(body), source))
        except SeriesAbsent as e:
            with lock:
                absent[r.key] = str(e)[:240]
        except Exception as e:                              # noqa: BLE001
            with lock:
                failed[r.key] = f"{type(e).__name__}: {e}"[:240]
        with lock:
            n = len(done) + len(failed) + len(absent)
            if progress and n % 50 == 0:
                progress(len(done), len(failed), already, len(requests))

    if todo:
        with _cf.ThreadPoolExecutor(max_workers=concurrency) as ex:
            list(ex.map(work, todo))

    return {"contract": CONTRACT, "requested": len(requests),
            "already_cached": already, "fetched": len(done),
            "failed": len(failed), "failures": failed,
            # ABSENCES ARE NOT FAILURES. A series that begins in 2001 has no
            # 1998 vintage, and reporting that as a failure makes a clean
            # acquisition look broken.
            "absent": len(absent), "absences": absent,
            "concurrency": concurrency,
            "entries": [{"series_id": r.series_id, "vintage": r.vintage,
                         "content_hash": h, "source": s, "reason": r.reason}
                        for r, h, s in sorted(done, key=lambda x: x[0].key)]}


def write_manifest(payload: dict, path: pathlib.Path = None) -> pathlib.Path:
    dest = path or MANIFEST
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return dest
