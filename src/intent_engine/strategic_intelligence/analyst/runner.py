"""Running the analyst: evidence in, verified analysis out.

Operational rules, all of which exist because this runs on a public demo:

  * bounded  -- one call, a hard token ceiling, a timeout, at most one retry
  * cached   -- keyed by the evidence itself, so re-opening a report is free
  * offline-safe -- no client configured means an honest state, never a guess
  * silent about secrets -- usage is logged, the key never is
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

from intent_engine.strategic_intelligence.analyst.contract import (
    ANALYSIS_SCHEMA, PROMPT_VERSION, AnalysisRejected, ResultState,
    StrategicAnalysis,
)
from intent_engine.strategic_intelligence.analyst.critic import (
    rejects, verify_analysis,
)

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-5"
MAX_OUTPUT_TOKENS = 4000
MAX_EVIDENCE_ITEMS = 40
MAX_EXCERPT_CHARS = 700
REQUEST_TIMEOUT_S = 60.0
MAX_ATTEMPTS = 2

#: minimum evidence before it is worth asking for a strategic reading at all
MIN_OBSERVATIONS = 3


class AnalystUnavailable(RuntimeError):
    """No reasoning backend is configured. Never a reason to invent output."""


SYSTEM_PROMPT = """\
You are a strategy partner briefing a chief executive. You have been given the \
complete evidence retrieved about one company. You may reason only from that \
evidence.

What makes an insight worth the reader's time:

- It is about THIS company. If your sentence would read just as well with a \
different company's name in it, it is not an insight; delete it.
- It names a real trade-off. Strategy is what a company gives up. A claim with \
no tension in it is a description.
- It reaches the financial statements. Say which lever moves -- margin, \
capital, pricing, retention, distribution, switching cost -- and how.
- It is comparative. A position only exists relative to competitors, \
substitutes, or the norm in that industry.
- It argues against itself. State the strongest case that you are wrong.
- It changes a decision. If nothing a leader does depends on it, it is trivia.

Hard rules:

1. Cite an observation id for every material claim. If you cannot cite it, you \
may not claim it.
2. Never state a number -- a percentage, a currency figure, a magnitude -- \
that does not appear in the evidence. Do not estimate, annualise or infer \
figures.
3. Never assert private knowledge: not what executives "discussed", "decided" \
or "believe". You may infer what their public behaviour implies, and you must \
label it as inference.
4. Distinguish the entity from its parent. A fact reported about a group is \
not a fact about a subsidiary, and vice versa. If the evidence mixes levels, \
say so in scope_note.
5. Confidence must track the evidence, not your fluency. Company-owned pages \
are one vantage point no matter how many of them there are; three of them \
agreeing is a company being consistent, not corroboration.
6. Recency of retrieval is not recency of publication. A page fetched today \
may describe something from years ago.

