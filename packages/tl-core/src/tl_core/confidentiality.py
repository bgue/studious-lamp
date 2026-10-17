"""Confidentiality: who may read a record of which class (ADR-0016).

A module declares what it makes confidential (``ModuleSpec.confidential``). This file turns those
declarations into one SQL fragment that lists the records a viewer must not see, and into the small
helpers every read path uses. The rules, in short:

* classes are ``internal`` < ``restricted`` < ``privileged``; any other value is **hidden from
  everyone** and so is a confidential record that has no row in its module table;
* an agent reads ``internal``; a person reads ``internal``; a document controller or an admin also
  reads ``restricted``; ``privileged`` is read only by the accounts named in the module's clearance
  table (an admin is not special) and never by an agent;
* the viewer is held in a context variable whose default is the **lowest** clearance, so code that
  forgets to set it hides too much, never too little. The faces set it from the authenticated
  principal (``use_viewer(viewer_for(principal))``); code that must see everything (projectors,
  rebuilds, the derivation worker) does not use the filtered reads or runs under ``system_view()``.

``not_hidden(column)`` gives ``(sql, params)`` for a ``WHERE`` clause; ``is_hidden`` and
``require_visible`` answer for one record; ``hidden_among`` filters a small list in Python.
"""

from __future__ import annotations

from collections.abc import Generator, Iterable, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import Connection, bindparam, text

from tl_core.auth.types import Principal
from tl_core.ledger import Event
from tl_core.modules import ChildSource, ConfidentialSource, confidential_sources
from tl_core.services.errors import RecordNotFoundError

INTERNAL: Final = "internal"
RESTRICTED: Final = "restricted"
PRIVILEGED: Final = "privileged"
#: The classes, least strict first.
CLASSES: Final = (INTERNAL, RESTRICTED, PRIVILEGED)
#: The clearance level that reads each class that has one (``privileged`` has none: it is named).
_LEVELS: Final = {INTERNAL: 0, RESTRICTED: 1}
ACCOUNT_PARAM: Final = "_cf_acct"


@dataclass(frozen=True)
class Viewer:
    """Who is reading. ``level`` is 0 (internal) or 1 (restricted); ``account`` is the name a
    clearance row can carry, empty for a viewer that can never be named (an agent, the default)."""

    actor: str = ""
    level: int = 0
    account: str = ""
    system: bool = False


#: The viewer when nobody set one: reads ``internal`` only, can never be named.
LOWEST: Final = Viewer()
_SYSTEM: Final = Viewer(actor="system", level=1, account="", system=True)

_VIEWER: ContextVar[Viewer] = ContextVar("tl_viewer", default=LOWEST)


def viewer_for(principal: Principal) -> Viewer:
    """The viewer a principal is: agents read ``internal``; a document controller or admin reads
    ``restricted``; only a person or a simulated person can be named on a privileged item."""
    agent = principal.kind == "agent"
    return Viewer(
        actor=principal.actor,
        level=1 if principal.is_controller else 0,
        account="" if agent else principal.actor,
    )


def current_viewer() -> Viewer:
    return _VIEWER.get()


@contextmanager
def use_viewer(viewer: Viewer) -> Generator[None]:
    """Read as ``viewer`` inside the block. A system viewer is refused: use ``system_view``."""
    if viewer.system:
        raise ValueError("use system_view() to read without filters")
    token = _VIEWER.set(viewer)
    try:
        yield
    finally:
        _VIEWER.reset(token)


@contextmanager
def system_view() -> Generator[None]:
    """Read everything inside the block. Jobs and operator tools only; a test lists the callers."""
    token = _VIEWER.set(_SYSTEM)
    try:
        yield
    finally:
        _VIEWER.reset(token)


def _types(types: Iterable[str]) -> str:
    return ", ".join(f"'{t}'" for t in sorted(types))  # names were checked by ConfidentialSource


def _allowed(source: ConfidentialSource, viewer: Viewer) -> str:
    null = source.null_class or ""
    cls = f"COALESCE(s.{source.class_column}, '{null}')"
    classes = ", ".join(f"'{c}'" for c in sorted(_LEVELS) if _LEVELS[c] <= viewer.level)
    clause = f"{cls} IN ({classes})"
    if source.clearance_table is not None and viewer.account:
        clause += (
            f" OR ({cls} = '{PRIVILEGED}' AND EXISTS (SELECT 1 FROM {source.clearance_table} c "
            f"WHERE c.{source.clearance_record_column} = s.{source.id_column} "
            f"AND c.{source.clearance_account_column} = :{ACCOUNT_PARAM}))"
        )
    return clause


