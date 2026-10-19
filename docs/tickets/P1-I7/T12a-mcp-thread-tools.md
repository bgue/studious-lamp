# P1-I7-T12a — MCP: read_thread and post_thread_message

Status: ready
Tier: haiku
Labels: mcp
Depends on: S3 (in the tree): `tl_mcp/thread_tools.py` (the tool registration, the result model and `propose_dispatch` are final), `tl_core/threads/{queries,messages}.py`, `packages/tl-mcp/tests/mcp_harness.py`
Branch: `p1/i7b-t12a-mcp-thread-tools`

## Goal
An AI agent reads a record's thread and posts to it. `read_thread` returns the newest messages with the participants; `post_thread_message` writes a message directly, labelled with the agent (a message changes no record and never dispatches, even when its text starts with `/`). The tool registration, the argument bounds and the `ThreadPostResult` model are written in `packages/tl-mcp/src/tl_mcp/thread_tools.py`; the bodies of `read_thread_impl` and `post_thread_message_impl` raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 21.5.** MCP `read_thread`, `post_thread_message`, `propose_dispatch`. "Visibility equals the record's visibility." **FANOUT D9/D10/D12:** `read_thread` is a read (at most `READ_THREAD_MAX_PAGE` = 200 per page, enforced by the tool's argument bounds); `post_thread_message` is direct, like `post_feed` ("a message changes no record and never dispatches"); agents propose dispatches (`propose_dispatch`, final, not yours).
>
> **How tools work here (`tl_mcp`).** Every tool runs inside `guarded(ctx, name, resource)` (the authorise hook, bounds, error mapping), which the registration already does. An impl opens a unit of work with `ctx.factory(True)` (read) or `ctx.factory(False)` (write) and calls one `tl_core` function as `ctx.actor` (`agent:<id>`); everything done for the agent has the source `proposals.source_for(ctx.actor)` (`mcp:<id>`). A record is named by id, or by key with `scope`: `resolve_record_id(uow, record, scope)` finds the id and raises `RecordNotFoundError`.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-mcp/src/tl_mcp/context.py` (read only):
```python
class McpContext:
    factory: UowFactory
    actor: str  # ``agent:<id>`` or ``user:<id>``, fixed for the life of the server (ADR-0005)
    authorize: Authorizer
    lake: LakeQueryService  # the guarded, read-only lake_query service (brief 11.3, 28.4)
    objects: ObjectStore | None = None  # bodies of object-backed extension records (brief 31)
```

`packages/tl-mcp/src/tl_mcp/tools.py` (read only):
```python
def resolve_record_id(uow: UnitOfWork, record: str, scope: str | None) -> str:
    """The id of ``record``, which is a record id or (with ``scope``) a record key.
    ..."""
```

`packages/tl-mcp/src/tl_mcp/write_tools.py` (read only):
```python
def _envelope(ctx: McpContext, record: str, scope: str | None) -> dict[str, Any]:
    """The record's envelope (read once, in its own read-only unit of work)."""
    ...
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
```

`packages/tl-core/src/tl_core/threads/messages.py` (read only):
```python
def handle_post_thread_message(uow: UnitOfWork, cmd: PostThreadMessage) -> CommandResult:
    """Post a message. Raises ``RecordNotFoundError`` (no such record in the scope, or not
    readable) and ``ThreadsDisabledError``."""
    ...
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

def read_thread(
    uow: UnitOfWork,
    record_id: str,
    *,
    actor: str,
    scope: str | None = None,
    limit: int = 50,
    before_seq: int | None = None,
) -> ThreadPage:
    """The newest ``limit`` messages (at most ``READ_THREAD_MAX_PAGE``) before ``before_seq``."""
    ...
```

`packages/tl-mcp/src/tl_mcp/thread_tools.py` (read only):
```python
class ThreadPostResult(BaseModel):
    """What ``post_thread_message`` returns."""

    message_id: str
    record_id: str
    author: str
    mentions: list[str]
    record_refs: list[str]
```

## Context (read these, nothing else)
- `packages/tl-mcp/src/tl_mcp/thread_tools.py (the file you edit)`
- `packages/tl-mcp/src/tl_mcp/write_tools.py (`post_feed_impl`, `_envelope`: the same shape, complete)`
- `packages/tl-mcp/src/tl_mcp/tools.py (`resolve_record_id`, `get_record_impl`)`
- `packages/tl-mcp/tests/mcp_harness.py (the harness the test uses)`
- `docs/tickets/P1-I7/provided/t12a-test_mcp_thread_tools.py.txt (the test)`
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for `tl-core`, and `just check` runs it on the whole tree.
- The provided test lives under `docs/tickets/P1-I7/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I7/P1-I7-T12a.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. When you implement the stub, remove the `STUB` paragraph from the module docstring, every `STEPS` comment, the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line (L-P1-I3-3).
- Never change `schema/**` or anything under `generated/`. Never edit a file outside *Allowed paths*.
- Do not run `just test`, `just test-parity` or `just test-tui` (they take an hour); run the scoped commands in *Acceptance*. Other tests of `tests/threads/` exercise the same code (`test_planner.py`, `test_dispatch.py`); they are red until every ticket of the batch is merged and are not part of your acceptance.
- Tests that open a database use the `db` fixture of `tests/threads/conftest.py`, so they run once per adapter named by `--adapters` (default sqlite). `tests/threads/thread_world.py` holds the helpers; it is in the tree and read only (L-P1-I7B-1).

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/thread_tools.py (edit)`
- `packages/tl-mcp/tests/test_mcp_thread_tools.py (create; byte-identical copy of the provided test)`
- `docs/reports/P1-I7/P1-I7-T12a.md (create)`

## Lines you must not change
- The signature, decorator and docstring of every function and class in the stub file: you replace only the bodies that have a `STEPS` comment.
- The provided test: the copy stays byte-identical to `docs/tickets/P1-I7/provided/t12a-test_mcp_thread_tools.py.txt`.
- Every other file of the repository. The only files you create or edit are in *Allowed paths*.
- `propose_dispatch_impl`, `register_thread_tools`, `ThreadPostResult` and the argument types in `thread_tools.py`.

## Steps
- `packages/tl-mcp/src/tl_mcp/thread_tools.py` (edit)
- `packages/tl-mcp/tests/test_mcp_thread_tools.py` (create)
- `docs/reports/P1-I7/P1-I7-T12a.md` (create)

1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I7/provided/t12a-test_mcp_thread_tools.py.txt` to `packages/tl-mcp/tests/test_mcp_thread_tools.py`.
3. Implement the two `_impl` bodies by their STEPS comments; remove the STUB paragraph, the STEPS comments and the two lint-silencing lines.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-mcp/tests/test_mcp_thread_tools.py -q
```
Expected: `just check` clean; 8 pass. (`tests/test_mcp_propose_dispatch.py` also uses this module but is not part of your acceptance.)

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). Put `Deviations` first (or "none") and list every file you changed.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, or if the test needs a change outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
