"""Secure configuration preflight — item 7.

Reports whether each credential the platform needs is configured, WITHOUT
ever reading, logging, returning, or echoing the secret value. Only the
env-var NAME and a coarse status leave this module. A missing/invalid
required key produces a persistent `config.preflight_failed` event and a
visible health status — never a silent empty day.

Statuses:
    configured        present and passes a coarse format sanity check
    missing           env var absent or empty
    invalid_format    present but fails the sanity check (likely a paste error)
    unprobed          present; not live-probed (no network probe run here)

A live probe (network call to confirm the key works / is not rate-limited)
is intentionally NOT done here: preflight is credential-independent and safe
to run anywhere, including tests and the sandbox. A job may separately
record `rate_limited` / `unavailable` when a real call fails.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional


@dataclass(frozen=True)
class CredentialSpec:
    env_var: str
    purpose: str
    subsystems: tuple            # which runtime jobs need it
    required: bool               # a required missing key fails preflight
    secret: bool
    sanity: Optional[Callable[[str], bool]] = None


def _min_len(n: int) -> Callable[[str], bool]:
    return lambda v: len(v.strip()) >= n


CREDENTIALS: List[CredentialSpec] = [
    CredentialSpec("TIINGO_API_KEY", "market prices for prediction resolution "
                   "and paper marks", ("market_daily", "resolution"),
                   required=True, secret=True, sanity=_min_len(20)),
    CredentialSpec("FRED_API_KEY", "macro series for macro predictions",
                   ("market_daily", "resolution"), required=True, secret=True,
                   sanity=_min_len(20)),
    CredentialSpec("ANTHROPIC_API_KEY", "LLM for Synthetic Worlds --live and "
                   "reasoning legs", ("synthetic_live",), required=False,
                   secret=True, sanity=lambda v: v.strip().startswith("sk-")),
    CredentialSpec("PUBLER_API_KEY", "external marketing publication "
                   "(disabled by default)", ("marketing_publish",),
                   required=False, secret=True, sanity=_min_len(10)),
    CredentialSpec("WEBAPP_SECRET", "web session/CSRF signing (production)",
                   ("webapp",), required=False, secret=True,
                   sanity=_min_len(32)),
]


def _status_for(spec: CredentialSpec) -> str:
    raw = os.environ.get(spec.env_var)
    if not raw or not raw.strip():
        return "missing"
    if spec.sanity is not None and not spec.sanity(raw):
        return "invalid_format"
    return "unprobed"          # present + sane; not live-probed


def check_config() -> Dict[str, dict]:
    """The full report. Values are NEVER included — only name/status/meta."""
    report: Dict[str, dict] = {}
    for spec in CREDENTIALS:
        report[spec.env_var] = {
            "status": _status_for(spec),
            "purpose": spec.purpose,
            "subsystems": list(spec.subsystems),
            "required": spec.required,
            "secret": spec.secret,
        }
    return report


def missing_required(report: Optional[Dict[str, dict]] = None) -> List[str]:
    report = report or check_config()
    return [name for name, r in report.items()
            if r["required"] and r["status"] in ("missing", "invalid_format")]


def preflight(*, bus=None, root: Optional[Path] = None,
              actor_id: str = "config_preflight") -> dict:
    """Run preflight, persist a health snapshot, and emit a persistent
    failure event for each missing/invalid REQUIRED credential. Returns the
    overall health (never any secret)."""
    report = check_config()
    failures = missing_required(report)
    healthy = not failures
    snapshot = {"healthy": healthy, "missing_required": failures,
                "report": report}

    if root is not None:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        # append-only health log (one line per preflight), plus a latest file
        import json
        from datetime import datetime, timezone
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        line = json.dumps({"at": stamp, **snapshot}, sort_keys=True)
        with open(root / "config_health.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")
        (root / "config_health_latest.json").write_text(
            json.dumps({"at": stamp, **snapshot}, indent=2, sort_keys=True))

    if bus is not None:
        for name in failures:
            bus.publish(
                "config.preflight_failed", subject_type="job",
                subject_id=f"config:{name}", producer="config_preflight",
                actor_type="system", actor_id=actor_id, source="system",
                payload={"env_var": name, "status": report[name]["status"],
                         "required_for": report[name]["subsystems"]},
                idempotency_key=f"config_missing:{name}:{_day()}")
    return snapshot


def _day() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
