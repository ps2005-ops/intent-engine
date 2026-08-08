"""Refuse an unsupported number before the critic is asked to.

Two lines of defence, deliberately not one. This gate is a SCHEMA check: does
every figure in the analysis correspond to a fact in the ledger the analyst was
handed? The critic remains an independent verifier against the evidence itself
and is not weakened, replaced or consulted here -- if this gate were removed
tomorrow the critic would still reject the same claims.

The measured failure: 15 of 16 rejected figures existed in no retrieved byte.
The model was recalling them. A gate that runs before the critic makes that a
contract violation rather than a matter of prompt compliance.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from intent_engine.strategic_intelligence.numeric_ledger import (
    supported_values,
)

# Figures that carry no claim on their own and would only create noise:
# years, small ordinals, list counters, and the observation ids themselves.
_YEAR = re.compile(r"^(19|20)\d{2}$")
_TRIVIAL = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
            "100", "0.0", "1.0"}

# A WHOLE numeric token. The boundaries matter more than the digits:
#
#   * the lookbehind stops a match STARTING mid-number, which is what turned
#     "$1,058,226" into the phantom claims '058' and '226';
#   * the lookahead stops it ENDING mid-number, so "1,094,517" is one token.
#
# Both were live false positives: the gate reported figures the analysis never
# stated, on a run (ASML) the critic had passed clean.
_NUMBER = re.compile(
    r"(?<![\w.,$€£¥-])(?P<cur>[$€£¥])?"
    r"(?P<body>\d[\d,]*(?:\.\d+)?)\s?(?P<pct>%)?(?![\d,])")

# Identifier shapes whose digits are never a claim (obs-src-20260714).
_IDENTIFIER = re.compile(r"(?:obs|src|ev|nf|replay)[-_][A-Za-z0-9-]*", re.I)


@dataclass(frozen=True)
class NumericFinding:
    check: str
    severity: str
    message: str
    rejects: bool = True

    @property
    def where(self) -> str:
        return "numeric_contract"


def _candidate_numbers(text: str):
    scrubbed = _IDENTIFIER.sub(" ", text or "")
    for match in _NUMBER.finditer(scrubbed):
        raw = match.group(0).strip()
        bare = match.group("body").replace(",", "")
        if not bare or bare in _TRIVIAL or _YEAR.match(bare):
            continue
        try:
            value = float(bare)
        except ValueError:
            continue
        if abs(value) < 10:                # "3 decisions", "2 segments"
            continue
        yield raw, bare, value


def _walk(value, path="analysis"):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, sub in value.items():
            yield from _walk(sub, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for i, sub in enumerate(value):
            yield from _walk(sub, f"{path}[{i}]")


def validate_numeric_claims(analysis: dict, ledger) -> List[NumericFinding]:
    """Every stated figure must exist in the ledger. Returns findings."""
    allowed = supported_values(ledger)
    allowed_bare = {a.lstrip("$€£¥").rstrip("%").replace(",", "")
                    for a in allowed}
    findings: List[NumericFinding] = []
    seen = set()
    allowed_values = set()
    for fact in ledger:
        allowed_values.add(round(abs(fact.value), 6))
        # the figure as WRITTEN, before scale was applied ("$2.13 billion")
        try:
            allowed_values.add(round(abs(float(
                fact.raw.strip().lstrip("$€£¥").rstrip("%")
                .replace(",", ""))), 6))
        except ValueError:
            pass
    for path, text in _walk(analysis or {}):
        for raw, bare, value in _candidate_numbers(text):
            if raw in allowed or bare in allowed_bare:
                continue
            if round(abs(value), 6) in allowed_values:
                continue
            if bare in seen:
                continue
            seen.add(bare)
            findings.append(NumericFinding(
                check="unsupported_numeric_claim",
                severity="reject",
                message=(f"the figure {raw!r} is stated at {path} but appears "
                         f"in no numeric fact supplied to the analyst"),
            ))
    return findings
