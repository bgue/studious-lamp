"""A command that must name a record version runs, from automation, on the record as it is.

Found by the demo: a mapped ``SetPsetValues`` was refused (``expected_version: Field required``),
because a payload cannot know a version. The version is read when the command runs; a mapping or
a rule step that names one is refused.
"""

from __future__ import annotations

from intworld import World
from tl_api.commands import command_runner
from tl_core.integration.automation import ServerFields, plan_command
from tl_core.integration.contract import AUTOMATION_COMMANDS

FIELDS = ServerFields(
    actor="svc:inbound-erp.orders",
    source="inbound:erp/orders",
    scope="project:P123",
    correlation_id="C" * 26,
    causation_id=None,
)
TWICE = (
    '[{"command": "SetPsetValues", "args": {"stream_id": {"$key": "V-1"}, "pset": "valve_data", '
    '"layer": "standard", "values": {"tag_no": "FV-1001"}}}, '
    '{"command": "SetPsetValues", "args": {"stream_id": {"$key": "V-1"}, "pset": "valve_data", '
    '"layer": "standard", "values": {"manufacturer": "Acme"}}}]'
)


def test_a_mapping_that_names_a_version_is_refused() -> None:
    built = plan_command(
        command_runner(),
        "SetPsetValues",
        {
            "stream_id": "r1",
            "expected_version": 1,
            "pset": "valve_data",
            "layer": "standard",
            "values": {"a": 1},
        },
        FIELDS,
        declared="user",
        allowed=AUTOMATION_COMMANDS,
        link_source="mapping",
    )
    assert built.command is None and built.planned.problem is not None
    assert built.planned.problem.code == "expected_version"


def test_the_preview_of_a_versioned_command_shows_no_version() -> None:
    built = plan_command(
        command_runner(),
        "SetPsetValues",
        {
            "stream_id": "r1",
            "pset": "valve_data",
            "layer": "standard",
            "values": {"tag_no": "FV-1001"},
        },
        FIELDS,
        declared="user",
        allowed=AUTOMATION_COMMANDS,
        link_source="mapping",
    )
    assert built.command is not None and built.planned.permitted
    assert "expected_version" not in built.planned.command


def test_two_pset_writes_to_one_record_in_one_delivery_both_apply(world: World) -> None:
    world.record("V-1")
    made = world.endpoint(mapping=TWICE, allowed_commands=["SetPsetValues"])
    world.deliver(made.endpoint_id, {})
    world.inbound_runner().run_until_idle()
    [delivery] = world.deliveries()
    assert (delivery["state"], delivery["command_count"]) == ("applied", 2), delivery
    [row] = world.rows("SELECT psets_json FROM cur_core_record WHERE key = 'V-1'")
    assert "FV-1001" in row["psets_json"] and "Acme" in row["psets_json"]


# --- a proposal a rule made is accepted on the record as it is then (re-check finding 3) --------


def propose_and_accept(world: World, step: dict[str, object]) -> str:
    from intworld import PERSON
    from tl_core.services import proposals

    rule_id = world.create_rule(then=[step])
    world.switch_rule(rule_id, on=True)
    world.post("go #safety")
    world.worker().run_until_idle()
    with world.factory(readonly=True) as uow:
        [pending] = proposals.list_proposals(uow.conn(), "project:P123", status="pending")
    # the record changes between the rule's proposal and the person's decision
    world.retitle_record(str(step["args"]["stream_id"]), "Retitled meanwhile")  # type: ignore[index]
    done = proposals.accept_or_fail(world.factory, proposal_id=pending.proposal_id, by=PERSON)
    assert done.status == "accepted", done
    return pending.command_type


def test_a_propose_mode_set_pset_values_is_accepted(world: World) -> None:
    record = world.record("V-1")
    assert propose_and_accept(
        world,
        {
            "command": "SetPsetValues",
            "args": {
                "stream_id": record, "pset": "valve_data", "layer": "standard",
                "values": {"tag_no": "FV-1001"},
            },
        },
    ) == "SetPsetValues"  # fmt: skip
    assert "FV-1001" in world.rows("SELECT psets_json FROM cur_core_record")[0]["psets_json"]


def test_a_propose_mode_update_record_is_accepted(world: World) -> None:
    record = world.record("V-1")
    propose_and_accept(
        world,
        {"command": "UpdateRecord", "args": {"stream_id": record, "changes": {"title": "New"}}},
    )
    assert world.rows("SELECT title FROM cur_core_record")[0]["title"] == "New"


def test_a_propose_mode_transition_is_accepted(world: World) -> None:
    record = world.record("V-1")
    before = world.rows("SELECT status FROM cur_core_record")[0]["status"]
    propose_and_accept(
        world,
        {"command": "TransitionWorkflow", "args": {"stream_id": record, "transition": "submit"}},
    )
    assert world.rows("SELECT status FROM cur_core_record")[0]["status"] != before
