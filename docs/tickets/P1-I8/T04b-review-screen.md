# P1-I8-T04b — Schema review screen: classification, impact, test on a sample, submit, approve and publish

Status: ready
Tier: haiku
Review: full
Labels: tui, schema-registry
Depends on: P1-I8-S5 and P1-I8-T03 on `p1/i8` (client methods, fakes, the impact report); T04a opens this screen with `v` but is not needed (the test mounts this screen itself)
Branch: `p1/i8-t04b-review`

## Goal
A steward who has a package version highlighted in the workbench presses `v` and reviews it: what kind of change it is, what it touches (the stored impact report, or the impact of pinning it in the project of the current scope), a test on a sample of records, and the steps of the review (analyse, submit, approve, send back with a reason, publish after typing the word). `packages/tl-tui/src/tl_tui/schema_review_text.py` (pure text) and `packages/tl-tui/src/tl_tui/widgets/schema_review_screen.py` (the modal `SchemaReviewScreen(client, scope, actor, ref)`) exist as stubs: the layout, the key bindings and the hints are in the tree. You write the bodies marked `STEPS` so the two provided test files pass. Each step is one `client.schemareg_command(name, command)` call as the signed-in person; the module decides what is allowed.

## Brief references (pasted)
> **Brief 27.4.** A schema package moves Draft, analysed, in review, approved, published; the classification report and the impact report are made at analysis; adoption of a constraining or renaming version needs the project's review of its project-specific impact report.
>
> **Increment 8 decisions (FANOUT D2, D4).** Drafting, revising, analysing and submitting are any signed-in person's (bound to the author); sending back, approving and publishing are the administrator's, and the person who submitted cannot approve. `breaking` and `forbidden` changes cannot be submitted. Publishing cannot be undone, so the screen asks for the word `publish`. The screen shows the module's refusal and changes nothing.

### Specification
- The commands are `tl_mod_schemareg.handlers.packages.AnalyseSchemaPackage`, `SubmitSchemaPackage`, `ApproveSchemaPackage`, `RequestSchemaChanges(reason=...)` and `PublishSchemaPackage`; each takes `actor`, `source`, `scope` and `package_id`. Use `actor=self.actor`, `source="tui"`, `scope="company"`. The name passed to `schemareg_command` is the class name.
- `PromptScreen(title, label)` (`tl_tui.widgets.prompt`) is a one-line modal that dismisses with the typed text or None; `self.app.push_screen(screen, callback=fn)` calls `fn(answer)`.
- `project_of_scope("project:P123")` is `"P123"`, `"company"` gives None (`tl_core.settings.layers`).
- The tests push the screen themselves and read the rendered text. Do not change a widget id or a key.

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
From `tl_mod_schemareg` (read-only; abridged):
```python
class PackageDetail(PackageSummary):      # views; summary fields: id, key, package, version, state, worst_class, ...
    classification: ClassificationReport | None
    impact: ImpactReport | None
class SampleTestView(BaseModel):
    package: str; scope: str; sample: int; checked: int
    newly_nonconformant: int; newly_warning: int; fixed: int
    examples: list[SampleExample]       # key, path, rule, message
class ImpactReport(BaseModel):          # impact_types
    scope: str; entries: tuple[ImpactEntry, ...]; counts: dict[str, int]; truncated: bool
    digest: str                         # a property
class ImpactEntry(BaseModel):
    section: str; target: str; change: str; count: int | None; detail: str
# tl_schema.classify.ClassificationReport: base: str | None, changes: tuple[Change, ...],
#   worst: str, auto_adoptable: bool, blocks_submit: bool      Change: cls, path, detail
# ClientInterface: get_schema_package(ref), sample_test_schema_package(ref, sample=1000),
#   get_project_schema_impact(project, package, version) -> ImpactReport, schemareg_command(name, cmd)
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/schema_review_text.py` and `packages/tl-tui/src/tl_tui/widgets/schema_review_screen.py` (the stubs)
- `docs/tickets/P1-I8/provided/t04b-test_schema_review_text.py.txt` and `docs/tickets/P1-I8/provided/t04b-test_schema_review_screen.py.txt`
- `packages/tl-tui/src/tl_tui/widgets/integration_screen.py` (a finished screen of the same shape: commands, a refusal in the status line)
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/schema_review_text.py` (modify: the function bodies, the stub paragraph and directives, the unused imports)
- `packages/tl-tui/src/tl_tui/widgets/schema_review_screen.py` (modify: the methods marked STEPS, the stub paragraph and directives, the unused imports)
- `packages/tl-tui/tests/test_schema_review_text.py` and `packages/tl-tui/tests/test_schema_review_screen.py` (create: byte-for-byte copies of the provided files)
- `docs/reports/P1-I8/P1-I8-T04b.md` (create: your report; commit it)

## Steps
1. Copy the two provided tests into `packages/tl-tui/tests/`. Do not edit the copies (they are ruff-clean and pyright-clean as provided).
2. Run them once; the cases fail against the stubs.
3. Write `schema_review_text.py` first (pure), then the screen methods by their STEPS. Remove the STUB paragraphs, the directive lines, every STEPS comment, every `raise NotImplementedError` and the imports the finished files do not use. Run `uv run ruff format` before `just check`.
4. Run the commands under *Acceptance*.

## Acceptance
```
uv run ruff format packages/tl-tui
uv run pytest packages/tl-tui/tests/test_schema_review_text.py packages/tl-tui/tests/test_schema_review_screen.py packages/tl-tui/tests/test_keymap.py -q --basetemp=/tmp/pt-t04b
just check
```
Expected: all pass (the two provided files hold 17 cases); `just check` is clean (run it with a 600 000 ms timeout). Remove `/tmp/pt-t04b` after you have read the exit code.

## Tests to add
None beyond the provided files. If you think a case is missing, say so under *Open questions* in the report; do not edit the provided files.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), committed at `docs/reports/P1-I8/P1-I8-T04b.md`. Deviations first. Paste the last lines of each acceptance command.

## Escalation triggers
- Stop and report *Blocked* if a provided test fails and you cannot see a difference between your reading of the STEPS and the test after two attempts.
- Stop if the pasted interface and the repository disagree.
- Stop if you would have to change a provided test, `app.py`, `keymap.py`, `commands.py`, `client.py`, the workbench screen or any file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
