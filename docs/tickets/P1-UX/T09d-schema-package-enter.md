# P1-UX-T09d — Schema workbench: Enter on a package row opens the record screen, package Details

Status: ready (stage)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: S2, T09c (merged)
Branch: `p1/ux-t09d-schema-package-enter`

## Goal
In the schema workbench (Ctrl+O) Enter on a package row opens the full record screen of that package version (Esc returns on the same row), and its Details tab shows labelled fields:
plain names the version in words (`Pressure vessel, version 2.1.0`), people by name, no `name@version` key and no content hash; technical adds the key, hash, scope and the envelope rows.

## Brief references (pasted)
> SCOPE clause 1: Enter on any row opens the full record view; Esc returns on the same row. Clause 2/3: plain by default, technical adds the details. D15: `PackageSummary.id` is a record id; accounts, tokens and settings are not records (no Enter). D22: open on `DataTable.RowSelected`. D14: the screen already has `refresh_for_display_mode` (T09c).
> D13/D19: the workbench Version column and Property/Lint/Diff tabs stay as they are (T09c).

## Interfaces (verbatim from repo)
```python
# tl_tui/widgets/schema_screen.py (today): SchemaScreen(client, scope, actor, *, tab=0); self.rows: list[PackageSummary]; table "#schema-table" (row key = row.id); self.scope, self.actor, self.client;
#   on_data_table_row_highlighted(event) -> self._describe(); action_review pushes SchemaReviewScreen.
# PackageSummary (tl_mod_schemareg.views): id key scope package version kind project title state worst_class analysed drafted_by; PackageDetail adds content content_sha256 submitted_by approved_by published_at changelog drafted_by
# client.get_schema_package(ref) -> PackageDetail   (ref is the id or the `package@version` key; the fake accepts both)
# tl_tui/widgets/record_screen.py: open_record(screen, client, scope, project, actor, record_id) -> None;  project = project_of_scope(scope) or ""   (from tl_core.settings.layers)
# tl_tui/schema_text.py: plain_ref(key) -> "Pressure vessel, version 2.1.0" (humanize(name), version); header_lines(detail, *, technical)
# tl_tui/details/__init__.py: DetailRow(label, value, technical=False); @register("schemareg.SchemaPackage") renderer(client, project, record, labels) -> list[DetailRow]; model: details/schedule.py
# details/generic.py technical_rows(record); tl_tui/display.py: Labels, actor_label, type_label, humanize; tl_tui/text.py: EMPTY, timestamp
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/schema_screen.py`, `details/schedule.py` (model), `schema_text.py` (lines 1-30 and the `plain_ref` / `header_lines` functions)
- `packages/tl-tui/tests/test_schema_screen.py`, `test_schema_plain.py`, `test_record_screen.py` (Enter/Esc pattern, lines 1-120)
- `packages/tl-tui/tests/fakes_schemareg.py` (read-only: `seed_schema_package(detail)`, `add_stored_record(id, key, type, title)` is on `FakeClient`)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/schema_screen.py`
- `packages/tl-tui/src/tl_tui/details/schemareg.py` (create)
- `packages/tl-tui/tests/test_schema_screen.py`, `test_schema_plain.py` (update pinned expectations only)
- `packages/tl-tui/tests/test_schema_enter.py` (create)
- `docs/reports/P1-UX/T09d.md` (create)

## Steps
1. `SchemaScreen.on_data_table_row_selected(self, event)`: `event.stop()`; guard the index against `self.rows`; `open_record(self, self.client, self.scope, project_of_scope(self.scope) or "", self.actor, self.rows[event.cursor_row].id)`.
2. `details/schemareg.py`: `@register("schemareg.SchemaPackage")` reads `client.get_schema_package(str(record["id"]))`. Rows: Type (`type_label`), Package (`plain_ref(detail.key)`), Title (if set), Kind (`humanize`), State (`humanize`), Project (if set), Worst change (`worst_class` or EMPTY),
   `Drafted by`, `Submitted by` (if set), `Approved by` (if set) via `actor_label`, Published (`timestamp`, if set), Changelog (if set), Created, Updated, then technical-only rows `Key` (`detail.key`), `Content hash` (`content_sha256`), then `technical_rows(record)`.
3. Update pinned expectations only if Enter now changes one (none expected).

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_schema_screen.py packages/tl-tui/tests/test_schema_plain.py packages/tl-tui/tests/test_schema_enter.py packages/tl-tui/tests/test_schema_text.py packages/tl-tui/tests/test_schema_review_screen.py packages/tl-tui/tests/test_details_registry.py packages/tl-tui/tests/test_record_screen.py packages/tl-tui/tests/test_fakes_schemareg.py packages/tl-tui/tests/test_technical_toggle.py
```
Gate paths: all exist at dispatch except `test_schema_enter.py` (new, this ticket creates it). Expected `gate: PASS`. No snapshot test shows these. Do not run the whole suite.

## Tests to add
`packages/tl-tui/tests/test_schema_enter.py` (TlApp on `FakeClient`; seed packages as `test_schema_screen.py` does; open with `ctrl+o`; `client.add_stored_record(<package id>, <key>, "schemareg.SchemaPackage", <title>)`):
- `test_enter_on_a_package_row_opens_the_record_and_escape_returns_to_the_same_row` (second row selected).
- `test_a_package_the_viewer_cannot_read_opens_as_no_record` (no stored record; no id in the text).
- `test_package_details_plain_have_no_key_or_hash_and_technical_adds_them` (`details_for`; `find_technical(text) == []` in plain).
- `test_enter_does_not_steal_the_review_key` (press `v`: still opens the review).

## Report requirements
Standard report.

## Escalation triggers
- The record id of a package row is not a stored record in the embedded client (record screen shows "No record" for a real package): stop and report.
- `get_schema_package` rejects a record id: stop and report.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
