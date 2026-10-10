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
4. Filter the list: `/` opens the filter bar; type query-language text (`status:open title~bevel linked:NCR`, reference: `docs/reference/query-language.md`) and press Enter. The bar shows `N matches`, or the parser's message with a caret under the character it stopped at. A blank filter clears it; Esc leaves the bar.
5. Run against a server instead of the file (remote mode). In one terminal start the API, in another the TUI:
   ```
   export TL_TOKEN="$(uv run tl dev token add user:alice)"
   uv run tl serve                                   # 127.0.0.1:8765
   uv run tl tui --remote http://127.0.0.1:8765      # token from TL_TOKEN
   ```
   Expected: the same screens, header `● remote`. A record written by someone else (another TUI, `tl record create`, an MCP agent) shows a `•` on its row for a few seconds; an open record shows `! Updated by user:x (now vN)`; an open edit form shows `✗ Conflict` and refuses to save until you cancel and open it again.

## Verify
- After a save, `uv run tl pset get --project P123 V-0001` shows the same values and the conformance level.
- `uv run tl events tail --project P123 -n 5` shows the `Pset.ValuesSet` events.

## Roll back
- Edits are events and are never deleted. To start over, delete `dev/data/tl.db` and run `uv run tl init`.

## Troubleshooting
- Empty Psets tab with "pset services are not installed yet": the checkout predates the pset services; update the branch.
- Wrong or missing property list: `TL_SCHEMA_DIR` points at another package directory (default `schema/fixtures`); `uv run tl schema validate` names the problem.
- Terminal too narrow: at 80 columns or fewer the side panels become overlays on `F2` and `F3`.
- Red line under the header, "Server unreachable" (remote): the TUI cannot reach the API. Check `tl serve` is running and the URL and token are right; the TUI retries (0.25 s growing to 5 s) and resumes from the last event it saw, so nothing is missed or repeated. "server ledger changed; reloaded" means the server's ledger was replaced or restored; the TUI read everything again.
- A 401 in remote mode: the token is not in the server's token file (`uv run tl dev token add user:<id>`; the file must be mode 0600).
- No live marks in embedded mode when another process writes: both must use the same `TL_DB` file; the TUI polls the file every 0.25 s.

## Related
- `packages/tl-tui/README.md`; `docs/runbooks/rebuild-projections.md`; `docs/runbooks/schema-package-change.md`.
