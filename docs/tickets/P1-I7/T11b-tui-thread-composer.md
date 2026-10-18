# P1-I7-T11b — TUI: the thread composer

Status: ready
Tier: haiku
Labels: tui
Depends on: S3 (in the tree): `ClientInterface` thread methods, `FakeClient` (`packages/tl-tui/tests/fakes_threads.py`), `tl_tui/widgets/composer.py` (`completion_token`, `apply_completion`, final), `tl_tui/messages.py`
Branch: `p1/i7b-t11b-tui-thread-composer`

## Goal
A person writes into a record's thread from the TUI. The composer is a one-line modal: `/` offers the eleven verbs, `#` and `@` complete records and people (as the post composer does), Enter posts a plain message, and a line that starts with `/` is previewed first: the panel lists what would run with the caller's access, Enter again confirms exactly that plan (the preview's token), Esc goes back to editing. `packages/tl-tui/src/tl_tui/compose_text.py` (the pure text) and `widgets/thread_composer.py` (the screen) have the layout, bindings, constructor and the small handlers; `verb_candidates`, `preview_lines`, `verb_token` and six `ThreadComposer` methods raise `NotImplementedError`. You implement them. Two provided test files must pass.

## Brief references (pasted)
> **Brief 21.5 and sketch 13.** `> /dispatch scaffold-mod SCF-0088 add lift EL+107▏ — Tab complete · /help · Enter send · @ people · # records · Ctrl+R reference tray`. "Side-effecting commands show a preview to confirm. The result posts back into the thread as a card." A message does not dispatch; a command line does, after a preview.
>
> **TUI rules (AGENTS.md).** No business logic in the TUI: the screen calls `ClientInterface` (`thread_post`, `thread_preview`, `thread_dispatch`, `feed_complete`) and shows what it returns; it never decides what a command line means or whether it may run (the server previews with the caller's own access). Text is a pure function in `compose_text.py`. A client failure (`CLIENT_ERRORS`) is shown with `describe_error` under the input, never raised.
>
> **Stages.** `edit` (typing) and `confirm` (a preview is shown). Any edit of the text, or Esc, returns to `edit` and drops the preview. A `DispatchStaleError` on confirm goes back to `edit` with "The plan changed since the preview: preview it again". The screen dismisses with the new message's id (`result.key`), or `None` on cancel.

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

`packages/tl-tui/src/tl_tui/widgets/composer.py` (read only):
```python
def completion_token(text: str, cursor: int) -> tuple[Literal["#", "@"], str, int] | None:
    """The `#` or `@` token the cursor is at the end of: ``(sigil, typed prefix, start offset)``.

    ``"see #FV-1"`` with the cursor at 9 gives ``("#", "FV-1", 4)``. A sigil starts a token only at
    the start of the text or after a character that is not a word character, `#` or `@` (``a#b`` and
    ``me@site.org`` are not tokens). The prefix is the word characters, ``.``, ``:``, ``/`` and
    ``-`` after the sigil, up to the cursor. ``None`` when the cursor is not at the end of such a
    token (for example after a space). Hint: ``_TOKEN`` matches the end of ``text[:cursor]``.
    """
    match = _TOKEN.search(text[:cursor])
    if match is None:
        return None
    sigil, prefix = match.group(1), match.group(2)
    return ("#" if sigil == "#" else "@", prefix, match.start())


def apply_completion(
    text: str, cursor: int, start: int, sigil: str, candidate: str
) -> tuple[str, int]:
    """``text`` with the token from ``start`` to ``cursor`` replaced by ``sigil + candidate``.

    A space is added after it unless the text after the cursor already begins with one. Returns the
    new text and the new cursor offset: just after the inserted text and that space (when a space
    was already there, just after it).
    """
    inserted = sigil + candidate
    after = text[cursor:]
    if after.startswith(" "):
        new_text = text[:start] + inserted + after
    else:
        new_text = text[:start] + inserted + " " + after
    return new_text, start + len(inserted) + 1
```

`packages/tl-core/src/tl_core/threads/contract.py` (read only):
```python
class DispatchPreview(BaseModel):
    """What the caller sees before a side-effecting dispatch runs.

    ``can_dispatch`` is true when every planned command is ``permitted`` and has no ``problem``.
    ``token`` is the SHA-256 of the canonical JSON of (record id, record version, ``line``,
    ``planned``); a confirmation names it, and the run is refused (``dispatch_stale``) when the
    plan made then differs or ``expires_at`` has passed.
    """

    record: RecordRef
    parsed: ParsedDispatch
    planned: list[PlannedCommand] = Field(
        default_factory=list[PlannedCommand], max_length=MAX_PLANNED_COMMANDS
    )
    links: list[PlannedLink] = Field(default_factory=list[PlannedLink])
    side_effecting: bool
    can_dispatch: bool
    token: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: str
    problems: list[Problem] = Field(default_factory=list[Problem])
    #: e.g. "summary is deterministic, no model (ADR-0008 decision 8)".
    notes: list[str] = Field(default_factory=list[str], max_length=20)
```

`packages/tl-core/src/tl_core/integration/contract.py` (read only):
```python
class PlannedCommand(BaseModel):
    """One command that automation or a dispatch would run, as a preview shows it.

    ``command`` holds the fields of the command model except ``actor`` (which the runner sets).
    ``access`` is what the command needs (``None``: nothing declares it, so it is refused);
    ``permitted`` says whether the actor that would run it holds that access. ``problem`` is set
    when the command would be refused (validation, access, a missing record, a stale state).
    """

    command_type: str
    command: dict[str, Any] = Field(default_factory=dict[str, Any])
    access: Access | None = None
    permitted: bool = False
    summary: str = Field(default="", max_length=MAX_SUMMARY_CHARS)
    problem: Problem | None = None

class Problem(BaseModel):
    """A refusal or a failure: a short fixed code and words for a person (no paths, no traces)."""

    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    message: str = Field(max_length=MAX_MESSAGE_CHARS)
```

`packages/tl-core/src/tl_core/threads/contract.py` (read only):
```python
class ParseProblem(BaseModel):
    """A command line the parser refused. ``column`` is 0-based in ``line`` when known."""

    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    message: str = Field(max_length=500)
    column: int | None = None
```

`packages/tl-core/src/tl_core/threads/dispatch.py` (read only):
```python
class DispatchFromThread(Command):
    """Confirm the dispatch of ``text`` on the thread of ``record_id`` as ``actor``.

    ``token`` is the one a preview returned for the same text; ``expires_at`` (optional) is the
    preview's own, and a confirmation after it is stale. Who may run it is decided by the caller's
    access and ``threads.dispatch.roles``, never by a field here.
    """

    record_id: str
    text: str
    token: str
    expires_at: str | None = None

    @field_validator("token")
    @classmethod
    def _token_shape(cls, value: str) -> str:
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise ValueError("token must be the 64 hex characters a preview returned")
        return value
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

`packages/tl-core/src/tl_core/threads/planner.py` (read only):
```python
class PreviewResult(BaseModel):
    """What the preview route and client return: a preview, or the parse problem to show.

    A command line that does not parse is feedback for the composer, not a failed request.
    """

    preview: DispatchPreview | None = None
    problem: ParseProblem | None = None
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/thread_composer.py (the file you edit)`
- `packages/tl-tui/src/tl_tui/compose_text.py (the file you edit)`
- `packages/tl-tui/src/tl_tui/widgets/composer.py (the post composer: the same pattern, complete)`
- `packages/tl-tui/tests/fakes_threads.py (the fake the tests use: `script_preview`, `dispatched`, `thread_commands`)`
- `docs/tickets/P1-I7/provided/t11b-test_compose_text.py.txt (test 1)`
- `docs/tickets/P1-I7/provided/t11b-test_thread_composer.py.txt (test 2)`
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for `tl-core`, and `just check` runs it on the whole tree.
- The provided test lives under `docs/tickets/P1-I7/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I7/P1-I7-T11b.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. When you implement the stub, remove the `STUB` paragraph from the module docstring, every `STEPS` comment, the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line (L-P1-I3-3).
- Never change `schema/**` or anything under `generated/`. Never edit a file outside *Allowed paths*.
- Do not run `just test`, `just test-parity` or `just test-tui` (they take an hour); run the scoped commands in *Acceptance*. Other tests of `tests/threads/` exercise the same code (`test_planner.py`, `test_dispatch.py`); they are red until every ticket of the batch is merged and are not part of your acceptance.
- Tests that open a database use the `db` fixture of `tests/threads/conftest.py`, so they run once per adapter named by `--adapters` (default sqlite). `tests/threads/thread_world.py` holds the helpers; it is in the tree and read only (L-P1-I7B-1).

## Allowed paths
- `packages/tl-tui/src/tl_tui/compose_text.py (edit)`
- `packages/tl-tui/src/tl_tui/widgets/thread_composer.py (edit)`
- `packages/tl-tui/tests/test_compose_text.py (create; byte-identical copy of test 1)`
- `packages/tl-tui/tests/test_thread_composer.py (create; byte-identical copy of test 2)`
- `docs/reports/P1-I7/P1-I7-T11b.md (create)`

## Lines you must not change
- The signature, decorator and docstring of every function and class in the stub file: you replace only the bodies that have a `STEPS` comment.
- The provided test: the copy stays byte-identical to `docs/tickets/P1-I7/provided/t11b-test_*.py.txt`.
- Every other file of the repository. The only files you create or edit are in *Allowed paths*.
- `VERB_HELP` in `compose_text.py`; `compose`, `on_mount`, `popup_visible`, `on_input_changed`, `action_choose`, `on_input_submitted` and `_back_to_edit` in `thread_composer.py`.
- `tests/fakes_threads.py` and `tests/helpers.py` (read only).

## Steps
- `packages/tl-tui/src/tl_tui/compose_text.py` (edit)
- `packages/tl-tui/src/tl_tui/widgets/thread_composer.py` (edit)
- `packages/tl-tui/tests/test_compose_text.py` and `test_thread_composer.py` (create)
- `docs/reports/P1-I7/P1-I7-T11b.md` (create)

1. `uv sync --all-packages`.
2. Copy the two provided tests to the names above.
3. Implement the bodies by their STEPS comments; remove each STUB paragraph, the STEPS comments and the two lint-silencing lines of both files.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_compose_text.py packages/tl-tui/tests/test_thread_composer.py -q
```
Expected: `just check` clean; 5 + 12 pass.

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
