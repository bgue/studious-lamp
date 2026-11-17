# V3-F1s · Form sources for quality and permits (demo clause 6)
kind: piece · review: full + security · branch `p2/v3-f1s-sources` · worktree `/home/user/wt/v3p/f1s` · base
`p2/v3-forms` (F1a merged). Process: `docs/build-spec/process-v3.md` section 2. Old item S3s (README row and the
"approvers" and seam notes in `docs/tickets/P2-FORMS/README.md`) is the reference; S1 defines `FormSource`,
`FormBinding` and the entry-point group `throughline.form_sources`; S3 added the seam that runs a command inside the
caller's unit of work.

## Goal
An inspection's result, and a permit's precaution ticks, can be filled through a form: `GET /forms/for/{key}` and
`tl form` answer which template and which typed command for an inspection or permit key, and submitting the filled
form records the result through the module's own typed command (the inspection result command; the permit request or
precaution-tick command), in the same unit of work. The typed module keeps its lifecycle; forms only captures.

## Build
1. `FormSource` entry points in `quality` and `permits` (append lines only to the entry-point tables; awp lines stay).
   Each maps a record to its `FormBinding` (template from the record's checklist or precaution list) and maps answers
   to the typed command's arguments. Reuse `tl_mod_quality.insp_rules` validation; do not duplicate rules.
2. Access: the typed command's own access words decide (an inspector records a result; a permit holder ticks
   precautions); a reader without the word gets that command's refusal, not a forms one. A hidden subject answers
   `None` from the source, so `/forms/for/{key}` answers exactly like a missing key (hidden == missing).
3. Generator: one inspection and one permit in the demo project bound to a form, if the existing sections lack one
   (append to the forms section; do not move other sections' pins).
4. Tests: per source, a fill that records the typed result; refusal without the word (exact text); hidden subject ==
   missing on `/forms/for/{key}` and `tl form` (byte comparison, five readers); a failing answer set is refused before
   any event is written.
5. Demo clause 6 in `dev/demos/p2_forms_demo.py`: fill an inspection result through its form binding from the CLI, then
   read the inspection and see the result. `PASS clause 6` only after the read. Earlier clauses stay green.

## Rules
Writes in two other modules are allowed for this unit only through their form-source entry points and existing typed
commands; no change to their handlers' logic, no schema change, no new event, no edit of `confidentiality.py`. If a
typed command lacks an argument the binding needs, stop and return `4` with the question.

## Gate
`just gate-changed` (if it stops at the deferred `test_check_wheels` pin, run its later steps by hand and say so),
`just gate packages/tl-modules/quality/tests packages/tl-modules/permits/tests`, then
`TL_DEMO_BACKENDS=sqlite just demo P2-FORMS`. Report `docs/reports/P2-FORMS/V3-F1s.md`, at most 15 lines. Prefix `V3-F1s:`.
