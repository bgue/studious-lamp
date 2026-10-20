# P1-I8-T05a4c — `tl schema import-git`: draft the packages a directory of files holds

Status: ready
Tier: haiku
Review: full
Labels: cli, schema-registry, files
Depends on: P1-I8-S2 and P1-I8-S5 on `p1/i8`; no other ticket (it does not need `export-git`)
Branch: `p1/i8-t05a4c-import-git`

## Goal
A steward edits package files in a git repository and brings them into the registry as drafts. `packages/tl-cli/src/tl_cli/schema_import.py` holds the command `tl schema import-git DIR [--dry-run]` (already registered in `tl schema`). It checks every file first, then drafts each new version exactly as `tl schema package draft FILE` does; nothing is analysed, submitted or published. `_files`, `_read` and `register` are complete; `import_git` raises `NotImplementedError` today. You write its body by the STEPS comments and the output formats in its docstring so the one provided test file passes. The files are untrusted input: the reading rules are in `_files` and `_read`; do not weaken them.

## Brief references (pasted)
> **Brief 27.8.** `tl schema` CLI: ... `export-git` / `import-git`. Agents can draft, but humans review and publish.
>
> **Increment 8 decisions (FANOUT D2, D4).** Drafting is any signed-in person's, and the module binds analyse and submit to the person who drafted. A draft of a version that is already in force (in the schema directory or published) is refused by the module (`DuplicateSchemaPackageError`); the command reports such a file as `skipped` instead of failing the whole import. A package does not parse: the module's message (`InvalidSchemaPackageError`) is the reason.

### Specification
- `analysis.parse_content(text)` (from `tl_mod_schemareg`) parses and checks size, YAML and shape and raises `InvalidSchemaPackageError`; it returns a `PackageDoc` with `.package`, `.version`, `.key()`.
- `registry.find_package(conn, name, version)` returns the ledger's row (with `.content`) or None. `analysis.provider().registry().origin(name, version)` is not None when the schema directory or a published version answers for that version.
- The file name must be `<package>@<version>.yaml`; the check is on the parsed package, so a misnamed file is a problem, not a draft.
- The ledger is read in one read-only unit of work; each draft is its own `open_uow(db)` inside `service_errors()` (an earlier draft stays when a later one fails; that cannot happen after the checks, except on a race).

### Learnings that apply
> **L-P1-I3-3.** A stub also fails pyright on unused imports, so the stub file carries `# ruff: noqa: F401` and a `# pyright: reportUnusedImport=false` line. Remove both with the STEPS comments when the body is written, and remove every import the finished file does not use.
>
> **L-P1-I4-9.** A first `just check` in a fresh worktree takes over two minutes: run it with a 600 000 ms timeout (or in the background and wait). Run `uv run ruff format <file>` first, because the format check rewrites a hand-wrapped line.
>
> **L-P0-I1-6.** ruff's `E501` applies to comments and docstrings at 100 columns.
>
> **L-P0-I6C-8.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`.
>
> **L-P1-I8-5.** Never delete anything under `/tmp/pytest-of-root`: other agents use it. Give each pytest run `--basetemp=/tmp/pt-<ticket>` and remove only that directory after you have read the exit code.
>
> **L-P1-I4-16.** A read command is easy to get wrong in the part the test does not touch (a fixed value, the other half of a condition, the order of fields). Print exactly the fields and the order in the docstring; the provided test checks them with values that differ from each other.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/schema_import.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401
# pyright: reportUnusedImport=false
"""`tl schema import-git DIR [--dry-run]`: draft the packages a directory of files holds (T05a4c).

STUB: this file is the interface P1-I8-T05a4c implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it. `_files`, `_read` and `register` are
complete.

DIR is what `tl schema export-git` writes, or a git checkout of it: files `<package>@<version>.yaml`
directly in DIR. Each becomes a Draft package version, drafted by the signed-in person, exactly as
`tl schema package draft FILE` would; nothing is analysed, submitted or published. The files are
untrusted: only regular files are read (links are not followed), at most 200 of them, each at most
`MAX_CONTENT_BYTES`, and a file name must say what the file holds. One bad file stops the import
before anything is drafted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_schemareg import analysis, registry
from tl_mod_schemareg.errors import InvalidSchemaPackageError
from tl_mod_schemareg.handlers.packages import DraftSchemaPackage, handle_draft_schema_package
from tl_mod_schemareg.limits import MAX_CONTENT_BYTES
from tl_schema.packages import PackageDoc, version_tuple

from tl_cli.derive_support import DEV_ACTOR, SOURCE, Actor, acting, fail, service_errors
from tl_cli.session import require_session

MAX_FILES = 200


def _files(directory: Path) -> list[Path]:
    """The `*.yaml` entries directly in `directory`, by name (a link or folder is still listed)."""
    found = sorted(p for p in directory.iterdir() if p.name.endswith(".yaml"))
    if len(found) > MAX_FILES:
        fail(f"{directory} holds more than {MAX_FILES} package files")
    return found


def _read(path: Path) -> tuple[str | None, str | None]:
    """`(text, None)` for a usable file, `(None, problem)` for one that is not."""
    if path.is_symlink() or not path.is_file():
        return None, "is not a regular file"
    if path.stat().st_size > MAX_CONTENT_BYTES:
        return None, f"is larger than {MAX_CONTENT_BYTES} bytes"
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError:
        return None, "is not UTF-8 text"


def import_git(
    ctx: typer.Context,
    directory: Annotated[
        Path,
        typer.Argument(
            help="The directory of <package>@<version>.yaml files.",
            exists=True,
            file_okay=False,
            readable=True,
        ),
    ],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Say what would be drafted; draft nothing.")
    ] = False,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Draft every package version in DIR that the registry does not hold yet.

    First every file is checked (nothing is drafted while any file has a problem). A problem is
    the line `problem <file> <reason>`: the reason is `is not a regular file`, `is larger than
    <n> bytes`, `is not UTF-8 text`, the module's message for a package that does not parse,
    `name does not match its package and version`, or `exists with other text` (the registry holds
    that version with other text). With a problem the last line is the summary and the exit code
    is 1.

    Then one line per package, by name and version: `unchanged <key>` (the registry holds this
    very text), `skipped <key> in force already` (the schema directory or a published version
    answers for it, so a draft is refused) or `drafted <key> <id>` (`would draft <key>` with
    `--dry-run`). The last line is
    `imported <d> drafted, <u> unchanged, <s> skipped, <p> problems`, or
    `dry run <d> to draft, <u> unchanged, <s> skipped, <p> problems`.
    """
    # STEPS
    # 1. db: DbTarget = ctx.obj; require_session(db).
    # 2. In `with service_errors(), open_uow(db, readonly=True) as uow:` take
    #    `held = analysis.provider()` and, for each path in `_files(directory)`, `_read` it;
    #    collect problems as `(path.name, reason)`. Parse the text with
    #    `analysis.parse_content(text)` (a problem with `str(exc)` on InvalidSchemaPackageError);
    #    the name must be `f"{doc.package}@{doc.version}.yaml"`. Then
    #    `registry.find_package(uow.conn(), doc.package, doc.version)`: a row with the same
    #    `content` is `unchanged`, a row with other content is a problem, no row and
    #    `held.registry().origin(doc.package, doc.version) is not None` is `skipped`, else `draft`.
    #    Keep `(doc, text, state)` triples.
    # 3. Print `problem <file> <reason>` for each problem; with any, print the summary (0 drafted)
    #    and `raise typer.Exit(code=1)`.
    # 4. Sort the triples by `(doc.package, version_tuple(doc.version))` and print one line each
    #    as in the docstring. For state `draft` and no `--dry-run` open `open_uow(db)` inside
    #    `service_errors()` and call handle_draft_schema_package with
    #    DraftSchemaPackage(actor=acting(db, actor), source=SOURCE, scope="company",
    #    content=text); print `drafted <doc.package>@<doc.version> <result.stream_id>`.
    # 5. Print the summary line.
    raise NotImplementedError("STEPS: see the comments")


def register(app: typer.Typer) -> None:
    """Add the command to `tl schema`."""
    app.command("import-git")(import_git)
```

