# P1-I8-T05a2 — `tl schema package publish|deprecate|retire` and `tl schema adopt|adoptions|drift`

Status: ready
Tier: haiku
Labels: cli, schema-registry
Depends on: P1-I8-S2, P1-I8-S5 and P1-I8-T05a1 on `p1/i8` (the registry, its commands and the report commands; the provided test calls `tl schema package impact --project`)
Branch: `p1/i8-t05a2-publish-adopt`

## Goal
The governance half of the `tl schema` commands. An administrator publishes an approved package version, can stop new adoptions of it (deprecate) and take it out of every effective schema (retire), pins a version for a project (adopt) and reads which projects pin what and which are behind the company. `packages/tl-cli/src/tl_cli/schema_gov.py` holds six functions; `register` already adds three to the group `tl schema package` and three to `tl schema`. The six function bodies raise `NotImplementedError` today. You write them by the STEPS comments and the output formats in their docstrings, so the one provided test file passes. The rules (states, gates, the digest of the impact report, who may approve) are the registry module's handlers; the commands call them and print.

## Brief references (pasted)
> **Brief 27.8.** *`tl schema` CLI:* `lint`, `diff`, `classify`, `impact --project P123`, `test --sample 1000`, `publish`, `adopt`, `crosswalk`, `promote`, `export-git` / `import-git`.
>
> **Brief 27.4.** *Adoption is per project: constraining or renaming versions need the project data manager to adopt after reviewing their project-specific impact report.* Company packages are published by the schema steward after review.
>
> **Increment 8 decisions (FANOUT D2, D4).** Publishing, deprecating, retiring and adopting are the administrator's (no new role). Publish needs an Approved package whose classification is still the one approved. Adoption of anything but an additive version needs the SHA-256 of the project impact report the caller saw (`tl schema package impact REF --project P` prints it). Retire is refused while a project pins the version. `--auto-adopt` on publish moves the projects that pin the version below when the change is purely additive.

