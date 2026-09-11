"""The canonical company object: what this business is, and where each part came from.

WHY EVERY FIELD CARRIES ITS PROVENANCE
--------------------------------------
The recorded failure this design exists to prevent is precise: per-class
business-model text made five software companies byte-identical. A profile
that mixes "what this company's own filing says" with "what a business of
this kind is like" and prints both in the same voice cannot be audited, and
what gets shipped is the class prior wearing the company's name.

So no field here is a bare string. Each is a `Fact` carrying:

    value        the sentence
    provenance   SUBJECT_EVIDENCE | ANALYST | CLASS_PRIOR | MANIFEST |
                 NOT_ESTABLISHED
    basis        why it is believed, in the reader's language
    evidence     the quoted span or observation id, where one exists

CLASS_PRIOR IS NOT A DEFECT. It is a legitimate and useful answer -- "a
subscription software business earns next period's revenue from the installed
base before any new sale" is true of subscription software businesses by
construction. What is a defect is a class prior PRESENTED AS a finding about
this company, and the provenance tag is what makes the difference visible to
the reader, to the composer, and to `differentiation.genericity`.

`specificity` counts it: the share of populated fields that came from this
company's own evidence or from the analyst's evidence-cited reconstruction.
A profile whose specificity is near zero is a profile that has learned the
company's name and nothing else, and the product says so rather than
composing around it.

WHAT THIS MODULE MAY NOT DO
---------------------------
It states no number that is not in the evidence, invents no capability, and
never promotes a class prior to a company finding. A company it cannot read
gets NOT_ESTABLISHED fields and a stated reason -- never the average
company's profile, which is how one business's economics becomes another's.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Dict, Optional, Tuple

from intent_engine.adaptive.classify import (
    EvidenceClassification, classify_from_evidence,
)

CONTRACT = "company_strategic_profile.v1"

#: WHAT KIND OF SOURCE ESTABLISHED THE BUSINESS MODEL, in four kinds that
#: call for four different levels of trust. Exposed in telemetry so a matrix
#: can say HOW a classification was reached, never only WHAT it was -- the
#: live run that prompted this reported a populated model beside an empty
#: confidence and an empty span.
MODEL_SOURCE_CURATED = "CURATED_CLASSIFICATION"
MODEL_SOURCE_REGULATOR = "REGULATOR_INDUSTRY_CODE"
MODEL_SOURCE_SUBJECT = "SUBJECT_PUBLISHED_EVIDENCE"
MODEL_SOURCE_NONE = "NOT_ESTABLISHED"

#: How each maps to what `company_profile` records internally.
_MODEL_SOURCE = {
    "VALIDATION_MANIFEST": MODEL_SOURCE_CURATED,
    "SEC_SIC": MODEL_SOURCE_REGULATOR,
    "SEC_SIC+FILING_REVENUE": MODEL_SOURCE_REGULATOR,
    "SUBJECT_EVIDENCE": MODEL_SOURCE_SUBJECT,
    "NONE": MODEL_SOURCE_NONE,
}

#: What each means to a reader who has never heard of any of them.
MODEL_SOURCE_WORDS = {
    MODEL_SOURCE_CURATED:
        "a reviewed classification of this company held by this system",
    MODEL_SOURCE_REGULATOR:
        "the industry code a regulator assigns this filer",
    MODEL_SOURCE_SUBJECT:
        "this company's own published account of what it sells and how it "
        "is paid",
    MODEL_SOURCE_NONE:
        "not enough evidence to classify confidently",
}


def model_source_of(profile_source: str) -> str:
    return _MODEL_SOURCE.get(str(profile_source or "NONE"),
                             MODEL_SOURCE_NONE)


SUBJECT_EVIDENCE = "SUBJECT_EVIDENCE"
ANALYST = "ANALYST"
CLASS_PRIOR = "CLASS_PRIOR"
MANIFEST = "MANIFEST"
NOT_ESTABLISHED = "NOT_ESTABLISHED"

#: Provenances that make a field a statement about THIS company rather than
#: about businesses of its kind.
COMPANY_SPECIFIC = (SUBJECT_EVIDENCE, ANALYST)


@dataclasses.dataclass(frozen=True)
class Fact:
    """One field of the profile, and where it came from."""
    value: str = ""
    provenance: str = NOT_ESTABLISHED
    basis: str = ""
    evidence: str = ""

    def __bool__(self) -> bool:
        return bool(self.value) and self.provenance != NOT_ESTABLISHED

    @property
    def company_specific(self) -> bool:
        return bool(self) and self.provenance in COMPANY_SPECIFIC

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def _unknown(reason: str) -> Fact:
    return Fact(value="", provenance=NOT_ESTABLISHED, basis=reason)


# --- reading capabilities and dependencies out of the company's own words ---
#
# Both extractors are deliberately conservative and BOTH quote what they
# matched. An asset nobody can point at in the company's own text is an
# invention, and this layer's whole claim is that it did not invent anything.

_ASSET_PATTERNS = (
    re.compile(r"\b(?:our|the)\s+(?:proprietary|patented|purpose[- ]built|"
               r"unique|award[- ]winning)\s+"
               r"([a-z][a-z0-9\-]{3,}(?:\s+[a-z0-9\-]+){0,3})"
               r"(?=[.,;:]|\s+(?:and|that|which|for|to)\b)", re.I),
    re.compile(r"\bthe only\s+([a-z][a-z0-9\-]{3,}(?:\s+[a-z0-9\-]+){0,3})\s+(?:that|which|to)"
               r"\b", re.I),
    re.compile(r"\b(?:we|our platform|the platform)\s+(?:is|are)\s+the\s+"
               r"([a-z][a-z0-9\-]{3,}(?:\s+[a-z0-9\-]+){0,3})(?=[.,;:]|\s+(?:that|which|for)\b)",
               re.I),
    re.compile(r"\bpurpose[- ]built\s+(?:for|to)\s+"
               r"([a-z][a-z0-9\-]{3,}(?:\s+[a-z0-9\-]+){0,3})(?=[.,;:]|\s+(?:and|that)\b)",
               re.I),
    re.compile(r"\bpatented\s+([a-z][a-z0-9\-]{3,}(?:\s+[a-z0-9\-]+){0,3})"
               r"(?=[.,;:]|\s+(?:and|that|which)\b)", re.I),
)

#: What a company names as something it builds on, integrates with, runs on
#: or partners with.
#:
#: THE VERB IS CASE-INSENSITIVE AND THE CAPTURE IS NOT, AND THAT SPLIT IS THE
#: WHOLE FIX. An earlier version compiled these entirely case-sensitively, so
#: "Integrates with Salesforce" -- at the start of a sentence, which is where
#: a marketing page puts it -- matched nothing. Measured across ten companies
#: whose pages all name their integrations: 0 dependencies found. The capture
#: stays capitalised because a dependency IS a proper noun; lowercasing it
#: would admit "integrates with your existing tools", which names nobody.
_DEPENDENCY_PATTERNS = (
    re.compile(r"(?i:\b(?:integrat(?:es|ed|ion)s?)\s+with\s+)"
               r"([A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*){0,3})"),
    re.compile(r"(?i:\bbuilt\s+(?:on|for)\s+)"
               r"([A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*){0,3})"),
    re.compile(r"(?i:\bpowered\s+by\s+)"
               r"([A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*){0,3})"),
    re.compile(r"(?i:\b(?:runs?|available|deployed)\s+on\s+)"
               r"([A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*){0,3})"),
    re.compile(r"(?i:\bpartners?(?:hips?)?\s+with\s+)"
               r"([A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*){0,3})"),
)

#: HOW A COMPANY SAYS WHAT IT IS, IN ITS OWN FIRST SENTENCE.
#:
#: This is the single most differentiating sentence most companies publish,
#: and it is the one the product was throwing away. Measured across the ten
#: companies this phase qualifies: "Highspot is the sales enablement platform
#: that increases the performance of revenue teams", "Cyera is the data
#: security platform for the AI era", "Sigma is the cloud analytics platform
#: that gives business users a spreadsheet interface". Two of those are the
#: same business model, the same lens family and the same class prior, and no
#: reader would confuse them.
#:
#: The company's OWN NAME is the anchor, which is what keeps this from
#: matching a rival's self-description sitting in the same corpus.
_SELF_PATTERNS = (
    r"\b{name}\s+(?:is|are)\s+(?:the|a|an)\s+"
    r"([a-z][^.;:]{{8,150}}?)(?=[.;:]|\s+(?:and we|and our)\b)",
    r"\b{name}\s+(?:helps|enables|gives|delivers|provides|powers)\s+"
    r"([a-z][^.;:]{{8,150}}?)(?=[.;:])",
    # THE POSSESSIVE FORM. A company that describes itself THROUGH its own
    # product is still describing itself, and it is a very common way to do
    # it: "Druva's AI-powered, cloud-native SaaS platform delivers data
    # security, identity resilience and cyber recovery." Measured live at
    # 807a4143, Druva was one of only two companies with no self-description
    # at all, and the pair collapsed to 0.927 similarity as a result.
    #
    # A descriptive VERB is required rather than matching every possessive,
    # because "Druva's customers say ..." is a testimonial and "Druva's
    # press releases" is furniture -- both are possessives about the company
    # and neither is the company's account of what it is.
    r"\b{name}(?:'s|\u2019s)\s+"
    r"([a-z][^.;:]{{2,90}}?\s+(?:delivers|provides|powers|helps|enables)\s+"
    r"[^.;:]{{8,120}}?)(?=[.;:])",
)


#: Third-party recognition, which is about a ranking rather than a business.
_ACCOLADE = re.compile(
    r"\b(?:strong performer|leader in the|magic quadrant|forrester wave|"
    r"gartner|named (?:a|the)|recognit?[sz]ed as|awarded|award[- ]winning|"
    r"ranked|rated|#\s*1|no\.\s*1|winner of|voted|top \d+|best[- ]in[- ]class"
    r")\b", re.I)


def _self_description(text: str, company: str):
    """(sentence, quoted span) -- how this company describes itself, or None.

    Anchored on the company's own name so a competitor's self-description in
    the same corpus can never be read as this company's. Returns the clause
    AFTER the verb, because "Highspot is" carries nothing and "the sales
    enablement platform that increases the performance of revenue teams"
    carries everything.
    """
    name = str(company or "").strip()
    if not name:
        return None
    # The distinctive leading token, so "Monte Carlo Data" also matches the
    # "Monte Carlo is..." its own pages actually write. A GENERIC leading word
    # is refused: "Point B" must never be matched on "Point", and the recorded
    # case is "Bank of America" becoming the term "Bank".
    words = name.split()
    variants = [name]
    # PROGRESSIVELY SHORTER PREFIXES, longest first. "Monte Carlo Data" is
    # written "Monte Carlo" on its own pages, and a whole-name-only match
    # found nothing for it. A TWO-WORD prefix is always safe -- two words are
    # already a distinctive name. A ONE-WORD prefix is admitted only when it
    # is long and not a generic leading word, because the recorded collision
    # is "Bank of America" being matched as the term "Bank".
    for cut in range(len(words) - 1, 1, -1):
        variants.append(" ".join(words[:cut]))
    if len(words) > 1:
        head = words[0]
        if len(head) >= 5 and head.lower() not in (
                "point", "bank", "first", "general", "united", "american",
                "national", "global", "cloud", "prime", "alpha", "linear",
                "apple", "oracle", "delta", "chase", "union", "royal"):
            variants.append(head)
    for variant in variants:
        for template in _SELF_PATTERNS:
            pattern = re.compile(
                template.format(name=re.escape(variant)), re.I)
            m = pattern.search(text)
            if m is None:
                continue
            phrase = " ".join(m.group(1).split())
            if len(phrase.split()) < 3:
                continue
            # A TESTIMONIAL IS NOT A SELF-DESCRIPTION. Measured on Cyera's own
            # site: a customer quote reading "what Cyera gives me is almost
            # immeasurable" matched the verb pattern and would have been
            # printed to an executive as "in its own words". Two tells, both
            # grammatical rather than semantic: the clause opens on a personal
            # pronoun, or it carries its own finite verb in the first few
            # words, which means the match cut across a clause boundary.
            head = phrase.split()
            if head[0].lower() in ("me", "us", "you", "them", "him", "her",
                                   "my", "your", "their", "his", "our"):
                continue
            if any(w.lower() in ("is", "was", "are", "were", "has", "have")
                   for w in head[:3]):
                continue
            # AN ACCOLADE IS NOT A DESCRIPTION OF A BUSINESS. Measured on
            # Druva's own site: "Druva is a Strong Performer in The Forrester
            # Wave" matched perfectly and would have been printed to an
            # executive as what the company IS. It is a third party's rating,
            # in the same family as the customer testimonial this filter
            # already refuses -- grammatically a self-description, and about
            # how the company was ranked rather than about what it sells.
            if _ACCOLADE.search(phrase):
                continue
            # THE WHOLE CLAUSE, VERB INCLUDED, so it can be QUOTED rather than
            # paraphrased. Returning the object alone produced "BigID
            # describes itself as organizations discover and govern their
            # data" -- a sentence with the verb removed from the middle of
            # it. A quotation cannot be ungrammatical, because it is what the
            # company wrote.
            said = " ".join(text[m.start():m.end()].split()).rstrip(" .,;:")
            from intent_engine.adaptive.spans import quote_around
            return said + ".", quote_around(text, m.start(), m.end(),
                                            max_chars=280)
    return None


#: Words that are grammatically a capture but semantically furniture. A
#: capture list that admits "the following" and "a leading" produces a
#: strategic-asset list nobody would recognise as one.
_NOISE = {
    "following", "leading", "world", "best", "first", "new", "next",
    "same", "other", "more", "most", "many", "such", "these", "those",
    "company", "companies", "customers", "business", "solution",
    "solutions", "platform", "software", "team", "teams", "way", "ways",
    "time", "times", "data", "information", "content", "service",
    "services", "product", "products", "industry", "market",
}


def _clean_phrase(text: str) -> str:
    words = [w for w in re.split(r"\s+", str(text or "").strip()) if w]
    while words and words[0].lower() in ("a", "an", "the", "of", "for", "to"):
        words.pop(0)
    while words and words[-1].lower() in ("a", "an", "the", "of", "for", "to",
                                          "and", "or", "with", "in", "on"):
        words.pop()
    return " ".join(words).strip(" .,-")


#: Legal-form words that carry no identity, stripped before comparing names.
_LEGAL_FORMS = frozenset((
    "inc", "inc.", "incorporated", "llc", "ltd", "limited", "corp",
    "corporation", "co", "company", "plc", "gmbh", "sa", "nv", "ab", "as",
    "group", "holdings", "technologies", "software",
))


def _name_tokens(value: str) -> Tuple[str, ...]:
    """A name reduced to the words that identify it."""
    cleaned = re.sub(r"[^\w\s]", " ", str(value or "")).casefold()
    return tuple(t for t in cleaned.split() if t and t not in _LEGAL_FORMS)


def _is_the_subject(phrase: str, company: str) -> bool:
    """Is this extracted name the company we are analysing?

    MEASURED LIVE (Highspot, be5fde12). Its own page says "Partner with
    Highspot's services team", the dependency pattern matched `partners with`
    and captured the subject, and the report told Highspot's chief executive:

        "It names Highspot as something it depends on."

    A company is not its own dependency. The comparison is WHOLE TOKENS and
    prefix-wise in both directions -- "Monte Carlo" against "Monte Carlo
    Data" is still the subject -- and never a substring, because a substring
    wall refuses real companies ("alpha" inside "Alphabet") and invents
    false ones.
    """
    a, b = _name_tokens(phrase), _name_tokens(company)
    if not a or not b:
        return False
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return longer[:len(shorter)] == shorter


def _extract(patterns, text: str, *, limit: int = 6) -> Tuple[Tuple[str, str], ...]:
    """(phrase, quoted span) pairs, deduplicated, in order of appearance."""
    seen, out = set(), []
    for pattern in patterns:
        for m in pattern.finditer(text):
            phrase = _clean_phrase(m.group(1))
            if len(phrase) < 5 or len(phrase.split()) > 8:
                continue
            head = phrase.split()[0].lower()
            if head in _NOISE and len(phrase.split()) < 3:
                continue
            key = phrase.lower()
            if key in seen:
                continue
            seen.add(key)
            from intent_engine.adaptive.spans import quote_around
            out.append((phrase,
                        quote_around(text, m.start(), m.end(),
                                     max_chars=240)))
            if len(out) >= limit:
                return tuple(out)
    return tuple(out)


@dataclasses.dataclass(frozen=True)
class CompanyStrategicProfile:
    """What kind of business this is, how it makes money, and what reaches it.

    Every field is a `Fact`, so a reader (and the composer, and the genericity
    detector) can always tell a statement about THIS company from a statement
    about businesses of its kind.
    """
    # --- identity ---
    canonical_name: str = ""
    domain: str = ""
    identity: Fact = dataclasses.field(default_factory=Fact)
    industry: Fact = dataclasses.field(default_factory=Fact)
    #: how this company describes itself, in its own words
    self_description: Fact = dataclasses.field(
        default_factory=Fact)

    # --- how the money works ---
    business_model: Fact = dataclasses.field(default_factory=Fact)
    business_model_class: str = "UNKNOWN"
    customer_job: Fact = dataclasses.field(default_factory=Fact)
    economic_engine: Fact = dataclasses.field(default_factory=Fact)
    revenue_drivers: Tuple[str, ...] = ()
    cost_drivers: Tuple[str, ...] = ()
    margin_drivers: Fact = dataclasses.field(default_factory=Fact)
    capital_intensity: Fact = dataclasses.field(default_factory=Fact)
    pricing_model: Fact = dataclasses.field(default_factory=Fact)
    customer_structure: Fact = dataclasses.field(default_factory=Fact)

    # --- what it holds and what it leans on ---
    strategic_assets: Tuple[Fact, ...] = ()
    critical_dependencies: Tuple[Fact, ...] = ()
    data_assets: Tuple[Fact, ...] = ()

    # --- what reaches it ---
    competitive_structure: Fact = dataclasses.field(default_factory=Fact)
    regulatory_exposure: Fact = dataclasses.field(default_factory=Fact)
    technology_exposure: Fact = dataclasses.field(default_factory=Fact)
    macro_exposures: Tuple[str, ...] = ()
    operational_exposures: Tuple[str, ...] = ()

    # --- how it decides ---
    decision_cycles: Tuple[str, ...] = ()
    likely_executive_priorities: Tuple[str, ...] = ()
    current_strategic_tensions: Tuple[Fact, ...] = ()
    known_constraints: Tuple[str, ...] = ()
    potential_intent_engine_roles: Tuple[str, ...] = ()

    # --- epistemics ---
    confidence: str = "none"
    #: PROFILE_AVAILABLE | PROFILE_PARTIAL | PROFILE_EVIDENCE | PROFILE_SPARSE
    profile_state: str = "PROFILE_SPARSE"
    profile_source: str = "NONE"
    profile_limitation: str = ""
    evidence_refs: Tuple[str, ...] = ()
    provenance: str = ""
    uncertainty: Tuple[str, ...] = ()
    falsifiers: Tuple[str, ...] = ()
    information_gaps: Tuple[str, ...] = ()
    classification: Optional[EvidenceClassification] = None
    contract: str = CONTRACT

    # --- derived ---
    @property
    def known(self) -> bool:
        return self.business_model_class != "UNKNOWN"

    @property
    def specificity(self) -> float:
        """How much of this company was learned FROM this company.

        The number the whole design turns on, and the denominator is the
        whole of it.

        THE DENOMINATOR IS EVERY CANDIDATE FIELD, NOT THE POPULATED ONES.
        The first version divided by what happened to be filled in, and a
        profile that established exactly one thing -- the company's name --
        scored 1.000, the same as one that established twelve. Measured
        in-process: `company_specificity_score: 1.0` beside
        `business_model: UNKNOWN`, `primary_lens: ""` and zero decision
        opportunities. That number fed the composer and the
        differentiation flag, so the emptiest possible profile was reported
        as the most specific one there could be.

        Coverage and provenance are the same question here: "how much of
        this reading is about this company" has to fall when we learned
        little, not only when we learned the wrong kind of thing.
        """
        single = (self.identity, self.industry, self.self_description,
                  self.business_model,
                  self.customer_job, self.economic_engine, self.margin_drivers,
                  self.capital_intensity, self.pricing_model,
                  self.customer_structure, self.competitive_structure,
                  self.regulatory_exposure, self.technology_exposure)
        grouped = (self.strategic_assets, self.critical_dependencies,
                   self.data_assets, self.current_strategic_tensions)
        specific = sum(1 for f in single if f.company_specific)
        specific += sum(1 for group in grouped
                        if any(f.company_specific for f in group))
        return round(specific / float(len(single) + len(grouped)), 3)

    @property
    def company_specific_fields(self) -> Tuple[str, ...]:
        out = []
        for name in ("identity", "industry", "self_description",
                     "business_model", "customer_job",
                     "economic_engine", "margin_drivers", "capital_intensity",
                     "pricing_model", "customer_structure",
                     "competitive_structure", "regulatory_exposure",
                     "technology_exposure"):
            if getattr(self, name).company_specific:
                out.append(name)
        for name in ("strategic_assets", "critical_dependencies",
                     "data_assets", "current_strategic_tensions"):
            if any(f.company_specific for f in getattr(self, name)):
                out.append(name)
        return tuple(out)

    def as_dict(self) -> dict:
        out = {}
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            if isinstance(value, Fact):
                out[field.name] = value.as_dict()
            elif isinstance(value, tuple):
                out[field.name] = [
                    v.as_dict() if isinstance(v, Fact) else v for v in value]
            elif isinstance(value, EvidenceClassification):
                out[field.name] = value.as_dict()
            else:
                out[field.name] = value
        out["specificity"] = self.specificity
        out["company_specific_fields"] = list(self.company_specific_fields)
        out["known"] = self.known
        return out


def _analyst_fact(analysis, key: str, *, basis: str) -> Fact:
    """One field of the analyst's evidence-cited business-model reconstruction.

    ANALYST provenance is company-specific because the critic already refused
    any claim without a cited observation and any figure without a ledger
    fact. It is not the same as SUBJECT_EVIDENCE -- it is an inference from
    it -- and the two are kept apart so a reader can see which is which.
    """
    if analysis is None:
        return _unknown("no strategic reading was produced for this run")
    model = getattr(analysis, "business_model", None)
    if not isinstance(model, dict):
        model = (analysis or {}).get("business_model") \
            if isinstance(analysis, dict) else {}
    value = str((model or {}).get(key) or "").strip()
    if not value:
        return _unknown(f"the strategic reading did not establish {basis}")
    return Fact(value=value, provenance=ANALYST, basis=basis)


def build_profile(*, company: str, domain: str = "",
                  evidence_text: str = "",
                  intelligence_profile=None,
                  analysis=None,
                  observations=(),
                  documents=(),
                  identity_line: str = "") -> CompanyStrategicProfile:
    """Compose the canonical profile from everything this run holds.

    `intelligence_profile` is `company_profile.CompanyIntelligenceProfile` --
    the manifest/SIC classifier's answer, which OUTRANKS the evidence
    classifier and is used whenever it produced one. The evidence classifier
    fills the case both of the existing two refuse, which is every private
    company.

    `analysis` is the verified `StrategicAnalysis`, whose business-model
    reconstruction is evidence-cited and critic-checked.
    """
    body = str(evidence_text or "")[:200_000]
    name = str(company or "").strip()
    ip = intelligence_profile

    # --- what kind of business, in strict order of authority ----------------
    classification = None
    model_class = str(getattr(ip, "business_model_class", "") or "UNKNOWN")
    # READ IT BACK EVEN WHEN `profile_for` ALREADY DID THE WORK.
    #
    # Once the third classifier moved inside `profile_for`, `ip.known` became
    # True for exactly the companies this layer exists to serve, so the branch
    # below stopped running and `classification` stayed None -- taking the
    # confidence and the quoted span out of telemetry with it. Measured live:
    # `business_model: SUBSCRIPTION_SOFTWARE` beside an empty
    # `business_model_confidence` and an empty `business_model_evidence`, so
    # the matrix could report WHAT was decided and never HOW. It is a pure
    # function over text already in memory.
    if str(getattr(ip, "profile_source", "")) == "SUBJECT_EVIDENCE" and body:
        classification = classify_from_evidence(body)
    state = str(getattr(ip, "profile_state", "") or "PROFILE_SPARSE")
    source = str(getattr(ip, "profile_source", "") or "NONE")
    limitation = str(getattr(ip, "profile_limitation", "") or "")
    if not (ip is not None and getattr(ip, "known", False)):
        classification = classify_from_evidence(body)
        if classification.known:
            model_class = classification.model_class
            state = "PROFILE_EVIDENCE"
            source = "SUBJECT_EVIDENCE"
            limitation = (
                "Read from this company's own published account of what it "
                "sells and how it is paid, rather than from a regulator's "
                "industry code -- this company does not file one. The "
                "business model is therefore established and the analysis is "
                "selected for it; the within-industry detail a filing would "
                "carry (capital intensity, demand cyclicality, regulatory "
                "regime) is not, and is shown as not established.")
            # THE ECONOMICS COME FROM THE CLASS THE EVIDENCE SELECTED. That
            # is a class prior and it is tagged as one everywhere below; what
            # it is NOT is a different company's economics, because the class
            # was chosen by this company's own sentence about its revenue.
            try:
                from intent_engine.executive import company_profile as CP
                econ = CP._ECONOMICS.get(model_class)
                if econ is not None:
                    ip = CP.CompanyIntelligenceProfile(
                        company_id=name, company_name=name, known=True,
                        profile_state="PROFILE_PARTIAL",
                        profile_source="SUBJECT_EVIDENCE",
                        profile_limitation=limitation,
                        basis=(f"classified from this company's own published "
                               f"statement of how it is paid: "
                               f"{classification.evidence_span[:160]}"),
                        sector=str(getattr(ip, "sector", "") or "UNKNOWN"),
                        business_model_class=model_class,
                        business_model=econ["business_model"],
                        industry_structure=econ["industry_structure"],
                        primary_revenue_drivers=tuple(econ["revenue_drivers"]),
                        primary_cost_drivers=tuple(econ["cost_drivers"]),
                        demand_model=econ["demand_model"],
                        customer_structure=econ["customer_structure"],
                        supplier_structure=econ["supplier_structure"],
                        pricing_model=econ["pricing_model"],
                        operating_leverage=econ["operating_leverage"],
                        relevant_macro_channels=tuple(
                            c for c in econ["macro"]
                            if (c, model_class) in CP._TRANSMISSION),
                        primary_management_levers=tuple(econ["levers"]),
                        decision_archetypes=tuple(econ["archetypes"]),
                    )
            except Exception:                                # noqa: BLE001
                pass
        else:
            limitation = (
                "What kind of business this is has not been established. "
                + classification.reason.capitalize()
                + ". The reading below is selected from the published record "
                  "alone and does not use this company's business model to "
                  "decide what is worth asking.")

    prior = f"a {model_class.replace('_', ' ').lower()} business" \
        if model_class != "UNKNOWN" else "a business of this kind"

    # --- the fields ---------------------------------------------------------
    self_said = _self_description(body, name)
    self_description = (
        Fact(value=self_said[0], provenance=SUBJECT_EVIDENCE,
             basis="how this company describes itself, in its own words",
             evidence=self_said[1])
        if self_said else
        _unknown("this company's own material does not carry a sentence "
                 "describing what it is"))

    identity = (Fact(value=identity_line, provenance=SUBJECT_EVIDENCE,
                     basis="the canonical subject line for this run")
                if identity_line else
                _unknown("no canonical identity line was composed"))

    industry = (Fact(value=str(getattr(ip, "sector", "") or "").replace(
                        "_", " ").lower(),
                     provenance=(MANIFEST if source == "VALIDATION_MANIFEST"
                                 else SUBJECT_EVIDENCE),
                     basis=f"the {source.replace('_', ' ').lower()} "
                           f"classification of this company")
                if str(getattr(ip, "sector", "") or "UNKNOWN") != "UNKNOWN"
                else _unknown("no sector classification was established"))

    business_model = _analyst_fact(
        analysis, "one_line", basis="what it sells, to whom, and how it is paid")
    if not business_model and getattr(ip, "business_model", "UNKNOWN") not in (
            "", "UNKNOWN"):
        business_model = Fact(
            value=str(ip.business_model), provenance=CLASS_PRIOR,
            basis=f"the structural economics of {prior}")
    if not business_model:
        business_model = _unknown(
            "neither this company's own material nor a strategic reading "
            "established how it is paid")

    customer_job = _analyst_fact(
        analysis, "what_customers_actually_buy",
        basis="the job customers are actually paying for")
    economic_engine = _analyst_fact(
        analysis, "where_profit_comes_from", basis="where profit comes from")
    margin_drivers = _analyst_fact(
        analysis, "where_value_leaks",
        basis="where value is created and not captured")
    if not margin_drivers and getattr(ip, "operating_leverage",
                                      "UNKNOWN") not in ("", "UNKNOWN"):
        margin_drivers = Fact(
            value=str(ip.operating_leverage), provenance=CLASS_PRIOR,
            basis=f"the operating leverage of {prior}")

    def _prior_fact(attr, what) -> Fact:
        value = str(getattr(ip, attr, "") or "UNKNOWN")
        if value in ("", "UNKNOWN"):
            return _unknown(f"{what} has not been established for this company")
        return Fact(value=value, provenance=CLASS_PRIOR,
                    basis=f"the {what} of {prior}")

    capital_intensity = _prior_fact("capital_intensity", "capital intensity")
    pricing_model = _prior_fact("pricing_model", "pricing model")
    customer_structure = _prior_fact("customer_structure",
                                     "customer structure")
    competitive_structure = _prior_fact("industry_structure",
                                        "industry structure")
    regulatory_exposure = _prior_fact("regulatory_exposure",
                                      "regulatory exposure")

    # --- what this company itself claims to hold and to lean on -------------
    assets = tuple(
        Fact(value=phrase, provenance=SUBJECT_EVIDENCE,
             basis="claimed by this company in its own published material",
             evidence=span)
        for phrase, span in _extract(_ASSET_PATTERNS, body))
    dependencies = tuple(
        Fact(value=phrase, provenance=SUBJECT_EVIDENCE,
             basis="named by this company as something it builds on, "
                   "integrates with or partners with",
             evidence=span)
        for phrase, span in _extract(_DEPENDENCY_PATTERNS, body)
        # A COMPANY IS NOT ITS OWN DEPENDENCY. "Partner with Highspot's
        # services team" is the subject talking about itself.
        if not _is_the_subject(phrase, company))

    data_assets = ()
    if re.search(r"\b(?:our|proprietary)\s+(?:data|dataset|database|index|"
                 r"graph|corpus)\b", body, re.I):
        m = re.search(r"[^.]*\b(?:our|proprietary)\s+(?:data|dataset|"
                      r"database|index|graph|corpus)\b[^.]*\.", body, re.I)
        data_assets = (Fact(
            value="a proprietary data asset this company claims as its own",
            provenance=SUBJECT_EVIDENCE,
            basis="this company describes a dataset it owns",
            evidence=" ".join((m.group(0) if m else "").split())[:280]),)

    technology_exposure = (
        Fact(value=("this company's own material describes its product in "
                    "terms of AI or machine learning, so a change in what "
                    "those systems can do reaches its offer directly"),
             provenance=SUBJECT_EVIDENCE,
             basis="this company describes its own product in AI terms",
             evidence=" ".join(
                 (re.search(r"[^.]*\b(?:artificial intelligence|machine "
                            r"learning|\bAI\b|generative)\b[^.]*\.", body)
                  or re.match("", "")).group(0).split() if re.search(
                     r"\b(?:artificial intelligence|machine learning|\bAI\b|"
                     r"generative)\b", body) else [])[:280])
        if re.search(r"\b(?:artificial intelligence|machine learning|\bAI\b|"
                     r"generative)\b", body)
        else _unknown("this company's material does not describe its product "
                      "in terms of AI, so no direct technology exposure is "
                      "asserted"))

    tensions = ()
    tension = {}
    if analysis is not None:
        insight = getattr(analysis, "the_insight", None)
        if not isinstance(insight, dict) and isinstance(analysis, dict):
            insight = analysis.get("the_insight")
        tension = (insight or {}).get("tension") or {}
    if tension.get("side_a") and tension.get("side_b"):
        tensions = (Fact(
            value=(f"{tension['side_a']} against {tension['side_b']}"),
            provenance=ANALYST,
            basis="the trade-off this company's own evidence shows it "
                  "managing",
            evidence=str(tension.get("why_it_exists") or "")),)

    gaps = tuple(str(g) for g in (getattr(analysis, "evidence_gaps", ())
                                  or ()) if str(g).strip())[:5]
    falsifiers = tuple(
        str(a.get("what_would_break_it")) for a in
        (getattr(analysis, "assumptions", ()) or ())
        if isinstance(a, dict) and str(a.get("what_would_break_it") or "").strip()
    )[:3]

    # WHAT THIS COMPANY'S LEADERSHIP IS LIKELY WEIGHING.
    #
    # Declared on this object from the first version and written by nothing,
    # which is the "declared kind with no detector" failure in miniature: a
    # field that is always empty reads to every consumer as "this company has
    # no executive priorities" rather than as "nobody computed any".
    #
    # Drawn from the DECISIONS THE EVIDENCE RAISED where there are any, and
    # from the class's own management levers where there are not -- and the
    # two are never mixed silently, because the first is about this company
    # and the second is about businesses like it.
    priorities = []
    for d in (getattr(analysis, "decisions", ()) or ()):
        if not isinstance(d, dict):
            continue
        text = str(d.get("decision") or "").strip()
        if text:
            priorities.append(text.rstrip("."))
    if priorities:
        priority_basis = "raised by this company's own evidence"
    else:
        priorities = [str(lever) for lever in
                      (getattr(ip, "primary_management_levers", ()) or ())][:4]
        priority_basis = ("the levers a business of this kind has, since the "
                          "evidence raised no decision of its own")

    refs = tuple(
        str(o.get("observation_id")) for o in (observations or ())
        if isinstance(o, dict) and o.get("observation_id"))[:24]

    confidence = ("high" if state in ("PROFILE_AVAILABLE",) and analysis
                  else "moderate" if model_class != "UNKNOWN" and analysis
                  else "low" if model_class != "UNKNOWN"
                  else "none")

    profile = CompanyStrategicProfile(
        canonical_name=name, domain=str(domain or ""),
        identity=identity, industry=industry,
        self_description=self_description,
        business_model=business_model, business_model_class=model_class,
        customer_job=customer_job, economic_engine=economic_engine,
        revenue_drivers=tuple(getattr(ip, "primary_revenue_drivers", ()) or ()),
        cost_drivers=tuple(getattr(ip, "primary_cost_drivers", ()) or ()),
        margin_drivers=margin_drivers, capital_intensity=capital_intensity,
        pricing_model=pricing_model, customer_structure=customer_structure,
        strategic_assets=assets, critical_dependencies=dependencies,
        data_assets=data_assets, competitive_structure=competitive_structure,
        regulatory_exposure=regulatory_exposure,
        technology_exposure=technology_exposure,
        macro_exposures=tuple(getattr(ip, "relevant_macro_channels", ()) or ()),
        operational_exposures=tuple(
            getattr(ip, "primary_management_levers", ()) or ()),
        decision_cycles=tuple(getattr(ip, "decision_archetypes", ()) or ()),
        likely_executive_priorities=tuple(priorities[:4]),
        current_strategic_tensions=tensions,
        known_constraints=gaps,
        potential_intent_engine_roles=(),
        confidence=confidence, profile_state=state, profile_source=source,
        profile_limitation=limitation, evidence_refs=refs,
        provenance=(f"business model {model_class} from "
                    f"{source.replace('_', ' ').lower()}; executive "
                    f"priorities {priority_basis}"),
        uncertainty=gaps, falsifiers=falsifiers, information_gaps=gaps,
        classification=classification,
    )
    return profile
