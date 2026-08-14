"""Where the market engine's snapshots are, and whether they are usable.

WHY THIS FILE EXISTS
--------------------
The market engine publishes demo snapshots under ITS runtime root. The
founder web service reads under `RUNTIME_ROOT`, which is its own persistent
disk. Those are two different directories in every deployment that has ever
run, so the founder side looked in a place the market side never writes to,
found nothing, and reported "no market snapshot has been published for this
company" -- a true sentence about the wrong directory.

Twenty-six real snapshots existed on disk while the product showed none of
them. Nothing raised, because a missing snapshot is a legitimate state and
the code was reporting it correctly.

THE CONTRACT
------------
One explicit setting, `MARKET_SNAPSHOT_ROOT`. It is not guessed from the
current working directory, not searched for, and never falls back to a stale
fixture: an unconfigured bridge is MISSING and says so, which an operator can
fix, while a silent fallback is a second system of record that nobody can see.

`assess()` answers the only question a startup check should ask -- can this
deployment read the market engine's output right now, and if not, why -- and
`for_company()` answers it for one company at the moment a dossier is built.

THE STATES ARE NOT INTERCHANGEABLE
----------------------------------
CURRENT   a snapshot exists, parses, is for this company, and is inside the
          freshness window.
MISSING   nothing is published here. Includes the unconfigured root: no
          market engine has ever written to this deployment.
STALE     a real snapshot, correctly formed, whose evidence is older than the
          bounded window. Its content is still shown; its age is stated.
INVALID   something is there and cannot be trusted -- unparseable, a
          contract this side does not read, or filed under another company.
          This is the one state that must never be shown as data.

STALE and INVALID both mean "do not treat this as current", and they call for
opposite repairs: STALE means run the market cycle, INVALID means someone is
writing bytes this side cannot read. Collapsing them into one "not current"
is what turns a contract break into a scheduling question.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
from datetime import date
from typing import Any, Optional

from intent_engine.demo_dossier import transport as _T
from intent_engine.demo_dossier import vocabulary as V
from intent_engine.demo_dossier.contracts import read_market_snapshot

#: The ONE setting. Absent means no market engine feeds this deployment.
ENV_VAR = "MARKET_SNAPSHOT_ROOT"

#: A DECLARED, version-controlled deployment setting. Not a search path.
#:
#: WHY THIS EXISTS AND WHY IT IS NOT A FALLBACK
#: --------------------------------------------
#: `MARKET_SNAPSHOT_ROOT` carries no credential -- its value is a directory --
#: and the preview service is dashboard-configured rather than Blueprint-
#: managed, so the value could only be set by hand. A deployment blocked on a
#: human retyping a non-secret literal is a deployment that stays blocked.
#:
#: The distinction that matters: this file is READ AT A FIXED PATH and states
#: one value. Nothing here searches the working directory, walks parents, or
#: picks a plausible-looking directory -- those are the behaviours the bridge
#: refuses, and they are refused because a guessed root silently serves
#: somebody else's intelligence. A checked-in declaration is reviewable,
#: diffable, and wrong in exactly one visible place if it is wrong.
PREVIEW_CONFIG = ("config", "preview.yaml")
PREVIEW_KEY = "market_snapshot_root"

#: Where the setting came from. On `/readyz`, so an operator can tell a
#: dashboard value from a checked-in one without reading either.
SOURCE_ENV = "ENV"
SOURCE_PREVIEW_CONFIG = "PREVIEW_CONFIG"
SOURCE_MISSING = "MISSING"

CURRENT = "MARKET_BRIDGE_CURRENT"
MISSING = "MARKET_BRIDGE_MISSING"
STALE = "MARKET_BRIDGE_STALE"
INVALID = "MARKET_BRIDGE_INVALID"

STATES = (CURRENT, MISSING, STALE, INVALID)

#: States whose payload may be read as this company's market intelligence.
#: STALE is included deliberately -- its content is real and its age is
#: stated -- and INVALID never is.
USABLE = frozenset({CURRENT, STALE})


class BridgeAssessment:
    """One answer about one bridge. Plain object; it crosses no contract."""

    __slots__ = ("state", "reason", "source_path", "configured",
                 "schema", "company_id", "generated_at", "digest",
                 "freshness_days", "snapshot")

    def __init__(self, state: str, reason: str = "", *, source_path: str = "",
                 configured: bool = False, schema: str = "",
                 company_id: str = "", generated_at: str = "",
                 digest: str = "", freshness_days: Optional[int] = None,
                 snapshot: Any = None):
        self.state = state
        self.reason = reason
        self.source_path = source_path
        self.configured = configured
        self.schema = schema
        self.company_id = company_id
        self.generated_at = generated_at
        self.digest = digest
        self.freshness_days = freshness_days
        self.snapshot = snapshot

    @property
    def usable(self) -> bool:
        return self.state in USABLE

    def as_dict(self) -> dict:
        """What an operator surface shows. The snapshot itself never crosses
        here -- this is the diagnosis, not the payload."""
        return {"state": self.state, "reason": self.reason,
                "source_path": self.source_path, "configured": self.configured,
                "schema": self.schema, "company_id": self.company_id,
                "generated_at": self.generated_at, "digest": self.digest,
                "freshness_days": self.freshness_days}


def _repo_root() -> pathlib.Path:
    """The directory the checked-in config belongs to.

    Derived from THIS FILE's location, not from the working directory: the
    package lives at `<root>/src/intent_engine/demo_dossier/bridge.py`, so the
    root is four parents up. A process started from anywhere resolves the
    same path, which is the property a cwd-relative read does not have.
    """
    return pathlib.Path(__file__).resolve().parents[3]


def _preview_config_root(root: Optional[pathlib.Path] = None):
    """The declared preview root, or None. Reads ONE file at ONE path.

    A relative value is resolved against the repo root rather than the
    working directory. `market_snapshot_root: "."` therefore means "the
    checkout", wherever the service happens to be started from -- on Render
    that is `/opt/render/project/src`, and nothing here needs to know that.

    Parsed with a two-line reader rather than a YAML dependency: the contract
    is one scalar, and adding a package to production for it would be a
    heavier change than the setting it carries.
    """
    path = (root or _repo_root()).joinpath(*PREVIEW_CONFIG)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line.startswith(PREVIEW_KEY):
            continue
        _, _, value = line.partition(":")
        value = value.strip().strip('"').strip("'")
        if not value:
            return None
        declared = pathlib.Path(value).expanduser()
        if declared.is_absolute():
            return declared
        return ((root or _repo_root()) / declared).resolve()
    return None


def configured_root(env=None, config_root=None) -> Optional[pathlib.Path]:
    """The configured market snapshot root, or None. Precedence is strict.

        environment variable  ->  declared preview config  ->  None

    NO CWD GUESSING, NO SEARCH. The environment wins because an operator
    setting it means it; the checked-in declaration is consulted only when
    the environment is silent; and when neither speaks the answer is None,
    which reads as MISSING rather than as a directory somebody guessed.
    """
    env = os.environ if env is None else env
    raw = str(env.get(ENV_VAR) or "").strip()
    if raw:
        return pathlib.Path(raw).expanduser()
    return _preview_config_root(config_root)


def config_source(env=None, config_root=None) -> str:
    """Which of the two declarations supplied the root.

    `config_root` exists so a caller can ask what happens when NEITHER
    source speaks -- the state an operator sees on a deployment that ships
    no declaration. Without it that branch is unreachable from a checkout
    that does ship one, and an unreachable branch is an untested one.
    """
    env = os.environ if env is None else env
    if str(env.get(ENV_VAR) or "").strip():
        return SOURCE_ENV
    return (SOURCE_PREVIEW_CONFIG
            if _preview_config_root(config_root) is not None
            else SOURCE_MISSING)


def _digest(payload: Any) -> str:
    """A semantic digest: the same intelligence digests the same regardless of
    key order or whitespace, so a redeploy that rewrites bytes without
    changing meaning does not read as new market intelligence."""
    import json
    try:
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          default=str)
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _age_days(stamp: str, today: str) -> Optional[int]:
    try:
        a = date.fromisoformat(str(stamp)[:10])
        b = date.fromisoformat(str(today)[:10])
    except (ValueError, TypeError):
        return None
    return (b - a).days


def for_company(company_key: str, *, root=None, env=None, config_root=None,
                aliases=(), today: str = "") -> BridgeAssessment:
    """Assess the bridge for one company. The reading a dossier build uses.

    THE TWO SIDES KEY THE SAME COMPANY DIFFERENTLY, and this is where that
    was found: the founder files a dossier under its manifest id
    (`cloudflare`), and the market publishes under the key derived from the
    legal name (`cloudflare-inc`). Live, that produced
    FOUNDER_AVAILABLE_MARKET_UNAVAILABLE for a company whose market snapshot
    was sitting on disk -- the exact failure `strategic_publish.publish`
    documents as having carried zero dossiers with a full suite passing.

    `aliases` are the OTHER keys this company is legitimately known by, tried
    in the order given. Each candidate is still checked against the snapshot
    filed under THAT key, so trying more keys can never attribute one
    company's intelligence to another -- the identity check is per-candidate,
    not relaxed.

    A MISSING result on the primary key is not returned until every alias has
    been tried, and the reason names the primary, because that is the key an
    operator will look for on disk.
    """
    today = today or date.today().isoformat()
    if aliases:
        first = None
        for candidate in (company_key, *aliases):
            if not candidate:
                continue
            found = for_company(candidate, root=root, env=env,
                                config_root=config_root, today=today)
            if found.usable:
                return found
            if first is None:
                first = found
        return first if first is not None else for_company(
            company_key, root=root, env=env, config_root=config_root,
            today=today)
    resolved = (configured_root(env, config_root) if root is None
                else pathlib.Path(root))
    if resolved is None:
        return BridgeAssessment(
            MISSING, configured=False,
            reason=(f"{ENV_VAR} is not set, so no market engine feeds this "
                    f"deployment. No market intelligence was looked for."))
    path = _T.market_snapshot_path(resolved, company_key)
    if not path.exists():
        return BridgeAssessment(
            MISSING, configured=True, source_path=str(path),
            reason=(f"The market engine has published no snapshot for "
                    f"{company_key!r} under the configured root. Nothing "
                    f"about the market was measured for this company."))
    payload = _T.payload_from_file(path)
    if payload is None:
        return BridgeAssessment(
            INVALID, configured=True, source_path=str(path),
            reason=("A file is published here and could not be read as a "
                    "snapshot. It was not joined."))

    snapshot = read_market_snapshot(payload, expected_company=company_key,
                                    today=today)
    common = {
        "configured": True, "source_path": str(path),
        "schema": str(payload.get("contract_version") or ""),
        "company_id": snapshot.company_id,
        "generated_at": snapshot.generated_at,
        "digest": _digest(payload),
        "freshness_days": _age_days(snapshot.evidence_cutoff or
                                    snapshot.generated_at, today),
    }
    # A refused or incompatible read is the INVALID case, and the reader's own
    # reason is kept: it already names whether this was the wrong company, an
    # unreadable contract or a forbidden field, and restating it here would
    # let the two drift.
    if snapshot.availability in (V.REFUSED, V.INCOMPATIBLE):
        return BridgeAssessment(INVALID, snapshot.reason, snapshot=snapshot,
                                **common)
    if snapshot.availability == V.STALE:
        return BridgeAssessment(
            STALE,
            (snapshot.reason or
             f"The newest market snapshot for this company is older than the "
             f"{V.BOUNDED_WINDOW_DAYS}-day window. Its content is shown and "
             f"its age is stated; it is not current."),
            snapshot=snapshot, **common)
    if snapshot.availability == V.UNAVAILABLE:
        return BridgeAssessment(
            MISSING,
            (snapshot.reason or
             "The market engine published a stated absence for this company."),
            snapshot=snapshot, **common)
    return BridgeAssessment(CURRENT, "", snapshot=snapshot, **common)


def assess(*, root=None, env=None, config_root=None, today: str = "") -> dict:
    """The STARTUP reading: is this deployment wired to a market engine.

    Deliberately cheap -- it counts files and reads one -- because a startup
    check that parses every snapshot would make boot time a function of how
    many companies the market engine has ever published.
    """
    today = today or date.today().isoformat()
    resolved = (configured_root(env, config_root) if root is None
                else pathlib.Path(root))
    source = config_source(env, config_root) if root is None else "EXPLICIT"
    if resolved is None:
        return {"state": MISSING, "configured": False, "root": "",
                "config_source": source, "snapshot_count": 0,
                "reason": (f"Neither {ENV_VAR} nor "
                           f"{'/'.join(PREVIEW_CONFIG)} declares a market "
                           f"snapshot root. This deployment reads no market "
                           f"intelligence; the founder side runs alone, "
                           f"which is a supported configuration.")}
    directory = pathlib.Path(resolved).joinpath(*_T.MARKET_SNAPSHOT_DIR)
    if not directory.is_dir():
        return {"state": MISSING, "configured": True, "root": str(resolved),
                "config_source": source,
                "snapshot_count": 0, "directory": str(directory),
                "reason": (f"{ENV_VAR} is set to {resolved} but no snapshot "
                           f"directory exists under it. Either the market "
                           f"engine has never run here, or the root is "
                           f"wrong -- and those need different repairs.")}
    files = sorted(p for p in directory.glob("*.json") if p.is_file())
    if not files:
        return {"state": MISSING, "configured": True, "root": str(resolved),
                "config_source": source,
                "snapshot_count": 0, "directory": str(directory),
                "reason": ("The configured snapshot directory exists and is "
                           "empty. The market engine has published nothing "
                           "to this deployment.")}
    # Read the NEWEST by content, not by mtime: a redeploy that copies files
    # rewrites every mtime, and a bridge that reads freshness off the
    # filesystem would then call a year-old snapshot current.
    newest, newest_stamp, invalid = None, "", 0
    for path in files:
        payload = _T.payload_from_file(path)
        if not isinstance(payload, dict):
            invalid += 1
            continue
        stamp = str(payload.get("evidence_cutoff")
                    or payload.get("generated_at") or "")
        if stamp > newest_stamp:
            newest, newest_stamp = payload, stamp
    if newest is None:
        return {"state": INVALID, "configured": True, "root": str(resolved),
                "config_source": source,
                "snapshot_count": len(files), "directory": str(directory),
                "invalid_files": invalid,
                "reason": (f"{len(files)} file(s) are published here and none "
                           f"could be read as a snapshot. This is a contract "
                           f"break, not an empty schedule.")}
    age = _age_days(newest_stamp, today)
    state = (STALE if age is not None and age > V.BOUNDED_WINDOW_DAYS
             else CURRENT)
    return {
        "state": state, "configured": True, "root": str(resolved),
        "config_source": source,
        "directory": str(directory), "snapshot_count": len(files),
        "invalid_files": invalid,
        "schema": str(newest.get("contract_version") or ""),
        "generated_at": str(newest.get("generated_at") or ""),
        "evidence_cutoff": newest_stamp, "freshness_days": age,
        "digest": _digest(newest),
        "reason": ("" if state == CURRENT else
                   f"The newest of {len(files)} published snapshots is {age} "
                   f"days old, past the {V.BOUNDED_WINDOW_DAYS}-day window. "
                   f"The market engine is not running on this schedule."),
    }
