# P1-I7-T11a — TUI: the thread tab and its text

Status: ready
Tier: haiku
Labels: tui
Depends on: S3 (in the tree): `ClientInterface.thread_page`, `FakeClient` (`packages/tl-tui/tests/fakes_threads.py`), `tl_tui/messages.py`, the record view's Thread tab; T11b (`ThreadComposer`: `action_compose` opens it, and the provided tab test composes through it)
Branch: `p1/i7b-t11a-tui-thread-tab`

## Goal
A person reads a record's thread in the TUI. The Thread tab shows a header (the record, the number of participants, whether dispatch is on), the messages oldest first (a clock, the author, the first line, the rest indented, `(edited)`, `[retracted]`), the result card of a dispatch under its message, and loads older pages with `o`. `c` opens the composer. `packages/tl-tui/src/tl_tui/thread_text.py` (pure text) and `widgets/thread_tab.py` (the widget) have the layout, bindings and constructor; `header_text`, `card_lines`, `message_lines` and four `ThreadTab` methods raise `NotImplementedError`. You implement them. Two provided test files must pass.

## Brief references (pasted)
> **Brief 21.5 and sketch 13.** "Messages do not appear in the activity stream"; a retraction leaves a tombstone; "the result posts back into the thread as a card". Visibility is the record's: the server returns only what the viewer may read.
>
> **TUI rules (AGENTS.md).** No business logic in the TUI: the tab calls `client.thread_page(record id, limit=, before_seq=)` and shows what it returns. Text is a pure function of the page (`thread_text.py`), never of a widget. A client failure (`CLIENT_ERRORS`) is a `StatusMessage(describe_error(exc), "error")` and the display is kept. A client that has no threads raises `NotImplementedError`: the tab stays empty.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-tui/src/tl_tui/client.py (ClientInterface, thread part)` (read only):
```python
    def thread_page(
        self, record_id: str, *, limit: int = 50, before_seq: int | None = None
    ) -> ThreadPage:
        """The newest messages of the record's thread (oldest first), its participants and whether
        threads and dispatch are on for it. ``before_seq`` is ``ThreadPage.next_before``."""
        ...

    def thread_post(self, cmd: PostThreadMessage) -> CommandResult:
        """Post a message. The result's ``key`` is the message id."""
        ...

    def thread_edit(self, cmd: EditThreadMessage) -> CommandResult: ...

    def thread_retract(self, cmd: RetractThreadMessage) -> CommandResult: ...

    def thread_preview(self, record_id: str, text: str) -> PreviewResult:
        """Plan a slash command as the signed-in person: a preview, or the parse problem."""
        ...

    def thread_dispatch(self, cmd: DispatchFromThread) -> CommandResult:
        """Run a previewed command (``cmd.token`` from the preview) in one transaction."""
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

`packages/tl-tui/src/tl_tui/messages.py` (read only):
```python
class RecordChanged(Message):
    """A command succeeded for this record; views showing it should reload."""

    def __init__(self, record_id: str) -> None:
        super().__init__()
        self.record_id = record_id

```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/thread_text.py (the file you edit)`
- `packages/tl-tui/src/tl_tui/widgets/thread_tab.py (the file you edit)`
- `packages/tl-tui/src/tl_tui/widgets/thread_composer.py (the composer `action_compose` opens)`
- `packages/tl-tui/tests/fakes_threads.py (the fake the tests use)`
- `docs/tickets/P1-I7/provided/t11a-test_thread_text.py.txt (test 1)`
- `docs/tickets/P1-I7/provided/t11a-test_thread_tab.py.txt (test 2)`
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for `tl-core`, and `just check` runs it on the whole tree.
- The provided test lives under `docs/tickets/P1-I7/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I7/P1-I7-T11a.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. When you implement the stub, remove the `STUB` paragraph from the module docstring, every `STEPS` comment, the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line (L-P1-I3-3).
- Never change `schema/**` or anything under `generated/`. Never edit a file outside *Allowed paths*.
- Do not run `just test`, `just test-parity` or `just test-tui` (they take an hour); run the scoped commands in *Acceptance*. Other tests of `tests/threads/` exercise the same code (`test_planner.py`, `test_dispatch.py`); they are red until every ticket of the batch is merged and are not part of your acceptance.
- Tests that open a database use the `db` fixture of `tests/threads/conftest.py`, so they run once per adapter named by `--adapters` (default sqlite). `tests/threads/thread_world.py` holds the helpers; it is in the tree and read only (L-P1-I7B-1).

## Allowed paths
- `packages/tl-tui/src/tl_tui/thread_text.py (edit)`
- `packages/tl-tui/src/tl_tui/widgets/thread_tab.py (edit)`
- `packages/tl-tui/tests/test_thread_text.py (create; byte-identical copy of test 1)`
- `packages/tl-tui/tests/test_thread_tab.py (create; byte-identical copy of test 2)`
- `docs/reports/P1-I7/P1-I7-T11a.md (create)`

## Lines you must not change
- The signature, decorator and docstring of every function and class in the stub file: you replace only the bodies that have a `STEPS` comment.
- The provided test: the copy stays byte-identical to `docs/tickets/P1-I7/provided/t11a-test_*.py.txt`.
- Every other file of the repository. The only files you create or edit are in *Allowed paths*.
- `person` and `clock` in `thread_text.py`; `BINDINGS`, `__init__`, `compose` and `show_record` in `thread_tab.py`.
- `tests/fakes_threads.py` and `tests/helpers.py` (read only).

## Steps
- `packages/tl-tui/src/tl_tui/thread_text.py` (edit)
- `packages/tl-tui/src/tl_tui/widgets/thread_tab.py` (edit)
- `packages/tl-tui/tests/test_thread_text.py` and `test_thread_tab.py` (create)
- `docs/reports/P1-I7/P1-I7-T11a.md` (create)

1. `uv sync --all-packages`.
2. Copy the two provided tests to the names above.
3. Implement the bodies by their STEPS comments; remove each STUB paragraph, the STEPS comments and the two lint-silencing lines of both files.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_thread_text.py packages/tl-tui/tests/test_thread_tab.py -q
```
Expected: `just check` clean; 6 + 7 pass.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). Put `Deviations` first (or "none") and list every file you changed.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and a provided test disagree, if the fake lacks something a test needs, or if a test needs a change outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