From `tl_mod_schemareg` (read-only; abridged):
```python
class DraftSchemaPackage(Command):      # handlers.packages; extra fields forbidden
    content: str
    changelog: str | None = None
    # every Command also has: actor: str, source: str, scope: str
def handle_draft_schema_package(uow, cmd: DraftSchemaPackage) -> CommandResult: ...

class CommandResult(BaseModel):
    stream_id: str        # the new package's record id
    key: str | None       # name@version

# registry.PackageRow: .package, .version, .content, .state
def find_package(conn, name: str, version: str) -> PackageRow | None: ...
# analysis: parse_content(text) -> PackageDoc  (raises errors.InvalidSchemaPackageError)
#           provider().registry().origin(name, version) -> object | None
# tl_schema.packages: def version_tuple(version: str) -> tuple[int, ...]
```

From `tl_cli` (read-only): `DEV_ACTOR`, `SOURCE`, `Actor`, `acting(db, actor)`, `fail(message)` and `service_errors()` in `tl_cli.derive_support`; `require_session(db)` in `tl_cli.session`. The finished `draft` command in `tl_cli/schema_pkg.py` makes the same call.
```text

```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/schema_import.py` (the stub)
- `docs/tickets/P1-I8/provided/t05a4c-test_cli_schema_import.py.txt`
- `packages/tl-cli/src/tl_cli/schema_pkg.py` (lines 144-165, the `draft` command)
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/schema_import.py` (modify: the body of `import_git`, the stub paragraph and directives, the unused imports)
- `packages/tl-cli/tests/test_cli_schema_import.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I8/P1-I8-T05a4c.md` (create: your report; commit it)

## Steps
1. Copy the provided test to `packages/tl-cli/tests/test_cli_schema_import.py`. Do not edit the copy (it is ruff-clean and pyright-clean as provided).
2. Run it once; all ten cases fail against the stub.
3. Write the body of `import_git` by its STEPS and docstring. Remove the STUB paragraph, the two directive lines, every STEPS comment and the `raise NotImplementedError` line, and the imports the finished file does not use. Run `uv run ruff format` before `just check`.
4. Run the commands under *Acceptance*.

## Acceptance
```
uv run ruff format packages/tl-cli
uv run pytest packages/tl-cli/tests/test_cli_schema_import.py packages/tl-cli/tests/test_cli_schema_package.py -q --adapters sqlite,postgres --basetemp=/tmp/pt-t05a4c
just check
```
Expected: ten pass on SQLite; on Postgres nine pass and the one that signs in a second account skips; the existing `test_cli_schema_package.py` passes unchanged; `just check` is clean (run it with a 600 000 ms timeout). Remove `/tmp/pt-t05a4c` after you have read the exit code.

## Tests to add
None beyond the provided file. If you think a case is missing, say so under *Open questions* in the report; do not edit the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), committed at `docs/reports/P1-I8/P1-I8-T05a4c.md`. Deviations first. Paste the last lines of each acceptance command.

## Escalation triggers
- Stop and report *Blocked* if a provided test fails and you cannot see a difference between your reading of the STEPS and the test after two attempts.
- Stop if the pasted interface and the repository disagree.
- Stop if you would have to change a provided test or any file outside *Allowed paths*, or follow a link.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
