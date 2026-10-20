"""A load run from the file to the reconciliation, and back (brief 29.6; P1-I8 S6)."""

from __future__ import annotations

import json

import pytest
from tl_adapters.db import open_uow
from tl_core.services.errors import ServiceError
from tl_mod_legacy.errors import (
    CompensationRefusedError,
    LoadRefusedError,
    LoadRunStateError,
    SourceFileError,
    UnknownLoaderError,
)
from tl_mod_legacy.testing import ADMIN, PROJECT, TAG_FILE, LegacyWorld, tag_csv

DATA = tag_csv(14)


def test_a_tag_list_goes_from_the_file_to_the_reconciliation(world: LegacyWorld) -> None:
    run = world.open("test-tags", "instrument-index.csv", DATA)
    assert (run.key, run.state, run.number) == ("plantx/tags#1", "Opened", 1)
    assert run.source_size == len(DATA) and run.source_sha256 is not None

    extracted = world.service.extract(PROJECT, run.key, actor=ADMIN)
    assert (extracted.state, extracted.row_count, extracted.column_count) == ("Extracted", 14, 11)

    profiled = world.service.profile(PROJECT, run.key, actor=ADMIN)
    assert profiled.state == "Profiled"
    profile = world.service.profile_of(PROJECT, run.key)
    assert profile["rows"] == 14
    by_name = {c["name"]: c for c in profile["columns"]}
    assert by_name["TAG NO"]["key_candidate"] is True and by_name["REMARKS"]["non_empty"] == 0

    planned, plan = world.service.plan(PROJECT, run.key, actor=ADMIN)
    assert planned.state == "Planned"
    assert (planned.plan_new, planned.plan_existing, planned.plan_invalid) == (14, 0, 0)
    assert len(plan.rows) == 14
    assert world.scalar("SELECT count(*) FROM cur_core_record WHERE type = 'engineering.Tag'") == 0

    outcome = world.service.load(PROJECT, run.key, actor=ADMIN)
    assert outcome.created == 14 and outcome.skipped_existing == 0
    assert outcome.correlation_id.startswith("load:")
    assert outcome.source_layer_rows == 14
    loaded = world.run(run.key)
    assert loaded.state == "Loaded" and loaded.loaded_count == 14
    assert len(loaded.record_ids) == 14 and loaded.correlation_id == outcome.correlation_id

    tags = world.rows(
        "SELECT id, key, status FROM cur_core_record WHERE type = 'engineering.Tag' ORDER BY key"
    )
    assert sorted(t["id"] for t in tags) == sorted(loaded.record_ids)
    first = world.rows(
        "SELECT * FROM events WHERE stream_id = :i AND event_type = 'Record.Created'",
        i=loaded.record_ids[0],
    )[0]
    assert first["source"] == "legacy:plantx" and first["correlation_id"] == outcome.correlation_id

    reconciled, report = world.service.reconcile(PROJECT, run.key, actor=ADMIN)
    assert reconciled.state == "Reconciled" and reconciled.mismatches == 0
    assert report["matched"] == 14 and report["created_by_this_run"] == 14
    assert world.service.report_of(PROJECT, run.key)["mismatches"] == 0


def test_the_events_of_a_run_carry_counts_and_ids_but_no_cell(world: LegacyWorld) -> None:
    run = world.loaded("test-tags", "instrument-index.csv", DATA)
    world.service.reconcile(PROJECT, run.key, actor=ADMIN)
    payloads = " ".join(
        r["payload"] if isinstance(r["payload"], str) else json.dumps(r["payload"])
        for r in world.rows("SELECT payload FROM events WHERE stream_id = :i", i=run.id)
    )
    for cell in ("Acme Valves", "Service 3", "47-FV-1003"):
        assert cell not in payloads
    assert world.events_of(run.id)[:2] == ["Record.Created", "LoadRun.Opened"]


def test_the_source_layer_keeps_the_columns_the_mapping_does_not_use(world: LegacyWorld) -> None:
    run = world.loaded("test-tags", "instrument-index.csv", DATA)
    tag = world.rows("SELECT psets_json FROM cur_core_record WHERE id = :i", i=run.record_ids[0])[0]
    psets = json.loads(tag["psets_json"])
    layer = next(
        v for k, v in psets.items() if k == "src.legacy-plantx.tags" or k.startswith("src")
    )
    flat = json.dumps(layer)
    assert "PID-4701" in flat  # the P&ID column is ignored by the mapping and kept as it was
    values = world.rows(
        "SELECT pset, layer FROM cur_pset_values WHERE record_id = :i AND layer = 'source'",
        i=run.record_ids[0],
    )
    assert values and {v["pset"] for v in values} == {"src.legacy-plantx.tags"}


