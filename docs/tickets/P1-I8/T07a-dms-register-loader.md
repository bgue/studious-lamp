# P1-I8-T07a — Loader `dms-register`: the document register of the incumbent DMS

Status: ready
Tier: haiku
Labels: legacy-loaders
Depends on: P1-I8-S6 on `p1/i8` (the loader framework); no other ticket
Branch: `p1/i8-t07a-dms-register-loader`

## Goal
The first loader of the legacy framework. A loader is a name, a mapping template and the kind of record it writes; the stages (open, extract, profile, plan, load, reconcile, compensate) are the framework's. `dms-register` reads the document register that the incumbent DMS exports (one row per document: number, title, type, discipline, originator, and the revision, status and date the old register shows) and registers the documents. After this ticket `tl load loaders` lists it, and `tl load open register.csv --project P123 --loader dms-register` starts a run. `loaders/dms_register.py` is a stub whose `loader()` raises `NotImplementedError`; the mapping template does not exist yet; the entry-point table of the package is empty. You write the function, create the template and add the entry point, so the one provided test file passes.

## Brief references (pasted)
> **Brief 29.6 (loading from the incumbent systems).** Land the file as it is; extract and profile it; map it to the platform's records with a mapping a person can read; run the mapping as a dry run that says what would be created; load as one batch that can be reversed; reconcile the platform against the file and keep the report.
>
> **Brief 9 M1 (document register).** A document has a number, a title, a type and a discipline; the old register's revision, status and date are kept as a note until the revisions are loaded with their files.
>
> **Increment 8 decisions (FANOUT D6, D7).** The loader reuses the mapping template of `tl doc import` (`tl_mod_documents.imports.mapping`) and its rules (`RegisterDocument`): the number must fit the document numbering pattern and the type and discipline must be usable codes. A row the project already holds is left alone. Every column of the file, mapped or not, is kept in the source layer `src.legacy-<system>.<table>`.

### Specification
- `loader()` returns a `LoaderDef` (below) with exactly the values in the STEPS; leave `sheet`, `header_row` and `confidentiality` at their defaults.
- The template `mappings/dms-register.yaml` is a copy of `dev/seed/templates/document-register-dms-export.yaml` with the first lines (the comment block and `name:`) replaced by the head below and `name: dms-register`. Nothing else in it changes: the columns, the value translations and the `ignore` list stay as they are, byte for byte, because the provided test reads them.
- The entry point is one line under the table `[project.entry-points."throughline.loaders"]` of `packages/tl-modules/legacy/pyproject.toml`: `dms-register = "tl_mod_legacy.loaders.dms_register:loader"`. After you add it, run `uv sync --all-packages` once so the installed metadata knows the entry point (the provided test reads it).
- The head of the template (replace everything before the line `description: >-`):
```yaml
# Mapping template of the loader `dms-register` (P1-I8-T07a): the document register export of the
# incumbent DMS, one row per document. Read by tl_mod_documents.imports.mapping; the loader framework
# makes the delimiter a comma because it hands the template the extracted grid as CSV text.
# The sample file `dev/seed/legacy/dms-document-register.csv` is in this form. The old register's
# revision, status and date are kept as a note in the document's description; every column of the
# file, mapped or not, is also kept in the source layer `src.legacy-dms.register`.
name: dms-register
```

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

>
> **Note.** The loaders are found by the entry-point group `throughline.loaders`; the tests that use `use_loaders` replace the found set, and only `test_it_is_installed_under_its_name` reads the installed metadata.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/legacy/src/tl_mod_legacy/loaders/dms_register.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401
# pyright: reportUnusedImport=false
"""The loader `dms-register`: the document register export of the incumbent DMS (P1-I8-T07a).

STUB: this file is the interface P1-I8-T07a implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it.
"""

from __future__ import annotations

from tl_mod_legacy.loaders import read_mapping
from tl_mod_legacy.model import LoaderDef


def loader() -> LoaderDef:
    """One row per document: number, title, type, discipline, originator and the old register's
    revision, status and date. Documents are registered ``internal``.

    The mapping template is the data file ``mappings/dms-register.yaml`` of this package.
    """
    # STEPS
    # 1. Return a LoaderDef with name "dms-register", system "dms", table "register", target
    #    "documents", description "Document register export of the incumbent DMS (CSV or XLSX).",
    #    mapping_text read_mapping("dms-register.yaml"), file_types ("csv", "xlsx"). Leave the
    #    other fields at their defaults.
    raise NotImplementedError("STEPS: see the comments")
