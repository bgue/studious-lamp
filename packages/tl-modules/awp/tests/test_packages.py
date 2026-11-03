"""The owner's external packages, EWP and PWP (S4)."""

from __future__ import annotations

import pytest
from awp_world import EWP, PWP, World, refuses
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import NoChangesError, RecordNotFoundError
from tl_mod_awp.errors import DuplicateCodeError

KINDS = (("ewp", "EWP-0042", EWP, "cur_awp_ewp_ref"), ("pwp", "PWP-0042", PWP, "cur_awp_pwp_ref"))


@pytest.mark.parametrize(("kind", "number", "record_type", "table"), KINDS)
def test_record_update_and_void(
    world: World, kind: str, number: str, record_type: str, table: str
) -> None:
    world.call(
        "uma",
        "RecordExternalPackage",
        package_type=kind,
        package_no=number,
        title=f"Package {number}",
        status_text="In review",
        forecast_date="2026-11-20",
        constraint_source=True,
        source_system="Owner portal",
    )
    pid = world.id_of(number, record_type)
    refuses(
        DuplicateCodeError,
        lambda: world.call(
            "uma",
            "RecordExternalPackage",
            package_type=kind,
            package_no=number,
            title="Again",
            constraint_source=False,
        ),
    )
    world.call(
        "uma",
        "UpdateExternalPackage",
        id=pid,
        status_text="Approved",
        constraint_source=False,
        actual_date="2026-11-18",
    )
    got = world.rows(f"SELECT status_text, constraint_source, actual_date FROM {table}")
    assert [(g["status_text"], bool(g["constraint_source"]), g["actual_date"]) for g in got] == [
        ("Approved", False, "2026-11-18")
    ]
    refuses(
        NoChangesError,
        lambda: world.call("uma", "UpdateExternalPackage", id=pid, status_text="Approved"),
    )
    refuses(
        ForbiddenError,
        lambda: world.call("uma", "VoidExternalPackage", id=pid, reason="x"),
    )
    world.call("sue", "VoidExternalPackage", id=pid, reason="withdrawn")
    assert bool(world.scalar("SELECT voided FROM cur_core_record WHERE id = :i", i=pid))
    refuses(
        RecordNotFoundError,
        lambda: world.call("uma", "UpdateExternalPackage", id=pid, status_text="Again"),
    )


def test_the_two_kinds_may_share_a_number(world: World) -> None:
    for kind in ("ewp", "pwp"):
        world.call(
            "uma",
            "RecordExternalPackage",
            package_type=kind,
            package_no="X-1",
            title="T",
            constraint_source=False,
        )
    assert world.id_of("X-1", EWP) != world.id_of("X-1", PWP)


def test_a_viewer_may_not_record_a_package(world: World) -> None:
    refuses(
        ForbiddenError,
        lambda: world.call(
            "vera",
            "RecordExternalPackage",
            package_type="ewp",
            package_no="E-1",
            title="T",
            constraint_source=False,
        ),
    )
