# P0-I3-T12 — Link picker modal

Status: ready
Tier: haiku
Labels: tui
Depends on: the TUI wiring commit on the base branch (`TlApp.action_link`, `ClientInterface` link methods, the stub)
Branch: `p0/i3-t12-link-picker`

## Goal
`l` on the grid selection or on the open record opens the link picker: search records, tick one or more with `Ctrl+T`, choose the relation (pre-selected
from the record types) and an optional pin and note, and press Enter to link. `Ctrl+N` creates a new record and links it in place. The app wiring
(`TlApp.action_link`), the types, the layout (`compose`), the constructor, the key bindings, and the relation helpers exist in
`tl_tui/widgets/link_picker.py`; the four pure functions and the methods marked `raise NotImplementedError` are the work. A provided test file
(25 tests) must pass.

## Brief references (pasted)
> **7.2 Link picker (`l`):** Search across types, filter, multi-select, preview, choose relation and pin, or create a new record and link it in place. Creating a link needs read access on the target. **Create-and-link:** new records start linked to their origin.
> **Sketch 4:** title "Link 3 selected welds →"; a line of Relation / Type / Scope / Pin selectors; `Search`; rows `▶ NCR-P123-0042   Bevel damage…   Open   QA   2026-10-07` with a final row "+ Create new NCR and link  Ctrl+N"; a preview line "NCR-P123-0042 · Open · disposition: repair · 6 linked welds"; `Note`; footer "Space select · Enter link · Ctrl+N create & link · Esc cancel". (In this build the tick key is `Ctrl+T` because `Space` types a space in the search box.)

### Specification (the provided test checks it)
Pure functions:
- `title_text(sources)`: `f"Link {sources[0].key} →"` for one source, else `f"Link {len(sources)} selected records →"`.
- `result_line(target, selected, highlighted, width)`: exactly `width` cells (`rich.cells.cell_len`, `set_cell_size`). `mark = f"{'▶' if highlighted else ' '} [{'x' if selected else ' '}]"`; `left = f"{mark} {target.key or EMPTY}  {target.title}"`; `right = target.status or EMPTY`; `room = width - cell_len(right) - 1`; if `cell_len(left) > room` then `left = set_cell_size(left, room - 1) + "…"` (`""` when `room <= 0`); then `left + spaces + right` with the spaces filling to `width` (at least 0), finally `set_cell_size(result, width)`.
- `preview_text(target)`: `"No record highlighted"` for `None`, else `f"{key} · {title} · {status} · {link_total} linked"` with `key = target.key or EMPTY`, `status = target.status or EMPTY`.
- `build_commands(sources, targets, *, relation, pin, note, scope, actor)`: for each source (outer) and each target (inner) whose ids differ, `AddLink(actor=actor, source="tui", scope=scope, from_id=source.id, to_id=target.id, relation=relation, pin=pin, note=note, link_source="manual")`.

