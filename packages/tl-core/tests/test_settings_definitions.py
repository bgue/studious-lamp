"""The setting definitions: the platform file, its agreement with the LinkML class, extensions."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal, get_args

import jsonschema
import pytest
import yaml
from tl_core.services.errors import UnknownSettingError
from tl_core.settings import registry as defs
from tl_core.settings import types as runtime
from tl_core.settings.registry import (
    SettingDefinitionError,
    get_definition,
    parse_definitions,
    register_definitions,
    unregister_definitions,
    use_definitions,
)
from tl_schema import generated
from tl_schema.generated import models as gen

REPO = Path(__file__).resolve().parents[3]
PLATFORM = REPO / "schema" / "settings" / "platform.yaml"
CORE_JSON_SCHEMA = Path(generated.__file__).parent / "json_schema" / "core.schema.json"


@pytest.fixture
def clean() -> Iterator[None]:
    """Run with the platform file loaded and no extension keys, restoring them afterwards."""
    with use_definitions(defs.load_definitions(PLATFORM)):
        yield


def entry(key: str, **extra: Any) -> dict[str, Any]:
    return {
        "key": key,
        "type": "bool",
        "default": True,
        "description": "d",
        "scopes": ["platform", "project"],
        "since": "1.0.0",
        **extra,
    }


def doc(*entries: dict[str, Any]) -> str:
    return yaml.safe_dump({"settings": list(entries)})


# --- the platform file ---------------------------------------------------------------------------


def test_the_platform_file_defines_the_keys_of_decision_d2() -> None:
    keys = {d.key for d in defs.load_definitions(PLATFORM)}
    assert keys == {
        "feed.reactions.enabled",
        "feed.signal_tags",
        "webhooks.retry.max_hours",
        "webhooks.egress.allowlist",
        "lake.sync.interval",
        "ai.agents.default_mode",
        "ai.agents.daily_proposals",
        "project.mode",
        "ui.tui.keymap",
        "ui.tui.graphics",
    }


def test_every_platform_default_is_valid_and_no_key_is_secret() -> None:
    loaded = defs.load_definitions(PLATFORM)  # check_definition runs inside
    assert all(d.sensitivity == "normal" and d.owner == "platform" for d in loaded)
    assert all("platform" in d.scopes for d in loaded)
    user_keys = [d.key for d in loaded if "user" in d.scopes]
    assert user_keys and all(k.startswith("ui.") for k in user_keys)


def test_the_dangerous_and_advanced_keys_are_marked() -> None:
    by_key = {d.key: d for d in defs.load_definitions(PLATFORM)}
    assert by_key["webhooks.egress.allowlist"].risk == "dangerous"
    assert by_key["ai.agents.default_mode"].risk == "advanced"
    assert by_key["ai.agents.default_mode"].validation is not None
    assert by_key["ai.agents.default_mode"].validation.choices == ["propose"]  # write is a gate
    assert by_key["feed.reactions.enabled"].risk == "normal"


# --- D1: the pydantic model and the LinkML class agree ------------------------------------------


def literal_values(annotation: Any) -> set[str]:
    return set(get_args(annotation))


def test_the_runtime_model_and_the_generated_class_have_the_same_fields() -> None:
    ours, theirs = runtime.SettingDefinition, gen.SettingDefinition
    assert set(ours.model_fields) == set(theirs.model_fields)
    required_ours = {n for n, f in ours.model_fields.items() if f.is_required()}
    required_theirs = {n for n, f in theirs.model_fields.items() if f.is_required()}
    assert required_ours == required_theirs
    assert set(runtime.SettingValidation.model_fields) == set(gen.SettingValidation.model_fields)


def test_the_enumerations_agree() -> None:
    pairs: list[tuple[Any, Any]] = [
        (runtime.SettingType, gen.SettingType),
        (runtime.SettingScope, gen.SettingScope),
        (runtime.SettingEffect, gen.SettingEffect),
        (runtime.SettingSensitivity, gen.SettingSensitivity),
        (runtime.SettingRisk, gen.SettingRisk),
    ]
    for literal, enum in pairs:
        assert literal_values(literal) == {member.value for member in enum}, enum.__name__


def test_the_defaults_agree() -> None:
    ours, theirs = runtime.SettingDefinition.model_fields, gen.SettingDefinition.model_fields
    for name in ("lockable", "effect", "sensitivity", "risk", "owner"):
        left = ours[name].default
        right = theirs[name].default
        assert left == getattr(right, "value", right), name


def test_the_generated_json_schema_accepts_every_platform_entry() -> None:
    core = json.loads(CORE_JSON_SCHEMA.read_text(encoding="utf-8"))
    # the generator renders LinkML `Any` without arrays; a JSON column holds any JSON value
    schema = {"$ref": "#/$defs/SettingDefinition", "$defs": {**core["$defs"], "Any": {}}}
    validator = jsonschema.Draft202012Validator(schema)
    document = yaml.safe_load(PLATFORM.read_text(encoding="utf-8"))
    for entry_ in document["settings"]:
        errors = [e.message for e in validator.iter_errors(entry_)]
        assert errors == [], (entry_["key"], errors)
    bad = {**document["settings"][0], "type": "float"}
    assert not validator.is_valid(bad)
    assert not validator.is_valid({**document["settings"][0], "key": "NotDotted"})


# --- parsing -------------------------------------------------------------------------------------


def test_parse_fills_the_owner_and_keeps_order() -> None:
    found = parse_definitions(doc(entry("a.b"), entry("a.c")), owner="co.acme.Thing")
    assert [d.key for d in found] == ["a.b", "a.c"]
    assert {d.owner for d in found} == {"co.acme.Thing"}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("settings: [", "invalid YAML"),
        ("- a", "expected a mapping"),
        ("settings: 3", "expected a mapping"),
        (doc(entry("a.b", surprise=1)), "unknown fields"),
        (doc(entry("NotDotted")), "key"),
        (doc(entry("a.b"), entry("a.b")), "defined twice"),
        (doc(entry("a.b", type="enum")), "enum needs"),
        (doc(entry("a.b", default="yes")), "default is not valid"),
        (doc(entry("a.b", scopes=["company"])), "platform"),
        (doc(entry("a.b", scopes=["nowhere"])), "scopes"),
    ],
)
def test_a_bad_definition_file_names_its_source(text: str, message: str) -> None:
    with pytest.raises(SettingDefinitionError, match=message) as caught:
        parse_definitions(text, source="my.yaml")
    assert str(caught.value).startswith("my.yaml")


def test_a_missing_file_is_a_definition_error(tmp_path: Path) -> None:
    with pytest.raises(SettingDefinitionError, match="cannot read"):
        defs.load_definitions(tmp_path / "nope.yaml")


# --- the registry and extension types ------------------------------------------------------------


def test_an_unknown_key_is_refused(clean: None) -> None:
    with pytest.raises(UnknownSettingError, match="no.such"):
        get_definition("no.such")


def test_extension_keys_carry_the_namespace_of_their_type(clean: None) -> None:
    mine = parse_definitions(doc(entry("co.acme.lift.max_load")), owner="co.acme.LiftPlan")
    register_definitions(mine, owner="co.acme.LiftPlan")
    assert get_definition("co.acme.lift.max_load").owner == "co.acme.LiftPlan"
    assert "co.acme.lift.max_load" in defs.definitions()
    stray = parse_definitions(doc(entry("other.key")), owner="co.acme.LiftPlan")
    with pytest.raises(SettingDefinitionError, match="must start with 'co.acme.'"):
        register_definitions(stray, owner="co.acme.LiftPlan")


def test_an_extension_cannot_shadow_a_platform_key_or_another_type(clean: None) -> None:
    shadow = parse_definitions(doc(entry("feed.reactions.enabled")), owner="feed.reactions.Type")
    with pytest.raises(SettingDefinitionError, match="already defined"):
        register_definitions(shadow, owner="feed.reactions.Type")
    first = parse_definitions(doc(entry("co.acme.a")), owner="co.acme.One")
    register_definitions(first, owner="co.acme.One")
    second = parse_definitions(doc(entry("co.acme.a")), owner="co.acme.Two")
    with pytest.raises(SettingDefinitionError, match="already defined"):
        register_definitions(second, owner="co.acme.Two")
    with pytest.raises(SettingDefinitionError, match="platform"):
        register_definitions(first, owner="platform")
    with pytest.raises(SettingDefinitionError, match="namespace"):
        register_definitions(first, owner="NoDot")


def test_registering_an_owner_again_replaces_its_keys_and_nothing_is_kept_on_failure(
    clean: None,
) -> None:
    v1 = parse_definitions(doc(entry("co.acme.a"), entry("co.acme.b")), owner="co.acme.One")
    register_definitions(v1, owner="co.acme.One")
    v2 = parse_definitions(doc(entry("co.acme.a")), owner="co.acme.One")
    register_definitions(v2, owner="co.acme.One")
    assert "co.acme.b" not in defs.definitions() and "co.acme.a" in defs.definitions()
    clash = parse_definitions(
        doc(entry("co.acme.c"), entry("feed.signal_tags")), owner="co.acme.One"
    )
    with pytest.raises(SettingDefinitionError):
        register_definitions(clash, owner="co.acme.One")
    assert "co.acme.a" in defs.definitions() and "co.acme.c" not in defs.definitions()
    unregister_definitions("co.acme.One")
    assert "co.acme.a" not in defs.definitions()


def test_definitions_come_back_sorted_by_key(clean: None) -> None:
    keys = list(defs.definitions())
    assert keys == sorted(keys)


def test_use_definitions_restores_the_registry() -> None:
    before = list(defs.definitions())
    only = parse_definitions(doc(entry("t.one")))
    with use_definitions(only):
        assert list(defs.definitions()) == ["t.one"]
    assert list(defs.definitions()) == before


def test_the_platform_file_can_be_named_by_an_environment_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = tmp_path / "p.yaml"
    other.write_text(doc(entry("x.only")), encoding="utf-8")
    monkeypatch.setenv(defs.PLATFORM_FILE_ENV, str(other))
    assert defs.platform_file() == other
    assert [d.key for d in defs.load_definitions(defs.platform_file())] == ["x.only"]


def test_the_literal_types_name_every_value_the_class_knows() -> None:
    kinds: Any = Literal["bool", "int"]
    assert literal_values(kinds) == {"bool", "int"}
