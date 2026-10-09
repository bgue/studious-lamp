# P0-I2-T17b — Key map data and the help screen (`F1`, `?`)

Status: ready
Tier: haiku
Labels: tui
Depends on: P0-I2-T16b, P0-I2-T16c (merged on `p0/i2b`); independent of T17
Branch: `p0/i2b-t17b-keymap-help`

## Goal
The key map becomes data (`tl_tui/keymap.py`) with a test that every documented key is a real binding on its widget, and `F1` or `?` opens a modal
that shows it. `Esc`, `F1` or `?` closes it. The footer's default hints already mention `F1 help`.

## Brief references (pasted)
> Discoverability: `?` shows contextual help; `F1` full key map; palette shows shortcuts. (§10.3)
> Default key map (§10.4): `Enter` open · `Esc` back/close overlay · `n` new · `e` edit · `Ctrl+S` save · `Space`/`Shift+↑↓` select · `Ctrl+A` select all · `[`/`]` previous/next record · `h` history · `F6`/`Shift+F6` cycle panels · `?`/`F1` help.
> All bindings user-configurable; conflict detection in the binding editor (later increment).

Learnings that apply:
- `uv` prints a harmless "UV_NATIVE_TLS is deprecated" warning on every call; ignore it.
- ruff `E501` is 100 columns, docstrings and comments included. Before `just check`, run
  `uv run ruff format packages/tl-tui` and `uv run ruff check --fix packages/tl-tui`.
- `Static` parses `[...]` as markup (the key map contains `[  ]`): use `markup=False`.
- Do not name an attribute after a Textual `Widget`/`Screen` attribute.
- An app-level binding stays active under a modal; the `help` action must do nothing when a modal screen is already showing.
- In a Textual `Binding`, `?` is `question_mark`, `[` is `left_square_bracket`.
- Tests have no async plugin: use `helpers.run_pilot` and `helpers.screen_text`.
- You may commit your report as `docs/reports/P0-I2/P0-I2-T17b.md`.

## Interfaces (verbatim from repo at the branch point, plus the new modules)
```python
# packages/tl-tui/src/tl_tui/app.py (existing): class TlApp(App[None]) with BINDINGS: ClassVar[list[BindingType]]; ModalScreen is already imported there
# packages/tl-tui/src/tl_tui/widgets/footer.py: DEFAULT_HINTS = "F1 help  F2 nav  F3 context  F6 panels  Ctrl+Q quit"   (already updated; do not edit footer.py)

# NEW: packages/tl-tui/src/tl_tui/keymap.py
CONTEXTS = ("App", "Grid", "Record view", "Forms")
@dataclass(frozen=True)
class KeyEntry:
    context: str; keys: str; description: str
    owner: str | None = None       # class name that implements the key, or None for keys Textual provides (Tab, Ctrl+Q)
    binding: str | None = None     # that class's binding key string, or None
KEYMAP: tuple[KeyEntry, ...]
def help_text() -> str: ...

# NEW: packages/tl-tui/src/tl_tui/widgets/help_screen.py
class HelpScreen(ModalScreen[None]):
    KEY_HINTS: ClassVar[str] = "Esc close"
```

Content of `KEYMAP` (exactly these 24 entries, in this order; `KeyEntry(context, keys, description, owner, binding)`):
```
App:         "F1  ?" "Show this key map" TlApp f1 | "F2" "Show or hide the navigation panel" TlApp f2 | "F3" "Show or hide the context panel" TlApp f3
             "F6  Shift+F6" "Move focus between panels" TlApp f6 | "n" "New record" TlApp n
             "Esc" "Close an open side panel (narrow terminals)" TlApp escape | "Ctrl+Q" "Quit" (no owner, no binding)
Grid:        "Up Down PgUp PgDn Home End" "Move the cursor" RecordGrid up | "Left Right" "Choose the column to sort by" RecordGrid left
             "Space" "Select or unselect the row" RecordGrid space | "Shift+Up Shift+Down" "Extend the selection" RecordGrid shift+down
             "Ctrl+A" "Select all loaded rows" RecordGrid ctrl+a | "Enter" "Open the record" RecordGrid enter
             "s" "Sort by the chosen column (again: descending, then off)" RecordGrid s | "c" "Choose columns" RecordGrid c
             "y" "Copy the selection as TSV" RecordGrid y | "r" "Reload the rows" RecordGrid r
Record view: "Esc" "Back to the grid" RecordView escape | "[  ]" "Previous or next record in the list" RecordView left_square_bracket
             "h" "Show the History tab" RecordView h | "e" "Edit the record" RecordView e
Forms:       "Tab  Shift+Tab" "Next or previous field" (no owner, no binding) | "Ctrl+S" "Save (edit form) or create (new record)" EditForm ctrl+s
             "Esc" "Cancel" EditForm escape
```
Rules for `help_text()`: for each context in `CONTEXTS`, in order, a heading line (the context name), then one line per entry of that context:
`f"  {entry.keys:<30}{entry.description}"`; a single empty line between contexts; lines joined with `"\n"` (no trailing newline).

Rules for `HelpScreen`: bindings `escape`, `f1`, `question_mark` all run `close` (`dismiss(None)`; the last two `show=False`). Layout: centred, about 90% wide (max 100) and 90% high,
`Vertical` with a border and `padding: 0 1`, holding `Static("Key map", markup=False)` and a `VerticalScroll` with `Static(help_text(), id="help-body", markup=False)`.

Rules for `TlApp` (`app.py`, the only edit there): add bindings `Binding("f1", "help", "Help", show=False)` and `Binding("question_mark", "help", "Help", show=False)` to `BINDINGS`,
and `action_help(self) -> None` that does nothing if `isinstance(self.screen, ModalScreen)`, otherwise (function-level import of `HelpScreen`) `self.push_screen(HelpScreen())`.

## Context (read these, nothing else)
- `AGENTS.md`, `packages/tl-tui/AGENTS.md`
- `packages/tl-tui/src/tl_tui/app.py`
- `packages/tl-tui/src/tl_tui/widgets/new_record_form.py` (read only: an example modal)
- `docs/tickets/P0-I2/provided/test_keymap.py.txt` (the test you must make pass)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/keymap.py` (create)
- `packages/tl-tui/src/tl_tui/widgets/help_screen.py` (create)
- `packages/tl-tui/src/tl_tui/app.py` (edit: the two bindings and `action_help` only)
- `packages/tl-tui/tests/test_keymap.py` (create by copying the provided file; do not edit it)
- `docs/reports/P0-I2/P0-I2-T17b.md` (your report)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_keymap.py.txt packages/tl-tui/tests/test_keymap.py`
2. Create the two modules; edit `app.py`.
3. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_keymap.py -q
uv run pytest packages/tl-tui -q
```
Expected: all pass.

## Tests to add
None beyond the provided file. It checks that every documented binding exists on its owner, the contexts, the brief keys, `help_text` lines, the default hints, opening and closing help with `F1` and `?`, no stacking, and no help over a form.

## Report requirements
Standard report, committed at `docs/reports/P0-I2/P0-I2-T17b.md`. State that the provided test file is byte-identical to the `.txt` and list the lines you changed in `app.py`.

## Escalation triggers
- Stop and report *Blocked* if a documented key is not a real binding on its owner and fixing that would need a change outside *Allowed paths*.

## Blocked

## Decision
