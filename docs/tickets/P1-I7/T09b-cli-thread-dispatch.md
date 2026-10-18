# P1-I7-T09b — CLI: tl thread preview, dispatch, reminders

Status: ready
Tier: haiku
Labels: cli
Depends on: S2 (in the tree): `tl_core/threads/{planner,dispatch,reminders}.py`, `tl_api/thread_runner.py`, `tl_cli/thread_common.py` (`record_of`, `holds_of`); T09a merged (the test calls `tl thread show` and `tl thread post`); T10a, T10b, T10c, T10d merged (the test previews `/link`, `/raise record`, `/summarise` and `/remind` and runs a reminder job); the fixture `packages/tl-cli/tests/thread_cli_support.py`
Branch: `p1/i7b-t09b-cli-thread-dispatch`

## Goal
A person plans, runs and follows up a slash command from the shell. `tl thread preview RECORD '/link REC-2'` prints what the command would do (each planned command with the access it needs and whether you hold it, the problems, a token) and writes nothing; `tl thread dispatch RECORD '/link REC-2' --token T` (or `--yes`) runs exactly that plan in one transaction as you; `tl thread reminders` posts the `/remind` reminders that have fallen due. `packages/tl-cli/src/tl_cli/thread_dispatch.py` has the options and docstrings; the bodies of `preview_lines`, `_preview`, `preview`, `dispatch` and `reminders` raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 21.5.** "Each command is a ledgered command: permissions and validation apply. Side-effecting commands show a preview to confirm. The result posts back into the thread as a card." `/remind` queues a job; `/summarise` is a deterministic summary (ADR-0008 decision 8).
>
> **ADR-0018.** The preview is made by `ThreadPlanner.preview` as the caller, with the caller's own `holds` (never more); its `token` hashes the plan. The confirmation, `handle_dispatch_from_thread`, plans again, compares the token (`DispatchStaleError` otherwise), refuses a plan with problems and runs the message, the commands and `Thread.Dispatched` in ONE unit of work. The CLI passes `holds_of(db, who)` (read from the account) and the typed command table `thread_runner()`; a request never supplies roles.
>
> **CLI rules.** One `error: <message>` line on stderr and exit 1 for a service failure (`service_errors()`); `fail(msg)` prints the same and exits. A write command declares `--actor` with the `DEV_ACTOR` default and runs `acting(db, actor)` first. `preview`, `dispatch` and `reminders` are plain functions: `tl_cli/main.py` adds them to the `tl thread` group (`thread.app.command("preview")(thread_dispatch.preview)`), so there is no `@app.command` here.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/thread_common.py` (read only):
```python
SOURCE = "cli"

def record_of(db: DbTarget, project: str, record: str) -> tuple[str, str]: ...  # (id, scope)
def holds_of(db: DbTarget, actor: str) -> Callable[[Access], bool]: ...  # what actor holds, from its account
```

`packages/tl-cli/src/tl_cli/derive_support.py` (read only):
```python
Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]
Actor = Annotated[str, typer.Option("--actor", help="Actor recorded on events.")]
def fail(message: str) -> NoReturn: ...
def service_errors() -> Iterator[None]: ...
def acting(db: DbTarget, actor: str) -> str: ...
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

`packages/tl-core/src/tl_core/threads/planner.py` (read only):
```python
class ThreadPlanner:
    def __init__(self, *, parser=None, targets=None, factory: Factory | None = None, clock=utcnow) -> None: ...

    def preview(
        self,
        uow: UnitOfWork,
        *,
        record_id: str,
        text: str,
        actor: str,
        holds: Callable[[Access], bool],
        runner: CommandRunner,
    ) -> DispatchPreview | ParseProblem: ...  # raises DispatchForbiddenError, ThreadsDisabledError, ... (ServiceErrors)
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

def handle_dispatch_from_thread(uow, cmd: DispatchFromThread, *, holds, runner, planner=None, now=None) -> CommandResult: ...
# CommandResult.key is the message id; result.events holds the Thread.Dispatched event, whose
# payload has `verb`, `summary` and `results` (dicts with command_type, stream_id, key, version).
```

