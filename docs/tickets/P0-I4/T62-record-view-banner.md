# P0-I4-T62 — Record view "updated by" line

Status: ready
Tier: haiku
Labels: tui
Depends on: —
Branch: `p0/i4d-t62-record-banner`

## Goal
`RecordView` shows a one-line notice under its header when another client changed the open record: `! Updated by user:bob (now v5)`. The stub adds `note_remote_update` and `clear_remote_update` with final signatures (bodies raise `NotImplementedError`). Implement them, add the hidden `Static` the line lives in, and make sure an unchanged record view looks exactly as before (the snapshot tests must stay green). The app (supervisor, next round) calls `note_remote_update` after reloading the view for a change made elsewhere. One provided test file (5 tests) must pass.

## Brief references (pasted)
> **Phase 0 plan, increment 4, workstream D:** "record view 'updated by X' banner". **10.3:** meaning never rides on colour alone, so the line starts with `!`.

### Specification (the provided tests check it)
- In `compose`, right after the `#rv-header` Static, yield `Static("", id="rv-banner", markup=False)`.
- Add a class attribute to `RecordView`:
  ```python
  DEFAULT_CSS = """
  RecordView #rv-banner { height: auto; display: none; background: $warning 35%; padding: 0 1; }
  """
  ```
  (hidden while empty, so existing layouts and snapshots do not change).
- `note_remote_update(actor, version, when=None)`: text is `f"! Updated by {actor}{at} (now v{version})"` where `at` is `f" at {when:%H:%M:%S}"` when `when` is given, else empty. Update the Static with it and set its `display = True`. A later call replaces the text.
- `clear_remote_update()`: update the Static with `""` and set `display = False`.
- `reload()` must not touch the line (the provided test calls `reload()` after a note and expects the line to stay). Do not change `reload()`.

Learnings that apply:
- The provided test lives at `docs/tickets/P0-I4/provided/test_record_view_banner.py.txt`; copy it to `packages/tl-tui/tests/test_record_view_banner.py` and do not edit the copy. It is already formatted: `diff` the copy against the original in the last acceptance step.
- Textual: a `Static` shows `[...]` as markup unless `markup=False`; do not name an attribute after a DOM property. Do not add `__init__.py` to the tests directory.
- ruff limits lines to 100 columns, docstrings included; run `uv run ruff format packages` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- A `Blocked` caused by a red `just check` on the branch point (not by your change) is not a strike: report it and stop.
- Commit your report file (`docs/reports/P0-I4/P0-I4-T62.md`); it is inside your Allowed paths.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/widgets/record_view.py (the stub; `from datetime import datetime` is already imported)
class RecordView(Vertical, can_focus=True):
    def note_remote_update(self, actor: str, version: int, when: datetime | None = None) -> None
    def clear_remote_update(self) -> None
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/record_view.py`
- `packages/tl-tui/tests/test_record_view_banner.py` (after you copy it)
- `packages/tl-tui/tests/test_record_view.py` (existing tests that must stay green)
- `packages/tl-tui/AGENTS.md`
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/record_view.py` (edit)
- `packages/tl-tui/tests/test_record_view_banner.py` (create: copy of the provided test)
- `docs/reports/P0-I4/P0-I4-T62.md` (create: your report)

## Acceptance
```
cp docs/tickets/P0-I4/provided/test_record_view_banner.py.txt packages/tl-tui/tests/test_record_view_banner.py
uv run pytest packages/tl-tui/tests/test_record_view_banner.py -q
just check
uv run pytest packages/tl-tui -q
diff packages/tl-tui/tests/test_record_view_banner.py docs/tickets/P0-I4/provided/test_record_view_banner.py.txt
```
Expected: 5 tests pass in the first command; `just check` is clean; the whole TUI suite (including its snapshot tests) passes; the diff is empty.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report. Paste the pass counts of the first and third commands.

## Escalation triggers
- Stop and report *Blocked* if a snapshot test changes (the line must be invisible while empty), or if a provided test cannot pass without changing a file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
