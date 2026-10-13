# P1-I1-T09e — `tl standards class`: define, ls, show, revise, close

Status: ready
Tier: haiku
Labels: cli
Depends on: P1-I1-T07 (tag class commands, merged) and the standards loader (test setup only), on `p1/i1`; no other ticket
Branch: `p1/i1-t09e-cli-tag-class`

## Goal
The administrator defines and changes tag classes from the shell. `packages/tl-cli/src/tl_cli/standards_class.py` has the helpers and the five commands' signatures, options and docstrings final; the bodies raise `NotImplementedError`. The group is already registered in `tl_cli/main.py` as `tl standards class`. You implement the bodies. One provided test file (`7` test functions) must pass on SQLite and on Postgres (one case is SQLite-only and skips on Postgres).

## Brief references (pasted)
> **Brief 9 M2 Engineering Data.** `TagClass`: class definition, required psets, applicable ITR templates. Tag class determines mandatory psets (e.g. control valve: size, rating, body material, actuator type, fail action). A constraining change (a class that gains a required pset) flags existing records non-conformant; nothing is rewritten.
>
> **P1-I1 plan D8.** Registry writes, tag classes included, are admin-only.

### Specification
- **Output is part of the contract**: the test compares lines exactly. The STEPS give the formats.
- Tag classes are company data: every command uses scope `company` (`COMPANY` from `tl_mod_engineering.names`). `define`, `revise` and `close` call `require_admin(db)` first; `ls` and `show` need no admin.
- A failure prints `error: <message>` on stderr and exits 1 with no traceback. `_service_errors()` does that for service and validation failures. The messages come from the handlers (an unknown pset, a duplicate class, nothing to change).
- A class is named by its code. `_class(uow, code)` finds it (the active one, else the newest) and exits with `error: no tag class 'X'`.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/standards_class.py` (the stub you complete):
```python
"""The `tl standards class` group: tag classes, the classes that bind property sets (P1-I1-T09e).

A tag class names the property sets a tag of that class must carry (brief 9 M2). Each subcommand
parses options, makes one call into `tl_mod_engineering` (a handler or a read) and prints. The rules
(a required pset must exist, a closed class takes no more tags) live in the module. Classes are
company data: define, revise and close need the admin role; ls and show are open.

STUB (P1-I1-T09e): the bodies of the commands raise NotImplementedError; their signatures, options
and docstrings and the helpers (`_service_errors`, `_class`, `_list`) are final. Each body has a
STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa`
line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any, NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.db import DbTarget, open_uow
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_mod_engineering import registry
from tl_mod_engineering.handlers.tag_class import (
    REVISABLE,
    CloseTagClass,
    DefineTagClass,
    ReviseTagClass,
    handle_close_tag_class,
    handle_define_tag_class,
    handle_revise_tag_class,
)
from tl_mod_engineering.names import COMPANY

from tl_cli.session import require_admin

app = typer.Typer(help="Define, show and change tag classes.", no_args_is_help=True)

_DEFAULT_ACTOR = "user:dev"
_Actor = Annotated[str, typer.Option("--actor", help="Actor recorded on events.")]
_Reason = Annotated[str, typer.Option("--reason", help="Why (kept in the history).")]
_Code = Annotated[str, typer.Argument(help="The class code, for example ControlValve.")]


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a service, concurrency or input-validation failure into `error:` on stderr, exit 1."""
    try:
        yield
    except (ServiceError, ConcurrencyError) as exc:
        _fail(str(exc))
    except ValidationError as exc:
        _fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))


def _class(uow: Any, code: str) -> registry.TagClassRow:
    """The active class ``code``, else the newest of any lifecycle, else `error:` and exit 1."""
    rows = registry.find_tag_classes(uow.conn(), COMPANY, code=code)
    if not rows:
        _fail(f"no tag class {code!r}")
    active = [row for row in rows if row.active]
    return (active or rows)[-1]


def _list(values: list[str]) -> str:
    return ", ".join(values) if values else "-"


