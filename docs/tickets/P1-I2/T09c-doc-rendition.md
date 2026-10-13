# P1-I2-T09c — `tl doc rendition`: add, replace-signed, ls

Status: ready
Tier: haiku
Labels: cli
Depends on: S3, S4 and S6 on `p1/i2`; no other ticket (T09b is not needed: `doc_rev.py` is already in the tree as the final module it will be)
Branch: `p1/i2-t09c-cli-doc-rendition`

## Goal
A document controller adds a file to a revision as a controlled rendition from the shell. `packages/tl-cli/src/tl_cli/doc_rendition.py` has the group, the upload helper (final, complete) and the three commands' signatures, options and docstrings final; the three bodies raise `NotImplementedError`. The group is already registered as `tl doc rendition`. You implement the bodies. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Brief 9 M1.** `Rendition`: hash, filename, MIME, size, page count, native/PDF/markup. **Brief 20.1.** File slots on a revision: `native`, `pdf`, `markup`, `signed`.
>
> **P1-I2 rules (ADR-0010 second addendum).** What a revision accepts depends on its state: Draft takes native, pdf and markup; In Review takes markup; Issued and Superseded take markup and signed; Void takes nothing. The upload itself is refused when the state does not take the kind. A newer native or PDF supersedes the older; a markup is additive; the signed copy is written once and replaced only by the admin command `ReplaceSignedRendition` with a reason (ADR-0011).

### Specification
- **Output is part of the contract**: the test compares lines exactly. The STEPS give the formats.
- A command takes the ledger from the root `--db` (`ctx.obj`), the project from `--project`, and an actor from `--actor` (do not change the default text). The object store comes from the environment (`TL_OBJECT_ROOT`; the test sets it).
- A failure prints `error: <message>` on stderr and exits 1 with no traceback. `_service_errors()` does that for every service failure.
- `_upload` (final) hashes the file, registers it in the revision's slot and completes the upload; it is two units of work, and `AttachRendition` is a third. The slot has the name of the kind.
- `replace-signed` calls `require_admin(db)` before anything else; `add` and `ls` are open to any signed-in person.
- The listing format is part of the contract: two spaces between fields.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/doc_rendition.py` (the stub you complete):
```python
"""The `tl doc rendition` group: add a file to a revision as a controlled rendition, and list them.

A rendition is a file of a revision in one of its four kinds: `native`, `pdf`, `markup`, `signed`.
Adding one is two steps that the module keeps apart: the upload (the file service hashes, scans and
stores the bytes in the revision's slot of that name) and `AttachRendition` (the module registers
the available file as the revision's rendition and supersedes an older native or PDF). The commands
here do both. What a revision accepts depends on its state; the module says so. Replacing a signed
copy is an admin's act (ADR-0011).

STUB (P1-I2-T09c): the bodies of the three commands raise NotImplementedError; their signatures,
options, docstrings and the helpers are final. Each body has a STEPS comment. Implement them,
then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_adapters.objectstore import make_object_store, object_secret
from tl_core.files.service import CompleteUpload, FileService, RegisterUpload
from tl_mod_documents import registry
from tl_mod_documents.handlers.renditions import (
    AttachRendition,
    ReplaceSignedRendition,
    handle_attach_rendition,
    handle_replace_signed_rendition,
)

from tl_cli.doc import (
    _DEFAULT_ACTOR,
    _Actor,
    _fail,
    _Project,
    _Reason,
    _service_errors,
)
from tl_cli.doc_rev import _Code, _Number, _revision
from tl_cli.session import require_admin

app = typer.Typer(help="Add, replace and list the renditions of a revision.", no_args_is_help=True)

KINDS = ("native", "pdf", "markup", "signed")
_CHUNK = 1024 * 1024
_File = Annotated[Path, typer.Argument(help="The file to add.", exists=True, dir_okay=False)]
_Pages = Annotated[int | None, typer.Option("--pages", min=0, help="Page count, if known.")]
_ContentType = Annotated[
    str | None, typer.Option("--content-type", help="Default: guessed from the file name.")
]


def _upload(
    db: DbTarget,
    scope: str,
    actor: str,
    record_id: str,
    slot: str,
    path: Path,
    content_type: str | None,
) -> str:
    """Upload ``path`` into the ``slot`` of the revision record; returns the file id.

    The bytes are hashed first, registered (a file the store already holds is not sent again) and
    completed. A storage setup problem exits `error: ...`.
    """
    media = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    try:
        service = FileService(make_object_store(), secret=object_secret())
    except ValueError as exc:
        _fail(str(exc))
    with _service_errors(), open_uow(db) as uow:
        ticket = service.register_upload(
            uow,
            RegisterUpload(
                actor=actor,
                source="cli",
                scope=scope,
                record_id=record_id,
                slot=slot,
                filename=path.name,
                content_type=media,
                size=path.stat().st_size,
                sha256=digest.hexdigest(),
            ),
        )
        complete = CompleteUpload(
            actor=actor, source="cli", scope=scope, upload_id=ticket.upload_id
        )
        if ticket.exists:
            done = service.complete_upload(uow, complete)
        else:
            with path.open("rb") as source_file:
                done = service.complete_upload(uow, complete, source_file)
    return done.file_id


@app.command("add")
def add(
    ctx: typer.Context,
    number: _Number,
    code: _Code,
    path: _File,
    project: _Project,
    kind: Annotated[str, typer.Option("--kind", help="native, pdf, markup or signed.")],
    pages: _Pages = None,
    content_type: _ContentType = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Upload a file into a revision and register it as a rendition of that kind."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}". If kind is not in KINDS,
    #    _fail(f"kind must be one of {', '.join(KINDS)}").
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` rev = _revision(uow,
    #    scope, project, number, code).
    # 3. file_id = _upload(db, scope, actor, rev.id, kind, path, content_type) (final helper;
    #    the slot has the name of the kind).
    # 4. `with _service_errors(), open_uow(db) as uow:` made = handle_attach_rendition(uow,
    #    AttachRendition(actor=actor, source="cli", scope=scope, revision_id=rev.id,
    #    file_id=file_id, page_count=pages)).
    # 5. Print `attached <kind> <path.name> to <number>@<code>`, then `rendition <made.stream_id>`.
    raise NotImplementedError


@app.command("replace-signed")
def replace_signed(
    ctx: typer.Context,
    number: _Number,
    code: _Code,
    path: _File,
    project: _Project,
    reason: _Reason,
    pages: _Pages = None,
    content_type: _ContentType = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Replace the signed copy of a revision by another file (admin). The reason is kept."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}"; call require_admin(db) first.
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` rev = _revision(uow,
    #    scope, project, number, code).
    # 3. file_id = _upload(db, scope, actor, rev.id, "signed", path, content_type).
    # 4. `with _service_errors(), open_uow(db) as uow:` made = handle_replace_signed_rendition(
    #    uow, ReplaceSignedRendition(actor=actor, source="cli", scope=scope, revision_id=rev.id,
    #    file_id=file_id, page_count=pages, reason=reason)).
    # 5. Print `replaced the signed copy of <number>@<code> with <path.name>` and then
    #    `rendition <made.stream_id>`.
    raise NotImplementedError


@app.command("ls")
def ls(
    ctx: typer.Context,
    number: _Number,
    code: _Code,
    project: _Project,
    all_: Annotated[
        bool, typer.Option("--all", help="Include renditions that were replaced.")
    ] = False,
) -> None:
    """List a revision's renditions: kind, file name, size, pages, sha256 (first 12), state."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` rev = _revision(uow,
    #    scope, project, number, code); rows = registry.renditions_of(uow.conn(), rev.id,
    #    current_only=not all_).
    # 3. For each row print two spaces between: kind, filename, f"{size}B", f"{page_count}p"
    #    (or "-p" when page_count is None), sha256[:12], "current" or "replaced".
    raise NotImplementedError
