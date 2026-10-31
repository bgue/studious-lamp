# Report — T07 (ticket P2-W0-RM-S3-L)

Branch: `p2/w0-t07-roles-lows`   Commit(s): the T07 commit on this branch (sha in `git log`; this report is in that commit)

## Deviations
Report path: written to `docs/reports/P2-W0/RM-S3-L.md`, the ticket's Allowed path, not `docs/reports/P2-W0/T07.md` as the task text asked. The ticket's Allowed paths is the write boundary (AGENTS.md rule 1). The commit trailer names Claude Haiku 5.5, my own model; the task text said Opus 5.5.

## Changed files
- `packages/tl-tui/src/tl_tui/admin_text.py` — F1 `effective_line` returns `EMPTY` (docstring fixed); F2 `effective_page` passes `summary=join_facts(...)` with a local `n`; imports `EMPTY`, `join_facts` from `tl_tui.layout`
- `packages/tl-tui/src/tl_tui/widgets/admin_screen.py` — F3 `getattr(self.app, "is_admin", False)`
- `packages/tl-cli/src/tl_cli/admin_roles.py` — F4 deleted the two comment lines and one of the two blank lines after them (two blank lines still precede `def scope_of`)
- `docs/reports/P2-W0/RM-S3-L.md` — this report

## Commands and output
```
$ just check
uv run python -m tl_api.openapi --check
uv run python dev/tools/check_licences.py
licences ok
(exit 0)
$ uv run python dev/accept/P2-W0/RM-S3.py | tail -15
PASS CLI: a signed-in plain user is refused `tl admin roles ls` (exit 1, forbidden)
PASS module roles log at 170 columns: 3 rows, panel, refusal in the status line
PASS module roles log: key n opens the form and sends one grant for the current project
PASS key m opens nothing for a non-admin (F10 refuses; no module role call was made)
ALL PASS
(exit 0; no PASS line changed wording; the script does not pin `none`)
$ grep -rn "effective_line\|\"none\"" packages/tl-tui/tests/test_admin_text.py packages/tl-tui/tests/test_admin_plain.py
(no output, grep exit 1)
```

## Tests added
none (ticket: "Tests to add: None"; pytest not run per the ticket's Acceptance).

## Old-text pins (for the end-run TA)
- `packages/tl-tui/tests/test_admin_text.py`, `packages/tl-tui/tests/test_admin_plain.py`: no line pins the old `none` text of `effective_line`. Both files were searched as the ticket asks.
- Wider read-only search, no edit: no test references `effective_line` or `effective_page` by name, and no test asserts `Effective roles` text. `packages/tl-tui/tests/test_admin_text.py:114` (`"Lock      none"`) is the lock column, not this line, and is untouched.
- `fakes_admin.py` uses `source="none"` (a resolver source value, not the display text), untouched.

## Learnings (proposed)
- `AdminApp` already defaults `is_admin` to `False` (`packages/tl-tui/src/tl_tui/app.py:122`). F3 changes behaviour only for an app object that lacks the attribute entirely (test doubles). The real app is unaffected.
- `just check` does not run pytest, so F1 and F2 are not exercised by anything in this ticket. The end run must cover them.

## Open questions / Blocked
- Pluralisation: F2 as specified gives `1 of 1 modules` and `0 of 3 modules`. The ticket asked for this exact text, so I did not change it. The supervisor should decide whether to keep it.
- Report path (see Deviations): confirm `RM-S3-L.md` versus `T07.md`.
