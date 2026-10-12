"""Base reports of the engineering module (brief 12, 9 M2; P1-I1-T11).

Three views of a project's tags: how many there are by class and workflow state and how they
conform (``register_summary``), which of them still lack what their class requires
(``missing_psets``, evaluated live against the current effective schema, so a class that gained a
required pset shows at once), and which numbers break the numbering pattern
(``pattern_violations``). They read; nothing here writes. A tag that left service (state
``Superseded`` or ``Deleted``) is not reported.

STUB (P1-I1-T11): the three report functions raise NotImplementedError; the values, `_SUMMARY_SQL`
and the signatures are final. Each body has a STEPS comment. Implement them, then delete this
paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text
from tl_core.services.psets import conformance
from tl_core.uow import UnitOfWork

from tl_mod_engineering import registry
from tl_mod_engineering.names import TAG_TABLE

#: Conformance rules that mean "a value the record's class or state requires is missing".
MISSING_RULES = ("class_required", "required_in_state")


@dataclass(frozen=True)
class SummaryLine:
    class_code: str | None  # None: tags with no class
    status: str | None  # None: tags that never left the initial state
    tags: int
    ok: int  # tags whose stored conformance is ok or waived
    warning: int
    nonconformant: int


@dataclass(frozen=True)
class MissingIssue:
    path: str  # psets.valve_data or psets.valve_data.size_in
    rule: str  # class_required | required_in_state
    level: str  # warning | nonconformant
    message: str


@dataclass(frozen=True)
class MissingLine:
    number: str
    class_code: str | None
    status: str | None
    issues: list[MissingIssue]


@dataclass(frozen=True)
class ViolationLine:
    number: str
    number_status: str  # ok | violation
    problems: list[dict[str, Any]]  # {segment, rule, level, message}


_SUMMARY_SQL = text(
    "SELECT t.class_code AS class_code, r.status AS status, COUNT(*) AS tags, "
    "SUM(CASE WHEN r.conformance IN ('ok', 'waived') THEN 1 ELSE 0 END) AS ok, "
    "SUM(CASE WHEN r.conformance = 'warning' THEN 1 ELSE 0 END) AS warning, "
    "SUM(CASE WHEN r.conformance = 'nonconformant' THEN 1 ELSE 0 END) AS nonconformant "
    f"FROM {TAG_TABLE} t JOIN cur_core_record r ON r.id = t.id "
    "WHERE r.voided = :no AND t.scope = :scope "
    "AND (r.status IS NULL OR r.status NOT IN ('Superseded', 'Deleted')) "
    "GROUP BY t.class_code, r.status ORDER BY t.class_code, r.status"
)


def register_summary(conn: Connection, scope: str) -> list[SummaryLine]:
    """Tags in service by class and workflow state, with their stored conformance counts.

    Lines are ordered by class then state, a missing class or state first. Counts come from the
    conformance stored with the tag at its last write.
    """
    # STEPS
    # 1. rows = conn.execute(_SUMMARY_SQL, {"no": False, "scope": scope}).
    # 2. One SummaryLine per row: class_code, status, tags, ok, warning, nonconformant (the
    #    counts as int). The SQL already groups and orders.
    raise NotImplementedError


def missing_psets(uow: UnitOfWork, scope: str, *, level: str | None = None) -> list[MissingLine]:
    """Tags in service that lack a value their class or state requires, by number.

    Each tag is evaluated now against the scope's current effective schema (``conformance``). Only
    the issues of ``MISSING_RULES`` are listed; a tag with none is left out. With ``level``
    ("warning" or "nonconformant") only issues of that level count.
    """
    # STEPS
    # 1. For each tag of registry.list_tags(uow.conn(), scope, limit=100000) (ordered by number):
    #    report = conformance(uow, tag.id).
    # 2. issues = [MissingIssue(i.path, i.rule, i.level, i.message) for i in report.issues if
    #    i.rule in MISSING_RULES and (level is None or i.level == level)].
    # 3. If issues is not empty append MissingLine(tag.number, tag.class_code, tag.status, issues).
    # 4. return the lines.
    raise NotImplementedError


def pattern_violations(
    conn: Connection, scope: str, *, include_warnings: bool = False
) -> list[ViolationLine]:
    """Tags in service whose number breaks the numbering pattern, by number.

    These are tags stored with ``number_status`` ``violation`` (a legacy import). With
    ``include_warnings`` tags whose number is fine but carries a warning (a mnemonic that does not
    usually identify the class) are listed too.
    """
    # STEPS
    # 1. For each tag of registry.list_tags(conn, scope, limit=100000): include it when
    #    tag.number_status == "violation", or when include_warnings is true and tag.violations is
    #    not empty. A line is ViolationLine(tag.number, tag.number_status, tag.violations).
    # 2. return the lines (already in number order).
    raise NotImplementedError
