# V3-P0c · the last three module reports: requisitions, activities, QR codes
kind: piece · review: full + security (QR adds a new read) · branch `p2/v3-p0c-reports` · worktree
`/home/user/wt/v3p/p0c` · base `p2/v3-forms` · Process: `docs/build-spec/process-v3.md` section 2, rule 6.

## Goal
The three reports V3-P0b left out (see `docs/reports/P2-FORMS/V3-P0b.md`), same pattern and same tests as P0b
(`docs/tickets/P2-FORMS/v3/P0b-registrations.md`, `tests/reports/test_demo_reports.py`): pinned header, count equals
the list read for the same viewer, JSONL equals CSV, page boundaries at sizes 1 and 2, refusal without the view word
(no header), and the restricted-record byte test (low bytes = unedited ledger's low bytes minus that line; present
for the controller). Columns never include a record id; the key or number names the row.

| report | hook file | read | rulings |
|---|---|---|---|
| `requisitions` | `tl_mod_requisitions.report_rows` | `views.requisition_list` (clamped: add a keyword-only `offset`, default 0, as P0b did) | one row per requisition of every kind (general, labor, material, scaffold request); a `kind` column; columns from `RequisitionRow`; view word `requisitions.view` |
| `activities` | `tl_mod_schedule.report_rows` | `registry` activity rows of each schedule's **current snapshot** (`current_snapshot_id`); a schedule with none adds no rows | columns: schedule code, snapshot number, activity id, name, state, planned and actual start/finish, total float (hours, as stored); check the view word on the schedule list read and use it if one exists |
| `qr-codes` | `tl_mod_qr.report_rows` | new select over the project's codes with `confidentiality.not_hidden` on the code's subject (`qr.ScanCode` is in `SUBJECT_LINKS`), ordered by issue time then label | columns: label_text, size, state, subject_key, issued_by, issued_at, expires_on, revoked_at; **never** a code value, token, hash or salt, and no column a scan URL can be rebuilt from |

## Rules
No edit of `confidentiality.py`, no schema change, no new event. Existing callers of the views unchanged. The QR
select is the only new SQL; keep it to one statement with `not_hidden`, and add a perf-budget line for it in
`tests/perf/test_budget.py` (under 1 s as treyes and mokafor). Board and `STATE.md` are the orchestrator's.

## Gate
`just gate-changed` (if it stops at the deferred `test_check_wheels` pin, run its later steps by hand and say so);
`just gate tests/reports tests/perf` plus the touched module tests. Never run `just check` while another gate is
running (16 GB box). Report `docs/reports/P2-FORMS/V3-P0c.md`, at most 15 lines. Subject prefix `V3-P0c:`.
