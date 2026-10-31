"""The resolver (roles-mvp.md section 4): precedence 1 to 7, agent cap, service actors, scope."""

from __future__ import annotations

from unittest import mock

import pytest
from moduleroles import P1, P2, Roles
from tl_core.auth import accounts
from tl_core.auth.module_roles import (
    Holder,
    holder_for_actor,
    holder_for_principal,
    holds_word,
    load_role_table,
    scoped_holds,
)
from tl_core.auth.types import Principal

ALL_ROLES = set(load_role_table().roles)


@pytest.fixture
def people(roles: Roles) -> Roles:
    roles.person("alice")
    roles.person("bob")
    roles.person("carol")
    roles.person("dora", ("document_controller",))
    roles.person("dora2", ("document_controller", "user"))
    roles.person("zed")
    roles.person("bot", kind="agent")
    return roles


# --- 1: disabled, missing or inexact -----------------------------------------------------------


def test_1_a_disabled_account_holds_nothing_whatever_it_was_granted(people: Roles) -> None:
    people.grant("zed", P1, "documents", "superuser")
    assert people.resolve("user:zed", P1, "documents").source == "granted"
    with people.world.factory() as uow:
        accounts.disable(uow, account_id=people.ids["zed"], by="user:ada", reason="away")
    got = people.resolve("user:zed", P1, "documents")
    assert (got.roles, got.words, got.source) == (frozenset(), frozenset(), "none")


def test_1_a_disabled_admin_holds_nothing(people: Roles) -> None:
    people.person("boss", ("admin",))
    with people.world.factory() as uow:
        accounts.disable(uow, account_id=people.ids["boss"], by="user:ada", reason="away")
    assert people.resolve("user:boss", P1, "documents").source == "none"


@pytest.mark.parametrize("actor", ["user:ALICE", "user:Alice", "agent:alice"])
def test_1_an_inexact_or_missing_actor_holds_nothing(people: Roles, actor: str) -> None:
    people.grant("alice", P1, "documents", "superuser")
    got = people.resolve(actor, P1, "documents")
    assert got.source == "none" and not got.roles and not got.words


def test_1_a_missing_account_holds_nothing_off_the_dev_ledger(people: Roles) -> None:
    with people.world.factory(readonly=True) as uow:
        ghost = holder_for_actor(uow.conn(), "user:nobody", dev_file=False)
    assert people.resolve("user:nobody", P1, "documents", ghost).source == "none"


def test_1_a_holder_with_no_account_id_holds_nothing(people: Roles) -> None:
    ghost = Holder(actor="user:alice", kind="person", account_id=None, account_roles=("admin",))
    assert people.resolve("user:alice", P1, "documents", ghost).source == "none"


# --- 2: admin ---------------------------------------------------------------------------------


def test_2_an_active_admin_holds_every_role_and_word_plus_admin(people: Roles) -> None:
    got = people.resolve("user:ada", P1, "documents")
    assert got.source == "admin" and got.roles == ALL_ROLES
    assert got.words == {"read", "user", "controller", "admin"}


def test_2_admin_beats_a_viewer_grant(people: Roles) -> None:
    people.person("kim", ("admin", "user"))
    people.grant("kim", P1, "documents", "viewer")
    got = people.resolve("user:kim", P1, "documents")
    assert got.source == "admin" and "controller" in got.words and "admin" in got.words


# --- 3: company scope -------------------------------------------------------------------------


def test_3_a_project_grant_is_not_read_at_company_scope(people: Roles) -> None:
    people.grant("alice", P1, "documents", "superuser")
    got = people.resolve("user:alice", "company", "documents")
    assert got.roles == {"user"} and got.source == "derived"


def test_3_an_all_modules_grant_is_not_read_at_company_scope(people: Roles) -> None:
    people.grant("carol", P1, "*", "superuser")
    assert people.resolve("user:carol", "company", "documents").source == "derived"


# --- 4: grants for (account, project, module) replace the derived roles ------------------------


def test_4_an_explicit_viewer_replaces_the_derived_user(people: Roles) -> None:
    people.grant("bob", P1, "documents", "viewer")
    got = people.resolve("user:bob", P1, "documents")
    assert got.roles == {"viewer"} and got.words == {"read"} and got.source == "granted"


def test_4_an_explicit_grant_holds_where_nothing_was_derived(people: Roles) -> None:
    people.person("pat", ("document_controller",))
    people.grant("pat", P1, "cost", "superuser")
    assert people.resolve("user:pat", P1, "cost").source == "granted"
    assert people.resolve("user:pat", P1, "engineering").source == "derived"


