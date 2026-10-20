"""`tl schema crosswalk` (P1-I8-T05a4a). Provided; do not edit."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from auth_support import run as tl
from derivecli_support import as_admin
from doccli_support import docs_env
from tl_adapters.db import DbTarget
from tl_cli.schema_crosswalk import crosswalk_rows
from tl_mod_schemareg import analysis
from tl_schema.effective import EffectiveProperty, EffectivePset, EffectiveSchema
from tl_schema.forms import EnumValue
from typer.testing import Result as RunResult


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return docs_env(new_db, monkeypatch)


def crosswalk(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = tl(env, "schema", "crosswalk", *args)
    assert (result.exit_code == 0) is ok, result.output
    return result


def prop(
    name: str,
    policy: str | None,
    values: list[tuple[str, str | None]] | None,
    code_list: str | None = "Colour",
    layer: str = "standard",
) -> EffectiveProperty:
    return EffectiveProperty(
        name=name,
        layer=layer,  # type: ignore[arg-type]
        label=name,
        description="A property.",
        kind="enum",
        code_list=code_list,
        enum_values=None
        if values is None
        else [EnumValue(code=c, label=c.title(), crosswalk=x) for c, x in values],
        value_list_policy=policy,  # type: ignore[arg-type]
        enforcement="advisory",
        origin="t@1.0.0",
    )


def pset(name: str, props: list[EffectiveProperty], custom: list[EffectiveProperty]) -> Any:
    return EffectivePset(
        name=name,
        layer="project",
        label=name,
        description="A pset.",
        package="t",
        version="1.0.0",
        applies_to=["core.Record"],
        enforcement="advisory",
        adoption="optional",
        custom_allowed=True,
        properties={p.name: p for p in props},
        custom={p.name: p for p in custom},
    )


def schema() -> EffectiveSchema:
    """Four lists: a closed one, an extensible one (two company values, two project values), a
    project-defined one (a mapped, an `other` and an unmapped value) and a custom property."""
    paint = pset(
        "paint",
        [
            prop("closed_colour", "closed", [("red", None), ("blue", "red")]),
            prop(
                "colour",
                "extensible",
                [("red", None), ("other", None), ("teal", "blue"), ("navy", "other")],
            ),
            prop(
                "finish",
                "project_defined",
                [("matt", "gloss"), ("satin", "other"), ("rough", None)],
                code_list="Finish",
                layer="project",
            ),
            prop("free", None, None, code_list=None),
        ],
        [prop("grade", "project_defined", [("a", None)], code_list="Grade", layer="custom")],
    )
    return EffectiveSchema(scope="project:P1", packages=[], core_digest="0", psets={"paint": paint})


def test_only_the_values_a_project_owns_are_listed_with_where_they_map() -> None:
    rows = [
        (r.property, r.code, r.maps_to, r.status, r.policy, r.code_list)
        for r in crosswalk_rows(schema())
    ]
    assert rows == [
        ("colour", "teal", "blue", "mapped", "extensible", "Colour"),
        ("colour", "navy", "other", "other", "extensible", "Colour"),
        ("finish", "matt", "gloss", "mapped", "project_defined", "Finish"),
        ("finish", "satin", "other", "other", "project_defined", "Finish"),
        ("finish", "rough", None, "unmapped", "project_defined", "Finish"),
        ("x.grade", "a", None, "unmapped", "project_defined", "Grade"),
    ]  # a closed list and a property without values have none; company values are not listed
    first = crosswalk_rows(schema())[0]
    assert (first.pset, first.label) == ("paint", "Teal")


def test_one_list_can_be_asked_for() -> None:
    assert {r.code for r in crosswalk_rows(schema(), "Finish")} == {"matt", "satin", "rough"}
    assert crosswalk_rows(schema(), "Colour")[0].code == "teal"
    assert crosswalk_rows(schema(), "Nope") == []


class _Held:
    def effective(self, scope: str) -> EffectiveSchema:
        assert scope == "project:P1"
        return schema()


def test_the_command_prints_a_line_per_value_and_counts_the_unmapped(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    as_admin(env)
    monkeypatch.setattr(analysis, "provider", lambda: _Held())
    out = crosswalk(env, "--project", "P1").stdout.splitlines()
    assert out[0] == "crosswalk project:P1"
    assert out[1] == "paint.colour  Colour  teal  blue  mapped"
    assert out[2] == "paint.colour  Colour  navy  other  other"
    assert out[5] == "paint.finish  Finish  rough  -  unmapped"
    assert out[6] == "paint.x.grade  Grade  a  -  unmapped"
    assert out[7] == "values 6, unmapped 2" and len(out) == 8
    only = crosswalk(env, "--project", "P1", "--list", "Grade").stdout.splitlines()
    assert only == [
        "crosswalk project:P1",
        "paint.x.grade  Grade  a  -  unmapped",
        "values 1, unmapped 1",
    ]
    none = crosswalk(env, "--project", "P1", "--list", "Nope").stdout.splitlines()
    assert none == ["crosswalk project:P1", "values 0, unmapped 0"]


def test_json_holds_the_scope_the_count_and_the_rows(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    as_admin(env)
    monkeypatch.setattr(analysis, "provider", lambda: _Held())
    body = json.loads(crosswalk(env, "--project", "P1", "--json").stdout)
    assert (body["scope"], body["unmapped"], len(body["rows"])) == ("project:P1", 2, 6)
    assert body["rows"][0] == {
        "pset": "paint",
        "property": "colour",
        "code_list": "Colour",
        "policy": "extensible",
        "code": "teal",
        "label": "Teal",
        "maps_to": "blue",
        "status": "mapped",
    }


def test_the_fixture_project_p123_maps_its_added_material(env: dict[str, str]) -> None:
    as_admin(env)
    out = crosswalk(env, "--project", "P123").stdout.splitlines()
    assert out == [
        "crosswalk project:P123",
        "valve_data.body_material  MaterialCode  SS316L-NACE  SS316L  mapped",
        "values 1, unmapped 0",
    ]
    quiet = crosswalk(env, "--project", "P999").stdout.splitlines()
    assert quiet == ["crosswalk project:P999", "values 0, unmapped 0"]


def test_a_project_id_that_is_not_one_is_an_error_line(env: dict[str, str]) -> None:
    as_admin(env)
    bad = crosswalk(env, "--project", "not a project", ok=False)
    assert bad.output.startswith("error:") and "project" in bad.output
