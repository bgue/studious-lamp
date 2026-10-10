# P0-I3-T13b — Reference tray screen

Status: ready
Tier: haiku
Labels: tui
Depends on: the TUI wiring commit on the base branch (`ReferenceTray`, `TlApp.action_tray_add` and `action_tray_open`, the stub)
Branch: `p0/i3-t13b-reference-tray`

## Goal
The reference tray is a clipboard of records: `R` adds the selection, the cursor row or the open record (the app part is written). `F4` opens this
screen, which lists the tray, lets the user tick, remove or clear entries, and links the ticked ones to the open record with a chosen relation and pin.
`tl_tui/widgets/ref_tray.py` has the layout (`compose`), constructor, key bindings, `title_text`, the relation helpers and a `TrayList` that makes Space tick;
the two pure functions and the methods marked `raise NotImplementedError` are the work. A provided test file (13 tests) must pass.

## Brief references (pasted)
> **7.2 Reference tray (`R`):** a clipboard for references. Add records from anywhere (grid, search, model, feed, thread) across screens and sessions, then link the checked ones to the current record with one action (sketch §10.6).
> **Sketch 12** (right panel): `Reference tray (4) [R]`, rows `[x] 47-1240-W008  Weld`, `[ ] D-4471  client DMS`; "Link checked here as: [requires ▾] [floating ▾] [ Link 3 ] [ Clear tray ]".
> (In this build the tray is session state of the app; it is not kept between sessions.)

### Specification (the provided test checks it)
Pure functions (`TrayItem(record_id, key, type, title)` and `ReferenceTray` are in the interfaces):
- `tray_line(item, checked, highlighted, width)`: exactly `width` cells (`rich.cells.cell_len`, `set_cell_size`). `mark = f"{'▶' if highlighted else ' '} [{'x' if checked else ' '}]"`; `left = f"{mark} {item.key}  {item.title}"`; `right = item.type or EMPTY`; `room = width - cell_len(right) - 1`; if `cell_len(left) > room` then `left = set_cell_size(left, room - 1) + "…"` (`""` when `room <= 0`); then `left + spaces + right` filling to `width` (at least 0 spaces), finally `set_cell_size(result, width)`.
- `target_text(target, ticked)`: `"Open a record to link the ticked ones to it"` when `target` is `None`; else `f"Link {ticked} ticked to {target.get('key') or target['id']} as:"`.
- `build_commands(items, target_id, *, relation, pin, scope, actor)`: one `AddLink(actor=actor, source="tui", scope=scope, from_id=target_id, to_id=item.record_id, relation=relation, pin=pin, link_source="tray")` per item whose `record_id != target_id`, in order.

