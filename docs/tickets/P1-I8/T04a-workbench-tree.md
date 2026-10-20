# P1-I8-T04a — Schema workbench screen: the package tree, what a version defines, lint and diff

Status: ready
Tier: haiku
Review: full
Labels: tui, schema-registry
Depends on: P1-I8-S5 on `p1/i8` (client methods and fakes); the review screen is T04b and is not needed (a stub exists)
Branch: `p1/i8-t04a-workbench`

## Goal
A schema steward opens the workbench with `Ctrl+O` and sees every package version as a tree, and for the highlighted one three tabs: what it defines (code lists, psets, properties, or an extension's changes), its lint findings and the diff against the version below. `packages/tl-tui/src/tl_tui/schema_text.py` (pure text) and `packages/tl-tui/src/tl_tui/widgets/schema_screen.py` (the modal `SchemaWorkbenchScreen`) exist as stubs: the key, the app action, the layout, the key bindings and the `v` action that opens T04b's review screen are already in the tree. You write the bodies marked `STEPS` so the two provided test files pass. The screen only reads: every call is a `ClientInterface` method, and the screen contains no schema rules.

## Brief references (pasted)
> **Brief 27.8.** *Schema workbench* (TUI, later web; sketch in 10.6): package tree, pset/property editor, enforcement and policy toggles, value lists and crosswalks, diff, lint, impact, test on sample, review and publish.
>
> **Increment 8 scope.** T04a is the read half: tree, properties, lint, diff. Impact, test on sample, review and publish are T04b. Editing a property is not in this increment (a package is drafted from a file, `tl schema package draft`). Screens call the same query contracts the API uses; no business logic in the TUI (AGENTS).

### Specification
- `Ctrl+O` is bound in `TlApp` to `action_schema`, which pushes `SchemaWorkbenchScreen(client, scope, actor)`. Keys taken in the app: F1-F12, Ctrl+P, Ctrl+R, Ctrl+E, Ctrl+G, Ctrl+O.
- `client.list_schema_packages()` returns `PackageSummary` rows, highest first; `client.get_schema_package(ref)` returns the `PackageDetail` (a summary plus `content`, `lint`, `diff`, ...). Errors are `CLIENT_ERRORS`; `describe_error(exc)` is the one-line text.
- The tests mount the screen through the app (`ctrl+o`) with `FakeClient`; they read the rendered text (`screen_text`). Do not change a widget id.

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
> **L-P0-I3-7.** A `DataTable` cell that is a plain `str` is parsed as Rich markup: wrap row text in `rich.text.Text(...)`.
>
> **L-P1-I4-15 and L-P1-I7A-10.** A Textual widget owns names such as `offset` and `_id`: never use them for an attribute or a method of a screen. Filling a `DataTable` posts `RowHighlighted` after the fill returned.
>
> **L-P1-I2b-3.** A hint line is cut at the terminal width: the provided test checks that the hint lines fit 80 columns (they do, as given).

## Interfaces (verbatim from the repo at the branch point)
From `tl_mod_schemareg.views` (read-only; abridged):
```python
class PackageSummary(BaseModel):   # frozen
    id: str; key: str; scope: str; package: str; version: str; kind: str; project: str | None
    title: str | None; state: str; worst_class: str | None
    analysed: bool          # the reports are for the content as it is now
    drafted_by: str; submitted_by: str | None; approved_by: str | None
    published_at: str | None; changelog: str | None

class LintIssueView(BaseModel):  # frozen
    severity: str; rule: str; path: str; message: str

class PackageDetail(PackageSummary):
    content: str                       # the package YAML
    classification: ClassificationReport | None   # None until analysed
    lint: list[LintIssueView]
    diff: str                          # unified diff against the base; "" for a first version
    diff_truncated: bool
```

From `tl_schema` (read-only; abridged): `registry.parse_package(text, source=...) -> PackageDoc` raises `registry.PackageError`.
```python
class PackageDoc(StrictModel):
    package: str; version: str; kind: str
    code_lists: dict[str, CodeList]    # CodeList: value_list_policy: str, values: list[CodeValue]
    psets: dict[str, PsetDef]          # PsetDef: enforcement, adoption, applies_to: list[str], properties: dict[str, PropertyDef]
    extends: list[ExtendsDef]          # ExtendsDef: ref, tighten: dict[str, TightenDef], add_values: dict[str, list[CodeValue]], custom: dict[str, PropertyDef]
# PropertyDef: range: str, required: bool, required_in_states: list[str], enforcement: str | None, value_list_policy: str | None
# CodeValue: code: str, label: str, crosswalk: str | None
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/schema_text.py` and `packages/tl-tui/src/tl_tui/widgets/schema_screen.py` (the stubs)
- `docs/tickets/P1-I8/provided/t04a-test_schema_text.py.txt` and `docs/tickets/P1-I8/provided/t04a-test_schema_screen.py.txt`
- `packages/tl-tui/src/tl_tui/widgets/integration_screen.py` (a finished screen of the same shape: table, panel, status line)
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/schema_text.py` (modify: the function bodies, the stub paragraph and directives, the unused imports)
- `packages/tl-tui/src/tl_tui/widgets/schema_screen.py` (modify: the methods marked STEPS, the stub paragraph and directives, the unused imports)
- `packages/tl-tui/tests/test_schema_text.py` and `packages/tl-tui/tests/test_schema_screen.py` (create: byte-for-byte copies of the provided files)
- `docs/reports/P1-I8/P1-I8-T04a.md` (create: your report; commit it)

## Steps
1. Copy the two provided tests into `packages/tl-tui/tests/`. Do not edit the copies (they are ruff-clean and pyright-clean as provided).
2. Run them once; the cases fail against the stubs.
3. Write `schema_text.py` first (it is pure; its test needs no terminal), then the screen methods by their STEPS. Remove the STUB paragraphs, the directive lines, every STEPS comment, every `raise NotImplementedError` and the imports the finished files do not use. Run `uv run ruff format` before `just check`.
4. Run the commands under *Acceptance*.

## Acceptance
```
uv run ruff format packages/tl-tui
uv run pytest packages/tl-tui/tests/test_schema_text.py packages/tl-tui/tests/test_schema_screen.py packages/tl-tui/tests/test_keymap.py packages/tl-tui/tests/test_palette.py -q --basetemp=/tmp/pt-t04a
just check
```
Expected: all pass (the two provided files hold 16 cases); `just check` is clean (run it with a 600 000 ms timeout). Remove `/tmp/pt-t04a` after you have read the exit code.

## Tests to add
None beyond the provided files. If you think a case is missing, say so under *Open questions* in the report; do not edit the provided files.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), committed at `docs/reports/P1-I8/P1-I8-T04a.md`. Deviations first. Paste the last lines of each acceptance command.

## Escalation triggers
- Stop and report *Blocked* if a provided test fails and you cannot see a difference between your reading of the STEPS and the test after two attempts.
- Stop if the pasted interface and the repository disagree.
- Stop if you would have to change a provided test, `app.py`, `keymap.py`, `commands.py`, `client.py` or any file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