def test_4_a_grant_binds_one_project_and_one_module(people: Roles) -> None:
    people.grant("alice", P1, "documents", "superuser")
    assert people.resolve("user:alice", P1, "documents").roles == {"superuser"}
    other_project = people.resolve("user:alice", P2, "documents")
    assert other_project.roles == {"user"} and other_project.source == "derived"
    other_module = people.resolve("user:alice", P1, "cost")
    assert other_module.roles == {"user"} and other_module.source == "derived"


def test_4_several_roles_for_one_module_are_unioned(people: Roles) -> None:
    people.grant("bob", P1, "cost", "viewer")
    people.grant("bob", P1, "cost", "superuser")
    got = people.resolve("user:bob", P1, "cost")
    assert got.roles == {"viewer", "superuser"} and got.words == {"read", "user", "controller"}


def test_4_a_revoke_returns_the_account_to_its_derived_roles(people: Roles) -> None:
    people.grant("bob", P1, "documents", "viewer")
    people.revoke("bob", P1, "documents", "viewer")
    got = people.resolve("user:bob", P1, "documents")
    assert got.roles == {"user"} and got.source == "derived"


# --- 5: grants for (account, project, "*") ----------------------------------------------------


def test_5_an_all_modules_grant_covers_every_module_of_the_project(people: Roles) -> None:
    people.grant("carol", P1, "*", "superuser")
    for module in ("schedule", "cost", "documents"):
        got = people.resolve("user:carol", P1, module)
        assert got.roles == {"superuser"} and got.source == "granted_all_modules"
    assert people.resolve("user:carol", P2, "schedule").source == "derived"


def test_5_a_module_grant_beats_the_all_modules_grant(people: Roles) -> None:
    people.grant("carol", P1, "*", "superuser")
    people.grant("carol", P1, "documents", "viewer")
    got = people.resolve("user:carol", P1, "documents")
    assert got.roles == {"viewer"} and got.source == "granted"
    assert people.resolve("user:carol", P1, "schedule").roles == {"superuser"}


# --- 6: derived -------------------------------------------------------------------------------


def test_6_a_user_derives_user_in_every_module(people: Roles) -> None:
    for module in ("documents", "cost", "schedule"):
        got = people.resolve("user:alice", P1, module)
        assert got.roles == {"user"} and got.source == "derived"
        assert got.words == {"read", "user"}


def test_6_a_document_controller_derives_superuser_of_three_modules(people: Roles) -> None:
    for module in ("documents", "correspondence", "schedule"):
        got = people.resolve("user:dora", P1, module)
        assert "superuser" in got.roles and got.source == "derived"
        assert "controller" in got.words
    other = people.resolve("user:dora", P1, "cost")
    assert other.roles == {"user"} and "controller" not in other.words


def test_6_two_account_roles_union_their_derived_roles(people: Roles) -> None:
    got = people.resolve("user:dora2", P1, "documents")
    assert got.roles == {"user", "superuser"}


# --- 7: nothing --------------------------------------------------------------------------------


def test_7_an_account_with_no_derived_role_holds_nothing(roles: Roles) -> None:
    roles.person("odd", ("document_controller",))
    got = roles.resolve("user:odd", P1, "engineering")
    assert got.roles == {"user"}  # D3: the controller derives `user` in every module
    # an account whose roles derive nothing: remove them all through an empty holder
    empty = Holder(actor="user:odd", kind="person", account_id=roles.ids["odd"], account_roles=())
    assert roles.resolve("user:odd", P1, "engineering", empty).source == "none"


def test_7_a_role_no_longer_in_the_table_grants_nothing(people: Roles) -> None:
    people.raw_grant("alice", P1, "documents", "retired_role")
    got = people.resolve("user:alice", P1, "documents")
    assert got.roles == {"user"} and got.source == "derived"
    people.person("lone", ("document_controller",))
    empty = Holder(
        actor="user:lone", kind="person", account_id=people.ids["lone"], account_roles=()
    )
    people.raw_grant("lone", P1, "documents", "retired_role")
    assert people.resolve("user:lone", P1, "documents", empty).source == "none"


# --- agents, services --------------------------------------------------------------------------


def test_an_agent_holds_at_most_the_agent_roles(people: Roles) -> None:
    people.raw_grant("bot", P1, "correspondence", "superuser")  # the command would refuse it
    got = people.resolve("agent:bot", P1, "correspondence")
    assert got.roles == frozenset() and got.source == "none" and "controller" not in got.words
    people.grant("bot", P1, "documents", "user")
    ok = people.resolve("agent:bot", P1, "documents")
    assert ok.roles == {"user"} and ok.source == "granted" and "controller" not in ok.words


