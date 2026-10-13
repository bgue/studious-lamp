# P1-I2-T09a — `tl doc`: register, show, ls, update, supersede, void

Status: ready
Tier: haiku
Labels: cli
Depends on: S3 and S4 on `p1/i2`; no other ticket
Branch: `p1/i2-t09a-cli-doc`

## Goal
A document controller works with the register from the shell. `packages/tl-cli/src/tl_cli/doc.py` has the helpers and the six commands' signatures, options and docstrings final; the six bodies raise `NotImplementedError`. The group is already registered in `tl_cli/main.py` as `tl doc`. You implement the bodies. One provided test file (13 test functions) must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Brief 9 M1.** `Document`: doc number (pattern-validated), title, type, discipline, originator, confidentiality, current revision, status. Workflow: Draft -> Registered -> In Review -> Issued -> Superseded/Void. Links can pin a revision or float.
>
> **Brief 7.3.** Automatic health checks: target voided or superseded -> `stale`.
>
> **P1-I2 demo (07-phase1-plan.md).** register `ISO-1234` rev A (IFR) with a PDF rendition; link a tag to it pinned; issue rev B (IFC); the tag's link shows `stale`; re-pin shows the revision diff summary; a transmittal lists rev B.

### Specification
- **Output is part of the contract**: the test compares lines exactly. The STEPS give the formats.
- A command takes the ledger from the root `--db` (`ctx.obj`), the project from `--project`, and an actor from `--actor` (the default `user:dev` is replaced by the signed-in user by the root; do not change the default text).
- A failure prints `error: <message>` on stderr and exits 1 with no traceback. `_service_errors()` does that for every service failure, prints one `  - <segment>: <message> (<level>)` line per problem when a document number is refused, and turns an input-validation failure into `error: <field>: <message>`.
- Rules are in the handlers: a command makes one call and prints. Look a document up by number with `_document(...)` (it exits `error: no document 'X' in project 'P'`).
- Reads (`show`, `ls`) open the unit of work with `readonly=True`; writes use `open_uow(db)`.
- `tl doc void` needs the admin role: call `require_admin(db)` before anything else (it ends the command with an error line for anyone else). Every other command here is open to any signed-in person.
- The test makes revisions, files and links with the module's own test world (`tl_mod_documents.testing`, through `tests/doccli_support.py`, both already in the tree); it never calls the `tl doc rev` commands, which belong to another ticket.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/doc.py` (the stub you complete):
```python
"""The `tl doc` group: register, show, list and change controlled documents (brief 9 M1; T09a).

Each subcommand parses options, makes one call into `tl_mod_documents` (a handler or a read) and
prints. The rules (the number pattern, the code lists, the revision scheme, what a void document
does to its links) live in the module. Documents are named by number; the project comes from
`--project`. Revisions, renditions, links and reports are the groups `tl doc rev`, `tl doc
rendition`, `tl doc link` and `tl doc report`.

STUB (P1-I2-T09a): the bodies of the six commands raise NotImplementedError; their signatures,
options, docstrings and the helpers (`_fail`, `_service_errors`, `_document`, `_current_text`,
`_revision_line`) are final. Each body has a STEPS comment. Implement them, then delete this
paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any, NoReturn

import typer
from pydantic import ValidationError
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_core.uow import UnitOfWork
from tl_mod_documents import registry
from tl_mod_documents.errors import InvalidDocumentNumberError
from tl_mod_documents.handlers.documents import (
    RegisterDocument,
    SupersedeDocument,
    UpdateDocument,
    VoidDocument,
    handle_register_document,
    handle_supersede_document,
    handle_update_document,
    handle_void_document,
)
from tl_mod_documents.handlers.revisions import CreateRevision, handle_create_revision

from tl_cli.session import require_admin

app = typer.Typer(help="Register, show and change controlled documents.", no_args_is_help=True)

_DEFAULT_ACTOR = "user:dev"
_Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]
_Actor = Annotated[str, typer.Option("--actor", help="Actor recorded on events.")]
_Reason = Annotated[str, typer.Option("--reason", help="Why (kept in the history).")]

_LINKS_SQL = text(
    "SELECT COUNT(*) AS total, "
    "COALESCE(SUM(CASE WHEN status = 'stale' THEN 1 ELSE 0 END), 0) AS stale "
    "FROM cur_links WHERE to_id = :id AND status IN ('active', 'stale')"
)


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a service, concurrency or input-validation failure into `error:` on stderr, exit 1.

    A document number the registry pattern refuses prints one `  - <segment>: <message>
    (<level>)` line per problem.
    """
    try:
        yield
    except InvalidDocumentNumberError as exc:
        typer.echo(f"error: {exc}", err=True)
        for issue in exc.issues:
            where = issue["segment"] or "number"
            typer.echo(f"  - {where}: {issue['message']} ({issue['level']})", err=True)
        raise typer.Exit(code=1) from exc
    except (ServiceError, ConcurrencyError) as exc:
        _fail(str(exc))
    except ValidationError as exc:
        _fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))


def _document(uow: UnitOfWork, scope: str, project: str, number: str) -> registry.DocumentRow:
    found = registry.find_document(uow.conn(), scope, number)
    if found is None:
        _fail(f"no document {number!r} in project {project!r}")
    return found


def _current_text(row: registry.DocumentRow) -> str:
    """``B IFC construction 2026-10-14``, or ``-`` while no revision is issued."""
    if row.current_revision_code is None:
        return "-"
    parts = [
        row.current_revision_code,
        row.current_revision_status or "-",
        row.current_revision_class or "-",
        row.current_revision_issued_on or "-",
    ]
    return " ".join(parts)


def _revision_line(rev: registry.RevisionRow) -> str:
    current = " current" if rev.is_current else ""
    return (
        f"revision {rev.code} {'Void' if rev.voided else rev.state} {rev.issue_status or '-'} "
        f"{rev.status_class or '-'} {rev.issued_on or '-'}{current}"
    )


@app.command("register")
def register(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document number, for example ISO-1234.")],
    project: _Project,
    title: Annotated[str, typer.Option("--title", help="The document title.")],
    doc_type: Annotated[str | None, typer.Option("--type", help="Document type code.")] = None,
    discipline: Annotated[str | None, typer.Option("--discipline")] = None,
    originator: Annotated[str | None, typer.Option("--originator")] = None,
    confidentiality: Annotated[str | None, typer.Option("--confidentiality")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    scheme: Annotated[
        str | None, typer.Option("--scheme", help="Revision scheme; default from the scheme file.")
    ] = None,
    first_revision: Annotated[
        bool, typer.Option("--first-revision", help="Also start the first revision, as a draft.")
    ] = False,
    purpose: Annotated[
        str | None, typer.Option("--purpose", help="Purpose of the first revision.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Register a document under its number. The number must fit the registry pattern."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}"; common = {"actor": actor,
    #    "source": "cli", "scope": scope}.
    # 2. Inside `with _service_errors(), open_uow(db) as uow:` made =
    #    handle_register_document(uow, RegisterDocument(**common, number=number, title=title,
    #    description=description, doc_type=doc_type, discipline=discipline,
    #    originator=originator, confidentiality=confidentiality, revision_scheme=scheme)).
    # 3. With --first-revision, still inside the block: started = handle_create_revision(uow,
    #    CreateRevision(**common, document_id=made.stream_id, purpose=purpose,
    #    correlation_id=made.events[0].correlation_id)); revision = started.key.
    # 4. Still inside the block: row = _document(uow, scope, project, number).
    # 5. After the block print f"registered {made.stream_id}", f"document {row.number}", f"state
    #    {row.state}", f"scheme {row.revision_scheme}" and, when a revision was started,
    #    f"revision {code} Draft" where code is the part of the revision key after the last "@".
    raise NotImplementedError


@app.command("show")
def show(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document number.")],
    project: _Project,
) -> None:
    """Show a document: its register fields, its current revision, its revisions, its links."""
    # STEPS
    # 1. Inside `with _service_errors(), open_uow(db, readonly=True) as uow:` row =
    #    _document(uow, scope, project, number); revisions = registry.revisions_of(uow.conn(),
    #    row.id); links = uow.conn().execute(_LINKS_SQL, {"id": row.id}).one(); replaced_by =
    #    registry.get_document( uow.conn(), row.superseded_by) when row.superseded_by is set,
    #    else None.
    # 2. After the block print `name: value` lines in this order: id, number, title, state, type
    #    (doc_type or "-"), discipline ("-"), originator ("-"), confidentiality ("-"), scheme
    #    (revision_scheme), pattern (pattern_code or "-"), current (_current_text(row)),
    #    superseded_by (replaced_by.number or "-"), conformance, version.
    # 3. Then one `_revision_line(rev)` per revision, then f"links: {int(links.total)}
    #    ({int(links.stale)} stale)".
    raise NotImplementedError


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: _Project,
    doc_type: Annotated[str | None, typer.Option("--type")] = None,
    discipline: Annotated[str | None, typer.Option("--discipline")] = None,
    state: Annotated[str | None, typer.Option("--state", help="For example Issued.")] = None,
    include_void: Annotated[bool, typer.Option("--all", help="Include void documents.")] = False,
    limit: Annotated[int, typer.Option("--limit", min=1, max=5000)] = 1000,
) -> None:
    """List a project's documents by number: number, state, current, type, discipline, title."""
    # STEPS
    # 1. Inside `with _service_errors(), open_uow(db, readonly=True) as uow:` rows =
    #    registry.list_documents( uow.conn(), f"project:{project}", doc_type=doc_type,
    #    discipline=discipline, state=state, limit=limit, include_void=include_void).
    # 2. One line per row: number, state, current, doc_type or "-", discipline or "-", title
    #    joined with two spaces, where current is "-" when row.current_revision_code is None,
    #    else f"{row.current_revision_code}({row.current_revision_status})".
    raise NotImplementedError


@app.command("update")
def update(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document number.")],
    project: _Project,
    title: Annotated[str | None, typer.Option("--title")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    doc_type: Annotated[str | None, typer.Option("--type")] = None,
    discipline: Annotated[str | None, typer.Option("--discipline")] = None,
    originator: Annotated[str | None, typer.Option("--originator")] = None,
    confidentiality: Annotated[str | None, typer.Option("--confidentiality")] = None,
    reason: Annotated[str | None, typer.Option("--reason")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Change a document's title or register fields. An empty value ('') clears a field."""
    # STEPS
    # 1. given = the six options as a dict by field name (title, description, doc_type,
    #    discipline, originator, confidentiality). fields = {name: (value or None) for each
    #    option that is not None}: an empty string clears a field. No field given: _fail("give
    #    at least one field to change (--title, --type, --discipline, ...)") (type the dict as
    #    dict[str, Any]).
    # 2. Inside `with _service_errors(), open_uow(db) as uow:` row = _document(uow, scope,
    #    project, number); handle_update_document(uow, UpdateDocument(actor=actor, source="cli",
    #    scope=scope, stream_id=row.id, reason=reason, **fields)).
    # 3. After the block print f"updated {number}".
    raise NotImplementedError


@app.command("supersede")
def supersede(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document to replace.")],
    project: _Project,
    by: Annotated[str, typer.Option("--by", help="The number of the document that replaces it.")],
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Replace a document by another one. Every link to the old one goes stale."""
    # STEPS
    # 1. Inside `with _service_errors(), open_uow(db) as uow:` old = _document(uow, scope,
    #    project, number); new = _document(uow, scope, project, by);
    #    handle_supersede_document(uow, SupersedeDocument(actor=actor, source="cli",
    #    scope=scope, stream_id=old.id, superseded_by_id=new.id, reason=reason)).
    # 2. After the block print f"superseded {number} by {by}".
    raise NotImplementedError


@app.command("void")
def void(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document number.")],
    project: _Project,
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Void a document registered in error (admin). Every link to it goes stale."""
    # STEPS
    # 1. require_admin(db) first (it exits with an error line for anyone who is not an admin).
    # 2. Inside `with _service_errors(), open_uow(db) as uow:` row = _document(...);
    #    handle_void_document(uow, VoidDocument(actor=actor, source="cli", scope=scope,
    #    stream_id=row.id, reason=reason)).
    # 3. After the block print f"voided {number}".
    raise NotImplementedError
```

