# P1-I8-T05a3 — `tl schema waiver request|approve|revoke|ls`: time-limited exceptions

Status: ready
Tier: haiku
Review: full
Labels: cli, schema-registry
Depends on: P1-I8-S2 and P1-I8-S5 on `p1/i8` (the waiver handlers and `waiver_views` are merged); no other ticket
Branch: `p1/i8-t05a3-waivers-cli`

## Goal
A project that cannot meet one property of the schema yet asks for a waiver, an administrator approves it for a limited time, and anyone can list them. `packages/tl-cli/src/tl_cli/schema_waiver.py` holds four commands of the new group `tl schema waiver` (the group is already added to `tl schema`): `request`, `approve`, `revoke` and `ls`. The four functions raise `NotImplementedError` today; `_waiver_id` and the group are complete. You write the bodies by the STEPS comments and the output formats in their docstrings, so the one provided test file passes. The rules (366 days at most, a past date, the person who asked cannot approve, nothing to revoke twice) are the registry module's handlers; the commands call them and print.

## Brief references (pasted)
> **Brief 27.4 and 6.3.** A waiver is a time-limited, approved exception to one property of a project's effective schema; it is recorded in the ledger and listed. An approved waiver changes the project's effective schema (and its hash) until it expires or is revoked.
>
> **Increment 8 decisions (FANOUT D2, D5).** Asking is any signed-in person's. Approving and revoking are the administrator's; the person who asked cannot approve. A waiver lasts at most 366 days. `revoke` also refuses a waiver that is still only requested. A refusal of the module is `error: <message>` on stderr and exit code 1.

### Specification
- `request` and `ls` need a signed-in person (`require_session(db)`). `approve` and `revoke` need the administrator (`require_admin(db)`; anything else exits 1 with `error: forbidden: ...`).
- A waiver reference is a key (`P999/psets.valve_data.size_in@1`) or a record id; `_waiver_id` already resolves it.
- `request` scope is `project:<project>`; `approve` and `revoke` use scope `"company"`. Every write opens `open_uow(db)` inside `service_errors()`.
- Fields of `ls` are separated by two spaces. In `ls` call `views.waiver_views(...)` through the module name (`views.`): the test replaces it.

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
`packages/tl-cli/src/tl_cli/schema_waiver.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401
# pyright: reportUnusedImport=false
"""`tl schema waiver request|approve|revoke|ls`: the time-limited exceptions (P1-I8-T05a3).

STUB: this file is the interface P1-I8-T05a3 implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it. `_waiver_id` and the group are complete.

A waiver relaxes one property for one project until a date (at most 366 days ahead). Asking is any
signed-in person's; approving and revoking are the administrator's, and the person who asked
cannot approve (FANOUT D2, D5). The rules are the module's (`tl_mod_schemareg.handlers.waivers`);
these commands parse options, make one call and print. A refusal of the module is
`error: <message>` on stderr and exit code 1.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_schemareg import registry, views
from tl_mod_schemareg.handlers.waivers import (
    ApproveWaiver,
    RequestWaiver,
    RevokeWaiver,
    handle_approve_waiver,
    handle_request_waiver,
    handle_revoke_waiver,
)

from tl_cli.derive_support import DEV_ACTOR, SOURCE, Actor, acting, cell, fail, service_errors
from tl_cli.session import require_admin, require_session

app = typer.Typer(help="Ask for, approve, revoke and list waivers.", no_args_is_help=True)

_Ref = Annotated[str, typer.Argument(help="A waiver id or key, for example P123/psets.a.b@1.")]


def _waiver_id(db: DbTarget, ref: str) -> str:
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = registry.find_waiver(uow.conn(), ref)
    if found is None:
        fail(f"no waiver {ref!r}")
    return found.id


@app.command("request")
def request(
    ctx: typer.Context,
    project: Annotated[str, typer.Argument(help="The project, for example P123.")],
    path: Annotated[
        str, typer.Argument(help="The property, for example psets.valve_data.size_in.")
    ],
    reason: Annotated[str, typer.Option("--reason", help="Why the property is relaxed.")],
    expires: Annotated[str, typer.Option("--expires", help="The last day, YYYY-MM-DD.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Ask to relax a property for a project until a date. Prints `requested <key> <id>`."""
    # STEPS
    # 1. db = ctx.obj; require_session(db).
    # 2. In `with service_errors(), open_uow(db) as uow:` call handle_request_waiver with
    #    RequestWaiver(actor=acting(db, actor), source=SOURCE, scope=f"project:{project}",
    #    project=project, path=path, reason=reason, expires=expires); keep the CommandResult.
    # 3. Print `requested <result.key> <result.stream_id>`.
    raise NotImplementedError("STEPS: see the comments")


@app.command("approve")
def approve(
    ctx: typer.Context,
    ref: _Ref,
    comment: Annotated[str | None, typer.Option("--comment")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Approve a requested waiver (admin; never the person who asked). Prints `approved <key>`."""
    # STEPS
    # 1. db = ctx.obj; require_admin(db); waiver_id = _waiver_id(db, ref).
    # 2. In `with service_errors(), open_uow(db) as uow:` call handle_approve_waiver with
    #    ApproveWaiver(actor=acting(db, actor), source=SOURCE, scope="company",
    #    waiver_id=waiver_id, comment=comment).
    # 3. Print `approved <result.key>`.
    raise NotImplementedError("STEPS: see the comments")


@app.command("revoke")
def revoke(
    ctx: typer.Context,
    ref: _Ref,
    reason: Annotated[str, typer.Option("--reason", help="Why; kept in the ledger.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Revoke an approved waiver, or refuse a requested one (admin). Prints `revoked <key>`."""
    # STEPS
    # 1. As in approve: require_admin, _waiver_id, then handle_revoke_waiver with
    #    RevokeWaiver(actor, source, scope="company", waiver_id=waiver_id, reason=reason).
    # 2. Print `revoked <result.key>`.
    raise NotImplementedError("STEPS: see the comments")


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: Annotated[str | None, typer.Option("--project", help="Only this project.")] = None,
    state: Annotated[
        str | None, typer.Option("--state", help="Requested, Approved or Revoked.")
    ] = None,
) -> None:
    """List waivers, one line each.

    `<key>  <state>  until <expires>  by <requester>  approver <name or ->`; an approved waiver
    whose day has passed shows `Approved (expired)` as its state. With none: `no waivers`.
    """
    # STEPS
    # 1. db = ctx.obj; require_session(db).
    # 2. In `with service_errors(), open_uow(db, readonly=True) as uow:` call
    #    views.waiver_views(uow.conn(), project, state) (call it through `views.`, the test
    #    replaces it).
    # 3. No rows: print `no waivers` and return. Otherwise one line per row, fields separated
    #    by two spaces: key; state (`<state> (expired)` when the row's `expired` is true);
    #    `until <expires>`; `by <requested_by>`; `approver <cell(approver)>`.
    raise NotImplementedError("STEPS: see the comments")
```

