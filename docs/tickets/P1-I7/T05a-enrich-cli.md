# P1-I7-T05a — `tl enricher` and `tl enrich`: register enrichers, review their values

Status: ready
Tier: haiku
Labels: cli
Depends on: — (the services are in the tree)
Branch: `p1/i7a-t05a-enrich-cli`

## Goal
An admin can register enrichers, and a person can review what they proposed, from the command line. `packages/tl-cli/src/tl_cli/enricher.py` (`tl enricher`) and `enrich.py` (`tl enrich`) are registered and have their groups, the line formats, `enable`, `disable` and `_switch` (final); `ls`, `show`, `register` of `enricher.py` and `ls`, `show`, `accept`, `reject`, `run` of `enrich.py` raise `NotImplementedError`. You implement them from the docstrings. One provided test file must pass.

## Brief references (pasted)
> **Brief 18.9 Enrichment.** "Enrichers write back only into their own namespaced psets (`enrich.<enricher>.*`) ... Each enrichment value carries provenance ... Acceptance policy is set per property: `auto` (above a confidence threshold), `propose` (a person accepts it in a review queue), or `shadow`. Enrichment never overwrites authoritative fields."
>
> **FANOUT D6.** "`AcceptEnrichment` writes the value into the enricher's layer through a Python-only path and runs the target type's `SetPsetValues` allow-list and guards, so a closed type stays closed. It never writes an authoritative pset." Registering an enricher is the admin's; running one, accepting and rejecting are a person's.
>
> **Why the details matter.** A rejected value is not proposed to a person again; a shadow value is never accepted. The CLI only asks; the service decides, so print what the service answers and no more.

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

`packages/tl-core/src/tl_core/integration/enrichers/service.py` and `commands.py` (read only; abridged):
```python
class RegisterEnricher(Command):    # actor, source, scope, name, when: dict, properties: list[dict], access, owner, integration_app
class SetEnricherEnabled(Command):  # + enricher_id, enabled: bool
def handle_register_enricher(uow, cmd) -> CommandResult      # .stream_id
class RunEnricher(Command):         # + enricher: str (the name), record_id: str
class AcceptEnrichment(Command):    # + value_id: str
class RejectEnrichment(Command):    # + value_id: str, reason: str
def handle_run_enricher(uow, cmd) -> CommandResult           # .events: the Enrichment.* events it wrote
def handle_accept_enrichment(uow, cmd) -> CommandResult
def handle_reject_enrichment(uow, cmd) -> CommandResult
```
Rows: `cur_enricher` (`name`, `enricher_id`, `scope`, `version`, `code_version`, `enabled`, `access`, `owner`, `service_actor`, `when_json`, `properties_json`) and `cur_enrichment_value` (`value_id`, `acceptance_state`, `property_path`, `value_json`, `confidence`, `target_id`, `enricher`, `enricher_version`, `inputs_json`, `produced_at`, `decided_by`, `decided_at`, `reason`, `seq`); `rows` and `one` parse the `*_json` columns and drop the suffix.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/enricher.py` and `enrich.py` (the files you edit)
- `packages/tl-cli/src/tl_cli/integration_support.py` (the helpers; read only)
- `packages/tl-core/src/tl_core/integration/enrichers/service.py` and `commands.py` (read only)
- `docs/tickets/P1-I7/provided/t05a-test_cli_enrich.py.txt` (the test)
- `docs/templates/haiku-report.md`
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for the packages: the stub's two lint-silencing header lines come out when you implement it (L-P1-I3-3).
- The provided test lives under `docs/tickets/P1-I7/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean, and it was run against a reference implementation (L-P1-I3-12). Its helpers are in `packages/tl-cli/tests/intcli_support.py`, which is in the tree and is final.
- Commit your report at `docs/reports/P1-I7/P1-I7-T05a.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7). `docs/templates/haiku-report.md` is the template (L-P1-I3B-6).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*. **Known red on this branch:** `packages/tl-schema/tests/test_catalog.py::test_every_event_type_the_code_names_is_in_the_catalog` fails until workstream B adds its `Thread.*` catalog classes; it is not yours and not in any command below.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` paragraph that tells you how (the docstrings keep their first sentence), the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line when you implement the stub. Keep every signature, option name, help text and printed line exactly as the STEPS and the test say.
- A command writes with `--actor` (the stub's signature has it; the actor hook gives it the signed-in user as default, ADR-0009 section 7). A failure is `error: <message>` on stderr and exit code 1, through `service_errors()` or `fail()` of `tl_cli.integration_support`; never a traceback. A secret is printed only where the STEPS say, once, and never logged or echoed again.
- A command-group test builds a ledger with the `new_db` fixture, so it also runs on Postgres. Under load a file takes one to three minutes; run the acceptance commands once each. Do not run `just test` or `just test-parity` (they take an hour and the box is shared).
- The test count below was counted from the provided file (`pytest --collect-only -q`); a parametrized test counts once per case (L-P0-I8A-8).

## Allowed paths
- `packages/tl-cli/src/tl_cli/enricher.py` (edit)
- `packages/tl-cli/src/tl_cli/enrich.py` (edit)
- `packages/tl-cli/tests/test_cli_enrich.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I7/P1-I7-T05a.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I7/provided/t05a-test_cli_enrich.py.txt` to `packages/tl-cli/tests/test_cli_enrich.py`.
3. Implement the bodies that raise `NotImplementedError` by their docstrings (the paragraph that starts `STEPS`); remove the STUB paragraph and the two lint-silencing lines.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_enrich.py -q
```
Expected: `just check` clean; the provided test file passes (15 cases from 12 test functions).

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`).

## Escalation triggers
- Stop and report *Blocked* if a docstring and the provided test disagree.
- Stop if the test needs a change outside *Allowed paths*.
- `accept` must go through `handle_accept_enrichment`; never write a pset yourself.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
