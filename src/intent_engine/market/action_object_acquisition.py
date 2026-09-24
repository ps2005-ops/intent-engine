"""Retrieve the families a plan chose, and measure what they actually yield.

WHAT THIS MEASURES, AND WHY IT IS NOT ACTION COUNT
--------------------------------------------------
Wave 6 counted actions per document and concluded Salesforce was productive:
6 documents, 12 actions. Every one of those actions established no object,
so the count was measuring the announcement patterns, not the source. The
metric that decides where to spend retrieval budget is

    ESTABLISHED_ACTION_OBJECT / DOCUMENT

and it is reported per family, per subject, so a family that works for one
rival and not another is visible as exactly that.

A STATIC PRICE IS NOT A PRICE CHANGE
------------------------------------
This is the distinction the pricing family lives or dies on. A pricing page
states what a plan costs today. That is a fact about the world and it is not
an action: nobody did anything, no date attaches to it, and no counterparty
could respond to it. A pricing UPDATE page — "Starting June 1, 2026,
BigCommerce is updating its plan structure" — is an action, establishes its
own object, and carries an effective date.

The acquisition therefore retrieves pricing pages for their OBJECT-BEARING
language and admits an action only where the announcement gate fires. A
family can be excellent at establishing objects and produce no actions at
all, and those two numbers are reported separately for that reason.
"""
from __future__ import annotations

import collections
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urldefrag, urljoin, urlparse

from . import action_object_queries as Q
from . import competitive_actions as CA
from . import competitive_objects as CO

CONTRACT = "action_object_acquisition.v1"

#: Below this, a retrieved page is boilerplate or an error shell.
MIN_DOCUMENT_CHARS = 400

#: How far a page's own links are followed looking for the family's members.
MAX_PAGES_PER_FAMILY = 6


@dataclass(frozen=True)
class RetrievedDocument:
    document_id: str
    family: str
    actor: str
    url: str
    title: str
    text: str
    retrieved_at: str
    #: When the PAGE says it was published or last changed. Distinct from
    #: `retrieved_at`, which is when we looked. Empty when the page does
    #: not say — an index page usually does not, an entry page usually
    #: does, and that difference is why entry pages can be ordered.
    published_at: str = ""


@dataclass
class FamilyYield:
    """Every field is a count, and the ratio that matters is derived."""
    family: str
    actor: str = ""
    attempted: int = 0
    retrieved: int = 0
    actions_found: int = 0
    objects_established: int = 0
    objects_partial: int = 0
    objects_unknown: int = 0
    substitutes_named: int = 0
    #: The same announcement met again on another page of the same family.
    #: Kept because "we saw it five times" and "there were five of them"
    #: are opposite findings about the same number.
    duplicate_action_sightings: int = 0
    latency_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    refusal_reasons: Dict[str, int] = field(default_factory=dict)

    @property
    def established_per_document(self) -> float:
        if not self.retrieved:
            return 0.0
        return self.objects_established / self.retrieved

    @property
    def actions_per_document(self) -> float:
        if not self.retrieved:
            return 0.0
        return self.actions_found / self.retrieved

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "family": self.family, "actor": self.actor,
            "attempted": self.attempted, "retrieved": self.retrieved,
            "actions_found": self.actions_found,
            "objects_established": self.objects_established,
            "objects_partial": self.objects_partial,
            "objects_unknown": self.objects_unknown,
            "substitutes_named": self.substitutes_named,
            "duplicate_action_sightings": self.duplicate_action_sightings,
            "established_per_document": round(
                self.established_per_document, 4),
            "actions_per_document": round(self.actions_per_document, 4),
            "latency_seconds": round(self.latency_seconds, 2),
            "errors": self.errors[:5],
            "refusal_reasons": dict(sorted(self.refusal_reasons.items())),
        }


def _canonical(url: str) -> str:
    """One page is one document, whatever anchor you arrived through.

    A fragment identifies a POSITION INSIDE a document and never a different
    document. Following in-page links produced
    `/updates`, `/updates#main`, `/updates#one-page-checkout` ... as five
    separate retrievals of one page, which multiplied the denominator of
    every yield in the wave-8 grid by up to 4.5.
    """
    return urldefrag(url)[0].rstrip("/")


def _seeds(home_url: str, family: str) -> Tuple[str, ...]:
    base = home_url.rstrip("/")
    return tuple(_canonical(base + fragment) for fragment in Q.paths_for(family))