The commands the handlers take (read-only; from `tl_mod_schemareg.handlers.waivers`):
```python
class RequestWaiver(Command):   # extra fields forbidden
    project: str
    path: str
    reason: str
    expires: str          # YYYY-MM-DD

class ApproveWaiver(Command):
    waiver_id: str
    comment: str | None = None

class RevokeWaiver(Command):
    waiver_id: str
    reason: str

# every Command also has: actor: str, source: str, scope: str
def handle_request_waiver(uow, cmd: RequestWaiver) -> CommandResult: ...
def handle_approve_waiver(uow, cmd: ApproveWaiver) -> CommandResult: ...
def handle_revoke_waiver(uow, cmd: RevokeWaiver) -> CommandResult: ...

class CommandResult(BaseModel):
    stream_id: str        # the waiver's record id
    key: str | None       # <project>/<path>@<n>
```

From `tl_mod_schemareg.views` (read-only):
```python
class WaiverView(BaseModel):  # frozen
    id: str
    key: str
    project: str
    path: str
    number: int
    reason: str
    expires: str
    expired: bool         # approved and its last day has passed
    state: str            # Requested, Approved or Revoked
    requested_by: str
    approver: str | None

def waiver_views(conn: Connection, project: str | None = None, state: str | None = None) -> list[WaiverView]: ...
```

From `tl_cli` (read-only): `DEV_ACTOR`, `SOURCE`, `Actor`, `acting(db, actor)`, `cell(value, width=40)` (a dash for none) and `service_errors()` in `tl_cli.derive_support`; `require_admin(db)` and `require_session(db)` in `tl_cli.session`.
```text

```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/schema_waiver.py` (the stub)
- `docs/tickets/P1-I8/provided/t05a3-test_cli_schema_waiver.py.txt`
- `packages/tl-cli/src/tl_cli/schema_gov.py` (the finished governance commands of the same group: the style to follow)
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/schema_waiver.py` (modify: the four function bodies, the stub paragraph and directives, the unused imports)
- `packages/tl-cli/tests/test_cli_schema_waiver.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I8/P1-I8-T05a3.md` (create: your report; commit it)

## Steps
1. Copy the provided test to `packages/tl-cli/tests/test_cli_schema_waiver.py`. Do not edit the copy (it is ruff-clean and pyright-clean as provided).
2. Run it once; all cases fail against the stub.
3. Write the four bodies by their STEPS and docstrings. Remove the STUB paragraph, the two directive lines, every STEPS comment and every `raise NotImplementedError` line, and the imports the finished file does not use.
4. Run the commands under *Acceptance*.

## Acceptance
```
uv run ruff format packages/tl-cli
uv run pytest packages/tl-cli/tests/test_cli_schema_waiver.py packages/tl-cli/tests/test_cli_schema_gov.py -q --adapters sqlite,postgres --basetemp=/tmp/pt-t05a3
just check
```
Expected: all pass on both adapters (the provided file has ten cases; the one that signs in a second account skips on Postgres); `just check` is clean (run it with a 600 000 ms timeout). Remove `/tmp/pt-t05a3` after you have read the exit code.

## Tests to add
None beyond the provided file. If you think a case is missing, say so under *Open questions* in the report; do not edit the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), committed at `docs/reports/P1-I8/P1-I8-T05a3.md`. Deviations first. Paste the last lines of each acceptance command.

## Escalation triggers
- Stop and report *Blocked* if a provided test fails and you cannot see a difference between your reading of the STEPS and the test after two attempts.
- Stop if the pasted interface and the repository disagree.
- Stop if you would have to change a provided test or any file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
