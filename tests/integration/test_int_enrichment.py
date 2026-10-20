"""Enrichment: the dispatcher, the policies, the layer write and the review commands (D6)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import intfakes as fakes
import pytest
from intworld import ADMIN, PERSON, SCOPE, World
from tl_core.integration.enrichers import layer
from tl_core.integration.enrichers.commands import (
    AcceptEnrichment,
    RejectEnrichment,
    RunEnricher,
    handle_accept_enrichment,
    handle_reject_enrichment,
    handle_run_enricher,
)
from tl_core.integration.enrichers.dispatcher import EnrichmentDispatcher
from tl_core.integration.enrichers.pipeline import load_live_enricher, load_subject, run_enricher
from tl_core.integration.enrichers.registry import use_enrichers
from tl_core.integration.errors import (
    IntegrationNotFoundError,
    IntegrationStateError,
)
from tl_core.services.errors import UnsupportedRecordTypeError
from tl_core.webhooks.rows import as_object, load_json

OTHER = "user:mlee"


@pytest.fixture(autouse=True)
def plugins() -> Iterator[None]:
    fakes.reset()
    with use_enrichers({"fake": fakes.FakeEnricher}):
        yield


def prop(policy: str = "propose", threshold: float = 0.9, name: str = "label") -> dict[str, Any]:
    return {"name": name, "kind": "string", "policy": policy, "threshold": threshold}


def setup(world: World, policy: str = "propose", threshold: float = 0.9, **over: Any) -> str:
    enricher_id = world.register_enricher(properties=[prop(policy, threshold)], **over)
    world.switch_enricher(enricher_id, on=True)
    return enricher_id


def run(world: World) -> Any:
    return world.dispatcher().run_until_idle()


def decide(world: World, command: Any, handler: Any, *, actor: str = PERSON) -> Any:
    with world.factory() as uow:
        return handler(uow, command(actor=actor, source="test", scope=SCOPE))


def accept(world: World, value_id: str, actor: str = PERSON) -> Any:
    with world.factory() as uow:
        return handle_accept_enrichment(
            uow, AcceptEnrichment(actor=actor, source="api", scope=SCOPE, value_id=value_id)
        )


def reject(world: World, value_id: str, actor: str = PERSON) -> Any:
    with world.factory() as uow:
        return handle_reject_enrichment(
            uow,
            RejectEnrichment(
                actor=actor, source="api", scope=SCOPE, value_id=value_id, reason="wrong"
            ),
        )


# --- propose -------------------------------------------------------------------------------------


def test_a_proposed_value_waits_with_its_provenance_and_the_layer_is_untouched(
    world: World,
) -> None:
    setup(world)
    record = world.record("DOC-1", title="Pump datasheet")
    stats = run(world)
    assert (stats.proposed, stats.auto_accepted) == (1, 0)
    [value] = world.values()
    assert (value["acceptance_state"], value["property_path"]) == ("proposed", "enrich.fake.label")
    assert value["target_id"] == record and value["enricher_version"] == "1.0.0"
    assert load_json(value["value_json"]) == "alpha" and value["confidence"] == 0.95
    assert value["model_ref"] is None
    inputs = load_json(value["inputs_json"])
    assert inputs[0]["record"]["key"] == "DOC-1" and inputs[0]["file_sha256"] is None
    assert world.layer(record) == {}
    event = world.events("Enrichment.Proposed")[0]
    created = world.events("Record.Created")[0]
    assert event["actor"] == "svc:enricher-fake" and event["source"] == "enricher:fake@1.0.0"
    assert event["causation_id"] == created["event_id"]
    assert event["correlation_id"] == created["correlation_id"]


def test_a_person_accepts_and_the_layer_is_written_as_that_person(world: World) -> None:
    setup(world)
    record = world.record("DOC-1")
    run(world)
    [value] = world.values()
    made = accept(world, value["value_id"])
    assert made.events[-1].event_type == "Enrichment.Accepted"
    assert world.layer(record) == {"label": "alpha"}
    after = world.values()[0]
    assert (after["acceptance_state"], after["decided_by"]) == ("accepted", PERSON)
    write = [e for e in world.events("Pset.ValuesSet") if e["stream_id"] == record][-1]
    body = as_object(load_json(write["payload"]))
    assert (body["pset"], body["layer"], body["values"]) == (
        "enrich.fake",
        "enrichment",
        {"label": "alpha"},
    )
    assert write["actor"] == PERSON


def test_a_value_is_decided_once(world: World) -> None:
    setup(world)
    world.record("DOC-1")
    run(world)
    value_id = world.values()[0]["value_id"]
    accept(world, value_id)
    for call in (accept, reject):
        with pytest.raises(IntegrationStateError):
            call(world, value_id)
    with pytest.raises(IntegrationNotFoundError):
        with world.factory() as uow:
            handle_accept_enrichment(
                uow,
                AcceptEnrichment(
                    actor=PERSON, source="api", scope="project:OTHER", value_id=value_id
                ),
            )


def test_a_rejected_value_is_not_proposed_again_but_a_different_one_is(world: World) -> None:
    setup(world)
    world.record("DOC-1")
    run(world)
    reject(world, world.values()[0]["value_id"])
    assert world.values()[0]["acceptance_state"] == "rejected"
    world.record("DOC-2")  # the same plan for another record is a new value
    run(world)
    assert len(world.values()) == 2
    # the same enricher on the same record would say the same thing: a person said no to it
    ids = world.rows("SELECT id FROM cur_core_record WHERE key = 'DOC-1'")
    with world.factory() as uow:
        handle_run_enricher(
            uow,
            RunEnricher(
                actor=PERSON, source="api", scope=SCOPE, enricher="fake", record_id=ids[0]["id"]
            ),
        )
    assert len(world.values()) == 2


# --- the policies --------------------------------------------------------------------------------


def test_auto_accepts_at_or_above_the_threshold_as_the_service_actor(world: World) -> None:
    setup(world, "auto", 0.9)
    record = world.record("DOC-1")
    stats = run(world)
    assert (stats.proposed, stats.auto_accepted) == (1, 1)
    assert world.layer(record) == {"label": "alpha"}
    value = world.values()[0]
    assert (value["acceptance_state"], value["decided_by"]) == (
        "auto_accepted",
        "svc:enricher-fake",
    )
    write = [e for e in world.events("Pset.ValuesSet") if e["stream_id"] == record][-1]
    assert write["source"] == "enricher:fake@1.0.0" and write["actor"] == "svc:enricher-fake"


def test_auto_below_the_threshold_waits_like_propose(world: World) -> None:
    setup(world, "auto", 0.99)
    record = world.record("DOC-1")
    run(world)
    assert world.values()[0]["acceptance_state"] == "proposed" and world.layer(record) == {}


def test_a_shadow_value_is_stored_and_can_never_be_accepted(world: World) -> None:
    setup(world, "shadow")
    record = world.record("DOC-1")
    stats = run(world)
    assert (stats.shadow, stats.proposed) == (1, 0)
    value = world.values()[0]
    assert value["acceptance_state"] == "shadow"
    with pytest.raises(IntegrationStateError):
        accept(world, value["value_id"])
    assert world.layer(record) == {}


def test_a_newer_value_replaces_the_open_one(world: World) -> None:
    setup(world)
    record = world.record("DOC-1")
    run(world)
    fakes.FakeEnricher.plan = [("label", "beta", 0.5)]
    with world.factory() as uow:
        handle_run_enricher(
            uow,
            RunEnricher(actor=PERSON, source="api", scope=SCOPE, enricher="fake", record_id=record),
        )
    states = [(load_json(v["value_json"]), v["acceptance_state"]) for v in world.values()]
    assert states == [("alpha", "rejected"), ("beta", "proposed")]
    assert world.values()[0]["decided_by"] == "svc:enricher-fake"


def test_the_same_value_twice_is_one_proposal_even_after_a_replay(world: World) -> None:
    setup(world)
    world.record("DOC-1")
    run(world)
    world.rows("SELECT 1")  # the cursor is operational; put it back as a crash would leave it
    with world.factory() as uow:
        from sqlalchemy import text

        uow.conn().execute(text("UPDATE enrich_cursor SET last_seq = 0"))
    run(world)
    assert len(world.values()) == 1


def test_a_value_the_layer_already_holds_is_not_proposed(world: World) -> None:
    setup(world, "auto", 0.5)
    record = world.record("DOC-1")
    run(world)
    with world.factory() as uow:
        handle_run_enricher(
            uow,
            RunEnricher(actor=PERSON, source="api", scope=SCOPE, enricher="fake", record_id=record),
        )
    assert len(world.values()) == 1


# --- what the plugin may do ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "plan",
    [
        [("undeclared", "x", 0.9)],
        [("label", 5, 0.9)],
        [("label", True, 0.9)],
        [("label", ["a"], 0.9)],
    ],
)
def test_a_value_the_registration_does_not_declare_is_dropped(
    world: World, plan: list[tuple[str, Any, float]]
) -> None:
    setup(world)
    world.record("DOC-1")
    fakes.FakeEnricher.plan = plan
    stats = run(world)
    assert stats.skipped == 1 and world.values() == []


def test_a_plugin_that_fails_or_raises_stores_nothing(world: World) -> None:
    setup(world)
    world.record("DOC-1")
    fakes.FakeEnricher.status = "failed"
    assert run(world).failed == 1

    class Raises(fakes.FakeEnricher):
        def enrich(self, subject: Any) -> Any:
            raise RuntimeError("boom /secret/path")

    world.record("DOC-2")
    with use_enrichers({"fake": Raises}):
        assert run(world).failed == 1
    assert world.values() == []


def test_a_link_is_a_suggestion_with_the_enricher_source(world: World) -> None:
    setup(world)
    world.record("DOC-9")
    fakes.FakeEnricher.plan = []
    fakes.FakeEnricher.links = [("DOC-9", 0.8), ("NO-SUCH", 0.8)]
    world.record("DOC-1")
    stats = run(world)
    assert stats.links >= 1
    [suggested] = [e for e in world.events("Link.Suggested") if "DOC-9" not in e["stream_id"]][:1]
    body = as_object(load_json(suggested["payload"]))
    assert body["source"] == "enricher" and suggested["actor"] == "svc:enricher-fake"


# --- when it runs --------------------------------------------------------------------------------


def test_nothing_runs_for_a_disabled_enricher_or_before_it_was_switched_on(world: World) -> None:
    enricher_id = world.register_enricher()
    world.record("DOC-1")
    assert run(world).proposed == 0
    world.switch_enricher(enricher_id, on=True)
    world.record("DOC-2")  # only this one is after the switch
    run(world)
    assert [load_json(v["inputs_json"])[0]["record"]["key"] for v in world.values()] == ["DOC-2"]


def test_the_scope_of_the_enricher_limits_the_events(world: World) -> None:
    setup(world)
    world.record("DOC-1", scope="project:OTHER")
    assert run(world).proposed == 0


def test_an_enricher_does_not_run_on_its_own_work(world: World) -> None:
    setup(world, "auto", 0.5, when={"event_types": ["Record.Created", "Pset.ValuesSet"]})
    world.record("DOC-1")
    stats = run(world)
    assert stats.proposed == 1  # the layer write (source enricher:) started nothing


def test_the_kill_switch_passes_events_over_and_they_are_not_replayed(world: World) -> None:
    setup(world)
    world.record("DOC-1")
    world.setting("integration.kill_switch", True)
    stats = run(world)
    assert stats.killed >= 1 and world.values() == []
    world.setting("integration.kill_switch", False)
    run(world)
    assert world.values() == []
    world.record("DOC-2")
    run(world)
    assert len(world.values()) == 1


def test_a_disabled_app_stops_its_enrichers(world: World) -> None:
    from tl_core.integration.apps import (
        RegisterIntegrationApp,
        SetIntegrationAppEnabled,
        handle_register_app,
        handle_set_app_enabled,
    )

    with world.factory() as uow:
        made = handle_register_app(
            uow,
            RegisterIntegrationApp(
                actor=ADMIN, source="test", scope=SCOPE, name="docs", label="Docs"
            ),
        )
    setup(world, integration_app="docs")
    with world.factory() as uow:
        handle_set_app_enabled(
            uow,
            SetIntegrationAppEnabled(
                actor=ADMIN, source="test", scope=SCOPE, app_id=made.stream_id, enabled=False
            ),
        )
    world.record("DOC-1")
    assert run(world).proposed == 0


# --- RunEnricher ---------------------------------------------------------------------------------


def run_one(world: World, record: str, *, scope: str = SCOPE, name: str = "fake") -> Any:
    with world.factory() as uow:
        return handle_run_enricher(
            uow,
            RunEnricher(actor=PERSON, source="api", scope=scope, enricher=name, record_id=record),
        )


def test_run_enricher_runs_on_one_record(world: World) -> None:
    setup(world)
    record = world.record("DOC-1")
    run(world)
    world.rows("SELECT 1")
    fakes.FakeEnricher.plan = [("label", "gamma", 0.7)]
    made = run_one(world, record)
    assert any(e.event_type == "Enrichment.Proposed" for e in made.events)
    assert world.events("Enrichment.Proposed")[-1]["actor"] == "svc:enricher-fake"


def test_run_enricher_refuses_what_is_not_switched_on_or_not_there(world: World) -> None:
    enricher_id = world.register_enricher()
    record = world.record("DOC-1")
    with pytest.raises(IntegrationNotFoundError):
        run_one(world, record)  # registered but off
    world.switch_enricher(enricher_id, on=True)
    with pytest.raises(IntegrationNotFoundError):
        run_one(world, "01J0000000000000000000000X")
    with pytest.raises(IntegrationNotFoundError):
        run_one(world, record, scope="project:OTHER")
    with pytest.raises(IntegrationNotFoundError):
        run_one(world, record, name="ghost")
    world.setting("integration.kill_switch", True)
    with pytest.raises(IntegrationStateError):
        run_one(world, record)


# --- the target type decides ---------------------------------------------------------------------


def test_a_type_that_does_not_allow_set_pset_values_stays_closed(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup(world)
    record = world.record("DOC-1")
    run(world)

    def closed(*_a: Any, **_k: Any) -> None:
        raise UnsupportedRecordTypeError("closed")

    monkeypatch.setattr(layer, "require_generic", closed)
    value_id = world.values()[0]["value_id"]
    with pytest.raises(UnsupportedRecordTypeError):
        accept(world, value_id)
    assert world.values()[0]["acceptance_state"] == "proposed" and world.layer(record) == {}


def test_the_layer_has_no_other_writer(world: World) -> None:
    """``SetPsetValues`` still refuses the enrichment root (Phase 0)."""
    from tl_core.services.errors import LayerError
    from tl_core.services.psets import SetPsetValues, handle_set_pset_values

    record = world.record("DOC-1")
    with world.factory() as uow, pytest.raises(LayerError):
        handle_set_pset_values(
            uow,
            SetPsetValues(
                actor=PERSON,
                source="test",
                scope=SCOPE,
                stream_id=record,
                expected_version=1,
                pset="enrich.fake",
                layer="standard",
                values={"label": "x"},
            ),  # fmt: skip
        )


# --- a switch that goes off mid-batch stops the enricher at the next event (second review) ----


class SwitchingDispatcher(EnrichmentDispatcher):
    """Runs the first event, then calls ``after`` (a switch going off between two events)."""

    def __init__(self, world: World, after: Any) -> None:
        super().__init__(world.factory, clock=world.clock)
        self._after, self._done = after, False

    def _run(self, enricher: Any, row: Any, counts: Any) -> Any:
        stats = super()._run(enricher, row, counts)
        if not self._done:
            self._done = True
            self._after()
        return stats


def test_switching_an_enricher_off_mid_batch_stops_it_at_the_next_event(world: World) -> None:
    enricher_id = setup(world)
    world.record("DOC-1")
    world.record("DOC-2")
    SwitchingDispatcher(
        world, lambda: world.switch_enricher(enricher_id, on=False)
    ).run_until_idle()
    assert len(world.values()) == 1


def test_switching_its_app_off_mid_batch_stops_it_too(world: World) -> None:
    world.app("erp")
    setup(world, integration_app="erp")
    world.record("DOC-1")
    world.record("DOC-2")
    SwitchingDispatcher(world, lambda: world.switch_app("erp", on=False)).run_until_idle()
    assert len(world.values()) == 1


def test_an_enricher_that_lost_its_access_writes_nothing_even_when_called_directly(
    world: World,
) -> None:
    enricher_id = setup(world, policy="auto", threshold=0.5)
    record = world.record("DOC-1")
    with world.factory(readonly=True) as uow:
        stale = load_live_enricher(uow.conn(), "fake")
    assert stale is not None
    world.switch_enricher(enricher_id, on=False)
    with world.factory() as uow:
        stats, events = run_enricher(
            uow, stale, fakes.FakeEnricher(), load_subject(uow.conn(), record),  # type: ignore[arg-type]
            now=world.clock(), correlation_id=None, causation_id=None,
        )  # fmt: skip
    assert events == [] and stats.skipped == 1 and world.values() == []
