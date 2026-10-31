"""Company-level grants (wave0.md section 2): only for a module that declares ``company_roles``."""

from __future__ import annotations

import pytest
from moduleroles import P1, Roles, spec
from tl_core.auth.errors import ForbiddenError, NoCompanyRolesError
from tl_core.auth.module_roles import command_index, holder_for_actor, require_command_access
from tl_core.modules import use_modules
from tl_core.services.commands import Command


class DoThing(Command):
    """A stand-in module command for require_command_access."""


@pytest.fixture
def late(roles: Roles) -> Roles:
    roles.person("late")
    return roles


def standins():  # noqa: ANN202 - a context manager
    return use_modules(
        [
            spec("standin", company_roles=True, words={"DoThing": "controller"}),
            spec("plain", company_roles=False),
        ]
    )


def test_a_company_grant_is_accepted_for_a_module_with_company_roles(late: Roles) -> None:
    with standins():
        assert late.grant("late", "company", "standin", "superuser").changed is True
        assert late.grant("late", "company", "standin", "superuser").changed is False


def test_a_company_grant_for_any_other_module_raises_no_company_roles(late: Roles) -> None:
    with standins():
        for module in ("plain", "*", "ghost"):
            with pytest.raises(NoCompanyRolesError):
                late.grant("late", "company", module, "user")


def test_the_company_grant_is_read_at_scope_company_only(late: Roles) -> None:
    with standins():
        late.grant("late", "company", "standin", "superuser")
        at_company = late.resolve("user:late", "company", "standin")
        assert at_company.roles == {"superuser"} and at_company.source == "granted"
        at_project = late.resolve("user:late", P1, "standin")
        assert at_project.roles == {"user"} and at_project.source == "derived"


def test_a_project_grant_is_not_read_at_scope_company(late: Roles) -> None:
    with standins():
        late.grant("late", "company", "standin", "superuser")
        late.grant("late", P1, "standin", "viewer")
        assert late.resolve("user:late", "company", "standin").roles == {"superuser"}
        assert late.resolve("user:late", P1, "standin").roles == {"viewer"}


def test_a_module_without_company_roles_ignores_any_company_row_at_company_scope(
    late: Roles,
) -> None:
    with standins():
        late.raw_grant("late", "company", "plain", "superuser")
        got = late.resolve("user:late", "company", "plain")
        assert got.roles == {"user"} and got.source == "derived"


def test_the_command_word_is_checked_at_the_command_scope(late: Roles) -> None:
    with standins():
        assert command_index() == {"DoThing": ("standin", "controller")}
        late.grant("late", "company", "standin", "superuser")
        with late.world.factory(readonly=True) as uow:
            conn = uow.conn()
            ok = DoThing(actor="user:late", source="t", scope="company")
            require_command_access(conn, ok)
            with pytest.raises(ForbiddenError, match="controller access word for standin"):
                require_command_access(conn, DoThing(actor="user:late", source="t", scope=P1))
            holder = holder_for_actor(conn, "user:late")
            require_command_access(conn, ok, holder=holder)


def test_a_revoked_company_grant_stops_applying(late: Roles) -> None:
    with standins():
        late.grant("late", "company", "standin", "superuser")
        late.revoke("late", "company", "standin", "superuser")
        got = late.resolve("user:late", "company", "standin")
        assert got.roles == {"user"} and got.source == "derived"
