"""Publishing a valid derived document and rolling the publication back (S5; ADR-0014)."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from docworld import BASE, FIXTURES, World
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core.derivation.registry import use_extractors
from tl_core.derivation.testing import make_extractors
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_mod_documents.derivation import rows
from tl_mod_documents.derivation.publish import (
    CompensatePublication,
    PublishDerivedDocuments,
    PublishDerivedTags,
    handle_compensate_publication,
    handle_publish_derived_documents,
    handle_publish_derived_tags,
    preview_compensation,
    preview_publication,
)
from tl_mod_documents.derivation.store import use_files
from tl_mod_documents.errors import CompensationRefusedError, PublishRefusedError
from tl_mod_documents.testing import index_csv

TAGS = [
    ("47-FV-1001", "Feed", "CV", "4"),
    ("47-HV-1002", "Return", "HV", "6"),
    ("47-PSV-2001", "Vent", "PSV", "2"),
]
DOC_SCHEMA = {
    "type": "object",
    "required": ["number", "title"],
    "properties": {
        "number": {"type": "string"},
        "title": {"type": "string"},
        "discipline": {"type": "string"},
    },
}
DOC_MAPPING = {
    "target": "documents",
    "key_column": "number",
    "columns": [
        {"column": "number", "to": "number"},
        {"column": "title", "to": "title"},
        {"column": "discipline", "to": "discipline"},
    ],
}


@pytest.fixture(autouse=True)
def runtime(world: World) -> Iterator[None]:
    with use_extractors(make_extractors()), use_files(world.files):
        yield


@pytest.fixture
def ready(world: World) -> World:
    world.load_standards()
    world.register("ISD-001")
    world.create_revision("ISD-001")
    world.attach("ISD-001", "A")
    world.register_schema()
    return world


def publish_tags(world: World, derived: Any, **more: Any) -> Any:
    fields = {"derived_id": derived.id, "expected_content_rev": derived.content_rev, **more}
    with open_uow(world.db) as uow:
        return handle_publish_derived_tags(uow, PublishDerivedTags(**BASE, **fields))


def preview(world: World, derived_id: str) -> Any:
    with open_uow(world.db, readonly=True) as uow:
        return preview_publication(uow, BASE["scope"], derived_id)


def tags(world: World) -> list[dict[str, Any]]:
    return world.rows(
        "SELECT r.id, r.key, r.status, t.class_code, t.origin, r.psets_json "
        "FROM cur_core_record r JOIN cur_engineering_tag t ON t.id = r.id ORDER BY r.key"
    )


def test_the_preview_says_what_would_be_created_and_writes_nothing(ready: World) -> None:
    derived = ready.valid_derived(TAGS)
    before = ready.scalar("SELECT COUNT(*) FROM events")
    plan = preview(ready, derived.id)
    assert plan.can_publish and plan.problems == [] and plan.target == "tags"
    assert plan.counts == {"create": 3, "exists": 0, "differs": 0, "invalid": 0}
    assert [r.key for r in plan.rows] == [t[0] for t in TAGS]
    first = plan.rows[0]
    assert first.action == "create" and first.values["class"] == "ControlValve"
    assert first.values["service"] == "Feed"
    assert first.values["psets"] == {"valve_data": {"size_in": 4.0}}
    assert plan.schema_key == "instrument-index@1.0.0" and plan.source_ref == "src.doc.ISD-001@A"
    assert ready.scalar("SELECT COUNT(*) FROM events") == before


def test_publishing_creates_the_tags_with_provenance_and_a_link_in_one_correlated_import(
    ready: World,
) -> None:
    derived = ready.valid_derived(TAGS)
    made = publish_tags(ready, derived)
    after = ready.derived_row(derived.id)
    assert (
        after.state == "Published" and after.published_rev == 3 - 2 and after.published_count == 3
    )
    created = tags(ready)
    assert [t["key"] for t in created] == [t[0] for t in TAGS]
    assert {t["origin"] for t in created} == {"import"}
    assert [t["class_code"] for t in created] == ["ControlValve", "ManualValve", "SafetyValve"]
    import json

    for tag in created:
        psets = (
            json.loads(tag["psets_json"])
            if isinstance(tag["psets_json"], str)
            else tag["psets_json"]
        )
        assert psets["provenance"] == {
            "source": "src.doc.ISD-001@A",
            "derived_document": "ISD-001@A/instrument-index",
        }
        links = ready.rows(
            "SELECT status, relation, to_id FROM cur_links WHERE from_id = :i", i=tag["id"]
        )
        assert [(r["status"], r["relation"], r["to_id"]) for r in links] == [
            ("active", "derived_from", derived.id)
        ]
    # one correlation id for the whole import, the derived document's own events included
    corr = after.published_correlation_id
    assert corr is not None
    streams = ready.rows("SELECT DISTINCT stream_id FROM events WHERE correlation_id = :c", c=corr)
    ids = {r["stream_id"] for r in streams}
    assert {t["id"] for t in created} <= ids and derived.id in ids
    assert ready.scalar("SELECT COUNT(*) FROM events WHERE correlation_id = :c", c=corr) > 9
    assert all(
        e["source"] == f"import:derived-{derived.id}"
        for e in ready.rows("SELECT source FROM events WHERE correlation_id = :c", c=corr)
    )
    assert made.key == "ISD-001@A/instrument-index"
    assert [e.event_type for e in made.events][0] == "DerivedDocument.Published"


def test_a_published_derived_document_cannot_be_published_again(ready: World) -> None:
    derived = ready.valid_derived(TAGS)
    publish_tags(ready, derived)
    with pytest.raises(PublishRefusedError, match="Published"):
        publish_tags(ready, ready.derived_row(derived.id))
    assert len(tags(ready)) == 3


def test_the_content_revision_the_person_looked_at_must_be_the_latest(ready: World) -> None:
    derived = ready.valid_derived(TAGS)
    ready.upload_content(derived.id, index_csv([*TAGS, ("47-FV-1003", "Spare", "CV", "4")]))
    ready.start_extraction(derived_id=derived.id)
    ready.run_jobs()
    latest = ready.derived_row(derived.id)
    assert latest.content_rev == 2 and latest.state == "Valid"
    with pytest.raises(PublishRefusedError, match="latest content revision is 2, not 1") as caught:
        publish_tags(ready, latest, expected_content_rev=1)
    assert caught.value.problems
    assert tags(ready) == []
    publish_tags(ready, latest)
    assert len(tags(ready)) == 4


def test_only_a_valid_derived_document_is_published(ready: World) -> None:
    derived = ready.open_derived("ISD-001", "A")
    ready.upload_content(derived.id, index_csv([("bad", "x", "CV", "4")]))
    ready.start_extraction(derived_id=derived.id)
    ready.run_jobs()
    invalid = ready.derived_row(derived.id)
    assert invalid.state == "Invalid"
    with pytest.raises(PublishRefusedError, match="only a Valid derived document is published"):
        publish_tags(ready, invalid)
    assert preview(ready, derived.id).can_publish is False


def test_the_wrong_command_for_the_schemas_target_is_refused(ready: World) -> None:
    derived = ready.valid_derived(TAGS)
    with (
        open_uow(ready.db) as uow,
        pytest.raises(PublishRefusedError, match="publishes tags, not documents"),
    ):
        handle_publish_derived_documents(
            uow,
            PublishDerivedDocuments(
                **BASE, derived_id=derived.id, expected_content_rev=derived.content_rev
            ),
        )


def test_rows_that_exist_stop_the_publication_unless_they_are_skipped(ready: World) -> None:
    from tl_mod_engineering.handlers.tags import RecordTag, handle_record_tag

    with open_uow(ready.db) as uow:
        handle_record_tag(uow, RecordTag(**BASE, number="47-FV-1001", class_code="ControlValve"))
    derived = ready.valid_derived(TAGS)
    plan = preview(ready, derived.id)
    assert plan.counts["create"] == 2 and plan.counts["exists"] + plan.counts["differs"] == 1
    assert plan.can_publish and plan.needs_skip_existing
    with pytest.raises(PublishRefusedError, match="skip_existing"):
        publish_tags(ready, derived)
    publish_tags(ready, derived, skip_existing=True)
    created = {t["key"] for t in tags(ready)}
    assert created == {t[0] for t in TAGS}
    links = ready.scalar("SELECT COUNT(*) FROM cur_links WHERE relation = 'derived_from'")
    assert links == 2  # the tag that was already there is not linked: it was not published


def test_a_number_held_by_an_ended_tag_is_refused_in_the_preview(ready: World) -> None:
    from tl_mod_engineering.handlers.tags import RecordTag, handle_record_tag

    with open_uow(ready.db) as uow:
        made = handle_record_tag(
            uow, RecordTag(**BASE, number="47-FV-1001", class_code="ControlValve")
        )
    ready.move(made.stream_id, "delete")
    derived = ready.valid_derived(TAGS)
    plan = preview(ready, derived.id)
    assert plan.counts["invalid"] == 1 and not plan.can_publish
    assert "already used by a deleted tag" in plan.rows[0].problems[0]
    with pytest.raises(PublishRefusedError, match="47-FV-1001"):
        publish_tags(ready, derived)


def test_a_refusal_half_way_leaves_nothing_behind(ready: World) -> None:
    changed = {
        "columns": [
            {"column": "tag", "to": "number"},
            {
                "column": "type",
                "to": "class",
                "values": {"CV": "NoSuchClass", "HV": "ManualValve", "PSV": "SafetyValve"},
            },
        ],
        "target": "tags",
        "key_column": "tag",
    }
    ready.register_schema(semver="1.1.0", mapping=changed)
    derived = ready.valid_derived(TAGS)
    # the derived document was opened against 1.0.0; point it at 1.1.0 and check again
    from tl_mod_documents.derivation.derived import ValidateDerived, handle_validate_derived

    with open_uow(ready.db) as uow:
        handle_validate_derived(
            uow, ValidateDerived(**BASE, derived_id=derived.id, schema_semver="1.1.0")
        )
    ready.run_jobs()
    again = ready.derived_row(derived.id)
    assert again.state == "Valid" and again.schema_version == "1.1.0"
    before = ready.scalar("SELECT COUNT(*) FROM events")
    with pytest.raises(PublishRefusedError):
        publish_tags(ready, again)
    assert ready.scalar("SELECT COUNT(*) FROM events") == before and tags(ready) == []


def test_a_cell_the_mapping_cannot_translate_is_a_row_problem(ready: World) -> None:
    narrow = {
        "target": "tags",
        "key_column": "tag",
        "columns": [
            {"column": "tag", "to": "number"},
            {"column": "type", "to": "class", "values": {"CV": "ControlValve"}},
        ],
    }
    ready.register_schema(semver="1.1.0", mapping=narrow)
    derived = ready.valid_derived(TAGS)
    from tl_mod_documents.derivation.derived import ValidateDerived, handle_validate_derived

    with open_uow(ready.db) as uow:
        handle_validate_derived(
            uow, ValidateDerived(**BASE, derived_id=derived.id, schema_semver="1.1.0")
        )
    ready.run_jobs()
    plan = preview(ready, derived.id)
    assert plan.counts["invalid"] == 2
    assert "'HV' has no translation" in plan.rows[1].problems[0]


def test_without_the_provenance_pset_nothing_is_published(ready: World, tmp_path: Path) -> None:
    copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, copy)
    company = copy / "co.acme.engineering@3.2.0.yaml"
    text = company.read_text(encoding="utf-8")
    company.write_text(text[: text.index("  provenance:")], encoding="utf-8")
    derived = ready.valid_derived(TAGS)
    with use_provider(DirectorySchemaProvider(copy)):
        plan = preview(ready, derived.id)
        assert not plan.can_publish
        assert "no 'provenance' property set for engineering.Tag" in " ".join(plan.problems)
        with pytest.raises(PublishRefusedError, match="provenance"):
            publish_tags(ready, derived)
    assert tags(ready) == []


# --- compensation -------------------------------------------------------------------------


def test_the_compensation_preview_lists_every_record_and_link(ready: World) -> None:
    derived = ready.valid_derived(TAGS)
    publish_tags(ready, derived)
    with open_uow(ready.db, readonly=True) as uow:
        plan = preview_compensation(uow, BASE["scope"], derived.id)
    assert plan.can_compensate and plan.problems == []
    assert sorted(i.action for i in plan.items) == ["delete_tag"] * 3 + ["retract_link"] * 3
    assert plan.import_correlation_id == ready.derived_row(derived.id).published_correlation_id


def test_compensation_ends_what_the_import_made_and_leaves_the_history(ready: World) -> None:
    derived = ready.valid_derived(TAGS)
    publish_tags(ready, derived)
    published = ready.derived_row(derived.id)
    events_before = ready.scalar("SELECT COUNT(*) FROM events")
    with open_uow(ready.db) as uow:
        made = handle_compensate_publication(
            uow, CompensatePublication(**BASE, derived_id=derived.id, reason="wrong revision")
        )
    assert made.key == "ISD-001@A/instrument-index"
    after = ready.derived_row(derived.id)
    assert after.state == "Valid" and after.published_rev is None
    assert after.published_correlation_id is None
    assert [t["status"] for t in tags(ready)] == ["Deleted"] * 3
    links = ready.rows("SELECT status FROM cur_links WHERE relation = 'derived_from'")
    assert {r["status"] for r in links} == {"retracted"}
    # the original events are all still there, and the reversing ones are new and correlated
    assert ready.scalar("SELECT COUNT(*) FROM events") > events_before
    corr = published.published_correlation_id
    original = ready.scalar("SELECT COUNT(*) FROM events WHERE correlation_id = :c", c=corr)
    assert original > 9
    content = ready.contents(derived.id)[-1]
    assert content.published is False
    comp = ready.rows(
        "SELECT DISTINCT correlation_id FROM events "
        "WHERE event_type = 'DerivedDocument.PublicationCompensated'"
    )
    assert len(comp) == 1 and comp[0]["correlation_id"] != corr
    reversing = ready.scalar(
        "SELECT COUNT(*) FROM events WHERE correlation_id = :c", c=comp[0]["correlation_id"]
    )
    assert reversing >= 7  # 3 retractions, 3 deletions and the derived document's two
    with open_uow(ready.db) as uow, pytest.raises(CompensationRefusedError, match="no publication"):
        handle_compensate_publication(
            uow, CompensatePublication(**BASE, derived_id=derived.id, reason="again")
        )


def test_after_a_compensation_the_same_keys_cannot_be_published_again(ready: World) -> None:
    derived = ready.valid_derived(TAGS)
    publish_tags(ready, derived)
    with open_uow(ready.db) as uow:
        handle_compensate_publication(
            uow, CompensatePublication(**BASE, derived_id=derived.id, reason="redo")
        )
    again = ready.derived_row(derived.id)
    plan = preview(ready, derived.id)
    assert not plan.can_publish and plan.counts["invalid"] == 3
    assert "already used by a deleted tag" in plan.rows[0].problems[0]
    with pytest.raises(PublishRefusedError):
        publish_tags(ready, again)


def test_a_tag_that_was_replaced_blocks_the_whole_compensation(ready: World) -> None:
    derived = ready.valid_derived(TAGS)
    publish_tags(ready, derived)
    victim = tags(ready)[0]
    ready.move(victim["id"], "supersede")
    events_before = ready.scalar("SELECT COUNT(*) FROM events")
    with (
        open_uow(ready.db) as uow,
        pytest.raises(CompensationRefusedError, match="Superseded") as caught,
    ):
        handle_compensate_publication(
            uow, CompensatePublication(**BASE, derived_id=derived.id, reason="redo")
        )
    assert caught.value.problems
    assert ready.scalar("SELECT COUNT(*) FROM events") == events_before  # nothing was written
    assert ready.derived_row(derived.id).state == "Published"


# --- documents ----------------------------------------------------------------------------


def documents_derived(world: World) -> Any:
    world.register_schema(
        code="doc-register",
        json_schema=DOC_SCHEMA,
        mapping=DOC_MAPPING,
        target_kind="documents",
        key_column="number",
        title="Document register",
    )
    derived = world.open_derived("ISD-001", "A", "doc-register")
    data = b"number,title,discipline\nGA-100,General arrangement,PIP\nGA-101,Sections,PIP\n"
    world.upload_content(derived.id, data, name="register.csv")
    world.start_extraction(derived_id=derived.id)
    world.run_jobs()
    return world.derived_row(derived.id)


def test_documents_are_registered_with_provenance_and_rolled_back_by_voiding(ready: World) -> None:
    derived = documents_derived(ready)
    assert derived.state == "Valid"
    with open_uow(ready.db) as uow:
        handle_publish_derived_documents(
            uow,
            PublishDerivedDocuments(
                **BASE, derived_id=derived.id, expected_content_rev=derived.content_rev
            ),
        )
    docs = ready.rows(
        "SELECT r.key, r.psets_json, d.discipline FROM cur_core_record r "
        "JOIN cur_documents_document d ON d.id = r.id WHERE r.key LIKE 'GA-%' ORDER BY r.key"
    )
    assert [d["key"] for d in docs] == ["GA-100", "GA-101"]
    assert {d["discipline"] for d in docs} == {"PIP"}
    assert ready.scalar("SELECT COUNT(*) FROM cur_links WHERE relation = 'derived_from'") == 2
    assert "src.doc.ISD-001@A" in str(docs[0]["psets_json"])
    with open_uow(ready.db) as uow:
        handle_compensate_publication(
            uow, CompensatePublication(**BASE, derived_id=derived.id, reason="no")
        )
    states = ready.rows("SELECT r.status, r.voided FROM cur_core_record r WHERE r.key LIKE 'GA-%'")
    assert all(bool(s["voided"]) for s in states)
    assert rows is not None


def test_a_document_that_got_a_revision_blocks_its_compensation(ready: World) -> None:
    derived = documents_derived(ready)
    with open_uow(ready.db) as uow:
        handle_publish_derived_documents(
            uow,
            PublishDerivedDocuments(
                **BASE, derived_id=derived.id, expected_content_rev=derived.content_rev
            ),
        )
    ready.create_revision("GA-100")
    with open_uow(ready.db) as uow, pytest.raises(CompensationRefusedError, match="revision"):
        handle_compensate_publication(
            uow, CompensatePublication(**BASE, derived_id=derived.id, reason="no")
        )


# --- compensation trusts what the publication wrote down, not a correlation id ------------------


def inject(world: World, correlation: str) -> dict[str, str]:
    """What a client who knows the publication's correlation id can make: events that carry it."""
    from tl_core.services.commands import CreateRecord
    from tl_core.services.links import AddLink, handle_add_link
    from tl_core.services.records import handle_create_record
    from tl_mod_documents.handlers.documents import RegisterDocument, handle_register_document

    with open_uow(world.db) as uow:
        doc = handle_register_document(
            uow, RegisterDocument(**BASE, correlation_id=correlation, number="INJ-001", title="x")
        )
        other = handle_create_record(
            uow,
            CreateRecord(
                **BASE,
                correlation_id=correlation,
                record_type="core.Record",
                title="not a tag",
                key="INJ-REC-1",
            ),
        )
        link = handle_add_link(
            uow,
            AddLink(
                **BASE,
                correlation_id=correlation,
                from_id=other.stream_id,
                to_id=doc.stream_id,
                relation="references",
            ),
        )
    return {"document": doc.stream_id, "record": other.stream_id, "link": link.stream_id}


