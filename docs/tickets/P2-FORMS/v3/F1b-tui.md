# V3-F1b · Forms in the terminal app: forms log and runner screen (demo clause 11)
kind: piece · review: full · branch `p2/v3-f1b-tui` · worktree `/home/user/wt/v3p/f1b` · base `p2/v3-forms` (F1a merged)
Process: `docs/build-spec/process-v3.md` section 2. Old ticket T07 (README row) is the reference; load the `tui-layout`
skill (`.claude/skills/tui-layout/SKILL.md`) and follow `packages/tl-tui/README.md` "Log screens".

## Goal
In the terminal app a person opens the forms log of the demo project, sees templates and submissions like any other
module log, opens a submission's record screen, and fills a published template step by step through the runner model
(`tl_core/forms/runner.py`) and submits it. Both through the client methods F1a put on `tl_tui/client.py` and
`embedded.py` (fill any stub F1a left for the runner; do not change the signatures of methods F1a defined).

## Build
1. `form_runner_text.py`: Textual-free logic (step text, answer parsing, review page) with unit tests; then the runner
   screen over it. One field per step, back, forward, hidden fields skipped, review, confirm; errors from the server
   shown as the CLI shows them.
2. Forms log (templates and submissions tabs or two logs, as other modules do) and the submission record screen,
   registered through the forms module's TUI hook rows (F1a's hook rows; add the screen rows only).
3. Walk: the TUI reads of this unit for the five readers (`tests/confidentiality/` pattern; F1a's
   `test_forms_walk.py` shows the readers): a hidden or other-author draft submission never appears in the log and its
   key opens the same "not found" as a missing key; a privileged submission appears only for its author (D40).
4. Demo clause 11 in `dev/demos/p2_forms_demo.py` (headless Textual pilot, as other demos drive the TUI if one does;
   else the runner screen driven through `form_runner_text` plus one `run_test` pass): open the log, fill and submit
   one template through the runner screen, the new number shows in the log. Prints wall time; `PASS clause 11` only
   after a real check. Clauses 1-3, 5, 7, 8 must stay green.

## Rules
May change forms fixtures, the forms generator section and the forms demo. No edit of `confidentiality.py`, no other
module's screens or handlers, no schema change. One tour shot is welcome but not required (F5 does the tour).

## Gate
`just gate-changed` (if it stops at the deferred `test_check_wheels` pin, run its later steps by hand and say so), then
`TL_DEMO_BACKENDS=sqlite just demo P2-FORMS`. Report `docs/reports/P2-FORMS/V3-F1b.md`, at most 15 lines. Prefix `V3-F1b:`.
