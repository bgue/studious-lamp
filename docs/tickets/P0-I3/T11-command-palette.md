# P0-I3-T11 — Command palette

Status: ready
Tier: haiku
Labels: tui
Depends on: the TUI wiring commit on the base branch (`TlApp.action_palette`, `commands.py`, the stub)
Branch: `p0/i3-t11-command-palette`

## Goal
`Ctrl+P` and `:` open a palette over the whole app: typing searches records by key or title and filters the app's commands; Enter opens the
record or runs the command. The app wiring (`TlApp.action_palette`, `tl_tui/commands.py`), the data types, the layout (`compose`), the
constructor and the key bindings exist in `tl_tui/widgets/palette.py`; the three pure functions and the methods marked
`raise NotImplementedError` are the work. A provided test file (31 tests) must pass.

## Brief references (pasted)
> **10.2 Command palette:** Fuzzy search over every command, record type, saved view, and record key. The universal entry point. **Go-to:** type any record key → open it.
> **Sketch 3** (overlay, `Ctrl+P` or `:`): a search line; then sections `Records` (key, type, state), `Screens & views`, `Commands` (label and its key on the right); footer "Tab type filter · ↑↓ move · Enter run · Esc close".

### Specification (the provided test checks it)
Pure functions (module level):
- `fuzzy_score(query, text) -> int | None`: case-insensitive subsequence match of the query's non-space characters against `text`. Walk the query characters in order, each found with `lowered.find(char, position)` starting after the previous match; a missing character gives `None`. Each matched character scores 1; +4 if it is directly after the previous match (`found == previous + 1`, with `previous` starting at `-2`); +6 if it starts a word (index 0, or the character before it is not a letter or digit). After the loop, +20 once if the whole non-space query is a prefix of the lower-cased text. An empty (or all-space) query scores 0.
- `build_rows(query, commands, records, mode="all") -> list[PaletteRow]`: first a records section when `mode != "commands"` and `records` is non-empty: `PaletteRow("header", "Records")`, then per record `PaletteRow("record", key, f"{title} · {status}", "Enter", PaletteChoice("record", key=target.key))` where `key = target.key or EMPTY` and `status = target.status or EMPTY` (`EMPTY` is `—`, from `tl_tui.text`). Then, when `mode != "records"`: score every command with `fuzzy_score(query, command.label)`, keep those that are not `None`, sort by `(-score, original index)`; if any are kept: `PaletteRow("header", "Commands")` then per command `PaletteRow("command", command.label, "", command.keys, PaletteChoice("command", command_id=command.id))`.
- `row_line(row, selected, width) -> str`, exactly `width` cells (use `rich.cells.cell_len` and `set_cell_size`): a header row is `f"─ {row.label} "` followed by `─` up to `width` (cut with `set_cell_size(head, width)` if it is already as long). Any other row: `left = ("▶ " if selected else "  ") + row.label + (f"  {row.detail}" if row.detail else "")`; `room = width - (cell_len(row.hint) + 1 if row.hint else 0)`; if `cell_len(left) > room` then `left = set_cell_size(left, room - 1) + "…"` (or `""` when `room <= 0`); then `left + spaces + row.hint` where the spaces fill to `width` (at least 0); finally `set_cell_size(result, width)`.

