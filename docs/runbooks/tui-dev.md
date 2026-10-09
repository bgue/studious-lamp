# Runbook — Run the TUI on the dev ledger

Purpose: start the Textual TUI in embedded mode against the SQLite dev ledger, load some records, and recover from the usual first-run problems. Brief: §4, §10.

## When to use
- Trigger: a developer or demo needs to see or edit records and psets in the TUI.

## Before you start
- Access needed: the repository, `uv` and `just` (the SessionStart hook installs both).
- Safe to run during business hours: yes (a local file ledger, `dev/data/tl.db`, which is git-ignored).

## Steps
1. Create a few records (the TUI has `n` for new records too, but a CLI seed is quicker):
   ```
   uv run tl init
   uv run tl record create --project P123 --key V-0001 --title "Valve 1"
   uv run tl record create --project P123 --title "Valve 2"
   ```
   Expected: `created <id>` and `key V-0001`; the second record, given no key, gets `P123-REC-0001` from the numbering pattern.
2. Start the TUI:
   ```
   just tui
   ```
   Expected: the grid lists V-0001 and P123-REC-0001. `Enter` opens a record, `e` edits it (Ctrl+S saves), `n` creates one, `F1` shows the key map, `Ctrl+Q` quits. In a record: `l` links it to another, `w` shows workflow actions, `t` traces its links, `R` adds it to the reference tray (`F4` opens the tray), `Alt+Left` goes back. `Ctrl+P` opens the command palette.
3. Use another ledger or project with environment variables:
   ```
   TL_DB=/tmp/other.db TL_PROJECT=P124 just tui
   ```

## Verify
- After a save, `uv run tl pset get --project P123 V-0001` shows the same values and the conformance level.
- `uv run tl events tail --project P123 -n 5` shows the `Pset.ValuesSet` events.

## Roll back
- Edits are events and are never deleted. To start over, delete `dev/data/tl.db` and run `uv run tl init`.

## Troubleshooting
- Empty Psets tab with "pset services are not installed yet": the checkout predates the pset services; update the branch.
- Wrong or missing property list: `TL_SCHEMA_DIR` points at another package directory (default `schema/fixtures`); `uv run tl schema validate` names the problem.
- Terminal too narrow: at 80 columns or fewer the side panels become overlays on `F2` and `F3`.

## Related
- `packages/tl-tui/README.md`; `docs/runbooks/rebuild-projections.md`; `docs/runbooks/schema-package-change.md`.
