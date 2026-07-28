"""Retrieval tracing — what actually happened to every URL we touched.

WHY THIS EXISTS
---------------
The offline fixture suite proves the pipeline *can* produce a good report. It
cannot tell us why the deployed service produces a worse one, because the
fixtures are hand-written pages that serve their content the way the parser
already reads it. Live sites do not.

When live and offline diverge, the interesting question is never "did it fail"
— the event store already answers that — but "at which stage was the
information discarded, and was it ever there at all". Answering it requires
observations the ordinary pipeline throws away as soon as it has made its
decision: the redirect chain, the robots policy in force, the declared MIME,
how many bytes arrived, which parser ran, how much text it recovered, and
whether that text was recovered from the document body or scraped out of
metadata as a last resort.

This module records exactly that, as an ordinary Python object attached to a
run. It changes no decision: a traced fetch and an untraced fetch return the
same result. Tracing is off unless a caller asks for it.

Nothing here bypasses anything. It observes the same requests the pipeline
would have made anyway.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from urllib.parse import urlparse

TRACE_VERSION = "ci_trace.v1"

# How text was recovered from a document — the single most diagnostic field in
# the whole trace, because "we fetched 692 KB and admitted 120 characters" is
# invisible in every other record we keep.
EXTRACT_BODY = "body"            # real block-level text from the document
EXTRACT_METADATA = "metadata"    # salvage only: title/OpenGraph/JSON-LD
EXTRACT_STRUCTURED = "structured"  # server-rendered state (e.g. __NEXT_DATA__)
EXTRACT_NONE = "none"            # nothing usable at all


@dataclass
class SourceTrace:
    """One URL, from discovery to whatever became of it."""

    discovered_url: str
    canonical_url: str = ""
    evidence_family: str = ""
    discovery_method: str = ""
    source_class: str = ""

    # transport
    redirects: list = field(default_factory=list)
    final_url: str = ""
    status_code: int | None = None
    mime_type: str = ""
    bytes_received: int = 0
    elapsed_ms: int = 0
    timed_out: bool = False
    timeout_budget_s: float = 0.0

    # policy
    robots_checked: bool = False
    robots_allowed: bool | None = None
    robots_rule: str = ""

    # parsing / extraction
    parser: str = ""
    extraction_mode: str = ""
    extracted_chars: int = 0
    extraction_ok: bool = False

    # outcome
    admitted: bool = False
    rejected_reason: str = ""
    quality_score: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)


class RetrievalTrace:
    """Collects SourceTrace rows for one run. Ordinary object; no I/O."""

    def __init__(self, *, run_id: str = "", label: str = ""):
        self.run_id = run_id
        self.label = label
        self.started_at = time.time()
        self._rows: dict = {}
        self.robots: dict = {}          # host -> {'allowed': [...], ...}

    # -- recording ---------------------------------------------------------
    def row(self, url: str) -> SourceTrace:
        """The row for ``url``, created on first use. Rows are keyed by the
        URL as discovered, so a redirect chain stays attached to the URL the
        pipeline actually proposed."""
        if url not in self._rows:
            self._rows[url] = SourceTrace(discovered_url=url)
        return self._rows[url]

    def note_robots(self, host: str, *, allowed: bool, rule: str = "",
                    reachable: bool = True) -> None:
        self.robots[host] = {"allowed": allowed, "rule": rule,
                             "reachable": reachable}

    def apply_robots(self, url: str) -> None:
        """Attach the host's robots verdict to a row (call after note_robots)."""
        host = urlparse(url).hostname or ""
        verdict = self.robots.get(host)
        if verdict is None:
            return
        row = self.row(url)
        row.robots_checked = True
        row.robots_allowed = verdict["allowed"]
        row.robots_rule = verdict["rule"]

    # -- transport wrapper --------------------------------------------------
    def transport(self, inner=None):
        """Wrap a transport so every HTTP hop is recorded.

        The returned callable has the transport contract exactly:
        ``(url, timeout) -> (status, headers, body, exceeded)``. It records
        what it saw and re-raises anything the inner transport raised, so the
        pipeline's behaviour is bit-for-bit unchanged.
        """
        import urllib.error

        from intent_engine.company_ingestion.fetch import _default_transport

        inner = inner or _default_transport
        origin = {"url": None}

        def traced(url: str, timeout: float):
            # The first hop of a chain owns the row; later hops append to it.
            if origin["url"] is None or not self._is_hop(origin["url"], url):
                origin["url"] = url
            row = self.row(origin["url"])
            row.timeout_budget_s = float(timeout)
            started = time.time()
            try:
                status, headers, body, exceeded = inner(url, timeout)
            except urllib.error.HTTPError as exc:
                row.elapsed_ms += int((time.time() - started) * 1000)
                row.status_code = exc.code
                location = exc.headers.get("Location") if exc.headers else None
                if exc.code in (301, 302, 303, 307, 308) and location:
                    row.redirects.append({"from": url, "to": location,
                                          "status": exc.code})
                    self._pending_hop = location
                else:
                    row.final_url = url
                    row.rejected_reason = f"http_status:{exc.code}"
                raise
            except (TimeoutError,) as exc:
                row.elapsed_ms += int((time.time() - started) * 1000)
                row.timed_out = True
                row.final_url = url
                row.rejected_reason = f"timeout:{str(exc)[:80]}"
                raise
            except Exception as exc:                        # noqa: BLE001
                row.elapsed_ms += int((time.time() - started) * 1000)
                text = str(exc).lower()
                row.timed_out = "timed out" in text
                row.final_url = url
                row.rejected_reason = (
                    f"{'timeout' if row.timed_out else 'connection'}:"
                    f"{str(exc)[:80]}")
                raise
            row.elapsed_ms += int((time.time() - started) * 1000)
            row.status_code = status
            row.final_url = url
            row.bytes_received = len(body or b"")
            row.mime_type = ((headers.get("content-type") or "")
                             .split(";")[0].strip())
            if exceeded:
                row.rejected_reason = "too_large"
            return status, headers, body, exceeded

        self._pending_hop = None
        return traced

    def _is_hop(self, origin_url: str, url: str) -> bool:
        """True when ``url`` continues the chain that began at ``origin_url``."""
        row = self._rows.get(origin_url)
        if row is None:
            return False
        if url == origin_url:
            return True
        return any(hop.get("to") == url or
                   (hop.get("to") or "").rstrip("/") == url.rstrip("/")
                   for hop in row.redirects)

    # -- parse/extraction ---------------------------------------------------
    def note_parse(self, url: str, parsed: dict, *, parser: str = "",
                   canonical: str = "") -> None:
        """Record what the parser recovered, and — crucially — from where."""
        row = self.row(url)
        row.parser = parser or parsed.get("parser_version", "")
        row.canonical_url = canonical or (parsed.get("canonical_url") or "")
        text = parsed.get("text") or ""
        row.extracted_chars = len(text)
        row.extraction_mode = parsed.get("extraction_mode") or (
            EXTRACT_BODY if parsed.get("blocks_found") else
            (EXTRACT_METADATA if text.strip() else EXTRACT_NONE))
        row.extraction_ok = bool(text.strip())

    def note_admitted(self, url: str, *, family: str = "",
                      quality: float | None = None) -> None:
        row = self.row(url)
        row.admitted = True
        if family:
            row.evidence_family = family
        if quality is not None:
            row.quality_score = quality

    def note_rejected(self, url: str, reason: str) -> None:
        row = self.row(url)
        row.admitted = False
        row.rejected_reason = reason

    def note_candidate(self, url: str, *, family: str = "",
                       discovery_method: str = "",
                       source_class: str = "") -> None:
        row = self.row(url)
        row.evidence_family = family or row.evidence_family
        row.discovery_method = discovery_method or row.discovery_method
        row.source_class = source_class or row.source_class

    # -- output -------------------------------------------------------------
    @property
    def rows(self) -> list:
        return list(self._rows.values())

    def as_dict(self) -> dict:
        rows = self.rows
        admitted = [r for r in rows if r.admitted]
        return {
            "trace_version": TRACE_VERSION,
            "run_id": self.run_id,
            "label": self.label,
            "elapsed_s": round(time.time() - self.started_at, 2),
            "robots": self.robots,
            "totals": {
                "urls_touched": len(rows),
                "http_ok": sum(1 for r in rows
                               if r.status_code and 200 <= r.status_code < 300),
                "admitted": len(admitted),
                "bytes_received": sum(r.bytes_received for r in rows),
                "chars_extracted": sum(r.extracted_chars for r in rows),
                "metadata_only_admissions": sum(
                    1 for r in admitted
                    if r.extraction_mode == EXTRACT_METADATA),
            },
            "sources": [r.as_dict() for r in rows],
        }

    def to_json(self, *, indent=2) -> str:
        return json.dumps(self.as_dict(), indent=indent, sort_keys=True)

    def table(self) -> str:
        """A compact operator-readable view: one line per URL."""
        lines = [f"{'status':>6} {'bytes':>8} {'chars':>7} {'mode':<10} "
                 f"{'family':<12} url / reason"]
        for row in sorted(self.rows, key=lambda r: r.discovered_url):
            status = row.status_code if row.status_code is not None else "-"
            tail = row.discovered_url
            if row.rejected_reason:
                tail += f"   [{row.rejected_reason}]"
            lines.append(
                f"{status:>6} {row.bytes_received:>8} {row.extracted_chars:>7} "
                f"{(row.extraction_mode or '-'):<10} "
                f"{(row.evidence_family or '-'):<12} {tail}")
        return "\n".join(lines)
