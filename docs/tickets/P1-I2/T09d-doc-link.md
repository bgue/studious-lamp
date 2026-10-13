# P1-I2-T09d — `tl doc link`, `stale`, `diff`, `repin`

Status: ready
Tier: haiku
Labels: cli
Depends on: S3, S4 and S6 on `p1/i2`; no other ticket
Branch: `p1/i2-t09d-cli-doc-link`

## Goal
A person links a record to a document (floating or pinned to a revision), lists the links that went stale, and re-pins one after seeing what changed. `packages/tl-cli/src/tl_cli/doc_link.py` has the four functions' signatures, options and docstrings final (and the helpers); the four bodies raise `NotImplementedError`. `tl_cli/main.py` registers them as `tl doc link`, `stale`, `diff` and `repin`. You implement the bodies. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Brief 7.1.** A link can pin a revision or float (mean the current one). **Brief 7.3.** When a new revision is issued, pinned links go stale; the owner is notified and re-pins with a diff of the two revisions shown before confirming. A target that is voided or superseded makes its links stale.
>
> **P1-I2 demo.** `tl doc link 47-FV-1001 ISO-1234 --project P123 --pin A`; after revision B is issued: `tl doc stale --project P123` lists it; `tl doc repin <link> --project P123` shows the diff summary; `--apply` confirms.

### Specification
- **Output is part of the contract**: the test compares lines exactly. The STEPS give the formats.
- A command takes the ledger from the root `--db` (`ctx.obj`), the project from `--project`, and an actor from `--actor` (do not change the default text).
- A failure prints `error: <message>` on stderr and exits 1 with no traceback. `_service_errors()` does that for every service failure.
- Rules are in the module (`resolver.py`): a command makes the calls its STEPS name and prints. Linking and re-pinning are open to any signed-in person (ADR-0011; Phase 1 has no per-record access lists).
- `repin` without `--apply` opens the unit of work read-only and changes nothing; with `--apply` it writes.
- These four functions are plain functions (not decorated): `tl_cli/main.py` registers them on the `tl doc` group, so they keep their names.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/doc_link.py` (the stub you complete):
```python
"""Pinned links of documents: `tl doc link|stale|diff|repin`.

A record can be linked to a document floating (it means whatever revision is current) or pinned to
an issued revision. When a later revision is issued, a pinned link goes stale; `tl doc stale` lists
them and `tl doc repin` moves one to another revision after showing what changed between the two
(`tl doc diff` shows the same without moving anything). The rules live in
`tl_mod_documents.resolver`; the commands parse options, make one call and print.
The four functions are registered on the `tl doc` group by `tl_cli.main`.

STUB (P1-I2-T09d): the bodies of the four commands raise NotImplementedError; their signatures,
options, docstrings and the helpers are final. Each body has a STEPS comment. Implement them,
then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from typing import Annotated

import typer
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core.services.queries import get_record
from tl_mod_documents import registry
from tl_mod_documents.resolver import (
    CURRENT,
    LinkToDocument,
    RepinDocumentLink,
    RevisionDiff,
    handle_link_to_document,
    handle_repin_document_link,
    links_to_documents,
    revision_diff,
)

from tl_cli.doc import (
    _DEFAULT_ACTOR,
    _Actor,
    _document,
    _fail,
    _Project,
    _service_errors,
)
from tl_cli.doc_rev import _Number

_LINK_SQL = text(
    "SELECT l.to_id, l.pin, l.status, x.key AS from_key FROM cur_links l "
    "JOIN cur_core_record x ON x.id = l.from_id "
    "WHERE l.link_id = :id AND l.scope = :scope"
)


def _diff_lines(result: RevisionDiff) -> list[str]:
    """A revision diff as lines: the heading (`ISO-1234: A (IFR) to B (IFC)`), then `- ` facts."""
    return [result.summary[0], *(f"- {line}" for line in result.summary[1:])]


def link(
    ctx: typer.Context,
    from_key: Annotated[str, typer.Argument(help="Key of the record that links, e.g. 47-FV-1001.")],
    number: _Number,
    project: _Project,
    pin: Annotated[
        str | None,
        typer.Option("--pin", help="A revision code, or `current`. Omit to float."),
    ] = None,
    relation: Annotated[str | None, typer.Option("--relation")] = None,
    note: Annotated[str | None, typer.Option("--note")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Link a record to a document, floating or pinned to an issued revision."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db) as uow:` doc = _document(uow, scope, project,
    #    number); source = get_record(uow, scope, from_key); if source is None, _fail(f"no record
    #    with key {from_key!r} in project {project!r}").
    # 3. fields = {"actor": actor, "source": "cli", "scope": scope, "from_id": source["id"],
    #    "document_id": doc.id, "pin": pin, "note": note}; add "relation": relation only when it
    #    is not None (the command has a default). made = handle_link_to_document(uow,
    #    LinkToDocument(**fields)).
    # 4. Print `linked <from_key> to <number> pinned <resolved pin>` or `... floating`, then
    #    `link <made.stream_id>`. The resolved pin is the stored one: read it with the SQL
    #    `SELECT pin FROM cur_links WHERE link_id = :id` (made.stream_id) in the same unit of work
    #    (`current` becomes the revision code).
    raise NotImplementedError


def stale(
    ctx: typer.Context,
    project: _Project,
    number: Annotated[
        str | None, typer.Option("--document", help="Only the links to this document.")
    ] = None,
) -> None:
    """List links that are stale: the record, the document, its pin, what is current now, the id."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` doc_id = None, or
    #    _document(uow, scope, project, number).id when --document is given; found =
    #    links_to_documents(uow.conn(), scope, document_id=doc_id, only_stale=True).
    # 3. For each PinnedLink print, joined by two spaces: from_key or "-", "->", document_number,
    #    f"pin {pin or '-'}", f"current {resolution.current_code or '-'}", link_id.
    raise NotImplementedError


