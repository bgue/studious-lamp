# P1-I3-T14c — CLI `tl derive show|report|rows|diff|check|validate`

Status: ready
Tier: haiku
Labels: cli
Depends on: S4, T14b (its `open`, `start`, `content` and `worker` are used by the test setup; the supervisor merges T14b first or runs this ticket after it)
Branch: `p1/i3a-t14c-cli-derive-read`

## Goal
A person looks at a derived document from the terminal: its passes, the validation report, the extracted rows, the diff against the previous pass, a check against another schema version, and a queued re-validation. `packages/tl-cli/src/tl_cli/derive_read.py` has the group, the options, the docstrings (exact output lines) and the helper `_print_report` written; the bodies of `show`, `report`, `rows_command`, `diff`, `check` and `validate` raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **ADR-0014 (the derivation pipeline).** A derived document is the table of data read from one revision of a controlled document (a rendition, or a CSV or XLSX a person attached), checked against a document schema and, when valid and approved, published as tags or documents. Rows and reports are files; each pass over a file is a content revision. Starting, validating and cancelling are open to any signed-in person; publishing into tags and compensating need the admin role, publishing into documents the document controller role. A publication only creates records; compensation takes the whole batch back or nothing.
>
> **Surfaces do not re-implement rules.** The module (`tl_mod_documents.derivation`) decides; a surface parses its input, calls one function and prints what comes back.
>
> **Reads write nothing.** `report` prints the stored report of a pass; `check` validates the stored rows against a schema now and stores nothing; `validate` queues a job that keeps the report (`ValidateDerived`, any signed-in person). Rows and reports are files, read through `configure_files()`.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/derive_support.py` (final; read only):
```python
Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]
OptProject = Annotated[str | None, typer.Option("--project", ...)]
Actor = Annotated[str | None, typer.Option("--actor", ...)]   # default: the session's actor
SOURCE = "cli"
def fail(message: str) -> NoReturn: ...              # prints `error: <message>` on stderr, exit 1
def service_errors() -> ContextManager[None]: ...    # ServiceError and friends -> `error: ...`, exit 1
def configure_files() -> FileService: ...            # the module's file reads use this process's store
def scope_of(project: str | None, company: bool = False) -> str: ...
def acting(db: DbTarget, actor: str | None) -> str: ...
def cell(value: object, width: int = 40) -> str: ...  # `-` for none, one line, cut to width
```
`tl_mod_documents.derivation.views` (read only): `schema_summaries`, `schema_view`, `find_derived`, `derived_summaries`, `derived_view`, `job_views`, `job_view`, `derived_rows`, `derived_report`, `derived_diff`, `validate_stored`, `publish_preview`, `compensation_preview`. The handlers and commands are in `tl_mod_documents.derivation.{schemas,derived,publish}`. Each stub already imports what its bodies need.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/derive_read.py` (the file you edit)
- `packages/tl-cli/src/tl_cli/derive_support.py`
- `packages/tl-modules/documents/src/tl_mod_documents/derivation/views.py` (the read functions and their models)
- `packages/tl-cli/tests/derivecli_support.py`
- `docs/tickets/P1-I3/provided/t14c-test_cli_derive_read.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for the packages it checks; `just check` runs it on the whole tree.
- The provided test lives under `docs/tickets/P1-I3/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I3/P1-I3-T14c.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. When you implement the stub, remove the `STUB` paragraph from the module docstring, every `STEPS` comment, the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line.
- Never change `schema/**` or anything under `generated/`. Never edit a file outside *Allowed paths*.
- Do not run `just test`, `just test-parity` or `just test-tui` (they take an hour); run the scoped commands in *Acceptance*.
Expected: `just check` clean; 9 pass on SQLite; with both adapters 17 pass and 1 skips (the actor test, which is about a setup the Postgres conftest replaces).

## Allowed paths
- pytest runs in importlib mode: a test cannot import a sibling test file; the helpers it needs are `packages/tl-cli/tests/derivecli_support.py`, `doccli_support.py` and `auth_support.py` (all in the tree, read only) (L-P0-I2-B1).
- These tests use the `new_db` fixture, so they run on SQLite and, with `--adapters sqlite,postgres`, on Postgres (L-P1-I1-6). On SQLite an admin command needs a signed-in admin: the helpers do `bootstrap` and `sign_in`; do not weaken `require_admin` to make a test pass.
- The commands call the module's functions directly (`open_uow`, a `handle_*` function or a `views.*` read) and print; they do not re-implement any rule. A refusal is a `ServiceError` and `service_errors()` turns it into `error: ...` on stderr and exit 1.
- Output lines are asserted exactly, including the two spaces between fields: copy the formats from the docstring of each command.
- This ticket's test file has 9 test functions. Several run the worker through `tl derive worker`, which is finished (T14b's file; if it is still a stub on your branch, the T14b ticket merges first: ask the supervisor).

## Lines you must not change
`validate` starts with `who = acting(db, actor)`: the actor check comes before anything is read or written (security review of P1-I3, finding 2). Keep it, and use `who` as the command's actor. `--actor` is declared with the default `DEV_ACTOR` so that the hook of `tl_cli.actor_hook` installs; do not change that declaration.

## Steps
- `packages/tl-cli/src/tl_cli/derive_read.py` (edit)
- `packages/tl-cli/tests/test_cli_derive_read.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I3/P1-I3-T14c.md` (create)

## Acceptance
```
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I3/provided/t14c-test_cli_derive_read.py.txt` to `packages/tl-cli/tests/test_cli_derive_read.py`.
3. Implement the six bodies by their STEPS comments; remove the STUB paragraph, the STEPS comments and the two lint-silencing lines.
4. Run the acceptance commands.
```
just check
uv run pytest packages/tl-cli/tests/test_cli_derive_read.py -q
TL_REQUIRE_POSTGRES=1 uv run pytest packages/tl-cli/tests/test_cli_derive_read.py -q --adapters sqlite,postgres

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, or if a test needs a change outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