def retrieve(actor: str, home_url: str, family: str, *,
             as_of: str, fetcher: Optional[Callable] = None,
             max_pages: int = MAX_PAGES_PER_FAMILY
             ) -> Tuple[Tuple[RetrievedDocument, ...], FamilyYield]:
    """Fetch one family for one actor, following the family's own links once.

    The hop matters for pricing and migration: the page that ANNOUNCES a
    change is routinely one link below the page that states the current
    state, and the announcement is the only one of the two that is an action.
    """
    from intent_engine.company_ingestion import fetch as F
    from intent_engine.company_ingestion import parsing as P

    read = fetcher or (lambda url, **kw: F.safe_fetch(url, **kw))
    host = urlparse(home_url).hostname or ""
    report = FamilyYield(family=family, actor=actor)
    started = time.monotonic()

    frontier: List[str] = list(_seeds(home_url, family))
    seen: set = set()
    bodies: set = set()
    out: List[RetrievedDocument] = []

    while frontier and len(out) < max_pages:
        url = _canonical(frontier.pop(0))
        if url in seen:
            continue
        seen.add(url)
        report.attempted += 1
        try:
            result = read(url)
        except Exception as exc:                            # noqa: BLE001
            report.errors.append(f"{type(exc).__name__} on {url}")
            continue
        if not (result or {}).get("ok"):
            report.refusal_reasons["fetch_not_ok"] = \
                report.refusal_reasons.get("fetch_not_ok", 0) + 1
            continue
        parsed = P.parse_html(result.get("body") or result.get("text") or "")
        text = " ".join(str(parsed.get("text") or "").split())
        if len(text) < MIN_DOCUMENT_CHARS:
            report.refusal_reasons["too_short_to_be_a_document"] = \
                report.refusal_reasons.get(
                    "too_short_to_be_a_document", 0) + 1
            continue
        # Two URLs, one document. `/releases` and
        # `/products/innovation/releases` returned byte-identical text, which
        # the fragment rule cannot see: the paths genuinely differ. Content
        # identity is the only thing that settles it, and counting both would
        # inflate the denominator exactly as the anchors did.
        fingerprint = str(parsed.get("content_hash") or "") or text[:2000]
        if fingerprint in bodies:
            report.refusal_reasons["same_document_at_another_url"] = \
                report.refusal_reasons.get("same_document_at_another_url", 0) + 1
            continue
        bodies.add(fingerprint)

        report.retrieved += 1
        out.append(RetrievedDocument(
            document_id=f"{family}:{url}", family=family, actor=actor,
            url=url, title=str(parsed.get("title") or ""), text=text,
            retrieved_at=as_of[:10],
            published_at=str(parsed.get("modified_date") or "")[:10]))

        # One hop, and only to members of the SAME family, so a pricing page
        # can reach the pricing-update page without wandering onto the blog.
        if len(out) < max_pages:
            for link in (parsed.get("links") or []):
                href = link if isinstance(link, str) else (
                    link or {}).get("href", "")
                if not href:
                    continue
                target = _canonical(urljoin(url, href))
                if urlparse(target).hostname != host:
                    continue
                if Q.family_of(target) == family and target not in seen:
                    frontier.append(target)

    report.latency_seconds = time.monotonic() - started
    return tuple(out), report


def actions_and_objects(document: RetrievedDocument, *,
                        competitive_object_label: str = "",
                        other_actors: Sequence[str] = ()
                        ) -> Tuple[Tuple[CA.CompetitiveAction, ...],
                                   Dict[str, CO.CompetitiveObject],
                                   Dict[str, int]]:
    """Pull actions from a document, then read each action's OWN object.

    `competitive_object_label` is passed through to the action record only
    because `CompetitiveAction` carries the field; it is marked
    `object_established=False` unless the DOCUMENT established one, and the
    relevance check refuses the label outright. The object below comes from
    `CO.extract`, which cannot receive it.
    """
    found, refused = CA.extract(
        document.text, actor=document.actor,
        competitive_object=competitive_object_label,
        event_time=document.retrieved_at, source=document.url,
        source_family=document.family, other_actors=other_actors)
    objects: Dict[str, CO.CompetitiveObject] = {}
    for act in found:
        obj, _evidence = CO.extract(
            act.span, action_id=act.action_id, actor=act.actor,
            source=document.url, created_at=act.event_time,
            evidence_ids=act.evidence_ids, action_type=act.action_type)
        if obj is not None:
            objects[act.action_id] = obj
    return found, objects, refused


