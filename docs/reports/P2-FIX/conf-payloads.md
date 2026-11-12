# P2-FIX-CONF: payload and cursor leaks (outside review 2026-11-09)

Deviations: none outside scope. `redact_events` stays as an alias of the new `redact_for_viewer`.

## What changed
- F1: `tl_core.intent.redact_for_viewer` (beside the intent redaction) applies intent redaction and a
  per-event-type table `PAYLOAD_REFS`. `core.Constraint` is not in `SCANNED_STREAM_TYPES`.
  - `Constraint.Raised`: `target_kind`, `target_id`, `target_ref_type`, `target_ref_text` are null when
    the target is hidden from the viewer (the same keys stay, so the event reads as a no-target raise;
    `target_kind` is nulled too because the constraint read does).
  - `Constraint.Cleared`: `resolved_by` is null when that record is hidden.
- Call sites: `services/queries.record_history` now redacts itself (covers `/records/{id}/history`,
  the CWP timeline in `routes/awp.py`, the TUI timeline and embedded history, thread creator read);
  `routes/events.py` (`/events`), `api/feed.py` (SSE), `routes/records.py`, `insights/activity.py`,
  `tui/embedded.py` use the new name; `tl events tail` (cli) now redacts. The CWP timeline already
  filtered through `record_history`; it now redacts as well.
- F2: `tl_lake.sync._event_rows` redacts the intent and constraint payload of visible rows at the
  lake's reader level (`confidentiality.LOWEST`).
- F4: `record_activity` returns the smallest readable candidate seq (else none) as `next_before_seq`,
  never the batch's last candidate.
- F7: `link_trace` uses `not_hidden_each("r.id")`.

## Tests
- `tl-core/tests/constraints/test_constraint_payload_twin.py` (SQLite and Postgres): hidden target and
  hidden resolver read byte for byte as no target and no resolver; visible target kept, also beside a
  hidden one; activity page and event read carry no hidden id.
- `tl-core/tests/insights/test_activity_cursor_hidden.py`: cursor never a hidden seq.
- `tl-lake/tests/test_bronze_visible_redaction.py`: intent reads "not available", constraint payload
  has no target in bronze.

## Mutants
Sentinel (skip payload redaction) killed by 3 tests. Targeted: drop `Constraint.Cleared` rule killed;
drop `target_kind` from nulled fields killed; flip `& hidden` to `| hidden` survived, so a test for a
visible target beside a hidden one was added and kills it; drop `target_ref_text` from nulled fields
survived (equivalent: a target id and a reference text never coexist, `_validate_target`), kept as
defence. F4 mutant (return old cursor) killed.

## Gates
See the commit's gate lines in the hand-off: check, insights+constraints, gate-pg of new tests,
tl-lake, tests/confidentiality, tl-api, gate-pg tests/confidentiality.
