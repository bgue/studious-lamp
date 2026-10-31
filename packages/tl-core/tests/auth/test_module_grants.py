"""Grant and revoke a module role (roles-mvp.md section 3): checks in order, idempotence, events."""

from __future__ import annotations

import pytest
from moduleroles import P1, P2, Roles
from tl_core.auth import accounts
from tl_core.auth.errors import (
    AccountNotFoundError,
    ForbiddenError,
    InvalidAccountError,
    NoCompanyRolesError,
    NoSuchGrantError,
    UnknownModuleError,
    UnknownRoleError,
)
from tl_core.auth.module_grants import GrantModuleRole
from tl_core.auth.module_roles import load_role_table
from tl_core.changefeed import SubscriptionFilter
from tl_core.ledger import Event
from tl_core.modules import use_modules

GRANTED = "Account.ModuleRoleGranted"
REVOKED = "Account.ModuleRoleRevoked"


@pytest.fixture
def people(roles: Roles) -> Roles:
    roles.person("alice")
    roles.person("bob")
    roles.person("bot", kind="agent")
    return roles


def rows(r: Roles, account: str) -> list[tuple[str, str, str]]:
    with r.world.factory(readonly=True) as uow:
        found = uow.conn().exec_driver_sql(
            "SELECT project, module, role FROM cur_account_module_role "
            f"WHERE account_id = '{r.ids[account]}' ORDER BY project, module, role"
        )
        return [(str(a), str(b), str(c)) for a, b, c in found.all()]


def event_count(r: Roles) -> int:
    return r.count("SELECT COUNT(*) FROM events")


def test_a_grant_appends_one_event_and_writes_the_projection_row(people: Roles) -> None:
    before = event_count(people)
    done = people.grant("alice", P1, "documents", "superuser")
    assert done.changed is True and len(done.events) == 1
    assert event_count(people) == before + 1
    assert rows(people, "alice") == [(P1, "documents", "superuser")]
    with people.world.factory(readonly=True) as uow:
        row = (
            uow.conn()
            .exec_driver_sql("SELECT granted_by FROM cur_account_module_role")
            .scalar_one()
        )
    assert row == "user:ada"


def test_the_event_sits_on_the_account_stream_in_company_scope(people: Roles) -> None:
    people.grant("alice", P1, "documents", "superuser")
    kinds = people.world.rows(
        "SELECT stream_type, scope, stream_id, actor, event_type FROM events "
        "WHERE event_type LIKE 'Account.ModuleRole%'"
    )
    assert kinds == [
        ("core.Account", "company", f"account:{people.ids['alice']}", "user:ada", GRANTED)
    ]


def test_granting_a_role_already_held_appends_nothing_and_answers_changed_false(
    people: Roles,
) -> None:
    people.grant("alice", P1, "documents", "superuser")
    before = event_count(people)
    again = people.grant("alice", P1, "documents", "superuser")
    assert again.changed is False and again.events == []
    assert event_count(people) == before


def test_a_revoke_removes_the_row_and_appends_a_revoked_event(people: Roles) -> None:
    people.grant("alice", P1, "documents", "superuser")
    gone = people.revoke("alice", P1, "documents", "superuser")
    assert gone.changed is True and len(gone.events) == 1
    assert rows(people, "alice") == []
    assert [e[0] for e in people.world.events() if e[0].startswith("Account.ModuleRole")] == [
        GRANTED,
        REVOKED,
    ]


def test_revoking_a_role_not_held_is_no_such_grant_and_writes_nothing(people: Roles) -> None:
    before = event_count(people)
    with pytest.raises(NoSuchGrantError):
        people.revoke("alice", P1, "documents", "superuser")
    people.grant("alice", P1, "documents", "superuser")
    people.revoke("alice", P1, "documents", "superuser")
    with pytest.raises(NoSuchGrantError):
        people.revoke("alice", P1, "documents", "superuser")
    assert event_count(people) == before + 2


def test_a_revoke_names_the_exact_project_module_and_role(people: Roles) -> None:
    people.grant("alice", P1, "documents", "superuser")
    for project, module, role in (
        (P2, "documents", "superuser"),
        (P1, "cost", "superuser"),
        (P1, "documents", "user"),
    ):
        with pytest.raises(NoSuchGrantError):
            people.revoke("alice", project, module, role)
    assert rows(people, "alice") == [(P1, "documents", "superuser")]


def test_a_grant_made_under_an_older_table_can_still_be_revoked(people: Roles) -> None:
    people.grant("alice", P1, "documents", "viewer")
    # the same row with a role the table no longer has: revoke checks only admin, account, held
    people.raw_grant("bob", P1, "retired_module", "retired_role")
    done = people.revoke("bob", P1, "retired_module", "retired_role")
    assert done.changed is True and rows(people, "bob") == []
    with pytest.raises(UnknownRoleError):
        people.grant("bob", P1, "documents", "retired_role")