def measure(subjects: Sequence[Tuple[str, str]], families: Sequence[str], *,
            as_of: str, fetcher: Optional[Callable] = None,
            max_pages: int = MAX_PAGES_PER_FAMILY
            ) -> Tuple[Dict[str, FamilyYield],
                       List[CA.CompetitiveAction],
                       Dict[str, CO.CompetitiveObject]]:
    """Run the whole retrieval → action → object path and count everything.

    `subjects` is (actor, home_url). The home URL is an ADDRESS — the same
    kind of fact as the universe's `website` field — and asserts nothing
    about anybody's competitive position.
    """
    yields: Dict[str, FamilyYield] = {}
    all_actions: List[CA.CompetitiveAction] = []
    all_objects: Dict[str, CO.CompetitiveObject] = {}

    for actor, home_url in subjects:
        for family in families:
            documents, report = retrieve(
                actor, home_url, family, as_of=as_of, fetcher=fetcher,
                max_pages=max_pages)
            # An announcement is one action however many pages carry it.
            # `action_id` was ALREADY stable across duplicate retrievals and
            # nothing counted on it: the wave-8 grid reported 5 established
            # objects that were five readings of one sentence, and
            # `all_objects` — a dict keyed by action_id — had been silently
            # deduping to 1 the whole time while the counters said 5.
            counted: set = set()
            # Every OTHER subject in the run is a name this measurement
            # already knows. It may only remove a misattribution.
            others = [name for name, _ in subjects if name != actor]
            for document in documents:
                actions, objects, refused = actions_and_objects(
                    document, other_actors=others)
                for key, count in refused.items():
                    report.refusal_reasons[key] = \
                        report.refusal_reasons.get(key, 0) + count
                for act in actions:
                    if act.action_id in counted:
                        report.duplicate_action_sightings += 1
                        continue
                    counted.add(act.action_id)
                    report.actions_found += 1
                    obj = objects.get(act.action_id)
                    if obj is None:
                        report.objects_unknown += 1
                    elif obj.standing == CO.ESTABLISHED:
                        report.objects_established += 1
                    elif obj.standing == CO.PARTIAL:
                        report.objects_partial += 1
                    else:
                        report.objects_unknown += 1
                    if obj is not None and obj.substitute:
                        report.substitutes_named += 1
                    all_actions.append(act)
                all_objects.update(objects)
            yields[f"{actor}|{family}"] = report
    return yields, all_actions, all_objects


def performance_table(yields: Dict[str, FamilyYield]
                      ) -> Dict[str, Tuple[int, int]]:
    """Collapse to family -> (established, retrieved), which is what the
    planner ranks on. Subjects are summed: a family's editorial purpose does
    not change between vendors, and separating them here would give every
    cell a sample of one."""
    table: Dict[str, List[int]] = collections.defaultdict(lambda: [0, 0])
    for report in yields.values():
        table[report.family][0] += report.objects_established
        table[report.family][1] += report.retrieved
    return {family: (pair[0], pair[1]) for family, pair in table.items()}


def summarise(yields: Dict[str, FamilyYield]) -> dict:
    by_family: Dict[str, List[int]] = collections.defaultdict(
        lambda: [0, 0, 0, 0])
    for report in yields.values():
        row = by_family[report.family]
        row[0] += report.attempted
        row[1] += report.retrieved
        row[2] += report.actions_found
        row[3] += report.objects_established
    ranked = sorted(by_family.items(),
                    key=lambda kv: (-(kv[1][3] / kv[1][1] if kv[1][1] else 0),
                                    kv[0]))
    return {
        "contract": CONTRACT,
        "cells": len(yields),
        "documents_retrieved": sum(r.retrieved for r in yields.values()),
        "actions_found": sum(r.actions_found for r in yields.values()),
        "objects_established": sum(r.objects_established
                                   for r in yields.values()),
        "objects_partial": sum(r.objects_partial for r in yields.values()),
        "by_family": {
            family: {
                "attempted": row[0], "retrieved": row[1],
                "actions": row[2], "established": row[3],
                "established_per_document": round(
                    row[3] / row[1], 4) if row[1] else None,
            } for family, row in ranked},
        "note": ("a static price is not a price change: a family may "
                 "establish objects and produce no actions, and the two "
                 "counts are reported separately for that reason"),
    }
