"""Deterministic verification of the analyst's output.

Everything here runs without a network and without a model. That is the point:
the reasoning is probabilistic, so the checking must not be. A finding at
severity "reject" discards the whole analysis and the run reports an honest
limited state instead -- it never falls through to the generic scaffolds,
because a plausible-sounding wrong answer is worse than a visible gap.

The genericity check is the one that addresses the original complaint. A
sentence like "absorbing adjacent tools until the work lives inside it" is
fluent, confident, and equally true of Atlassian, Notion, Monday, Adobe,
Microsoft and Salesforce -- which is what makes it worthless. The test is
therefore not "does this read well" but "is this anchored to words that appear
in the evidence for THIS company".
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Strategy-speak: fluent, universally applicable, and empty as the SUBSTANCE of
# a claim. These may appear in a headline, but they cannot be what the headline
# is made of.
_GENERIC_VOCAB = frozenset("""
platform platforms ecosystem ecosystems digital transformation synergy
synergies leverage leveraging scale scaling growth innovative innovation
solution solutions strategic strategy value proposition customer customers
market markets business businesses product products service services
technology technologies enterprise enterprises operational efficiency
optimize optimizing optimise robust seamless holistic comprehensive
end-to-end best-in-class world-class cutting-edge next-generation
capabilities capability offering offerings vertical horizontal adjacent
expanding expansion positioning positioned differentiated differentiation
competitive advantage moat future company companies organisation organization
""".split())

# Phrases that are pure filler. Their presence in a headline is disqualifying.
_BANNED_PHRASES = (
    "digital transformation", "best-in-class", "world-class",
    "cutting-edge", "next-generation", "paradigm shift", "synergy",
    "unlock value", "drive growth", "at scale", "holistic approach",
)

_STOPWORDS = frozenset("""
the a an and or but if then than that this these those with without within
into onto from for to of in on at by as is are was were be been being it its
their there here what which who whom whose how why when where while more most
less least much many few own same so not no nor can could will would should
may might must have has had do does did about over under between across
toward towards after before during through against among both each other
""".split())

_NUM_RE = re.compile(r"""
    (?P<currency>[$€£¥]\s?\d[\d,]*(?:\.\d+)?)
  | (?P<percent>\d[\d,]*(?:\.\d+)?\s?%)
  | (?P<scaled>\d[\d,]*(?:\.\d+)?\s?(?:million|billion|trillion|bn|m\b|k\b))
  | (?P<big>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,})
