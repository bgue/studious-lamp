# P1-I3-T14d — CLI `tl derive publish` and `tl derive compensate`

Status: ready
Tier: haiku
Labels: cli
Depends on: S5; T14a and T14b for the test setup (the supervisor merges them first)
Branch: `p1/i3a-t14d-cli-derive-publish`

## Goal
A person previews and approves the publication of a valid derived document, and takes it back, from the terminal. Both commands preview by default and write only with `--apply`. `packages/tl-cli/src/tl_cli/derive_publish.py` has the group, the options and the docstrings (exact output lines) written; the bodies of `publish` and `compensate` raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **ADR-0014 (the derivation pipeline).** A derived document is the table of data read from one revision of a controlled document (a rendition, or a CSV or XLSX a person attached), checked against a document schema and, when valid and approved, published as tags or documents. Rows and reports are files; each pass over a file is a content revision. Starting, validating and cancelling are open to any signed-in person; publishing into tags and compensating need the admin role, publishing into documents the document controller role. A publication only creates records; compensation takes the whole batch back or nothing.
>
> **Surfaces do not re-implement rules.** The module (`tl_mod_documents.derivation`) decides; a surface parses its input, calls one function and prints what comes back.
>
> **Publication (ADR-0014 sections 5 and 6).** One correlated import through module commands; it creates records and never changes existing ones; rows whose key exists need `--skip-existing`. Publishing into tags needs the admin role (`require_admin`), into documents the document controller role (`require_controller`); compensation needs admin. The gates are in the stub already (final); the correlation id is made by the server with the prefix `derive:`.

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
`tl_cli.session` (read only): `require_admin(db)`, `require_controller(db)` exit with `error: ...` when the signed-in person lacks the role.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/derive_publish.py` (the file you edit)
- `packages/tl-cli/src/tl_cli/derive_support.py`
- `packages/tl-modules/documents/src/tl_mod_documents/derivation/publish.py` (`PublishPlan`, `PlanRow`, `CompensationPlan`, the commands and handlers; read the class docstrings only)
- `packages/tl-cli/tests/derivecli_support.py`
- `docs/tickets/P1-I3/provided/t14d-test_cli_derive_publish.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for the packages it checks; `just check` runs it on the whole tree.
- The provided test lives under `docs/tickets/P1-I3/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I3/P1-I3-T14d.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. When you implement the stub, remove the `STUB` paragraph from the module docstring, every `STEPS` comment, the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line.
- Never change `schema/**` or anything under `generated/`. Never edit a file outside *Allowed paths*.
- Do not run `just test`, `just test-parity` or `just test-tui` (they take an hour); run the scoped commands in *Acceptance*.
Expected: `just check` clean; 8 pass on SQLite; with both adapters 14 pass and 2 skip (the role test and the actor test, which are about a setup the Postgres conftest replaces).

## Allowed paths
- pytest runs in importlib mode: a test cannot import a sibling test file; the helpers it needs are `packages/tl-cli/tests/derivecli_support.py`, `doccli_support.py` and `auth_support.py` (all in the tree, read only) (L-P0-I2-B1).
- These tests use the `new_db` fixture, so they run on SQLite and, with `--adapters sqlite,postgres`, on Postgres (L-P1-I1-6). On SQLite an admin command needs a signed-in admin: the helpers do `bootstrap` and `sign_in`; do not weaken `require_admin` to make a test pass.
- The commands call the module's functions directly (`open_uow`, a `handle_*` function or a `views.*` read) and print; they do not re-implement any rule. A refusal is a `ServiceError` and `service_errors()` turns it into `error: ...` on stderr and exit 1.
- Output lines are asserted exactly, including the two spaces between fields: copy the formats from the docstring of each command.
- This ticket's test file has 8 test functions. Its setup uses `tl derive open|content|start|worker` and `tl derive schema register` (T14a, T14b); the supervisor merges those first.
- The gate comes first: a person without the role must see the error and no record may be written.

## Lines you must not change
Both commands start with `who = acting(db, actor)` and, with `--apply`, the role gate (`_require_publisher` for `publish`: admin for tags, document controller or admin for documents; `require_admin` for `compensate`), all before anything is read for output or written (security review of P1-I3, findings 1 and 2). They are written in the stub and are final: keep them, use `who` as the actor of the command, and do not move them. `--actor` is declared with the default `DEV_ACTOR` so that the hook of `tl_cli.actor_hook` installs; do not change that declaration.

## Steps
- `packages/tl-cli/src/tl_cli/derive_publish.py` (edit)
- `packages/tl-cli/tests/test_cli_derive_publish.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I3/P1-I3-T14d.md` (create)

## Acceptance
```
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I3/provided/t14d-test_cli_derive_publish.py.txt` to `packages/tl-cli/tests/test_cli_derive_publish.py`.
3. Implement the two bodies by their STEPS comments; remove the STUB paragraph, the STEPS comments and the two lint-silencing lines.
4. Run the acceptance commands.
```
just check
uv run pytest packages/tl-cli/tests/test_cli_derive_publish.py -q
TL_REQUIRE_POSTGRES=1 uv run pytest packages/tl-cli/tests/test_cli_derive_publish.py -q --adapters sqlite,postgres

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