`CommandPalette` (a `ModalScreen[PaletteChoice | None]`; `compose` is written: an `Input#palette-input`, an `OptionList#palette-list`, a `Static#palette-foot`):
- `on_mount`: focus the input, then `_refresh()`.
- `_records(query) -> list[LinkTarget]`: `[]` for a blank query, else `self.client.search_linkable(self.scope, query, limit=RECORD_LIMIT)`; on `CLIENT_ERRORS` (from `tl_tui.errors`) return `[]`.
- `_refresh()`: `query` = the input's value; `self.rows = build_rows(query, self.commands, self._records(query), self.mode)`; `width = max(option_list.size.width, 40)`; `option_list.clear_options()` then `add_options([...])` with one `Option(Text(row_line(row, False, width)), id=str(i), disabled=row.kind == "header")` per row (**wrap in `rich.text.Text`**: a plain string is parsed as markup); set `option_list.highlighted` to the index of the first row that is not a header; set the footer Static to `f"Showing: {self.mode}"`.
- `on_input_changed(event)`: `event.stop()` then `_refresh()`. `on_input_submitted(event)`: `event.stop()` then `_choose(option_list.highlighted)`. `on_option_list_option_selected(event)`: `event.stop()` then `_choose(event.option_index)`.
- `_choose(index)`: ignore `None` or an out-of-range index; `choice = self.rows[index].choice`; if not `None`, `self.dismiss(choice)`.
- `action_move(delta)`: `option_list.action_cursor_down()` for `delta > 0`, else `action_cursor_up()`.
- `action_next_mode()`: `self.mode` becomes the next entry of `MODES` (wrapping), then `_refresh()`. `action_cancel()`: `self.dismiss(None)`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I3/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- No async pytest plugin: tests use `helpers.run_pilot` and `helpers.screen_text`. `Static` and `OptionList` parse `[...]` as markup: use `markup=False` / `rich.text.Text`.
- Do not name an attribute after a Textual DOM property. `uv run ruff format` and `uv run ruff check --fix` before `just check`; ruff limits lines to 100 columns. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- The stub had its unused imports removed; add back what you use (`Text`, `Option`, `cell_len`, `set_cell_size`, `CLIENT_ERRORS`, `EMPTY`).
- Remove the `STUB (P0-I3-T11)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/widgets/palette.py (existing stub; keep every name, signature and the layout)
Mode = Literal["all", "records", "commands"]; MODES: tuple[Mode, ...] = ("all", "records", "commands"); RECORD_LIMIT = 8
@dataclass(frozen=True) class PaletteChoice: kind: Literal["record", "command"]; key: str | None = None; command_id: str | None = None
@dataclass(frozen=True) class PaletteRow: kind: Literal["header", "record", "command"]; label: str; detail: str = ""; hint: str = ""; choice: PaletteChoice | None = None
def fuzzy_score(query: str, text: str) -> int | None
def build_rows(query: str, commands: Sequence[AppCommand], records: Sequence[LinkTarget], mode: Mode = "all") -> list[PaletteRow]
def row_line(row: PaletteRow, selected: bool, width: int) -> str
class CommandPalette(ModalScreen[PaletteChoice | None]):
    def __init__(self, client: ClientInterface, scope: str, commands: Sequence[AppCommand] = APP_COMMANDS) -> None   # sets .client .scope .commands .mode ("all") .rows ([])
```
```python
# existing
# tl_tui.commands.AppCommand: id, label, keys, action        (frozen dataclass)
# tl_core.services.link_queries.LinkTarget: id, key (str | None), type, title, status (str | None), scope, link_total
# ClientInterface.search_linkable(scope, query, *, record_type=None, exclude_id=None, limit=20) -> list[LinkTarget]
# tl_tui.errors.CLIENT_ERRORS (tuple of exception types); tl_tui.text.EMPTY == "—"
```

## Context (read these, nothing else)
- `AGENTS.md`, `packages/tl-tui/AGENTS.md`
- `packages/tl-tui/src/tl_tui/widgets/palette.py`
- `packages/tl-tui/src/tl_tui/widgets/help_screen.py` (style of a modal)
- `packages/tl-tui/tests/fakes.py` (read only; `FakeClient`)
- `docs/tickets/P0-I3/provided/test_palette.py.txt` (the test you must make pass)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/palette.py` (edit)
- `packages/tl-tui/tests/test_palette.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I3/P0-I3-T11.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I3/provided/test_palette.py.txt packages/tl-tui/tests/test_palette.py`
2. Implement the three functions and the methods; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-tui/tests/test_palette.py -q
just check
just test
diff docs/tickets/P0-I3/provided/test_palette.py.txt packages/tl-tui/tests/test_palette.py
```
Expected: 31 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change `app.py`, `commands.py`, the fakes or any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