```

`packages/tl-modules/documents/src/tl_mod_documents/handlers/renditions.py` (excerpts; read-only, do not edit):
```python
class AttachRendition(Command):
    """Register an uploaded, scanned file of a revision as a rendition.

    ``file_id`` is a file attached to the revision in the slot named like the rendition kind.
    ``page_count`` is optional (an extractor fills it in later).
    """

    model_config = ConfigDict(extra="forbid")

    revision_id: str
    file_id: str = Field(min_length=1, max_length=MAX_NUMBER)
    page_count: int | None = Field(default=None, ge=0, le=MAX_PAGES)


class ReplaceSignedRendition(Command):
    """Replace the signed copy of a revision by another file, with a reason (admin).

    The signed copy is write-once for everyone else: a correction is an admin's decision and the
    reason is kept in the event.
    """

    model_config = ConfigDict(extra="forbid")

    revision_id: str
    file_id: str = Field(min_length=1, max_length=MAX_NUMBER)
    page_count: int | None = Field(default=None, ge=0, le=MAX_PAGES)
    reason: str = Field(max_length=MAX_REASON)


def handle_attach_rendition(uow: UnitOfWork, cmd: AttachRendition) -> CommandResult:
    """Append ``Record.Created`` and ``Rendition.Defined``; supersede the previous native or PDF."""
    ...


def handle_replace_signed_rendition(uow: UnitOfWork, cmd: ReplaceSignedRendition) -> CommandResult:
    """Register the file as the signed copy and supersede the current one. Admin only."""
    ...
```

`packages/tl-modules/documents/src/tl_mod_documents/registry.py` (excerpts; read-only, do not edit):
```python
@dataclass(frozen=True)
class RenditionRow:
    id: str
    scope: str
    revision_id: str
    document_id: str
    key: str
    kind: str
    file_id: str
    filename: str
    content_type: str
    size: int
    sha256: str
    page_count: int | None
    is_current: bool
    superseded_by: str | None
    version: int
    created_at: str


def renditions_of(
    conn: Connection, revision_id: str, *, current_only: bool = False, kind: str | None = None
) -> list[RenditionRow]:
    """The renditions of a revision ordered by kind, then oldest first (by creation, id)."""
    ...
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/doc_rendition.py` (the file you edit)
- `packages/tl-cli/src/tl_cli/doc.py` and `packages/tl-cli/src/tl_cli/doc_rev.py` (the helpers you import; do not edit)
- `packages/tl-cli/src/tl_cli/tag.py` (a finished group of the same shape; style)
- `packages/tl-modules/documents/src/tl_mod_documents/registry.py`
- `packages/tl-cli/src/tl_cli/file.py` (`tl file put`, the same upload sequence)
- `packages/tl-cli/tests/doccli_support.py` (the test helpers, already in the tree)
- `docs/tickets/P1-I2/provided/t09c-test_cli_doc_rendition.py.txt` (the test)
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
- `packages/tl-cli/src/tl_cli/doc_rendition.py` (edit)
- `packages/tl-cli/tests/test_cli_doc_rendition.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T09c.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t09c-test_cli_doc_rendition.py.txt` to `packages/tl-cli/tests/test_cli_doc_rendition.py`.
3. Implement the commands by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_doc_rendition.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-cli/tests/test_cli_doc_rendition.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli -q
```
Expected: `just check` clean; 7 test functions pass on SQLite and again on Postgres; the whole tl-cli package passes.

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
