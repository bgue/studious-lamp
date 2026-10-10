"""Fail when an installed distribution is copyleft or has no declared licence (ADR-0006).

``python dev/tools/check_licences.py`` reads the licence metadata of every installed distribution
and exits 1 with one line per problem. It is part of ``just check``.

Rules (ADR-0006, decision 1 to 3):

* The workspace's own packages (names starting ``tl-``) are exempt.
* GPL, LGPL and AGPL distributions are refused. A distribution that is offered under several
  licences (an ``OR`` expression, or several licence classifiers, as docutils has) passes when at
  least one of them is permissive.
* MPL-2.0 is allowed only for the distributions in ``MPL_ALLOWED``.
* A distribution with no licence information is refused.
"""

from __future__ import annotations

import importlib.metadata as metadata
import re
import sys
from collections.abc import Iterable
from typing import NamedTuple

MPL_ALLOWED = frozenset({"certifi", "tqdm", "fqdn", "hypothesis"})
EXEMPT_PREFIX = "tl-"

COPYLEFT = re.compile(r"gpl|general public|affero|lesser general", re.IGNORECASE)
MPL = re.compile(r"\bmpl\b|mpl-|mozilla public", re.IGNORECASE)
PERMISSIVE = re.compile(
    r"\bmit\b|\bbsd|apache|\bisc\b|\bpsf\b|python software foundation|public domain|unlicense"
    r"|\bcc0|\bzlib\b|\b0bsd\b|\bhpnd\b|python-2\.0|\bw3c\b",
    re.IGNORECASE,
)
SHORT = 120  # a License field longer than this is licence text, not an identifier


class Dist(NamedTuple):
    name: str
    expression: str  # License-Expression, or ""
    license: str  # License field, or ""
    classifiers: tuple[str, ...]  # the "License :: ..." classifiers


def collect() -> list[Dist]:
    """One ``Dist`` per installed distribution (``importlib.metadata.distributions()``).

    ``name`` is ``meta["Name"]``; ``expression`` is the ``License-Expression`` header or ``""``;
    ``license`` is the ``License`` header or ``""``; ``classifiers`` are the ``Classifier`` headers
    that start with ``License``.
    """
    dists: list[Dist] = []
    for installed in metadata.distributions():
        meta = installed.metadata
        dists.append(
            Dist(
                name=meta["Name"],
                expression=meta.get("License-Expression") or "",
                license=meta.get("License") or "",
                classifiers=tuple(
                    c for c in (meta.get_all("Classifier") or ()) if c.startswith("License")
                ),
            )
        )
    return dists


def term_ok(term: str, name: str) -> bool:
    """One licence name. False if ``COPYLEFT`` matches (copyleft wins over everything). Otherwise,
    if ``MPL`` matches: True only when ``name.lower()`` is in ``MPL_ALLOWED``. Otherwise True when
    ``PERMISSIVE`` matches, else False (an unrecognised licence is refused)."""
    if COPYLEFT.search(term):
        return False
    if MPL.search(term):
        return name.lower() in MPL_ALLOWED
    return PERMISSIVE.search(term) is not None


def statement_ok(statement: str, name: str) -> bool:
    """A licence statement. Replace ``(`` and ``)`` with spaces. If the result is longer than
    ``SHORT`` it is licence text: return ``term_ok`` of its first 300 characters. Otherwise split on
    ``OR`` (``re.split(r"\\s+OR\\s+", ...)``): the statement passes when any alternative passes; an
    alternative is split on ``AND`` and passes when every part passes ``term_ok``."""
    text = statement.replace("(", " ").replace(")", " ")
    if len(text) > SHORT:
        return term_ok(text[:300], name)
    return any(
        all(term_ok(part.strip(), name) for part in re.split(r"\s+AND\s+", alternative))
        for alternative in re.split(r"\s+OR\s+", text)
    )


def statements(dist: Dist) -> list[str]:
    """The statements a distribution makes about its licence, in order: its ``expression`` if it
    has one, otherwise its ``license`` field unless that is empty or ``UNKNOWN`` (any case); then
    the last ``::``-separated segment of every classifier (stripped). Empty strings are dropped."""
    found: list[str] = []
    expression = dist.expression.strip()
    license_field = dist.license.strip()
    if expression:
        found.append(expression)
    elif license_field and license_field.upper() != "UNKNOWN":
        found.append(license_field)
    found.extend(c.split("::")[-1].strip() for c in dist.classifiers)
    return [s for s in found if s]


def problems(dists: Iterable[Dist]) -> list[str]:
    """One line per refused distribution, sorted by name (case-insensitive).

    A distribution whose name, lower-cased with ``_`` replaced by ``-``, starts with
    ``EXEMPT_PREFIX`` is skipped. With no statements the line is ``"<Name>: no licence declared"``.
    When no statement passes ``statement_ok`` (a distribution offered under several licences passes
    if any one does) the line is ``"<Name>: licence not allowed (<statements joined by '; '>)"``.
    ``<Name>`` is ``dist.name`` as given."""
    refused: list[tuple[str, str]] = []
    for dist in dists:
        if dist.name.lower().replace("_", "-").startswith(EXEMPT_PREFIX):
            continue
        found = statements(dist)
        if not found:
            refused.append((dist.name, f"{dist.name}: no licence declared"))
        elif not any(statement_ok(s, dist.name) for s in found):
            joined = "; ".join(found)
            refused.append((dist.name, f"{dist.name}: licence not allowed ({joined})"))
    refused.sort(key=lambda item: item[0].lower())
    return [line for _, line in refused]


def main() -> int:
    """Print every line of ``problems(collect())``. When there are any, also print
    ``"<n> licence problem(s); see docs/adr/0006-dependency-licences.md"`` and return 1.
    Otherwise print ``"licences ok"`` and return 0."""
    lines = problems(collect())
    for line in lines:
        print(line)
    if lines:
        print(f"{len(lines)} licence problem(s); see docs/adr/0006-dependency-licences.md")
        return 1
    print("licences ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