def diff(
    ctx: typer.Context,
    number: _Number,
    from_code: Annotated[str, typer.Argument(metavar="FROM", help="The earlier revision code.")],
    to_code: Annotated[str, typer.Argument(metavar="TO", help="The later revision code.")],
    project: _Project,
) -> None:
    """Show what changed between two issued revisions of a document, without changing anything."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` doc = _document(uow, scope,
    #    project, number); result = revision_diff(uow.conn(), doc.id, from_code, to_code).
    # 3. Print the lines of _diff_lines(result) (the helper is final).
    raise NotImplementedError


def repin(
    ctx: typer.Context,
    link_id: Annotated[str, typer.Argument(help="The link id (from `tl doc stale`).")],
    project: _Project,
    pin: Annotated[str, typer.Option("--pin", help="A revision code, or `current`.")] = CURRENT,
    apply: Annotated[bool, typer.Option("--apply", help="Confirm and move the pin.")] = False,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Show what changed between the pinned revision and another; with --apply, move the pin."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db, readonly=not apply) as uow:` row =
    #    uow.conn().execute(_LINK_SQL, {"id": link_id, "scope": scope}).first(); if it is None,
    #    _fail(f"no link {link_id!r} in project {project!r}"). doc = registry.get_document(
    #    uow.conn(), row.to_id); if doc is None, _fail("this link does not point to a document").
    #    If row.pin is None, _fail("this link floats; it has no pin to move").
    # 3. target = doc.current_revision_code when pin == CURRENT, else pin. If target is None,
    #    _fail(f"{doc.number} has no issued revision"). result = revision_diff(uow.conn(), doc.id,
    #    row.pin, target) and print the lines of _diff_lines(result).
    # 4. Without --apply print `not re-pinned; run again with --apply to confirm` and stop.
    # 5. With --apply: handle_repin_document_link(uow, RepinDocumentLink(actor=actor,
    #    source="cli", scope=scope, link_id=link_id, pin=target)) and print
    #    `re-pinned <link_id> to <target>`.
    raise NotImplementedError
```

`packages/tl-modules/documents/src/tl_mod_documents/resolver.py` (excerpts; read-only, do not edit):
```python
@dataclass(frozen=True)
class PinResolution:
    """What a pin on a document means now."""

    document_id: str
    document_number: str
    pin: str | None  # as stored on the link; None floats
    state: PinState
    resolved_code: (
        str | None
    )  # the revision the link means: the pin, or the current one when floating
    resolved_revision_id: str | None
    current_code: str | None  # the document's current revision
    newer_codes: list[str] = field(default_factory=lambda: [])  # issued revisions after the pin

    @property
    def stale(self) -> bool:
        return self.state == "stale"


@dataclass(frozen=True)
class PinnedLink:
    """One link that points to a document, with what its pin means now."""

    link_id: str
    from_id: str
    from_key: str | None
    from_type: str
    from_title: str
    document_id: str
    document_number: str
    document_title: str
    relation: str
    link_status: str  # active | stale (the link lifecycle)
    pin: str | None
    resolution: PinResolution


def links_to_documents(
    conn: Connection,
    scope: str,
    *,
    document_id: str | None = None,
    only_stale: bool = False,
    limit: int = 1000,
) -> list[PinnedLink]:
    """Links (active or stale) that point to a document of the scope, with each pin resolved."""
    ...


@dataclass(frozen=True)
class RevisionDiff:
    """What changed from one revision of a document to another, for a person about to re-pin."""

    document_number: str
    from_code: str
    to_code: str
    from_status: str | None
    to_status: str | None
    steps: list[str]  # one line per revision issued after ``from`` up to ``to``
    renditions: list[RenditionChange]
    summary: list[str]  # the same facts as short sentences, in reading order

    @property
    def changed(self) -> bool:
        return any(c.change != "unchanged" for c in self.renditions) or bool(self.steps)


def revision_diff(conn: Connection, document_id: str, from_code: str, to_code: str) -> RevisionDiff:
    """The difference between two issued revisions of a document."""
    ...


class LinkToDocument(Command):
    """Link a record to a document, floating or pinned to an issued revision.

    ``pin`` is a revision code, ``current`` (pin the revision that is current now), or empty to
    float. The source record's type decides whether it may be linked at all (the generic ``AddLink``
    allow-list); this command adds the check that the pin names a real issued revision.
    """

    model_config = ConfigDict(extra="forbid")

    from_id: str
    document_id: str
    relation: str = Field(default=PIN_RELATION, max_length=MAX_NUMBER)
    pin: str | None = Field(default=None, max_length=MAX_NUMBER)
    note: str | None = Field(default=None, max_length=MAX_REASON)


class RepinDocumentLink(Command):
    """Move a link to another revision of its document (``current`` for the current one).

    Bring a stale link back to active. Show the person ``revision_diff`` first; the command itself
    only records the decision.
    """

    model_config = ConfigDict(extra="forbid")

    link_id: str
    pin: str | None = Field(default=CURRENT, max_length=MAX_NUMBER)
    expected_version: int | None = None


def handle_link_to_document(uow: UnitOfWork, cmd: LinkToDocument) -> CommandResult:
    """Emits ``Link.Added``. Raises ``DocumentNotFoundError``, ``InvalidPinError``, link errors."""
    ...


def handle_repin_document_link(uow: UnitOfWork, cmd: RepinDocumentLink) -> CommandResult:
    """Emits ``Link.Repinned``. Raises ``RecordNotFoundError``, ``InvalidPinError``, link errors."""
    ...
```

`tl_core.services.queries.get_record(uow, scope, key)` returns the record's envelope dictionary (`id`, `key`, `type`, `title`, ...) or `None`.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/doc_link.py` (the file you edit)
- `packages/tl-cli/src/tl_cli/doc.py` and `packages/tl-cli/src/tl_cli/doc_rev.py` (the helpers you import; do not edit)
- `packages/tl-cli/src/tl_cli/tag.py` (a finished group of the same shape; style)
- `packages/tl-modules/documents/src/tl_mod_documents/resolver.py`
- `packages/tl-modules/documents/src/tl_mod_documents/registry.py`
- `packages/tl-cli/tests/doccli_support.py` (the test helpers, already in the tree)
- `docs/tickets/P1-I2/provided/t09d-test_cli_doc_link.py.txt` (the test)
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
- `packages/tl-cli/src/tl_cli/doc_link.py` (edit)
- `packages/tl-cli/tests/test_cli_doc_link.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T09d.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t09d-test_cli_doc_link.py.txt` to `packages/tl-cli/tests/test_cli_doc_link.py`.
3. Implement the commands by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_doc_link.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-cli/tests/test_cli_doc_link.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli -q
```
Expected: `just check` clean; 6 test functions pass on SQLite and again on Postgres; the whole tl-cli package passes.

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