If the evidence is descriptive marketing rather than strategic signal, set \
sufficient_for_strategic_analysis to false, explain why, and return no \
insights. That is a correct answer and it is strongly preferred to a \
confident-sounding invention. One well-evidenced insight beats three weak \
ones."""


def _evidence_pack(observations, company_name, *, entity_hint=None) -> str:
    lines = [f"COMPANY UNDER ANALYSIS: {company_name}"]
    if entity_hint:
        lines.append(f"ENTITY NOTE: {entity_hint}")
    lines.append("")
    lines.append(f"EVIDENCE ({len(observations)} retrieved observations). "
                 "Cite by observation_id.")
    lines.append("")
    for o in observations[:MAX_EVIDENCE_ITEMS]:
        excerpt = (getattr(o, "excerpt", "") or "")[:MAX_EXCERPT_CHARS]
        lines.append(f"[{o.observation_id}]")
        lines.append(f"  source        : {getattr(o, 'source_title', '')}")
        lines.append(f"  url           : {getattr(o, 'origin', '')}")
        lines.append(f"  whose account : {getattr(o, 'source_class', '')}")
        lines.append(f"  retrieved     : {getattr(o, 'date', '') or 'unknown'}"
                     f"  (publication date NOT established unless stated in "
                     f"the text)")
        lines.append(f"  strength      : "
                     f"{getattr(o, 'evidence_quality', 'unknown')}")
        lines.append(f"  excerpt       : {excerpt}")
        lines.append("")
    return "\n".join(lines)


def evidence_digest(observations, company_name) -> str:
    """Stable fingerprint of exactly what the analyst was shown."""
    h = hashlib.sha256()
    h.update(company_name.encode("utf-8"))
    for o in sorted(observations, key=lambda o: o.observation_id):
        h.update(o.observation_id.encode("utf-8"))
        h.update((getattr(o, "excerpt", "") or "").encode("utf-8"))
        h.update((getattr(o, "source_class", "") or "").encode("utf-8"))
    return h.hexdigest()


def cache_key(observations, company_name, model) -> str:
    return hashlib.sha256("|".join([
        evidence_digest(observations, company_name), model, PROMPT_VERSION,
    ]).encode("utf-8")).hexdigest()


class FileCache:
    """Evidence-keyed cache. A changed prompt or model invalidates it."""

    def __init__(self, root):
        self.root = Path(root)

    def get(self, key):
        p = self.root / f"{key}.json"
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text("utf-8"))
        except (ValueError, OSError):
            return None

    def put(self, key, value):
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            tmp = self.root / f"{key}.json.tmp"
            tmp.write_text(json.dumps(value), "utf-8")
            tmp.replace(self.root / f"{key}.json")
        except OSError as exc:                       # cache is best-effort
            log.warning("analyst cache write failed: %s", exc)


def default_client(model=DEFAULT_MODEL):
    """The real client, or None when no key is configured.

    Returning None rather than raising lets a deployment run in deterministic
    mode without pretending the analyst exists.
    """
    try:                        # a .env is how local runs supply the key
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:         # pragma: no cover - dotenv is a hard dep
        pass
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    from intent_engine.core.llm_client import LLMClient
    return LLMClient(model=model)


def analyse(company_name, observations, *, client=None, cache=None,
            model=DEFAULT_MODEL, entity_hint=None, now=None):
    """Produce a verified StrategicAnalysis, or a state explaining why not.

    Returns (analysis_or_None, state, findings). Raises AnalystUnavailable when
    no reasoning backend is configured -- the caller decides what to show, and
    must not substitute template hypotheses.
    """
    observations = list(observations)
    if len(observations) < MIN_OBSERVATIONS:
        return (None, ResultState.EVIDENCE_LIMITED, [])

    if client is None:
        raise AnalystUnavailable(
            "no reasoning backend configured (ANTHROPIC_API_KEY unset)")

    key = cache_key(observations, company_name, model)
    if cache is not None:
        hit = cache.get(key)
        if hit is not None:
            log.info("analyst cache hit company=%s key=%s", company_name,
                     key[:12])
            return _verify_and_wrap(hit, observations, company_name, model,
                                    usage={"cached": True})

    user_message = _evidence_pack(observations, company_name,
                                  entity_hint=entity_hint)

    raw, usage, last_error = None, {}, None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.monotonic()
        try:
            raw = client.call_tool(
                system=SYSTEM_PROMPT,
                user_message=user_message,
                tool_name="record_strategic_analysis",
                tool_description=(
                    "Record the strategic analysis of this company, grounded "
                    "entirely in the supplied evidence."),
                input_schema=ANALYSIS_SCHEMA,
                max_tokens=MAX_OUTPUT_TOKENS,
            )
            usage = {"attempts": attempt,
                     "elapsed_s": round(time.monotonic() - started, 2)}
            break
        except Exception as exc:                    # noqa: BLE001 - bounded
            last_error = exc
            log.warning("analyst call failed (attempt %d/%d): %s",
                        attempt, MAX_ATTEMPTS, type(exc).__name__)
            if attempt == MAX_ATTEMPTS:
                return (None, ResultState.FAILED, [])

    if raw is None:                                  # pragma: no cover
        log.error("analyst produced no output: %s", last_error)
        return (None, ResultState.FAILED, [])

    if cache is not None:
        cache.put(key, raw)
    return _verify_and_wrap(raw, observations, company_name, model, usage)


def _verify_and_wrap(raw, observations, company_name, model, usage):
    findings = verify_analysis(raw, observations=observations,
                               company_name=company_name)
    if rejects(findings):
        log.warning("analyst output rejected for %s: %s", company_name,
                    "; ".join(f.check for f in findings if f.rejects))
        return (None, ResultState.STRATEGICALLY_INSUFFICIENT, findings)

    if not raw.get("sufficient_for_strategic_analysis", False):
        analysis = _to_analysis(raw, model, usage)
        return (analysis, ResultState.STRATEGICALLY_INSUFFICIENT, findings)

    if not (raw.get("insights") or []):
        analysis = _to_analysis(raw, model, usage)
        return (analysis, ResultState.STRATEGICALLY_INSUFFICIENT, findings)

    return (_to_analysis(raw, model, usage), ResultState.COMPLETE, findings)


def _to_analysis(raw, model, usage) -> StrategicAnalysis:
    return StrategicAnalysis(
        entity_scope=raw.get("entity_scope") or {},
        business_model=raw.get("business_model", ""),
        insights=list(raw.get("insights") or []),
        evidence_gaps=list(raw.get("evidence_gaps") or []),
        sufficient=bool(raw.get("sufficient_for_strategic_analysis")),
        insufficiency_reason=raw.get("insufficiency_reason", ""),
        model=model, prompt_version=PROMPT_VERSION, usage=usage or {})
