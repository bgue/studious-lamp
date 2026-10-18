"""The triage suggestion engine: which domain and subtype a received item probably belongs to.

A pure function of the item's text and the domain definitions: no database, no clock, no model.
Each domain and each subtype lists the words and phrases that point to it (``triage_keywords`` and
``keywords`` in the domain file); the engine counts how many *different* keywords occur in the
subject and the body and picks the best. The suggestion is only a suggestion: a person confirms it
(``ConfirmTriage``) and an agent's call is a proposal a person accepts.

Matching is on whole words or phrases, ignoring case; a keyword in the subject counts double
(a letter's subject is what its writer thought it was about). Ties go to the domain named
``general`` when it is among the best, otherwise to the lowest code, so the answer never depends on
the order of the files. A text with no keyword at all gets the ``general`` domain (or the first
domain when there is none) with a score of 0 and says so.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

from tl_mod_correspondence.domains import DomainDefinition
from tl_mod_correspondence.names import DOMAIN_GENERAL

#: Only this much of the subject and the body is read.
MAX_SUBJECT_CHARS: Final = 500
MAX_BODY_CHARS: Final = 20_000
SUBJECT_WEIGHT: Final = 2


@dataclass(frozen=True)
class Suggestion:
    """The proposed domain and subtype, how sure the engine is, and why."""

    domain: str | None
    subtype: str | None
    score: int  # the winning domain's score; 0 means no keyword matched
    reasons: tuple[str, ...] = ()
    scores: dict[str, int] = field(default_factory=lambda: {})  # domain code to score


def _found(keyword: str, subject: str, body: str) -> int:
    """How much a keyword counts: ``SUBJECT_WEIGHT`` in the subject, 1 in the body only, else 0."""
    pattern = re.compile(rf"(?<![a-z0-9]){re.escape(keyword.lower())}(?![a-z0-9])")
    if pattern.search(subject):
        return SUBJECT_WEIGHT
    return 1 if pattern.search(body) else 0


def suggest(
    domains: Sequence[DomainDefinition], *, subject: str, body: str | None = None
) -> Suggestion:
    """The best domain and subtype for the text, or an empty suggestion when there are no domains.

    A domain's score is the sum of the weights of its distinct ``triage_keywords`` and of the
    distinct keywords of all its subtypes. Its subtype is the one with the highest keyword score;
    a tie, or no match, gives the domain's ``default_subtype``.
    """
    if not domains:
        return Suggestion(domain=None, subtype=None, score=0, reasons=("no domain is defined",))
    low_subject = subject[:MAX_SUBJECT_CHARS].lower()
    low_body = (body or "")[:MAX_BODY_CHARS].lower()
    scores: dict[str, int] = {}
    reasons: dict[str, list[str]] = {}
    subtype_scores: dict[str, dict[str, int]] = {}
    for domain in domains:
        total, why = 0, []
        for word in domain.triage_keywords:
            weight = _found(word, low_subject, low_body)
            if weight:
                total += weight
                why.append(f"{domain.code}: '{word}'")
        by_subtype: dict[str, int] = {}
        for subtype in domain.subtypes:
            own = 0
            for word in subtype.keywords:
                weight = _found(word, low_subject, low_body)
                if weight:
                    own += weight
                    why.append(f"{domain.code}/{subtype.code}: '{word}'")
            by_subtype[subtype.code] = own
            total += own
        scores[domain.code] = total
        reasons[domain.code] = why
        subtype_scores[domain.code] = by_subtype
    best = max(scores.values())
    leaders = sorted(code for code, score in scores.items() if score == best)
    code = DOMAIN_GENERAL if DOMAIN_GENERAL in leaders else leaders[0]
    if best == 0 and DOMAIN_GENERAL not in scores:
        code = sorted(scores)[0]
    chosen = next(d for d in domains if d.code == code)
    own = subtype_scores[code]
    top = max(own.values()) if own else 0
    winners = [s for s, n in own.items() if n == top]
    subtype = winners[0] if top > 0 and len(winners) == 1 else chosen.default_subtype
    why_not = ("no keyword matched; the default domain",) if best == 0 else ()
    return Suggestion(
        domain=code,
        subtype=subtype,
        score=best,
        reasons=tuple(reasons[code]) or why_not,
        scores=dict(sorted(scores.items())),
    )
