"""Acceptance script for P2-W0 RM-S1: module roles, grants, resolver, company grants.

Runs on SQLite with a temp ledger. Prints one ``PASS <check>`` line per check and the precedence
table (holder x result); exits 0 when every check passes, 1 on the first failure.
"""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

from sqlalchemy import text
from tl_adapters.db import create_schema, make_uow_factory
from tl_core.auth import accounts
from tl_core.auth.errors import (
    ForbiddenError,
    InvalidAccountError,
    NoCompanyRolesError,
    NoSuchGrantError,
    RoleTableError,
    UnknownModuleError,
    UnknownRoleError,
)
from tl_core.auth.module_grants import (
    GrantModuleRole,
    RevokeModuleRole,
    grant_module_role,
    revoke_module_role,
)
from tl_core.auth.module_roles import (
    Holder,
    command_index,
    effective_roles,
    holder_for_actor,
    holds_word,
    load_role_table,
    require_command_access,
)
from tl_core.auth.projector import account_stream_id
from tl_core.ledger import NewEvent
from tl_core.modules import ModuleSpec, use_modules
from tl_core.services.commands import Command

P1, P2 = "project:P1", "project:P2"
TABLE_FILE = Path(__file__).resolve().parents[3] / "schema" / "settings" / "module-roles.yaml"
TABLE = TABLE_FILE.read_text(encoding="utf-8")
ROWS: list[tuple[str, str, str, str]] = []


def passed(check: str) -> None:
    print(f"PASS {check}")


def refuses(error: type[Exception], call: Callable[[], Any]) -> None:
    try:
        call()
    except error:
        return
    raise AssertionError(f"expected {error.__name__}")


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="rm-s1-"))
    db = work / "ledger.db"
    create_schema(db)
    factory = make_uow_factory(db)
    try:
        run(factory, work)
    finally:
        factory.dispose()
    return 0


class DoThing(Command):
    """A stand-in module command for require_command_access."""