def test_the_publication_has_a_server_made_correlation_id_and_records_what_it_made(
    ready: World,
) -> None:
    import json

    derived = ready.valid_derived(TAGS)
    publish_tags(ready, derived)
    after = ready.derived_row(derived.id)
    assert after.published_correlation_id is not None
    assert after.published_correlation_id.startswith("derive:")
    event = ready.rows("SELECT payload FROM events WHERE event_type = 'DerivedDocument.Published'")[
        0
    ]["payload"]
    payload = json.loads(event) if isinstance(event, str) else event
    created = {t["id"] for t in tags(ready)}
    assert set(payload["record_ids"]) == created and len(payload["record_ids"]) == 3
    linked = {
        r["link_id"]
        for r in ready.rows("SELECT link_id FROM cur_links WHERE relation = 'derived_from'")
    }
    assert set(payload["link_ids"]) == linked and payload["created_count"] == 3


def test_events_a_client_gave_the_publications_correlation_id_are_not_compensated(
    ready: World,
) -> None:
    derived = ready.valid_derived(TAGS)
    publish_tags(ready, derived)
    corr = ready.derived_row(derived.id).published_correlation_id
    assert corr is not None
    injected = inject(ready, corr)
    with open_uow(ready.db, readonly=True) as uow:
        plan = preview_compensation(uow, BASE["scope"], derived.id)
    assert plan.can_compensate and plan.problems == []  # the foreign record does not block it
    assert sorted(i.action for i in plan.items) == ["delete_tag"] * 3 + ["retract_link"] * 3
    assert injected["document"] not in {i.record_id for i in plan.items}
    with open_uow(ready.db) as uow:
        handle_compensate_publication(
            uow, CompensatePublication(**BASE, derived_id=derived.id, reason="redo")
        )
    assert [t["status"] for t in tags(ready)] == ["Deleted"] * 3
    document = ready.rows(
        "SELECT voided, status FROM cur_core_record WHERE id = :i", i=injected["document"]
    )
    assert document[0]["voided"] in (False, 0)  # the injected document is untouched
    record = ready.rows("SELECT voided FROM cur_core_record WHERE id = :i", i=injected["record"])
    assert record[0]["voided"] in (False, 0)
    link = ready.rows("SELECT status FROM cur_links WHERE link_id = :i", i=injected["link"])
    assert link[0]["status"] == "active"  # the injected link is not retracted


def test_a_recorded_record_that_is_gone_blocks_the_compensation(ready: World) -> None:
    derived = ready.valid_derived(TAGS)
    publish_tags(ready, derived)
    victim = tags(ready)[0]["id"]
    with open_uow(ready.db) as uow:
        uow.conn().execute(text("DELETE FROM cur_core_record WHERE id = :i"), {"i": victim})
    with open_uow(ready.db, readonly=True) as uow:
        plan = preview_compensation(uow, BASE["scope"], derived.id)
    assert not plan.can_compensate and any("not there" in p for p in plan.problems)