`packages/tl-modules/documents/src/tl_mod_documents/handlers/documents.py` and `revisions.py` (commands and handler signatures):
```python
class RegisterDocument(Command):
    """Register a document in a project under its number. The number becomes the record key.

    The number must fit the registry numbering pattern for documents when there is one. The type
    and the discipline must be usable values of the code lists ``DocumentType`` and ``Discipline``
    when the company has registered them. The revision scheme defaults from the scheme file.
    """

    model_config = ConfigDict(extra="forbid")

    number: str = Field(min_length=1, max_length=MAX_NUMBER)
    title: str = Field(min_length=1, max_length=MAX_TEXT)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    doc_type: str | None = Field(default=None, max_length=MAX_NUMBER)
    discipline: str | None = Field(default=None, max_length=MAX_NUMBER)
    originator: str | None = Field(default=None, max_length=MAX_TEXT)
    confidentiality: str | None = Field(default=None, max_length=MAX_NUMBER)
    revision_scheme: str | None = Field(default=None, max_length=MAX_NUMBER)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        return _non_blank(value)

class UpdateDocument(Command):
    """Change a document's title, description or register fields (not its number or scheme)."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    doc_type: str | None = Field(default=None, max_length=MAX_NUMBER)
    discipline: str | None = Field(default=None, max_length=MAX_NUMBER)
    originator: str | None = Field(default=None, max_length=MAX_TEXT)
    confidentiality: str | None = Field(default=None, max_length=MAX_NUMBER)
    reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return None if value is None else _non_blank(value)

class SupersedeDocument(Command):
    """Replace a document by another one: the old is Superseded and its links go stale."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    superseded_by_id: str
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)

class VoidDocument(Command):
    """Void a document that was registered in error. Its links go stale. Admin only."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)

def handle_register_document(uow: UnitOfWork, cmd: RegisterDocument) -> CommandResult: ...

def handle_update_document(uow: UnitOfWork, cmd: UpdateDocument) -> CommandResult: ...

def handle_supersede_document(uow: UnitOfWork, cmd: SupersedeDocument) -> CommandResult: ...

def handle_void_document(uow: UnitOfWork, cmd: VoidDocument) -> CommandResult: ...

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

    @field_validator("revision_date")
    @classmethod
    def _date(cls, value: str | None) -> str | None:
        return check_date(value, "revision_date")

def handle_create_revision(uow: UnitOfWork, cmd: CreateRevision) -> CommandResult: ...
```

