"""Content cache for SEC filing documents, keyed on the FILING's identity.

WHY. The 60-company validation programme reads the same statutory documents
over and over: a second iteration of one company, a repeat validation run, and
every cross-company mention analysis all re-request filings that have not
changed since they were filed. A 10-K is immutable by construction — it is a
dated, accession-numbered document that SEC will never revise in place — so
re-fetching it is pure cost to us and pure load on a host that has already
answered 429 to this product.

THE KEY IS THE FILING, NOT THE URL. Keying on the URL string looked equivalent
and is not: the same document is reachable under more than one spelling (case,
scheme, a trailing query), and two DIFFERENT documents differ only in a path
segment. The cache therefore parses the EDGAR archive path into its attested
identity — (CIK, accession, document) — and refuses to cache anything whose
identity it cannot read. A URL that is not an EDGAR archive document is a
CACHE_BYPASS, never a guessed key.

WHAT IS CACHED, AND WHAT MUST NEVER BE. Cached: the retrieved bytes, the MIME
type, the HTTP status, whether the read was truncated, a content hash, the
source URL, and when it was retrieved. NOT cached, ever: how a document
relates to a focal company, whether it is relevant to that company, whether a
name in it is a competitor, or any strategic conclusion. Those are functions
of (document, focal company) and the whole point of reading one filing for
several companies is that they come out different. The cache sits BEFORE
parsing and interpretation for exactly that reason.

TENANCY. Every byte here is a public document published by a public
regulator, addressed by its public accession number. The key contains no
run id, no tenant, no company the caller was analysing — so one tenant can
never learn from the cache what another tenant asked about, and a guard test
holds the key surface to that.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

#: Cache outcomes, instrumented so a run can say what the cache did for it.
CACHE_HIT = "CACHE_HIT"
CACHE_MISS = "CACHE_MISS"
CACHE_BYPASS = "CACHE_BYPASS"      # not a cacheable identity (not EDGAR)
CACHE_INVALID = "CACHE_INVALID"    # stored entry unreadable / hash mismatch

DEFAULT_CACHE_DIR = Path("data/cache/sec_filings")

_CIK_RE = re.compile(r"^\d{1,10}$")
_ACCESSION_RE = re.compile(r"^\d{18}$")
_DOC_RE = re.compile(r"^[A-Za-z0-9._\-]{1,120}$")


def filing_identity(url: str):
    """(cik, accession, document) for an EDGAR archive document, else None.

    Deliberately strict. A partial match — an index page, a directory, a
    malformed accession — returns None and the caller bypasses the cache,
    because a key we had to guess at is a key that can collide.
    """
    try:
        parsed = urlparse(url or "")
    except Exception:                                       # noqa: BLE001
        return None
    host = (parsed.hostname or "").lower()
    if host not in ("www.sec.gov", "sec.gov"):
        return None
    parts = [p for p in (parsed.path or "").split("/") if p]
    # /Archives/edgar/data/<cik>/<accession_nodash>/<document>
    if len(parts) != 6:
        return None
    if [p.lower() for p in parts[:3]] != ["archives", "edgar", "data"]:
        return None
    cik, accession, document = parts[3], parts[4], parts[5]
    if not (_CIK_RE.match(cik) and _ACCESSION_RE.match(accession)
            and _DOC_RE.match(document)):
        return None
    if document in (".", ".."):
        return None
    return cik.lstrip("0") or "0", accession, document


def cache_dir() -> Path:
    return Path(os.environ.get("SEC_FILING_CACHE_DIR")
                or DEFAULT_CACHE_DIR)


class FilingCache:
    """Disk-backed store of retrieved SEC filing documents.

    Fully defensive: any storage failure degrades to a miss and a network
    read. A cache that can break a run is worse than no cache.
    """

    def __init__(self, root=None, *, enabled: bool = True, clock=None):
        self.root = Path(root) if root is not None else cache_dir()
        self.enabled = enabled
        self._clock = clock or time.time
        self.counters = {CACHE_HIT: 0, CACHE_MISS: 0,
                         CACHE_BYPASS: 0, CACHE_INVALID: 0}

    # --- identity -------------------------------------------------------
    def _paths(self, identity):
        cik, accession, document = identity
        base = self.root / cik / accession
        return base / document, base / (document + ".meta.json")

    # --- reads ----------------------------------------------------------
    def get(self, url: str):
        """(outcome, entry_or_None). ``entry`` carries body/mime/status."""
        identity = filing_identity(url)
        if identity is None or not self.enabled:
            self.counters[CACHE_BYPASS] += 1
            return CACHE_BYPASS, None
        body_path, meta_path = self._paths(identity)
        if not (body_path.exists() and meta_path.exists()):
            self.counters[CACHE_MISS] += 1
            return CACHE_MISS, None
        try:
            meta = json.loads(meta_path.read_text("utf-8"))
            raw = body_path.read_bytes()
        except Exception:                                   # noqa: BLE001
            self.counters[CACHE_INVALID] += 1
            return CACHE_INVALID, None
        # THE HASH IS CHECKED, NOT TRUSTED. A half-written entry from an
        # interrupted run would otherwise be served as a complete filing,
        # and a truncated filing presented as whole is the one thing the
        # retrieval contract most needs to be true.
        if meta.get("content_hash") != hashlib.sha256(raw).hexdigest():
            self.counters[CACHE_INVALID] += 1
            return CACHE_INVALID, None
        self.counters[CACHE_HIT] += 1
        return CACHE_HIT, {
            "body": raw,
            "mime_type": meta.get("mime_type", ""),
            "status_code": meta.get("status_code", 200),
            "truncated": bool(meta.get("truncated", False)),
            "content_hash": meta.get("content_hash", ""),
            "source_url": meta.get("source_url", url),
            "retrieved_at": meta.get("retrieved_at", ""),
            "cik": identity[0], "accession": identity[1],
            "document": identity[2],
        }

    # --- writes ---------------------------------------------------------
    def put(self, url: str, *, body, mime_type="", status_code=200,
            truncated=False) -> bool:
        identity = filing_identity(url)
        if identity is None or not self.enabled:
            return False
        raw = body if isinstance(body, bytes) else str(body).encode("utf-8")
        body_path, meta_path = self._paths(identity)
        try:
            body_path.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256(raw).hexdigest()
            # Body first, metadata second: an interruption between the two
            # leaves an entry with no metadata, which reads as a MISS. The
            # other order would leave metadata pointing at absent bytes.
            tmp = body_path.with_suffix(body_path.suffix + ".part")
            tmp.write_bytes(raw)
            tmp.replace(body_path)
            meta_path.write_text(json.dumps({
                "cik": identity[0], "accession": identity[1],
                "document": identity[2],
                "source_url": url, "mime_type": mime_type,
                "status_code": status_code, "truncated": bool(truncated),
                "content_hash": digest, "bytes": len(raw),
                "retrieved_at": _iso(self._clock()),
            }, indent=2), "utf-8")
        except Exception:                                   # noqa: BLE001
            return False
        return True

    def snapshot(self) -> dict:
        return dict(self.counters)


def _iso(epoch: float) -> str:
    import datetime
    return datetime.datetime.utcfromtimestamp(
        float(epoch)).replace(microsecond=0).isoformat() + "Z"
