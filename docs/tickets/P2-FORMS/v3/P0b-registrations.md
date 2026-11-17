# V3-P0b · register the remaining module reports (`tl report`)
kind: piece · review: full · branch `p2/v3-p0b-reports` · base: V3-P0 merged
Process: `docs/build-spec/process-v3.md` section 2.

## Goal
Add one `Report` row per module below (the `reports` hook from V3-P0). Each is about 20 lines: a rows function that
pages through the existing list view as the viewer, the `Report(name, title, columns, rows)` row, and a pinned-header
test line in `tests/reports/test_demo_reports.py` (`HEADERS`). No new SQL unless noted. Columns never include a record
id; the record key (or number) names the row. A module hook ref names its own `tl_mod_<name>.report_rows:REPORTS`
(or `tl_cli.report_<x>:REPORTS` when it needs another module's views, as awp and materials do).
Each report also needs the P0 checks: count equals the list view for the same viewer, JSONL equals CSV, and a
restricted record present for a controller and absent (not counted, not marked) for a low viewer.

## Modules, list views and proposed columns
| report name | module / hook file | list view (page through it) | proposed columns |
|---|---|---|---|
| `tags` | engineering | `registry.list_tags` (limit only; read in one call as `tl tag report` does) | tag, class, state, description, system, area, ended_on |
| `cwps` | awp `report_rows` | `views.cwp_list` (`CwpRow`) | number, title, state, discipline, cwa, planned_start, planned_finish, budget_hours, allocated |
| `iwps` | awp | `iwp_views.iwp_list` (`IwpRow`) | number, title, state, discipline, planned_start, planned_finish, foreman, estimated_hours, cwp_number, scope_count |
| `constraints` | awp | `iwp_reports.constraint_log` rows exist as `awp-constraint-log`; add the full register from the constraint view if more columns are wanted | key, state, category, severity, owner, phase, due, age_days, aging |
| `activities` | schedule | `registry.activity_page` of the latest snapshot | activity id, name, state, planned and actual start and finish, float (check the registry row for the exact names) |
| `requisitions` | requisitions | `views.requisition_list` | key, kind, state, subject, requested_on, needed_on, requester (read `RequisitionRow`) |
| `work-orders` | requisitions | `views.work_order_list` | key, state, subject, dates, assignee (read the row) |
| `punch` | quality | `views.punch_list` (`PunchRow`) | key, subject, state, category, area, system, due_on, assignee, raised_by, source_key |
| `inspections` | quality | `insp_views.inspection_list` (`InspectionRow`) | key, title, subject_key, for_key, state, point, area, planned_on, scheduled_for, inspector, result, done_on, punch_count |
| `permits` | permits | `views.permit_list` (`PermitRow`) | key, subject, permit_type, state, area, holder, issued_at, valid_until, revalidation_count, closed_by, for_key |
| `isolations` | permits | `iso_views.isolation_list` (`IsolationRow`) | key, point_text, energy, method, lock_number, tag_number, state, applied_by, applied_at, verified_by, verified_at, depends |
| `qr-codes` | qr | codes of the project; `views.codes_for_record` is per record, so this one needs a minimal select with `confidentiality.not_hidden` (the one SQL addition) | label_text, size, state, issued_by, issued_at, expires_on, revoked_at |

Also worth one row each if the owner wants them: documents transmittals (`tl_mod_documents.reports.transmittal_log`),
form intake codes and items (`tl_mod_forms.intake_views.code_list`, `item_list`; the intake item body is never a column),
checklists (`insp_views.checklist_list`).

## Notes for the builder
- Several views take `limit` only or clamp it; of the views V3-P0 used only `scaffold_list` clamps (500), and
  `correspondence.views.register` pages by re-reading from the top (so V3-P0 reads it once with a large bound).
  Give the others an `offset` the way V3-P0 did for `scaffold_list`
  (a default-0 keyword, `OFFSET :offset`), never a read of "everything" through a bound that the clamp cuts.
- Datetime columns render ISO through `tl_core.report_out.plain`; leave them as `datetime`.
- Check the module's view word where its list read has one (for example `scaffold.view`, through the same
  `require_word`, so a viewer without it gets the list read's refusal and no header). See "Follow-up: view words"
  in the V3-P0 report. A module without a view word on its list read needs nothing.

## Gate
`just check` on changed files; `just gate tests/reports tests/confidentiality packages/tl-core/tests packages/tl-cli/tests`
plus each touched module's tests. `uv run python dev/tools/export_reports.py` unchanged.
