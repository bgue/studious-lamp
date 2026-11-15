"""A scaffold takes the class of the record its request serves (``for_record_id``): hidden for the
lowest viewer as a record that never existed. The register, its inspections and the refusal text
answer alike for a scaffold that is hidden and for an id that is not there."""

from __future__ import annotations

import pytest
from scaffold_world import World
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.services.errors import RecordNotFoundError
from tl_mod_scaffold.names import INSPECTION, SCAFFOLD

MISSING = "01J9Z6Q4W3X2Y1V0T9S8R7Q6PZ"
CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")


def hidden_scaffold(world: World) -> tuple[str, str, str]:
    """A scaffold whose request serves a restricted record, with one inspection:
    ``(scaffold id, inspection id, the subject id)``. The request is pointed at the subject by a
    projection write (an IWP is not confidential today and the rule is generic in the subject)."""
    request = world.request()
    subject = world.hidden_record()
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_requisitions_scaffold_request SET for_record_id = :s WHERE id = :i"),
            {"s": subject, "i": request},
        )
    sid = world.register(request, who="dora")
    world.advance_as(sid, "Erecting", "dora")
    world.call("dora", "TagScaffoldGreen", scaffold=sid)
    inspection = str(
        world.scalar(
            "SELECT id FROM cur_scaffold_scaffold_inspection WHERE scaffold_id = :i", i=sid
        )
    )
    return sid, inspection, subject


def count(world: World, record_type: str, viewer: cf.Viewer) -> int:
    visible, extra = cf.not_hidden_each("r.id", viewer)
    return int(
        world.scalar(
            f"SELECT count(*) FROM cur_core_record r WHERE r.type = :t AND {visible}",
            t=record_type,
            **extra,
        )
    )


def test_the_subject_is_copied_to_the_scaffold(world: World) -> None:
    sid, _, subject = hidden_scaffold(world)
    assert world.row(sid)["for_record_id"] == subject


def test_the_scaffold_and_its_inspection_are_hidden_for_the_lowest_viewer(world: World) -> None:
    sid, inspection, _ = hidden_scaffold(world)
    with open_uow(world.db, readonly=True) as uow:
        conn = uow.conn()
        for record in (sid, inspection):
            assert cf.is_hidden(conn, record, cf.LOWEST)
            assert not cf.is_hidden(conn, record, CLEARED)
            with pytest.raises(RecordNotFoundError):
                cf.require_visible(conn, record, cf.LOWEST)
    assert (count(world, SCAFFOLD, cf.LOWEST), count(world, INSPECTION, cf.LOWEST)) == (0, 0)
    assert (count(world, SCAFFOLD, CLEARED), count(world, INSPECTION, CLEARED)) == (1, 1)


def test_a_scaffold_of_an_open_record_is_visible_to_all(world: World) -> None:
    iwp = world.iwp("IWP-1")
    sid = world.register(world.request(for_record_id=iwp))
    assert count(world, SCAFFOLD, cf.LOWEST) == 1
    with open_uow(world.db, readonly=True) as uow:
        assert not cf.is_hidden(uow.conn(), sid, cf.LOWEST)


@pytest.mark.parametrize(
    ("name", "extra"),
    [
        ("DesignScaffold", {}),
        ("TagScaffoldGreen", {}),
        ("ErectScaffold", {}),
        ("InspectScaffold", {"result": "fail"}),
        ("ReleaseScaffold", {}),
        ("ModifyScaffold", {"reason": "x"}),
        ("DismantleScaffold", {"reason": "x"}),
        ("RemoveScaffold", {}),
    ],
)
def test_every_command_on_a_hidden_scaffold_answers_as_for_one_that_is_not_there(
    world: World, name: str, extra: dict
) -> None:  # type: ignore[type-arg]
    sid, _, _ = hidden_scaffold(world)
    with pytest.raises(RecordNotFoundError) as absent:
        world.call("uma", name, scaffold=MISSING, **extra)
    with pytest.raises(RecordNotFoundError) as hidden:
        world.call("uma", name, scaffold=sid, **extra)
    assert str(hidden.value) == str(absent.value)
    assert sid not in str(hidden.value)


def test_the_dismantle_refusal_of_a_hidden_scaffold_leaks_nothing(world: World) -> None:
    sid, _, _ = hidden_scaffold(world)
    world.require(world.iwp("IWP-SECRET", "Issued"), sid)
    with pytest.raises(RecordNotFoundError) as caught:
        world.call("uma", "DismantleScaffold", scaffold=sid, reason="x")
    assert "IWP-SECRET" not in str(caught.value) and "Issued" not in str(caught.value)


def test_a_cleared_person_runs_the_commands_on_it(world: World) -> None:
    sid, _, _ = hidden_scaffold(world)
    world.call("dora", "ModifyScaffold", scaffold=sid, reason="Extend")
    assert world.state(sid) == "Modify"


def test_a_request_of_a_hidden_record_cannot_be_registered_by_the_lowest_viewer(
    world: World,
) -> None:
    request = world.request()
    subject = world.hidden_record()
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_requisitions_scaffold_request SET for_record_id = :s WHERE id = :i"),
            {"s": subject, "i": request},
        )
    with pytest.raises(RecordNotFoundError):
        world.call("uma", "RegisterScaffold", request_id=request, title="A")
    assert world.scalar("SELECT count(*) FROM cur_scaffold_scaffold") == 0
