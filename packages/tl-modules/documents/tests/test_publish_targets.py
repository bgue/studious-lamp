"""Publish targets found by entry point (W0-B2): the registry, its refusals, the built-ins."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from docworld import BASE, World
from tl_adapters.db import open_uow
from tl_core.derivation.registry import use_extractors
from tl_core.derivation.testing import make_extractors
from tl_core.modules import ModuleLoadError
from tl_mod_documents.derivation.publish import (
    PublishDerivedDocuments,
    PublishDerivedTags,
    documents_target,
    handle_publish_derived_documents,
    handle_publish_derived_tags,
    preview_publication,
    tags_target,
)
from tl_mod_documents.derivation.publish_targets import (
    PUBLISH_ENTRY_POINT,
    PublishTarget,
    PublishTargetLoadError,
    load_publish_targets,
    publish_target_for,
    publish_targets,
    use_publish_targets,
)
from tl_mod_documents.derivation.store import use_files
from tl_mod_documents.errors import PublishRefusedError

TAGS = [("47-FV-1001", "Feed", "CV", "4"), ("47-HV-1002", "Return", "HV", "6")]
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


class Target:
    """A publish target that plans nothing and creates nothing."""

    module = "test"
    record_type = "test.Thing"

    def __init__(self, name: str) -> None:
        self.name = name

    def plan_rows(
        self, conn: Any, scope: str, mapped: list[Any]
    ) -> tuple[list[Any], list[Any], dict[str, int]]:
        return [], [], {"create": 0, "exists": 0, "differs": 0, "invalid": 0}

    def create(
        self, uow: Any, base: dict[str, Any], built: Any, provenance: dict[str, str]
    ) -> list[str]:
        return []


class Entry:
    """The members of an ``EntryPoint`` that ``load_publish_targets`` uses."""

    def __init__(self, name: str, factory: Callable[[], Any], value: str = "x:y") -> None:
        self.name = name
        self.value = value
        self._factory = factory

    def load(self) -> Callable[[], Any]:
        return self._factory


def entry(name: str, target_name: str | None = None) -> Entry:
    return Entry(name, lambda: Target(name if target_name is None else target_name))


def load(*entries: Entry) -> dict[str, PublishTarget]:
    return load_publish_targets(entries)  # type: ignore[arg-type]


# --- the registry -------------------------------------------------------------------------------


def test_the_group_name_is_the_documented_one() -> None:
    assert PUBLISH_ENTRY_POINT == "throughline.publish_targets"


def test_the_installed_targets_are_tags_and_documents_in_name_order() -> None:
    found = publish_targets()
    # the workspace also installs other modules' targets (materials registers ``mto``)
    assert list(found) == sorted(found)
    assert {"documents", "tags"} <= set(found)
    assert (found["tags"].module, found["tags"].record_type) == ("documents", "engineering.Tag")
    assert (found["documents"].module, found["documents"].record_type) == (
        "documents",
        "documents.Document",
    )
    assert all(isinstance(t, PublishTarget) for t in found.values())
    assert list(load_publish_targets()) == list(found)


def test_the_two_factories_return_targets_of_their_own_name() -> None:
    assert tags_target().name == "tags" and documents_target().name == "documents"


def test_a_plugin_is_found_and_the_result_is_sorted() -> None:
    assert list(load(entry("zeta"), entry("alpha"))) == ["alpha", "zeta"]
    assert load() == {}


def test_a_duplicate_name_is_refused() -> None:
    with pytest.raises(PublishTargetLoadError, match="declared twice") as caught:
        load(entry("same"), Entry("same", lambda: Target("same"), value="other:y"))
    assert "'same'" in str(caught.value) and PUBLISH_ENTRY_POINT in str(caught.value)


def test_the_load_error_is_a_module_load_error() -> None:
    assert issubclass(PublishTargetLoadError, ModuleLoadError)


def test_a_plugin_that_fails_to_load_is_refused_with_the_exception_type_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken() -> Any:
        raise RuntimeError("secret internals hunter2")

    with caplog.at_level(logging.WARNING), pytest.raises(PublishTargetLoadError) as caught:
        load(Entry("broken", broken))
    assert "'broken'" in str(caught.value) and "RuntimeError" in str(caught.value)
    assert "hunter2" not in str(caught.value)
    assert "hunter2" in caplog.text  # the full text goes to the log


@pytest.mark.parametrize("produced", [None, "text", 3, object()])
def test_a_plugin_that_returns_no_target_is_refused(produced: Any) -> None:
    with pytest.raises(PublishTargetLoadError, match="must return a PublishTarget"):
        load(Entry("odd", lambda: produced))


def test_a_target_named_differently_from_its_entry_point_is_refused() -> None:
    with pytest.raises(PublishTargetLoadError, match="of the same name"):
        load(entry("one", "other"))


@pytest.mark.parametrize("bad", ["", "Upper", "1st", "has-dash", "has space", "_x"])
def test_a_bad_entry_point_name_is_refused_before_it_is_loaded(bad: str) -> None:
    def never() -> Any:
        raise AssertionError("loaded a misnamed plugin")

    with pytest.raises(PublishTargetLoadError, match="must match"):
        load(Entry(bad, never))


def test_an_unknown_target_is_a_publish_refusal_that_lists_the_known_ones() -> None:
    with pytest.raises(PublishRefusedError) as caught:
        publish_target_for("nope")
    assert "'nope'" in str(caught.value)
    assert "known: documents, " in str(caught.value) and "tags" in str(caught.value)


def test_with_none_installed_the_refusal_says_so() -> None:
    with use_publish_targets({}), pytest.raises(PublishRefusedError, match="none installed"):
        publish_target_for("tags")


def test_use_publish_targets_replaces_the_registry_for_the_block_only() -> None:
    mine = Target("mine")
    with use_publish_targets({"mine": mine}):
        assert publish_target_for("mine") is mine
        assert list(publish_targets()) == ["mine"]
        with pytest.raises(PublishRefusedError):
            publish_target_for("tags")
    assert {"documents", "tags"} <= set(publish_targets())
    assert "mine" not in publish_targets()
    assert publish_target_for("tags").name == "tags"


# --- the built-ins in the pipeline --------------------------------------------------------------


class Spy:
    """Wraps a real target and records which methods the pipeline called."""

    def __init__(self, inner: PublishTarget, calls: list[str]) -> None:
        self.inner = inner
        self.calls = calls
        self.name, self.module, self.record_type = inner.name, inner.module, inner.record_type

    def plan_rows(self, conn: Any, scope: str, mapped: list[Any]) -> Any:
        self.calls.append(f"{self.name}.plan_rows")
        return self.inner.plan_rows(conn, scope, mapped)

    def create(self, uow: Any, base: dict[str, Any], built: Any, provenance: dict[str, str]) -> Any:
        self.calls.append(f"{self.name}.create")
        return self.inner.create(uow, base, built, provenance)


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


def test_publishing_tags_goes_through_the_registered_tags_target_and_creates_the_tags(
    ready: World,
) -> None:
    derived = ready.valid_derived(TAGS)
    calls: list[str] = []
    with use_publish_targets({"tags": Spy(tags_target(), calls), "documents": documents_target()}):
        with open_uow(ready.db) as uow:
            handle_publish_derived_tags(
                uow,
                PublishDerivedTags(
                    **BASE, derived_id=derived.id, expected_content_rev=derived.content_rev
                ),
            )
    assert "tags.plan_rows" in calls and calls.count("tags.create") == 1
    keys = ready.rows(
        "SELECT r.key, t.origin FROM cur_core_record r JOIN cur_engineering_tag t ON t.id = r.id "
        "ORDER BY r.key"
    )
    assert [(k["key"], k["origin"]) for k in keys if k["key"] in {t[0] for t in TAGS}] == [
        ("47-FV-1001", "import"),
        ("47-HV-1002", "import"),
    ]


def test_publishing_documents_goes_through_the_registered_documents_target(ready: World) -> None:
    derived = documents_derived(ready)
    calls: list[str] = []
    with use_publish_targets({"tags": tags_target(), "documents": Spy(documents_target(), calls)}):
        with open_uow(ready.db) as uow:
            handle_publish_derived_documents(
                uow,
                PublishDerivedDocuments(
                    **BASE, derived_id=derived.id, expected_content_rev=derived.content_rev
                ),
            )
    assert calls.count("documents.create") == 1 and "documents.plan_rows" in calls
    found = ready.rows("SELECT r.key FROM cur_core_record r WHERE r.key LIKE 'GA-%' ORDER BY r.key")
    assert [r["key"] for r in found] == ["GA-100", "GA-101"]


def test_an_unregistered_target_is_refused_before_anything_is_read_or_written(
    ready: World,
) -> None:
    derived = ready.valid_derived(TAGS)
    events = ready.scalar("SELECT COUNT(*) FROM events")
    with use_publish_targets({"documents": documents_target()}):  # no `tags`
        with pytest.raises(PublishRefusedError, match="no publish target 'tags'"):
            with open_uow(ready.db) as uow:
                handle_publish_derived_tags(
                    uow,
                    PublishDerivedTags(
                        **BASE, derived_id=derived.id, expected_content_rev=derived.content_rev
                    ),
                )
    assert ready.scalar("SELECT COUNT(*) FROM events") == events
    assert ready.derived_row(derived.id).state == "Valid"


def test_the_preview_of_a_built_in_target_is_unchanged(ready: World) -> None:
    derived = ready.valid_derived(TAGS)
    with open_uow(ready.db, readonly=True) as uow:
        plan = preview_publication(uow, BASE["scope"], derived.id)
    assert plan.target == "tags" and plan.can_publish
    assert plan.counts == {"create": 2, "exists": 0, "differs": 0, "invalid": 0}
