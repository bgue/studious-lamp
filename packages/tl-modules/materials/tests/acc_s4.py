"""Helpers and checks of the S4 module tests (the MTO publish target and AssignMtoLines)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import require_command_access
from tl_core.ledger import NewEvent
from tl_core.util import new_ulid
from tl_mod_documents.derivation.mapping import MappingInvalidError, check_mapping
from tl_mod_documents.derivation.publish import (
    CompensatePublication,
    PublishDerivedDocuments,
    PublishDerivedTags,
    handle_compensate_publication,
    handle_publish_derived_documents,
    handle_publish_derived_tags,
    preview_publication,
)
from tl_mod_documents.derivation.publish_targets import publish_targets
from tl_mod_documents.derivation.schemas import (
    RegisterDocumentSchema,
    handle_register_document_schema,
)
from tl_mod_documents.errors import (
    CompensationRefusedError,
    InvalidDocumentSchemaError,
    PublishRefusedError,
)
from tl_mod_documents.testing import BASE, DocumentsWorld
from tl_mod_materials.errors import (
    MtoLineInUseError,
    WorkPackageNotFoundError,
)
from tl_mod_materials.handlers.items import (
    AdoptItem,
    DefineItem,
    handle_adopt_item,
    handle_define_item,
)
from tl_mod_materials.handlers.mto import (
    AssignMtoLines,
    PublishDerivedMto,
    handle_assign_mto_lines,
    handle_publish_derived_mto,
)

REPO = Path(__file__).resolve().parents[4]
os.environ.setdefault("TL_ENV", "dev")
FIXTURES = REPO / "schema" / "fixtures"
PROJECT = BASE["scope"]
ACTOR = "user:accept"
SOURCE = "accept"
FIXED_IN_USE = "the take-off has a line with a reservation or an issue"

MTO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["line", "item", "qty", "uom"],
    "properties": {
        "line": {"type": "string"},
        "item": {"type": "string"},
        "qty": {"type": "string"},
        "uom": {"type": "string"},
        "tag": {"type": "string"},
    },
}


def mapping_for(target: str = "mto", **changes: Any) -> dict[str, Any]:
    columns = [
        {"column": "line", "to": "number"},
        {"column": "item", "to": "item_code"},
        {"column": "qty", "to": "qty"},
        {"column": "uom", "to": "uom"},
        {"column": "tag", "to": "tag"},
    ]
    return {"target": target, "key_column": "line", "columns": columns, **changes}


TAG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["tag", "type"],
    "properties": {"tag": {"type": "string"}, "type": {"type": "string"}},
}
DOC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["number", "title"],
    "properties": {"number": {"type": "string"}, "title": {"type": "string"}},
}


def expect_refused(call: Callable[[], object], error: type[Exception], what: str) -> Exception:
    try:
        call()
    except error as raised:
        return raised
    raise AssertionError(f"{what}: expected {error.__name__}, nothing was refused")


class World:
    """One empty ledger, the documents helpers over it and the hand-made records."""

    def __init__(self, target: DbTarget, objects: Path) -> None:
        self.target = target
        self.docs = DocumentsWorld(target, objects)
        self.docs.people(
            "u"
        )  # the actor of the documents helpers; a Postgres ledger has no dev rule

    # --- reads ---------------------------------------------------------------------------------

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        return self.docs.rows(sql, **params)

    def one(self, sql: str, **params: Any) -> dict[str, Any]:
        found = self.rows(sql, **params)
        assert len(found) == 1, (sql, found)
        return found[0]

    def seq(self) -> int:
        return int(self.docs.scalar("SELECT COALESCE(MAX(seq), 0) FROM events"))

    def id_of(self, key: str) -> str:
        return str(
            self.one(
                "SELECT id FROM cur_core_record WHERE scope = :s AND key = :k", s=PROJECT, k=key
            )["id"]
        )

    def lines(self, mto_key: str) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT r.key, r.voided, l.* FROM cur_materials_mto_line l "
            "JOIN cur_core_record r ON r.id = l.id JOIN cur_core_record m ON m.id = l.mto_id "
            "WHERE m.key = :k ORDER BY l.line_no",
            k=mto_key,
        )

    def live_links(self, from_key: str, relation: str) -> list[dict[str, Any]]:
        return self.rows(
            "SELECT k.link_id, t.key AS to_key, k.source FROM cur_links k "
            "JOIN cur_core_record f ON f.id = k.from_id JOIN cur_core_record t ON t.id = k.to_id "
            "WHERE f.key = :f AND k.relation = :r AND k.status <> 'retracted' ORDER BY t.key",
            f=from_key,
            r=relation,
        )

    # --- writes --------------------------------------------------------------------------------

    def run(self, handler: Callable[[Any, Any], Any], model: Any, **fields: Any) -> Any:
        scope = fields.pop("scope", PROJECT)
        with open_uow(self.target) as uow:
            return handler(uow, model(actor=ACTOR, source=SOURCE, scope=scope, **fields))

    def create(self, record_type: str, key: str, events: list[NewEvent]) -> str:
        stream = new_ulid()
        created = NewEvent(
            event_type="Record.Created",
            payload={
                "record_type": record_type,
                "key": key,
                "title": key,
                "description": None,
                "psets": {},
            },
        )
        with open_uow(self.target) as uow:
            uow.append(
                stream_id=stream,
                stream_type=record_type,
                scope=PROJECT,
                expected_version=0,
                events=[created, *events],
                actor=ACTOR,
                source=SOURCE,
                correlation_id=new_ulid(),
            )
        return stream

    def add(self, stream: str, record_type: str, events: list[NewEvent]) -> None:
        with open_uow(self.target) as uow:
            version = (
                uow.conn()
                .execute(text("SELECT version FROM cur_core_record WHERE id = :i"), {"i": stream})
                .scalar_one()
            )
            uow.append(
                stream_id=stream,
                stream_type=record_type,
                scope=PROJECT,
                expected_version=int(version),
                events=events,
                actor=ACTOR,
                source=SOURCE,
                correlation_id=new_ulid(),
            )

    def lot(self) -> str:
        """A stock lot made by hand, holding 20 EA at a made-up location."""
        key = f"LOT-{uuid.uuid4().hex[:8]}"
        lot = self.create(
            "materials.StockLot",
            key,
            [
                NewEvent(
                    event_type="StockLot.Defined",
                    payload={
                        "project_item_id": new_ulid(),
                        "heat_no": "H-1",
                        "receipt_id": new_ulid(),
                        "receipt_line": 1,
                        "uom": "EA",
                    },
                )
            ],
        )
        self.move(lot, kind="receive", qty="20.000", to_location_id=self.location)
        return lot

    def move(self, lot: str, **payload: Any) -> None:
        body = {"feed_policy": "none", "uom": "EA", **payload}
        self.add(lot, "materials.StockLot", [NewEvent(event_type="StockLot.Moved", payload=body)])

    location = new_ulid()

    def derived(self, number: str, schema_code: str, csv: str) -> Any:
        opened = self.docs.open_derived(number, "A", schema_code)
        self.docs.upload_content(opened.id, csv.encode("utf-8"), name="takeoff.csv")
        self.docs.start_extraction(derived_id=opened.id)
        self.docs.run_jobs()
        return self.docs.derived_row(opened.id)

    def schema(self, code: str, **more: Any) -> None:
        fields: dict[str, Any] = {
            "json_schema": MTO_SCHEMA,
            "key_column": "line",
            "target_kind": "mto",
            "mapping": mapping_for(),
            "title": "Material take-off",
        }
        fields.update(more)
        self.docs.register_schema(code=code, **fields)

    def publish(self, derived: Any, **more: Any) -> Any:
        with open_uow(self.target) as uow:
            return handle_publish_derived_mto(
                uow,
                PublishDerivedMto(
                    actor=ACTOR,
                    source=SOURCE,
                    scope=PROJECT,
                    derived_id=derived.id,
                    expected_content_rev=derived.content_rev,
                    **more,
                ),
            )

    def compensate(self, derived: Any, reason: str = "acceptance") -> Any:
        with open_uow(self.target) as uow:
            return handle_compensate_publication(
                uow,
                CompensatePublication(
                    actor=ACTOR, source=SOURCE, scope=PROJECT, derived_id=derived.id, reason=reason
                ),
            )

    def assign(self, keys: list[str], number: str) -> Any:
        return self.run(
            handle_assign_mto_lines, AssignMtoLines, mto_lines=keys, work_package_number=number
        )


def passed(name: str) -> None:
    print(f"PASS {name}")


# --- the checks ----------------------------------------------------------------------------------


def check_registry(w: World) -> None:
    targets = publish_targets()
    assert {"tags", "documents", "mto"} <= set(targets), sorted(targets)
    assert targets["mto"].module == "materials" and targets["mto"].record_type == "materials.MTO"
    assert targets["tags"].module == "documents"
    passed("mto is listed among the publish targets with module materials")


def check_mapping_refusals(w: World) -> None:
    schema = MTO_SCHEMA
    assert check_mapping(mapping_for(), schema, "mto").target == "mto"
    columns = [*mapping_for()["columns"], {"column": "line", "to": "no_such_field"}]
    refused = expect_refused(
        lambda: check_mapping(mapping_for(columns=columns), schema, "mto"),
        MappingInvalidError,
        "a column mapped to a field the mto target does not offer",
    )
    assert "no_such_field" in str(refused)
    other = [{"column": "line", "to": "number"}, {"column": "item", "to": "class"}]
    expect_refused(
        lambda: check_mapping(mapping_for(columns=other), schema, "mto"),
        MappingInvalidError,
        "a tag field on the mto target",
    )
    expect_refused(
        lambda: check_mapping(mapping_for("bogus"), schema, "bogus"),
        MappingInvalidError,
        "a target nobody registered",
    )
    expect_refused(
        lambda: check_mapping(mapping_for("tags"), schema, "mto"),
        MappingInvalidError,
        "a mapping whose target is not the schema's target_kind",
    )
    problem = expect_refused(
        lambda: handle_register(w, target_kind="nope", mapping=mapping_for("nope")),
        InvalidDocumentSchemaError,
        "a schema naming an unregistered target_kind",
    )
    assert "publish target" in str(problem)
    passed("an mto mapping naming a column the target does not offer is refused by check_mapping")
    passed("a target nobody registered is refused as a mapping target and as a target_kind")


def handle_register(w: World, **more: Any) -> None:
    with open_uow(w.target) as uow:
        handle_register_document_schema(
            uow,
            RegisterDocumentSchema(
                actor=ACTOR,
                source=SOURCE,
                scope="company",
                code="bogus",
                semver="1.0.0",
                title="x",
                json_schema=MTO_SCHEMA,
                key_column="line",
                **more,
            ),
        )


class Fixtures:
    """What the take-offs refer to: library items adopted by the project, a tag, work packages."""

    def __init__(self, w: World) -> None:
        for code, uom in (("FLG-6", "EA"), ("PIPE-6", "m"), ("VLV-6", "EA"), ("ORPHAN-1", "EA")):
            w.run(
                handle_define_item,
                DefineItem,
                scope="company",
                code=code,
                title=code,
                category="other",
                base_uom=uom,
            )
            if code != "ORPHAN-1":
                w.run(handle_adopt_item, AdoptItem, item_code=code)
        self.tag = w.create("engineering.Tag", "XV-9001", [])
        self.wp1 = w.create("awp.CWP", "P123-CWP-PIP-0001", [])
        self.wp2 = w.create("awp.IWP", "P123-IWP-PIP-0002", [])
        w.create("core.Record", "P123-NOT-A-WP", [])
        w.docs.register("ISO-1234")
        w.docs.create_revision("ISO-1234")
        w.docs.attach("ISO-1234", "A")
        for other in ("ISO-2000", "ISO-3000"):
            w.docs.register(other)
            w.docs.create_revision(other)
            w.docs.attach(other, "A")
        for code in ("mto", "mto-b", "mto-c", "mto-d"):
            w.schema(code)
        self.pid = w.id_of("FLG-6")


GOOD = "line,item,qty,uom,tag\n1,FLG-6,10,EA,\n2,PIPE-6,5.5,m,XV-9001\n3,VLV-6,2,EA,\n"


def check_publish(w: World, f: Fixtures) -> Any:
    first = w.derived("ISO-1234", "mto", GOOD)
    assert first.state == "Valid" and first.row_count == 3, (first.state, first.row_count)
    result = w.publish(first)
    assert result.key == first.key
    mto = w.one("SELECT * FROM cur_materials_mto m JOIN cur_core_record r ON r.id = m.id")
    assert mto["key"] == "ISO-1234@A/MTO" and mto["type"] == "materials.MTO", mto
    assert mto["line_count"] == 3 and mto["derived_document_id"] == first.id
    assert mto["revision_id"] == first.source_revision_id
    lines = w.lines("ISO-1234@A/MTO")
    assert [r["key"] for r in lines] == [f"ISO-1234@A/MTO/00{i}" for i in (1, 2, 3)]
    assert [(r["line_no"], float(r["qty"]), r["uom"]) for r in lines] == [
        (1, 10.0, "EA"),
        (2, 5.5, "m"),
        (3, 2.0, "EA"),
    ]
    assert all(r["work_package_id"] is None for r in lines)
    assert lines[1]["tag_id"] == f.tag and lines[0]["tag_id"] is None
    assert lines[0]["project_item_id"] == f.pid
    passed("a derived mto document of 3 rows publishes: one MTO ISO-1234@A/MTO, lines 001..003")
    passed("MTO line_count is 3; quantities, units, items and the tag reference are the rows'")
    derived_from = w.live_links("ISO-1234@A/MTO", "derived_from")
    assert sorted(r["to_key"] for r in derived_from) == sorted([first.key, "ISO-1234@A"]), (
        derived_from
    )
    belongs = w.live_links("ISO-1234@A/MTO/002", "belongs_to")
    assert [r["to_key"] for r in belongs] == ["ISO-1234@A/MTO"] and belongs[0]["source"] == "import"
    refs = w.live_links("ISO-1234@A/MTO/002", "references")
    assert [r["to_key"] for r in refs] == ["XV-9001"]
    assert w.live_links("ISO-1234@A/MTO/001", "references") == []
    published = w.one("SELECT payload FROM events WHERE event_type = 'DerivedDocument.Published'")[
        "payload"
    ]
    assert '"target_kind":"mto"' in str(published).replace(" ", "")
    assert w.docs.derived_row(first.id).state == "Published"
    passed("links are present: MTO derived_from, lines belongs_to the MTO and references the tag")
    return first


def check_skip_existing(w: World, f: Fixtures) -> None:
    second = w.derived("ISO-1234", "mto-b", GOOD)
    with open_uow(w.target, readonly=True) as uow:
        plan = preview_publication(uow, PROJECT, second.id)
    assert plan.counts == {"create": 0, "exists": 3, "differs": 0, "invalid": 0}, plan.counts
    assert [r.action for r in plan.rows] == ["exists"] * 3
    before = w.seq()
    expect_refused(
        lambda: w.publish(second, skip_existing=True), PublishRefusedError, "a second publish"
    )
    assert w.seq() == before
    assert w.one("SELECT COUNT(*) AS n FROM cur_materials_mto")["n"] == 1
    assert w.one("SELECT COUNT(*) AS n FROM cur_materials_mto_line")["n"] == 3
    # the same, with a row the take-off lacks: skipped and counted, never added
    third = w.derived("ISO-1234", "mto-c", GOOD + "4,FLG-6,1,EA,\n")
    with open_uow(w.target, readonly=True) as uow:
        plan = preview_publication(uow, PROJECT, third.id)
    assert plan.counts == {"create": 0, "exists": 3, "differs": 1, "invalid": 0}, plan.counts
    passed("a second publish with skip_existing creates 0 and counts 3 skipped; nothing changes")


def check_plan_problems(w: World, f: Fixtures) -> None:
    csv = (
        "line,item,qty,uom,tag\n"
        "1,FLG-6,10,EA,\n"
        "2,ORPHAN-1,4,EA,\n"  # a library item the project has not adopted
        "3,VLV-6,2,m,\n"  # the item's unit is EA
        "4,VLV-6,0,EA,\n"  # zero quantity
    )
    bad = w.derived("ISO-2000", "mto", csv)
    with open_uow(w.target, readonly=True) as uow:
        plan = preview_publication(uow, PROJECT, bad.id)
    by_row = {r.row: r for r in plan.rows}
    assert [by_row[i].action for i in (1, 2, 3, 4)] == ["create", "invalid", "invalid", "invalid"]
    assert "not adopted" in by_row[2].problems[0] and "unit of the item" in by_row[3].problems[0]
    text_ = " ".join(p for r in plan.rows for p in r.problems)
    assert "ORPHAN" not in text_ and "ORPHAN" not in str(plan.problems)
    before = w.seq()
    raised = expect_refused(lambda: w.publish(bad), PublishRefusedError, "the bad rows")
    message = str(raised)
    assert "row 2" in message and "row 3" in message and "row 4" in message
    assert "ORPHAN" not in message and w.seq() == before
    passed("an unadopted item code and a uom mismatch are plan problems naming row numbers only")


def check_assign(w: World, f: Fixtures) -> None:
    keys = [f"ISO-1234@A/MTO/00{i}" for i in (1, 2, 3)]
    done = w.assign([keys[1], keys[2]], "P123-CWP-PIP-0001")
    assert len(done.events) >= 2
    lines = w.lines("ISO-1234@A/MTO")
    assert [r["work_package_id"] for r in lines] == [None, f.wp1, f.wp1]
    assert [r["to_key"] for r in w.live_links(keys[1], "belongs_to")] == [
        "ISO-1234@A/MTO",
        "P123-CWP-PIP-0001",
    ]
    assigned = w.rows("SELECT COUNT(*) AS n FROM events WHERE event_type = 'MTOLine.Assigned'")[0][
        "n"
    ]
    assert assigned == 2
    passed("AssignMtoLines sets the work package, one MTOLine.Assigned per line")
    before = w.seq()
    expect_refused(
        lambda: w.assign([keys[0]], "P123-NOT-A-WP"),
        WorkPackageNotFoundError,
        "a record that is no WP",
    )
    expect_refused(
        lambda: w.assign([keys[0]], "NO-SUCH-WP"), WorkPackageNotFoundError, "an unknown number"
    )
    assert w.seq() == before
    passed("AssignMtoLines is refused for an unknown work package number; nothing changes")
    # a line with a reservation: the batch is refused and the other line is not moved either
    lot = w.lot()
    w.move(
        lot, kind="reserve", qty="4.000", from_location_id=w.location, mto_line_id=w.id_of(keys[0])
    )
    before = w.seq()
    expect_refused(
        lambda: w.assign([keys[1], keys[0]], "P123-IWP-PIP-0002"),
        MtoLineInUseError,
        "a line with a reservation",
    )
    assert w.seq() == before
    assert w.lines("ISO-1234@A/MTO")[1]["work_package_id"] == f.wp1
    passed("AssignMtoLines is refused for a line with a reservation and is all or nothing")
    f.reserved_lot = lot  # type: ignore[attr-defined]


def check_compensation_refusals(w: World, f: Fixtures, first: Any) -> None:
    before = w.seq()
    raised = expect_refused(
        lambda: w.compensate(first), CompensationRefusedError, "a reserved line"
    )
    assert FIXED_IN_USE in str(raised), str(raised)
    assert w.seq() == before
    assert all(not bool(r["voided"]) for r in w.lines("ISO-1234@A/MTO"))
    assert w.docs.derived_row(first.id).state == "Published"
    passed("compensation with a reservation is refused with the fixed message; nothing changes")
    # a take-off with an issued line (no reservation held): refused too
    issued = w.derived("ISO-3000", "mto", "line,item,qty,uom,tag\n1,FLG-6,3,EA,\n")
    w.publish(issued)
    line = w.id_of("ISO-3000@A/MTO/001")
    lot = w.lot()
    w.move(lot, kind="issue", qty="1.000", from_location_id=w.location, mto_line_id=line)
    row = w.one("SELECT reserved_qty, issued_qty FROM cur_materials_mto_line WHERE id = :i", i=line)
    assert float(row["reserved_qty"]) == 0 and float(row["issued_qty"]) == 1
    before = w.seq()
    raised = expect_refused(
        lambda: w.compensate(issued), CompensationRefusedError, "an issued line"
    )
    assert FIXED_IN_USE in str(raised) and w.seq() == before
    expect_refused(
        lambda: w.assign(["ISO-3000@A/MTO/001"], "P123-CWP-PIP-0001"),
        MtoLineInUseError,
        "an issued line",
    )
    passed("compensation with an issue is refused with the fixed message; nothing changes")


def check_compensate_and_republish(w: World, f: Fixtures, first: Any) -> None:
    w.move(
        f.reserved_lot,  # type: ignore[attr-defined]
        kind="unreserve",
        qty="4.000",
        from_location_id=w.location,
        mto_line_id=w.id_of("ISO-1234@A/MTO/001"),
    )
    w.compensate(first, "wrong revision")
    mto = w.one("SELECT voided FROM cur_core_record WHERE key = 'ISO-1234@A/MTO'")
    assert bool(mto["voided"]) is True
    lines = w.lines("ISO-1234@A/MTO")
    assert len(lines) == 3 and all(bool(r["voided"]) for r in lines)
    for line in lines:
        assert w.live_links(line["key"], "belongs_to") == []
        assert w.live_links(line["key"], "references") == []
    assert w.live_links("ISO-1234@A/MTO", "derived_from") == []
    compensated = w.rows(
        "SELECT COUNT(*) AS n FROM events "
        "WHERE event_type = 'DerivedDocument.PublicationCompensated'"
    )[0]["n"]
    assert compensated == 1
    live = w.one(
        "SELECT COUNT(*) AS n FROM cur_core_record WHERE type LIKE 'materials.MTO%' AND NOT voided"
    )
    assert live["n"] == 2  # the ISO-3000 take-off and its line
    passed("compensation without a reservation or an issue removes the MTO and its lines")
    again = w.docs.derived_row(first.id)
    assert again.state == "Valid"
    w.publish(again)
    fresh = w.lines("ISO-1234@A/MTO-2")
    assert [r["key"] for r in fresh] == [f"ISO-1234@A/MTO-2/00{i}" for i in (1, 2, 3)]
    assert all(not bool(r["voided"]) for r in fresh)
    assert (
        w.one(
            "SELECT line_count FROM cur_materials_mto m JOIN cur_core_record r ON r.id = m.id "
            "WHERE r.key = 'ISO-1234@A/MTO-2'"
        )["line_count"]
        == 3
    )
    passed("republish after compensation creates the take-off and its lines again")
    # a work package named on the command assigns every line
    wp = w.derived("ISO-2000", "mto-d", "line,item,qty,uom,tag\n1,FLG-6,2,EA,\n")
    w.publish(wp, work_package_number="P123-CWP-PIP-0001")
    assert [r["work_package_id"] for r in w.lines("ISO-2000@A/MTO")] == [f.wp1]
    expect_refused(
        lambda: w.publish(
            w.derived("ISO-2000", "mto-b", "line,item,qty,uom,tag\n1,FLG-6,2,EA,\n"),
            work_package_number="NO-SUCH-WP",
        ),
        WorkPackageNotFoundError,
        "an unknown work package on the publish command",
    )
    passed("PublishDerivedMto assigns every line to the work package it names, or is refused")


def check_word(w: World) -> None:
    from tl_mod_materials.commands import MATERIALS_COMMANDS

    words = {c.model.__name__: c.access for c in MATERIALS_COMMANDS}
    assert words["PublishDerivedMto"] == "materials.mto.publish"
    assert words["AssignMtoLines"] == "materials.mto.assign"
    w.docs.people("alice")
    base: dict[str, Any] = {"source": SOURCE, "scope": PROJECT}
    publish = PublishDerivedMto(actor="user:alice", derived_id="x", expected_content_rev=1, **base)
    with open_uow(w.target, readonly=True) as uow:
        expect_refused(
            lambda: require_command_access(uow.conn(), publish), ForbiddenError, "a plain user"
        )
        require_command_access(
            uow.conn(),
            AssignMtoLines(actor="user:alice", mto_lines=["x"], work_package_number="y", **base),
        )
    passed("a user without materials.mto.publish is refused through the command's word")


def check_builtin_targets(w: World) -> None:
    w.docs.load_standards()
    w.docs.register("ISD-001")
    w.docs.create_revision("ISD-001")
    w.docs.attach("ISD-001", "A")
    w.docs.register_schema()
    tags = w.docs.valid_derived(
        [
            ("47-FV-1001", "Feed", "CV", "4"),
            ("47-HV-1002", "Return", "HV", "6"),
            ("47-PSV-2001", "Vent", "PSV", "2"),
        ]
    )
    with open_uow(w.target) as uow:
        handle_publish_derived_tags(
            uow,
            PublishDerivedTags(**BASE, derived_id=tags.id, expected_content_rev=tags.content_rev),
        )
    made = w.rows(
        "SELECT key FROM cur_core_record WHERE type = 'engineering.Tag' AND key LIKE '47-%' "
        "ORDER BY key"
    )
    assert [r["key"] for r in made] == ["47-FV-1001", "47-HV-1002", "47-PSV-2001"]
    w.compensate(tags, "smoke")
    ended = w.rows("SELECT status FROM cur_core_record WHERE key LIKE '47-%'")
    assert len(ended) == 3 and all(r["status"] == "Deleted" for r in ended), ended
    passed("the tags target still publishes and compensates")
    w.docs.register_schema(
        code="doc-register",
        json_schema=DOC_SCHEMA,
        target_kind="documents",
        key_column="number",
        title="Document register",
        mapping={
            "target": "documents",
            "key_column": "number",
            "columns": [{"column": "number", "to": "number"}, {"column": "title", "to": "title"}],
        },
    )
    docs = w.derived("ISD-001", "doc-register", "number,title\nGA-100,General\nGA-101,Sections\n")
    with open_uow(w.target) as uow:
        handle_publish_derived_documents(
            uow,
            PublishDerivedDocuments(
                **BASE, derived_id=docs.id, expected_content_rev=docs.content_rev
            ),
        )
    assert w.one("SELECT COUNT(*) AS n FROM cur_core_record WHERE key LIKE 'GA-%'")["n"] == 2
    w.compensate(docs, "smoke")
    voided = w.rows("SELECT voided FROM cur_core_record WHERE key LIKE 'GA-%'")
    assert len(voided) == 2 and all(bool(r["voided"]) for r in voided)
    passed("the documents target still publishes and compensates")
