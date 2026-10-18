# P1-I7-T10d — The thread.reminder job kind

Status: merged
Tier: haiku
Labels: core
Depends on: S1 and S2 (in the tree): `tl_core/jobs/runner.py` (`JobKind`, `JobFailure`), `tl_core/threads/{messages,effects,queries,parser}.py`, `dispatch.py` (it queues the job) and the fixture `tests/threads/thread_world.py`; **T10a** (`/link`'s target: the fourth test dispatches `/link` to make a message that is not a `/remind`; merged before this ticket runs)
Branch: `p1/i7b-t10d-reminder-job`

## Goal
A `/remind` falls due and is posted. `/remind +2h @lchen check the bevels` queues a `thread.reminder` job whose id is the id of the dispatch message; when the job runs, `ThreadReminderKind` reads that message, parses its command line again and posts a `reminder` message as `svc:threads` that names who it is for. `tl_core/threads/reminders.py` has the kind, `ReminderWork`, `THREAD_SERVICE_ACTOR`, `started`, `run`, `failed` and `expired`; `reminder_text`, `prepare` and `settle` raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 21.5.** `/remind <when>`: reminders. **FANOUT D9:** `/remind` queues a `thread.reminder` job (`run_after`); it posts a `reminder` message as `svc:threads` naming who. Mentions are recorded; inbox delivery waits for its model.
>
> **ADR-0014 (job runner, final).** A kind has `started`, `prepare` (read-only; raise `JobFailure(code, message, retryable=...)`), `run` (pure), `settle` (writes, only if the claim is still ours; the queue guarantees at most once) and `failed`/`expired`. A non-retryable failure fails the job for good at once.
>
> **What is stored.** Nothing but the dispatch message: its body is the command line `/remind ...`, its id is the job id. `prepare` parses the body again with `CommandLineParser` and keeps `args.who` (names as typed, no sigil) and `args.text`.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-core/src/tl_core/jobs/runner.py` (read only):
```python
class JobFailure(Exception):
    """What a kind raises (or returns the news of) when an attempt cannot finish.

    ``code`` is short and fixed (``source_not_available``); ``message`` is words for a person,
    without paths or stack traces. A non-retryable failure fails the job for good at once.
    """

    def __init__(self, code: str, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable

class JobKind(Protocol):
    """A kind of job: the code that knows its record, its events and its work."""

    kind: str

    def started(self, uow: UnitOfWork, claim: Claim) -> None:
        """Append the "started" event of the attempt (same transaction as the claim)."""
        ...

    def prepare(self, uow: UnitOfWork, claim: Claim) -> Any:
        """Read what the work needs, in a read-only unit of work. Raise ``JobFailure``."""
        ...

    def run(self, work: Any) -> Any:
        """Do the work with no transaction open. Pure: no ledger, no network. May raise."""
        ...

    def settle(self, uow: UnitOfWork, claim: Claim, outcome: Any) -> None:
        """Write the results and the "succeeded" event. Called only when the claim is still ours."""
        ...

    def failed(
        self,
        uow: UnitOfWork,
        claim: Claim,
        failure: JobFailure,
        *,
        final: bool,
        retry_at: str | None,
    ) -> None:
        """Append the "failed" event of the attempt."""
        ...

    def expired(self, uow: UnitOfWork, item: Expired) -> None:
        """Append the final "failed" event of a job whose lease ran out with no attempt left."""
        ...
```

`packages/tl-core/src/tl_core/jobs/types.py` (read only):
```python
class Claim:
    """A job leased to one worker for one attempt."""

    job_id: str
    kind: str
    scope: str
    attempt: int
    max_attempts: int
    owner: str
    lease_until: str
```

`packages/tl-core/src/tl_core/threads/messages.py` (read only):
```python
def post_message(
    uow: UnitOfWork,
    *,
    record: ThreadRecord,
    actor: str,
    source: str,
    body: str,
    kind: str = "message",
    message_id: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    check_enabled: bool = True,
) -> CommandResult:
    """Append ``Thread.MessagePosted`` for ``record`` (the caller has already read the record).
    ...
```

`packages/tl-core/src/tl_core/threads/contract.py` (read only):
```python
class RemindArgs(_Args):
    verb: Literal["remind"] = "remind"
    #: As typed (``+2h``, ``2026-11-02T09:00``); the planner resolves it with the server clock.
    when: str
    who: list[str] = Field(default_factory=list[str], max_length=MAX_MENTIONS)
    text: str | None = None
```

`packages/tl-core/src/tl_core/threads/visibility.py` (read only):
```python
def readable_record(
    uow: UnitOfWork, record_id: str, *, actor: str, scope: str | None = None
) -> ThreadRecord: ...
```

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/threads/reminders.py (the file you edit)`
- `packages/tl-core/src/tl_core/threads/messages.py (`post_message`)`
- `packages/tl-core/src/tl_core/threads/effects.py (where the job is queued: read only)`
- `packages/tl-core/src/tl_core/jobs/runner.py (`JobKind`)`
- `tests/threads/thread_world.py (the fixture the test uses)`
- `docs/tickets/P1-I7/provided/t10d-test_reminders.py.txt (the test)`
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for `tl-core`, and `just check` runs it on the whole tree.
- The provided test lives under `docs/tickets/P1-I7/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I7/P1-I7-T10d.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. When you implement the stub, remove the `STUB` paragraph from the module docstring, every `STEPS` comment, the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line (L-P1-I3-3).
- Never change `schema/**` or anything under `generated/`. Never edit a file outside *Allowed paths*.
- Do not run `just test`, `just test-parity` or `just test-tui` (they take an hour); run the scoped commands in *Acceptance*. Other tests of `tests/threads/` exercise the same code (`test_planner.py`, `test_dispatch.py`); they are red until every ticket of the batch is merged and are not part of your acceptance.
- Tests that open a database use the `db` fixture of `tests/threads/conftest.py`, so they run once per adapter named by `--adapters` (default sqlite). `tests/threads/thread_world.py` holds the helpers; it is in the tree and read only (L-P1-I7B-1).

## Allowed paths
- `packages/tl-core/src/tl_core/threads/reminders.py (edit)`
- `tests/threads/test_reminders.py (create; byte-identical copy of the provided test)`
- `docs/reports/P1-I7/P1-I7-T10d.md (create)`

## Lines you must not change
- The signature, decorator and docstring of every function and class in the stub file: you replace only the bodies that have a `STEPS` comment.
- The provided test: the copy in `tests/threads/` stays byte-identical to `docs/tickets/P1-I7/provided/t10d-test_reminders.py.txt`.
- Everything under `tests/threads/` other than your copy, and `packages/tl-core/src/tl_core/threads/` other than the files in *Allowed paths* (the planner, the engine, `resolve.py`, `targets/__init__.py`).
- `ReminderWork`, `THREAD_SERVICE_ACTOR`, `_MESSAGE_SQL`, `started`, `run`, `failed` and `expired` in `reminders.py`.

## Steps
- `packages/tl-core/src/tl_core/threads/reminders.py` (edit)
- `tests/threads/test_reminders.py` (create)
- `docs/reports/P1-I7/P1-I7-T10d.md` (create)

1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I7/provided/t10d-test_reminders.py.txt` to `tests/threads/test_reminders.py`.
3. Implement `reminder_text`, `prepare` and `settle` by their STEPS comments; remove the STUB paragraph, the STEPS comments and the two lint-silencing lines.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest tests/threads/test_reminders.py -q
```
Expected: `just check` clean; 4 pass. The test also needs `tests/threads/test_dispatch.py`'s code path (the dispatch of `/remind`), which is final.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). Put `Deviations` first (or "none") and list every file you changed.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, if you think the kind should write an event in `started`, `failed` or `expired` (it must not), or if the test needs a change outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