def _source_hidden(source: ConfidentialSource, viewer: Viewer) -> str:
    return (
        f"SELECT r.id FROM cur_core_record r WHERE r.type IN ({_types(source.record_types)}) "
        f"AND NOT EXISTS (SELECT 1 FROM {source.table} s WHERE s.{source.id_column} = r.id "
        f"AND ({_allowed(source, viewer)}))"
    )


def _child_hidden(source: ConfidentialSource, child: ChildSource, viewer: Viewer) -> str:
    """The children whose root is not readable. A flat join to the root: nesting one subquery
    inside another per level overflows SQLite's parser stack."""
    if child.hop is None:
        via, root_key = "", f"ch.{child.root_column}"
    else:
        table, key, root = child.hop
        via = f" JOIN {table} hop ON hop.{key} = ch.{child.root_column}"
        root_key = f"hop.{root}"
    return (
        f"SELECT r.id FROM cur_core_record r WHERE r.type IN ({_types(child.record_types)}) "
        f"AND NOT EXISTS (SELECT 1 FROM {child.table} ch{via} "
        f"JOIN {source.table} s ON s.{source.id_column} = {root_key} "
        f"WHERE ch.{child.id_column} = r.id AND ({_allowed(source, viewer)}))"
    )


def _source_parts(source: ConfidentialSource, viewer: Viewer) -> list[str]:
    """The root's hidden records, then each child's."""
    return [_source_hidden(source, viewer)] + [
        _child_hidden(source, child, viewer) for child in source.children
    ]


def hidden_sql(viewer: Viewer | None = None) -> str | None:
    """A ``SELECT id`` of every record ``viewer`` must not read; ``None`` when nothing is hidden.

    The text holds only names the modules declared and the bind parameter ``_cf_acct`` (see
    ``params_for``). A system viewer hides nothing.
    """
    who = viewer if viewer is not None else current_viewer()
    if who.system:
        return None
    parts: list[str] = []
    for source in confidential_sources():
        parts.extend(_source_parts(source, who))
    return " UNION ALL ".join(parts) if parts else None


def params_for(sql: str, viewer: Viewer | None = None) -> dict[str, Any]:
    """The bind parameters ``sql`` (from this module) needs: the account, when it names one."""
    who = viewer if viewer is not None else current_viewer()
    return {ACCOUNT_PARAM: who.account} if f":{ACCOUNT_PARAM}" in sql else {}


def not_hidden(id_expr: str, viewer: Viewer | None = None) -> tuple[str, dict[str, Any]]:
    """``(clause, params)``: ``id_expr`` is a record the viewer may read.

    ``id_expr`` is SQL written by the caller (a column such as ``r.id``), never user input. Merge
    ``params`` into the statement's parameters. For a system viewer the clause is ``1 = 1``.
    """
    sql = hidden_sql(viewer)
    if sql is None:
        return "1 = 1", {}
    return f"{id_expr} NOT IN ({sql})", params_for(sql, viewer)


def is_hidden(conn: Connection, record_id: str, viewer: Viewer | None = None) -> bool:
    """True when the record exists and the viewer must not read it (a missing one is not hidden)."""
    sql = hidden_sql(viewer)
    if sql is None:
        return False
    statement = text(f"SELECT 1 FROM cur_core_record x WHERE x.id = :_cf_id AND x.id IN ({sql})")
    found = conn.execute(statement, {"_cf_id": record_id, **params_for(sql, viewer)}).first()
    return found is not None


def require_visible(conn: Connection, record_id: str, viewer: Viewer | None = None) -> None:
    """Raise ``RecordNotFoundError`` (404, the same text as a record that does not exist) when the
    record is hidden from the viewer. A write that names a hidden record answers like this too."""
    if is_hidden(conn, record_id, viewer):
        raise RecordNotFoundError(f"no record {record_id!r}")


