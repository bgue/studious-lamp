# Runbook — Run the TUI on the dev ledger

Purpose: start the Textual TUI in embedded mode against the dev ledger (a SQLite file, or a Postgres database: see `docs/runbooks/run-on-postgres.md`), load some records, and recover from the usual first-run problems. Brief: §4, §10.

## When to use
- Trigger: a developer or demo needs to see or edit records and psets in the TUI.

## Before you start
- Access needed: the repository, `uv` and `just` (the SessionStart hook installs both).
- Safe to run during business hours: yes (a local file ledger, `dev/data/tl.db`, which is git-ignored).

## Steps
1. Create a few records (the TUI has `n` for new records too, but a CLI seed is quicker):
   ```
   uv run tl init --dev
   uv run tl record create --project P123 --key V-0001 --title "Valve 1"
   uv run tl record create --project P123 --title "Valve 2"
   ```
   Expected: `created <id>` and `key V-0001`; the second record, given no key, gets `P123-REC-0001` from the numbering pattern.
2. Start the TUI:
   ```
   just tui
   ```
   Expected: first the sign-in screen (`demo` / `demo`, created by `tl init --dev` in a dev setup; or sign in beforehand with `uv run tl login <username>` and the TUI skips the screen), then the grid lists V-0001 and P123-REC-0001. `F10` opens the accounts screen for an admin (`docs/runbooks/accounts-and-access.md`). `Enter` opens a record, `e` edits it (Ctrl+S saves), `n` creates one, `F1` shows the key map, `Ctrl+Q` quits. In a record: `l` links it to another, `w` shows workflow actions, `t` traces its links, `R` adds it to the reference tray (`F4` opens the tray), `Alt+Left` goes back. `Ctrl+P` opens the command palette.
3. Use another ledger or project with environment variables:
   ```
   TL_DB=/tmp/other.db TL_PROJECT=P124 just tui
   ```
4. Filter the list: `/` opens the filter bar; type query-language text (`status:open title~bevel linked:NCR`, reference: `docs/reference/query-language.md`) and press Enter. The bar shows `N matches`, or the parser's message with a caret under the character it stopped at. A blank filter clears it; Esc leaves the bar.
4b. Open about:config with `F9` (or `about:config` in the command palette): every setting with its value, type, origin and lock; `/` filters, `m` shows only what is set here, `e` edits (the form asks for a reason, and for a dangerous key the box "I accept the risk"), `r` resets, `h` shows the history (`u` undoes the latest change at a layer), `k` locks for projects, `L` sends changes to the company instead of the project. See `settings.md`.
5. Run against a server instead of the file (remote mode). In one terminal start the API, in another the TUI:
   ```
   uv run tl serve                                   # 127.0.0.1:8765
   uv run tl tui --remote http://127.0.0.1:8765      # the sign-in screen asks for a username and password
   ```
   A dev token still works where the server allows dev tokens (`TL_ENV` dev, test or ci): `export TL_TOKEN="$(uv run tl dev token add user:alice)"` skips the sign-in screen.
   Expected: the same screens, header `● remote`. A record written by someone else (another TUI, `tl record create`, an MCP agent) shows a `•` on its row for a few seconds; an open record shows `! Updated by user:x (now vN)`; an open edit form shows `✗ Conflict` and refuses to save until you cancel and open it again.

6. Open files and see page 1 (the document register `F7`, the Files tab `6` of a record). `v` or Enter opens the chosen file in the system viewer; where the terminal shows colour the first page of a PDF is drawn in the panel. Control both with environment variables:
   ```
   TL_IMAGES=off     just tui   # text only: kind, size, page count (also what the tests use)
   TL_IMAGES=kitty   just tui   # force the picture: kitty, iterm2 or sixel; any other value means off
   TL_VIEWER_CMD="/path/to/record-path.sh" just tui   # run this instead of xdg-open/open; the file path is added as the last argument
   ```
   Without `TL_IMAGES` the terminal is detected from `KITTY_WINDOW_ID`, `TERM`, `TERM_PROGRAM`, `WT_SESSION` (never under tmux or screen). `TL_VIEWER_CMD` is split like a shell line but run without a shell. Pictures are cached in `~/.cache/throughline/preview` (`$XDG_CACHE_HOME`); delete the folder to clear it. Expected: the register's panel lists `sheet-B.pdf  PDF document  1.2 MB  3 pages`, `v` starts the viewer, the status line says `Opened sheet-B.pdf.`

7. Prove the log standard and the file preview end to end, and regenerate the tours. `just demo P1-UX2` seeds three RFIs (one after an answer round, with two files), a document with a 3-page PDF and a recorder script as `TL_VIEWER_CMD`, then drives the TUI headless on SQLite and on a throw-away Postgres database (about 4 minutes per backend, most of it seeding through the `tl` commands). It prints one `PASS` line for each of four clauses: the breadcrumb follows the highlighted row; the bar offers Answer where an answer is due and Issue to a controller only, and `a` from the bar answers; the RFI record shows the question, the timeline and both files; `v` hands the viewer a private copy whose sha256 equals the stored file's, and with `TL_IMAGES=off` the panel reads `PDF document ... 3 pages`. Section 24 of `docs/reports/PHASE-1-TOUR.md` shows the same screens. `just tour-all` rewrites both tours and checks every plain screenshot for ids, hashes and internal keys while it visits the screens (a `LEAK <shot> <tokens>` line and exit 1 on a hit); a second run changes no file. Fix a leak in the screen, or in the tour's own list when the text is a false hit, never by hiding text.

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
- A 401 in remote mode with a token from `TL_TOKEN`: the token is not in the server's token file (`uv run tl dev token add user:<id>`; the file must be mode 0600).
- No live marks in embedded mode when another process writes: both must use the same `TL_DB` (the same file, or the same Postgres database and schema); the TUI polls the ledger every 0.25 s on either database.

## Related
- `packages/tl-tui/README.md`; `docs/runbooks/rebuild-projections.md`; `docs/runbooks/schema-package-change.md`.
