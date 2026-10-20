# P1-I8-T07b — Loaders `instrument-index` and `equipment-list`: tag lists from workbooks

Status: ready
Tier: haiku
Labels: legacy-loaders
Depends on: P1-I8-S6 and P1-I8-T07a on `p1/i8` (the framework, and the entry-point table with its first line)
Branch: `p1/i8-t07b-tag-list-loaders`

## Goal
Two more loaders for the legacy framework, both for lists of tags that a project keeps in workbooks. `instrument-index` reads the instrument index (the same columns as the seed file `dev/seed/legacy/instrument-index.csv`) from a workbook or a CSV file. `equipment-list` reads the equipment list from a workbook whose sheet is called `Equipment List` and whose header is on row 3, below two title rows; its `TYPE` column names the tag class (pump, vessel, exchanger, compressor, motor). The mapping templates already exist in `loaders/mappings/`. `loaders/instrument_index.py` and `loaders/equipment_list.py` are stubs whose `loader()` raises `NotImplementedError`, and neither name is in the entry-point table yet. You write the two functions and add the two entry-point lines, so the one provided test file passes. After this ticket `tl load loaders` lists three loaders.

## Brief references (pasted)
> **Brief 29.6 (loading from the incumbent systems).** Land the file as it is; extract and profile it; map it to the platform's records with a mapping a person can read; run the mapping as a dry run that says what would be created; load as one batch that can be reversed; reconcile the platform against the file and keep the report.
>
> **Brief 9 M2 (tag list import).** A tag has a number, a class and a service; the class decides which property sets it holds. The import reads a list with a mapping template and refuses the rows that break the rules (blank number, unknown class, number that is not in the numbering pattern, a number that appears twice).
>
> **Increment 8 decisions (FANOUT D6, D7).** The loader reuses the mapping template of `tl tag import` (`tl_mod_engineering.imports.mapping`) and its rules. A row the project already holds is left alone. Every column of the file, mapped or not, is kept in the source layer `src.legacy-<system>.<table>`. The extractor takes two options from the loader: `sheet` (the sheet to read; the first when `None`) and `header_row` (the row that holds the column names; 1 when the file has none above it).

### Specification
- Each `loader()` returns a `LoaderDef` (see T07a for its fields) with exactly the values in its STEPS.
- The entry points are two lines under the table `[project.entry-points."throughline.loaders"]` of `packages/tl-modules/legacy/pyproject.toml`, below the line T07a added:
  `instrument-index = "tl_mod_legacy.loaders.instrument_index:loader"` and `equipment-list = "tl_mod_legacy.loaders.equipment_list:loader"`. Run `uv sync --all-packages` once after you add them.
- Do not edit the mapping templates.

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
`packages/tl-modules/legacy/src/tl_mod_legacy/loaders/instrument_index.py` (a stub you complete; the whole file):
```python
# ruff: noqa: F401
# pyright: reportUnusedImport=false
"""The loader `instrument-index`: the instrument index of the incumbent system (P1-I8-T07b).

STUB: this file is the interface P1-I8-T07b implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it.
"""

from __future__ import annotations

from tl_mod_legacy.loaders import read_mapping
from tl_mod_legacy.model import LoaderDef


def loader() -> LoaderDef:
    """One row per tag: number, service, type code and the valve data the export carries.

    The mapping template is the data file ``mappings/instrument-index.yaml`` of this package.
    """
    # STEPS
    # 1. Return a LoaderDef with name "instrument-index", system "instr", table "index", target
    #    "tags", description "Instrument index of the incumbent system (workbook or CSV).",
    #    mapping_text read_mapping("instrument-index.yaml"), file_types ("xlsx", "csv"). Leave
    #    sheet, header_row and confidentiality at their defaults (the first sheet, header on row 1).
    raise NotImplementedError("STEPS: see the comments")
```

`packages/tl-modules/legacy/src/tl_mod_legacy/loaders/equipment_list.py` (a stub you complete; the whole file):
```python
# ruff: noqa: F401
# pyright: reportUnusedImport=false
"""The loader `equipment-list`: the equipment list of the incumbent system (P1-I8-T07b).

STUB: this file is the interface P1-I8-T07b implements. Remove this paragraph, the two directive
lines above and every STEPS comment when you implement it.
"""

from __future__ import annotations

from tl_mod_legacy.loaders import read_mapping
from tl_mod_legacy.model import LoaderDef


def loader() -> LoaderDef:
    """One row per equipment tag: number, description and the type that names the tag class.

    The workbook has the sheet ``Equipment List`` and two title rows above the header, so the
    header is on row 3. The mapping template is ``mappings/equipment-list.yaml``.
    """
    # STEPS
    # 1. Return a LoaderDef with name "equipment-list", system "equip", table "list", target
    #    "tags", description "Equipment list of the incumbent system (workbook).", mapping_text
    #    read_mapping("equipment-list.yaml"), file_types ("xlsx",), sheet "Equipment List",
    #    header_row 3. Leave confidentiality at its default.
    raise NotImplementedError("STEPS: see the comments")
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
    sheet: str | None = None    # the sheet the extractor reads; the first sheet when None
    header_row: int = 1         # the row with the column names
    confidentiality: str | None = None
```

## Context (read these, nothing else)
- `packages/tl-modules/legacy/src/tl_mod_legacy/loaders/instrument_index.py` and `equipment_list.py` (the stubs)
- `docs/tickets/P1-I8/provided/t07b-test_loaders_tag_lists.py.txt`
- `packages/tl-modules/legacy/src/tl_mod_legacy/loaders/dms_register.py` (the finished loader of T07a, as an example)
- `packages/tl-modules/legacy/src/tl_mod_legacy/loaders/mappings/equipment-list.yaml`
- `packages/tl-modules/legacy/pyproject.toml`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/legacy/src/tl_mod_legacy/loaders/instrument_index.py` (modify: `loader()`, the stub paragraph and directives)
- `packages/tl-modules/legacy/src/tl_mod_legacy/loaders/equipment_list.py` (modify: the same)
- `packages/tl-modules/legacy/pyproject.toml` (modify: two entry-point lines)
- `packages/tl-modules/legacy/tests/test_loaders_tag_lists.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I8/P1-I8-T07b.md` (create: your report; commit it)

## Steps
1. Copy the provided test to `packages/tl-modules/legacy/tests/test_loaders_tag_lists.py`. Do not edit the copy.
2. Write the two `loader()` functions by their STEPS. Remove the STUB paragraphs, the directive lines, every STEPS comment and the `raise NotImplementedError` lines.
3. Add the two entry-point lines to `pyproject.toml` and run `uv sync --all-packages`.
4. Run the commands under *Acceptance*.

## Acceptance
```
uv run ruff format packages/tl-modules/legacy
uv run pytest packages/tl-modules/legacy/tests -q --adapters sqlite,postgres --basetemp=/tmp/pt-t07b
just check
```
Expected: all pass on both adapters (the provided file has eight cases; the module's other tests still pass); `just check` is clean (run it with a 600 000 ms timeout). Remove `/tmp/pt-t07b` after you have read the exit code.

## Tests to add
None beyond the provided file. If you think a case is missing, say so under *Open questions* in the report; do not edit the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), committed at `docs/reports/P1-I8/P1-I8-T07b.md`. Deviations first. Paste the last lines of each acceptance command.

## Escalation triggers
- Stop and report *Blocked* if a provided test fails and you cannot see a difference between your reading of the STEPS and the test after two attempts.
- Stop if the pasted interface and the repository disagree.
- Stop if you would have to change a provided test or any file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
