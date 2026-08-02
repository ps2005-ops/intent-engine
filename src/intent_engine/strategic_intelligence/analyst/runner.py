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
# The decision-shaped contract asks for a business-model reconstruction, an
# insight with a consequence chain, three to five decisions each with upside,
# downside, cost of waiting and a falsifier, plus competitive dynamics and
# questions. At 4000 that truncated on a five-document run and the whole
# analysis was lost to a retry that truncated identically.
MAX_OUTPUT_TOKENS = 8000
MAX_EVIDENCE_ITEMS = 40
MAX_EXCERPT_CHARS = 700
REQUEST_TIMEOUT_S = 60.0
MAX_ATTEMPTS = 2

#: minimum evidence before it is worth asking for a strategic reading at all
MIN_OBSERVATIONS = 3
#: caps enforced in code, because schema maxItems is a request not a guarantee
MAX_DECISIONS = 3
MAX_ASSUMPTIONS = 2


class AnalystUnavailable(RuntimeError):
    """No reasoning backend is configured. Never a reason to invent output."""


SYSTEM_PROMPT = """\
You are the advisor a founder calls before a decision they cannot take back. \
Think like a former operator, a board member, an investor and a competitor at \
once. You have the complete evidence retrieved about one company, and you may \
reason only from it.

You are not writing a report. You are giving advice. Write the way a person \
speaks when they respect the reader's time and have nothing to prove.

A founder has five minutes. When they close this they should know what business this company is really in, what game it is actually playing, what leadership is protecting, what assumption is carrying the weight, and what a competitor should be afraid of. Nothing you write that does not serve one of those five earns its place.

Write less than you want to. Every sentence a founder skips costs you the one after it. Simple words, concrete nouns, no jargon: clear enough for a smart nineteen-year-old, worth the time of a chief executive.

Start with the money. Before inferring any strategy, work out how the business \
actually makes money, where profit really comes from, and where it leaks. The \
gap between what a company sells and what its customers are actually paying \
for is where most real insight lives.

Then find the one thing worth remembering. Test it: would a competent \
executive at this company read your sentence and think "I hadn't looked at it \
that way"? If they would nod and move on, it is a summary. Delete it and look \
harder. In particular, reject anything that is a restatement of the company's \
own homepage, an industry cliche, or a sentence that would survive swapping in \
a different company's name.

Then say what to DO. Every decision you name must be a real fork with two \
sides a reasonable person could take, not a topic to explore. Say what it \
costs to wait, because the cost of waiting is usually the whole argument. Say \
what a competitor might do first.

Show the chain. One move causes another. Follow it as far as the evidence \
supports and then stop -- three honest links beat five invented ones.

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

7. Write like a strategist, not like software. Never use the words \
"supporting evidence", "decision affected", "likely agenda", "current \
discussion", "strategic hypothesis" or "affected functions" in anything a \
reader sees. Say "this matters because", "the choice is", "watch for".

8. Every decision must end in one of: do it now, monitor it, research it, wait, or ignore it. "It depends" is the absence of a recommendation wearing the clothes of one. If you genuinely cannot tell, the answer is "research" plus the cheapest experiment that would settle it.

9. Say how reversible each decision is. A one-way door deserves weeks of thought; an easily reversed call deserves a day and should not consume attention. Most decisions are not high impact -- say so.

10. Name what you are assuming, and what would break each assumption. A founder who knows which belief is load-bearing knows what to watch.

11. Say what almost nobody is discussing. That is the most valuable thing an outside view can offer. If nothing qualifies, say nothing qualifies -- inventing a blind spot is worse than admitting the obvious things are the only things.

12. Say each thing once. If an idea belongs in the insight, it does not also \
belong in a decision and in a question. Repetition reads as padding.

If the evidence is descriptive marketing rather than strategic signal, set \
sufficient_for_strategic_analysis to false, explain why, and return no \
decisions. That is a correct answer and it is strongly preferred to a \
confident-sounding invention. Three real decisions beat five padded ones."""


_CLOSED_EVIDENCE_NOTICE = """\
CLOSED-EVIDENCE TASK. Measured failure this guards against: on five real
companies the critic rejected 16 figures and 15 of them appeared in NO
retrieved document -- they were recalled, not read.

  * Use ONLY the evidence in this request.
  * You may already know this company. Do not use anything you remember.
  * State a number ONLY if it appears in NUMERIC_FACTS below, and cite its
    fact_id. There are no exceptions for figures you are confident about.
  * Do not compute a new number from the facts. A derivation you perform
    silently cannot be verified and will be refused.
  * Where evidence and memory disagree, the evidence wins.
  * Where a figure is missing, say so: "the retrieved evidence does not
    provide a verified figure", or describe direction without magnitude.

Withholding is a correct answer. An unsupported figure is not."""


def _evidence_pack(observations, company_name, *, entity_hint=None,
                   ledger=None) -> str:
    lines = [f"COMPANY UNDER ANALYSIS: {company_name}"]
    if entity_hint:
        lines.append(f"ENTITY NOTE: {entity_hint}")
    lines.append("")
    lines.append(_CLOSED_EVIDENCE_NOTICE)
    lines.append("")
    if ledger is not None:
        from intent_engine.strategic_intelligence.numeric_ledger import (
            render_for_pack,
        )
        lines.append(render_for_pack(ledger))
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


