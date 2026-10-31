"""``cur_account_module_role`` reads the same on SQLite and on Postgres (RM-S1, P2-W0).

Runs once per adapter named by ``--adapters`` (the ``world`` fixture asks for ``db``): the rows are
compared with one literal, types included (text columns are text, ``seq`` is an integer, times are
``...Z`` text), so a dialect difference in the generated table or the projector shows here.
"""

from __future__ import annotations

from typing import Any

import pytest
from authworld import World
from sqlalchemy import text
from tl_core.auth.module_grants import (
    GrantModuleRole,
    RevokeModuleRole,
    grant_module_role,
    revoke_module_role,
)

pytestmark = pytest.mark.parity

P1, P2 = "project:P1", "project:P2"


def run(
    world: World, cls: type[Any], fn: Any, account_id: str, project: str, module: str, role: str
) -> None:
    command = cls(
        actor="user:root", source="test", scope="company", account_id=account_id,
        project=project, module=module, role=role, reason="parity",
    )  # fmt: skip
    with world.factory() as uow:
        fn(uow, command)


def typed(rows: list[tuple[Any, ...]]) -> list[list[tuple[str, Any]]]:
    return [[(type(v).__name__, v) for v in row] for row in rows]


def test_the_projection_rows_have_the_same_types_and_values_on_every_adapter(world: World) -> None:
    world.admin("root")
    amy = world.create("amy").account_id
    bot = world.create("bot", kind="agent").account_id
    grant = (GrantModuleRole, grant_module_role)
    revoke = (RevokeModuleRole, revoke_module_role)
    run(world, *grant, amy, P1, "documents", "superuser")
    run(world, *grant, amy, P1, "*", "viewer")
    run(world, *grant, amy, P2, "cost", "user")
    run(world, *grant, bot, P1, "documents", "user")
    run(world, *revoke, amy, P2, "cost", "user")

    rows = world.rows(
        "SELECT project, module, role, granted_by, "
        "granted_at LIKE '____-__-__T%Z', seq > 0 FROM cur_account_module_role "
        "WHERE account_id = :a ORDER BY project, module, role",
        a=amy,
    )
    assert typed(rows) == typed(
        [
            (P1, "*", "viewer", "user:root", rows[0][4], rows[0][5]),
            (P1, "documents", "superuser", "user:root", rows[1][4], rows[1][5]),
        ]
    )
    assert [bool(r[4]) and bool(r[5]) for r in rows] == [True, True]
    assert world.rows("SELECT COUNT(*) FROM cur_account_module_role") == [(3,)]
    kinds = world.rows(
        "SELECT event_type, scope, stream_type FROM events WHERE event_type LIKE "
        "'Account.ModuleRole%' ORDER BY seq"
    )
    assert [(k[0], k[1], k[2]) for k in kinds] == [
        ("Account.ModuleRoleGranted", "company", "core.Account"),
        ("Account.ModuleRoleGranted", "company", "core.Account"),
        ("Account.ModuleRoleGranted", "company", "core.Account"),
        ("Account.ModuleRoleGranted", "company", "core.Account"),
        ("Account.ModuleRoleRevoked", "company", "core.Account"),
    ]


def test_a_grant_is_unique_per_account_project_module_and_role(world: World) -> None:
    world.admin("root")
    amy = world.create("amy").account_id
    grant = (GrantModuleRole, grant_module_role)
    run(world, *grant, amy, P1, "documents", "user")
    run(world, *grant, amy, P1, "documents", "user")  # changed: false, no second row
    with world.factory(readonly=True) as uow:
        count = (
            uow.conn().execute(text("SELECT COUNT(*) FROM cur_account_module_role")).scalar_one()
        )
    assert count == 1