def run(factory: Any, work: Path) -> None:
    ids: dict[str, str] = {}

    def make(name: str, roles: tuple[str, ...], kind: str = "person") -> None:
        with factory() as uow:
            view = accounts.create_account(
                uow, username=name, display_name=name.title(), kind=kind,  # type: ignore[arg-type]
                roles=list(roles), password=None, by="user:root",
            )  # fmt: skip
        ids[name] = view.account_id

    make("ada", ("admin",))
    make("alice", ("user",))
    make("bob", ("user",))
    make("carol", ("user",))
    make("dora", ("document_controller",))
    make("dora2", ("document_controller", "user"))
    make("zed", ("user",))
    make("bot", ("user",), kind="agent")
    make("late", ("user",))

    def cmd(cls: type[Any], actor: str, who: str, project: str, module: str, role: str) -> Any:
        return cls(
            actor=actor, source="accept", scope="company", account_id=ids[who],
            project=project, module=module, role=role, reason="acceptance",
        )  # fmt: skip

    def grant(who: str, project: str, module: str, role: str, by: str = "user:ada") -> Any:
        with factory() as uow:
            return grant_module_role(uow, cmd(GrantModuleRole, by, who, project, module, role))

    def revoke(who: str, project: str, module: str, role: str, by: str = "user:ada") -> Any:
        with factory() as uow:
            return revoke_module_role(uow, cmd(RevokeModuleRole, by, who, project, module, role))

    def resolve(actor: str, scope: str, module: str, holder: Holder | None = None) -> Any:
        with factory(readonly=True) as uow:
            conn = uow.conn()
            who = holder if holder is not None else holder_for_actor(conn, actor)
            return effective_roles(conn, who, scope=scope, module=module)

    def rows(sql: str, **params: Any) -> list[Any]:
        with factory(readonly=True) as uow:
            return [tuple(r) for r in uow.conn().execute(text(sql), params).all()]

    def show(label: str, scope: str, module: str, got: Any) -> None:
        ROWS.append((label, f"{scope} {module}", ",".join(sorted(got.roles)) or "-", got.source))

    # --- the table ---------------------------------------------------------------------------
    table = load_role_table()
    assert list(table.roles) == ["viewer", "user", "superuser"], table.roles
    assert set(table.words) == {"read", "user", "controller"}
    assert table.agent_roles == ("viewer", "user")
    passed("role table loads: three roles, three words, agent_roles viewer+user")

    def bad(name: str, old: str, new: str) -> None:
        assert old in TABLE, old
        copy = work / f"{name}.yaml"
        copy.write_text(TABLE.replace(old, new, 1), encoding="utf-8")
        refuses(RoleTableError, lambda: load_role_table(copy))

    bad("word", "superuser: [read, user, controller]", "superuser: [read, user, approve]")
    passed("unknown word in a bad copy is a RoleTableError")
    bad("role", "- {module: documents, role: superuser}", "- {module: documents, role: boss}")
    passed("unknown role in a bad copy is a RoleTableError")
    bad("account_role", "  document_controller:\n", "  site_manager:\n")
    passed("unknown account role in a bad copy is a RoleTableError")
    bad("agent", "agent_roles: [viewer, user]", "agent_roles: [viewer, boss]")
    bad("platform", "  read: Read", "  admin: Read")
    passed("unknown agent role and a platform word in the table are RoleTableErrors")

    # --- grants and revokes ------------------------------------------------------------------
    before = rows("SELECT COUNT(*) FROM events")[0][0]
    first = grant("alice", P1, "documents", "superuser")
    assert first.changed and len(first.events) == 1
    held = rows(
        "SELECT project, module, role, granted_by FROM cur_account_module_role "
        "WHERE account_id = :a", a=ids["alice"],
    )  # fmt: skip
    assert held == [(P1, "documents", "superuser", "user:ada")], held
    passed("ada grants alice superuser of documents on P1: event appended, projection row present")
    again = grant("alice", P1, "documents", "superuser")
    assert again.changed is False and again.events == []
    assert rows("SELECT COUNT(*) FROM events")[0][0] == before + 1
    passed("a repeated grant appends nothing and answers changed: false")

    gone = revoke("alice", P1, "documents", "superuser")
    assert gone.changed and rows("SELECT COUNT(*) FROM cur_account_module_role") == [(0,)]
    refuses(NoSuchGrantError, lambda: revoke("alice", P1, "documents", "superuser"))
    passed("revoke removes the row; a second revoke is NoSuchGrantError")
    grant("alice", P1, "documents", "superuser")  # kept for the precedence table

    refuses(UnknownRoleError, lambda: grant("bob", P1, "documents", "boss"))
    refuses(UnknownModuleError, lambda: grant("bob", P1, "no_such_module", "user"))
    refuses(InvalidAccountError, lambda: grant("bot", P1, "documents", "superuser"))
    refuses(ForbiddenError, lambda: grant("bob", P1, "documents", "user", by="user:alice"))
    refuses(ForbiddenError, lambda: grant("bob", P1, "documents", "user", by="user:nobody"))
    refuses(NoCompanyRolesError, lambda: grant("bob", "company", "documents", "user"))
    refuses(NoCompanyRolesError, lambda: grant("bob", "company", "*", "user"))
    passed(
        "unknown role / module, agent superuser, non-admin granter, company without roles refused"
    )
    assert grant("bot", P1, "documents", "user").changed  # an agent may hold user
    passed("an agent may be granted a role in agent_roles")

    # the events are on the account stream, stream type core.Account, scope company
    kinds = rows(
        "SELECT DISTINCT stream_type, scope, stream_id FROM events WHERE event_type LIKE "
        "'Account.ModuleRole%' AND stream_id = :s", s=account_stream_id(ids["alice"]),
    )  # fmt: skip
    assert kinds == [("core.Account", "company", account_stream_id(ids["alice"]))], kinds
    passed("events are stream type core.Account, scope company, on account:<id>")

    # --- precedence 1-7 ----------------------------------------------------------------------
    # explicit grants for the table; the agent's superuser goes in as a raw event (the command
    # refuses it) to prove the resolver caps an agent at agent_roles whatever the ledger holds
    grant("bob", P1, "documents", "viewer")  # replaces bob's derived user
    grant("carol", P1, "*", "superuser")
    grant("carol", P1, "documents", "viewer")  # a module grant wins over '*'
    grant("zed", P1, "documents", "superuser")
    with factory() as uow:
        version = int(
            uow.conn()
            .execute(
                text("SELECT version FROM cur_account WHERE account_id = :a"), {"a": ids["bot"]}
            )
            .scalar_one()
        )
        uow.append(
            stream_id=account_stream_id(ids["bot"]), stream_type="core.Account", scope="company",
            expected_version=version, actor="user:ada", source="accept", correlation_id="c" * 26,
            events=[NewEvent(event_type="Account.ModuleRoleGranted", payload={
                "account_id": ids["bot"], "project": P1, "module": "correspondence",
                "role": "superuser", "reason": "raw"})],
        )  # fmt: skip
    with factory() as uow:
        accounts.disable(uow, account_id=ids["zed"], by="user:ada", reason="acceptance")

    def expect(label: str, got: Any, roles: set[str], source: str) -> None:
        assert got.roles == frozenset(roles) and got.source == source, (label, got)

    r = resolve("user:zed", P1, "documents")
    show("disabled zed (granted superuser)", P1, "documents", r)
    expect("disabled", r, set(), "none")
    r = resolve("user:ALICE", P1, "documents")
    show("inexact actor user:ALICE", P1, "documents", r)
    expect("inexact", r, set(), "none")
    r = resolve("user:nobody", P1, "documents")
    show("missing account user:nobody", P1, "documents", r)
    expect("missing", r, set(), "none")
    r = resolve("user:ada", P1, "documents")
    show("admin ada", P1, "documents", r)
    expect("admin", r, set(table.roles), "admin")
    assert "admin" in r.words and r.words >= {"read", "user", "controller"}
    r = resolve("user:alice", "company", "documents")
    show("alice at command scope company", "company", "documents", r)
    expect("company scope ignores project grants", r, {"user"}, "derived")
    r = resolve("user:alice", P1, "documents")
    show("alice, explicit grant", P1, "documents", r)
    expect("granted", r, {"superuser"}, "granted")
    r = resolve("user:bob", P1, "documents")
    show("bob, explicit viewer replaces derived user", P1, "documents", r)
    expect("replace", r, {"viewer"}, "granted")
    assert not r.words >= {"user"} and r.words == frozenset({"read"})
    r = resolve("user:bob", P1, "cost")
    show("bob, other module: derived", P1, "cost", r)
    expect("derived", r, {"user"}, "derived")
    r = resolve("user:carol", P1, "schedule")
    show("carol, '*' grant", P1, "schedule", r)
    expect("*", r, {"superuser"}, "granted_all_modules")
    r = resolve("user:carol", P1, "documents")
    show("carol, module grant beats '*'", P1, "documents", r)
    expect("module over *", r, {"viewer"}, "granted")
    r = resolve("user:alice", P2, "documents")
    show("alice on P2: P1 grant does not apply", P2, "documents", r)
    expect("other project", r, {"user"}, "derived")
    for module in ("documents", "correspondence", "schedule"):
        r = resolve("user:dora", P1, module)
        show("dora (document_controller)", P1, module, r)
        expect("dora", r, {"superuser"}, "derived")
    r = resolve("user:dora", P1, "cost")
    show("dora, other module", P1, "cost", r)
    expect("dora none", r, set(), "none")
    r = resolve("user:dora2", P1, "documents")
    show("dora2 (controller + user)", P1, "documents", r)
    expect("dora2", r, {"user", "superuser"}, "derived")
    r = resolve("agent:bot", P1, "correspondence")
    show("agent bot, raw superuser event", P1, "correspondence", r)
    expect("agent cap", r, set(), "none")
    r = resolve("agent:bot", P1, "documents")
    show("agent bot, user grant", P1, "documents", r)
    expect("agent user", r, {"user"}, "granted")
    assert "controller" not in r.words
    for held, words in (("user", {"user"}), ("controller", {"user", "controller"}), (None, set())):
        with mock.patch("tl_core.integration.actor_access.held_access", return_value=held):
            r = resolve("svc:rule-demo", P1, "documents")
        show(f"service actor, held {held}", P1, "documents", r)
        assert r.words == frozenset(words) and r.source == ("service" if held else "none"), r
    passed("precedence 1-7: disabled, inexact, admin, company scope, grant, '*', derived, none")
    passed("document_controller derives superuser of documents, correspondence and schedule")
    passed("agent capped at agent_roles; svc: actor keeps its held access")

    with factory(readonly=True) as uow:
        conn = uow.conn()
        holder = holder_for_actor(conn, "user:alice")
        assert holds_word(conn, holder, scope=P1, module="documents", word="controller")
        assert not holds_word(conn, holder, scope=P2, module="documents", word="controller")
    passed("holds_word follows the scope")

    # --- company grants with stand-in modules ------------------------------------------------
    def spec(name: str, *, company_roles: bool, words: dict[str, str] | None = None) -> ModuleSpec:
        return ModuleSpec(
            name=name, record_types=frozenset(), projectors=lambda: [],
            command_words=words or {}, company_roles=company_roles,
        )  # fmt: skip

    with use_modules(
        [
            spec("standin", company_roles=True, words={"DoThing": "controller"}),
            spec("plain", company_roles=False),
        ]
    ):
        assert grant("late", "company", "standin", "superuser").changed
        refuses(NoCompanyRolesError, lambda: grant("late", "company", "plain", "user"))
        refuses(NoCompanyRolesError, lambda: grant("late", "company", "*", "user"))
        refuses(NoCompanyRolesError, lambda: grant("late", "company", "ghost", "user"))
        r = resolve("user:late", "company", "standin")
        show("late, company grant (company_roles)", "company", "standin", r)
        expect("company grant", r, {"superuser"}, "granted")
        r = resolve("user:late", P1, "standin")
        show("late on P1: company grant not read", P1, "standin", r)
        expect("project ignores company", r, {"user"}, "derived")
        grant("late", P1, "standin", "viewer")
        r = resolve("user:late", "company", "standin")
        expect("company ignores project", r, {"superuser"}, "granted")
        r = resolve("user:late", "company", "plain")
        show("late, company scope, no company_roles", "company", "plain", r)
        expect("derived only", r, {"user"}, "derived")
        assert command_index() == {"DoThing": ("standin", "controller")}
        with factory(readonly=True) as uow:
            conn = uow.conn()
            for scope, allowed in (("company", True), (P1, False)):
                command = DoThing(actor="user:late", source="accept", scope=scope)
                if allowed:
                    require_command_access(conn, command)
                else:
                    refuses(ForbiddenError, lambda c=command: require_command_access(conn, c))
    passed("company grant accepted for company_roles module, read at scope company only")
    passed("company grant for a module without company_roles refused: NoCompanyRolesError")
    passed("require_command_access: command word checked against the holder's words")

    print()
    print(f"{'holder':44} {'scope module':28} {'roles':22} source")
    for label, where, got_roles, source in ROWS:
        print(f"{label:44} {where:28} {got_roles:22} {source}")


if __name__ == "__main__":
    sys.exit(main())
