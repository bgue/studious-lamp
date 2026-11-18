# V3-FN1 · a form submission is never the subject of another record (wave review F1, N1)
kind: piece · review: full + security re-check · branch `p2/v3-fn1-subject` · worktree `/home/user/wt/v3p/fn1` ·
base `p2/v3-forms`. Process: `docs/build-spec/process-v3.md` section 2.

## Finding (wave security review, MD)
`confidentiality._chain_sql` walks past a `forms.Submission` met on a hop: its own `answer_class` and the draft rule
(`OWN_CLASS_TYPES`, `DRAFT_TYPE`) are checked only for the submission itself. So an internal submission S2 whose
subject is a privileged submission S1 (or someone's draft D) is visible to readers who may not see S1, and its row
names S1's id (`subject_id`, `?subject=<id>` confirms it). The same holds for an intake code whose context is S1.
Proof: `/tmp/claude-0/wave-probe/n1_probe.py` (SQLite, forms_world). Only a person who can read S1 can make S2.

## Ruling (orchestrator, 2026-11-18)
Refuse instead of widening the chain: no edit of `confidentiality.py`. Precedent: punch `SOURCE_REFUSED`.
1. `tl_mod_forms/handlers/common.py` `require_subject`: a subject whose record type is `forms.Submission` raises
   `RecordNotFoundError(MSG_UNKNOWN)`, the same text as a hidden or absent one, after the visibility check.
2. The intake code context check (`handlers/intake.py` ~177) does the same.
3. Every other command in the tree that writes a link column listed in `confidentiality.SUBJECT_LINKS` (and the QR
   code target) and accepts any record type there: refuse `forms.Submission` the same way, each with that module's
   own "unknown" text. Find them with a grep over `SUBJECT_LINKS` columns; list what you checked in the report.
4. Wave review F2 LO goes away with 1. F3 LO: fix the `tl_web/pages/forms.py:67` docstring (FX added the rows).
5. Tests: turn the probe into `tests/confidentiality/test_forms_submission_subject.py`, with S2, S5 and the code
   refused with the one unknown text, byte-equal to an absent id. A submission whose subject is a plain record still
   works. Check whether the demo generator or fixtures create a submission about a submission, and say so.
No schema change, no new event, no data migration: existing rows stay as they are, and the report says whether the
demo ledger has any.

## Gate
`uv sync --frozen --all-packages`; ruff and pyright on changed files; `just gate tests/confidentiality
packages/tl-modules/forms/tests` plus the touched modules' tests; `TL_DEMO_BACKENDS=sqlite just demo P2-FORMS`. A
full suite is running on lock 1, so use `.2.lock` and wait for it. Mutation: sentinel plus 2 targeted (drop the
refusal in require_subject; drop it in the intake context). Report `docs/reports/P2-FORMS/V3-FN1.md`, at most 15
lines. Prefix `V3-FN1:`.
