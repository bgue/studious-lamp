"""ADR-0016 in the core: classes, viewers, the hidden-record SQL and the shared read functions.

A fake module, ``vault``, stands in for a real one. Its ``Item`` has a class column and a
clearance table; its ``Note`` hangs on an item; its ``Task`` hangs on a note, which hangs on an
item (a hop). The tests read through the same functions the API, the MCP server, the CLI and the
TUI read through, as each kind of viewer.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core import confidentiality as cf
from tl_core.ledger import Event
from tl_core.modules import (
    ChildSource,
    ConfidentialSource,
    ModuleLoadError,
    ModuleSpec,
    use_modules,
)
from tl_core.query import QuerySpec, count_query, parse, run_query
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services import link_queries, link_trace, queries
from tl_core.services.commands import Command
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.records import create_module_record

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures"
SCOPE = "project:P123"
ITEM, NOTE, TASK = "vault.Item", "vault.Note", "vault.Task"

SOURCE = ConfidentialSource(
    record_types=frozenset({ITEM}),
    table="cur_vault_item",
    id_column="id",
    class_column="klass",
    null_class=None,
    clearance_table="cur_vault_clearance",
    children=(
        ChildSource(frozenset({NOTE}), "cur_vault_note", "id", "item_id"),
        ChildSource(
            frozenset({TASK}),
            "cur_vault_task",
            "id",
            "note_id",
            hop=("cur_vault_note", "id", "item_id"),
        ),
    ),
)
DDL = [
    "CREATE TABLE IF NOT EXISTS cur_vault_item (id TEXT PRIMARY KEY, klass TEXT)",
    "CREATE TABLE IF NOT EXISTS cur_vault_clearance "
    "(record_id TEXT NOT NULL, account TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS cur_vault_note (id TEXT PRIMARY KEY, item_id TEXT)",
    "CREATE TABLE IF NOT EXISTS cur_vault_task (id TEXT PRIMARY KEY, note_id TEXT)",
]


class VaultProjector:
    name = "vault"
    handles = frozenset({"Vault.Never"})

    def ddl(self, dialect: str) -> list[str]:
        return DDL

    def apply(self, conn: Connection, event: Event) -> None:
        return None

    def reset(self, conn: Connection) -> None:
        return None


def spec(source: ConfidentialSource = SOURCE) -> ModuleSpec:
    return ModuleSpec(
        name="vault",
        record_types=frozenset({ITEM, NOTE, TASK}),
        projectors=lambda: [VaultProjector()],
        confidential=(source,),
    )


@pytest.fixture(autouse=True)
def fixture_schemas() -> Iterator[None]:
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        yield


@pytest.fixture(autouse=True)
def vault_module() -> Iterator[None]:
    with use_modules([spec()]):
        yield


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    target = new_db()
    create_schema(target)
    return target


USER = cf.Viewer(actor="user:ann", level=0, account="user:ann")
OTHER = cf.Viewer(actor="user:bo", level=0, account="user:bo")
CONTROLLER = cf.Viewer(actor="user:ctl", level=1, account="user:ctl")
AGENT = cf.Viewer(actor="agent:x", level=0, account="")
NOBODY = cf.LOWEST


class Vault:
    """Records of the fake module: one item per class, notes and a task, all by secret titles."""

    def __init__(self, db: DbTarget) -> None:
        self.db = db
        self.ids: dict[str, str] = {}

    def add(
        self, name: str, record_type: str, klass: str | None, *, parent: str | None = None
    ) -> str:
        with open_uow(self.db) as uow:
            made = create_module_record(
                uow,
                Command(actor="user:u", source="test", scope=SCOPE),
                record_type=record_type,
                title=f"SECRET-{name}",
                key=f"K-{name}",
            )
            conn = uow.conn()
            if record_type == ITEM:
                conn.execute(
                    text("INSERT INTO cur_vault_item (id, klass) VALUES (:i, :k)"),
                    {"i": made.stream_id, "k": klass},
                )
            elif record_type == NOTE:
                conn.execute(
                    text("INSERT INTO cur_vault_note (id, item_id) VALUES (:i, :p)"),
                    {"i": made.stream_id, "p": parent},
                )
            elif record_type == TASK:
                conn.execute(
                    text("INSERT INTO cur_vault_task (id, note_id) VALUES (:i, :p)"),
                    {"i": made.stream_id, "p": parent},
                )
        self.ids[name] = made.stream_id
        return made.stream_id

    def name_account(self, name: str, account: str) -> None:
        with open_uow(self.db) as uow:
            uow.conn().execute(
                text("INSERT INTO cur_vault_clearance (record_id, account) VALUES (:r, :a)"),
                {"r": self.ids[name], "a": account},
            )


@pytest.fixture
def vault(db: DbTarget) -> Vault:
    v = Vault(db)
    v.add("open", ITEM, "internal")
    v.add("restricted", ITEM, "restricted")
    v.add("privileged", ITEM, "privileged")
    v.add("bogus", ITEM, "Confidential")
    v.add("null", ITEM, None)
    v.add("empty", ITEM, "")
    v.add("upper", ITEM, "INTERNAL")
    v.add("note-open", NOTE, None, parent=v.ids["open"])
    v.add("note-restricted", NOTE, None, parent=v.ids["restricted"])
    v.add("task-open", TASK, None, parent=v.ids["note-open"])
    v.add("task-restricted", TASK, None, parent=v.ids["note-restricted"])
    v.add("lonely-note", NOTE, None, parent=None)
    v.name_account("privileged", "user:ann")
    return v


def titles(db: DbTarget, viewer: cf.Viewer) -> set[str]:
    with cf.use_viewer(viewer), open_uow(db, readonly=True) as uow:
        rows = queries.list_records(uow, SCOPE)
    return {str(r["title"]).removeprefix("SECRET-") for r in rows}


# --- who reads which class -----------------------------------------------------------------------


def test_an_internal_item_is_read_by_everyone_and_nothing_else_is_read_by_a_plain_viewer(
    db: DbTarget, vault: Vault
) -> None:
    for viewer in (USER, OTHER, AGENT, NOBODY):
        assert {"open"} <= titles(db, viewer)
        assert not {"restricted", "bogus", "null", "empty", "upper"} & titles(db, viewer)


def test_a_controller_reads_restricted_but_not_privileged_unless_named(
    db: DbTarget, vault: Vault
) -> None:
    seen = titles(db, CONTROLLER)
    assert {"open", "restricted", "note-restricted", "task-restricted"} <= seen
    assert "privileged" not in seen  # an admin or a controller is not special for privileged


def test_a_named_account_reads_the_privileged_item_and_nobody_else_does(
    db: DbTarget, vault: Vault
) -> None:
    assert "privileged" in titles(db, USER)
    for viewer in (OTHER, CONTROLLER, AGENT, NOBODY):
        assert "privileged" not in titles(db, viewer)


def test_an_agent_is_never_named_even_when_an_agent_account_is_in_the_clearance_table(
    db: DbTarget, vault: Vault
) -> None:
    vault.name_account("privileged", "agent:x")
    assert "privileged" not in titles(db, AGENT)  # the agent viewer carries no account


def test_an_unknown_class_a_null_class_and_a_wrong_case_are_hidden_from_everyone(
    db: DbTarget, vault: Vault
) -> None:
    for viewer in (USER, CONTROLLER, AGENT, NOBODY):
        assert not {"bogus", "null", "empty", "upper"} & titles(db, viewer)
    with cf.system_view(), open_uow(db, readonly=True) as uow:
        assert {r["title"] for r in queries.list_records(uow, SCOPE)} >= {
            "SECRET-bogus",
            "SECRET-null",
        }


def test_a_source_may_say_that_a_null_class_means_internal(db: DbTarget, vault: Vault) -> None:
    lenient = ConfidentialSource(
        record_types=SOURCE.record_types,
        table=SOURCE.table,
        id_column="id",
        class_column="klass",
        null_class="internal",
        clearance_table=SOURCE.clearance_table,
        children=SOURCE.children,
    )
    with use_modules([spec(lenient)]):
        assert "null" in titles(db, NOBODY)
        assert "bogus" not in titles(db, NOBODY) and "empty" not in titles(db, NOBODY)


def test_a_record_of_a_confidential_type_with_no_row_in_its_table_is_hidden(
    db: DbTarget, vault: Vault
) -> None:
    with open_uow(db) as uow:
        create_module_record(
            uow,
            Command(actor="user:u", source="test", scope=SCOPE),
            record_type=ITEM,
            title="SECRET-rowless",
            key="K-rowless",
        )
    for viewer in (USER, CONTROLLER, AGENT, NOBODY):
        assert "rowless" not in titles(db, viewer)


def test_a_child_follows_its_root_through_one_hop_and_two(db: DbTarget, vault: Vault) -> None:
    assert {"note-open", "task-open"} <= titles(db, NOBODY)
    assert not {"note-restricted", "task-restricted"} & titles(db, NOBODY)
    assert {"note-restricted", "task-restricted"} <= titles(db, CONTROLLER)
    assert "lonely-note" not in titles(db, CONTROLLER)  # a child with no root is hidden


def test_a_class_change_applies_at_once(db: DbTarget, vault: Vault) -> None:
    assert "restricted" not in titles(db, USER)
    with open_uow(db) as uow:
        uow.conn().execute(
            text("UPDATE cur_vault_item SET klass = 'internal' WHERE id = :i"),
            {"i": vault.ids["restricted"]},
        )
    assert {"restricted", "note-restricted"} <= titles(db, USER)


# --- the viewer --------------------------------------------------------------------------------


def test_with_no_viewer_set_the_lowest_clearance_reads(db: DbTarget, vault: Vault) -> None:
    assert cf.current_viewer() == cf.LOWEST
    with open_uow(db, readonly=True) as uow:
        found = {r["title"] for r in queries.list_records(uow, SCOPE)}
    assert "SECRET-open" in found and "SECRET-restricted" not in found


def test_a_viewer_applies_inside_its_block_only(db: DbTarget, vault: Vault) -> None:
    with cf.use_viewer(CONTROLLER):
        assert cf.current_viewer() == CONTROLLER
        with cf.use_viewer(USER):
            assert cf.current_viewer() == USER
        assert cf.current_viewer() == CONTROLLER
    assert cf.current_viewer() == cf.LOWEST


def test_system_view_is_only_for_system_view(db: DbTarget) -> None:
    with pytest.raises(ValueError, match="system_view"):
        with cf.use_viewer(cf.Viewer(system=True)):
            pass
    with pytest.raises(ValueError, match="system_view"):
        cf.set_viewer(cf.Viewer(system=True))
    with cf.system_view():
        assert cf.current_viewer().system
    assert not cf.current_viewer().system


def test_set_and_reset_restore_what_was_there() -> None:
    token = cf.set_viewer(USER)
    assert cf.current_viewer() == USER
    cf.reset_viewer(token)
    assert cf.current_viewer() == cf.LOWEST


def test_the_viewer_of_a_principal_follows_kind_and_roles() -> None:
    from tl_core.auth.types import Principal

    def principal(kind: str, roles: list[str]) -> Principal:
        return Principal.model_validate(
            {
                "actor": f"{'agent' if kind == 'agent' else 'user'}:z",
                "account_id": "A1",
                "kind": kind,
                "roles": roles,
                "via": "password",
            }
        )

    assert cf.viewer_for(principal("person", ["user"])) == cf.Viewer("user:z", 0, "user:z")
    assert cf.viewer_for(principal("person", ["document_controller"])).level == 1
    assert cf.viewer_for(principal("person", ["admin"])).level == 1
    assert cf.viewer_for(principal("sim", ["user"])).account == "user:z"
    agent = cf.viewer_for(principal("agent", ["admin"]))  # a role never lifts an agent
    assert agent.account == "" and agent.level == 0


def test_a_viewer_of_an_account_is_read_from_the_projection(db: DbTarget) -> None:
    from tl_core.auth import accounts
    from tl_core.auth.password import prepare_password

    with open_uow(db) as uow:
        for name, kind, roles in (
            ("ann", "person", ["user"]),
            ("ctl", "person", ["document_controller"]),
            ("bot", "agent", ["user"]),
        ):
            accounts.create_account(
                uow,
                username=name,
                display_name=name,
                kind=kind,  # type: ignore[arg-type]
                roles=roles,
                password=None if kind == "agent" else prepare_password("a long enough pass 1"),
                by="svc:test",
            )
    with open_uow(db, readonly=True) as uow:
        conn = uow.conn()
        assert cf.viewer_for_actor(conn, "user:ann") == cf.Viewer("user:ann", 0, "user:ann")
        assert cf.viewer_for_actor(conn, "user:ctl").level == 1
        assert cf.viewer_for_actor(conn, "agent:bot") == cf.LOWEST
        assert cf.viewer_for_actor(conn, "user:nobody") == cf.LOWEST
        assert cf.viewer_for_actor(conn, "svc:x") == cf.LOWEST


# --- the helpers -------------------------------------------------------------------------------


def test_is_hidden_and_require_visible(db: DbTarget, vault: Vault) -> None:
    with open_uow(db, readonly=True) as uow:
        conn = uow.conn()
        assert cf.is_hidden(conn, vault.ids["restricted"], USER)
        assert not cf.is_hidden(conn, vault.ids["restricted"], CONTROLLER)
        assert not cf.is_hidden(conn, vault.ids["open"], NOBODY)
        assert not cf.is_hidden(conn, "NO-SUCH-RECORD", NOBODY)  # a missing record is not hidden
        with cf.use_viewer(USER):
            with pytest.raises(RecordNotFoundError):
                cf.require_visible(conn, vault.ids["restricted"])
            cf.require_visible(conn, vault.ids["open"])
        with cf.system_view():
            assert not cf.is_hidden(conn, vault.ids["bogus"])


def test_hidden_among_filters_a_list(db: DbTarget, vault: Vault) -> None:
    ids = [vault.ids[n] for n in ("open", "restricted", "privileged", "bogus", "note-restricted")]
    with open_uow(db, readonly=True) as uow:
        hidden = cf.hidden_among(uow.conn(), [*ids, "", "unknown"], USER)
        assert hidden == {vault.ids[n] for n in ("restricted", "bogus", "note-restricted")}
        assert cf.hidden_among(uow.conn(), [], USER) == set()
        many = [f"X{i}" for i in range(1200)] + ids
        assert cf.hidden_among(uow.conn(), many, NOBODY) >= {vault.ids["restricted"]}


def test_not_hidden_is_a_noop_for_the_system_and_a_clause_for_everyone_else() -> None:
    assert cf.not_hidden("r.id", cf.Viewer(system=True)) == ("1 = 1", {})
    clause, params = cf.not_hidden("r.id", USER)
    assert clause.startswith("r.id NOT IN (") and params == {"_cf_acct": "user:ann"}
    clause, params = cf.not_hidden("r.id", AGENT)
    assert params == {}  # an agent has no account: the clause names none


def test_with_no_confidential_module_nothing_is_hidden(db: DbTarget, vault: Vault) -> None:
    with use_modules([]):
        assert cf.hidden_sql(NOBODY) is None
        assert cf.not_hidden("id", NOBODY) == ("1 = 1", {})
        with open_uow(db, readonly=True) as uow:
            assert not cf.is_hidden(uow.conn(), vault.ids["restricted"], NOBODY)


def test_the_sql_is_flat_enough_for_sqlite_whatever_the_number_of_sources() -> None:
    many = tuple(
        ConfidentialSource(
            record_types=frozenset({f"m{i}.T"}),
            table=f"cur_m{i}_t",
            id_column="id",
            class_column="klass",
            children=(ChildSource(frozenset({f"m{i}.C"}), f"cur_m{i}_c", "id", "t_id"),),
        )
        for i in range(60)
    )
    specs = [
        ModuleSpec(
            name=f"m{i}",
            record_types=frozenset({f"m{i}.T", f"m{i}.C"}),
            projectors=lambda: [],
            confidential=(many[i],),
        )
        for i in range(60)
    ]
    with use_modules(specs):
        sql = cf.hidden_sql(NOBODY)
    assert sql is not None and sql.count(" UNION ALL ") == 119
    # depth: no subquery sits inside another more than three levels deep
    assert max(_depth(part) for part in sql.split(" UNION ALL ")) <= 3


def _depth(sql: str) -> int:
    depth = best = 0
    for char in sql:
        if char == "(":
            depth += 1
            best = max(best, depth)
        elif char == ")":
            depth -= 1
    return best


def test_a_source_with_an_unusable_name_does_not_load() -> None:
    for bad in (
        {"table": "cur_x; DROP TABLE y"},
        {"id_column": "id) OR (1=1"},
        {"class_column": "Klass"},
        {"clearance_table": "a b"},
        {"null_class": "privileged"},
        {"record_types": frozenset({"no-dot"})},
    ):
        base: dict[str, Any] = {
            "record_types": frozenset({ITEM}),
            "table": "cur_vault_item",
            "id_column": "id",
            "class_column": "klass",
            **bad,
        }
        with pytest.raises(ModuleLoadError):
            ConfidentialSource(**base)


def test_a_module_cannot_make_confidential_what_it_does_not_own() -> None:
    foreign = ConfidentialSource(
        record_types=frozenset({"other.Item"}),
        table="cur_other_item",
        id_column="id",
        class_column="klass",
    )
    with pytest.raises(ModuleLoadError, match="does not own"):
        spec(foreign)


# --- the shared reads --------------------------------------------------------------------------


def one(db: DbTarget, name: str, viewer: cf.Viewer, vault: Vault) -> Any:
    with cf.use_viewer(viewer), open_uow(db, readonly=True) as uow:
        return queries.get_record_by_id(uow, vault.ids[name])


def test_get_by_id_and_by_key_answer_none_for_a_hidden_record(db: DbTarget, vault: Vault) -> None:
    assert one(db, "restricted", USER, vault) is None
    assert one(db, "restricted", CONTROLLER, vault)["title"] == "SECRET-restricted"
    with cf.use_viewer(USER), open_uow(db, readonly=True) as uow:
        assert queries.get_record(uow, SCOPE, "K-restricted") is None
        assert queries.get_record(uow, SCOPE, "K-open") is not None
        assert queries.record_history(uow, vault.ids["restricted"]) == []
        assert queries.record_history(uow, vault.ids["open"]) != []
        assert queries.record_history(uow, "NO-SUCH") == []  # same answer as a hidden one


def test_the_query_language_does_not_find_or_count_a_hidden_record(
    db: DbTarget, vault: Vault
) -> None:
    spec_ = QuerySpec(scope=SCOPE, where=parse("SECRET"))
    with cf.use_viewer(USER), open_uow(db, readonly=True) as uow:
        found = {r["title"] for r in run_query(uow, spec_)}
        assert "SECRET-open" in found and "SECRET-restricted" not in found
        assert count_query(uow, spec_) == len(found)
    with cf.use_viewer(CONTROLLER), open_uow(db, readonly=True) as uow:
        assert "SECRET-restricted" in {r["title"] for r in run_query(uow, spec_)}


def link(db: DbTarget, vault: Vault, a: str, b: str) -> None:
    with cf.system_view(), open_uow(db) as uow:
        handle_add_link(
            uow,
            AddLink(
                actor="user:u",
                source="test",
                scope=SCOPE,
                from_id=vault.ids[a],
                to_id=vault.ids[b],
                relation="references",
            ),
            by_module=True,
        )


def test_a_link_to_a_hidden_record_is_not_listed_counted_traced_or_searched(
    db: DbTarget, vault: Vault
) -> None:
    link(db, vault, "open", "restricted")
    link(db, vault, "open", "note-open")
    with cf.use_viewer(USER), open_uow(db, readonly=True) as uow:
        others = {v.other_title for v in link_queries.links_of(uow, vault.ids["open"])}
        assert others == {"SECRET-note-open"}
        counts = link_queries.link_counts(uow, [vault.ids["open"], vault.ids["restricted"]])
        assert counts[vault.ids["open"]].active_out == 1
        assert counts[vault.ids["restricted"]].active_in == 0
        tree = link_trace.trace(uow, vault.ids["open"])
        assert {c.title for c in tree.children} == {"SECRET-note-open"}
        found = {t.title for t in link_queries.search_linkable(uow, SCOPE, "SECRET")}
        assert "SECRET-restricted" not in found and "SECRET-open" in found
        with pytest.raises(RecordNotFoundError):
            link_queries.links_of(uow, vault.ids["restricted"])
        with pytest.raises(RecordNotFoundError):
            link_trace.trace(uow, vault.ids["restricted"])
    with cf.use_viewer(CONTROLLER), open_uow(db, readonly=True) as uow:
        others = {v.other_title for v in link_queries.links_of(uow, vault.ids["open"])}
        assert others == {"SECRET-note-open", "SECRET-restricted"}
        counts = link_queries.link_counts(uow, [vault.ids["open"]])
        assert counts[vault.ids["open"]].active_out == 2


def test_a_command_on_a_link_with_a_hidden_end_answers_as_for_a_link_that_was_never_made(
    db: DbTarget, vault: Vault
) -> None:
    from tl_core.services.errors import LinkNotFoundError
    from tl_core.services.links import (
        AdminFlagLink,
        FlagLink,
        RetractLink,
        VerifyLink,
        handle_admin_flag_link,
        handle_flag_link,
        handle_retract_link,
        handle_verify_link,
    )

    link(db, vault, "open", "restricted")
    with open_uow(db, readonly=True) as uow:
        link_id = str(
            uow.conn()
            .execute(
                text("SELECT link_id FROM cur_links WHERE to_id = :t"),
                {"t": vault.ids["restricted"]},
            )
            .scalar_one()
        )
    base: dict[str, Any] = {"actor": "user:ann", "source": "test", "scope": SCOPE}
    attempts = [
        (handle_verify_link, VerifyLink(**base, link_id=link_id)),
        (handle_flag_link, FlagLink(**base, link_id=link_id, status="stale", reason="x")),
        (handle_retract_link, RetractLink(**base, link_id=link_id, reason="x")),
        (
            handle_admin_flag_link,
            AdminFlagLink(**base, link_id=link_id, status="stale", reason="x"),
        ),
    ]
    for handler, command in attempts:
        with cf.use_viewer(USER), open_uow(db) as uow:
            with pytest.raises(LinkNotFoundError) as seen:
                handler(uow, command)  # type: ignore[operator]
        with cf.use_viewer(USER), open_uow(db) as uow:
            with pytest.raises(LinkNotFoundError) as never:
                handler(uow, command.model_copy(update={"link_id": "01J000000000000000000000"}))  # type: ignore[operator]
        assert str(seen.value).replace(link_id, "X") == str(never.value).replace(
            "01J000000000000000000000", "X"
        )
    with cf.use_viewer(CONTROLLER), open_uow(db) as uow:  # a reader of both ends gets past it
        from tl_core.services.errors import UnsupportedRecordTypeError

        with pytest.raises(UnsupportedRecordTypeError):  # the module's own rule for the item
            handle_verify_link(uow, VerifyLink(**base, link_id=link_id))


def test_the_query_language_does_not_match_through_a_link_to_a_hidden_record(
    db: DbTarget, vault: Vault
) -> None:
    link(db, vault, "open", "restricted")
    spec_ = QuerySpec(scope=SCOPE, where=parse("linked(*).title:SECRET-restricted"))
    with cf.use_viewer(USER), open_uow(db, readonly=True) as uow:
        assert run_query(uow, spec_) == []
    with cf.use_viewer(CONTROLLER), open_uow(db, readonly=True) as uow:
        assert [r["title"] for r in run_query(uow, spec_)] == ["SECRET-open"]


def test_a_command_that_names_a_hidden_record_answers_as_if_it_did_not_exist(
    db: DbTarget, vault: Vault
) -> None:
    command = AddLink(
        actor="user:ann",
        source="test",
        scope=SCOPE,
        from_id=vault.ids["open"],
        to_id=vault.ids["restricted"],
        relation="references",
    )
    with cf.use_viewer(USER), open_uow(db) as uow:
        with pytest.raises(RecordNotFoundError):
            handle_add_link(uow, command, by_module=True)
    with cf.use_viewer(CONTROLLER), open_uow(db) as uow:
        assert handle_add_link(uow, command, by_module=True).events


def test_a_generic_edit_of_a_hidden_record_does_not_tell_its_type(
    db: DbTarget, vault: Vault
) -> None:
    from tl_core.services.commands import UpdateRecord
    from tl_core.services.records import handle_update_record

    def attempt(record_id: str, viewer: cf.Viewer) -> str:
        command = UpdateRecord(
            actor="user:ann", source="test", scope=SCOPE, stream_id=record_id,
            expected_version=1, changes={"title": "x"},
        )  # fmt: skip
        with cf.use_viewer(viewer), open_uow(db) as uow:
            with pytest.raises(Exception) as seen:
                handle_update_record(uow, command)
        return f"{type(seen.value).__name__}: {seen.value}".replace(record_id, "ID")

    hidden = attempt(vault.ids["restricted"], USER)
    never = attempt("01J000000000000000000000", USER)
    assert hidden.split(":")[0] == never.split(":")[0] == "RecordNotFoundError"
    assert "vault" not in hidden  # nothing about the module or the type
    # a reader gets the module's own answer
    assert attempt(vault.ids["restricted"], CONTROLLER).startswith("UnsupportedRecordTypeError")


def test_events_of_a_hidden_stream_are_filtered(db: DbTarget, vault: Vault) -> None:
    link(db, vault, "open", "restricted")
    with open_uow(db, readonly=True) as uow:
        everything = uow.ledger.read_after(0, scope=SCOPE, limit=1000)
        with cf.use_viewer(USER):
            shown = cf.filter_events(uow.conn(), everything)
        with cf.use_viewer(CONTROLLER):
            more = cf.filter_events(uow.conn(), everything)
        with cf.system_view():
            all_of_them = cf.filter_events(uow.conn(), everything)
    hidden_streams = {vault.ids[n] for n in ("restricted", "bogus", "null", "empty", "upper")}
    assert not {e.stream_id for e in shown} & hidden_streams
    assert vault.ids["restricted"] in {e.stream_id for e in more}
    assert len(all_of_them) == len(everything) > len(more) > len(shown)
    # the link event has a hidden end: it is hidden for the user, shown to the controller
    kinds = lambda events: [e.event_type for e in events if e.event_type.startswith("Link.")]  # noqa: E731
    assert kinds(shown) == [] and kinds(more) == ["Link.Added"]