def cache_key(observations, company_name, model, *, ledger_size=0) -> str:
    return hashlib.sha256("|".join([
        evidence_digest(observations, company_name), model, PROMPT_VERSION,
        f"ledger={ledger_size}",
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

    from intent_engine.strategic_intelligence.numeric_ledger import (
        build_ledger,
    )
    # The ledger is part of WHAT THE ANALYST WAS SHOWN, so it belongs in the
    # cache identity: a run that saw different figures is a different run.
    ledger = build_ledger(observations)
    key = cache_key(observations, company_name, model,
                    ledger_size=len(ledger))
    if cache is not None:
        hit = cache.get(key)
        if hit is not None:
            log.info("analyst cache hit company=%s key=%s", company_name,
                     key[:12])
            return _verify_and_wrap(hit, observations, company_name, model,
                                    usage={"cached": True}, ledger=ledger)

    user_message = _evidence_pack(observations, company_name,
                                  entity_hint=entity_hint, ledger=ledger)

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
            # Truncation is deterministic: the same prompt will truncate the
            # same way, so retrying only spends a second call to fail again.
            truncated = "max_tokens" in str(exc)
            log.warning("analyst call failed (attempt %d/%d): %s%s",
                        attempt, MAX_ATTEMPTS, type(exc).__name__,
                        " (truncated - not retrying)" if truncated else "")
            if truncated or attempt == MAX_ATTEMPTS:
                return (None, ResultState.FAILED, [])

    if raw is None:                                  # pragma: no cover
        log.error("analyst produced no output: %s", last_error)
        return (None, ResultState.FAILED, [])

    if cache is not None:
        cache.put(key, raw)
    return _verify_and_wrap(raw, observations, company_name, model, usage,
                            ledger=ledger)


def _normalise(raw):
    """Coerce shape variation the model is allowed to produce.

    Found by a fresh cross-sector run, not by any test: `assumptions` came back
    as a list of plain strings rather than objects, which crashed the critic
    outright and -- before the crash -- rejected the analysis for having no
    falsifier, a complaint that was an artifact of the shape rather than a
    judgement about the content.

    A schema is a request, not a guarantee. Anything walking a model's output
    has to survive the model answering the question a slightly different way.
    """
    if not isinstance(raw, dict):
        return {}
    out = dict(raw)
    # A truncated response can leave a field holding a STRING where a list was
    # asked for. Iterating it yields characters: one fresh run produced 1,131
    # "assumptions", each a single character, each separately rejected.
    for key in ("assumptions", "decisions", "questions", "evidence_gaps"):
        if isinstance(out.get(key), str):
            out[key] = []
    fixed = []
    for a in (out.get("assumptions") or []):
        if isinstance(a, str) and len(a.split()) >= 4:
            fixed.append({"assumption": a, "why_we_believe_it": "",
                          "what_would_break_it": "", "how_load_bearing": "",
                          "confidence": "", "_shape_recovered": True})
        elif isinstance(a, dict):
            fixed.append(a)
    # maxItems in a schema is a request. One fresh run returned far more than
    # the cap; a list of twenty assumptions is a list of none.
    out["assumptions"] = fixed[:MAX_ASSUMPTIONS]
    out["decisions"] = (out.get("decisions") or [])[:MAX_DECISIONS]
    out["decisions"] = [d for d in (out.get("decisions") or [])
                        if isinstance(d, dict)]
    for key in ("entity_scope", "business_model", "the_insight", "competitive",
                "blind_spots", "scenarios", "mental_model"):
        if not isinstance(out.get(key), dict):
            out[key] = {}
    for key in ("questions", "evidence_gaps"):
        out[key] = [q for q in (out.get(key) or []) if isinstance(q, str)]
    return out


def _verify_and_wrap(raw, observations, company_name, model, usage,
                     ledger=None):
    raw = _normalise(raw)
    # SCHEMA GATE, ahead of the critic and separate from it. A numeric claim
    # with no fact_id behind it never reaches the critic; the critic stays an
    # independent second line of defence rather than the only one.
    from intent_engine.strategic_intelligence.contract_numeric import (
        validate_numeric_claims,
    )
    schema_findings = validate_numeric_claims(raw, ledger or [])
    findings = list(schema_findings) + list(verify_analysis(
        raw, observations=observations, company_name=company_name))
    if rejects(findings):
        log.warning("analyst output rejected for %s: %s", company_name,
                    "; ".join(f.check for f in findings if f.rejects))
        return (None, ResultState.STRATEGICALLY_INSUFFICIENT, findings)

    if not raw.get("sufficient_for_strategic_analysis", False):
        analysis = _to_analysis(raw, model, usage)
        return (analysis, ResultState.STRATEGICALLY_INSUFFICIENT, findings)

    if not (raw.get("decisions") or []):
        analysis = _to_analysis(raw, model, usage)
        return (analysis, ResultState.STRATEGICALLY_INSUFFICIENT, findings)

    return (_to_analysis(raw, model, usage), ResultState.COMPLETE, findings)


def _to_analysis(raw, model, usage) -> StrategicAnalysis:
    return StrategicAnalysis(
        entity_scope=raw.get("entity_scope") or {},
        business_model=raw.get("business_model") or {},
        the_insight=raw.get("the_insight") or {},
        decisions=list(raw.get("decisions") or []),
        competitive=raw.get("competitive") or {},
        questions=list(raw.get("questions") or []),
        mental_model=raw.get("mental_model") or {},
        assumptions=list(raw.get("assumptions") or []),
        blind_spots=raw.get("blind_spots") or {},
        scenarios=raw.get("scenarios") or {},
        strongest_case_we_are_wrong=raw.get("strongest_case_we_are_wrong", ""),
        evidence_gaps=list(raw.get("evidence_gaps") or []),
        sufficient=bool(raw.get("sufficient_for_strategic_analysis")),
        insufficiency_reason=raw.get("insufficiency_reason", ""),
        model=model, prompt_version=PROMPT_VERSION, usage=usage or {})
