"""The code-list service: resolution, crosswalks, effective dates and the three policies."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from engworld import COMPANY, PROJECT, Events, apply
from sqlalchemy import Engine
from tl_mod_engineering import codelists
from tl_mod_engineering.errors import (
    CrosswalkRequiredError,
    DuplicateCodeValueError,
    InvalidCrosswalkError,
    ListClosedError,
    UnknownCodeError,
    UnknownCodeListError,
)
from tl_mod_engineering.names import (
    CODE_LIST,
    CODE_VALUE,
    CODE_VALUE_CLOSED,
    CODE_VALUE_DEFINED,
    STANDARD_DEFINED,
)

EDITION = "co.acme.standards@1.0.0"
DAY = date(2026, 6, 1)


def put_list(events: Events, engine: Engine, name: str, policy: str) -> None:
    sid = f"L-{name}"
    apply(
        engine,
        events.created(sid, CODE_LIST, f"CL:{name}@1.0.0", scope=COMPANY),
        events.make(
            STANDARD_DEFINED,
            {
                "kind": "code_list",
                "code": name,
                "label": name,
                "edition": EDITION,
                "value_list_policy": policy,
            },
            stream_id=sid,
            stream_type=CODE_LIST,
            scope=COMPANY,
        ),
    )


def put_value(
    events: Events, engine: Engine, name: str, code: str, *, scope: str = COMPANY, **more: Any
) -> str:
    sid = f"V-{scope}-{name}-{code}"
    payload: dict[str, Any] = {
        "code_list": name,
        "code": code,
        "label": f"{code} label",
        "origin": "company" if scope == COMPANY else "project",
        "edition": EDITION,
    }
    payload.update(more)
    apply(
        engine,
        events.created(sid, CODE_VALUE, f"CV:{name}.{code}@1.0.0", scope=scope),
        events.make(
            CODE_VALUE_DEFINED, payload, stream_id=sid, stream_type=CODE_VALUE, scope=scope
        ),
    )
    return sid


@pytest.fixture
def world(engine: Engine, events: Events) -> Engine:
    put_list(events, engine, "Material", "extensible")
    put_list(events, engine, "Discipline", "closed")
    put_list(events, engine, "Craft", "project_defined")
    for code in ("CS", "SS316L", "other"):
        put_value(
            events, engine, "Material", code, sort_order={"CS": 1, "SS316L": 2, "other": 9}[code]
        )
    put_value(events, engine, "Discipline", "PIP")
    put_value(events, engine, "Craft", "WLD")
    return engine


def conn_of(engine: Engine) -> Any:
    return engine.connect()


def test_a_company_value_resolves_to_itself(world: Engine) -> None:
    with conn_of(world) as conn:
        found = codelists.resolve(conn, PROJECT, "Material", "CS", on=DAY)
    assert (found.code, found.company_code, found.origin, found.scope) == (
        "CS",
        "CS",
        "company",
        COMPANY,
    )
    assert found.usable and not found.via_crosswalk


def test_a_project_value_resolves_to_the_company_code_it_maps_to(
    world: Engine, events: Events
) -> None:
    put_value(events, world, "Material", "SS316L-NACE", scope=PROJECT, crosswalk="SS316L")
    with conn_of(world) as conn:
        found = codelists.resolve(conn, PROJECT, "Material", "SS316L-NACE", on=DAY)
        with pytest.raises(UnknownCodeError):  # another project does not see it
            codelists.resolve(conn, "project:P999", "Material", "SS316L-NACE", on=DAY)
    assert (found.company_code, found.origin, found.via_crosswalk) == ("SS316L", "project", True)


def test_a_project_value_with_no_crosswalk_has_no_company_code(
    world: Engine, events: Events
) -> None:
    put_value(events, world, "Craft", "RIG", scope=PROJECT)
    with conn_of(world) as conn:
        assert codelists.resolve(conn, PROJECT, "Craft", "RIG", on=DAY).company_code is None


def test_unknown_lists_and_codes_are_named(world: Engine) -> None:
    with conn_of(world) as conn:
        with pytest.raises(UnknownCodeListError, match="Nope"):
            codelists.resolve(conn, PROJECT, "Nope", "x")
        with pytest.raises(UnknownCodeError, match="'ZZ' is not a value of Material"):
            codelists.resolve(conn, PROJECT, "Material", "ZZ")


def test_a_value_is_usable_only_inside_its_dates_and_while_active(
    world: Engine, events: Events
) -> None:
    put_value(events, world, "Discipline", "OLD", effective_to="2026-01-31")
    put_value(events, world, "Discipline", "NEW", effective_from="2027-01-01")
    sid = put_value(events, world, "Discipline", "GONE")
    apply(
        world,
        events.make(
            CODE_VALUE_CLOSED,
            {"lifecycle": "retired", "reason": "x"},
            stream_id=sid,
            stream_type=CODE_VALUE,
            scope=COMPANY,
        ),
    )
    with conn_of(world) as conn:
        usable = {
            c: codelists.resolve(conn, PROJECT, "Discipline", c, on=DAY).usable
            for c in ("PIP", "OLD", "NEW", "GONE")
        }
    assert usable == {"PIP": True, "OLD": False, "NEW": False, "GONE": False}


def test_values_lists_company_then_project_in_order_and_hides_the_unusable(
    world: Engine, events: Events
) -> None:
    put_value(events, world, "Material", "SS316L-NACE", scope=PROJECT, crosswalk="SS316L")
    put_value(events, world, "Material", "EXPIRED", effective_to="2020-01-01")
    with conn_of(world) as conn:
        shown = [r.code for r in codelists.values(conn, PROJECT, "Material", on=DAY)]
        everything = [
            r.code for r in codelists.values(conn, PROJECT, "Material", on=DAY, usable_only=False)
        ]
        company_only = [r.code for r in codelists.values(conn, COMPANY, "Material", on=DAY)]
    assert shown == ["CS", "SS316L", "other", "SS316L-NACE"]
    assert "EXPIRED" in everything and "EXPIRED" not in shown
    assert "SS316L-NACE" not in company_only


# --- policy --------------------------------------------------------------------------------------


def plan(engine: Engine, **kwargs: Any) -> codelists.ValuePlan:
    fields: dict[str, Any] = {
        "scope": PROJECT,
        "name": "Material",
        "code": "NEW",
        "crosswalk": None,
    }
    fields.update(kwargs)
    with conn_of(engine) as conn:
        return codelists.plan_new_value(conn, **fields)


def test_the_company_may_add_to_any_list_without_a_crosswalk(world: Engine) -> None:
    for name in ("Material", "Discipline", "Craft"):
        assert plan(world, scope=COMPANY, name=name) == codelists.ValuePlan("company", None)
    with pytest.raises(InvalidCrosswalkError, match="company value has no crosswalk"):
        plan(world, scope=COMPANY, crosswalk="CS")


def test_a_closed_list_refuses_a_project_value(world: Engine) -> None:
    with pytest.raises(ListClosedError, match="Discipline is closed"):
        plan(world, name="Discipline", crosswalk="PIP")


def test_an_extensible_list_needs_a_crosswalk_to_an_active_company_value(world: Engine) -> None:
    assert plan(world, crosswalk="SS316L") == codelists.ValuePlan("project", "SS316L")
    assert plan(world, crosswalk="other") == codelists.ValuePlan("project", "other")
    with pytest.raises(CrosswalkRequiredError):
        plan(world)
    with pytest.raises(InvalidCrosswalkError, match="'NOPE' is not an active company value"):
        plan(world, crosswalk="NOPE")


def test_a_crosswalk_to_a_retired_or_project_value_is_refused(
    world: Engine, events: Events
) -> None:
    sid = put_value(events, world, "Material", "OLD")
    apply(
        world,
        events.make(
            CODE_VALUE_CLOSED,
            {"lifecycle": "retired", "reason": "x"},
            stream_id=sid,
            stream_type=CODE_VALUE,
            scope=COMPANY,
        ),
    )
    put_value(events, world, "Material", "MINE", scope=PROJECT, crosswalk="CS")
    for target in ("OLD", "MINE"):
        with pytest.raises(InvalidCrosswalkError):
            plan(world, crosswalk=target)


def test_a_project_defined_list_takes_values_with_or_without_a_crosswalk(world: Engine) -> None:
    assert plan(world, name="Craft") == codelists.ValuePlan("project", None)
    assert plan(world, name="Craft", crosswalk="WLD") == codelists.ValuePlan("project", "WLD")
    with pytest.raises(InvalidCrosswalkError):
        plan(world, name="Craft", crosswalk="NOPE")


def test_a_code_cannot_be_added_twice_or_shadow_a_company_code(
    world: Engine, events: Events
) -> None:
    put_value(events, world, "Craft", "RIG", scope=PROJECT)
    with pytest.raises(DuplicateCodeValueError, match="in scope 'project:P123'"):
        plan(world, name="Craft", code="RIG")
    with pytest.raises(DuplicateCodeValueError, match="company value 'WLD'"):
        plan(world, name="Craft", code="WLD")
    with pytest.raises(DuplicateCodeValueError):
        plan(world, scope=COMPANY, code="CS")


def test_a_list_that_does_not_exist_is_named(world: Engine) -> None:
    with pytest.raises(UnknownCodeListError):
        plan(world, name="Nope", crosswalk="x")