```

`packages/tl-modules/legacy/src/tl_mod_legacy/loaders/__init__.py` (read-only):
```python
"""The loaders the module ships: a name, a mapping template and the kind of record they write.

Each loader is a function returning a :class:`tl_mod_legacy.model.LoaderDef`, named in the
``throughline.loaders`` entry-point group of ``pyproject.toml`` (the entry-point name is the
loader's name). The mapping template is a data file in ``mappings/`` next to this package, of the
kind ``tl tag import`` or ``tl doc import`` reads (the delimiter is made a comma at run time).
"""

from __future__ import annotations

from importlib.resources import files


def read_mapping(filename: str) -> str:
    """The text of the mapping template ``mappings/<filename>`` of this package."""
    return files(__package__).joinpath("mappings", filename).read_text(encoding="utf-8")
```

`tl_mod_legacy.model.LoaderDef` (read-only):
```python
@dataclass(frozen=True)
class LoaderDef:
    name: str
    system: str
    table: str
    target: TargetKind          # "tags" or "documents"
    description: str
    mapping_text: str
    file_types: tuple[str, ...] = ("csv", "xlsx")
    sheet: str | None = None
    header_row: int = 1
    confidentiality: str | None = None
```

`packages/tl-modules/legacy/pyproject.toml` (the end of the file as it is; you add one line under the second table):
```toml
[project.entry-points."throughline.modules"]
legacy = "tl_mod_legacy.module:spec"

# One line per loader: <name> = "<module>:<function>" (the function returns a LoaderDef).
[project.entry-points."throughline.loaders"]
```

## Context (read these, nothing else)
- `packages/tl-modules/legacy/src/tl_mod_legacy/loaders/dms_register.py` (the stub)
- `docs/tickets/P1-I8/provided/t07a-test_loader_dms_register.py.txt`
- `packages/tl-modules/legacy/src/tl_mod_legacy/loaders/__init__.py`
- `dev/seed/templates/document-register-dms-export.yaml` (the template you copy)
- `packages/tl-modules/legacy/pyproject.toml`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/legacy/src/tl_mod_legacy/loaders/dms_register.py` (modify: `loader()`, the stub paragraph and directives)
- `packages/tl-modules/legacy/src/tl_mod_legacy/loaders/mappings/dms-register.yaml` (create)
- `packages/tl-modules/legacy/pyproject.toml` (modify: one entry-point line)
- `packages/tl-modules/legacy/tests/test_loader_dms_register.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I8/P1-I8-T07a.md` (create: your report; commit it)

## Steps
1. Copy the provided test to `packages/tl-modules/legacy/tests/test_loader_dms_register.py`. Do not edit the copy.
2. Create the template and write `loader()` by its STEPS. Remove the STUB paragraph, the two directive lines, every STEPS comment and the `raise NotImplementedError` line.
3. Add the entry-point line to `pyproject.toml` and run `uv sync --all-packages`.
4. Run the commands under *Acceptance*.

## Acceptance
```
uv run ruff format packages/tl-modules/legacy
uv run pytest packages/tl-modules/legacy/tests -q --adapters sqlite,postgres --basetemp=/tmp/pt-t07a
just check
```
Expected: all pass on both adapters (the provided file has six cases; the module's other tests still pass); `just check` is clean (run it with a 600 000 ms timeout). Remove `/tmp/pt-t07a` after you have read the exit code.

## Tests to add
None beyond the provided file. If you think a case is missing, say so under *Open questions* in the report; do not edit the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), committed at `docs/reports/P1-I8/P1-I8-T07a.md`. Deviations first. Paste the last lines of each acceptance command. Say whether `uv sync --all-packages` was needed after the entry-point line.

## Escalation triggers
- Stop and report *Blocked* if a provided test fails and you cannot see a difference between your reading of the STEPS and the test after two attempts.
- Stop if the pasted interface and the repository disagree.
- Stop if you would have to change a provided test or any file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
