"""Inbound endpoints: create, revise, switch, rotate (FANOUT D4, D12; ADR-0017)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from intworld import ADMIN, SCOPE, World
from tl_core.integration.apps import RegisterIntegrationApp, handle_register_app
from tl_core.integration.errors import (
    DuplicateIntegrationError,
    IntegrationNotFoundError,
    IntegrationStateError,
    InvalidIntegrationError,
)
from tl_core.integration.inbound.service import (
    CreateInboundEndpoint,
    ReviseInboundEndpoint,
    RotateInboundSecret,
    SetInboundEndpointEnabled,
    create_endpoint,
    endpoint_of_row,
    handle_revise_endpoint,
    handle_set_endpoint_enabled,
    rotate_endpoint_secret,
)

MAPPING = '{"command": "PostToFeed", "args": {"body": $.text}}'


def register_app(world: World, name: str = "erp") -> None:
    with world.factory() as uow:
        handle_register_app(
            uow,
            RegisterIntegrationApp(actor=ADMIN, source="test", scope=SCOPE, name=name, label=name),
        )


def make(world: World, **over: Any) -> Any:
    values: dict[str, Any] = {
        "actor": ADMIN,
        "source": "test",
        "scope": SCOPE,
        "app": "erp",
        "name": "orders",
        "mapping": MAPPING,
        "allowed_commands": ["PostToFeed"],
    }
    values.update(over)
    with world.factory() as uow:
        return create_endpoint(uow, CreateInboundEndpoint(**values))


def row(world: World) -> dict[str, Any]:
    return world.rows("SELECT * FROM cur_inbound_endpoint")[0]


def test_an_endpoint_starts_disabled_in_dry_run_with_a_secret_shown_once(world: World) -> None:
    register_app(world)
    made = make(world)
    assert made.secret is not None and made.secret.secret.startswith("whsec_")
    assert "whsec_" not in repr(made)
    found = row(world)
    assert (found["app"], found["name"], found["service_actor"]) == (
        "erp",
        "orders",
        "svc:inbound-erp-orders",
    )
    assert not bool(found["enabled"]) and bool(found["dry_run"])
    assert found["current_secret_id"] == made.secret_id
    model = endpoint_of_row(found)
    assert model.allowed_commands == ["PostToFeed"] and model.version == 1


def test_the_secret_is_in_no_event_and_no_projection(world: World) -> None:
    register_app(world)
    made = make(world)
    assert made.secret is not None
    for table in ("events", "outbox_events", "cur_inbound_endpoint"):
        dump = json.dumps(world.rows(f"SELECT * FROM {table}"), default=str)  # noqa: S608
        assert made.secret.secret not in dump, table


@pytest.mark.parametrize(
    "over",
    [
        {"mapping": "$eval('1')"},
        {"mapping": "a.[["},
        {"allowed_commands": ["DeleteRecord"]},
        {"allowed_commands": []},
        {"name": "Bad Name"},
        {"app": "x" * 60, "name": "y" * 60},
    ],
)
def test_an_endpoint_outside_the_profile_is_not_stored(world: World, over: dict[str, Any]) -> None:
    register_app(world)
    if "app" in over:
        register_app(world, over["app"])
    with pytest.raises(InvalidIntegrationError):
        make(world, **over)
    assert world.rows("SELECT * FROM cur_inbound_endpoint") == []


def test_the_app_must_exist_and_the_path_is_unique(world: World) -> None:
    with pytest.raises(InvalidIntegrationError):
        make(world)
    register_app(world)
    make(world)
    with pytest.raises(DuplicateIntegrationError):
        make(world)


def test_a_revision_changes_the_mapping_and_checks_it(world: World) -> None:
    register_app(world)
    made = make(world)
    new = '{"command": "PostToFeed", "args": {"body": "x" & $.text}}'
    with world.factory() as uow:
        handle_revise_endpoint(
            uow,
            ReviseInboundEndpoint(
                actor=ADMIN, source="test", scope=SCOPE, endpoint_id=made.endpoint_id,
                changes={"mapping": new}, reason="prefix",
            ),
        )  # fmt: skip
    assert endpoint_of_row(row(world)).mapping == new and row(world)["version"] == 2
    for bad in ({"mapping": "$now()"}, {"app": "other"}, {"enabled": True}, {}):
        with world.factory() as uow, pytest.raises(InvalidIntegrationError):
            handle_revise_endpoint(
                uow,
                ReviseInboundEndpoint(
                    actor=ADMIN, source="test", scope=SCOPE, endpoint_id=made.endpoint_id,
                    changes=bad, reason="x",
                ),
            )  # fmt: skip
    with world.factory() as uow, pytest.raises(InvalidIntegrationError):
        handle_revise_endpoint(
            uow,
            ReviseInboundEndpoint(
                actor=ADMIN, source="test", scope=SCOPE, endpoint_id=made.endpoint_id,
                changes={"mapping": new}, reason="same",
            ),
        )  # fmt: skip


def test_switching_on_and_off(world: World) -> None:
    register_app(world)
    made = make(world)

    def switch(on: bool) -> None:
        with world.factory() as uow:
            handle_set_endpoint_enabled(
                uow,
                SetInboundEndpointEnabled(
                    actor=ADMIN,
                    source="test",
                    scope=SCOPE,
                    endpoint_id=made.endpoint_id,
                    enabled=on,
                ),
            )

    switch(True)
    assert bool(row(world)["enabled"])
    with pytest.raises(IntegrationStateError):
        switch(True)
    switch(False)
    assert not bool(row(world)["enabled"])


def test_another_scope_does_not_find_the_endpoint(world: World) -> None:
    register_app(world)
    made = make(world)
    with world.factory() as uow, pytest.raises(IntegrationNotFoundError):
        handle_set_endpoint_enabled(
            uow,
            SetInboundEndpointEnabled(
                actor=ADMIN, source="test", scope="project:OTHER", endpoint_id=made.endpoint_id,
                enabled=True,
            ),
        )  # fmt: skip


def test_a_rotation_keeps_the_old_secret_for_the_overlap(world: World) -> None:
    register_app(world)
    made = make(world)
    with world.factory() as uow:
        rotated = rotate_endpoint_secret(
            uow,
            RotateInboundSecret(
                actor=ADMIN,
                source="test",
                scope=SCOPE,
                endpoint_id=made.endpoint_id,
                overlap_hours=2,
            ),
        )
    assert rotated.secret is not None and made.secret is not None
    assert rotated.secret.secret != made.secret.secret
    assert row(world)["current_secret_id"] == rotated.secret_id
    secrets = world.rows("SELECT secret_id, expires_at FROM int_secret ORDER BY created_at")
    assert len(secrets) == 2 and secrets[0]["expires_at"] is not None
    dump = json.dumps(world.rows("SELECT * FROM events"), default=str)
    assert rotated.secret.secret not in dump and made.secret.secret not in dump
