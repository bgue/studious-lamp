"""The reads of the pipeline: schemas, derived documents, jobs, rows, reports, diffs, previews."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from docworld import BASE, World
from tl_adapters.db import open_uow
from tl_core.derivation.registry import use_extractors
from tl_core.derivation.testing import make_extractors
from tl_mod_documents.derivation import views
from tl_mod_documents.derivation.store import use_files
from tl_mod_documents.errors import (
    DerivedNotFoundError,
    DerivedStateError,
    JobNotFoundError,
    SchemaNotFoundError,
)
from tl_mod_documents.testing import index_csv

SCOPE = BASE["scope"]
ONE = [("47-FV-1001", "Feed", "CV", "4"), ("47-FV-1002", "Return", "HV", "6")]
TWO = [*ONE[:1], ("47-FV-1002", "Return", "HV", "8"), ("47-HV-2001", "Vent", "PSV", "2")]


@pytest.fixture(autouse=True)
def extractors(world: World) -> Iterator[None]:
    with use_extractors(make_extractors()), use_files(world.files):
        yield


@pytest.fixture
def ready(world: World) -> World:
    world.register("ISD-001", doc_type="IDX")
    world.create_revision("ISD-001")
    world.attach("ISD-001", "A")
    world.register_schema()
    return world


def test_schemas_list_by_scope_and_resolve_by_code_or_version(ready: World) -> None:
    ready.register_schema(semver="1.1.0", title="Instrument index v1.1")
    with open_uow(ready.db, readonly=True) as uow:
        listed = views.schema_summaries(uow.conn(), SCOPE)
        assert [(s.code, s.semver) for s in listed] == [
            ("instrument-index", "1.0.0"),
            ("instrument-index", "1.1.0"),
        ]
        assert views.schema_view(uow.conn(), SCOPE, "instrument-index").semver == "1.1.0"
        old = views.schema_view(uow.conn(), SCOPE, "instrument-index@1.0.0")
        assert old.json_schema["required"] == ["tag", "type"] and old.mapping is not None
        with pytest.raises(SchemaNotFoundError):
            views.schema_view(uow.conn(), SCOPE, "nope")


def test_a_derived_document_reads_with_its_passes_rows_report_and_job(ready: World) -> None:
    derived = ready.valid_derived(ONE)
    with open_uow(ready.db, readonly=True) as uow:
        by_key = views.derived_view(uow.conn(), SCOPE, derived.key)
        assert by_key.id == derived.id == views.derived_view(uow.conn(), SCOPE, derived.id).id
        assert by_key.state == "Valid" and by_key.content_rev == 1 and by_key.row_count == 2
        assert [c.validation_status for c in by_key.contents] == ["valid"]
        assert by_key.active_job is None
        page = views.derived_rows(uow, SCOPE, derived.key, offset=1, limit=5)
        assert (page.total, page.offset, len(page.rows)) == (2, 1, 1)
        assert page.columns == ["tag", "service", "type", "size_in"]
        assert page.rows[0]["tag"] == "47-FV-1002"
        report = views.derived_report(uow, SCOPE, derived.key)
        assert report.status == "valid" and report.error_count == 0
        assert views.derived_summaries(uow.conn(), SCOPE, state="Valid")[0].id == derived.id
        assert views.derived_summaries(uow.conn(), SCOPE, document="NOPE") == []
        jobs = views.job_views(uow.conn(), SCOPE, derived=derived.key)
        assert [j.kind for j in jobs] == ["extract"] and jobs[0].state == "succeeded"
        assert views.job_view(uow.conn(), SCOPE, jobs[0].id).key == jobs[0].key
        with pytest.raises(JobNotFoundError):
            views.job_view(uow.conn(), SCOPE, "01NOSUCH")
        with pytest.raises(DerivedNotFoundError):
            views.derived_view(uow.conn(), SCOPE, "ISD-001@Z/none")


def test_reading_rows_before_any_pass_says_so(ready: World) -> None:
    derived = ready.open_derived("ISD-001", "A")
    with open_uow(ready.db, readonly=True) as uow:
        assert views.derived_view(uow.conn(), SCOPE, derived.id).state == "Pending"
        with pytest.raises(DerivedStateError, match="no extracted data"):
            views.derived_rows(uow, SCOPE, derived.id)
        with pytest.raises(DerivedStateError):
            views.derived_report(uow, SCOPE, derived.id)


def test_the_diff_compares_two_passes_by_the_key_column(ready: World) -> None:
    derived = ready.valid_derived(ONE)
    ready.upload_content(derived.id, index_csv(TWO), name="two.csv")
    ready.start_extraction(derived_id=derived.id)
    ready.run_jobs()
    with open_uow(ready.db, readonly=True) as uow:
        diff = views.derived_diff(uow, SCOPE, derived.id)
        assert diff.added == ["47-HV-2001"] and diff.removed == []
        assert [c.key for c in diff.changed] == ["47-FV-1002"]
        assert diff.unchanged_count == 1
        with pytest.raises(DerivedStateError, match="no earlier data"):
            views.derived_diff(uow, SCOPE, derived.id, content_rev=1)
        with pytest.raises(DerivedStateError, match="no earlier data"):
            views.derived_diff(uow, SCOPE, derived.id, against="previous_revision")
        with pytest.raises(DerivedStateError, match="cannot compare"):
            views.derived_diff(uow, SCOPE, derived.id, against="sideways")


def test_validate_stored_checks_rows_against_another_schema_and_stores_nothing(
    ready: World,
) -> None:
    derived = ready.valid_derived(ONE)
    ready.register_schema(
        semver="2.0.0",
        mapping=None,
        target_kind=None,
        json_schema={
            "type": "object",
            "required": ["tag"],
            "properties": {"tag": {"type": "string", "pattern": "^ZZ"}},
        },
    )
    before = len(ready.contents(derived.id))
    with open_uow(ready.db, readonly=True) as uow:
        own = views.validate_stored(uow, SCOPE, derived.id)
        other = views.validate_stored(uow, SCOPE, derived.id, schema_ref="instrument-index@2.0.0")
    assert own.status == "valid" and own.schema_version == "1.0.0"
    assert other.status == "invalid" and other.schema_version == "2.0.0"
    assert other.error_count == 2
    assert len(ready.contents(derived.id)) == before
    assert ready.derived_row(derived.id).state == "Valid"


def test_previews_read_the_plan_and_the_compensation_without_writing(ready: World) -> None:
    derived = ready.valid_derived(ONE)
    with open_uow(ready.db, readonly=True) as uow:
        plan = views.publish_preview(uow, SCOPE, derived.key)
        assert plan.derived_id == derived.id and plan.target == "tags"
        assert plan.counts["create"] == 2 and plan.can_publish
        nothing = views.compensation_preview(uow, SCOPE, derived.key)
        assert not nothing.can_compensate and "no publication to roll back" in nothing.problems[0]


def test_paging_through_one_pass_parses_it_once_and_a_different_pass_again(
    ready: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tl_core.derivation.types import ExtractionResult
    from tl_mod_documents.derivation import store

    derived = ready.valid_derived(ONE)
    store.forget_parsed()
    parses: list[int] = []
    real = ExtractionResult.model_validate_json

    def counting(*args: object, **kwargs: object) -> ExtractionResult:
        parses.append(1)
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ExtractionResult, "model_validate_json", counting)
    with open_uow(ready.db, readonly=True) as uow:
        first = views.derived_rows(uow, SCOPE, derived.key, offset=0, limit=1)
        second = views.derived_rows(uow, SCOPE, derived.key, offset=1, limit=1)
        views.derived_report(uow, SCOPE, derived.key)
        views.derived_report(uow, SCOPE, derived.key)
    assert (len(parses), first.rows[0]["tag"], second.rows[0]["tag"]) == (
        1,
        "47-FV-1001",
        "47-FV-1002",
    )
    # a later pass is another file: parsed once more
    ready.upload_content(derived.id, index_csv(TWO), name="two.csv")
    ready.start_extraction(derived_id=derived.id)
    ready.run_jobs()  # (the worker parses the extractor's answer once: not a read)
    before = len(parses)
    with open_uow(ready.db, readonly=True) as uow:
        assert views.derived_rows(uow, SCOPE, derived.key).total == 3
        views.derived_rows(uow, SCOPE, derived.key)
    assert len(parses) == before + 1


def test_the_cache_holds_a_few_entries_and_a_cached_file_is_still_checked(
    ready: World,
) -> None:
    from tl_mod_documents.derivation import store

    derived = ready.valid_derived(ONE)
    store.forget_parsed()
    with open_uow(ready.db, readonly=True) as uow:
        views.derived_rows(uow, SCOPE, derived.key)
    assert len(store._parsed) == 1  # pyright: ignore[reportPrivateUsage]
    assert store.CACHE_ENTRIES == 4

    class Refusing:
        def open_file(self, *args: object, **kwargs: object) -> None:
            raise DerivedStateError("the file was rejected")

    with (
        use_files(Refusing()),  # type: ignore[arg-type]
        open_uow(ready.db, readonly=True) as uow,
        pytest.raises(DerivedStateError, match="rejected"),
    ):
        views.derived_rows(uow, SCOPE, derived.key)  # cached, and still refused


def test_the_cache_is_bounded_by_bytes_as_well_as_by_count(
    ready: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tl_mod_documents.derivation import store

    derived = ready.valid_derived(ONE)
    store.forget_parsed()
    monkeypatch.setattr(store, "CACHE_BYTES", 10)  # smaller than any stored result
    with open_uow(ready.db, readonly=True) as uow:
        rows = views.derived_rows(uow, SCOPE, derived.key)
    assert rows is not None
    assert len(store._parsed) == 0  # pyright: ignore[reportPrivateUsage]  # parsed, not kept