@app.command("define")
def define(
    ctx: typer.Context,
    code: _Code,
    label: Annotated[str, typer.Option("--label", help="What the class is called.")],
    family: Annotated[
        str,
        typer.Option("--family", help="instrument, valve, pump, line, equipment, cable, other."),
    ],
    edition: Annotated[
        str,
        typer.Option(
            "--edition", help="The standards edition, for example co.acme.standards@1.0.0."
        ),
    ],
    definition: Annotated[str | None, typer.Option("--definition")] = None,
    pset: Annotated[
        list[str] | None,
        typer.Option("--pset", help="A property set a tag of this class must carry; repeatable."),
    ] = None,
    mnemonic: Annotated[
        list[str] | None, typer.Option("--mnemonic", help="A tag prefix of this class; repeatable.")
    ] = None,
    itr: Annotated[
        list[str] | None, typer.Option("--itr", help="An ITR template of this class; repeatable.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Define a tag class (admin). Its required property sets must exist in the company schema."""
    # STEPS
    # 1. `db: DbTarget = ctx.obj`; `require_admin(db)`.
    # 2. Inside `with _service_errors(), open_uow(db) as uow:` handle_define_tag_class(uow,
    #    DefineTagClass(actor=actor, source="cli", scope=COMPANY, code=code, label=label,
    #    definition=definition, family=family, required_psets=pset or [], itr_templates=itr or
    #    [], mnemonics=mnemonic or [], edition=edition)).
    # 3. After the block print f"defined class {code}" and f"psets {_list(pset or [])}".
    raise NotImplementedError


@app.command("ls")
def ls(
    ctx: typer.Context,
    include_closed: Annotated[
        bool, typer.Option("--all", help="Include superseded and retired classes.")
    ] = False,
) -> None:
    """List tag classes by code: code, family, lifecycle, required property sets, label."""
    # STEPS
    # 1. Inside `with _service_errors(), open_uow(db, readonly=True) as uow:` rows =
    #    registry.find_tag_classes(uow.conn(), COMPANY, active_only=not include_closed).
    # 2. One line per row, columns separated by two spaces: code, family, lifecycle,
    #    _list(row.required_psets), label.
    raise NotImplementedError


@app.command("show")
def show(ctx: typer.Context, code: _Code) -> None:
    """Show one tag class: its fields, required property sets, prefixes and ITR templates."""
    # STEPS
    # 1. Inside `with _service_errors(), open_uow(db, readonly=True) as uow:` row = _class(uow,
    #    code).
    # 2. Print `name: value` lines in this order: code, label, family, lifecycle, edition, key
    #    ("-" when None), superseded_by ("-" when None), psets (_list of required_psets),
    #    mnemonics (_list), itr (_list of itr_templates), version.
    raise NotImplementedError


@app.command("revise")
def revise(
    ctx: typer.Context,
    code: _Code,
    reason: _Reason,
    label: Annotated[str | None, typer.Option("--label")] = None,
    family: Annotated[str | None, typer.Option("--family")] = None,
    pset: Annotated[
        list[str] | None,
        typer.Option("--pset", help="Replace the required property sets; repeatable."),
    ] = None,
    mnemonic: Annotated[
        list[str] | None, typer.Option("--mnemonic", help="Replace the tag prefixes; repeatable.")
    ] = None,
    itr: Annotated[
        list[str] | None, typer.Option("--itr", help="Replace the ITR templates; repeatable.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Change a tag class (admin). A list option replaces the whole list."""
    # STEPS
    # 1. `db: DbTarget = ctx.obj`; `require_admin(db)`.
    # 2. changes = {} with these entries, only for the options that were given: "label", "family",
    #    "required_psets" (from --pset), "mnemonics" (from --mnemonic), "itr_templates" (from
    #    --itr). None given: _fail("nothing to revise: give --label, --family, --pset, --mnemonic
    #    or --itr").
    # 3. Inside `with _service_errors(), open_uow(db) as uow:` row = _class(uow, code);
    #    handle_revise_tag_class(uow, ReviseTagClass(actor=actor, source="cli", scope=COMPANY,
    #    stream_id=row.id, changes=changes, reason=reason)).
    # 4. After the block print f"revised class {code}: " and the changed field names in the order
    #    of REVISABLE, joined by ", " (one line).
    raise NotImplementedError


@app.command("close")
def close(
    ctx: typer.Context,
    code: _Code,
    reason: _Reason,
    superseded_by: Annotated[
        str | None,
        typer.Option("--superseded-by", help="The replacing class's code; omit to retire."),
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """End the life of a tag class (admin). Tags already of that class keep it."""
    # STEPS
    # 1. `db: DbTarget = ctx.obj`; `require_admin(db)`.
    # 2. Inside `with _service_errors(), open_uow(db) as uow:` row = _class(uow, code); with
    #    --superseded-by other = _class(uow, superseded_by); lifecycle = "superseded" if other
    #    else "retired"; handle_close_tag_class(uow, CloseTagClass(actor=actor, source="cli",
    #    scope=COMPANY, stream_id=row.id, lifecycle=lifecycle, superseded_by=other.id if other
    #    else None, reason=reason)).
    # 3. After the block print f"closed class {code} as {lifecycle}".
    raise NotImplementedError
```

`packages/tl-modules/engineering/src/tl_mod_engineering/handlers/tag_class.py` (the commands you build; fields only):
```python
REVISABLE = ("label", "family", "required_psets", "itr_templates", "mnemonics")

class DefineTagClass(Command):   # + actor, source, scope="company"
    code: str; label: str; definition: str | None = None
    family: TagFamily   # Literal["instrument", "valve", "pump", "line", "equipment", "cable", "other"]
    required_psets: list[str] = []; itr_templates: list[str] = []; mnemonics: list[str] = []; edition: str
class ReviseTagClass(Command):
    stream_id: str; expected_version: int | None = None; changes: dict[str, Any]; reason: str
class CloseTagClass(Command):
    stream_id: str; expected_version: int | None = None
    lifecycle: Literal["superseded", "retired"] = "retired"; superseded_by: str | None = None  # the id of the replacing class
    reason: str
def handle_define_tag_class(uow, cmd) -> CommandResult: ...
def handle_revise_tag_class(uow, cmd) -> CommandResult: ...
def handle_close_tag_class(uow, cmd) -> CommandResult: ...
```

`packages/tl-modules/engineering/src/tl_mod_engineering/registry.py`:
```python
@dataclass(frozen=True)
class TagClassRow:
    id: str; scope: str; code: str; label: str; description: str | None; family: str
    required_psets: list[str]; itr_templates: list[str]; mnemonics: list[str]
    lifecycle: str; superseded_by: str | None; edition: str; key: str | None; version: int
    active: bool   # property

def find_tag_classes(conn, scope: str, *, code: str | None = None, active_only: bool = False) -> list[TagClassRow]: ...  # by code then edition
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/standards_class.py` (the file you edit)
- `packages/tl-cli/src/tl_cli/tag.py` (a finished group of the same shape; read it for style)
- `packages/tl-cli/tests/engcli_support.py` (test support; read only)
- `docs/tickets/P1-I1/provided/t09e-test_cli_standards_class.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- pyright is `standard` for `packages/tl-cli`; ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing.
- Provided files live under `docs/tickets/P1-I1/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I1/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*` table or change `schema/**` or anything under `generated/` unless this ticket says so.
- On Postgres the tl-cli `conftest.py` signs a test user in for you (L-P1-I0B-8); start Postgres with `sudo pg_ctlcluster 16 main start` if needed. A parity run of a CLI test file takes about one to two minutes.
- Admin-only commands call `tl_cli.session.require_admin(db)` first. On SQLite the test file signs an admin in through `engcli_support.admin_env` (already in the tree); do not change `engcli_support.py`.
- CLI tests (L-P0-I4-B8): `CliRunner.invoke` catches exceptions; the test asserts `exit_code` and that no traceback is printed. A command that crashes with `NotImplementedError` fails the test; do not catch it.
- The test loads the standards through the module (`engcli_support.load_acme`), not through `tl standards load`, so this ticket does not depend on the other CLI tickets.
- A record's `version` counts events: a new class is at version 2 (`Record.Created` and `TagClass.Defined`), and a revision makes it 3.
- `family` arrives as text; the command model validates it, and a wrong family becomes a `ValidationError` that `_service_errors` prints.


## Allowed paths
- `packages/tl-cli/src/tl_cli/standards_class.py` (edit)
- `packages/tl-cli/tests/test_cli_standards_class.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I1/P1-I1-T09e.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I1/provided/t09e-test_cli_standards_class.py.txt` to `packages/tl-cli/tests/test_cli_standards_class.py`.
3. Implement the five commands by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_standards_class.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-cli/tests/test_cli_standards_class.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli -q
```
Expected: `just check` clean; all cases pass on SQLite; with both adapters 1 case skips on Postgres and the rest pass; the whole tl-cli package passes.

## Tests to add
None beyond the provided file(s).

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the output of the parity run (decisive lines).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change outside the Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