`packages/tl-modules/documents/src/tl_mod_documents/registry.py` (reads, already written; the parts you use):
```python
@dataclass(frozen=True)
class DocumentRow:
    id: str
    scope: str
    number: str
    title: str
    description: str | None
    state: str  # the document workflow state
    voided: bool
    version: int
    conformance: str
    doc_type: str | None
    discipline: str | None
    originator: str | None
    confidentiality: str | None
    revision_scheme: str
    pattern_code: str | None
    current_revision_id: str | None
    current_revision_code: str | None
    current_revision_status: str | None
    current_revision_class: str | None
    current_revision_issued_on: str | None
    superseded_by: str | None
    created_at: str
    updated_at: str

    @property
    def closed(self) -> bool:
        """True once the document is void or superseded: it takes no more changes."""
        return self.voided or self.state in ("Void", "Superseded")

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

def find_document(conn: Connection, scope: str, number: str) -> DocumentRow | None: ...

def get_document(conn: Connection, document_id: str) -> DocumentRow | None: ...

def list_documents(
    conn: Connection,
    scope: str,
    *,
    doc_type: str | None = None,
    discipline: str | None = None,
    state: str | None = None,
    limit: int = 500,
    offset: int = 0,
    include_void: bool = False,
) -> list[DocumentRow]: ...

def revisions_of(
    conn: Connection, document_id: str, *, include_void: bool = True
) -> list[RevisionRow]: ...
```

