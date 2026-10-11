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


def test_extension_keys_carry_the_namespace_and_name_of_their_type(clean: None) -> None:
    mine = parse_definitions(doc(entry("co.acme.lift_plan.max_load")), owner="co.acme.LiftPlan")
    register_definitions(mine, owner="co.acme.LiftPlan")
    assert get_definition("co.acme.lift_plan.max_load").owner == "co.acme.LiftPlan"
    assert "co.acme.lift_plan.max_load" in defs.definitions()
    for stray in ("other.key", "co.acme.max_load", "co.acme.lift.max_load", "co.acme.lift_plans.x"):
        bad = parse_definitions(doc(entry(stray)), owner="co.acme.LiftPlan")
        with pytest.raises(SettingDefinitionError, match="must start with 'co.acme.lift_plan.'"):
            register_definitions(bad, owner="co.acme.LiftPlan")


def test_a_type_of_a_short_namespace_cannot_take_the_keys_of_another_namespace(
    clean: None,
) -> None:
    squat = parse_definitions(doc(entry("co.acme.lift_plan.max_load")), owner="co.Foo")
    with pytest.raises(SettingDefinitionError, match="must start with 'co.foo.'"):
        register_definitions(squat, owner="co.Foo")
    platform = parse_definitions(doc(entry("feed.reactions.enabled")), owner="co.Foo")
    with pytest.raises(SettingDefinitionError, match="must start with 'co.foo.'"):
        register_definitions(platform, owner="co.Foo")


def test_a_type_name_cannot_reproduce_another_namespace(clean: None) -> None:
    """`co.Acme` has the prefix `co.acme.`; `co.acme.Foo` the namespace `co.acme.foo`."""
    for owner, key in (
        ("co.Acme", "co.acme.x.y"),
        ("co.Acme", "co.acme.lift_plan.max_load"),
        ("co.acme.Foo", "co.acme.foo.x.k"),
    ):
        bad = parse_definitions(doc(entry(key)), owner=owner)
        with pytest.raises(SettingDefinitionError, match="one more segment without a dot"):
            register_definitions(bad, owner=owner)
    fine = parse_definitions(doc(entry("co.acme.x")), owner="co.Acme")
    register_definitions(fine, owner="co.Acme")  # its own single-segment key is fine
    unregister_definitions("co.Acme")


def test_an_extension_cannot_shadow_a_platform_key_or_another_type(clean: None) -> None:
    shadow = parse_definitions(doc(entry("feed.reactions.enabled")), owner="feed.reactions.Type")
    with pytest.raises(SettingDefinitionError, match="must start with 'feed.reactions.type.'"):
        register_definitions(shadow, owner="feed.reactions.Type")
    # two names that snake-case alike share a prefix, so the second cannot take the first's key
    first = parse_definitions(doc(entry("co.acme.http_server.a")), owner="co.acme.HTTPServer")
    register_definitions(first, owner="co.acme.HTTPServer")
    second = parse_definitions(doc(entry("co.acme.http_server.a")), owner="co.acme.HttpServer")
    with pytest.raises(SettingDefinitionError, match="already defined"):
        register_definitions(second, owner="co.acme.HttpServer")
    with pytest.raises(SettingDefinitionError, match="platform"):
        register_definitions(first, owner="platform")
    with pytest.raises(SettingDefinitionError, match="namespace"):
        register_definitions(first, owner="NoDot")


def test_a_secret_definition_is_refused(clean: None) -> None:
    secret = parse_definitions(
        doc(entry("co.acme.vault.token", sensitivity="secret")), owner="co.acme.Vault"
    )
    with pytest.raises(SettingDefinitionError, match="secret"):
        register_definitions(secret, owner="co.acme.Vault")
    assert "co.acme.vault.token" not in defs.definitions()


def test_a_platform_key_wins_over_an_extension_key_in_the_listing_too(clean: None) -> None:
    platform = defs.definitions()["feed.reactions.enabled"]
    squatter = platform.model_copy(update={"owner": "co.acme.Squatter", "default": False})
    with defs._registry.lock:  # pyright: ignore[reportPrivateUsage]
        defs._registry.extensions["co.acme.Squatter"] = {  # pyright: ignore[reportPrivateUsage]
            platform.key: squatter
        }
    try:
        assert defs.definitions()[platform.key].owner == "platform"
        assert defs.definitions()[platform.key] == get_definition(platform.key)
    finally:
        unregister_definitions("co.acme.Squatter")


def test_registering_an_owner_again_replaces_its_keys_and_nothing_is_kept_on_failure(
    clean: None,
) -> None:
    v1 = parse_definitions(doc(entry("co.acme.one.a"), entry("co.acme.one.b")), owner="co.acme.One")
    register_definitions(v1, owner="co.acme.One")
    v2 = parse_definitions(doc(entry("co.acme.one.a")), owner="co.acme.One")
    register_definitions(v2, owner="co.acme.One")
    assert "co.acme.one.b" not in defs.definitions() and "co.acme.one.a" in defs.definitions()
    clash = parse_definitions(
        doc(entry("co.acme.one.c"), entry("feed.signal_tags")), owner="co.acme.One"
    )
    with pytest.raises(SettingDefinitionError):
        register_definitions(clash, owner="co.acme.One")
    assert "co.acme.one.a" in defs.definitions() and "co.acme.one.c" not in defs.definitions()
    unregister_definitions("co.acme.One")
    assert "co.acme.one.a" not in defs.definitions()


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
