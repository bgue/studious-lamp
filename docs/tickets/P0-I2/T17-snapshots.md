# P0-I2-T17 — Snapshot tests for the shell, grid, record view, psets tab, forms and narrow mode

Status: ready
Tier: haiku
Labels: tui, tests
Depends on: P0-I2-T16b, P0-I2-T16c (merged on `p0/i2b`)
Branch: `p0/i2b-t17-snapshots`

## Goal
`just test-tui` gains 15 snapshot tests that pin how every Increment 2 screen looks at 120x40 and 80x24: the shell (wide, panels
collapsed, narrow, narrow with the nav overlay), the grid with a selection and a sort, the column chooser, the record view (Details,
History, narrow), the Psets tab for a conformant and a nonconformant record, the edit form, the new-record form, and the footer status line.
The test file is provided; this ticket generates, checks and commits the stored snapshots.

## Brief references (pasted)
> Snapshot tests for every TUI screen listed in a ticket (build spec 03 §10). Terminal sizes are pinned (120x40 and 80x24) to avoid flakiness (FANOUT risk).
> Exit criterion: TUI snapshot tests for shell, grid, record view, psets tab, narrow mode (FANOUT).
> Narrow terminal (80 columns or less): side panels become overlays on F2/F3 (§10.6 sketch 11).

Learnings that apply:
- `uv` prints a harmless "UV_NATIVE_TLS is deprecated" warning on every call; ignore it.
- `pytest-textual-snapshot` writes one `.raw` file per test to `__snapshots__/<test module>/<test name>.raw` beside the test file, and passes across separate processes.
  Create or refresh them only with `--snapshot-update`; a normal run compares. A snapshot test whose screen shows nothing useful is worthless, so the provided
  tests also assert strings on screen before the snapshot is taken.
- Nothing on screen may depend on the clock or on random values (the fake client is deterministic).
- Tests have no async plugin; the provided file already uses `snap_compare`.
- You may commit your report as `docs/reports/P0-I2/P0-I2-T17.md`.

## Interfaces (verbatim from repo at the branch point)
```python
# pytest fixture from pytest-textual-snapshot (already installed):
snap_compare(app_or_path, press=(), terminal_size=(80, 24), run_before=None) -> bool
# packages/tl-tui/tests/fakes.py: FakeClient.with_valve_example()   # three valve records, deterministic ids, times and hashes
# packages/tl-tui/tests/helpers.py: screen_text(app) -> str
```

## Context (read these, nothing else)
- `AGENTS.md`, `packages/tl-tui/AGENTS.md`
- `docs/tickets/P0-I2/provided/test_snapshots.py.txt` (the test file; read it fully)
- `packages/tl-tui/tests/helpers.py`
may explore: (none)

## Allowed paths
- `packages/tl-tui/tests/test_snapshots.py` (create by copying the provided file; do not edit it)
- `packages/tl-tui/tests/__snapshots__/test_snapshots/*.raw` (create; generated)
- `docs/reports/P0-I2/P0-I2-T17.md` (your report)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_snapshots.py.txt packages/tl-tui/tests/test_snapshots.py`
2. `uv run pytest packages/tl-tui/tests/test_snapshots.py -q --snapshot-update` once. Expect `15 snapshots generated`.
3. Check there are exactly 15 `.raw` files and that none is empty (`wc -c`). Open two of them (for example `test_shell_wide.raw` and `test_psets_tab_nonconformant.raw`) and confirm the text content shows the screen (the SVG holds the screen text, for example `FV-1001`).
4. Run `uv run pytest packages/tl-tui/tests/test_snapshots.py -q` three times without `--snapshot-update`; all three must pass (this is the flakiness check).
5. `git add` the test file and the 15 snapshots; commit.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_snapshots.py -q
just test-tui
```
Expected: 15 passed in the snapshot file; `just test-tui` green; `just check` clean.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report, committed at `docs/reports/P0-I2/P0-I2-T17.md`. Include the `wc -c` listing of the 15 snapshot files, the three passing runs, and a statement that the test file is byte-identical to the `.txt`.
If a run without `--snapshot-update` fails, do not regenerate to hide it: report which test failed and what differed.

## Escalation triggers
- Stop and report *Blocked* if any snapshot differs between two consecutive runs without an update (flaky), or if a provided test fails before the snapshot is taken.
- This ticket exceeds the 5-file guideline only because the snapshots are generated files.

## Blocked

## Decision
