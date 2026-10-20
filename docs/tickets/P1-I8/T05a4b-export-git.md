# P1-I8-T05a4b — `tl schema export-git`: the published packages as files for a git repository

Status: ready
Tier: haiku
Review: full
Labels: cli, schema-registry, files
Depends on: P1-I8-S2 and P1-I8-S5 on `p1/i8`; no other ticket
Branch: `p1/i8-t05a4b-export-git`

## Goal
The company keeps its schema in git as well as in the ledger. `packages/tl-cli/src/tl_cli/schema_export.py` holds the command `tl schema export-git DIR [--package NAME]` (already registered in `tl schema`): it writes one file `<package>@<version>.yaml` for every version in force, with the text exactly as it was drafted, and nothing else. `_file_name`, `_write_atomic` and `register` are complete; `export_git` raises `NotImplementedError` today. You write its body by the STEPS comments so the one provided test file passes. This is a command that writes files on the host: read the path rules below twice.

## Brief references (pasted)
> **Brief 27.8.** `tl schema` CLI: `lint`, `diff`, `classify`, `impact`, `test`, `publish`, `adopt`, `crosswalk`, `promote`, `export-git` / `import-git`.
>
> **Increment 8 (FANOUT F9, security review).** An export must not carry impact names or record text. A package is schema text; the impact report of a package names mappings and rules (administrators only) and is never exported. Only the administrator exports, because the command writes files where the process runs.