def test_the_checks_run_in_the_documented_order(people: Roles) -> None:
    # admin first: a plain user is forbidden even with every other field wrong
    with pytest.raises(ForbiddenError):
        people.grant("no-such", P1, "no_module", "no_role", by="user:alice")
    # then the account
    with pytest.raises(AccountNotFoundError):
        people.grant("no-such", P1, "no_module", "no_role")
    # then the role, then the module, then the agent cap
    with pytest.raises(UnknownRoleError):
        people.grant("alice", P1, "no_module", "no_role")
    with pytest.raises(UnknownModuleError):
        people.grant("alice", P1, "no_module", "user")
    with pytest.raises(InvalidAccountError):
        people.grant("bot", P1, "documents", "superuser")


@pytest.mark.parametrize("by", ["user:alice", "user:nobody", "agent:bot", "svc:rule"])
def test_only_an_active_human_admin_grants_or_revokes(people: Roles, by: str) -> None:
    people.grant("bob", P1, "documents", "viewer")
    with pytest.raises(ForbiddenError):
        people.grant("alice", P1, "documents", "user", by=by)
    with pytest.raises(ForbiddenError):
        people.revoke("bob", P1, "documents", "viewer", by=by)
    assert rows(people, "alice") == []


def test_a_disabled_admin_cannot_grant(people: Roles) -> None:
    people.person("boss", ("admin",))
    with people.world.factory() as uow:
        accounts.disable(uow, account_id=people.ids["boss"], by="user:ada", reason="away")
    with pytest.raises(ForbiddenError):
        people.grant("alice", P1, "documents", "user", by="user:boss")


def test_an_agent_may_hold_only_the_agent_roles(people: Roles) -> None:
    assert load_role_table().agent_roles == ("viewer", "user")
    assert people.grant("bot", P1, "documents", "user").changed is True
    assert people.grant("bot", P1, "documents", "viewer").changed is True
    with pytest.raises(InvalidAccountError):
        people.grant("bot", P1, "documents", "superuser")
    assert rows(people, "bot") == [(P1, "documents", "user"), (P1, "documents", "viewer")]


def test_the_all_modules_name_is_accepted_and_a_wrong_module_is_not(people: Roles) -> None:
    assert people.grant("alice", P1, "*", "viewer").changed is True
    with pytest.raises(UnknownModuleError):
        people.grant("alice", P1, "documentz", "viewer")


def test_a_company_grant_for_a_module_without_company_roles_is_refused(people: Roles) -> None:
    for module in ("documents", "*", "ghost"):
        with pytest.raises(NoCompanyRolesError):
            people.grant("alice", "company", module, "user")


def test_a_company_grant_needs_a_module_that_declares_company_roles(people: Roles) -> None:
    from moduleroles import spec

    with use_modules([spec("standin", company_roles=True), spec("plain")]):
        assert people.grant("alice", "company", "standin", "superuser").changed is True
        with pytest.raises(NoCompanyRolesError):
            people.grant("alice", "company", "plain", "user")


def test_the_command_scope_is_company_and_the_project_is_checked() -> None:
    GrantModuleRole(
        actor="user:ada",
        source="t",
        account_id="a",
        project=P1,
        module="m",
        role="user",
        reason="r",
    )
    with pytest.raises(ValueError, match="scope"):
        GrantModuleRole(
            actor="user:ada", source="t", scope=P1, account_id="a",
            project=P1, module="m", role="user", reason="r",
        )  # fmt: skip
    for bad in ("P1", "project:", "project:a b", "projects:P1"):
        with pytest.raises(ValueError):
            GrantModuleRole(
                actor="user:ada", source="t", account_id="a",
                project=bad, module="m", role="user", reason="r",
            )  # fmt: skip
    for reason in ("", "x" * 501):
        with pytest.raises(ValueError):
            GrantModuleRole(
                actor="user:ada", source="t", account_id="a",
                project=P1, module="m", role="user", reason=reason,
            )  # fmt: skip


def test_the_grant_events_are_hidden_from_a_subscriber_that_is_not_an_admin(
    people: Roles,
) -> None:
    done = people.grant("alice", P1, "documents", "superuser")
    revoked = people.revoke("alice", P1, "documents", "superuser")
    events: list[Event] = [*done.events, *revoked.events]
    assert [e.event_type for e in events] == [GRANTED, REVOKED]
    assert {e.stream_type for e in events} == {"core.Account"}
    default = SubscriptionFilter.of()  # what every non-admin consumer builds
    admin = SubscriptionFilter.of(hide_stream_types=())  # what the API builds for an admin
    assert not any(default.matches(e) for e in events)
    assert all(admin.matches(e) for e in events)