`packages/tl-cli/src/tl_cli/session.py`:
```python
def require_admin(db: DbTarget) -> Principal: ...
# Exits with `error: forbidden: this command needs the admin role` for anyone who is not an admin.
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/doc.py` (the file you edit)
- `packages/tl-cli/src/tl_cli/tag.py` (a finished group of the same shape; read it for style)
- `packages/tl-modules/documents/src/tl_mod_documents/registry.py`
- `packages/tl-cli/tests/doccli_support.py` (the test helpers, already in the tree)
- `docs/tickets/P1-I2/provided/t09a-test_cli_doc.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `standard` for `packages/tl-modules`, `tl-cli`, `tl-api`; strict for `tl_core`, `tl_schema`, `tl_adapters`.
- Provided files live under `docs/tickets/P1-I2/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I2/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8). A test that does not use the `db`, `world` or `engine` fixtures runs once under `--adapters sqlite,postgres`; one that does runs once per adapter (L-P1-I1-6).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*`, `hist_*` or `v_*` object, and never change `schema/**` or anything under `generated/` unless this ticket says so.
- `just test-parity` takes about 70 minutes for the whole repository (L-P1-I1-10): run the scoped command in *Acceptance*, never the whole parity suite.
- Start Postgres with `sudo pg_ctlcluster 16 main start` if it is not running; `TL_PG_URL` is `postgresql://postgres:postgres@localhost:5432/tl_test`.
- On Postgres the tl-cli `conftest.py` signs a test user in for you (L-P1-I0B-8); `tl doc void` on SQLite needs the admin the test bootstraps; the test skips the refusal part on Postgres (every command there runs as an admin).

## Allowed paths
- `packages/tl-cli/src/tl_cli/doc.py` (edit)
- `packages/tl-cli/tests/test_cli_doc.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T09a.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t09a-test_cli_doc.py.txt` to `packages/tl-cli/tests/test_cli_doc.py`.
3. Implement the six commands by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_doc.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-cli/tests/test_cli_doc.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli -q
```
Expected: `just check` clean; 13 passed on SQLite; 26 passed with both adapters (about 80 seconds); the whole tl-cli package passes.

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
