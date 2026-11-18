# V3-FN1: a form submission is never the subject of another record

Deviations: the permit, isolation and inspection handlers are touched too (item 3 of the ruling); `load_record`
in permits and quality `handlers/common.py` gains an `exclude` argument. No edit of `confidentiality.py`, no schema,
event or data change.

## Done
- `forms/handlers/common.py` `require_subject`: a subject of type `forms.Submission` raises
  `RecordNotFoundError(MSG_UNKNOWN)` after the visibility check. The intake code context (`handle_issue_intake_code`)
  goes through the same function, so one line covers items 1 and 2.
- Permit `for_record_id`, isolation `point_record_id`, inspection `subject_id` refuse it with the permits and
  quality "no record with that id" (`load_record(..., exclude=(SUBMISSION,))`).
- `tl_web/pages/forms.py` `_refused` docstring (F3 LO) corrected: the error table now has rows for these classes.

## Link columns checked (grep over `SUBJECT_LINKS` columns)
- Refused now: forms Submission/code context, permits Permit and Isolation, quality Inspection.
- Already refused: punch `source_id` (`SOURCE_REFUSED` holds every `SUBJECT_LINKS` type, so a submission too); QR
  target (the scan-card providers are awp, permits, quality only, none for a form, so `_issue` answers `MSG_UNKNOWN`;
  tested, no code change).
- Not open to a submission: requisitions `for_record_id` (IWP or CWP only), work order `requisition_id`, scaffold
  `for_record_id` (copied from its request), gas test `permit_id` (a permit), intake item `code_id`, scaffold
  inspection `scaffold_id`. Core constraints, correspondence and materials write columns outside `SUBJECT_LINKS`.

## Constraints (review re-check)
`constraints/handlers.py` `_raise`: after `_visible`, a subject whose type is in `confidentiality.OWN_CLASS_TYPES`
(forms.Submission; no forms import) raises `RecordNotFoundError("no record <id>")`, the absent subject's words, nothing
written. Covers `RaiseConstraint` and module raises. `grep subject_id packages/tl-core/src`: no other core writer of a
chain column (engine.py:292 only reads). Test added; mutant (check off) killed. Gate `tests/confidentiality` plus
`tl-core/tests/constraints`: 439 passed, PASS.

## Tests
`tests/confidentiality/test_forms_submission_subject.py` (3 tests, from the probe): S2 (privileged S1), S5 (a draft),
a draft save, intake code over S1 and over a draft, each byte-equal to an absent id's text and nothing written; a plain
subject still works; permit, isolation, inspection and QR target refused byte-equal to an absent id.
Mutation: sentinel (drop the check in `require_subject`, covers the intake context too) killed; 3 targeted (drop
`exclude` in inspection, isolation, permit) killed, 4/4. The intake context has no line of its own to drop.

## Gate
ruff, format and pyright clean on changed files. `just gate tests/confidentiality forms permits quality tl-web tests`:
1869 passed, 4 xfailed, PASS (`.gate/summary.txt`). Demo `TL_DEMO_BACKENDS=sqlite just demo P2-FORMS`: clauses 1-11 PASS, exit 0.

## Fixtures and ledgers
The demo generator (`dev/seed/demo_project/forms.py`) and the forms fixtures give no subject on a submission, so none
is about a submission; the demo ledger has no such row. Existing rows elsewhere are left as they are.
