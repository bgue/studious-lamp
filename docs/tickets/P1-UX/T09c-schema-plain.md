# P1-UX-T09c — Schema workbench and review in plain language

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: T00 (merged)
Branch: `p1/ux-t09c-schema-plain`

## Goal
The schema workbench (Ctrl+O) and its review screen show a package as "Engineering, version 3.2.0", never as
`co.acme.engineering@3.2.0`, and hide impact digests, in plain mode. Technical mode shows today's text. Split out of the
plan's T09b (checklist: too many files for one Haiku ticket). Enter-to-record on package rows comes in a later ticket after S2.

## Brief references (pasted)
> SCOPE clause 2: hidden by default: schema package names and versions, hashes and digests. Clause 3: technical mode shows them.
> D13 (supervisor, reversible): in the workbench the Version column stays (it tells the rows of one package apart) and the
> Property/Lint/Diff tabs stay as they are (they show package source, which is the subject of the tool). Hidden in plain
> mode: the joined `name@version` form everywhere it is printed, and the `Digest` line. Nothing else changes.
> Mode: `mode_of(self.app).technical`. Screens that depend on it define `refresh_for_display_mode(self) -> None`.

## Interfaces (verbatim from repo)
```python
# tl_tui/display.py (merged)
def humanize(name: str) -> str        # "co.acme.engineering" -> "Engineering"; "ControlValve" -> "Control valve"
def actor_label(labels: Labels, actor: str) -> str
def mode_of(widget_or_app: object) -> DisplayMode
# tl_tui/schema_text.py (today)
COLUMNS = ("Package", "Version", "State", "Class", "Scope", "Drafted by")
def tree_cells(rows: Sequence[PackageSummary]) -> list[tuple[str, ...]]:   # name shown on the first row of a run, "" on the others
def header_lines(detail: PackageDetail) -> list[str]:
    return [f"{detail.key}  {detail.state}", ..., f"Drafted by {detail.drafted_by}  Submitted by {detail.submitted_by or '-'}  Approved by ...", ...]
# tl_tui/schema_review_text.py (today)
def title_line(detail: PackageDetail) -> str:        # f"{detail.key}  {detail.state}  class {detail.worst_class or '-'}"
def classification_lines(detail) -> list[str]:       # head[1] = f"Base {report.base or '-'}"   (report.base is name@version)
def impact_lines(report: ImpactReport | None) -> list[str]:   # [f"Scope {report.scope}", f"Digest {report.digest}", f"Counts {counts}"] + entries
def sample_lines(view: SampleTestView | None) -> list[str]:   # f"Tested {view.package}  scope ..."
# PackageSummary fields: id key scope package version kind project title state worst_class analysed drafted_by submitted_by approved_by published_at changelog
# widgets/schema_screen.py: _describe() calls header_lines(detail); on error header.update(row.key); table built from tree_cells(self.rows)
# widgets/schema_review_screen.py:135: update(title_line(detail))
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/schema_text.py`, `schema_review_text.py`
- `packages/tl-tui/src/tl_tui/widgets/schema_screen.py`, `schema_review_screen.py`
- `packages/tl-tui/tests/test_schema_text.py`, `test_schema_review_text.py` (marked "Provided; do not edit" for the earlier ticket; this ticket changes the behaviour they pin, so it updates them)
may explore: `packages/tl-tui/tests/test_schema_screen.py`, `test_schema_review_screen.py`, `fakes_schemareg.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/schema_text.py`, `schema_review_text.py`, `widgets/schema_screen.py`, `widgets/schema_review_screen.py`
- `packages/tl-tui/tests/test_schema_text.py`, `test_schema_review_text.py`, `test_schema_screen.py`, `test_schema_review_screen.py` (update pinned expectations)
- `packages/tl-tui/tests/test_schema_plain.py` (create)
- `docs/reports/P1-UX/T09c.md` (create)

## Steps
1. In `schema_text.py` add `plain_ref(ref: str) -> str`: `"co.acme.engineering@3.2.0"` -> `"Engineering, version 3.2.0"`; no `@` -> `humanize(ref)`;
   split on the last `@`. Add keyword-only `technical: bool = False` to `tree_cells`, `header_lines`, and (review text) `title_line`,
   `classification_lines`, `impact_lines`, `sample_lines`.
2. Plain: `tree_cells` package cell = `row.title or humanize(row.package)`; `header_lines`/`title_line` first part = `plain_ref(detail.key)`;
   `Base` and `Tested` values go through `plain_ref`; `impact_lines` omits the `Digest` line; `Drafted/Submitted/Approved by` through `actor_label(Labels(), x)`.
   Technical: output byte-identical to today.
3. Screens pass `technical=mode_of(self.app).technical`; the error path `header.update(row.key)` uses `plain_ref` unless technical.
4. `SchemaWorkbenchScreen` and the review screen define `refresh_for_display_mode(self)` that re-renders (rebuild the table with the cursor kept; redo the header/title/tab text) using existing methods.
5. Update the pinned expectations in the four existing test files to the plain default; keep one technical-mode assertion per old pinned line.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_schema_text.py packages/tl-tui/tests/test_schema_review_text.py packages/tl-tui/tests/test_schema_screen.py packages/tl-tui/tests/test_schema_review_screen.py packages/tl-tui/tests/test_schema_plain.py -q
```
Expected: pass. Do not run the whole suite. If a snapshot test fails, regenerate only that snapshot with `--snapshot-update` and name it in the report.

## Tests to add
`packages/tl-tui/tests/test_schema_plain.py`:
- `test_plain_ref_forms` (`name@1.2.3`, `co.acme.engineering@3.2.0`, no-`@`, empty).
- `test_plain_header_and_title_have_no_joined_package_ref` (`find_technical(text) == []` over header, title, base and tested lines, plain; technical shows `co.acme.engineering@3.2.0`).
- `test_digest_line_only_in_technical_mode`.
- `test_screen_toggle_refresh` (pilot: open the workbench on the fake client, set `display_mode.technical = True`, call `refresh_for_display_mode()`, the header shows the joined key; off again hides it).

## Report requirements
Standard report. List existing assertions changed (one line each) and snapshots regenerated, if any.

## Escalation triggers
- A plain-mode line still carries `name@x.y.z`, a sha256 or a ULID on these screens that the steps do not name: list it, do not widen the ticket.
- `SampleTestView.package` is not a `name@version` string in the fake or the real client: use `humanize` on it and say so.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
