# ruff: noqa: F401
# pyright: reportUnusedImport=false
"""`tl schema crosswalk --project P [--list L] [--json]`: project values and their company values.

STUB: this file is the interface P1-I8-T05a4a implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it. `CrosswalkRow` and `register` are
complete.

A project may add values to an `extensible` code list (each must map to a company value or to
`other`) and owns a `project_defined` list outright (a mapping is optional, and keeps cross-project
reports working). The command lists every value the project owns and the company value it maps
to, and flags the ones that map to nothing. A `closed` list has no project values. Brief 6.3.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

import typer
from pydantic import BaseModel
from tl_adapters.db import DbTarget
from tl_mod_schemareg import analysis
from tl_schema.effective import EffectiveSchema

from tl_cli.derive_support import cell, service_errors
from tl_cli.session import require_session

Status = Literal["mapped", "other", "unmapped"]


class CrosswalkRow(BaseModel):
    pset: str  # "valve_data"
    property: str  # "body_material", or "x.fat_witness_by" for a custom property
    code_list: str | None  # "MaterialCode"
    policy: str  # "extensible" or "project_defined"
    code: str  # the project's value
    label: str
    maps_to: str | None  # the company value, "other", or None
    status: Status


def crosswalk_rows(schema: EffectiveSchema, list_name: str | None = None) -> list[CrosswalkRow]:
    """The values a project owns in the effective schema `schema`, with where each maps.

    STEPS
    1. Walk `schema.psets.values()` in order and, in each, `pset.all_properties()` in order.
    2. Skip a property whose `enum_values` is None or whose `value_list_policy` is not
       `extensible` or `project_defined`; with `list_name`, skip a property whose `code_list`
       differs from it.
    3. For each `EnumValue` in `prop.enum_values`, in order: on an `extensible` list skip a value
       whose `crosswalk` is None (it is a company value). Otherwise add a row:
       `pset` = pset.name, `property` = `prop.relative_key()`, `code_list` = prop.code_list,
       `policy` = prop.value_list_policy, `code`, `label`, `maps_to` = the value's crosswalk,
       `status` = `other` when the crosswalk is `"other"`, `mapped` when it is any other text,
       `unmapped` when it is None.
    """
    raise NotImplementedError("STEPS: see the docstring")


def crosswalk(
    ctx: typer.Context,
    project: Annotated[str, typer.Option("--project", help="The project, for example P123.")],
    list_name: Annotated[
        str | None, typer.Option("--list", help="Only this code list, for example MaterialCode.")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="The rows as JSON.")] = False,
) -> None:
    """List each project value and the company value it maps to; unmapped ones are flagged.

    Lines: `crosswalk project:<P>`, then one line per row,
    `<pset>.<property>  <code_list>  <code>  <maps_to>  <status>` (a dash for none), then
    `values <n>, unmapped <u>`. With `--json` one object: `{"scope": ..., "unmapped": u,
    "rows": [...]}` (the rows as `CrosswalkRow` fields), indented by 2.
    """
    # STEPS
    # 1. db: DbTarget = ctx.obj; require_session(db).
    # 2. In `with service_errors():` get the schema with
    #    `analysis.provider().effective(f"project:{project}")` (call it through `analysis.`; the
    #    test replaces `analysis.provider`) and the rows with crosswalk_rows(schema, list_name).
    # 3. Print as the docstring says. unmapped = the rows whose status is "unmapped".
    raise NotImplementedError("STEPS: see the comments")


def register(app: typer.Typer) -> None:
    """Add the command to `tl schema`."""
    app.command("crosswalk")(crosswalk)