### Specification
- States in force are `Published` and `Deprecated` (`tl_mod_schemareg.names.IN_FORCE`); a draft, a version in review or a retired one is not exported.
- `registry.list_packages(conn, state=..., package=..., limit=...)` takes one state at a time and returns rows with `.package`, `.version` and `.content` (the drafted text, kept as it was).
- Path rules (already in `_file_name` and `_write_atomic`; do not weaken them): the file name is built from the package name and version after a pattern check; a symbolic link is never written through; a file with other text is never overwritten; all targets are checked before the first write.
- `typer.Argument(..., file_okay=False)` already makes a file in place of the directory an error (exit code 2).

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
`packages/tl-cli/src/tl_cli/schema_export.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401
# pyright: reportUnusedImport=false
"""`tl schema export-git DIR [--package NAME]`: the published packages as files (P1-I8-T05a4b).

STUB: this file is the interface P1-I8-T05a4b implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it. `_file_name`, `_write_atomic` and
`register` are complete.

The files are what a git repository of the company's schema holds: one `<package>@<version>.yaml`
per version in force (Published or Deprecated), the text exactly as it was drafted. Nothing else
is written: no report, no impact, no record text (the impact report names mappings and rules,
which are for administrators; FANOUT F9). It writes files on the host, so it is the
administrator's. Importing is `tl schema import-git` (P1-I8-T05a4c).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_schemareg import registry
from tl_mod_schemareg.names import IN_FORCE
from tl_schema.packages import version_tuple

from tl_cli.derive_support import fail, service_errors
from tl_cli.session import require_admin

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


def _file_name(row: registry.PackageRow) -> str:
    """The file name of a version; a name that could leave the directory is an error."""
    if _NAME.fullmatch(row.package) is None or _VERSION.fullmatch(row.version) is None:
        fail(f"{row.package}@{row.version} cannot be a file name")
    return f"{row.package}@{row.version}.yaml"


def _write_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` through a temporary file in the same directory."""
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def export_git(
    ctx: typer.Context,
    directory: Annotated[
        Path, typer.Argument(help="The directory to write to; made when missing.", file_okay=False)
    ],
    package: Annotated[
        str | None, typer.Option("--package", help="Only the versions of this package.")
    ] = None,
) -> None:
    """Write every published version as `<package>@<version>.yaml` into DIR (admin).

    Lines: `wrote <file>` or `unchanged <file>` (the file already holds the same text), in the
    order package name then version, then `exported <w> written, <u> unchanged to <DIR>`. With
    nothing to export: `nothing to export` (and DIR is not made). A file that exists with other
    text, or is a symbolic link, is `error: ...` (exit 1) and nothing is written.
    """
    # STEPS
    # 1. db: DbTarget = ctx.obj; require_admin(db).
    # 2. In `with service_errors(), open_uow(db, readonly=True) as uow:` collect
    #    `registry.list_packages(uow.conn(), state=state, package=package,
    #    limit=registry.MAX_PAGE)` for each `state` in IN_FORCE. Sort by `(row.package,
    #    version_tuple(row.version))`.
    # 3. No rows: print `nothing to export` and return.
    # 4. `directory.mkdir(parents=True, exist_ok=True)`. For each row make the target
    #    `directory / _file_name(row)`. Before writing anything check all of them: a symbolic
    #    link (`is_symlink()`) or a file whose text differs from `row.content` is
    #    `fail(f"{target.name} exists with other text")` (say `is a link` for a link).
    # 5. Then for each row: write with `_write_atomic(target, row.content)` and print
    #    `wrote <name>`, or print `unchanged <name>` when the file already holds the text.
    # 6. Print the last line from the docstring.
    raise NotImplementedError("STEPS: see the comments")


def register(app: typer.Typer) -> None:
    """Add the command to `tl schema`."""
    app.command("export-git")(export_git)
```

From `tl_mod_schemareg.registry` (read-only; abridged):
```python
MAX_PAGE = 1000

@dataclass(frozen=True)
class PackageRow:
    package: str      # "co.acme.engineering"
    version: str      # "3.3.0"
    content: str      # the package YAML as drafted
    state: str        # Draft, InReview, Published, ...
    # (more fields)

def list_packages(conn, *, scope=None, state=None, package=None, limit=200, offset=0) -> list[PackageRow]: ...
# from tl_schema.packages: def version_tuple(version: str) -> tuple[int, ...]
```

From `tl_cli` (read-only): `fail(message)` (prints `error: ...` on stderr, exit 1) and `service_errors()` in `tl_cli.derive_support`; `require_admin(db)` in `tl_cli.session`.
```text

```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/schema_export.py` (the stub)
- `docs/tickets/P1-I8/provided/t05a4b-test_cli_schema_export.py.txt`
- `packages/tl-cli/src/tl_cli/schema_gov.py` (finished commands of the same group: the style to follow)
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/schema_export.py` (modify: the body of `export_git`, the stub paragraph and directives, the unused imports)
- `packages/tl-cli/tests/test_cli_schema_export.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I8/P1-I8-T05a4b.md` (create: your report; commit it)

## Steps
1. Copy the provided test to `packages/tl-cli/tests/test_cli_schema_export.py`. Do not edit the copy (it is ruff-clean and pyright-clean as provided).
2. Run it once; all six cases fail against the stub.
3. Write the body of `export_git` by its STEPS and docstring. Remove the STUB paragraph, the two directive lines, every STEPS comment and the `raise NotImplementedError` line, and the imports the finished file does not use.
4. Run the commands under *Acceptance*.

## Acceptance
```
uv run ruff format packages/tl-cli
uv run pytest packages/tl-cli/tests/test_cli_schema_export.py -q --adapters sqlite,postgres --basetemp=/tmp/pt-t05a4b
just check
```
Expected: six pass on SQLite; on Postgres five pass and the one that signs in a second account skips; `just check` is clean (run it with a 600 000 ms timeout). Remove `/tmp/pt-t05a4b` after you have read the exit code.

## Tests to add
None beyond the provided file. If you think a case is missing, say so under *Open questions* in the report; do not edit the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), committed at `docs/reports/P1-I8/P1-I8-T05a4b.md`. Deviations first. Paste the last lines of each acceptance command.

## Escalation triggers
- Stop and report *Blocked* if a provided test fails and you cannot see a difference between your reading of the STEPS and the test after two attempts.
- Stop if the pasted interface and the repository disagree.
- Stop if you would have to change a provided test or any file outside *Allowed paths*, or weaken a path rule.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
