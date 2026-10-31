# Report — P2-W0-TOUR (phase 1 tour, module-roles story)

Branch: `p2/w0-tour`   Commits: `3f69018` (tour, doc, screenshots), then this report.
Status: DONE. `just tour 1` runs to the end (83 screenshots); a second run changes no file.

## Deviations
- None outside the allowed paths. No product code touched. `uv sync --all-packages` was run once in the new worktree (no `.venv` there).

## What was refused, and why
- Section 14, step "dora has the role `user`, so issuing is refused": the tour asserted the old text
  `needs the document_controller or admin role`. The product refused correctly, with
  `IssueRevision needs the controller access word for documents on project:P123`.
  Not a product bug: dora (account role `user`) derives module role `user` only. After the
  grant of `document_controller` she derives `superuser` on documents and issues; this passed.
- Section 25 (`section_module_roles`, added by T11) then timed out waiting for lowercase `amy` and
  `documents`; the module roles log shows display names (`Amy A`, `Documents`, `Superuser`).

## Tour changes (dev/tour/phase1.py)
- `NEEDS` is now `needs the controller access word for documents`; two notes reworded (section 13, 14).
- Section 25 waits for and checks `Amy A` / `Documents` / `Superuser` on the screen.

## Story changes (docs/reports/PHASE-1-TOUR.md)
- Intro, section 13, section 14 and the 18b caption text now describe the access-word refusal
  and how the words are held (user derives `user`, `document_controller` derives `superuser` on
  documents, correspondence, schedule; admin holds all).
- New section 25 "Module roles" with 25a, 25b and a table row; limits bullet updated.
- Two screens still show the older text `this command needs the document_controller or admin role`
  (12-dms-import: apply a document import; 18b: accept a proposal). That is the product today, and the
  text says so (account-role checks, not the module word). Possible follow-up: move them to access words.

## Commands
- `just check` clean.
- `just tour 1` (rc 0, 83 screenshots); committed; `just tour 1` again: `git status --short docs/reports/tour dev` empty.
- No pytest run.
