# V3-P0c report: the last three module reports (requisitions, activities, QR codes)

- What: `tl report requisitions`, `activities`, `qr-codes` through the `reports` hook (commit e8d92e68).
  `requisition_list` gains a keyword-only `offset` (default 0; each kind fetches `offset + limit`, the merged
  order is sliced), existing callers unchanged. Requisition columns `key,kind,subject,state,requester,priority,
  need_by,approved_by` (no record id, no work-order or subject id). Same view word and refusal as work orders.
- Activities (`tl_mod_schedule.report_rows`): activity rows of each schedule's `current_snapshot_id` via the
  registry page; no current snapshot adds nothing. The schedule list read takes `document.read` through `guard`
  only (no module word), so the report checks none. "Planned" dates are the activity's target dates; float is
  `total_float_hr` as stored. Columns `schedule,snapshot,activity_id,name,state,planned_*,actual_*,total_float_hr`.
- QR (`tl_mod_qr.report_rows`): one select, `not_hidden("c.target_id")`, joined to the subject record for
  `subject_key`, ordered by `issued_at, label_text, id`, paged by offset; view word `qr.view`. State is the
  views' own `_state` rule. No code, hash, id or URL piece in any column.
- Tests (`tests/reports/test_demo_reports.py`, SECTIONS now includes `schedule`): headers pinned; counts equal
  the list read (requisitions, activities); JSONL = CSV; page sizes 1 and 2 (requisitions, activities, QR);
  refusal without `requisitions.view` / `qr.view`, no header; requisition hidden through its subject (low bytes =
  unedited low bytes minus that line); QR codes of an RFI made restricted (same byte test, non-vacuous: 3 lines);
  ordering, states, no secret in output; `requisition_list` offset pages are the list.
- Perf (`tests/perf/test_budget.py::test_the_report_selects_are_under_a_second`): QR, requisition, activity
  reports under 1 s as treyes and mokafor; the generator issues no codes, so 2,000 are written into the private
  copy first. Passed (2 passed in 223 s on the full ledger).
- Deviations: QR tests write `cur_qr_scan_code` rows directly into a ledger copy (the issue path needs a card
  provider and settings); the demo generator has no QR section. `just gate-changed` waited 30 min for the heavy
  lock and was stopped; the gate below was run by hand on the second lock.
- Mutation: sentinel (drop `approved_by` column) killed; QR `not_hidden` -> `1 = 1` killed; QR `require_word`
  removed killed; offset slice `[skip:skip+take]` -> `[:take]` killed. 0 survivors.
- Gate: see the commit's `.gate/summary.txt` line in the return.