def test_an_agent_with_both_a_capped_and_an_allowed_role_keeps_only_the_allowed(
    people: Roles,
) -> None:
    people.grant("bot", P1, "cost", "viewer")
    people.raw_grant("bot", P1, "cost", "superuser")
    got = people.resolve("agent:bot", P1, "cost")
    assert got.roles == {"viewer"} and got.words == {"read"}


@pytest.mark.parametrize(
    ("held", "words", "source"),
    [
        ("user", {"user"}, "service"),
        ("controller", {"user", "controller"}, "service"),
        ("admin", set(), "none"),
        (None, set(), "none"),
    ],
)
def test_a_service_actor_keeps_its_declared_access(
    roles: Roles, held: str | None, words: set[str], source: str
) -> None:
    with mock.patch("tl_core.integration.actor_access.held_access", return_value=held):
        got = roles.resolve("svc:rule-demo", P1, "documents")
    assert got.words == frozenset(words) and got.source == source and not got.roles


# --- the holders and the helpers --------------------------------------------------------------


def test_holder_for_actor_reads_the_account_row_and_keeps_the_id_of_a_twin(people: Roles) -> None:
    with people.world.factory(readonly=True) as uow:
        conn = uow.conn()
        exact = holder_for_actor(conn, "user:dora")
        twin = holder_for_actor(conn, "user:DORA")
        none = holder_for_actor(conn, "user:nobody", dev_file=False)
        agent = holder_for_actor(conn, "agent:bot")
        svc = holder_for_actor(conn, "svc:x")
    assert exact.account_id == people.ids["dora"] and exact.account_roles == (
        "document_controller",
    )
    assert twin.account_id == people.ids["dora"]  # refused later by precedence 1
    assert none.account_id is None and none.account_roles == ()
    assert agent.kind == "agent"
    assert svc.kind == "service" and svc.account_id is None


def test_the_dev_ledger_gives_an_account_less_user_actor_the_user_role_only(roles: Roles) -> None:
    with roles.world.factory(readonly=True) as uow:
        conn = uow.conn()
        dev = holder_for_actor(conn, "user:dev")
        off = holder_for_actor(conn, "user:dev", dev_file=False)
        agent = holder_for_actor(conn, "agent:ghost")
    assert dev.account_id == "dev:user:dev" and dev.account_roles == ("user",)
    assert off.account_id is None
    assert agent.account_id is None
    got = roles.resolve("user:dev", P1, "documents", dev)
    assert got.words == {"read", "user"} and "controller" not in got.words


def test_holder_for_principal_copies_the_principal(people: Roles) -> None:
    principal = Principal(
        actor="user:alice",
        kind="person",
        account_id=people.ids["alice"],
        roles=["user"],
        via="session",
    )
    holder = holder_for_principal(principal)
    assert (holder.actor, holder.kind, holder.account_id) == (
        "user:alice",
        "person",
        people.ids["alice"],
    )
    assert holder.account_roles == ("user",)


def test_holds_word_follows_the_scope(people: Roles) -> None:
    people.grant("alice", P1, "documents", "superuser")
    with people.world.factory(readonly=True) as uow:
        conn = uow.conn()
        who = holder_for_actor(conn, "user:alice")
        assert holds_word(conn, who, scope=P1, module="documents", word="controller")
        assert not holds_word(conn, who, scope=P2, module="documents", word="controller")
        assert holds_word(conn, who, scope=P2, module="documents", word="user")
        assert not holds_word(conn, who, scope=P1, module="documents", word="admin")


def test_scoped_holds_takes_admin_from_the_base_and_the_rest_from_the_roles(
    people: Roles,
) -> None:
    people.grant("alice", P1, "documents", "superuser")
    calls: list[str] = []

    def base(level: str) -> bool:
        calls.append(level)
        return level == "admin"

    with people.world.factory(readonly=True) as uow:
        conn = uow.conn()
        who = holder_for_actor(conn, "user:alice")
        here = scoped_holds(conn, who, scope=P1, module="documents", base=base)  # type: ignore[arg-type]
        there = scoped_holds(conn, who, scope=P2, module="documents", base=base)  # type: ignore[arg-type]
    assert here("user") and here("controller") and here("admin")
    assert there("user") and not there("controller") and there("admin")
    assert calls == ["admin", "admin"]