### Specification
- `publish`, `deprecate`, `retire` and `adopt` need the administrator: call `require_admin(db)` first (anything else exits 1 with `error: forbidden: ...`). `adoptions` and `drift` need a signed-in person: `require_session(db)`.
- A package argument is an id or `name@version`; `resolve_package(db, ref)` (in `tl_cli.schema_pkg`) gives the id. Every command that writes opens `open_uow(db)` inside `service_errors()`, so a refusal of the module is `error: <message>` on stderr and exit code 1.
- The scope of a package command is `"company"`; the handler sets the real scope. `adopt` uses `project:<id>`.
- Fields are separated by two spaces. The exact lines are in the docstrings; the provided test checks them.

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
`packages/tl-cli/src/tl_cli/schema_gov.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401
# pyright: reportUnusedImport=false
"""`tl schema package publish|deprecate|retire` and `tl schema adopt|adoptions|drift` (T05a2).

STUB: this file is the interface P1-I8-T05a2 implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it. `register` is complete.

Publishing, deprecating, retiring and adopting are the administrator's (FANOUT D2); the lists are
any signed-in person's. The rules are the module's (`tl_mod_schemareg.handlers`); these commands
parse options, make one call and print. A package that is not in the right state, an adoption that
needs the digest of the impact report and a retire that a project still pins are the module's
errors (`error: ...` on stderr, exit 1).
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_schemareg import analysis, views
from tl_mod_schemareg.handlers.adoption import AdoptSchemaPackage, handle_adopt_schema_package
from tl_mod_schemareg.handlers.packages import (
    DeprecateSchemaPackage,
    PublishSchemaPackage,
    RetireSchemaPackage,
    handle_deprecate_schema_package,
    handle_publish_schema_package,
    handle_retire_schema_package,
)

from tl_cli.derive_support import DEV_ACTOR, SOURCE, Actor, acting, cell, service_errors
from tl_cli.schema_pkg import resolve_package
from tl_cli.session import require_admin, require_session

_Ref = Annotated[str, typer.Argument(help="A package id or name@version, for example acme@1.1.0.")]
_Reason = Annotated[str, typer.Option("--reason", help="Why; kept in the ledger.")]


def publish(
    ctx: typer.Context,
    ref: _Ref,
    auto_adopt: Annotated[
        bool,
        typer.Option(
            "--auto-adopt", help="Move the projects that pin the version below, if it is additive."
        ),
    ] = False,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Publish an approved package version (admin). Prints `published <name@version> <id>`.

    With `--auto-adopt` it adds `auto-adopted <n>`: the projects whose pin moved to this version.
    """
    # STEPS
    # 1. db = ctx.obj; require_admin(db); target = resolve_package(db, ref).
    # 2. In `with service_errors(), open_uow(db) as uow:` call handle_publish_schema_package with
    #    a PublishSchemaPackage(actor=acting(db, actor), source=SOURCE, scope="company",
    #    package_id=target, auto_adopt=auto_adopt); keep the CommandResult.
    # 3. Print `published <result.key> <result.stream_id>`. With --auto-adopt print a second line
    #    `auto-adopted <n>`, where n counts the events of the result whose event_type is
    #    "Adoption.Pinned".
    raise NotImplementedError("STEPS: see the comments")


def deprecate(
    ctx: typer.Context,
    ref: _Ref,
    reason: _Reason,
    replacement: Annotated[
        str | None, typer.Option("--replacement", help="The version to use instead.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Stop new adoptions of a published version (admin). Prints `deprecated <name@version>`."""
    # STEPS
    # 1. require_admin(db); target = resolve_package(db, ref).
    # 2. Call handle_deprecate_schema_package with DeprecateSchemaPackage(actor, source, scope
    #    "company" as in publish, package_id=target, reason=reason, replacement=replacement).
    # 3. Print `deprecated <result.key>`.
    raise NotImplementedError("STEPS: see the comments")


def retire(ctx: typer.Context, ref: _Ref, reason: _Reason, actor: Actor = DEV_ACTOR) -> None:
    """Take a deprecated version out of every effective schema (admin).

    Refused while a project pins it. Prints `retired <name@version>`.
    """
    # STEPS
    # 1. require_admin(db); target = resolve_package(db, ref).
    # 2. Call handle_retire_schema_package with RetireSchemaPackage(actor, source, scope "company",
    #    package_id=target, reason=reason).
    # 3. Print `retired <result.key>`.
    raise NotImplementedError("STEPS: see the comments")


def adopt(
    ctx: typer.Context,
    project: Annotated[str, typer.Argument(help="The project, for example P123.")],
    package: Annotated[str, typer.Argument(help="The company package, for example acme.")],
    version: Annotated[str, typer.Argument(help="The version to pin, for example 1.1.0.")],
    impact_sha256: Annotated[
        str | None,
        typer.Option(
            "--impact-sha256",
            help="The digest `tl schema package impact --project` printed; needed unless additive.",
        ),
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Pin a company package version for a project (admin).

    Prints `adopted <project> <package>@<version>`. A change that is not additive is refused
    without the digest of the impact report the caller read.
    """
    # STEPS
    # 1. require_admin(db).
    # 2. Call handle_adopt_schema_package with AdoptSchemaPackage(actor=acting(db, actor),
    #    source=SOURCE, scope=f"project:{project}", project=project, package=package,
    #    version=version, impact_sha256=impact_sha256).
    # 3. Print `adopted <project> <package>@<version>`.
    raise NotImplementedError("STEPS: see the comments")


def adoptions(
    ctx: typer.Context,
    project: Annotated[
        str | None, typer.Option("--project", help="Only this project's pins.")
    ] = None,
) -> None:
    """List the pins, one line each.

    `<project>  <package>@<version>  from <previous or ->  <class or ->  by <actor>`. With none:
    `no adoptions`.
    """
    # STEPS
    # 1. require_session(db); read views.adoption_views(uow.conn(), project) in a read-only unit of
    #    work inside service_errors().
    # 2. With none print `no adoptions` and return.
    # 3. Otherwise one line per adoption in the format of the docstring; cell() for the previous
    #    version and the class, which may be None.
    raise NotImplementedError("STEPS: see the comments")


def drift(
    ctx: typer.Context,
    project: Annotated[str, typer.Argument(help="The project, for example P123.")],
) -> None:
    """Show which company packages a project is behind on, one line each.

    `<package>  project <version>  company <version>  behind|current  pinned|following`.
    """
    # STEPS
    # 1. require_session(db); inside service_errors() call views.drift_views(project).
    # 2. One line per item in the format of the docstring: `behind` when item.behind else
    #    `current`; `pinned` when item.pinned else `following`.
    raise NotImplementedError("STEPS: see the comments")


def register(package_app: typer.Typer, schema_app: typer.Typer) -> None:
    """Add the commands: three to `tl schema package`, three to `tl schema`."""
    package_app.command("publish")(publish)
    package_app.command("deprecate")(deprecate)
    package_app.command("retire")(retire)
    schema_app.command("adopt")(adopt)
    schema_app.command("adoptions")(adoptions)
    schema_app.command("drift")(drift)
```