def hidden_among(
    conn: Connection, record_ids: Sequence[str], viewer: Viewer | None = None
) -> set[str]:
    """The ids among ``record_ids`` that the viewer must not read (for a small list)."""
    sql = hidden_sql(viewer)
    ids = sorted({i for i in record_ids if i})
    if sql is None or not ids:
        return set()
    found: set[str] = set()
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        statement = text(
            f"SELECT x.id FROM cur_core_record x WHERE x.id IN :_cf_ids AND x.id IN ({sql})"
        ).bindparams(bindparam("_cf_ids", expanding=True))
        rows = conn.execute(statement, {"_cf_ids": chunk, **params_for(sql, viewer)})
        found.update(str(row[0]) for row in rows)
    return found


def not_hidden_item(item_expr: str, viewer: Viewer | None = None) -> tuple[str, dict[str, Any]]:
    """``(clause, params)``: ``item_expr`` is a feed item or post that does not tag a hidden record.

    A card or a post is about the records it tags (``cur_feed_tags`` of kind ``record``); when
    one of them is hidden the item is, because its summary can hold that record's title.
    """
    sql = hidden_sql(viewer)
    if sql is None:
        return "1 = 1", {}
    clause = (
        f"{item_expr} NOT IN (SELECT t.item_id FROM cur_feed_tags t "
        f"WHERE t.kind = 'record' AND t.record_id IN ({sql}))"
    )
    return clause, params_for(sql, viewer)


def hidden_event_streams(
    conn: Connection, streams: Iterable[tuple[str, str]], viewer: Viewer | None = None
) -> set[str]:
    """The ids among ``(stream_id, stream_type)`` pairs whose events the viewer must not read.

    A stream is hidden when it is a hidden record, a link with a hidden end, a file of a hidden
    record, or a feed item about a hidden record. Account, webhook, proposal and setting streams
    are not records and are never hidden here.
    """
    who = viewer if viewer is not None else current_viewer()
    ids = sorted({stream for stream, _ in streams if stream})
    if who.system or not ids or hidden_sql(who) is None:
        return set()
    hidden = hidden_among(conn, ids, who)
    sql = hidden_sql(who)
    assert sql is not None
    extra = {**params_for(sql, who)}
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        queries = (
            f"SELECT l.link_id FROM cur_links l WHERE l.link_id IN :_cf_ids "
            f"AND (l.from_id IN ({sql}) OR l.to_id IN ({sql}))",
            f"SELECT f.file_id FROM cur_files f WHERE f.file_id IN :_cf_ids "
            f"AND f.record_id IN ({sql})",
            f"SELECT t.item_id FROM cur_feed_tags t WHERE t.item_id IN :_cf_ids "
            f"AND t.kind = 'record' AND t.record_id IN ({sql})",
        )
        for query in queries:
            statement = text(query).bindparams(bindparam("_cf_ids", expanding=True))
            hidden.update(
                str(row[0]) for row in conn.execute(statement, {"_cf_ids": chunk, **extra})
            )
    return hidden


def filter_events(
    conn: Connection, events: Sequence[Event], viewer: Viewer | None = None
) -> list[Event]:
    """``events`` without those of streams the viewer must not read (ADR-0016).

    Give the viewer explicitly when the call runs in a worker thread: a thread started with
    ``run_in_executor`` does not inherit the context variable.
    """
    hidden = hidden_event_streams(conn, [(e.stream_id, e.stream_type) for e in events], viewer)
    return [e for e in events if e.stream_id not in hidden] if hidden else list(events)


def viewer_for_actor(conn: Connection, actor: str) -> Viewer:
    """The viewer a named account is, read from the account projection (``LOWEST`` when it is not
    an active person or simulated person). For deliveries made on someone's behalf, such as the
    webhooks of a subscription: the audience is the owner, not the process that sends."""
    from tl_core.auth.queries import find_account

    if not actor.startswith("user:"):
        return LOWEST
    account = find_account(conn, username=actor[len("user:") :])
    if account is None or account.status != "active" or account.kind == "agent":
        return LOWEST
    controller = "admin" in account.roles or "document_controller" in account.roles
    return Viewer(actor=actor, level=1 if controller else 0, account=actor)


#: The viewer that reads restricted records and can never be named: used to tell a restricted
#: record from a privileged or unknown one.
RESTRICTED_ONLY: Final = Viewer(actor="", level=1, account="")
