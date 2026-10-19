# P1-I7-T09a — CLI: tl thread show, post, edit, retract

Status: ready
Tier: haiku
Labels: cli
Depends on: S1 (in the tree): `tl_core/threads/{messages,queries}.py`, `tl_cli/thread_common.py` (`record_of`, final), `tl_cli/main.py` registers the group; the fixture `packages/tl-cli/tests/thread_cli_support.py`; T10a (the test posts a `/raise` line as plain text only, no dispatch is run)
Branch: `p1/i7b-t09a-cli-thread-messages`

## Goal
A person reads and writes a record's thread from the shell. `tl thread show` prints the header, the participants and the messages (oldest first, with `older: --before N` for paging); `post`, `edit` and `retract` write a message, change your own, or retract it. A message that starts with `/` is text, never a dispatch. `packages/tl-cli/src/tl_cli/thread.py` has the Typer group, the option declarations and docstrings; the bodies of `message_lines`, `show`, `post`, `edit` and `retract` raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 21.5.** Events `Thread.MessagePosted`, `Thread.MessageEdited`, `Thread.MessageRetracted`; "messages do not appear in the activity stream"; edits and retractions are the author's, and a retraction leaves a tombstone.
>
> **CLI rules (AGENTS.md, `tl_cli`).** A command parses options, makes one call into `tl_core` and prints; no rule lives in the command. A failure of a service is one `error: <message>` line on stderr and exit 1 (`service_errors()`). A write command declares `--actor` with the `DEV_ACTOR` default and runs `acting(db, actor)` first (it checks the session). The database is `ctx.obj` (a `DbTarget`), opened with `open_uow` (never a SQLite import).
>
> **Output (the test pins it).** `post`: `posted <message id>`, then `mentions @a, @b` when the message names people, then `refs N` when it names records. `edit`: `edited <id>`. `retract`: `retracted <id>`. `show`: the header, the participants line, one line per message (`message_lines`), `older: --before N` when more exist.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/thread_common.py` (read only):
```python
SOURCE = "cli"

def record_of(db: DbTarget, project: str, record: str) -> tuple[str, str]:
    """``(id, scope)`` of the record named by key in the project, or by id (RecordNotFoundError)."""
    ...
```

`packages/tl-cli/src/tl_cli/derive_support.py` (read only):
```python
Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]
Actor = Annotated[str, typer.Option("--actor", help="Actor recorded on events.")]
def fail(message: str) -> NoReturn: ...
def service_errors() -> Iterator[None]: ...  # a context manager: ServiceError -> `error:` and exit 1
def acting(db: DbTarget, actor: str) -> str: ...
```

`packages/tl-core/src/tl_core/threads/messages.py` (read only):
```python
class PostThreadMessage(Command):
    """Post ``body`` to the thread of ``record_id`` as ``actor`` (person or agent).

    It never dispatches: a body that starts with ``/`` is stored as the text it is.
    """

    record_id: str
    body: str

    @field_validator("body")
    @classmethod
    def _body_is_usable(cls, value: str) -> str:
        return _clean_body(value)


class EditThreadMessage(Command):
    """Replace the body of the author's own message."""

    record_id: str
    message_id: str
    body: str

    @field_validator("body")
    @classmethod
    def _body_is_usable(cls, value: str) -> str:
        return _clean_body(value)


class RetractThreadMessage(Command):
    """Retract the author's own message; a tombstone stays."""

    record_id: str
    message_id: str
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason_given(cls, value: str) -> str:
        if not value.strip() or len(value) > MAX_REASON_CHARS:
            raise ValueError(f"reason must be 1 to {MAX_REASON_CHARS} characters")
        return value
