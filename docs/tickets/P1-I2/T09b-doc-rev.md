# P1-I2-T09b — `tl doc rev`: create, issue, supersede, void, ls

Status: ready
Tier: haiku
Labels: cli
Depends on: S3, S4 and S6 on `p1/i2`; no other ticket
Branch: `p1/i2-t09b-cli-doc-rev`

## Goal
A document controller starts, issues, supersedes and voids the revisions of a document from the shell. `packages/tl-cli/src/tl_cli/doc_rev.py` has the group, its helpers and the five commands' signatures, options and docstrings final; the five bodies raise `NotImplementedError`. The group is already registered as `tl doc rev` in `tl_cli/main.py`. You implement the bodies. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Brief 9 M1.** `Revision`: code per scheme, date, purpose, status IFR/IFC/AFC/As-Built/Void, reviewer comments. Workflow: Draft -> Registered -> In Review -> Issued -> Superseded/Void. One current revision per status class; superseded revisions are retained and shown as superseded.
>
> **ADR-0011.** Issuing and superseding a revision are the admin's acts (`admin.command.IssueRevision`, `admin.command.SupersedeRevision`; the CLI calls `require_admin`). Creating and voiding a draft are open to any signed-in person.
>
> **P1-I2 demo.** `tl doc rev create ISO-1234 --project P123 --purpose "Issued for construction"`, then `tl doc rev issue ISO-1234 B --project P123 --status IFC` (the tag's link goes stale).

### Specification
- **Output is part of the contract**: the test compares lines exactly. The STEPS give the formats.
- A command takes the ledger from the root `--db` (`ctx.obj`), the project from `--project`, and an actor from `--actor` (the default `user:dev` is replaced by the signed-in user by the root; do not change the default text).
- A failure prints `error: <message>` on stderr and exits 1 with no traceback. `_service_errors()` does that for every service failure and turns an input-validation failure into `error: <field>: <message>`.
- Rules are in the handlers: a command makes one call and prints. A revision is looked up by document number and code with `_revision(...)` (it exits `error: no revision 'X' of N`).
- `issue` and `supersede` call `require_admin(db)` before anything else; `create`, `void` and `ls` are open to any signed-in person.
- Reads (`ls`) open the unit of work with `readonly=True`; writes use `open_uow(db)`.
- The test makes documents, files and links with the module's own test world (`tl_mod_documents.testing`, through `tests/doccli_support.py`, both already in the tree).

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/doc_rev.py` (the stub you complete):
```python
"""The `tl doc rev` group: start, issue, supersede, void and list the revisions of a document.

Each subcommand parses options, makes one call into `tl_mod_documents` (a handler or a read) and
prints. The rules (the revision scheme, one open revision, the status classes, stale pins, dates)
live in the module. A revision is named by its document number and its code (`ISO-1234 A`); the
project comes from `--project`. Issuing and superseding a revision are an admin's acts (ADR-0011).

STUB (P1-I2-T09b): the bodies of the five commands raise NotImplementedError; their signatures,
options, docstrings and the helpers are final. Each body has a STEPS comment. Implement them,
then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core.uow import UnitOfWork
from tl_mod_documents import registry
from tl_mod_documents.handlers.revisions import (
    CreateRevision,
    IssueRevision,
    SupersedeRevision,
    VoidRevision,
    handle_create_revision,
    handle_issue_revision,
    handle_supersede_revision,
    handle_void_revision,
)

from tl_cli.doc import (
    _DEFAULT_ACTOR,
    _Actor,
    _document,
    _fail,
    _Project,
    _Reason,
    _revision_line,
    _service_errors,
)
from tl_cli.session import require_admin

app = typer.Typer(help="Start, issue, supersede, void and list revisions.", no_args_is_help=True)

_Number = Annotated[str, typer.Argument(help="The document number, for example ISO-1234.")]
_Code = Annotated[str, typer.Argument(help="The revision code, for example A.")]


def _revision(
    uow: UnitOfWork, scope: str, project: str, number: str, code: str
) -> registry.RevisionRow:
    """The revision ``code`` of document ``number``; exits `error: no revision 'X' of N`."""
    doc = _document(uow, scope, project, number)
    found = registry.find_revision(uow.conn(), doc.id, code)
    if found is None:
        _fail(f"no revision {code!r} of {number}")
    return found


@app.command("create")
def create(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    code: Annotated[str | None, typer.Option("--code", help="Default: the next code.")] = None,
    stage: Annotated[str | None, typer.Option("--stage", help="For a staged scheme.")] = None,
    purpose: Annotated[str | None, typer.Option("--purpose")] = None,
    change_note: Annotated[str | None, typer.Option("--change-note")] = None,
    intended_status: Annotated[str | None, typer.Option("--intended-status")] = None,
    revision_date: Annotated[str | None, typer.Option("--date", help="YYYY-MM-DD.")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Start the next revision of a document, as a draft. Prints `created revision <code> Draft`."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db) as uow:` row = _document(uow, scope, project,
    #    number); made = handle_create_revision(uow, CreateRevision(actor=actor, source="cli",
    #    scope=scope, document_id=row.id, code=code, stage=stage, purpose=purpose,
    #    change_note=change_note, revision_date=revision_date, intended_status=intended_status)).
    # 3. made.key is `ISO-1234@A`: the code is made.key.rsplit("@", 1)[-1].
    # 4. Print `created revision <code> Draft`.
    raise NotImplementedError


@app.command("issue")
def issue(
    ctx: typer.Context,
    number: _Number,
    code: _Code,
    project: _Project,
    status: Annotated[str, typer.Option("--status", help="Issue status, for example IFR.")],
    issued_on: Annotated[
        str | None, typer.Option("--date", help="YYYY-MM-DD. Default today; never in the future.")
    ] = None,
    date_reason: Annotated[
        str | None, typer.Option("--date-reason", help="Required for a date before today.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Issue a draft revision (admin). Links pinned to other revisions go stale."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}"; call require_admin(db) first.
    # 2. `with _service_errors(), open_uow(db) as uow:` rev = _revision(uow, scope, project,
    #    number, code); result = handle_issue_revision(uow, IssueRevision(actor=actor,
    #    source="cli", scope=scope, stream_id=rev.id, issue_status=status, issued_on=issued_on,
    #    date_reason=date_reason)); issued = _revision(uow, scope, project, number, code).
    # 3. flagged = the number of events of result.events whose event_type is "Link.Flagged".
    # 4. Print `issued <number>@<code> as <status> on <issued.issued_on>`; when flagged > 0 print
    #    `flagged <flagged> link(s) stale` using "link" for 1 and "links" otherwise.
    raise NotImplementedError


@app.command("supersede")
def supersede(
    ctx: typer.Context,
    number: _Number,
    code: _Code,
    project: _Project,
    by: Annotated[str, typer.Option("--by", help="The code of the revision that replaces it.")],
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Mark an issued revision as replaced by another issued one (admin)."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}"; call require_admin(db) first.
    # 2. `with _service_errors(), open_uow(db) as uow:` old = _revision(uow, scope, project,
    #    number, code); new = _revision(uow, scope, project, number, by);
    #    handle_supersede_revision(uow, SupersedeRevision(actor=actor, source="cli",
    #    scope=scope, stream_id=old.id, superseded_by_id=new.id, reason=reason)).
    # 3. Print `superseded <number>@<code> by <by>`.
    raise NotImplementedError


@app.command("void")
def void(
    ctx: typer.Context,
    number: _Number,
    code: _Code,
    project: _Project,
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Void a draft revision started in error. An issued revision is superseded, never voided."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db) as uow:` rev = _revision(uow, scope, project,
    #    number, code); handle_void_revision(uow, VoidRevision(actor=actor, source="cli",
    #    scope=scope, stream_id=rev.id, reason=reason)).
    # 3. Print `voided <number>@<code>`.
    raise NotImplementedError


@app.command("ls")
def ls(ctx: typer.Context, number: _Number, project: _Project) -> None:
    """List the revisions of a document, oldest first, one `revision ...` line each."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` row = _document(uow,
    #    scope, project, number); revisions = registry.revisions_of(uow.conn(), row.id).
    # 3. Print `_revision_line(rev)` for each revision (the helper is final).
    raise NotImplementedError
```

`packages/tl-modules/documents/src/tl_mod_documents/handlers/revisions.py` (excerpts; read-only, do not edit):
```python
class CreateRevision(Command):
    """Start a new revision of a document, as a draft.

    ``code`` defaults to the next code of the document's scheme; ``stage`` starts a new stage of a
    staged scheme (``C`` after ``P3``). The revision date defaults to today.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: str
    code: str | None = Field(default=None, min_length=1, max_length=MAX_NUMBER)
    stage: str | None = Field(default=None, max_length=MAX_NUMBER)
    purpose: str | None = Field(default=None, max_length=MAX_TEXT)
    change_note: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    revision_date: str | None = None
    intended_status: str | None = Field(default=None, max_length=MAX_NUMBER)


class IssueRevision(Command):
    """Issue a draft revision with an issue status (IFR, IFC, AFC, ASB). Admin only."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    issue_status: str = Field(min_length=1, max_length=MAX_NUMBER)
    #: Defaults to today. Never in the future; a date before today needs ``date_reason``.
    issued_on: str | None = None
    date_reason: str | None = Field(default=None, max_length=MAX_REASON)


class SupersedeRevision(Command):
    """Mark an issued, current revision superseded by a later issued revision of the document."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    superseded_by_id: str
    reason: str = Field(max_length=MAX_REASON)


class VoidRevision(Command):
    """Void a draft revision created in error. An issued revision is superseded, not voided."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)
```

`packages/tl-modules/documents/src/tl_mod_documents/registry.py` (excerpts; read-only, do not edit):
```python
@dataclass(frozen=True)
class RevisionRow:
    id: str
    scope: str
    document_id: str
    document_number: str
    key: str
    title: str
    code: str
    ordinal: int
    state: str  # Draft, In Review, Issued, Superseded, Void
    voided: bool
    version: int
    previous_revision_id: str | None
    purpose: str | None
    change_note: str | None
    revision_date: str | None
    intended_status: str | None
    issue_status: str | None
    status_class: str | None
    issued_on: str | None
    is_current: bool
    superseded_by: str | None

    @property
    def issued(self) -> bool:
        return self.issued_on is not None

    @property
    def open(self) -> bool:
        return self.state in OPEN_STATES and not self.voided
```

`packages/tl-modules/documents/src/tl_mod_documents/registry.py` (excerpts; read-only, do not edit):
```python
def find_revision(conn: Connection, document_id: str, code: str) -> RevisionRow | None:
    ...


def revisions_of(
    conn: Connection, document_id: str, *, include_void: bool = True
) -> list[RevisionRow]:
    """The revisions of a document, oldest first (by ordinal)."""
    ...
```

`packages/tl-cli/src/tl_cli/session.py`:
```python
def require_admin(db: DbTarget) -> Principal: ...
# Exits with `error: forbidden: this command needs the admin role` for anyone who is not an admin.
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/doc_rev.py` (the file you edit)
- `packages/tl-cli/src/tl_cli/doc.py` and `packages/tl-cli/src/tl_cli/doc_rev.py` (the helpers you import; do not edit)
- `packages/tl-cli/src/tl_cli/tag.py` (a finished group of the same shape; style)
- `packages/tl-modules/documents/src/tl_mod_documents/registry.py`
- `packages/tl-cli/tests/doccli_support.py` (the test helpers, already in the tree)
- `docs/tickets/P1-I2/provided/t09b-test_cli_doc_rev.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `standard` for `packages/tl-cli`.
- Provided files live under `docs/tickets/P1-I2/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I2/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8). A test that does not use the `db`, `world` or `engine` fixtures runs once under `--adapters sqlite,postgres`; one that does runs once per adapter (L-P1-I1-6).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*`, `hist_*` or `v_*` object, and never change `schema/**` or anything under `generated/` unless this ticket says so.
- `just test-parity` takes about 70 minutes for the whole repository (L-P1-I1-10): run the scoped command in *Acceptance*, never the whole parity suite.
- Start Postgres with `sudo pg_ctlcluster 16 main start` if it is not running; `TL_PG_URL` is `postgresql://postgres:postgres@localhost:5432/tl_test`.
- On Postgres the tl-cli `conftest.py` signs a test admin in for you (L-P1-I0B-8); a command that needs the admin role runs as that admin there, and the test skips the refusal part (`doccli_support.admin_session` returns False).
- A signed-in person is needed for the admin commands of this group on SQLite: the test bootstraps `root` and signs in (`admin_session`), then `ordinary_env` gives a second, non-admin person.
- `doc.py` is merged and final. `doc_rev.py` is another ticket's file (T09b): its helpers `_Number`, `_Code` and `_revision` are final in the tree, its command bodies may still be stubs. Import the helpers; do not copy them and do not edit either file.

## Allowed paths
- `packages/tl-cli/src/tl_cli/doc_rev.py` (edit)
- `packages/tl-cli/tests/test_cli_doc_rev.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T09b.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t09b-test_cli_doc_rev.py.txt` to `packages/tl-cli/tests/test_cli_doc_rev.py`.
3. Implement the commands by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_doc_rev.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-cli/tests/test_cli_doc_rev.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli -q
```
Expected: `just check` clean; 9 test functions pass on SQLite and again on Postgres; the whole tl-cli package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of the parity run.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change in `tl_mod_documents` or in another `tl_cli` file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
