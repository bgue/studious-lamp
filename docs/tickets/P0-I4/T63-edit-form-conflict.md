# P0-I4-T63 — Edit form conflict banner

Status: ready
Tier: haiku
Labels: tui
Depends on: —
Branch: `p0/i4d-t63-edit-conflict`

## Goal
When the record being edited is changed by someone else, the edit form says so and refuses to save, instead of overwriting or failing late. The stub adds `EditForm.mark_conflict` (final signature; the body raises `NotImplementedError`) and the attributes `opened_version` and `conflict`. Implement the banner, the blocked save, and the same banner when the ledger refuses a save with `ConcurrencyError`. The app (supervisor, next round) calls `mark_conflict(actor, version)` when the change feed shows the record's `stream_version` moved past the version the form was opened at. One provided test file (5 tests) must pass; the existing edit-form tests must stay green.

## Brief references (pasted)
> **Phase 0 plan, increment 4, workstream D:** "conflict detection via `stream_version`". The save already sends `expected_version`, so the ledger refuses a stale write; this ticket makes the form say so early and keeps what the user typed. **10.3:** meaning never rides on colour alone, so the banner starts with `✗`.

### Specification (the provided tests check it)
- CSS: add this line inside the existing `DEFAULT_CSS`:
  `#form-conflict { height: auto; display: none; background: $error 50%; padding: 0 1; }`
- `compose`: right after `yield Static(f"Edit {self.record['key']}", markup=False)` yield `Static("", id="form-conflict", markup=False)`.
- `mark_conflict(actor=None, version=None)`: set `self.conflict = True`. Build `who = f"{actor} changed this record" if actor else "this record changed"` and `now = f" (now v{version}, you opened v{self.opened_version})" if version else ""`. Update `#form-conflict` with `f"✗ Conflict: {who}{now}. Saving is blocked: Esc cancels, then e opens it."` and set its `display = True`.
- `action_save`: first lines: `if self.conflict:` set the status (`self._status(...)`) to `"Not saved: the record changed; cancel and open the form again"` and `return`, so no command is sent.
- At the end of `action_save`, after the existing `self._status(f"Not saved: {reason}")` line, add `if isinstance(outcome.error, ConcurrencyError): self.mark_conflict()`. Keep the existing status text: the existing tests read it.
- Import to add: `from tl_core.ledger import ConcurrencyError` (next to the other `tl_*` imports, after `textual` imports, before `tl_schema`).

Learnings that apply:
- The provided test lives at `docs/tickets/P0-I4/provided/test_edit_form_conflict.py.txt`; copy it to `packages/tl-tui/tests/test_edit_form_conflict.py` and do not edit the copy. It is already formatted: `diff` the copy against the original in the last acceptance step.
- The existing `packages/tl-tui/tests/test_edit_form.py` reads the footer text `Not saved: this record changed since you opened it`; it must keep passing.
- Textual: a `Static` shows `[...]` as markup unless `markup=False`; do not name an attribute after a DOM property. Do not add `__init__.py` to the tests directory.
- ruff limits lines to 100 columns, docstrings included; run `uv run ruff format packages` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- A `Blocked` caused by a red `just check` on the branch point (not by your change) is not a strike: report it and stop.
- Commit your report file (`docs/reports/P0-I4/P0-I4-T63.md`); it is inside your Allowed paths.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/widgets/edit_form.py (the stub)
class EditForm(ModalScreen[bool]):
    # __init__ now also sets:  self.opened_version = int(record["version"]);  self.conflict = False
    def mark_conflict(self, actor: str | None = None, version: int | None = None) -> None
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/edit_form.py`
- `packages/tl-tui/tests/test_edit_form_conflict.py` (after you copy it)
- `packages/tl-tui/tests/test_edit_form.py` (existing tests that must stay green)
- `packages/tl-tui/AGENTS.md`
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/edit_form.py` (edit)
- `packages/tl-tui/tests/test_edit_form_conflict.py` (create: copy of the provided test)
- `docs/reports/P0-I4/P0-I4-T63.md` (create: your report)

## Acceptance
```
cp docs/tickets/P0-I4/provided/test_edit_form_conflict.py.txt packages/tl-tui/tests/test_edit_form_conflict.py
uv run pytest packages/tl-tui/tests/test_edit_form_conflict.py -q
just check
uv run pytest packages/tl-tui -q
diff packages/tl-tui/tests/test_edit_form_conflict.py docs/tickets/P0-I4/provided/test_edit_form_conflict.py.txt
```
Expected: 5 tests pass in the first command; `just check` is clean; the whole TUI suite passes; the diff is empty.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report. Paste the pass counts of the first and third commands.

## Escalation triggers
- Stop and report *Blocked* if an existing edit-form test fails because of the required change, or if a provided test cannot pass without changing a file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