`ReferenceTrayScreen` (a `ModalScreen[int | None]`; `compose` yields `Static#tray-title`, `TrayList#tray-list`, `Static#tray-target`, `Select#tray-relation`, `Input#tray-pin`, `Static#tray-status`; `__init__` sets `client`, `scope`, `tray`, `target` (a record dict or `None`), `actor`):
- `on_mount`: focus `#tray-list`, then `_draw()`. `_say(text)`: update `#tray-status`.
- `_draw(keep=0)`: `results = #tray-list`; `width = max(results.size.width, 60)`; `highlighted = results.highlighted` if not `None` else `keep`; `items = self.tray.items`; `clear_options()` then `add_options` with `Option(Text(tray_line(i, self.tray.is_checked(i.record_id), n == highlighted, width)), id=i.record_id)` per item (**wrap in `rich.text.Text`**: `[x]` is eaten as markup otherwise); if there are items, `results.highlighted = min(highlighted, len(items) - 1)`; update `#tray-title` with `title_text(self.tray)` and `#tray-target` with `target_text(self.target, len(self.tray.checked_items()))`; with no items `_say("The tray is empty. Press R on a record to add it.")`.
- `_highlighted() -> TrayItem | None`: the tray item at the list's highlighted index, or `None`.
- `action_move(delta)`: list `action_cursor_down()` for `delta > 0` else `action_cursor_up()`, then `_draw(results.highlighted or 0)`.
- `action_toggle_select()`: toggle the highlighted item (`self.tray.toggle(record_id)`), then `_draw(<highlighted index or 0>)`. `action_remove()`: remove the highlighted item from the tray, then `_draw(...)` the same way. `action_clear()`: `self.tray.clear()` then `_draw()`.
- `on_option_list_option_selected(event)`: `event.stop()` then `_link()`.
- `_link()`: with no target `_say("Open a record first: the ticked records link to it")` and return; with no ticked items `_say("Tick at least one record")` and return. `select: Select[str] = self.query_one("#tray-relation", Select)` (do not subscript inside `query_one`); `pin` = the stripped `#tray-pin` value or `None`. `commands = build_commands(self.tray.checked_items(), str(self.target["id"]), relation=str(select.value), pin=pin, scope=self.scope, actor=self.actor)`. Run `self.client.add_link(cmd)` for each; on `CLIENT_ERRORS` collect `f"{key}: {describe_error(exc)}"` (`key` is the item's key, found by `cmd.to_id`) and continue; on success count it and `self.tray.remove(cmd.to_id)`. If nothing was created: `_say("; ".join(messages) or "Nothing to link")` and stay open; else `self.dismiss(created)`.
- `action_close()`: `self.dismiss(None)`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I3/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- No async pytest plugin: tests use `helpers.run_pilot` and `helpers.screen_text`. `Static` and `OptionList` parse `[...]` as markup: use `markup=False` / `rich.text.Text`.
- Do not name an attribute after a Textual DOM property, and do not name a method `action_toggle` (use `action_toggle_select`).
- `uv run ruff format` and `uv run ruff check --fix` before `just check`; ruff limits lines to 100 columns. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- The stub had its unused imports removed; add back what you use (`Text`, `Option`, `cell_len`, `set_cell_size`, `AddLink`, `describe_error`, `EMPTY`, ...).
- Remove the `STUB (P0-I3-T13b)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/widgets/ref_tray.py (existing stub; keep every name and signature)
def tray_line(item: TrayItem, checked: bool, highlighted: bool, width: int) -> str
def title_text(tray: ReferenceTray) -> str        # written
def target_text(target: dict[str, Any] | None, ticked: int) -> str
def build_commands(items: Sequence[TrayItem], target_id: str, *, relation: str, pin: str | None, scope: str, actor: str) -> list[AddLink]
class TrayList(OptionList)                        # written: Space runs screen.toggle_select
class ReferenceTrayScreen(ModalScreen[int | None]):
    def __init__(self, client, scope, tray: ReferenceTray, target: dict[str, Any] | None, *, actor: str = "user:dev") -> None
```
```python
# existing
# tl_tui.tray.TrayItem(record_id, key, type, title) (frozen dataclass);  ReferenceTray: .items (copy), len(), is_checked(id), checked_items(), toggle(id), remove(id), clear()
# ClientInterface: add_link(cmd: AddLink) -> CommandResult;  relations(); default_relation(from_type, to_type)
# AddLink(Command): from_id, to_id, relation, pin, link_source, note       # tl_core.services.links
# tl_tui.errors: CLIENT_ERRORS, describe_error;  tl_tui.text.EMPTY == "—"
```

## Context (read these, nothing else)
- `AGENTS.md`, `packages/tl-tui/AGENTS.md`
- `packages/tl-tui/src/tl_tui/widgets/ref_tray.py`
- `packages/tl-tui/src/tl_tui/widgets/link_picker.py` (a sibling modal with the same row style)
- `packages/tl-tui/tests/fakes.py` and `packages/tl-tui/tests/fakes_links.py` (read only; `FakeClient`)
- `docs/tickets/P0-I3/provided/test_ref_tray.py.txt` (the test you must make pass)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/ref_tray.py` (edit)
- `packages/tl-tui/tests/test_ref_tray.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I3/P0-I3-T13b.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I3/provided/test_ref_tray.py.txt packages/tl-tui/tests/test_ref_tray.py`
2. Implement the functions and methods; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-tui/tests/test_ref_tray.py -q
just check
just test
diff docs/tickets/P0-I3/provided/test_ref_tray.py.txt packages/tl-tui/tests/test_ref_tray.py
```
Expected: 13 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change `app.py`, `tray.py`, the fakes or any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
