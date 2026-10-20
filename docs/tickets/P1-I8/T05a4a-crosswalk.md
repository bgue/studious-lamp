# P1-I8-T05a4a — `tl schema crosswalk`: project values and the company values they map to

Status: ready
Tier: haiku
Review: lite
Labels: cli, schema-registry
Depends on: P1-I8-S2 and P1-I8-S5 on `p1/i8`; no other ticket
Branch: `p1/i8-t05a4a-crosswalk`

## Goal
A cross-project report only works when a project's own values map to company values. `packages/tl-cli/src/tl_cli/schema_crosswalk.py` holds the command `tl schema crosswalk --project P [--list L] [--json]` (already registered in `tl schema`) and the pure function `crosswalk_rows(schema, list_name)` it prints from. Both raise `NotImplementedError` today; `CrosswalkRow` and `register` are complete. You write the two bodies by the STEPS comments, so the one provided test file passes. Nothing is written to the ledger.

## Brief references (pasted)
> **Brief 6.3.** `value_list_policy`: `closed` (company values only), `extensible` (projects may add values, which must crosswalk to a company value or `other`), or `project_defined` (projects own the list entirely; an optional crosswalk keeps cross-project reports working). Code lists follow the same `value_list_policy` and crosswalk rules (6.4), so a project's local values always map to company values for reporting.
>
> **Decision (Q2, 2026-10-20).** `tl schema crosswalk --project P [--list L] [--json]` lists each project value and the company value it maps to, and flags the unmapped ones. For an `extensible` list an unmapped value is a lint error already (the schema does not compose), so unmapped values only show on `project_defined` lists.

### Specification
- Needs a signed-in person (`require_session(db)`); it reads the effective schema the process provider holds (`analysis.provider().effective("project:<P>")`, called through `analysis.`: the test replaces `analysis.provider`). A project that has no packages answers with the company schema, so it has no rows.
- In the effective schema an `extensible` list holds the company values (`crosswalk` is None) and the project's added ones (`crosswalk` set); a `project_defined` list holds only the project's values. `EnumValue` is `code`, `label`, `crosswalk` (a company code, `other`, or None).
- Fields of a printed row are separated by two spaces; `cell(...)` prints a dash for None. A malformed project id is the provider's error: `service_errors()` prints it as `error: ...` and exits 1.

### Learnings that apply
> **L-P1-I3-3.** A stub also fails pyright on unused imports, so the stub file carries `# ruff: noqa: F401` and a `# pyright: reportUnusedImport=false` line. Remove both with the STEPS comments when the body is written, and remove every import the finished file does not use.
>
> **L-P1-I4-9.** A first `just check` in a fresh worktree takes over two minutes: run it with a 600 000 ms timeout (or in the background and wait). Run `uv run ruff format <file>` first, because the format check rewrites a hand-wrapped line.
>
> **L-P0-I1-6.** ruff's `E501` applies to comments and docstrings at 100 columns.
>
> **L-P0-I6C-8.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`.
>
> **L-P1-I8-5.** Never delete anything under `/tmp/pytest-of-root`: other agents use it. Give each pytest run `--basetemp=/tmp/pt-<ticket>` and remove only that directory after you have read the exit code.
>
> **L-P1-I4-16.** A read command is easy to get wrong in the part the test does not touch (a fixed value, the other half of a condition, the order of fields). Print exactly the fields and the order in the docstring; the provided test checks them with values that differ from each other.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/schema_crosswalk.py` (the stub you complete; the whole file):
```python
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
```

From `tl_schema.effective` (read-only; abridged):
```python
class EffectiveProperty(BaseModel):
    name: str
    enum_values: list[EnumValue] | None = None      # tl_schema.forms.EnumValue
    code_list: str | None = None                    # "MaterialCode"
    value_list_policy: Literal["closed", "extensible", "project_defined"] | None = None
    def relative_key(self) -> str: ...              # "size_in" or "x.fat_witness_by"

class EffectivePset(BaseModel):
    name: str
    def all_properties(self) -> list[EffectiveProperty]: ...   # standard, then custom

class EffectiveSchema(BaseModel):
    scope: str
    psets: dict[str, EffectivePset]                 # sorted by name
```

From `tl_cli` (read-only): `cell(value, width=40)` (a dash for none) and `service_errors()` in `tl_cli.derive_support`; `require_session(db)` in `tl_cli.session`. `analysis.provider()` (in `tl_mod_schemareg.analysis`) returns the process schema provider.
```text

```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/schema_crosswalk.py` (the stub)
- `docs/tickets/P1-I8/provided/t05a4a-test_cli_schema_crosswalk.py.txt`
- `packages/tl-cli/src/tl_cli/schema_pkg_read.py` (finished read commands of the same group: the style to follow)
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/schema_crosswalk.py` (modify: the two bodies, the stub paragraph and directives, the unused imports)
- `packages/tl-cli/tests/test_cli_schema_crosswalk.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I8/P1-I8-T05a4a.md` (create: your report; commit it)

## Steps
1. Copy the provided test to `packages/tl-cli/tests/test_cli_schema_crosswalk.py`. Do not edit the copy (it is ruff-clean and pyright-clean as provided).
2. Run it once; all six cases fail against the stub.
3. Write `crosswalk_rows` and `crosswalk` by their STEPS and docstrings. Remove the STUB paragraph, the two directive lines, every STEPS comment and every `raise NotImplementedError` line, and the imports the finished file does not use.
4. Run the commands under *Acceptance*.

## Acceptance
```
uv run ruff format packages/tl-cli
uv run pytest packages/tl-cli/tests/test_cli_schema_crosswalk.py -q --adapters sqlite,postgres --basetemp=/tmp/pt-t05a4a
just check
```
Expected: six passed on both adapters; `just check` is clean (run it with a 600 000 ms timeout). Remove `/tmp/pt-t05a4a` after you have read the exit code.

## Tests to add
None beyond the provided file. If you think a case is missing, say so under *Open questions* in the report; do not edit the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), committed at `docs/reports/P1-I8/P1-I8-T05a4a.md`. Deviations first. Paste the last lines of each acceptance command.

## Escalation triggers
- Stop and report *Blocked* if a provided test fails and you cannot see a difference between your reading of the STEPS and the test after two attempts.
- Stop if the pasted interface and the repository disagree.
- Stop if you would have to change a provided test or any file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