`packages/tl-api/src/tl_api/thread_runner.py` (read only):
```python
def thread_runner() -> CommandRunner: ...
```

`packages/tl-core/src/tl_core/jobs/runner.py` (read only):
```python
class JobRunner:
    def __init__(self, open_uow, queue, kinds: Sequence[JobKind], *, worker_id=None, lease_s=..., retry_base_s=..., clock=utcnow) -> None: ...
    def run_until_idle(self, *, scope: str | None = None, limit: int = 10_000) -> list[RunResult]: ...
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/thread_dispatch.py (the file you edit)`
- `packages/tl-cli/src/tl_cli/thread_common.py`
- `packages/tl-cli/src/tl_cli/thread.py (the sibling group, complete after T09a)`
- `packages/tl-cli/tests/thread_cli_support.py (the fixture the test uses)`
- `docs/tickets/P1-I7/provided/t09b-test_cli_thread_dispatch.py.txt (the test)`
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for `tl-core`, and `just check` runs it on the whole tree.
- The provided test lives under `docs/tickets/P1-I7/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I7/P1-I7-T09b.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. When you implement the stub, remove the `STUB` paragraph from the module docstring, every `STEPS` comment, the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line (L-P1-I3-3).
- Never change `schema/**` or anything under `generated/`. Never edit a file outside *Allowed paths*.
- Do not run `just test`, `just test-parity` or `just test-tui` (they take an hour); run the scoped commands in *Acceptance*. Other tests of `tests/threads/` exercise the same code (`test_planner.py`, `test_dispatch.py`); they are red until every ticket of the batch is merged and are not part of your acceptance.
- Tests that open a database use the `db` fixture of `tests/threads/conftest.py`, so they run once per adapter named by `--adapters` (default sqlite). `tests/threads/thread_world.py` holds the helpers; it is in the tree and read only (L-P1-I7B-1).
- The dispatching person needs an account: the command runner reads what an actor holds from `cur_account`, and `holds_of` (final) reads the same account, with no exception for a dev ledger. The fixture `thread_env` in `thread_cli_support.py` makes the account `user:dev` (L-P1-I7B-8). Do not add a fallback that says "holds everything".

## Allowed paths
- `packages/tl-cli/src/tl_cli/thread_dispatch.py (edit)`
- `packages/tl-cli/tests/test_cli_thread_dispatch.py (create; byte-identical copy of the provided test)`
- `docs/reports/P1-I7/P1-I7-T09b.md (create)`

## Lines you must not change
- The signature, decorator and docstring of every function and class in the stub file: you replace only the bodies that have a `STEPS` comment.
- The provided test: the copy stays byte-identical to `docs/tickets/P1-I7/provided/t09b-test_cli_thread_dispatch.py.txt`.
- Every other file of the repository. The only files you create or edit are in *Allowed paths*.
- `thread_common.py`, `thread.py`, `main.py` and `thread_cli_support.py`.

## Steps
- `packages/tl-cli/src/tl_cli/thread_dispatch.py` (edit)
- `packages/tl-cli/tests/test_cli_thread_dispatch.py` (create)
- `docs/reports/P1-I7/P1-I7-T09b.md` (create)

1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I7/provided/t09b-test_cli_thread_dispatch.py.txt` to `packages/tl-cli/tests/test_cli_thread_dispatch.py`.
3. Implement the five bodies by their STEPS comments; remove the STUB paragraph, the STEPS comments and the two lint-silencing lines.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_thread_dispatch.py -q
```
Expected: `just check` clean; 9 pass. Slow (about 1 minute): each test runs the CLI against a fresh ledger.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). Put `Deviations` first (or "none") and list every file you changed.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, if you think the CLI should pass roles to the planner (it must not: `holds_of` reads the account), or if the test needs a change outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
The block was an ordering fault of the ticket (third in this workstream, L-P1-I7B-9): three of the ten tests call `tl thread show` and `tl thread post`, which are T09a's. T09a merged first, `p1/i7b` was merged into this branch, all 10 tests then passed and the branch was merged. Depends now names T09a.
