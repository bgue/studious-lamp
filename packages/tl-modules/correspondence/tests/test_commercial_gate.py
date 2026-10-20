"""A Commercial item changes only in the hands of a controller (P1-I6 security review, F1).

An escalation names the readers of a privileged RFI on the Commercial item it makes, and a named
reader may be a plain person (level 0). They read the item; they must not pause or meet its time
bar, start a clock, void it, put it in a thread, link it or attach to it, whatever the access word
of the command says. The same commands work for a plain person on a Technical item.
"""

from __future__ import annotations

from typing import Any

import pytest
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.auth.errors import ForbiddenError
from tl_core.modules import require_generic
from tl_mod_correspondence.errors import ItemStateError
from tl_mod_correspondence.module import ITEM_GENERIC_COMMANDS
from tl_mod_correspondence.names import COMMERCIAL, TECHNICAL
from tl_mod_correspondence.testing import CorrWorld, frozen_today

AMY = cf.Viewer(actor="user:amy", level=0, account="user:amy")
BOSS = cf.Viewer(actor="user:ctl", level=1, account="user:ctl")  # named on the item below


class Scene:
    def __init__(self, world: CorrWorld) -> None:
        self.world = world
        self.item = world.forge_commercial("P123-EW-0001", confidentiality="privileged")
        for account in ("user:amy", "user:ctl"):
            world.forge_item_event(
                self.item,
                "Correspondence.ClearanceGranted",
                {"account": account, "granted_on": "2026-10-19", "reason": "counsel"},
            )
        with frozen_today("2026-10-19"), cf.use_viewer(BOSS):
            self.bar = world.start_clock(self.item, kind="time_bar", label="Bar").stream_id
            self.wait = world.start_clock(self.item, label="Reply").stream_id

    def events(self) -> int:
        return self.world.scalar("SELECT count(*) FROM events")


@pytest.fixture
def scene(world: CorrWorld) -> Scene:
    return Scene(world)


def test_the_named_plain_reader_reads_the_item_and_its_clocks(scene: Scene) -> None:
    with cf.use_viewer(AMY):
        row = scene.world.commercial("P123-EW-0001")
        assert row.item.confidentiality == "privileged"
        assert [c.key for c in scene.world.clocks("P123-EW-0001")] == [
            "P123-EW-0001-C01",
            "P123-EW-0001-C02",
        ]


def clock_commands(scene: Scene) -> list[Any]:
    world = scene.world
    return [
        lambda: world.start_clock(scene.item, label="Another"),
        lambda: world.pause(scene.bar),
        lambda: world.pause(scene.wait),
        lambda: world.resume(scene.bar),
        lambda: world.restart(scene.bar),
        lambda: world.restart(scene.wait),
        lambda: world.meet(scene.bar),
        lambda: world.meet(scene.wait),
        lambda: world.cancel(scene.bar),
        lambda: world.cancel(scene.wait),
    ]


def test_a_plain_reader_can_not_run_a_clock_command_on_a_commercial_item(scene: Scene) -> None:
    before = scene.events()
    with frozen_today("2026-10-20"), cf.use_viewer(AMY):
        for command in clock_commands(scene):
            with pytest.raises(ForbiddenError):
                command()
    assert scene.events() == before


def test_a_plain_reader_can_not_void_or_thread_a_commercial_item(scene: Scene) -> None:
    before = scene.events()
    world = scene.world
    with frozen_today("2026-10-20"), cf.use_viewer(AMY):
        with pytest.raises(ForbiddenError):
            world.void_draft(scene.item)
        with pytest.raises(ForbiddenError):
            world.assign(scene.item)
    assert scene.events() == before
    with cf.use_viewer(BOSS):  # the time bar is still running
        assert world.commercial("P123-EW-0001").item.state == "Draft"
        assert {c.state for c in world.clocks("P123-EW-0001")} == {"running"}


def test_a_controller_runs_the_same_commands(scene: Scene) -> None:
    world = scene.world
    with frozen_today("2026-10-20"), cf.use_viewer(BOSS):
        world.pause(scene.wait)
        world.resume(scene.wait)
        world.restart(scene.bar)
        world.assign(scene.item)
        world.void_draft(scene.item)
        assert world.commercial("P123-EW-0001").item.state == "Void"
        assert {c.state for c in world.clocks("P123-EW-0001")} == {"cancelled"}


@pytest.mark.parametrize("command", sorted(ITEM_GENERIC_COMMANDS))
def test_a_plain_reader_can_not_run_a_generic_command_on_a_commercial_item(
    scene: Scene, command: str
) -> None:
    def check(viewer: cf.Viewer, record_type: str, record_id: str) -> None:
        with cf.use_viewer(viewer), open_uow(scene.world.db, readonly=True) as uow:
            require_generic(uow.conn(), record_type, command, record_id, slot="original")

    with pytest.raises(ForbiddenError):
        check(AMY, COMMERCIAL, scene.item)
    check(BOSS, COMMERCIAL, scene.item)  # a controller named on it passes


def test_a_plain_person_still_runs_the_generic_commands_on_a_technical_item(
    world: CorrWorld,
) -> None:
    item = world.forge_technical("P123-RFI-0001")
    for command in sorted(ITEM_GENERIC_COMMANDS):
        with cf.use_viewer(AMY), open_uow(world.db, readonly=True) as uow:
            require_generic(uow.conn(), TECHNICAL, command, item, slot="original")
    with frozen_today("2026-10-20"), cf.use_viewer(AMY):
        world.start_clock(item, label="Reply")
        world.void_draft(item)


def test_the_commands_of_a_plain_letter_do_not_reach_a_commercial_item_either(scene: Scene) -> None:
    """The user-access commands that move a letter refuse a domain item, a named reader or not."""
    world = scene.world
    letter = world.forge_item("P123-COR-0001", state="Received")
    before = scene.events()
    with frozen_today("2026-10-20"), cf.use_viewer(AMY):
        for command in (
            lambda: world.update(scene.item, body="changed"),
            lambda: world.close(scene.item),
            lambda: world.respond(scene.item, letter),
            lambda: world.triage(scene.item),
            lambda: world.reclassify(scene.item, "general", "letter"),
        ):
            with pytest.raises((ItemStateError, ForbiddenError)):
                command()
    assert scene.events() == before
