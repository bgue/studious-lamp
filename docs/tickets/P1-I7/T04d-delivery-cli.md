# P1-I7-T04d — `tl delivery`: the inbound error queue and the dry run of a mapping

Status: ready
Tier: haiku
Labels: cli
Depends on: — (the services are in the tree)
Branch: `p1/i7a-t04d-delivery-cli`

## Goal
An admin can read the inbound error queue, retry a failed delivery and ask what a mapping would do, from the command line. `packages/tl-cli/src/tl_cli/delivery.py` is registered as `tl delivery` and has the group, `delivery_line`, `_configure_store` and the SQL (final); `ls`, `show`, `retry` and `dry_run` raise `NotImplementedError`. You implement them from the docstrings. One provided test file must pass.

## Brief references (pasted)
> **FANOUT D4 (error queue).** "Admin only. `RetryInboundDelivery` re-runs a failed delivery through the same worker path with the current mapping, optionally with a corrected payload that is stored as a new object; the event names the admin and both hashes. Dry run: `DryRunInboundMapping` (admin) returns the planned commands for a sample or a stored delivery and writes nothing."
>
> **Why the details matter.** The received body is never shown and never changed: `show` prints the size and the hash, not the payload. A message never holds a payload excerpt. A retry uses the endpoint's *current* mapping, so an admin fixes the mapping first and retries after.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/integration_support.py` (final; read only; the helpers you call):
```python
DEFAULT_ACTOR: str                                   # user:dev
SOURCE = "cli"
ActorOption, ProjectOption, CompanyOption            # the typer option annotations
def fail(message: str) -> NoReturn                   # `error: <message>` on stderr, exit code 1
def factory(ctx) -> ContextManager[UowFactory]       # `with factory(ctx) as opened:`; opened() writes,
                                                     # opened(readonly=True) reads
def service_errors() -> ContextManager[None]         # a refused command or bad input becomes `error:`
def scope_of(project: str | None, company: bool) -> str   # project:<ID> or company; exactly one given
def read_json_file(path: str) -> Any                 # a file, or - for standard input; bad JSON fails
def rows(uow, sql: str, **params) -> list[dict]      # a *_json column is parsed, named without _json
def one(uow, what: str, sql: str, **params) -> dict  # the first row or `error: no <what>`
def line(*columns) -> str                            # columns joined by two spaces; None prints "-"
def record_id_of(uow, key: str, scope: str) -> str   # the id of the live record with this key
def pairs(values: list[str], what: str) -> dict[str, str]   # ["a=1"] -> {"a": "1"}
def admin_gate(ctx) -> None                          # refuses a signed-in non-admin
```

`packages/tl-core/src/tl_core/integration/inbound/delivery.py` (read only; abridged):
```python
class RetryInboundDelivery(Command):   # actor, source, scope, delivery_id, corrected_payload: Any | None
def handle_retry_delivery(uow, cmd) -> CommandResult   # raises IntegrationStateError unless failed or killed
class MappingDryRun(BaseModel):
    endpoint: str; endpoint_version: int; status: str
    problems: list[Problem]            # .code, .message
    commands: list[PlannedCommand]     # .command_type, .permitted, .summary, .problem
def dry_run_mapping(uow, runner, *, endpoint_id, scope, sample=None, delivery_id=None) -> MappingDryRun
```
`tl_cli.endpoint.split_path(path) -> (app, name)` and `PathArg` (final; import them). `tl_api.commands.command_runner()` is the runner (import it inside the function).

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/delivery.py` (the file you edit)
- `packages/tl-cli/src/tl_cli/integration_support.py` and `endpoint.py` (read only)
- `packages/tl-core/src/tl_core/integration/inbound/delivery.py` (read only)
- `docs/tickets/P1-I7/provided/t04d-test_cli_delivery.py.txt` (the test)
- `docs/templates/haiku-report.md`
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for the packages: the stub's two lint-silencing header lines come out when you implement it (L-P1-I3-3).
- The provided test lives under `docs/tickets/P1-I7/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean, and it was run against a reference implementation (L-P1-I3-12). Its helpers are in `packages/tl-cli/tests/intcli_support.py`, which is in the tree and is final.
- Commit your report at `docs/reports/P1-I7/P1-I7-T04d.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7). `docs/templates/haiku-report.md` is the template (L-P1-I3B-6).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*. **Known red on this branch:** `packages/tl-schema/tests/test_catalog.py::test_every_event_type_the_code_names_is_in_the_catalog` fails until workstream B adds its `Thread.*` catalog classes; it is not yours and not in any command below.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` paragraph that tells you how (the docstrings keep their first sentence), the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line when you implement the stub. Keep every signature, option name, help text and printed line exactly as the STEPS and the test say.
- A command writes with `--actor` (the stub's signature has it; the actor hook gives it the signed-in user as default, ADR-0009 section 7). A failure is `error: <message>` on stderr and exit code 1, through `service_errors()` or `fail()` of `tl_cli.integration_support`; never a traceback. A secret is printed only where the STEPS say, once, and never logged or echoed again.
- A command-group test builds a ledger with the `new_db` fixture, so it also runs on Postgres. Under load a file takes one to three minutes; run the acceptance commands once each. Do not run `just test` or `just test-parity` (they take an hour and the box is shared).
- The test count below was counted from the provided file (`pytest --collect-only -q`); a parametrized test counts once per case (L-P0-I8A-8).

## Allowed paths
- `packages/tl-cli/src/tl_cli/delivery.py` (edit)
- `packages/tl-cli/tests/test_cli_delivery.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I7/P1-I7-T04d.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I7/provided/t04d-test_cli_delivery.py.txt` to `packages/tl-cli/tests/test_cli_delivery.py`.
3. Implement the bodies that raise `NotImplementedError` by their docstrings (the paragraph that starts `STEPS`); remove the STUB paragraph and the two lint-silencing lines.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_delivery.py -q
```
Expected: `just check` clean; the provided test file passes (8 cases from 8 test functions).

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`).

## Escalation triggers
- Stop and report *Blocked* if a docstring and the provided test disagree.
- Stop if the test needs a change outside *Allowed paths*.
- Never print the payload of a delivery, or any excerpt of it, in any command.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
