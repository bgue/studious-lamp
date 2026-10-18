# P1-I7-T02a — The `job` action executor and the example job

Status: ready
Tier: haiku
Labels: core
Depends on: — (the frozen contract and the conformance helper are in the tree; the entry point `echo` is registered in `packages/tl-core/pyproject.toml`)
Branch: `p1/i7a-t02a-job-executor`

## Goal
A `job` action can run. `packages/tl-core/src/tl_core/integration/executors/job.py` has `failed`, `use_jobs` and the module state (final); `_factory`, `result_problem` and `JobExecutor.execute` raise `NotImplementedError`. `packages/tl-core/src/tl_core/integration/action_jobs.py` has the example job `EchoJob` whose `run` raises `NotImplementedError`. You implement them. One provided test file must pass; it runs the shared executor contract checks and every way a job can misbehave. The test needs no database.

## Brief references (pasted)
> **Brief 18.7 Actions registry.** "An Action is a named, parameterised operation ... `executor`: `webhook`, `mcp_tool`, `connector`, `job` (internal), `agent`. ... The lifecycle (`Action.Requested -> Running -> Completed/Failed`) is ledgered." Phase 1 builds `job` and `webhook` only.
>
> **FANOUT D8.** "`job`: calls the `ActionJob` named in the config, found under `ACTION_JOB_ENTRY_POINT`; pure." A job action names installed code; an admin never supplies code. Whatever the job does wrong is a `failed` outcome with a fixed code; the executor never raises. `ACTION_MAX_RESULT_BYTES` (64 KiB as canonical JSON) bounds a result: a larger one fails the action, it is never cut.
>
> **Secrets and paths.** The text of an exception can hold a path or a value from the request, so only the exception *type* goes into a message.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-core/src/tl_core/integration/contract.py` (read only; abridged to what you use):
```python
ACTION_JOB_ENTRY_POINT = "throughline.action_jobs"
ACTION_MAX_RESULT_BYTES = 64 * 1024

class Problem(BaseModel):
    code: str      # ^[a-z][a-z0-9_]{0,63}$
    message: str   # at most 500 characters

class JobExecutorConfig(BaseModel):
    kind: Literal["job"] = "job"
    job: str       # ^[a-z][a-z0-9_.-]{0,62}$

class ActionRequest(BaseModel):
    invocation_id: str
    action: str
    action_version: int
    scope: str
    targets: list[RecordRef] = ...
    parameters: dict[str, Any] = ...
    invoked_by: str
    attempt: int
    config: JobExecutorConfig | WebhookExecutorConfig

class ActionOutcome(BaseModel):
    status: Literal["completed", "failed"]
    result: dict[str, Any] | None = None
    http_status: int | None = None
    retryable: bool = False
    problems: list[Problem] = ...   # a failed outcome names at least one
    notes: list[str] = ...

@runtime_checkable
class ActionJob(Protocol):
    name: str
    version: str
    side_effect_class: SideEffectClass
    def run(self, request: ActionRequest) -> ActionOutcome: ...
```
The stubs you complete are `.../integration/executors/job.py` and `.../integration/action_jobs.py`; each body has a STEPS comment. `packages/tl-core/pyproject.toml` already has `[project.entry-points."throughline.action_jobs"] echo = "tl_core.integration.action_jobs:EchoJob"`; do not edit it.

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/integration/executors/job.py` (the file you edit)
- `packages/tl-core/src/tl_core/integration/action_jobs.py` (the file you edit)
- `packages/tl-core/src/tl_core/integration/contract.py` (the models above)
- `docs/tickets/P1-I7/provided/t02a-test_job_executor.py.txt` (the test)
- `tests/contract/test_integration_contract.py` (`check_executor_contract`; read only)
- `docs/templates/haiku-report.md`
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages, and again after the branch gains an entry point (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for `packages/tl-core` (L-P1-I3-3: the stub's two lint-silencing header lines come out when you implement it).
- The provided test lives under `docs/tickets/P1-I7/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean (L-P1-I3-12).
- Commit your report at `docs/reports/P1-I7/P1-I7-T02a.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7). `docs/templates/haiku-report.md` is the template (L-P1-I3B-6).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*. **Known red on this branch:** `packages/tl-schema/tests/test_catalog.py::test_every_event_type_the_code_names_is_in_the_catalog` fails until workstream B adds its `Thread.*` catalog classes; it is not yours and not in any command below.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment, the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line when you implement the stub.
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never change `schema/**`, `pyproject.toml`, anything under `generated/`, or `tl_core/integration/contract.py` (frozen).
- Do not run `just test` or `just test-parity` (they take an hour); run the scoped commands in *Acceptance*. The test uses no database fixture, so it runs once whatever `--adapters` says: this ticket has no Postgres variant (L-P1-I1-6).
- The test count below was counted from the provided file (`grep -c "^def test_"`); a parametrized test counts once per case (L-P0-I8A-8).

## Allowed paths
- `packages/tl-core/src/tl_core/integration/executors/job.py` (edit)
- `packages/tl-core/src/tl_core/integration/action_jobs.py` (edit)
- `packages/tl-core/tests/test_job_executor.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I7/P1-I7-T02a.md` (create)

## Steps
1. `uv sync --all-packages` (this registers the `echo` entry point from `pyproject.toml`).
2. Copy `docs/tickets/P1-I7/provided/t02a-test_job_executor.py.txt` to `packages/tl-core/tests/test_job_executor.py`.
3. Implement the four bodies by their STEPS comments; remove the STUB paragraphs, the STEPS comments and the lint-silencing lines in both files.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-core/tests/test_job_executor.py -q
uv run pytest tests/contract -q
```
Expected: `just check` clean; the 19 test functions of the provided file pass; the contract tests pass.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if `test_the_example_job_is_registered_under_the_entry_point_group` fails after `uv sync --all-packages`: the entry point is the supervisor's.
- Stop if the test needs a change in `contract.py`, `pyproject.toml` or any file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
