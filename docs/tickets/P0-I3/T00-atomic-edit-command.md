# P0-I3-T00 — A single atomic edit command for a record form

Status: merged (built by the supervisor, reviewed by the orchestrator: pass)
Tier: sonnet
Labels: core, tui
Depends on: P0-I2 (workstreams A and B merged)
Branch: `p0/i3` (commit baab097; no separate branch)

## Goal
Saving a form in the TUI used to send one `UpdateRecord` and then one `SetPsetValues` per (pset, layer), so a failure after the first
command left earlier changes applied. One command, `EditRecord`, now carries the field changes and the pset batches and appends all
events in one unit of work, with one `expected_version` check and one correlation id. `tl_tui.forms.save_record_edits` makes a single
call, so a form save is all or nothing.

## Brief references
- §5.2 rules (events immutable, corrections are new events); §6.3 (`Pset.ValuesSet` records the effective schema hash); §10.2 (forms).
- Origin: P0-I2 decision B16 (acceptable for Phase 0, follow-up filed).

## Interfaces
```python
# packages/tl-core/src/tl_core/services/edit.py
class PsetEdit(BaseModel): pset: str; layer: Literal["standard", "custom", "project"]; values: dict[str, Any]
class EditRecord(Command): stream_id: str; expected_version: int; changes: dict[str, Any] = {}; pset_edits: list[PsetEdit] = []
def handle_edit_record(uow: UnitOfWork, cmd: EditRecord) -> CommandResult   # .version final, .events every event in order
# ClientInterface.edit_record(cmd: EditRecord) -> CommandResult   (embedded client: one unit of work; FakeClient: restores on failure)
```
Rules: the field changes run first (`handle_update_record`), then each pset edit in order (`handle_set_pset_values`), each chained from the
version the previous one produced. A part that changes nothing is skipped. If no part changes anything the edit raises `NoChangesError`
(also when `expected_version` is stale: an all-no-op edit reports "no changes" rather than a conflict; accepted, see D25). Any other refusal
(validation, layer, voided, stale version on a real change) is raised as that part's own error and the caller's unit of work rolls back.
The handler never commits.

## Acceptance
```
uv run pytest tests/services/test_edit_record.py -q
uv run pytest packages/tl-tui/tests/test_forms.py packages/tl-tui/tests/test_edit_form.py packages/tl-tui/tests/test_embedded_real_services.py -q
just check
just test
```

## Outcome
Built by the supervisor (command handler semantics). 12 service tests: events, versions and one correlation id; caller-supplied correlation id;
field-only and pset-only edits; skipped no-op parts; refusal of an all-no-op edit; four refused-part cases that roll back the parts before
them (head sequence, title, psets and version unchanged); stale version; voided record. TUI: `forms.save_record_edits` rewritten (the
`failed` field of `SaveOutcome` and the edit form's "saved X, failed Y" branch are gone), fake client `edit_record` with rollback, and two
real-service tests (a refused part leaves the record untouched; one save is one correlation). Learning L-P0-I3-10.
Orchestrator review: pass; a scratch test that failed partway left every table byte-identical.

## Blocked
(none)

## Decision
Minor 1 from review (all-no-op edit with a stale version raises `NoChangesError`) accepted and noted in D25.
