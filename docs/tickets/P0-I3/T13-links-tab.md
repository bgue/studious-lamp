# P0-I3-T13 — Links tab

Status: ready
Tier: haiku
Labels: tui
Depends on: the TUI wiring commit on the base branch (the record view hosts `LinksTab`; the stub; `ClientInterface` link methods)
Branch: `p0/i3-t13-links-tab`

## Goal
The record view's Links tab shows every link of the record in both directions, grouped by relation, with suggestions last and one line per
expected-but-missing link below; keys act on the highlighted link (follow, accept, decline, re-pin, verify, retract). The tab is mounted by
`RecordView`, which calls `show_record(record)` and relies on `highlighted_other()` (the app's `R` key). `tl_tui/widgets/links_tab.py` has the
layout (`compose`), constructor, attributes, key bindings and focus handling; the five pure functions and the methods marked
`raise NotImplementedError` (plus two lines marked `STUB`) are the work. A provided test file (17 tests) must pass.

## Brief references (pasted)
> **7.4 Links tab:** inbound and outbound links grouped by relation and type with counts, plus expected-but-missing, suggestions, and external references. Chips show status as colour **and** text/symbol.
> **7.3:** Pinned links go `stale` when a new revision is issued; **Re-pin** shows what changed. Suggested links wait for accept or decline; **declines are remembered**. **Verification:** people can mark links verified. **Retract, never delete**, with a reason.
> **Sketch 12** (the tab body): `▾ requires (3)` then rows `MR-0221  Material requisition  Open  ✓ verified`; `ISO-1236 rB  ▪ pinned  ! rC issued 10-08 [u] re-pin`; `▸ suggested (2)  47-FV-1002 (enricher 0.82)  [a] accept`; `! expected but missing: permit-to-work (rule: IWP@Issued)`; footer "Enter follow · l link · R add to tray · u re-pin · v verify · x retract · t trace".

### Specification (the provided test checks it)
Pure functions (module level; `LinkView`, `MissingLink` are in the interfaces below):
- `status_text(view)`: `suggested` → `f"? suggested ({view.confidence:.2f})"` (or `"? suggested"` when `confidence` is `None`); `active` → `"✓ verified"` if `view.verified_by` else `"active"`; `stale` → `"! stale"`; `broken` → `"✗ broken"`; anything else (retracted) → `"declined"` if `view.declined` else `"retracted"`.
- `pin_text(view)`: `"floating"` when `view.pin is None`, else `f"▪ {view.pin}"`. `group_title(label, count)`: `f"▾ {label} ({count})"`.
- `missing_line(missing)`: `rule = expectation.relation`, plus `f"@{expectation.by_state}"` if it has a `by_state`, plus `f", {missing.found} of {missing.needed}"` if `missing.needed > 1`; the line is `f"! expected but missing: {expectation.display} (rule: {rule})"`.
- `build_rows(views) -> list[TableRow]` (`TableRow(link_id, cells)` is written). Links whose status is not `suggested` are grouped by `(direction, relation)` in the order given. For each group: a header row `TableRow(None, (group_title(first_view.label, len(group)), "", "", "", "", ""))`, then per link `TableRow(view.link_id, ("", view.other_key or EMPTY, view.other_title, status_text(view), pin_text(view), view.note or ""))`. Suggested links form one last group: header `group_title("suggested", n)` (same six-cell shape), and their rows have the **label** (`view.label`) as first cell instead of `""`.

`LinksTab` (a `Vertical`; `compose` yields `DataTable#links-table`, `Static#links-missing`, `Static#links-note`; `on_mount` adds the `COLUMNS`; `on_focus` moves focus to the table):
- `show_record(record)` (**edit the `STUB` line**): store `record` and call `self.reload()`.
- `reload()`: return if no record. `views = self.client.links_of(record["id"])` and `missing = self.client.expected_links(record["id"])`. On `NotImplementedError`: `_note("Links unavailable: the link services are not installed yet")` and return. On `CLIENT_ERRORS`: `self.post_message(StatusMessage(describe_error(exc), "error"))` and return (keep what is shown). Then `self.views = {v.link_id: v for v in views}`; remember `table.cursor_row`; `table.clear()`; add one row per `build_rows(views)` entry with `table.add_row(*(Text(cell) for cell in row.cells), key=row.link_id or f"group:{n}")` (**cells must be `rich.text.Text`**: `[...]` in a plain string is markup); restore the cursor with `table.move_cursor(row=keep)` when there are views and `keep` is in range; set `#links-missing` to the `missing_line` of each missing link joined by newlines; `_note("" if views else "No links yet. Press l to link this record.")`.
- `_note(text)`: store it in `self.text` and update `#links-note`.
- `_highlighted() -> LinkView | None`: `None` when the table has no rows; else the view whose id is the row key of the cursor row (`table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value`); group header rows give `None` (their keys are not link ids).
- `highlighted_other()` (**edit the `STUB` return**): for the highlighted view, `{"id": other_id, "key": other_key, "type": other_type, "title": other_title}`, else `None`.
- `on_data_table_row_selected(event)`: `event.stop()` then `action_follow()`. `action_follow()`: for a highlighted view with an `other_key`, `self.post_message(OpenRecord(self.scope, view.other_key, follow=True))`.
- `_need_link()`: the highlighted view, or post `StatusMessage("Highlight a link first", "warning")` and return `None`.
- `_run(call, done)`: call `call()`; on `CLIENT_ERRORS` post `StatusMessage(describe_error(exc), "error")` and return; otherwise post `StatusMessage(done, "info")` and, if a record is shown, `RecordChanged(str(self.record["id"]))`.
- `action_accept`: needs a link; `AcceptLink(actor=self.actor, source="tui", scope=self.scope, link_id=view.link_id, expected_version=view.version)` → `self.client.accept_link(cmd)`; done text `f"Accepted link to {view.other_key}"`. `action_verify`: the same with `VerifyLink` / `client.verify_link` / `f"Verified link to {view.other_key}"`.
- `action_decline`: needs a link; `self.app.push_screen(PromptScreen("Decline suggestion", "Reason (optional)", required=False), decided)`; `decided(reason)` returns on `None`; else `DeclineLink(..., reason=reason or None)` → `client.decline_link`; done `f"Declined {view.other_key}"`.
- `action_repin`: needs a link; `PromptScreen("Re-pin link", "New pin (blank: floating to the current revision)", initial=view.pin or "", required=False)`; `decided(pin)` returns on `None`; else `RepinLink(..., pin=pin or None)` → `client.repin_link`; done `f"Re-pinned link to {view.other_key}"`.
- `action_retract`: needs a link; `PromptScreen("Retract link", "Reason")` (reason required); `decided(reason)` returns on `None`; else `RetractLink(..., reason=reason)` → `client.retract_link`; done `f"Retracted link to {view.other_key}"`.
Every command above passes `expected_version=view.version`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I3/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- No async pytest plugin: tests use `helpers.run_pilot` and `helpers.screen_text`. `Static`, `OptionList` and `DataTable` cells parse `[...]` as markup: use `markup=False` / `rich.text.Text`.
- Do not name an attribute after a Textual DOM property. `uv run ruff format` and `uv run ruff check --fix` before `just check`; ruff limits lines to 100 columns. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- The stub had its unused imports removed; add back what you use (`Text`, `describe_error`, `CLIENT_ERRORS`, `PromptScreen`, the command classes, `OpenRecord`, `RecordChanged`, `StatusMessage`, `EMPTY`).
- Remove the `STUB (P0-I3-T13)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/widgets/links_tab.py (existing stub; keep every name and signature)
COLUMNS = ("", "Key", "Title", "Status", "Pin", "Note"); SUGGESTED = "suggested"
@dataclass(frozen=True) class TableRow: link_id: str | None; cells: tuple[str, ...]
def status_text(view: LinkView) -> str; def pin_text(view: LinkView) -> str; def group_title(label: str, count: int) -> str
def missing_line(missing: MissingLink) -> str; def build_rows(views: Sequence[LinkView]) -> list[TableRow]
class LinksTab(Vertical, can_focus=True):
    def __init__(self, client, scope, *, actor="user:dev", id=None)      # .client .scope .actor .record (dict | None) .views (dict) .text (str)
    def show_record(self, record: dict[str, Any]) -> None; def reload(self) -> None; def highlighted_other(self) -> dict[str, Any] | None
```
```python
# existing
# LinkView (tl_core.services.link_queries): link_id, direction ("out"|"in"), relation, label, other_id, other_key (str | None), other_title, other_type,
#   other_status, other_voided, status, pin, note, source, confidence (float | None), reason, declined (bool), verified_by, verified_at, created_at, version
# MissingLink (tl_core.links.expected): expectation: ExpectedLink (.relation .by_state .display), found: int, needed: int
# ClientInterface: links_of(record_id, *, include_retracted=False) -> list[LinkView]; expected_links(record_id) -> list[MissingLink];
#   accept_link / decline_link / repin_link / verify_link / retract_link(cmd) -> CommandResult
# Commands (tl_core.services.links): AcceptLink / DeclineLink(reason) / RepinLink(pin) / VerifyLink / RetractLink(reason) — each Command(actor, source, scope) + link_id, expected_version
# tl_tui.messages: OpenRecord(scope, key, *, follow=False), RecordChanged(record_id), StatusMessage(text, severity)
# tl_tui.widgets.prompt.PromptScreen(title, label, *, initial="", required=True) -> ModalScreen[str | None]   (dismisses with the stripped text, or None on Esc)
```

## Context (read these, nothing else)
- `AGENTS.md`, `packages/tl-tui/AGENTS.md`
- `packages/tl-tui/src/tl_tui/widgets/links_tab.py`
- `packages/tl-tui/src/tl_tui/widgets/record_view.py` (read only; how the tab is mounted and refreshed)
- `packages/tl-tui/tests/fakes.py` and `packages/tl-tui/tests/fakes_links.py` (read only; `FakeClient`)
- `docs/tickets/P0-I3/provided/test_links_tab.py.txt` (the test you must make pass)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/links_tab.py` (edit)
- `packages/tl-tui/tests/test_links_tab.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I3/P0-I3-T13.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I3/provided/test_links_tab.py.txt packages/tl-tui/tests/test_links_tab.py`
2. Implement the functions and methods and the two `STUB` lines; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-tui/tests/test_links_tab.py -q
just check
just test
diff docs/tickets/P0-I3/provided/test_links_tab.py.txt packages/tl-tui/tests/test_links_tab.py
```
Expected: 17 tests pass, `just check` and `just test` exit 0 (all existing record-view and snapshot tests must still pass), `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change `record_view.py`, `app.py`, the fakes or any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