def test_rows_that_cannot_be_loaded_are_skipped_and_counted(world: LegacyWorld) -> None:
    run = world.through_plan("test-tags", "seed.csv", TAG_FILE.read_bytes())
    assert (run.plan_new, run.plan_existing, run.plan_invalid) == (11, 0, 3)
    outcome = world.service.load(PROJECT, run.key, actor=ADMIN)
    assert (outcome.created, outcome.skipped_invalid) == (11, 3)
    _, report = world.service.reconcile(PROJECT, run.key, actor=ADMIN)
    assert report["invalid_rows"] == 3 and report["mismatches"] == 0
    assert all("Acme" not in p for p in report["problems"])


def test_a_second_load_of_the_same_file_creates_nothing(world: LegacyWorld) -> None:
    world.loaded("test-tags", "instrument-index.csv", DATA)
    second = world.through_plan("test-tags", "instrument-index.csv", DATA)
    assert (second.plan_new, second.plan_existing) == (0, 14)
    with pytest.raises(LoadRefusedError, match="nothing to load"):
        world.service.load(PROJECT, second.key, actor=ADMIN)
    assert world.run(second.key).state == "Planned"
    assert world.scalar("SELECT count(*) FROM cur_core_record WHERE type = 'engineering.Tag'") == 14


def test_a_row_the_project_holds_is_left_alone_and_the_rest_is_loaded(world: LegacyWorld) -> None:
    lines = DATA.decode().splitlines()
    world.loaded("test-tags", "first.csv", ("\n".join(lines[:6]) + "\n").encode())
    run = world.through_plan("test-tags", "all.csv", DATA)
    assert (run.plan_new, run.plan_existing) == (9, 5)
    outcome = world.service.load(PROJECT, run.key, actor=ADMIN, expect_new=9)
    assert (outcome.created, outcome.skipped_existing) == (9, 5)
    assert world.scalar("SELECT count(*) FROM cur_core_record WHERE type = 'engineering.Tag'") == 14


def test_the_second_run_of_a_file_kind_has_the_next_number(world: LegacyWorld) -> None:
    first = world.open("test-tags", "a.csv", DATA)
    second = world.open("test-tags", "b.csv", DATA)
    assert (first.key, second.key) == ("plantx/tags#1", "plantx/tags#2")
    assert [r.key for r in world.runs()] == ["plantx/tags#2", "plantx/tags#1"]


def test_a_plan_the_project_has_moved_away_from_is_refused(world: LegacyWorld) -> None:
    lines = DATA.decode().splitlines()
    run = world.through_plan("test-tags", "all.csv", DATA)
    other = world.through_plan("test-tags", "some.csv", ("\n".join(lines[:4]) + "\n").encode())
    world.service.load(PROJECT, other.key, actor=ADMIN)
    with pytest.raises(LoadRefusedError, match="project changed since the plan"):
        world.service.load(PROJECT, run.key, actor=ADMIN)
    assert world.run(run.key).state == "Planned"
    assert world.run(run.key).loaded_count is None


def test_expecting_another_count_refuses(world: LegacyWorld) -> None:
    run = world.through_plan("test-tags", "all.csv", DATA)
    with pytest.raises(LoadRefusedError, match="expected 3 new"):
        world.service.load(PROJECT, run.key, actor=ADMIN, expect_new=3)


def test_stages_run_in_order(world: LegacyWorld) -> None:
    run = world.open("test-tags", "a.csv", DATA)
    for stage in (world.service.profile, world.service.plan):
        with pytest.raises(LoadRunStateError, match="needs"):
            stage(PROJECT, run.key, actor=ADMIN)
    with pytest.raises(LoadRunStateError):
        world.service.load(PROJECT, run.key, actor=ADMIN)
    with pytest.raises(LoadRunStateError):
        world.service.reconcile(PROJECT, run.key, actor=ADMIN)
    world.service.extract(PROJECT, run.key, actor=ADMIN)
    with pytest.raises(LoadRunStateError):
        world.service.extract(PROJECT, run.key, actor=ADMIN)


def test_a_plan_can_be_made_again(world: LegacyWorld) -> None:
    run = world.through_plan("test-tags", "a.csv", DATA)
    again, _ = world.service.plan(PROJECT, run.key, actor=ADMIN)
    assert again.state == "Planned" and again.plan_new == 14


def test_a_run_before_the_load_can_be_voided_and_one_after_cannot(world: LegacyWorld) -> None:
    run = world.open("test-tags", "a.csv", DATA)
    voided = world.service.void(PROJECT, run.key, actor=ADMIN, reason="wrong file")
    assert voided.state == "Void"
    done = world.loaded("test-tags", "b.csv", DATA)
    with pytest.raises(LoadRunStateError):
        world.service.void(PROJECT, done.key, actor=ADMIN, reason="too late")
    with pytest.raises(LoadRefusedError, match="reason"):
        world.service.void(
            PROJECT, world.open("test-tags", "c.csv", DATA).key, actor=ADMIN, reason=" "
        )


