"""The allow-lists the query language compiles from (brief 10.2, 5.4).

Every column name that reaches SQL comes from this table; no caller text is ever spliced into
SQL. Operators map to SQL through :data:`SQL_OPS`, never through the caller's string.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

FieldKind = Literal["text", "int", "bool", "datetime"]


@dataclass(frozen=True)
class Field:
    """One queryable envelope column of ``cur_core_record``."""

    name: str
    kind: FieldKind


ENVELOPE_FIELDS: dict[str, Field] = {
    f.name: f
    for f in (
        Field("id", "text"),
        Field("key", "text"),
        Field("type", "text"),
        Field("scope", "text"),
        Field("title", "text"),
        Field("description", "text"),
        Field("status", "text"),
        Field("voided", "bool"),
        Field("version", "int"),
        Field("last_seq", "int"),
        Field("effective_schema_hash", "text"),
        Field("conformance", "text"),
        Field("created_at", "datetime"),
        Field("updated_at", "datetime"),
    )
}

#: Envelope columns a result may be ordered by (everything but the boolean).
SORTABLE_FIELDS: frozenset[str] = frozenset(
    name for name, f in ENVELOPE_FIELDS.items() if f.kind != "bool"
)

#: Comparison operators the language knows, mapped to the SQL text they compile to.
SQL_OPS: dict[str, str] = {
    "=": "=",
    "!=": "<>",
    "<": "<",
    "<=": "<=",
    ">": ">",
    ">=": ">=",
}

#: Operators allowed per kind. ``~`` (contains) is for text only.
OPS_BY_KIND: dict[FieldKind, frozenset[str]] = {
    "text": frozenset({"=", "!=", "~", "<", "<=", ">", ">="}),
    "int": frozenset({"=", "!=", "<", "<=", ">", ">="}),
    "bool": frozenset({"=", "!="}),
    "datetime": frozenset({"=", "!=", "<", "<=", ">", ">="}),
}
PSET_OPS: frozenset[str] = frozenset({"=", "!=", "~", "<", "<=", ">", ">="})

#: ``psets.<pset>[.<section>].<property>`` as stored in ``cur_pset_values.path``: at least a pset
#: and a property after the ``psets`` head; each segment is letters, digits, ``_`` or ``-``.
_SEGMENT = r"[A-Za-z0-9_][A-Za-z0-9_-]*"
PSET_PATH_RE = re.compile(rf"^psets(?:\.{_SEGMENT}){{2,6}}$")

#: A relation code or a record type (aliases may be dotted: ``quality.NCR``).
RELATION_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
TYPE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)*")
TYPE_FULL_RE = re.compile(rf"^{TYPE_RE.pattern}$")

#: Statuses that make a link count as a link (brief 7.1, 7.3): suggestions are not links yet and
#: retracted links are over. See decision A8 in the plan.
LIVE_LINK_STATUSES: tuple[str, ...] = ("active", "stale", "broken")

MAX_INT = 2**63 - 1

#: Characters that end a field name or start an operator, and the two quote characters.
OP_CHARS = ":=!<>~"
QUOTES = "\"'"
