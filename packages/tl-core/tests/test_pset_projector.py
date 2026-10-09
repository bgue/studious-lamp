"""PsetProjector and promoted columns (P0-I2-T07)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.pool import StaticPool
from tl_core.ledger import Event
from tl_core.projection.defaults import default_registry
from tl_core.projection.promoted import ensure_promoted_columns
from tl_core.projection.pset import (
    apply_values,
    classify,
    flatten,
    set_nested,
    typed_columns,
    unset_nested,
)
from tl_schema.compose import compose
from tl_schema.effective import EffectiveSchema
from tl_schema.generators.promoted import column_ddl, promoted_columns, split_column
from tl_schema.packages import PackageDoc

FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures"
BASE_TIME = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
RID = "rec-1"


def effective_schema() -> EffectiveSchema:
    docs = [
        PackageDoc.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
        for p in sorted(FIXTURES.glob("*.yaml"))
    ]
    return compose(docs, "project:P123")


class Events:
    def __init__(self) -> None:
        self.seq = 0
        self.versions: dict[str, int] = {}

    def make(self, event_type: str, payload: dict[str, Any], stream_id: str = RID) -> Event:
        self.seq += 1
        version = self.versions.get(stream_id, 0) + 1
        self.versions[stream_id] = version
        at = BASE_TIME + timedelta(minutes=self.seq)
        return Event(
            event_type=event_type,
            payload=payload,
            seq=self.seq,
            event_id=f"E{self.seq:06d}",
            stream_id=stream_id,
            stream_type="core.Record",
            stream_version=version,
            scope="project:P123",
            actor="user:test",
            recorded_at=at,
            effective_at=at,
            correlation_id="c",
            causation_id=None,
            source="test",
            prev_hash=None,
            hash=f"h{self.seq}",
        )

    def created(self, psets: dict[str, Any] | None = None, stream_id: str = RID) -> Event:
        return self.make(
            "Record.Created",
            {
                "record_type": "core.Record",
                "key": f"K-{stream_id}",
                "title": "t",
                "psets": psets or {},
            },
            stream_id,
        )

    def values_set(
        self,
        pset: str,
        values: dict[str, Any],
        *,
        layer: str = "standard",
        units: dict[str, str] | None = None,
        conformance: str = "ok",
        stream_id: str = RID,
    ) -> Event:
        return self.make(
            "Pset.ValuesSet",
            {
                "pset": pset,
                "layer": layer,
                "values": values,
                "effective_schema_hash": "hash-1",
                "conformance": conformance,
                "units": units or {},
            },
            stream_id,
        )


@pytest.fixture
def engine() -> Iterator[Engine]:
    eng = create_engine("sqlite://", poolclass=StaticPool)
    registry = default_registry()
    with eng.begin() as conn:
        for projector in registry.all():
            for statement in projector.ddl("sqlite"):
                conn.exec_driver_sql(statement)
    yield eng
    eng.dispose()


def apply(engine: Engine, *events: Event) -> None:
    registry = default_registry()
    with engine.begin() as conn:
        for event in events:
            for projector in registry.for_event(event.event_type):
                projector.apply(conn, event)


def rows(engine: Engine, record_id: str = RID) -> dict[str, dict[str, Any]]:
    with engine.connect() as conn:
        found = conn.execute(
            text("SELECT * FROM cur_pset_values WHERE record_id = :id ORDER BY path"),
            {"id": record_id},
        ).mappings()
        return {r["path"]: dict(r) for r in found}


def record(engine: Engine, record_id: str = RID) -> dict[str, Any]:
    with engine.connect() as conn:
        row = (
            conn.execute(text("SELECT * FROM cur_core_record WHERE id = :id"), {"id": record_id})
            .mappings()
            .one()
        )
        return dict(row)


# --- pure helpers ------------------------------------------------------------------------------


def test_set_nested_creates_and_replaces() -> None:
    root: dict[str, Any] = {"a": 5}
    set_nested(root, ["a", "b"], 1)
    set_nested(root, ["c", "d", "e"], 2)
    assert root == {"a": {"b": 1}, "c": {"d": {"e": 2}}}


def test_flatten_descends_to_property_depth_and_keeps_lists() -> None:
    leaves = flatten({"b": {"y": 1, "x": {"z": [1, 2]}}, "a": True, "e": {}})
    assert leaves == [(["a"], True), (["b", "x", "z"], [1, 2]), (["b", "y"], 1)]


def test_flatten_stores_a_dict_value_whole_and_keeps_empty_dicts() -> None:
    psets = {
        "valve_data": {"notes": {"a": {"b": 1}}, "x": {"extra": {}}, "empty": {}},
        "prj": {"shutdown_tie_in": {"plan": {"steps": [1]}}},
        "src": {"ifc": {"Pset_V": {"Size": {"n": 1}}}},
        "section": {},
    }
    assert flatten(psets) == [
        (["prj", "shutdown_tie_in", "plan"], {"steps": [1]}),
        (["src", "ifc", "Pset_V", "Size"], {"n": 1}),
        (["valve_data", "empty"], {}),
        (["valve_data", "notes"], {"a": {"b": 1}}),
        (["valve_data", "x", "extra"], {}),
    ]


@pytest.mark.parametrize(
    ("segments", "expected"),
    [
        (["valve_data", "size_in"], ("valve_data", "size_in", "standard")),
        (["valve_data", "x", "fat_witness_by"], ("valve_data", "x.fat_witness_by", "custom")),
        (["prj", "shutdown_tie_in", "window"], ("prj.shutdown_tie_in", "window", "project")),
        (["enrich", "ai", "valve_type"], ("enrich.ai", "valve_type", "enrichment")),
        (["src", "ifc", "Pset_V", "Size"], ("src.ifc.Pset_V", "Size", "source")),
        (["loose"], ("loose", "loose", "standard")),
    ],
)
def test_classify(segments: list[str], expected: tuple[str, str, str]) -> None:
    assert classify(segments) == expected


def test_typed_columns() -> None:
    assert typed_columns(True)["value_type"] == "boolean"
    assert typed_columns(4)["value_num"] == 4.0
    assert typed_columns(2.5)["value_type"] == "number"
    assert typed_columns("x")["value_text"] == "x"
    listed = typed_columns([1, 2])
    assert listed["value_type"] == "json" and json.loads(listed["value_json"]) == [1, 2]


# --- projection --------------------------------------------------------------------------------


def test_values_set_merges_and_projects(engine: Engine) -> None:
    ev = Events()
    apply(
        engine,
        ev.created(),
        ev.values_set(
            "valve_data",
            {"size_in": 4, "body_material": "CS"},
            units={"size_in": "[in_i]"},
            conformance="warning",
        ),
        ev.values_set("valve_data", {"x.fat_witness_by": "client"}, layer="custom"),
        ev.values_set("prj.shutdown_tie_in", {"window": "SD-1", "approved": True}, layer="project"),
    )
    row = record(engine)
    assert json.loads(row["psets_json"]) == {
        "valve_data": {"size_in": 4, "body_material": "CS", "x": {"fat_witness_by": "client"}},
        "prj": {"shutdown_tie_in": {"window": "SD-1", "approved": True}},
    }
    assert row["version"] == 4 and row["last_seq"] == 4
    assert row["effective_schema_hash"] == "hash-1"
    assert row["conformance"] == "ok"  # the last event's conformance
    found = rows(engine)
    assert list(found) == [
        "psets.prj.shutdown_tie_in.approved",
        "psets.prj.shutdown_tie_in.window",
        "psets.valve_data.body_material",
        "psets.valve_data.size_in",
        "psets.valve_data.x.fat_witness_by",
    ]
    size = found["psets.valve_data.size_in"]
    assert (size["pset"], size["property_name"], size["layer"]) == (
        "valve_data",
        "size_in",
        "standard",
    )
    assert (size["value_type"], size["value_num"], size["unit"]) == ("number", 4.0, "[in_i]")
    assert size["scope"] == "project:P123"
    assert found["psets.valve_data.x.fat_witness_by"]["layer"] == "custom"
    assert found["psets.valve_data.x.fat_witness_by"]["property_name"] == "x.fat_witness_by"
    assert found["psets.prj.shutdown_tie_in.approved"]["value_bool"] == 1
    assert found["psets.prj.shutdown_tie_in.window"]["layer"] == "project"


def test_a_json_property_is_one_row_and_an_empty_dict_leaves_a_row(engine: Engine) -> None:
    ev = Events()
    apply(
        engine,
        ev.created(),
        ev.values_set("valve_data", {"notes": {"a": {"b": 1}}, "empty": {}}),
    )
    found = rows(engine)
    assert list(found) == ["psets.valve_data.empty", "psets.valve_data.notes"]
    assert found["psets.valve_data.empty"]["value_type"] == "json"
    assert json.loads(found["psets.valve_data.notes"]["value_json"]) == {"a": {"b": 1}}


def test_a_later_set_replaces_the_value_and_keeps_the_unit(engine: Engine) -> None:
    ev = Events()
    apply(
        engine,
        ev.created(),
        ev.values_set("valve_data", {"size_in": 4}, units={"size_in": "[in_i]"}),
        ev.values_set("valve_data", {"size_in": 6}),
    )
    size = rows(engine)["psets.valve_data.size_in"]
    assert size["value_num"] == 6.0
    assert size["unit"] == "[in_i]"
    assert size["last_seq"] == 3


def test_record_events_with_psets_keep_the_index_in_step(engine: Engine) -> None:
    ev = Events()
    apply(engine, ev.created({"valve_data": {"size_in": 2}, "note": "x"}))
    assert list(rows(engine)) == ["psets.note", "psets.valve_data.size_in"]
    updated = ev.make(
        "Record.Updated",
        {"changes": {"psets": [{"note": "x"}, {"valve_data": {"size_in": 3}}]}},
    )
    apply(engine, updated)
    assert list(rows(engine)) == ["psets.valve_data.size_in"]
    assert rows(engine)["psets.valve_data.size_in"]["value_num"] == 3.0
    untouched = ev.make("Record.Updated", {"changes": {"title": ["t", "u"]}})
    apply(engine, untouched)
    assert list(rows(engine)) == ["psets.valve_data.size_in"]


def test_records_do_not_see_each_others_rows(engine: Engine) -> None:
    ev = Events()
    apply(
        engine,
        ev.created(stream_id="a"),
        ev.created(stream_id="b"),
        ev.values_set("valve_data", {"size_in": 1}, stream_id="a"),
        ev.values_set("valve_data", {"size_in": 2}, stream_id="b"),
    )
    assert rows(engine, "a")["psets.valve_data.size_in"]["value_num"] == 1.0
    assert rows(engine, "b")["psets.valve_data.size_in"]["value_num"] == 2.0


def test_replay_gives_identical_rows(engine: Engine) -> None:
    ev = Events()
    events = [
        ev.created(),
        ev.values_set("valve_data", {"size_in": 4}, units={"size_in": "[in_i]"}),
        ev.values_set("valve_data", {"x.fat_witness_by": "c"}, layer="custom"),
    ]
    apply(engine, *events)
    first = (rows(engine), record(engine))
    registry = default_registry()
    with engine.begin() as conn:
        for projector in registry.all():
            projector.reset(conn)
    apply(engine, *events)
    assert (rows(engine), record(engine)) == first


def test_a_values_set_for_an_unknown_record_fails(engine: Engine) -> None:
    ev = Events()
    with pytest.raises(LookupError):
        apply(engine, ev.values_set("valve_data", {"size_in": 1}))


# --- promoted columns --------------------------------------------------------------------------


def test_promoted_column_plan() -> None:
    schema = effective_schema()
    columns = promoted_columns(schema)
    assert [(c.name, c.linkml_type) for c in columns] == [
        ("pset__valve_data__size_in", "decimal"),
        ("pset__valve_data__body_material", "string"),
    ]
    assert split_column("pset__valve_data__size_in") == ("valve_data", "size_in")
    assert split_column("psets_json") is None
    assert split_column("pset__a__b__c") is None
    sqlite = column_ddl(columns[0], "sqlite")
    assert sqlite[0] == "ALTER TABLE cur_core_record ADD COLUMN pset__valve_data__size_in NUMERIC"
    postgres = column_ddl(columns[0], "postgres")
    assert "ADD COLUMN IF NOT EXISTS" in postgres[0]
    assert sqlite[1].startswith("CREATE INDEX IF NOT EXISTS ix_cur_core_record_pset__")


def test_ensure_adds_columns_once_and_backfills(engine: Engine) -> None:
    ev = Events()
    apply(
        engine,
        ev.created(),
        ev.values_set("valve_data", {"size_in": 4, "body_material": "CS"}),
        ev.created(stream_id="other"),
    )
    schema = effective_schema()
    with engine.begin() as conn:
        added = ensure_promoted_columns(conn, schema)
    assert added == ["pset__valve_data__size_in", "pset__valve_data__body_material"]
    row = record(engine)
    assert row["pset__valve_data__size_in"] == 4
    assert row["pset__valve_data__body_material"] == "CS"
    assert record(engine, "other")["pset__valve_data__size_in"] is None
    with engine.begin() as conn:
        assert ensure_promoted_columns(conn, schema) == []
        names = {c["name"] for c in inspect(conn).get_columns("cur_core_record")}
    assert "pset__valve_data__size_in" in names


def test_projector_fills_promoted_columns_on_later_events(engine: Engine) -> None:
    with engine.begin() as conn:
        ensure_promoted_columns(conn, effective_schema())
    ev = Events()
    apply(engine, ev.created(), ev.values_set("valve_data", {"size_in": 2.5}))
    assert record(engine)["pset__valve_data__size_in"] == 2.5
    apply(engine, ev.values_set("valve_data", {"size_in": 3, "x.fat_witness_by": "c"}))
    row = record(engine)
    assert row["pset__valve_data__size_in"] == 3
    assert row["pset__valve_data__body_material"] is None
    updated = ev.make("Record.Updated", {"changes": {"psets": [{}, {"valve_data": {}}]}})
    apply(engine, updated)
    assert record(engine)["pset__valve_data__size_in"] is None


# --- None unsets a property --------------------------------------------------------------------


def test_unset_nested_prunes_empty_sections() -> None:
    root: dict[str, Any] = {"a": {"b": {"c": 1}}, "keep": 1}
    assert unset_nested(root, ["a", "b", "c"]) is True
    assert root == {"keep": 1}
    assert unset_nested(root, ["a", "b", "c"]) is False
    assert unset_nested(root, ["keep", "x"]) is False
    assert root == {"keep": 1}


def test_apply_values_sets_and_unsets() -> None:
    root: dict[str, Any] = {"valve_data": {"size_in": 4, "x": {"w": "c"}}}
    apply_values(root, "valve_data", {"size_in": None, "x.w": None, "tag_no": "FV-1", "gone": None})
    assert root == {"valve_data": {"tag_no": "FV-1"}}


def test_a_null_in_values_set_removes_the_key_row_and_promoted_value(engine: Engine) -> None:
    with engine.begin() as conn:
        ensure_promoted_columns(conn, effective_schema())
    ev = Events()
    apply(
        engine,
        ev.created(),
        ev.values_set(
            "valve_data", {"size_in": 4, "manufacturer": "A"}, units={"size_in": "[in_i]"}
        ),
        ev.values_set("valve_data", {"size_in": None}),
    )
    assert json.loads(record(engine)["psets_json"]) == {"valve_data": {"manufacturer": "A"}}
    assert list(rows(engine)) == ["psets.valve_data.manufacturer"]
    assert record(engine)["pset__valve_data__size_in"] is None
    # a later set starts without the old unit being resurrected
    apply(engine, ev.values_set("valve_data", {"size_in": 6}))
    assert rows(engine)["psets.valve_data.size_in"]["unit"] is None


def test_replay_with_a_clear_gives_identical_rows(engine: Engine) -> None:
    ev = Events()
    events = [
        ev.created(),
        ev.values_set("valve_data", {"size_in": 4, "x.fat_witness_by": "c"}),
        ev.values_set("valve_data", {"size_in": None, "x.fat_witness_by": None}),
    ]
    apply(engine, *events)
    first = (rows(engine), record(engine))
    with engine.begin() as conn:
        for projector in default_registry().all():
            projector.reset(conn)
    apply(engine, *events)
    assert (rows(engine), record(engine)) == first
    assert json.loads(first[1]["psets_json"]) == {}


def test_set_unset_set_replays_identically(engine: Engine) -> None:
    ev = Events()
    events = [
        ev.created(),
        ev.values_set("valve_data", {"size_in": 4}, units={"size_in": "[in_i]"}),
        ev.values_set("valve_data", {"size_in": None}),
        ev.values_set("valve_data", {"size_in": 6}),
    ]
    apply(engine, *events)
    first = (rows(engine), record(engine))
    assert json.loads(first[1]["psets_json"]) == {"valve_data": {"size_in": 6}}
    assert first[0]["psets.valve_data.size_in"]["unit"] is None  # the clear dropped the old unit
    with engine.begin() as conn:
        for projector in default_registry().all():
            projector.reset(conn)
    apply(engine, *events)
    assert (rows(engine), record(engine)) == first
