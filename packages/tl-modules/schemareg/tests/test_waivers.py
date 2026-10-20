"""Waivers: request, approve, revoke, and what they do to the effective schema (T01)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core.util import utcnow
from tl_mod_schemareg.errors import (
    InvalidWaiverError,
    SelfReviewError,
    WaiverStateError,
)
from tl_mod_schemareg.handlers.waivers import ApproveWaiver, RequestWaiver, RevokeWaiver
from tl_mod_schemareg.testing import ADMIN, AUTHOR, REVIEWER, RegistryWorld
from tl_schema.conformance import evaluate

PATH = "psets.valve_data.size_in"


def soon(days: int = 30) -> str:
    return (utcnow().date() + timedelta(days=days)).isoformat()


def request(world: RegistryWorld, project: str = "P999", path: str = PATH, days: int = 30):  # type: ignore[no-untyped-def]
    return world.do(
        RequestWaiver,
        AUTHOR,
        project=project,
        path=path,
        reason="Legacy valves have no size on record.",
        expires=soon(days),
    )


def missing_size(world: RegistryWorld, project: str = "P999") -> str:
    """The conformance status of a valve in state Installed that has no size."""
    schema = world.provider.effective(f"project:{project}")
    report = evaluate(
        schema,
        "core.Record",
        {"valve_data": {"manufacturer": "Acme"}},
        state="Installed",
        on=utcnow().date(),
    )
    return report.status


def test_a_request_is_a_record_in_the_state_requested(world: RegistryWorld) -> None:
    result = request(world)
    assert result.key == f"P999/{PATH}@1"
    row = world.waiver(result.stream_id)
    assert (row.state, row.requested_by, row.project, row.number) == (
        "Requested",
        AUTHOR,
        "P999",
        1,
    )
    assert row.approver is None and row.scope == "project:P999"


@pytest.mark.parametrize(
    "fields, message",
    [
        ({"path": "valve_data.size_in"}, "path must look like"),
        ({"path": "psets.valve_data.nope"}, "names no property"),
        ({"project": "bad project"}, "not written in a form"),
        ({"expires": "2020-01-01"}, "in the past"),
        ({"expires": "2999-01-01"}, "at most"),
        ({"expires": "2026-13-01"}, "real date"),
        ({"expires": "٢٠٢٦-٠١-٠١"}, "YYYY-MM-DD"),
    ],
)
def test_a_request_that_cannot_be_honoured_is_refused(
    world: RegistryWorld, fields: dict[str, str], message: str
) -> None:
    body = {"project": "P999", "path": PATH, "reason": "Because.", "expires": soon()} | fields
    with pytest.raises(InvalidWaiverError, match=message):
        world.do(RequestWaiver, AUTHOR, **body)


def test_a_project_whose_package_declares_strict_cannot_have_waivers(world: RegistryWorld) -> None:
    with pytest.raises(InvalidWaiverError, match="declares the conformance mode strict"):
        request(world, project="P123")


def test_an_open_request_blocks_a_second_one_for_the_same_path(world: RegistryWorld) -> None:
    request(world)
    with pytest.raises(InvalidWaiverError, match="already waived or asked for"):
        request(world)
    request(world, path="psets.valve_data.tag_no")


def test_the_requester_cannot_approve(world: RegistryWorld) -> None:
    waiver = request(world)
    with pytest.raises(SelfReviewError):
        world.do(ApproveWaiver, AUTHOR, waiver_id=waiver.stream_id)
    assert world.waiver(waiver.stream_id).state == "Requested"


def test_an_approved_waiver_reaches_the_effective_schema_and_the_evaluator(
    world: RegistryWorld,
) -> None:
    before = world.provider.effective("project:P999")
    assert before.conformance.waivers == [] and missing_size(world) == "nonconformant"
    waiver = request(world)
    assert world.provider.effective("project:P999").hash == before.hash  # a request changes nothing
    world.do(ApproveWaiver, ADMIN, waiver_id=waiver.stream_id, comment="Agreed.")
    after = world.provider.effective("project:P999")
    assert after.hash != before.hash
    assert after.conformance.mode == "strict_with_waivers"
    assert [w.path for w in after.conformance.waivers] == [PATH]
    assert after.conformance.waivers[0].approver == ADMIN
    assert missing_size(world) == "waived"
    assert world.waiver(waiver.stream_id).state == "Approved"
    # only that project: another keeps its rule
    assert missing_size(world, "P998") == "nonconformant"
    assert world.provider.effective("company").conformance.waivers == []


def test_a_revoked_waiver_is_gone_from_the_schema(world: RegistryWorld) -> None:
    waiver = request(world)
    world.do(ApproveWaiver, ADMIN, waiver_id=waiver.stream_id)
    assert missing_size(world) == "waived"
    world.do(RevokeWaiver, ADMIN, waiver_id=waiver.stream_id, reason="The data was corrected.")
    row = world.waiver(waiver.stream_id)
    assert (row.state, row.revoked_by) == ("Revoked", ADMIN)
    assert missing_size(world) == "nonconformant"
    assert world.provider.effective("project:P999").conformance.waivers == []
    with pytest.raises(WaiverStateError):
        world.do(RevokeWaiver, ADMIN, waiver_id=waiver.stream_id, reason="Twice.")
    with pytest.raises(WaiverStateError):
        world.do(ApproveWaiver, ADMIN, waiver_id=waiver.stream_id)


def test_a_request_can_be_refused_and_asked_for_again(world: RegistryWorld) -> None:
    first = request(world)
    world.do(RevokeWaiver, ADMIN, waiver_id=first.stream_id, reason="Not good enough.")
    second = request(world)
    assert second.key == f"P999/{PATH}@2"
    assert world.waiver(second.stream_id).number == 2


def test_an_expired_waiver_no_longer_holds_and_the_path_can_be_asked_for_again(
    world: RegistryWorld,
) -> None:
    waiver = request(world)
    world.do(ApproveWaiver, ADMIN, waiver_id=waiver.stream_id)
    assert missing_size(world) == "waived"
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_schemareg_waiver SET expires = '2020-01-01' WHERE id = :id"),
            {"id": waiver.stream_id},
        )
    world.provider.reload()
    assert world.provider.effective("project:P999").conformance.waivers == []
    assert missing_size(world) == "nonconformant"
    assert request(world).key == f"P999/{PATH}@2"


def test_an_expiry_on_the_last_day_still_holds(world: RegistryWorld) -> None:
    waiver = request(world, days=0)
    world.do(ApproveWaiver, ADMIN, waiver_id=waiver.stream_id)
    assert missing_size(world) == "waived"


def test_a_waiver_for_a_property_a_later_schema_dropped_is_left_out_not_fatal(
    world: RegistryWorld,
) -> None:
    waiver = request(world, path="psets.valve_data.tag_no")
    world.do(ApproveWaiver, ADMIN, waiver_id=waiver.stream_id)
    # the property goes away from the committed fixture: simulate with a row for a missing path
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_schemareg_waiver SET path = 'psets.valve_data.gone' WHERE id = :id"),
            {"id": waiver.stream_id},
        )
    world.provider.reload()
    schema = world.provider.effective("project:P999")
    assert schema.conformance.waivers == []


def test_the_reviewer_may_approve_what_someone_else_asked(world: RegistryWorld) -> None:
    waiver = request(world)
    world.do(ApproveWaiver, REVIEWER, waiver_id=waiver.stream_id)
    assert world.waiver(waiver.stream_id).approver == REVIEWER
