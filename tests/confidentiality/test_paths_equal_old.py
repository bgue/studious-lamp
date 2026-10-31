"""P2-PERF: the faster confidentiality paths give what the old ``NOT IN (all hidden)`` gave.

Each test builds a small project with open, restricted and privileged items (a long run of hidden
ones among the newest), then reads it as five kinds of reader (``USER`` named on a privileged
item, ``OTHER``, ``CONTROLLER``, ``AGENT``, ``NOBODY``) by the new path and by the old statement
(``cf.not_hidden``: the hidden records listed once), and compares. ``test_the_check_is_pushed_into
_the_statement`` and the sentinel test show the comparison can fail.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Literal

import pytest
from sqlalchemy import Connection, event, text
from sqlalchemy.engine import Engine
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core import confidentiality as cf
from tl_core.auth import accounts
from tl_core.query import QuerySpec, api, parse, run_query
from tl_core.query.compiler import compile_query
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services import link_queries as lq
from tl_core.services import queries
from tl_core.services.feed import PostToFeed, handle_post
from tl_mod_correspondence import registry as corr_registry
from tl_mod_correspondence import registry_domain as corr_domain
from tl_mod_correspondence.names import CORRESPONDENCE_VIEW
from tl_mod_correspondence.testing import CorrWorld
from tl_mod_documents import registry as doc_registry
from tl_mod_documents.derivation import store
from tl_mod_documents.handlers.documents import RegisterDocument, handle_register_document
from tl_mod_documents.names import DOCUMENT_VIEW

SCOPE = "project:P123"
FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures"
USER = cf.Viewer(actor="user:ann", level=0, account="user:ann")
OTHER = cf.Viewer(actor="user:bo", level=0, account="user:bo")
CONTROLLER = cf.Viewer(actor="user:ctl", level=1, account="user:ctl")
AGENT = cf.Viewer(actor="agent:x", level=0, account="")
NOBODY = cf.LOWEST
READERS = (USER, OTHER, CONTROLLER, AGENT, NOBODY)

LETTERS = 70  # numbers 1..LETTERS; the newest hidden run is longer than a first page of 30
RESTRICTED_FROM = 21  # 21..70 restricted, 11..15 privileged (ann named on 11 and 12), rest open
PRIVILEGED = range(11, 16)
TECHNICAL = 12


def number(prefix: str, i: int) -> str:
    return f"P123-{prefix}-{i:04d}"


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    target = new_db()
    create_schema(target)
    return target


@pytest.fixture
def world(db: DbTarget, tmp_path: Path) -> Iterator[CorrWorld]:
    """Letters, RFIs and documents of every class, a post and links across hidden records."""
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        made = CorrWorld(db, tmp_path / "objects")
        # The acting accounts exist with the ``user`` role: an account-less ``user:`` actor holds
        # the ``user`` word only on a dev ledger (SQLite), never on Postgres (owner decision D2).
        with open_uow(db) as uow:
            for name in ("u", "mlee"):
                accounts.create_account(
                    uow, username=name, display_name=name.title(), kind="person",
                    roles=["user"], password=None, by="svc:test",
                )  # fmt: skip
        with store.use_files(made.files):
            ids: dict[str, str] = {}
            for i in range(1, LETTERS + 1):
                klass = (
                    "privileged"
                    if i in PRIVILEGED
                    else "restricted"
                    if i >= RESTRICTED_FROM
                    else "internal"
                )
                ids[number("COR", i)] = made.forge_item(
                    number("COR", i), state="Received", confidentiality=klass
                )
            for i in (11, 12):
                made.forge_item_event(
                    ids[number("COR", i)],
                    "Correspondence.ClearanceGranted",
                    {"account": "user:ann", "granted_on": "2026-10-19", "reason": "counsel"},
                )
            for i in range(1, TECHNICAL + 1):
                made.forge_technical(
                    number("RFI", i),
                    state="Issued",
                    confidentiality="restricted" if i > TECHNICAL // 2 else "internal",
                )
            for i in range(1, 25):
                with cf.system_view(), open_uow(db) as uow:
                    handle_register_document(
                        uow,
                        RegisterDocument(
                            actor="user:u",
                            source="test",
                            scope=SCOPE,
                            number=f"DOC-{i:04d}",
                            title=f"Document {i}",
                            confidentiality="restricted" if i > 12 else None,
                        ),
                    )
            made.ids = ids  # type: ignore[attr-defined]
            yield made


def ids_of(world: CorrWorld) -> dict[str, str]:
    return world.ids  # type: ignore[attr-defined]


def read(world: CorrWorld, viewer: cf.Viewer) -> Any:
    """A read-only unit of work as ``viewer`` (a context manager)."""
    from contextlib import contextmanager

    @contextmanager
    def scope() -> Iterator[Connection]:
        with cf.use_viewer(viewer), open_uow(world.db, readonly=True) as uow:
            yield uow.conn()

    return scope()


class Statements:
    """The SQL a block of reads sent, newest last."""

    def __init__(self) -> None:
        self.sql: list[str] = []

    def __call__(
        self, conn: Any, cursor: Any, statement: str, params: Any, context: Any, many: Any
    ) -> None:
        self.sql.append(statement)


@pytest.fixture
def sent() -> Iterator[Statements]:
    listener = Statements()
    event.listen(Engine, "before_cursor_execute", listener)
    try:
        yield listener
    finally:
        event.remove(Engine, "before_cursor_execute", listener)


# --- the id is part of the statement; the answers are the old answers ------------------------


def test_the_check_is_pushed_into_the_statement(world: CorrWorld, sent: Statements) -> None:
    """``is_hidden`` and ``hidden_among`` ask about the records given, not every hidden one."""
    first = ids_of(world)[number("COR", 1)]
    with read(world, USER) as conn:
        parts = cf.hidden_sql(USER, only="hr.id = :_cf_id")
        whole = cf.hidden_sql(USER)
        assert parts is not None and whole is not None
        assert parts.count("hr.id = :_cf_id") == parts.count(" UNION ALL ") + 1
        assert "_cf_id" not in whole
        sent.sql.clear()
        cf.is_hidden(conn, first, USER)
        cf.hidden_among(conn, [first], USER)
    asked = [s for s in sent.sql if "cur_core_record hr" in s]
    assert len(asked) == 2
    assert all("hr.id = " in s for s in asked)


@pytest.mark.parametrize("viewer", READERS, ids=lambda v: v.actor or "nobody")
def test_is_hidden_and_hidden_among_equal_the_whole_set(
    world: CorrWorld, viewer: cf.Viewer
) -> None:
    every = list(ids_of(world).values())
    with read(world, viewer) as conn:
        clause, params = cf.not_hidden("x.id", viewer)
        shown = {
            str(r[0])
            for r in conn.execute(
                text(f"SELECT x.id FROM cur_core_record x WHERE {clause}"), params
            )
        }
        expected = {i for i in every if i not in shown}
        assert expected or viewer is CONTROLLER
        assert cf.hidden_among(conn, every, viewer) == expected
        assert {i for i in every if cf.is_hidden(conn, i, viewer)} == expected


@pytest.mark.parametrize("viewer", READERS, ids=lambda v: v.actor or "nobody")
def test_a_single_record_read_hides_what_the_whole_set_hid(
    world: CorrWorld, viewer: cf.Viewer
) -> None:
    with read(world, viewer) as conn:
        clause, params = cf.not_hidden("id", viewer)
        shown = {
            str(r[0])
            for r in conn.execute(text(f"SELECT id FROM cur_core_record WHERE {clause}"), params)
        }
    with cf.use_viewer(viewer), open_uow(world.db, readonly=True) as uow:
        for key, record_id in ids_of(world).items():
            found = queries.get_record(uow, SCOPE, key)
            assert (found is not None) == (record_id in shown)
            assert (queries.get_record_by_id(uow, record_id) is not None) == (record_id in shown)


# --- count_query, run_query -------------------------------------------------------------------


@pytest.mark.parametrize("viewer", READERS, ids=lambda v: v.actor or "nobody")
@pytest.mark.parametrize("limit_name", ["each", "set"])
def test_count_query_below_and_above_the_each_limit(
    world: CorrWorld,
    viewer: cf.Viewer,
    limit_name: str,
    monkeypatch: pytest.MonkeyPatch,
    sent: Statements,
) -> None:
    """A filter with few matches is counted row by row, one with many in one pass; same count."""
    monkeypatch.setattr(api, "COUNT_EACH_LIMIT", 100_000 if limit_name == "each" else 1)
    for expression in (
        "type=correspondence.Correspondence",
        "type=correspondence.TechnicalItem",
    ):
        spec = QuerySpec(scope=SCOPE, where=parse(expression))
        with cf.use_viewer(viewer), open_uow(world.db, readonly=True) as uow:
            old = compile_query(spec, count=True)  # compiled as this reader: the set form
            conn = uow.conn()
            wanted = int(conn.execute(text(old.sql), old.params).scalar_one())
            sent.sql.clear()
            got = api.count_query(uow, spec)
        assert got == wanted
        counted = [s for s in sent.sql if s.lstrip().startswith("SELECT COUNT(*)")]
        assert counted, "the count was sent"
        if wanted > 1 and limit_name == "each":
            assert any("hr.id = r.id" in s for s in counted)
        if wanted > 1 and limit_name == "set":
            assert not any("hr.id = r.id" in s for s in counted[-1:])


@pytest.mark.parametrize("viewer", READERS, ids=lambda v: v.actor or "nobody")
def test_run_query_pages_equal_the_old_statement(world: CorrWorld, viewer: cf.Viewer) -> None:
    for limit in (1, 25, 500, 5000, None):  # 5000 and None: above PAGE_ROWS_MAX
        orders: list[list[tuple[str, Literal["asc", "desc"]]]] = [[], [("title", "desc")]]
        for order in orders:
            spec = QuerySpec(scope=SCOPE, where=parse("type=correspondence.Correspondence"),
                             limit=limit, order_by=list(order))  # fmt: skip
            with cf.use_viewer(viewer), open_uow(world.db, readonly=True) as uow:
                old = compile_query(spec)  # compiled as this reader: the set form
                wanted = [r["id"] for r in uow.conn().execute(text(old.sql), old.params).mappings()]
                got = [r["id"] for r in run_query(uow, spec)]
            assert got == wanted


# --- visible_rows ------------------------------------------------------------------------------


@pytest.mark.parametrize("viewer", READERS, ids=lambda v: v.actor or "nobody")
@pytest.mark.parametrize("limit", [1, 7, 30, 60, 1000, 1001, 5000])
def test_visible_rows_over_a_long_run_of_hidden_rows_and_above_the_page_limit(
    world: CorrWorld, viewer: cf.Viewer, limit: int
) -> None:
    """Newest first, the newest 50 numbers are restricted: a first page of 30 is all hidden for
    some readers and must be refilled; a limit above ``PAGE_ROWS_MAX`` takes the SQL path."""
    assert 1001 > cf.PAGE_ROWS_MAX
    sql = "SELECT id FROM cur_core_record WHERE scope = :scope AND type = :t ORDER BY key DESC, id"
    params = {"scope": SCOPE, "t": "correspondence.Correspondence"}
    with read(world, viewer) as conn:
        clause, extra = cf.not_hidden("id", viewer)
        old = conn.execute(
            text(sql.replace(" ORDER BY", f" AND {clause} ORDER BY") + " LIMIT :n"),
            {**params, **extra, "n": limit},
        )
        wanted = [str(r.id) for r in old]
        got = [str(r.id) for r in cf.visible_rows(conn, sql, params, limit=limit, viewer=viewer)]
    assert got == wanted


# --- the lists: offset 0 against offset > 0 and the old statement -----------------------------


@pytest.mark.parametrize("viewer", READERS, ids=lambda v: v.actor or "nobody")
def test_correspondence_pages_at_offset_zero_and_beyond(
    world: CorrWorld, viewer: cf.Viewer
) -> None:
    with read(world, viewer) as conn:
        clause, params = cf.not_hidden("id", viewer)
        everything = [
            str(r.id)
            for r in conn.execute(
                text(
                    f"SELECT {corr_registry._ITEM_COLUMNS} "
                    f"FROM {CORRESPONDENCE_VIEW} "
                    f"WHERE scope = :scope AND {clause} AND COALESCE(status, 'Draft') <> 'Void' "
                    "ORDER BY number DESC, id"
                ),
                {"scope": SCOPE, **params},
            )
        ]
        for limit in (5, 40, 500):
            for offset in (0, 7, 25):
                got = [
                    r.id for r in corr_registry.list_items(conn, SCOPE, limit=limit, offset=offset)
                ]
                assert got == everything[offset : offset + limit], (limit, offset)
        technical = [r.item.id for r in corr_domain.list_technical(conn, SCOPE, limit=500)]
        later = [r.item.id for r in corr_domain.list_technical(conn, SCOPE, limit=500, offset=2)]
        assert later == technical[2:]
        assert len(technical) == len(set(technical))


@pytest.mark.parametrize("viewer", READERS, ids=lambda v: v.actor or "nobody")
def test_list_documents_at_offset_zero_and_beyond(world: CorrWorld, viewer: cf.Viewer) -> None:
    with read(world, viewer) as conn:
        clause, params = cf.not_hidden("id", viewer)
        everything = [
            str(r.id)
            for r in conn.execute(
                text(
                    f"SELECT {doc_registry._DOCUMENT_COLUMNS} FROM {DOCUMENT_VIEW} "
                    f"WHERE scope = :scope AND {clause} AND COALESCE(status, 'Draft') <> 'Void' "
                    "ORDER BY key, id"
                ),
                {"scope": SCOPE, **params},
            )
        ]
        for limit in (3, 25, 1500):  # 1500 is above PAGE_ROWS_MAX
            for offset in (0, 4):
                got = [
                    r.id
                    for r in doc_registry.list_documents(conn, SCOPE, limit=limit, offset=offset)
                ]
                assert got == everything[offset : offset + limit], (limit, offset)


@pytest.mark.parametrize("viewer", READERS, ids=lambda v: v.actor or "nobody")
def test_list_records_first_page_equals_the_old_statement(
    world: CorrWorld, viewer: cf.Viewer
) -> None:
    with cf.use_viewer(viewer), open_uow(world.db, readonly=True) as uow:
        clause, params = cf.not_hidden("id", viewer)
        old = [
            str(r.id)
            for r in uow.conn().execute(
                text(
                    f"{queries._SELECT} WHERE scope = :scope AND {clause} AND voided = :no "
                    "ORDER BY created_at, id"
                ),
                {"scope": SCOPE, "no": False, **params},
            )
        ]
        for limit in (1, 20, 90, 1500):
            got = [r["id"] for r in queries.list_records(uow, SCOPE, limit=limit)]
            assert got == old[:limit]


# --- links: a hidden end, and a post that tags a hidden record --------------------------------


@pytest.fixture
def linked(world: CorrWorld) -> dict[str, str]:
    """Open letters 1 and 2 linked to open, restricted and privileged letters; a post that tags
    open letter 1 and restricted letter 70; a post that tags open letter 1 only."""
    ids = ids_of(world)
    one, two = ids[number("COR", 1)], ids[number("COR", 2)]
    with cf.system_view():
        world.link(one, two)
        world.link(one, ids[number("COR", 70)])  # restricted
        world.link(two, ids[number("COR", 11)])  # privileged, ann named
        world.link(ids[number("COR", 13)], one)  # privileged, nobody named
        with open_uow(world.db) as uow:
            hidden_post = handle_post(
                uow,
                PostToFeed(
                    actor="user:mlee",
                    source="test",
                    scope=SCOPE,
                    body=f"see #{number('COR', 1)} and #{number('COR', 70)}",
                ),
            ).stream_id
        with open_uow(world.db) as uow:
            plain_post = handle_post(
                uow,
                PostToFeed(
                    actor="user:mlee", source="test", scope=SCOPE, body=f"see #{number('COR', 1)}"
                ),
            ).stream_id
    return {"one": one, "two": two, "hidden_post": hidden_post, "plain_post": plain_post}


def old_links(conn: Connection, record_id: str) -> list[tuple[str, str]]:
    """``(link_id, other_id)`` as the old statement gave them: both tests inside the SQL."""
    record_ok, params = cf.not_hidden("r.id")
    item_ok, item_params = cf.not_hidden_item("r.id")
    sql = lq._LINKS_SQL + f" AND l.status <> 'retracted' AND {record_ok} AND {item_ok}"
    rows = conn.execute(text(sql), {"id": record_id, **params, **item_params}).mappings()
    return sorted((r["link_id"], r["other_id"]) for r in rows)


def old_counts(conn: Connection, record_id: str) -> dict[str, int]:
    from_ok, params = cf.not_hidden("l.from_id")
    to_ok, to_params = cf.not_hidden("l.to_id")
    rows = conn.execute(
        text(
            "SELECT status, 1 AS out FROM cur_links l WHERE l.from_id = :id AND "
            f"{from_ok} AND {to_ok} UNION ALL SELECT status, 0 AS out FROM cur_links l "
            f"WHERE l.to_id = :id AND {from_ok} AND {to_ok}"
        ),
        {"id": record_id, **params, **to_params},
    )
    counts = {"active_out": 0, "active_in": 0, "stale": 0, "broken": 0, "suggested": 0}
    for status, out in rows:
        if status == "active":
            counts["active_out" if out else "active_in"] += 1
        elif status in counts:
            counts[status] += 1
    return counts


@pytest.mark.parametrize("viewer", READERS, ids=lambda v: v.actor or "nobody")
def test_links_of_and_link_counts_equal_the_old_statements(
    world: CorrWorld, linked: dict[str, str], viewer: cf.Viewer
) -> None:
    with cf.use_viewer(viewer), open_uow(world.db, readonly=True) as uow:
        conn = uow.conn()
        for name in ("one", "two"):
            record_id = linked[name]
            if cf.is_hidden(conn, record_id, viewer):
                continue
            views = lq.links_of(uow, record_id, include_retracted=False)
            assert sorted((v.link_id, v.other_id) for v in views) == old_links(conn, record_id)
            counted = lq.link_counts(uow, [record_id])[record_id]
            assert counted.model_dump(exclude={"record_id"}) == old_counts(conn, record_id)
    # the post that tags a hidden letter is not offered to a reader of letter 1 who may not read it
    with cf.use_viewer(viewer), open_uow(world.db, readonly=True) as uow:
        others = {v.other_id for v in lq.links_of(uow, linked["one"])}
        hidden_for_viewer = cf.is_hidden(uow.conn(), ids_of(world)[number("COR", 70)], viewer)
        assert (linked["hidden_post"] in others) == (not hidden_for_viewer)
        assert linked["plain_post"] in others


def test_the_post_end_takes_the_whole_sql_path(
    world: CorrWorld, linked: dict[str, str], sent: Statements
) -> None:
    with cf.use_viewer(USER), open_uow(world.db, readonly=True) as uow:
        sent.sql.clear()
        lq.links_of(uow, linked["one"])
    assert any("cur_feed_tags" in s for s in sent.sql)  # the item test ran in SQL
    with cf.use_viewer(USER), open_uow(world.db, readonly=True) as uow:
        sent.sql.clear()
        lq.links_of(uow, linked["two"])
    assert not any("cur_feed_tags" in s for s in sent.sql)  # record ends only: looked up by id


def test_not_hidden_each_is_the_same_test_as_not_hidden(world: CorrWorld) -> None:
    """The per-row form (used by link reads and a document's links) passes the same links."""
    for viewer in READERS:
        with read(world, viewer) as conn:
            whole, p1 = cf.not_hidden("l.to_id", viewer)
            each, p2 = cf.not_hidden_each("l.to_id", viewer)
            a = {
                r[0]
                for r in conn.execute(text(f"SELECT l.link_id FROM cur_links l WHERE {whole}"), p1)
            }
            b = {
                r[0]
                for r in conn.execute(text(f"SELECT l.link_id FROM cur_links l WHERE {each}"), p2)
            }
            assert a == b


def test_a_documents_links_are_tested_row_by_row_and_equal_the_scope_form(
    world: CorrWorld,
) -> None:
    """``links_to_documents`` with a document id uses ``not_hidden_each``; the answer is the one
    the scope-wide form gives for that document."""
    from tl_mod_documents.resolver import links_to_documents

    ids = ids_of(world)
    with cf.system_view():
        doc_id = world.scalar("SELECT id FROM cur_core_record WHERE key = 'DOC-0001'")
        world.link(ids[number("COR", 1)], doc_id)
        world.link(ids[number("COR", 70)], doc_id)  # restricted letter links to the document
    for viewer in READERS:
        with read(world, viewer) as conn:
            one = [p.link_id for p in links_to_documents(conn, SCOPE, document_id=doc_id)]
            every = [p.link_id for p in links_to_documents(conn, SCOPE) if p.document_id == doc_id]
            assert sorted(one) == sorted(every)


# --- the sentinel ------------------------------------------------------------------------------


def test_sentinel_a_broken_pushdown_is_caught(
    world: CorrWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the ``only`` branch of ``hidden_sql`` turned into a condition that is never true, the
    checks above fail (so they do test it): nothing is hidden any more."""
    every = list(ids_of(world).values())
    with read(world, NOBODY) as conn:
        assert cf.hidden_among(conn, every, NOBODY)  # the real one hides some
    monkeypatch.setattr(cf, "_only", lambda only: " AND 1 = 0" if only else "")
    with read(world, NOBODY) as conn:
        assert cf.hidden_among(conn, every, NOBODY) == set()
        assert not cf.is_hidden(conn, ids_of(world)[number("COR", 70)], NOBODY)