```

`packages/tl-core/src/tl_core/threads/messages.py` (read only):
```python
def handle_post_thread_message(uow: UnitOfWork, cmd: PostThreadMessage) -> CommandResult:
    """Post a message. Raises ``RecordNotFoundError`` (no such record in the scope, or not ...
def handle_edit_thread_message(uow: UnitOfWork, cmd: EditThreadMessage) -> CommandResult: ...
def handle_retract_thread_message(uow: UnitOfWork, cmd: RetractThreadMessage) -> CommandResult: ...
# CommandResult.key is the message id; CommandResult.events[0].payload of a post has `mentions` and `record_refs`.
```

`packages/tl-core/src/tl_core/threads/queries.py` (read only):
```python
class ThreadParticipant(BaseModel):
    actor: str
    reasons: list[str] = Field(default_factory=list[str])


class ThreadPage(BaseModel):
    """A page of a thread, oldest message first. ``next_before`` is the cursor of the older page."""

    record: RecordRef
    enabled: bool
    dispatch_enabled: bool
    message_count: int = 0
    participants: list[ThreadParticipant] = Field(default_factory=list[ThreadParticipant])
    messages: list[ThreadMessageView] = Field(default_factory=list[ThreadMessageView])
    next_before: int | None = None
    #: Sequence numbers of ``messages``, in the same order (the cursor for ``before``).
    seqs: list[int] = Field(default_factory=list[int])
    #: Kinds of ``messages`` (`message`, `dispatch`, `summary`, `reminder`), in the same order.
    kinds: list[str] = Field(default_factory=list[str])
```

`packages/tl-core/src/tl_core/threads/contract.py` (read only):
```python
class DispatchResult(BaseModel):
    """One command a confirmed dispatch ran."""

    command_type: str
    stream_id: str
    key: str | None = None
    version: int

class DispatchOutcome(BaseModel):
    """The payload of ``Thread.Dispatched`` and the result card in the thread."""

    message_id: str
    verb: DispatchVerb
    results: list[DispatchResult] = Field(default_factory=list[DispatchResult])
    link_ids: list[str] = Field(default_factory=list[str])
    summary: str = Field(default="", max_length=500)
class ThreadMessageView(BaseModel):
    """A message as the thread tab, the API and ``read_thread`` show it."""

    message_id: str
    record_id: str
    author: str
    body: str = Field(max_length=MAX_MESSAGE_CHARS)
    posted_at: str
    edited: bool = False
    retracted: bool = False
    mentions: list[str] = Field(default_factory=list[str])
    record_refs: list[str] = Field(default_factory=list[str])
    dispatch: DispatchOutcome | None = None
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/thread.py (the file you edit)`
- `packages/tl-cli/src/tl_cli/thread_common.py`
- `packages/tl-cli/src/tl_cli/feed.py (`post`, `ls`: the same shape, complete)`
- `packages/tl-cli/src/tl_cli/derive_support.py`
- `packages/tl-cli/tests/thread_cli_support.py (the fixture the test uses)`
- `docs/tickets/P1-I7/provided/t09a-test_cli_thread.py.txt (the test)`
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for `tl-core`, and `just check` runs it on the whole tree.
- The provided test lives under `docs/tickets/P1-I7/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I7/P1-I7-T09a.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. When you implement the stub, remove the `STUB` paragraph from the module docstring, every `STEPS` comment, the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line (L-P1-I3-3).
- Never change `schema/**` or anything under `generated/`. Never edit a file outside *Allowed paths*.
- Do not run `just test`, `just test-parity` or `just test-tui` (they take an hour); run the scoped commands in *Acceptance*. Other tests of `tests/threads/` exercise the same code (`test_planner.py`, `test_dispatch.py`); they are red until every ticket of the batch is merged and are not part of your acceptance.
- Tests that open a database use the `db` fixture of `tests/threads/conftest.py`, so they run once per adapter named by `--adapters` (default sqlite). `tests/threads/thread_world.py` holds the helpers; it is in the tree and read only (L-P1-I7B-1).

## Allowed paths
- `packages/tl-cli/src/tl_cli/thread.py (edit)`
- `packages/tl-cli/tests/test_cli_thread.py (create; byte-identical copy of the provided test)`
- `docs/reports/P1-I7/P1-I7-T09a.md (create)`

## Lines you must not change
- The signature, decorator and docstring of every function and class in the stub file: you replace only the bodies that have a `STEPS` comment.
- The provided test: the copy stays byte-identical to `docs/tickets/P1-I7/provided/t09a-test_cli_thread.py.txt`.
- Every other file of the repository. The only files you create or edit are in *Allowed paths*.
- `thread_common.py`, `thread_dispatch.py`, `main.py` and `thread_cli_support.py`.

## Steps
- `packages/tl-cli/src/tl_cli/thread.py` (edit)
- `packages/tl-cli/tests/test_cli_thread.py` (create)
- `docs/reports/P1-I7/P1-I7-T09a.md` (create)

1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I7/provided/t09a-test_cli_thread.py.txt` to `packages/tl-cli/tests/test_cli_thread.py`.
3. Implement the five bodies by their STEPS comments; remove the STUB paragraph, the STEPS comments and the two lint-silencing lines.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_thread.py -q
```
Expected: `just check` clean; 10 pass (the help test lists `preview`, `dispatch` and `reminders` too: they are registered by `main.py` from `thread_dispatch.py`, which is final in your tree as a stub).

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). Put `Deviations` first (or "none") and list every file you changed.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, if `thread_common.py` seems wrong, or if the test needs a change outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