`LinkPicker` (a `ModalScreen[LinkPickerResult | None]`; `compose` is written, with these ids: `#picker-title`, `#picker-relation` (a `Select`), `#picker-pin`, `#picker-search`, `#picker-results` (an `OptionList`), `#picker-preview`, `#picker-note`, `#picker-status`). State set in `__init__`: `found: list[LinkTarget]` (the rows shown), `selected: dict[str, LinkTarget]` (ticked, by id; kept across searches), `_manual_relation`, `_setting_relation`. `_relation_options()` and `_default_relation(target)` are written.
- `on_mount`: focus `#picker-search`, then `_search()`.
- `_search()`: `found = self.client.search_linkable(self.scope, <search text>, limit=RESULT_LIMIT)` (on `CLIENT_ERRORS`: `_say(describe_error(exc))` and `found = []`); `self.found` = those whose id is not a source id; then `_draw()`.
- `_draw(keep=0)`: `results = #picker-results`; `width = max(results.size.width, 60)`; `highlighted = results.highlighted` if not `None` else `keep`; `clear_options()`, then `add_options` with one `Option(Text(result_line(t, t.id in self.selected, i == highlighted, width)), id=t.id)` per found target (**wrap in `rich.text.Text`**: `[x]` is eaten as markup otherwise); if any rows, set `results.highlighted = min(highlighted, len(found) - 1)`; then `_on_highlight()`.
- `_highlighted()`: the `LinkTarget` at `results.highlighted`, or `None` (no rows or out of range).
- `_on_highlight()`: update `#picker-preview` with `preview_text(self._highlighted())`; if a target is highlighted and `not self._manual_relation`, `_set_relation(self._default_relation(target))`.
- `_set_relation(code)`: `select: Select[str] = self.query_one("#picker-relation", Select)` (**do not** write `Select[str]` inside `query_one`: it raises at run time); if `select.value != code` set `self._setting_relation = True`, assign `select.value = code` (ignore an exception: a code missing from the options keeps the old value), set it back to `False`.
- `on_input_changed(event)`: when `event.input.id == "picker-search"`, `event.stop()` and `_search()`. `on_select_changed(event)`: `event.stop()`; if not `_setting_relation`, set `_manual_relation = True`. `on_option_list_option_highlighted(event)`: `event.stop()`, `_on_highlight()`. `on_option_list_option_selected(event)`: `event.stop()`, `action_toggle_select()`.
- `action_move(delta)`: move the `OptionList` cursor down/up (`action_cursor_down` / `action_cursor_up`), then `_draw(results.highlighted or 0)`.
- `action_toggle_select()`: toggle the highlighted target in `self.selected`, then `_draw(<current highlighted index or 0>)`.
- `on_input_submitted(event)`: `event.stop()`; `self._link(list(self.selected.values()) or [highlighted target if any])`.
- `_say(text)`: update `#picker-status`.
- `_link(targets)`: no targets → `_say("Choose a record to link")` and return. `relation = str(Select.value)`; `pin` and `note` = the stripped input values or `None` when empty; `commands = build_commands(...)`. Run `self.client.add_link(cmd)` for each; count successes; on `CLIENT_ERRORS` collect `f"{keys[cmd.from_id]} → {keys[cmd.to_id]}: {describe_error(exc)}"` where `keys` maps source ids to source keys and target ids to `key or id`. If nothing was created: `_say("; ".join(messages) or "Nothing to link")` and stay open. Otherwise `self.dismiss(LinkPickerResult(created=created, messages=messages))`.
- `action_create_and_link()`: push `NewRecordForm(self.client, self.scope, actor=self.actor)` (`from tl_tui.widgets.new_record_form import NewRecordForm`, imported inside the method) on `self.app`; its callback receives the new record's key or `None`. For a key: `record = self.client.get_record(self.scope, key)` (if `None`, `_say(f"Created {key} but could not read it back")`), build a `LinkTarget(id, key, type, title, status, scope, link_total=0)` from the record dict and call `_link([target])`.
- `action_cancel()`: `self.dismiss(None)`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I3/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- No async pytest plugin: tests use `helpers.run_pilot` and `helpers.screen_text`. `Static` and `OptionList` parse `[...]` as markup: use `markup=False` / `rich.text.Text`.
- A widget that wraps an `Input` creates it in `compose()`, never `__init__` (already so). Do not name an attribute after a Textual DOM property, and do not name a method `action_toggle` (it overrides a Textual method).
- `uv run ruff format` and `uv run ruff check --fix` before `just check`; ruff limits lines to 100 columns. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- The stub had its unused imports removed; add back what you use (`Text`, `Option`, `cell_len`, `set_cell_size`, `describe_error`, `EMPTY`, `Input`, `Select`, ...).
- Remove the `STUB (P0-I3-T12)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/widgets/link_picker.py (existing stub; keep every name and signature)
RESULT_LIMIT = 20
@dataclass(frozen=True) class PickerSource: id: str; key: str; type: str; title: str     # + classmethod from_record(record) (written)
class LinkPickerResult(BaseModel): created: int; messages: list[str] = []
def title_text(sources: Sequence[PickerSource]) -> str
def result_line(target: LinkTarget, selected: bool, highlighted: bool, width: int) -> str
def preview_text(target: LinkTarget | None) -> str
def build_commands(sources, targets, *, relation: str, pin: str | None, note: str | None, scope: str, actor: str) -> list[AddLink]
class LinkPicker(ModalScreen[LinkPickerResult | None]):
    def __init__(self, client: ClientInterface, scope: str, sources: Sequence[PickerSource], *, actor: str = "user:dev") -> None
```
```python
# existing
# ClientInterface: search_linkable(scope, query, *, record_type=None, exclude_id=None, limit=20) -> list[LinkTarget];  relations() -> list[RelationInfo];
#   default_relation(from_type, to_type) -> str;  add_link(cmd: AddLink) -> CommandResult;  get_record(scope, key) -> dict | None
# LinkTarget: id, key (str | None), type, title, status (str | None), scope, link_total        # tl_core.services.link_queries
# AddLink(Command): from_id, to_id, relation, pin, link_source, note                           # tl_core.services.links
# tl_tui.errors: CLIENT_ERRORS, describe_error(exc) -> str;  tl_tui.text.EMPTY == "—"
# tl_tui.widgets.new_record_form.NewRecordForm(client, scope, *, record_type="core.Record", actor="user:dev") -> ModalScreen[str | None]
```

## Context (read these, nothing else)
- `AGENTS.md`, `packages/tl-tui/AGENTS.md`
- `packages/tl-tui/src/tl_tui/widgets/link_picker.py`
- `packages/tl-tui/src/tl_tui/widgets/new_record_form.py` (style of a modal that creates)
- `packages/tl-tui/tests/fakes.py` and `packages/tl-tui/tests/fakes_links.py` (read only; `FakeClient`)
- `docs/tickets/P0-I3/provided/test_link_picker.py.txt` (the test you must make pass)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/link_picker.py` (edit)
- `packages/tl-tui/tests/test_link_picker.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I3/P0-I3-T12.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I3/provided/test_link_picker.py.txt packages/tl-tui/tests/test_link_picker.py`
2. Implement the four functions and the methods; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-tui/tests/test_link_picker.py -q
just check
just test
diff docs/tickets/P0-I3/provided/test_link_picker.py.txt packages/tl-tui/tests/test_link_picker.py
```
Expected: 25 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change `app.py`, the fakes, `new_record_form.py` or any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