def test_a_file_a_loader_does_not_read_is_refused_before_a_run_exists(world: LegacyWorld) -> None:
    with pytest.raises(SourceFileError, match="reads csv, xlsx"):
        world.open("test-tags", "notes.pdf", b"%PDF-1.7")
    with pytest.raises(SourceFileError, match="empty"):
        world.open("test-tags", "a.csv", b"")
    with pytest.raises(UnknownLoaderError, match="installed: test-docs, test-tags"):
        world.open("nope", "a.csv", DATA)
    assert world.runs() == []


def test_a_file_the_reader_refuses_fails_the_stage_and_leaves_the_run(world: LegacyWorld) -> None:
    wide = (
        ",".join(f"c{i}" for i in range(201)) + "\n" + ",".join("x" for _ in range(201))
    ).encode()
    run = world.open("test-tags", "wide.csv", wide)
    with pytest.raises(SourceFileError):
        world.service.extract(PROJECT, run.key, actor=ADMIN)
    after = world.run(run.key)
    assert after.state == "Opened" and after.last_error is not None
    assert "LoadRun.Failed" in world.events_of(run.id)
    assert "c1" not in (after.last_error or "").replace("c1 ", "")  # no cell in the message


def test_a_mapping_that_does_not_fit_the_file_is_reported_at_the_plan(world: LegacyWorld) -> None:
    run = world.open("test-tags", "odd.csv", b"A,B\n1,2\n")
    world.service.extract(PROJECT, run.key, actor=ADMIN)
    world.service.profile(PROJECT, run.key, actor=ADMIN)
    with pytest.raises(ServiceError, match="lacks the column"):
        world.service.plan(PROJECT, run.key, actor=ADMIN)
    assert world.run(run.key).state == "Profiled"


def test_a_run_of_another_project_is_not_found(world: LegacyWorld) -> None:
    run = world.open("test-tags", "a.csv", DATA)
    with pytest.raises(ServiceError, match="no load run"):
        world.service.get("project:OTHER", run.key)
    with open_uow(world.db, readonly=True):
        pass


def test_compensation_ends_exactly_the_records_the_run_made(world: LegacyWorld) -> None:
    lines = DATA.decode().splitlines()
    world.loaded("test-tags", "first.csv", ("\n".join(lines[:4]) + "\n").encode())
    run = world.loaded("test-tags", "all.csv", DATA)
    assert run.loaded_count == 11
    assert world.service.preview_compensation(PROJECT, run.key) == []
    outcome = world.service.compensate(PROJECT, run.key, actor=ADMIN, reason="wrong register")
    assert outcome.reversed == 11 and outcome.correlation_id.startswith("load:")
    assert world.run(run.key).state == "Compensated"
    states = {
        r["key"]: r["status"]
        for r in world.rows(
            "SELECT key, status FROM cur_core_record WHERE type = 'engineering.Tag'"
        )
    }
    assert sum(1 for s in states.values() if s == "Deleted") == 11
    assert sum(1 for s in states.values() if s != "Deleted") == 3  # the first run's tags stay
    last = world.rows(
        "SELECT source, correlation_id FROM events WHERE stream_id = :i ORDER BY seq DESC LIMIT 1",
        i=run.id,
    )[0]
    assert last["correlation_id"] == outcome.correlation_id
    with pytest.raises(LoadRunStateError):
        world.service.compensate(PROJECT, run.key, actor=ADMIN, reason="again")


def test_compensation_is_all_or_nothing_and_refuses_a_record_changed_after_the_load(
    world: LegacyWorld,
) -> None:
    from tl_core.services.commands import UpdateRecord
    from tl_core.services.records import handle_update_record

    run = world.loaded("test-tags", "all.csv", DATA)
    victim = run.record_ids[3]
    with open_uow(world.db) as uow:
        version = world.scalar("SELECT version FROM cur_core_record WHERE id = :i", i=victim)
        handle_update_record(
            uow,
            UpdateRecord(
                actor="user:other", source="test", scope=PROJECT, stream_id=victim,
                expected_version=version, changes={"title": "Edited by a person"},
            ),
        )  # fmt: skip
    problems = world.service.preview_compensation(PROJECT, run.key)
    assert len(problems) == 1 and "changed after the load" in problems[0]
    with pytest.raises(CompensationRefusedError) as raised:
        world.service.compensate(PROJECT, run.key, actor=ADMIN, reason="undo")
    assert raised.value.problems == problems
    assert world.run(run.key).state == "Loaded"
    assert (
        world.scalar(
            "SELECT count(*) FROM cur_core_record "
            "WHERE type = 'engineering.Tag' AND status = 'Deleted'"
        )
        == 0
    )
