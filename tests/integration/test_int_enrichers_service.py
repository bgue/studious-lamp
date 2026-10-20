"""Registering enrichers (FANOUT D6, D12) and the access their service actor holds."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import intfakes as fakes
import pytest
from intworld import ADMIN, SCOPE, World
from pydantic import ValidationError
from tl_core.integration.actor_access import held_access
from tl_core.integration.enrichers.registry import use_enrichers
from tl_core.integration.enrichers.service import (
    ReviseEnricher,
    handle_revise_enricher,
)
from tl_core.integration.errors import (
    DuplicateIntegrationError,
    IntegrationNotFoundError,
    IntegrationStateError,
    InvalidIntegrationError,
)
from tl_core.webhooks.rows import as_list, as_object, load_json


@pytest.fixture(autouse=True)
def plugins() -> Iterator[None]:
    fakes.reset()
    with use_enrichers({"fake": fakes.FakeEnricher, "model_based": fakes.ModelEnricher}):
        yield


def row(world: World) -> dict[str, Any]:
    return world.rows("SELECT * FROM cur_enricher")[0]


def revise(world: World, enricher_id: str, changes: dict[str, Any], reason: str = "test") -> None:
    with world.factory() as uow:
        handle_revise_enricher(
            uow,
            ReviseEnricher(
                actor=ADMIN, source="test", scope=SCOPE, enricher_id=enricher_id,
                changes=changes, reason=reason,
            ),
        )  # fmt: skip


def test_an_enricher_starts_disabled_under_its_own_service_actor(world: World) -> None:
    world.register_enricher()
    found = row(world)
    assert (found["name"], found["version"], found["code_version"]) == ("fake", 1, "1.0.0")
    assert found["service_actor"] == "svc:enricher-fake" and found["model_ref"] is None
    assert not bool(found["enabled"]) and found["access"] == "user"
    props = as_list(load_json(found["properties_json"]))
    assert as_object(props[0]) == {
        "name": "label", "kind": "string", "policy": "propose", "threshold": 0.9
    }  # fmt: skip


@pytest.mark.parametrize(
    "over",
    [
        {"name": "not_installed"},
        {"name": "model_based"},
        {"name": "Bad Name"},
        {"when": {}},
        {"when": {"event_types": []}},
        {"properties": []},
        {"properties": [{"name": "a", "kind": "string"}, {"name": "a", "kind": "string"}]},
        {"properties": [{"name": "Bad", "kind": "string"}]},
        {"properties": [{"name": "a", "kind": "object"}]},
        {"properties": [{"name": "a", "kind": "string", "policy": "yolo"}]},
        {"properties": [{"name": "a", "kind": "string", "threshold": 1.5}]},
        {"properties": [{"name": "a", "kind": "string", "extra": 1}]},
        {"integration_app": "no_such_app"},
    ],
)
def test_a_registration_outside_the_rules_is_not_stored(world: World, over: dict[str, Any]) -> None:
    with pytest.raises(InvalidIntegrationError):
        world.register_enricher(**over)
    assert world.rows("SELECT * FROM cur_enricher") == []


def test_a_name_is_registered_once(world: World) -> None:
    world.register_enricher()
    with pytest.raises(DuplicateIntegrationError):
        world.register_enricher(scope="project:OTHER")


def test_switching_on_and_off_and_the_moment_it_was_switched_on(world: World) -> None:
    enricher_id = world.register_enricher()
    world.switch_enricher(enricher_id, on=True)
    first = row(world)
    assert bool(first["enabled"]) and int(first["enabled_from_seq"]) > 0
    with pytest.raises(IntegrationStateError):
        world.switch_enricher(enricher_id, on=True)
    world.switch_enricher(enricher_id, on=False)
    assert not bool(row(world)["enabled"])
    with pytest.raises(IntegrationNotFoundError):
        world.switch_enricher(enricher_id, on=True, scope="project:OTHER")


def test_a_plugin_that_is_gone_or_names_a_model_cannot_be_switched_on(world: World) -> None:
    enricher_id = world.register_enricher()
    with use_enrichers({}), pytest.raises(InvalidIntegrationError):
        world.switch_enricher(enricher_id, on=True)
    with use_enrichers({"fake": fakes.ModelEnricher}), pytest.raises(InvalidIntegrationError):
        world.switch_enricher(enricher_id, on=True)


def test_a_revision_carries_the_whole_registration_and_refreshes_the_code_version(
    world: World,
) -> None:
    enricher_id = world.register_enricher()

    class Newer(fakes.FakeEnricher):
        version = "1.1.0"

    with use_enrichers({"fake": Newer}):
        auto = {"name": "label", "kind": "string", "policy": "auto", "threshold": 0.8}
        revise(world, enricher_id, {"properties": [auto]}, "auto-accept above 0.8")
    found = row(world)
    assert (found["version"], found["code_version"]) == (2, "1.1.0")
    assert as_object(as_list(load_json(found["properties_json"]))[0])["policy"] == "auto"
    assert not bool(found["enabled"])  # a revision does not switch it
    event = world.events("Enricher.Revised")[0]
    assert as_object(load_json(event["payload"]))["enricher"]["code_version"] == "1.1.0"


@pytest.mark.parametrize(
    "changes",
    [{}, {"name": "other"}, {"enabled": True}, {"service_actor": "svc:enricher-x"},
     {"access": "admin"}, {"when": {}}, {"properties": []}, {"owner": " "}],
)  # fmt: skip
def test_a_revision_outside_the_rules_is_refused(world: World, changes: dict[str, Any]) -> None:
    enricher_id = world.register_enricher()
    with pytest.raises(InvalidIntegrationError):
        revise(world, enricher_id, changes)
    assert row(world)["version"] == 1


def test_a_revision_that_changes_nothing_is_refused(world: World) -> None:
    enricher_id = world.register_enricher()
    with pytest.raises(InvalidIntegrationError):
        revise(world, enricher_id, {"access": "user"})


def test_the_service_actor_holds_the_declared_access_and_no_more(world: World) -> None:
    """The branch of ``held_access`` for ``svc:enricher-*`` (coordinator decision, D14)."""
    world.switch_enricher(world.register_enricher(name="fake", access="user"), on=True)
    with use_enrichers({"fake": fakes.FakeEnricher, "second": _second()}):
        second = world.register_enricher(name="second", access="controller")
        world.switch_enricher(second, on=True)
    with world.factory(readonly=True) as uow:
        conn = uow.conn()
        assert held_access(conn, "svc:enricher-fake") == "user"
        assert held_access(conn, "svc:enricher-second") == "controller"
        assert held_access(conn, "svc:enricher-ghost") is None
        assert held_access(conn, "svc:enricher-fake-x") is None
    with pytest.raises(ValidationError):  # a service actor is never an admin
        world.register_enricher(name="third", access="admin")


def test_a_revision_of_access_changes_what_the_actor_holds(world: World) -> None:
    enricher_id = world.register_enricher()
    world.switch_enricher(enricher_id, on=True)
    revise(world, enricher_id, {"access": "controller"})
    with world.factory(readonly=True) as uow:
        assert held_access(uow.conn(), "svc:enricher-fake") == "controller"


def test_the_events_hold_no_secret_and_are_the_admins(world: World) -> None:
    world.register_enricher()
    dump = json.dumps(world.rows("SELECT * FROM events"), default=str)
    assert "whsec_" not in dump
    assert world.events("Enricher.Registered")[0]["actor"] == ADMIN


def _second() -> Any:
    class Second(fakes.FakeEnricher):
        name = "second"

    return Second
