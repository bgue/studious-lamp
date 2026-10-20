# P1-I7-T10c — The deterministic /summarise text

Status: merged
Tier: haiku
Labels: core
Depends on: S1 and S2 (in the tree): `tl_core/threads/queries.py` (`ThreadPage`), `contract.py`; no database fixture is needed
Branch: `p1/i7b-t10c-thread-summary`

## Goal
`/summarise` has its text. `build_summary(page)` in `tl_core/threads/summary.py` turns one page of a thread into a short, fixed-format summary: counts, participants, the commands that were dispatched, and the first line of the last messages people wrote. It is a pure function (ADR-0008 decision 8: no model, no spend), so the same page always gives the same text and the preview token of `/summarise` stays valid until the thread changes. The module has the constants and `_first_line`; `build_summary` raises `NotImplementedError`. You implement it. One provided test file must pass. The test needs no database.

## Brief references (pasted)
> **Brief 21.5.** `/summarise`: agent summary of the thread (posted as a proposal). **ADR-0008 decision 8:** no model call and no spend in Phase 1, so the summary is deterministic: counts, participants, dispatched commands, the first lines of the last `SUMMARY_MAX_MESSAGES` messages.
>
> **Where it is used.** `targets/summarise.py` (final) calls `build_summary(read_thread(...))` and plans a `ThreadSummary` effect with that text; the confirmation posts it as a message of kind `summary`. The text is part of the plan, so it must not change between two calls on the same page.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-core/src/tl_core/threads/contract.py` (read only):
```python
SUMMARY_MAX_MESSAGES = 50
SUMMARY_MAX_CHARS = 2_000

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

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/threads/summary.py (the file you edit)`
- `packages/tl-core/src/tl_core/threads/queries.py`
- `packages/tl-core/src/tl_core/threads/targets/summarise.py (the caller)`
- `docs/tickets/P1-I7/provided/t10c-test_summary.py.txt (the test)`
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for `tl-core`, and `just check` runs it on the whole tree.
- The provided test lives under `docs/tickets/P1-I7/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I7/P1-I7-T10c.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. When you implement the stub, remove the `STUB` paragraph from the module docstring, every `STEPS` comment, the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line (L-P1-I3-3).
- Never change `schema/**` or anything under `generated/`. Never edit a file outside *Allowed paths*.
- Do not run `just test`, `just test-parity` or `just test-tui` (they take an hour); run the scoped commands in *Acceptance*. Other tests of `tests/threads/` exercise the same code (`test_planner.py`, `test_dispatch.py`); they are red until every ticket of the batch is merged and are not part of your acceptance.
- Tests that open a database use the `db` fixture of `tests/threads/conftest.py`, so they run once per adapter named by `--adapters` (default sqlite). `tests/threads/thread_world.py` holds the helpers; it is in the tree and read only (L-P1-I7B-1).

## Allowed paths
- `packages/tl-core/src/tl_core/threads/summary.py (edit)`
- `tests/threads/test_summary.py (create; byte-identical copy of the provided test)`
- `docs/reports/P1-I7/P1-I7-T10c.md (create)`

## Lines you must not change
- The signature, decorator and docstring of every function and class in the stub file: you replace only the bodies that have a `STEPS` comment.
- The provided test: the copy in `tests/threads/` stays byte-identical to `docs/tickets/P1-I7/provided/t10c-test_summary.py.txt`.
- Everything under `tests/threads/` other than your copy, and `packages/tl-core/src/tl_core/threads/` other than the files in *Allowed paths* (the planner, the engine, `resolve.py`, `targets/__init__.py`).
- `LINE_CHARS` and `_first_line` in `summary.py`.

## Steps
- `packages/tl-core/src/tl_core/threads/summary.py` (edit)
- `tests/threads/test_summary.py` (create)
- `docs/reports/P1-I7/P1-I7-T10c.md` (create)

1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I7/provided/t10c-test_summary.py.txt` to `tests/threads/test_summary.py`.
3. Implement `build_summary` by its STEPS comment; remove the STUB paragraph, the STEPS comment and the two lint-silencing lines.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest tests/threads/test_summary.py -q
```
Expected: `just check` clean; 7 pass.

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