The commands the handlers take (read-only; from `tl_mod_schemareg.handlers`):
```python
class PublishSchemaPackage(Command):   # extra fields forbidden
    package_id: str
    auto_adopt: bool = False

class DeprecateSchemaPackage(Command):
    package_id: str
    reason: str
    replacement: str | None = None

class RetireSchemaPackage(Command):
    package_id: str
    reason: str

class AdoptSchemaPackage(Command):
    project: str
    package: str
    version: str
    impact_sha256: str | None = None

# every Command also has: actor: str, source: str, scope: str  (correlation_id and causation_id optional)
def handle_publish_schema_package(uow, cmd: PublishSchemaPackage) -> CommandResult: ...
def handle_deprecate_schema_package(uow, cmd: DeprecateSchemaPackage) -> CommandResult: ...
def handle_retire_schema_package(uow, cmd: RetireSchemaPackage) -> CommandResult: ...
def handle_adopt_schema_package(uow, cmd: AdoptSchemaPackage) -> CommandResult: ...

class CommandResult(BaseModel):
    stream_id: str
    key: str | None       # name@version for a package
    version: int
    events: list[Event]   # each Event has .event_type, for example "Adoption.Pinned"
```

From `tl_mod_schemareg.views` (read-only):
```python
class AdoptionView(BaseModel):  # frozen
    id: str
    project: str
    package: str
    version: str
    previous_version: str | None
    worst_class: str | None
    impact_sha256: str | None
    adopted_by: str
    adopted_at: str

class DriftView(BaseModel):  # frozen
    package: str
    project_version: str
    company_version: str
    behind: bool
    pinned: bool

def adoption_views(conn: Connection, project: str | None = None) -> list[AdoptionView]: ...
def drift_views(project: str) -> list[DriftView]: ...
```

From `tl_cli` (read-only): `resolve_package(db, ref) -> str` in `tl_cli.schema_pkg`; `DEV_ACTOR`, `SOURCE`, `Actor`, `acting(db, actor)`, `cell(value, width=40)` (a dash for none) and `service_errors()` in `tl_cli.derive_support`; `require_admin(db)` and `require_session(db)` in `tl_cli.session`.
```text

```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/schema_gov.py` (the stub)
- `docs/tickets/P1-I8/provided/t05a2-test_cli_schema_gov.py.txt`
- `packages/tl-cli/src/tl_cli/schema_pkg.py` (the review commands of the same group: the style to follow)
- `packages/tl-cli/src/tl_cli/schema_pkg_read.py` (the finished report commands of T05a1)
- `packages/tl-modules/schemareg/src/tl_mod_schemareg/views.py`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/schema_gov.py` (modify: the six function bodies, the stub paragraph and directives, the unused imports)
- `packages/tl-cli/tests/test_cli_schema_gov.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I8/P1-I8-T05a2.md` (create: your report; commit it)

## Steps
1. Copy the provided test to `packages/tl-cli/tests/test_cli_schema_gov.py`. Do not edit the copy (it is ruff-clean and pyright-clean as provided).
2. Run it once; all nine cases fail against the stub.
3. Write the six bodies by their STEPS and docstrings. Remove the STUB paragraph, the two directive lines, every STEPS comment and every `raise NotImplementedError` line, and the imports the finished file does not use. Leave `register` as it is.
4. Run the commands under *Acceptance*.

## Acceptance
```
uv run ruff format packages/tl-cli
uv run pytest packages/tl-cli/tests/test_cli_schema_gov.py packages/tl-cli/tests/test_cli_schema_package.py packages/tl-cli/tests/test_cli_schema_pkg_read.py -q --adapters sqlite,postgres --basetemp=/tmp/pt-t05a2
just check
```
Expected: all pass on both adapters (the provided file has nine cases; the administrator case skips on Postgres); `just check` is clean (run it with a 600 000 ms timeout). Remove `/tmp/pt-t05a2` after you have read the exit code.

## Tests to add
None beyond the provided file. If you think a case is missing, say so under *Open questions* in the report; do not edit the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), committed at `docs/reports/P1-I8/P1-I8-T05a2.md`. Deviations first. Paste the last lines of each acceptance command.

## Escalation triggers
- Stop and report *Blocked* if a provided test fails and you cannot see a difference between your reading of the STEPS and the test after two attempts.
- Stop if the pasted interface and the repository disagree.
- Stop if you would have to change a provided test or any file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
