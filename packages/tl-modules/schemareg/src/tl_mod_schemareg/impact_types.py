"""The shapes of the impact report (brief 27.4, 27.7; P1-I8-T03).

An impact report says what a change of the effective schema touches: the records that hold values
at changed paths, the promoted columns of the current-state tables, the regenerated views, the
mappings and reports that name a changed path, and the MCP tool schemas that change. It is made
from two effective schemas and the ``ImpactFacts`` read from the ledger, by the pure function
``tl_mod_schemareg.impact.impact_report``; nothing here touches a database.

The report is data a reviewer reads and an adopter acknowledges: ``digest`` is the SHA-256 of its
canonical JSON, so "I read this report" is a hash the adoption command checks.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict

Section = Literal["records", "columns", "views", "mappings", "reports", "mcp_schemas"]

#: Order of the sections in a report and in its counts.
SECTION_ORDER: tuple[Section, ...] = (
    "records",
    "columns",
    "views",
    "mappings",
    "reports",
    "mcp_schemas",
)

#: A report holds at most this many entries; ``truncated`` says when it was cut.
MAX_ENTRIES = 500

ReferenceKind = Literal["mapping", "rule", "endpoint", "enricher", "action", "report"]


@dataclass(frozen=True)
class Reference:
    """Something outside the registry that names a property path (a mapping, a rule, a report)."""

    kind: ReferenceKind
    name: str  # the thing's own name or key, for example the document schema code
    path: str  # a layer-aware path as written: ``psets.valve_data.size_in``


@dataclass(frozen=True)
class ImpactFacts:
    """What the ledger says about the paths of a change, gathered before the pure function runs.

    ``value_counts`` maps a layer-aware property path (``psets.valve_data.size_in``) to the number
    of records that hold a current value there, in the scope of the report. ``references`` are the
    things that name a path, found by scanning stored mappings, rules, endpoints, enrichers,
    actions and the registered reports. A path with no entry holds no value / is named by nothing.
    """

    value_counts: Mapping[str, int] = field(default_factory=lambda: {})
    references: Sequence[Reference] = ()


class ImpactEntry(BaseModel):
    """One thing the change touches."""

    model_config = ConfigDict(frozen=True)

    section: Section
    target: str  # what is touched: a path, a column, a view, a mapping or report name
    change: str  # why: a code such as ``property_removed`` or ``column_added``
    count: int | None = None  # records affected, where that has a meaning
    detail: str  # one sentence a person reads


class ImpactReport(BaseModel):
    """What a change of the effective schema of ``scope`` touches."""

    model_config = ConfigDict(frozen=True)

    scope: str
    old_hash: str | None  # None when there was no schema before
    new_hash: str
    changed_paths: tuple[
        str, ...
    ]  # sorted; the paths whose definition was added, removed or changed
    entries: tuple[ImpactEntry, ...]  # ordered by section, then target, then change
    counts: dict[str, int]  # entries per section that has any
    truncated: bool  # entries were cut at ``MAX_ENTRIES``

    @property
    def digest(self) -> str:
        """SHA-256 of the canonical JSON of the report."""
        return report_digest(self)


def report_digest(report: ImpactReport) -> str:
    body = json.dumps(
        report.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def empty_report(scope: str, old_hash: str | None, new_hash: str) -> ImpactReport:
    """A report that says nothing is touched."""
    return ImpactReport(
        scope=scope,
        old_hash=old_hash,
        new_hash=new_hash,
        changed_paths=(),
        entries=(),
        counts={},
        truncated=False,
    )


#: The sections whose entries name things other than property paths and record types: the
#: mappings, rules, enrichers, actions, endpoints and reports that use a path (ADR-0016 review F6).
NAMED_SECTIONS: tuple[Section, ...] = ("mappings", "reports")


def redact_names(report: ImpactReport) -> ImpactReport:
    """The report with the names of what uses a changed path replaced by counts.

    Who has a mapping, a rule or a report on a property is for those who administer them. Every
    other reader sees how many there are in each section and why, never the names. The digest of
    the redacted report is its own.
    """
    kept: list[ImpactEntry] = []
    grouped: dict[tuple[str, str], int] = {}
    for entry in report.entries:
        if entry.section in NAMED_SECTIONS:
            key = (entry.section, entry.change)
            grouped[key] = grouped.get(key, 0) + (entry.count or 1)  # a redacted entry counts n
        else:
            kept.append(entry)
    for (section, change), n in sorted(grouped.items()):
        kept.append(
            ImpactEntry(
                section=section,  # type: ignore[arg-type]
                target=f"{n} item(s)",
                change=change,
                count=n,
                detail=f"{n} {section} are affected; their names are shown to administrators",
            )
        )
    order = {name: i for i, name in enumerate(SECTION_ORDER)}
    kept.sort(key=lambda e: (order[e.section], e.target, e.change))
    return report.model_copy(update={"entries": tuple(kept)})
