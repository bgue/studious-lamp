"""A run has a class, and its files, events and ids follow it (ADR-0016; review findings F1, F4)."""

from __future__ import annotations

import pytest
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.confidentiality import hidden_among, hidden_event_streams
from tl_core.services.errors import ServiceError
from tl_mod_legacy.errors import LoadRefusedError
from tl_mod_legacy.model import use_loaders
from tl_mod_legacy.names import ACTOR
from tl_mod_legacy.testing import ADMIN, PROJECT, LegacyWorld, document_loader, tag_csv

CONTROLLER = cf.Viewer(actor=ADMIN, level=1, account=ADMIN)
DATA = tag_csv(4)


def restricted_run(world: LegacyWorld) -> str:
    """A restricted run taken to Loaded; its id."""
    with cf.use_viewer(CONTROLLER):
        run = world.service.open(
            PROJECT, "test-tags", "a.csv", DATA, actor=ADMIN, confidentiality="restricted"
        )
        world.service.extract(PROJECT, run.key, actor=ADMIN)
        world.service.profile(PROJECT, run.key, actor=ADMIN)
        world.service.plan(PROJECT, run.key, actor=ADMIN)
        world.service.load(PROJECT, run.key, actor=ADMIN)
    return run.id


def test_a_run_is_internal_unless_it_says_otherwise(world: LegacyWorld) -> None:
    run = world.open("test-tags", "a.csv", DATA)
    assert run.confidentiality == "internal"
    assert world.rows("SELECT confidentiality FROM cur_legacy_load_run") == [
        {"confidentiality": "internal"}
    ]


def test_a_restricted_run_is_hidden_from_a_plain_reader(world: LegacyWorld) -> None:
    run_id = restricted_run(world)
    with cf.use_viewer(cf.LOWEST):
        with pytest.raises(ServiceError, match="no load run"):
            world.service.get(PROJECT, "plantx/tags#1")
        with pytest.raises(ServiceError, match="no load run"):
            world.service.get(PROJECT, run_id)
        assert world.service.runs(PROJECT) == []
        with open_uow(world.db, readonly=True) as uow:
            assert hidden_among(uow.conn(), [run_id]) == {run_id}
            assert hidden_event_streams(uow.conn(), [(run_id, "legacy.LoadRun")]) == {run_id}
    with cf.use_viewer(CONTROLLER):
        assert [r.id for r in world.service.runs(PROJECT)] == [run_id]
        assert world.service.profile_of(PROJECT, "plantx/tags#1")["rows"] == 4


def test_the_files_of_a_restricted_run_are_hidden_with_it(world: LegacyWorld) -> None:
    run_id = restricted_run(world)
    ids = [
        str(r["file_id"])
        for r in world.rows("SELECT file_id FROM cur_files WHERE record_id = :r", r=run_id)
    ]
    assert len(ids) >= 3  # source, extracted, profile
    for file_id in ids:
        with cf.use_viewer(cf.LOWEST), open_uow(world.db, readonly=True) as uow:
            with pytest.raises(ServiceError):
                world.files.open_file(uow, PROJECT, file_id, actor=ACTOR)
        with cf.use_viewer(CONTROLLER), open_uow(world.db, readonly=True) as uow:
            opened = world.files.open_file(uow, PROJECT, file_id, actor=ACTOR)
            opened.data.close()


def test_an_agent_sees_no_restricted_run(world: LegacyWorld) -> None:
    restricted_run(world)
    with cf.use_viewer(cf.Viewer(actor="agent:bot", level=0, account="")):
        assert world.service.runs(PROJECT) == []


def test_a_loader_with_a_class_gives_it_to_its_runs(world: LegacyWorld) -> None:
    with (
        use_loaders({"test-docs": document_loader(confidentiality="restricted")}),
        cf.use_viewer(CONTROLLER),
    ):
        run = world.open("test-docs", "register.csv", b"DOC NO,TITLE\n")
    assert run.confidentiality == "restricted"


def test_an_unknown_class_is_refused(world: LegacyWorld) -> None:
    with pytest.raises(LoadRefusedError, match="internal or restricted"):
        world.service.open(
            PROJECT, "test-tags", "a.csv", DATA, actor=ADMIN, confidentiality="privileged"
        )
    assert world.runs() == []


def test_a_restricted_run_is_never_copied_to_the_lake(world: LegacyWorld) -> None:
    with cf.use_viewer(CONTROLLER):
        run = world.service.open(
            PROJECT, "test-tags", "a.csv", DATA, actor=ADMIN, confidentiality="restricted"
        )
        world.service.extract(PROJECT, run.key, actor=ADMIN)
        with pytest.raises(LoadRefusedError, match="restricted"):
            world.service.bronze(PROJECT, run.key, actor=ADMIN, include_confidential=True)
        assert world.run(run.key).bronze_rows is None


def test_an_internal_run_is_copied_only_when_the_administrator_says_so(
    world: LegacyWorld,
) -> None:
    run = world.through_plan("test-tags", "a.csv", DATA)
    with pytest.raises(LoadRefusedError, match="include_confidential"):
        world.service.bronze(PROJECT, run.key, actor=ADMIN)
    assert world.run(run.key).bronze_rows is None
    assert world.service.bronze(PROJECT, run.key, actor=ADMIN, include_confidential=True) == 4
    payload = world.rows(
        "SELECT payload FROM events WHERE stream_id = :i AND event_type = 'LoadRun.Bronzed'",
        i=run.id,
    )[0]["payload"]
    assert '"include_confidential":true' in str(payload).replace(" ", "")


def test_nothing_of_a_refused_copy_reaches_the_lake(world: LegacyWorld, lake) -> None:  # type: ignore[no-untyped-def]
    run = world.through_plan("test-tags", "a.csv", DATA)
    with pytest.raises(LoadRefusedError):
        world.service.bronze(PROJECT, run.key, actor=ADMIN)
    assert not any("legacy_plantx" in str(p) for p in lake.lake_dir.rglob("*"))
