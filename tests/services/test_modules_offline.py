"""Module-load checks for the offline classes (OC-S2): ``check_offline`` and discovery.

Stand-in specs carry the module name of a real module, so the record types resolve in the
generated offline table: ``cost.CostCode`` is ``none``, ``engineering.Tag`` is ``full``,
``documents.Document`` is ``draft_only``.
"""

from __future__ import annotations

from typing import Any

import pytest
from tl_core import modules
from tl_core.modules import ModuleLoadError, ModuleSpec, check_offline, load_modules


def stand_in(**kw: Any) -> ModuleSpec:
    return ModuleSpec(projectors=lambda: [], **kw)  # type: ignore[arg-type]


def documents(
    words: dict[str, str] | None = None, drafts: frozenset[str] | None = None
) -> ModuleSpec:
    return stand_in(
        name="documents",
        record_types=frozenset({"documents.Document"}),
        command_words=words or {},
        offline_drafts={"documents.Document": drafts} if drafts is not None else {},
    )


def test_a_record_type_with_no_offline_class_is_refused() -> None:
    spec = stand_in(name="zzz", record_types=frozenset({"zzz.Thing"}))
    with pytest.raises(ModuleLoadError) as caught:
        check_offline(spec)
    text = str(caught.value)
    assert "zzz" in text and "'zzz.Thing'" in text and "no offline class" in text


def test_the_undeclared_type_is_named_even_when_others_are_declared() -> None:
    spec = stand_in(name="cost", record_types=frozenset({"cost.CostCode", "cost.Ghost"}))
    with pytest.raises(ModuleLoadError, match="cost.Ghost"):
        check_offline(spec)


def test_a_drafting_entry_on_a_full_type_is_refused() -> None:
    spec = stand_in(
        name="engineering",
        record_types=frozenset({"engineering.Tag"}),
        command_words={"CreateTag": "user"},
        offline_drafts={"engineering.Tag": frozenset({"CreateTag"})},
    )
    with pytest.raises(ModuleLoadError) as caught:
        check_offline(spec)
    assert "engineering.Tag" in str(caught.value) and "'full'" in str(caught.value)
    assert "'draft_only'" in str(caught.value)


def test_a_drafting_entry_on_a_none_type_is_refused() -> None:
    spec = stand_in(
        name="cost",
        record_types=frozenset({"cost.CostCode"}),
        command_words={"X": "user"},
        offline_drafts={"cost.CostCode": frozenset({"X"})},
    )
    with pytest.raises(ModuleLoadError) as caught:
        check_offline(spec)
    assert "cost.CostCode" in str(caught.value) and "'none'" in str(caught.value)


@pytest.mark.parametrize("word", ["controller", "admin", "company"])
def test_a_drafting_command_with_a_central_word_is_refused(word: str) -> None:
    spec = documents({"RegisterDocument": word}, frozenset({"RegisterDocument"}))
    with pytest.raises(ModuleLoadError) as caught:
        check_offline(spec)
    text = str(caught.value)
    assert "documents" in text and "RegisterDocument" in text and repr(word) in text
    assert "'user'" in text


def test_a_drafting_command_missing_from_command_words_is_refused() -> None:
    spec = documents({}, frozenset({"RegisterDocument"}))
    with pytest.raises(ModuleLoadError) as caught:
        check_offline(spec)
    assert "RegisterDocument" in str(caught.value) and "command_words" in str(caught.value)


def test_a_key_the_module_does_not_own_is_refused() -> None:
    spec = stand_in(
        name="documents",
        record_types=frozenset({"documents.Document"}),
        command_words={"X": "user"},
        offline_drafts={"cost.CostCode": frozenset({"X"})},
    )
    with pytest.raises(ModuleLoadError) as caught:
        check_offline(spec)
    assert "cost.CostCode" in str(caught.value) and "not one of its record types" in str(
        caught.value
    )


def test_a_consistent_spec_passes() -> None:
    check_offline(documents({"RegisterDocument": "user"}, frozenset({"RegisterDocument"})))
    check_offline(documents({}, frozenset()))
    check_offline(documents())
    check_offline(stand_in(name="cost", record_types=frozenset({"cost.CostCode"})))


def test_the_real_modules_load_and_declare_only_draft_only_types() -> None:
    specs = load_modules()
    assert len(specs) == 9
    from tl_schema.generated.offline_classes import OFFLINE_CLASSES

    for spec in specs:
        check_offline(spec)
        for record_type in spec.offline_drafts:
            assert OFFLINE_CLASSES[record_type] == "draft_only"
        assert all(rt in OFFLINE_CLASSES for rt in spec.record_types)


def test_discovery_runs_the_check_on_every_module(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    real = modules.check_offline

    def spy(spec: ModuleSpec) -> None:
        seen.append(spec.name)
        real(spec)

    monkeypatch.setattr(modules, "check_offline", spy)
    monkeypatch.setattr(modules, "_loaded", None)
    monkeypatch.setattr(modules, "_override", None)
    assert len(modules.load_modules()) == 9
    assert sorted(seen) == [
        "awp",
        "correspondence",
        "cost",
        "documents",
        "engineering",
        "legacy",
        "materials",
        "schedule",
        "schemareg",
    ]
