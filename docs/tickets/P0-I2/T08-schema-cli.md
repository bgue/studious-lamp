# P0-I2-T08 — `tl schema hash|lint|validate`

Status: ready
Tier: haiku
Labels: cli
Depends on: P0-I2-T01, P0-I2-T03, P0-I2-T08a (merged into the base of this branch)
Branch: `p0/i2a-t08-schema-cli`

## Goal
The `tl schema` command group prints the content hash of a scope's effective schema, lints the package files, and validates that every scope
compiles. The group, its options and its three command signatures already exist (`tl_cli/schema.py`, registered in `main.py`); the command
bodies raise `NotImplementedError`. After this ticket they work and a provided test file passes (15 tests).

## Brief references (pasted)
> **27.8 `tl schema` CLI:** `lint`, `diff`, `classify`, `impact --project P123`, `test --sample 1000`, `publish`, `adopt`, `crosswalk`, `promote`, `export-git` / `import-git`. (This increment: `hash`, `lint`, `validate`.)
> **27.3 Effective schema:** core + modules + company packages (pinned versions adopted by the project) + project packages (pinned versions) = effective schema for project P123 (content hash #a91f...3c).
> **27.6 Lint:** naming conventions, missing definitions or units, orphan code lists, duplicate detection.

### Specification (the provided test checks it)
All three commands take `--dir PATH` (already declared as `DirOption`; env `TL_SCHEMA_DIR`; default `schema/fixtures` via `default_schema_dir()`).
Use the helpers already in the file: `_registry(directory)`, `_scope(target)`, `_fail(message)`, the `_schema_errors()` context manager (turns `PackageError` and `SchemaCompileError` into `error: <message>` on stderr and exit code 1).

- `tl schema hash TARGET`: `TARGET` is `company`, a project id (`P123`) or `project:P123`. Inside `with _schema_errors():` load the registry, compute `scope = _scope(target)`; for a project scope, if the project id is not in `registry.projects()` call `_fail(f"unknown project {project!r}")`. Print `compose(registry.adopted(scope), scope).hash` (one line, 64 hex characters).
- `tl schema lint`: load the registry (inside `_schema_errors()`); `docs = [registry.get(name, version) for name in registry.names() for version in registry.versions(name)]`; `issues = lint_documents(docs)`. Print one line per issue: `f"{issue.severity} {issue.rule} {issue.package} {issue.path} {issue.message}"`, then `f"{errors} errors, {warnings} warnings"` (always the plural words). Exit code 1 when `errors > 0` (`raise typer.Exit(code=1)`), otherwise 0.
- `tl schema validate [TARGET ...]`: inside `_schema_errors()` load the registry, call `registry.check()`, and choose scopes: `[_scope(t) for t in targets]` when targets are given, otherwise `["company", *(f"project:{p}" for p in registry.projects())]`. Then for each scope, outside that context manager: in a `try`, `schema = compose(registry.adopted(scope), scope)` and `build_view(schema)` (the LinkML rendering, as a smoke check); on `PackageError` or `SchemaCompileError` print `f"error: {scope}: {exc}"` to stderr (`typer.echo(..., err=True)`), remember the failure and continue with the next scope; on success print `f"ok {scope} {schema.hash[:12]}"`. Exit code 1 after the loop if any scope failed.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I2/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copied test.
- `pyright` does not run strict on `tl_cli`, but keep annotations complete; `ruff` enforces 100 columns and import order (`uv run ruff check --fix` sorts imports; then `uv run ruff format`).
- The package-wide rule "catch only `ServiceError` and `ConcurrencyError`" gains `PackageError` and `SchemaCompileError` for this group only; the supervisor updates `AGENTS.md`.
- `uv` prints "UV_NATIVE_TLS is deprecated" on every call; ignore it. If imports fail in a fresh worktree run `uv sync --all-packages`. Do not pipe `just check` into `tail`.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-cli/src/tl_cli/schema.py (existing; replace the three `raise NotImplementedError  # P0-I2-T08` lines and add imports)
@app.command("hash")     def hash_command(target: Annotated[str, typer.Argument(...)], directory: DirOption = None) -> None
@app.command("lint")     def lint(directory: DirOption = None) -> None
@app.command("validate") def validate(targets: Annotated[list[str] | None, typer.Argument(...)] = None, directory: DirOption = None) -> None
# helpers in the file: _fail(message) -> NoReturn; _schema_errors() context manager; _registry(directory) -> PackageRegistry; _scope(target) -> str
```
```python
# imports to add
from tl_schema.compose import compose                      # (docs: Sequence[PackageDoc], scope: str) -> EffectiveSchema (.hash: str)
from tl_schema.linkml_render import build_view             # (schema: EffectiveSchema) -> SchemaView
from tl_schema.lint import lint_documents                  # (docs) -> list[LintIssue(severity, rule, package, path, message)]
from tl_schema.packages import PackageDoc                  # only if you annotate the docs list
# PackageRegistry: names() -> list[str]; versions(name) -> list[str]; get(name, version) -> PackageDoc;
#   projects() -> list[str]; adopted(scope) -> list[PackageDoc]; check() -> None (raises PackageError)
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-cli/src/tl_cli/schema.py`
- `packages/tl-cli/src/tl_cli/record.py` (the style of an existing group)
- `docs/tickets/P0-I2/provided/test_cli_schema.py.txt`
- `schema/fixtures/x.P123@1.4.0.yaml` (what the tests edit)
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/schema.py` (edit: implement the three commands)
- `packages/tl-cli/tests/test_cli_schema.py` (create: `cp` of the provided file, byte for byte)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_cli_schema.py.txt packages/tl-cli/tests/test_cli_schema.py`
2. Implement the three commands as specified.
3. Run the acceptance commands.

## Acceptance
```
uv run pytest packages/tl-cli/tests/test_cli_schema.py -q
uv run tl schema hash P123
uv run tl schema lint
uv run tl schema validate
just check
just test
diff docs/tickets/P0-I2/provided/test_cli_schema.py.txt packages/tl-cli/tests/test_cli_schema.py
```
Expected: 15 tests pass; `hash` prints a 64-hex line; `lint` prints the single L004 warning line and `0 errors, 1 warnings`; `validate` prints `ok company <12 hex>` and `ok project:P123 <12 hex>`; `just check` and `just test` exit 0; `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive output of the three `tl schema` commands.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change `main.py`, the registry, or any `tl_schema` module.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
