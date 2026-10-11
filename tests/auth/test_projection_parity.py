"""The account projections read the same on SQLite and on Postgres (P1-I0-T12).

The other auth tests run on whichever adapter `--adapters` names. This one runs one script on
both in a single test and compares the projection rows column by column (types included: booleans
are 0 and 1, JSON is canonical text, times are `...Z` text), so a dialect difference in the
generated tables or the projector shows here and not in a screen.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from authworld import MovingClock, World
from sqlalchemy import text
from tl_adapters.db import create_schema, make_uow_factory
from tl_adapters.postgres import admin
from tl_core.auth import accounts

pytestmark = pytest.mark.requires_postgres

COLUMNS_ACCOUNT = "username, display_name, kind, roles_json, is_admin, status, version"
COLUMNS_TOKEN = "label, revoked, issued_by"


def script(world: World) -> None:
    root = world.admin("root")
    amy = world.create("amy")
    bot = world.create("bot", kind="agent")
    world.create("kim", roles=("user", "admin"))
    with world.factory() as uow:
        accounts.set_roles(
            uow, account_id=amy.account_id, roles=["admin", "user"], by="user:root", reason="lead"
        )
    with world.factory() as uow:
        accounts.disable(uow, account_id=amy.account_id, by="user:root", reason="away")
    with world.factory() as uow:
        accounts.enable(uow, account_id=amy.account_id, by="user:root", reason=None)
    with world.factory() as uow:
        view, _ = accounts.issue_agent_token(
            uow, account_id=bot.account_id, label="a", expires_at=None, by="user:root"
        )
        accounts.issue_agent_token(
            uow, account_id=bot.account_id, label="b", expires_at=None, by="user:root"
        )
    with world.factory() as uow:
        accounts.revoke_agent_token(uow, token_id=view.token_id, by="user:root", reason="x")
    assert root.username == "root"


def snapshot(world: World) -> dict[str, Any]:
    def typed(rows: list[tuple[Any, ...]]) -> list[list[Any]]:
        return [[(type(v).__name__, v) for v in row] for row in rows]

    with world.factory(readonly=True) as uow:
        conn = uow.conn()
        return {
            "accounts": typed(
                [
                    tuple(r)
                    for r in conn.execute(
                        text(f"SELECT {COLUMNS_ACCOUNT} FROM cur_account ORDER BY username")
                    ).all()
                ]
            ),
            "tokens": typed(
                [
                    tuple(r)
                    for r in conn.execute(
                        text(f"SELECT {COLUMNS_TOKEN} FROM cur_agent_token ORDER BY label")
                    ).all()
                ]
            ),
            "events": typed(
                [
                    tuple(r)
                    for r in conn.execute(
                        text(
                            "SELECT event_type, actor, scope, stream_id IS NOT NULL "
                            "FROM events ORDER BY seq"
                        )
                    ).all()
                ]
            ),
            "credentials": typed(
                [tuple(r) for r in conn.execute(text("SELECT COUNT(*) FROM auth_credential")).all()]
            ),
            "secrets": typed(
                [
                    tuple(r)
                    for r in conn.execute(text("SELECT COUNT(*) FROM auth_token_secret")).all()
                ]
            ),
        }


def test_the_same_script_gives_the_same_projection_rows_on_both_adapters(
    tmp_path: Path, pg_base_url: str | None
) -> None:
    if pg_base_url is None:
        import os

        if os.environ.get("TL_REQUIRE_POSTGRES") == "1":
            pytest.fail("Postgres is not reachable at TL_PG_URL")
        pytest.skip("Postgres is not reachable at TL_PG_URL")
    schema = "tl_t_" + uuid.uuid4().hex[:16]
    admin.create_schema_namespace(pg_base_url, schema)
    try:
        targets = [tmp_path / "tl.db", admin.schema_url(pg_base_url, schema)]
        seen: list[dict[str, Any]] = []
        for target in targets:
            create_schema(target)
            factory = make_uow_factory(target)
            try:
                world = World(target, factory, MovingClock())
                script(world)
                seen.append(snapshot(world))
            finally:
                factory.dispose()
    finally:
        admin.drop_schema_namespace(pg_base_url, schema)
    sqlite, postgres = seen
    for table in sqlite:
        assert sqlite[table] == postgres[table], table
    assert len(sqlite["accounts"]) == 4 and len(sqlite["tokens"]) == 2
    assert [row[0][1] for row in sqlite["events"]].count("AgentToken.Revoked") == 1