""", re.I | re.X)

_INDEPENDENT_CLASSES = frozenset(
    {"independent_reporting", "customer_voice", "competitor",
     "investor_material"})


@dataclass
class CriticFinding:
    check: str
    message: str
    severity: str = "reject"        # "reject" | "warn"
    where: str = ""

    @property
    def rejects(self) -> bool:
        return self.severity == "reject"


def _tokens(text: str) -> list:
    return re.findall(r"[a-z0-9][a-z0-9\-']+", (text or "").lower())


def _content_tokens(text: str, extra_stop=()) -> set:
    stop = _STOPWORDS | _GENERIC_VOCAB | set(extra_stop)
    return {t for t in _tokens(text) if len(t) >= 4 and t not in stop}


def _normalise_number(raw: str) -> str:
    return re.sub(r"[\s,]", "", (raw or "").lower())


def _numbers_in(text: str) -> set:
    out = set()
    for m in _NUM_RE.finditer(text or ""):
        out.add(_normalise_number(m.group(0)))
    return out


def _walk_strings(node, path="") -> list:
    """Every string in the analysis, with a path for error messages."""
    out = []
    if isinstance(node, str):
        out.append((path, node))
    elif isinstance(node, dict):
        for k, v in node.items():
            out.extend(_walk_strings(v, f"{path}.{k}" if path else str(k)))
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            out.extend(_walk_strings(v, f"{path}[{i}]"))
    return out


def verify_analysis(analysis: dict, *, observations, company_name: str) -> list:
    """Return findings. Any finding with severity 'reject' invalidates the run.

    `observations` are the StrategicObservation objects that were offered to the
    analyst -- the only things it was allowed to reason from.
    """
    findings = []
    by_id = {o.observation_id: o for o in observations}

    evidence_text = " ".join(
        " ".join(filter(None, [getattr(o, "text", ""), getattr(o, "excerpt", ""),
                               getattr(o, "source_title", "")]))
        for o in observations)
    evidence_vocab = _content_tokens(evidence_text)
    evidence_numbers = _numbers_in(evidence_text)
    company_tokens = set(_tokens(company_name))

    insights = analysis.get("insights") or []

    # --- 1. citations resolve -------------------------------------------------
    for i, ins in enumerate(insights):
        cites = ins.get("citations") or []
        if not cites:
            findings.append(CriticFinding(
                "citation_missing",
                f"insight {i} ({ins.get('headline', '')[:60]!r}) cites no "
                "evidence", where=f"insights[{i}]"))
            continue
        unknown = [c for c in cites if c not in by_id]
        if unknown:
            findings.append(CriticFinding(
                "citation_unresolvable",
                f"insight {i} cites observation id(s) that do not exist: "
                f"{', '.join(unknown)}", where=f"insights[{i}]"))

    # --- 2. no invented numbers ----------------------------------------------
    # Only figures that assert something about the company are checked --
    # percentages, currency, and magnitudes. A phrase like "over three years"
    # is reasoning about a horizon, not a claim about a financial fact.
    for path, text in _walk_strings(analysis):
        for num in _numbers_in(text):
            if num not in evidence_numbers:
                findings.append(CriticFinding(
                    "invented_number",
                    f"the figure {num!r} appears in the analysis but in no "
                    f"retrieved source", where=path))

    # --- 3. genericity --------------------------------------------------------
    for i, ins in enumerate(insights):
        headline = ins.get("headline", "") or ""
        low = headline.lower()
        hit = [p for p in _BANNED_PHRASES if p in low]
        if hit:
            findings.append(CriticFinding(
                "generic_filler",
                f"insight {i} headline uses filler ({', '.join(hit)}) instead "
                "of saying something about this company",
                where=f"insights[{i}].headline"))

        grounded = _content_tokens(headline, extra_stop=company_tokens)
        anchored = grounded & evidence_vocab
        if len(anchored) < 2:
            findings.append(CriticFinding(
                "generic_headline",
                f"insight {i} headline is not anchored to this company's "
                f"evidence (grounding terms found: "
                f"{sorted(anchored) or 'none'}). A headline that survives "
                "swapping the company name is not an insight",
                where=f"insights[{i}].headline"))

        # Anchoring alone is gameable: naming two real products and wrapping
        # them in strategy-speak ("PlayStation is expanding its subscription
        # platform ecosystem") clears the anchor test while saying nothing.
        # So also measure how much of the sentence IS strategy-speak.
        substantive = [t for t in _tokens(headline)
                       if len(t) >= 4 and t not in _STOPWORDS
                       and t not in company_tokens]
        if substantive:
            generic_share = (sum(1 for t in substantive if t in _GENERIC_VOCAB)
                             / len(substantive))
            if generic_share >= 0.4:
                findings.append(CriticFinding(
                    "generic_density",
                    f"insight {i} headline is {generic_share:.0%} "
                    "strategy-speak; the specific words are decoration on a "
                    "sentence that would fit any company",
                    where=f"insights[{i}].headline"))

    # --- 4. required substance -----------------------------------------------
    for i, ins in enumerate(insights):
        tension = ins.get("tension") or {}
        if not (tension.get("side_a") and tension.get("side_b")):
            findings.append(CriticFinding(
                "no_tension", f"insight {i} states no real trade-off",
                where=f"insights[{i}].tension"))
        econ = ins.get("economics") or {}
        if not econ.get("mechanism"):
            findings.append(CriticFinding(
                "no_economic_mechanism",
                f"insight {i} does not explain how this reaches the financial "
                "statements", where=f"insights[{i}].economics"))
        counter = ins.get("counterargument") or {}
        if not counter.get("strongest_case_against"):
            findings.append(CriticFinding(
                "no_counterargument",
                f"insight {i} offers no case against itself",
                where=f"insights[{i}].counterargument"))
        if not ins.get("decision_affected"):
            findings.append(CriticFinding(
                "no_decision", f"insight {i} affects no stated decision",
                where=f"insights[{i}]"))

    # --- 5. confidence may not exceed the evidence ---------------------------
    for i, ins in enumerate(insights):
        cited = [by_id[c] for c in (ins.get("citations") or []) if c in by_id]
        classes = {getattr(o, "source_class", "") for o in cited}
        independent = classes & _INDEPENDENT_CLASSES
        conf = (ins.get("confidence") or "").lower()
        if conf == "high" and not independent:
            findings.append(CriticFinding(
                "confidence_exceeds_evidence",
                f"insight {i} claims high confidence from company-owned "
                "sources only; one vantage point cannot corroborate itself",
                where=f"insights[{i}].confidence"))
        rationale = (ins.get("confidence_rationale") or "").strip()
        if len(rationale.split()) < 5:
            findings.append(CriticFinding(
                "unexplained_confidence",
                f"insight {i} gives a confidence label without explaining it "
                "in plain language", severity="warn",
                where=f"insights[{i}].confidence_rationale"))

    # --- 6. entity scope ------------------------------------------------------
    scope = analysis.get("entity_scope") or {}
    if scope.get("is_subsidiary") and not (scope.get("parent") or "").strip():
        findings.append(CriticFinding(
            "unnamed_parent",
            "the analysis says this is a subsidiary but does not name the "
            "parent, so the reader cannot tell which entity a fact belongs to",
            where="entity_scope"))

    # --- 7. an insight must not be a restatement of another ------------------
    seen = []
    for i, ins in enumerate(insights):
        key = _content_tokens(ins.get("headline", ""),
                              extra_stop=company_tokens)
        for j, prev in seen:
            if key and prev and len(key & prev) / len(key | prev) > 0.6:
                findings.append(CriticFinding(
                    "restatement",
                    f"insight {i} restates insight {j} rather than adding "
                    "something", severity="warn", where=f"insights[{i}]"))
        seen.append((i, key))

    return findings


def rejects(findings) -> bool:
    return any(f.rejects for f in findings)
