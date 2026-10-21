# P1-UX-T03 — Correspondence register, inbox, clocks: Enter opens the record screen, plain text, item and clock Details

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: T00, S2, S3 (merged)
Branch: `p1/ux-t03-correspondence-screen`

## Goal
In the correspondence screen (F5) Enter on a row of the register, the triage inbox or the clocks view opens the full record screen;
Esc returns on the same row. The Details tab of a correspondence item and of a response clock show labelled fields (new
`details/correspondence.py`). Plain mode shows `Letter`, not `general/letter`; no clock key, calendar id or version (`P123-default@1`),
no `user:` or `svc:` ids; technical mode adds them. RFI and commercial items opened from the register get the generic rows until T04/T05.

## Brief references (pasted)
> SCOPE clause 1: Enter on any row (correspondence register, triage inbox, clocks) opens the full record view; Esc returns on the same row.
> Clause 2: domain labels, not internal keys (`Letter`, not `general/letter`); hidden: clock ids, calendar ids and versions, actor ids.
> Clause 3: technical mode shows what plain hides. D14: define `refresh_for_display_mode(self) -> None`. D21 (supervisor): plain clock rows
> lead with the item number under `Item`; technical leads with the clock key under `Clock` (today's cell).
> Learning (S2): a `DataTable` consumes Enter before a screen binding; use `DataTable.RowSelected`, never a priority binding.
> S2 getter table: `get_correspondence(project, key)` key = number; `get_clock(project, record["id"])` takes the record id (the clock key is not the number).

## Interfaces (verbatim from repo)
```python
# tl_tui/widgets/record_screen.py (merged)
def open_record(screen: Screen[Any], client: ClientInterface, scope: str, project: str, actor: str, record_id: str) -> None
# tl_tui/details/__init__.py (merged)
@dataclass(frozen=True) class DetailRow: label: str; value: str; technical: bool = False
DetailRenderer = Callable[[ClientInterface, str, dict[str, Any], Labels], list[DetailRow]]   # (client, project, record, labels)
def register(*record_types: str) -> Callable[[DetailRenderer], DetailRenderer]
# tl_tui/details/generic.py: technical_rows(record) -> list[DetailRow]; details/documents.py is the model to follow
# tl_tui/display.py: domain_label(labels, domain, subtype=None) -> "Letter" (subtype label, else humanized subtype; domain label when no subtype; "—" none)
#   code_label(labels, list_name, code), humanize(name), actor_label(labels, actor), type_label, mode_of(app).technical
# tl_tui/labels_load.py: load_labels(client, scope, record_types=...) -> Labels (fills domains/subtypes from list_correspondence_domains; never raises)
# tl_tui/correspondence_text.py (today)
REGISTER_COLUMNS = ("Number", "State", "Dir", "Domain", "Date", "With", "Due", "Subject")
CLOCK_COLUMNS = ("Clock", "State", "Due", "Left", "Days", "Type", "Label")
def register_cells(line: RegisterLineView) -> tuple[str, ...]   # where = line.domain or "-"; += f"/{line.subtype}"; state raw; subject + f" [{kind}]" for non-items
def clock_cells(clock: ClockView) -> tuple[str, ...]            # (clock.key, effective_state, due_on, left, f"{n} {day_type[:3]}", kind.replace("_"," "), label)
def clock_line(clock: ClockView) -> str   # f"{key} {state} due {due} left {left} ({n} {day_type} days, calendar {clock.calendar}) {label}"
def suggestion_text(found: SuggestionView) -> str   # f"{domain}/{subtype or '-'} (score {score})" + reasons
def item_lines(item: ItemView, suggestion=None) -> list[str]    # line 1 "{number}  {state}  {direction}  {medium}  class {confidentiality}";
#   line 5 f"domain {item.domain or '-'}/{item.subtype or '-'}  thread ...  answers ..."; clocks via clock_line
def clock_lines(clock: ClockView) -> list[str]   # clock_line, "item {item_number} ... restarts", "owner {clock.owner}"
# ClockView: id key item_id item_number label kind start_on duration_days day_type calendar due_on state effective_state days_left owner restarts problem
# widgets/correspondence_screen.py (today): CorrespondenceScreen(client, project, actor, *, is_controller, mode); table "#corr-table" (row key = line/clock id);
#   self.lines / self.clocks; reload() rebuilds columns + rows (register_cells / clock_cells); _describe() uses item_lines / clock_lines; _key()
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/correspondence_screen.py`, `correspondence_text.py`
- `packages/tl-tui/src/tl_tui/details/documents.py` (the model), `details/generic.py`
- `packages/tl-tui/tests/test_correspondence_text.py`, `test_correspondence_screen.py`, `test_record_screen.py` (Enter/Esc pattern, lines 1-120)
- `packages/tl-tui/tests/fakes_correspondence.py` (read-only: `seed_correspondence` ids `ID-<number>`, clock `CLK-1`, line `TRN-1`; `seed_domains`)
- `packages/tl-tui/tests/fakes.py` (`FakeClient.add_stored_record`, new: registers a record under a view's id so Enter finds it)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/correspondence_screen.py`, `packages/tl-tui/src/tl_tui/correspondence_text.py`
- `packages/tl-tui/src/tl_tui/details/correspondence.py` (create)
- `packages/tl-tui/tests/test_correspondence_text.py`, `test_correspondence_screen.py` (update pinned expectations only)
- `packages/tl-tui/tests/test_correspondence_plain.py` (create)
- `docs/reports/P1-UX/T03.md` (create)

## Steps
1. `correspondence_text`: functions that print a domain, code or actor take `labels: Labels | None = None` and `technical: bool = False` where noted.
   `register_cells(line, labels=None)`: Domain = `domain_label(labels, line.domain, line.subtype)`, State via `humanize`, Dir `in`/`out`/`int` unchanged.
   `CLOCK_COLUMNS` stays the technical tuple; add `PLAIN_CLOCK_COLUMNS = ("Item", "State", "Due", "Left", "Days", "Type", "Label")`;
   `clock_cells(clock, *, technical=False)`: first cell `clock.item_number` (plain) or `clock.key` (technical); State via `humanize`.
   `clock_line(clock, *, technical=False)`: drop the key and `, calendar {…}` in plain mode (they come back when `technical`).
   `suggestion_text(found, labels=None)`: `Letter (score 4): …` via `domain_label`. `item_lines(item, suggestion=None, labels=None, *, technical=False)`:
   domain line via `domain_label`, class via `code_label(labels, "confidentiality", …)`, state `humanize`; a `record {item.id}` line only when `technical`.
   `clock_lines(clock, labels=None, *, technical=False)`: owner via `actor_label`.
2. Screen: `on_mount` sets `self.labels = load_labels(self.client, f"project:{self.project}", ("correspondence.Correspondence",))`; `reload()` and
   `_describe()` read `technical = mode_of(self.app).technical` and pass it and `self.labels`; the clocks table uses the plain or technical columns.
3. Add `on_data_table_row_selected(self, event)`: `event.stop()`; the row is `self.clocks[event.cursor_row]` in clocks mode, else `self.lines[event.cursor_row]`
   (guard the index); `open_record(self, self.client, f"project:{self.project}", self.project, self.actor, row.id)`. The id of a transmittal line is its record id.
4. Add `refresh_for_display_mode(self) -> None`: `self.reload()` (keeps the row; this re-reads once, acceptable).
5. `details/correspondence.py`: `@register("correspondence.Correspondence")` reads `client.get_correspondence(project, str(record["key"]))`; rows Type, Number,
   Subject, Domain (`domain_label`), State, Direction, Medium, From, To (names, else email), Copy (only if any), Received, Sent, Issued, Confidentiality (`code_label`),
   `Answer expected by` / `Answered on` (only if `response_required`), Thread (`thread_number`), `Replies to` (`responds_to_number`), `Triaged on`, Created, Updated, then
   `technical_rows(record)` and technical-only rows `Received via`, `External reference`. `@register("correspondence.ResponseClock")` reads
   `client.get_clock(project, str(record["id"]))`; rows Type, Item, Label, Kind (`humanize`), State, Started, Due, Days left, Length, Warns (days before), Owner, `Problem` (only if set),
   technical-only rows `Clock key`, `Calendar`, `Restarts`, then `technical_rows(record)`.
6. Update existing pinned expectations (`document_control/transmittal`, `P123-COR-0003-C01`, `calendar P123-default@1`, `general/letter`) to the plain words; keep one technical assertion each.

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_correspondence_text.py packages/tl-tui/tests/test_correspondence_screen.py packages/tl-tui/tests/test_correspondence_plain.py packages/tl-tui/tests/test_details_registry.py packages/tl-tui/tests/test_record_screen.py
```
Gate paths: all exist at dispatch except `test_correspondence_plain.py` (new, this ticket creates it). Expected: `gate: PASS`. No snapshot test shows this screen. Do not run the whole suite.

## Tests to add
`packages/tl-tui/tests/test_correspondence_plain.py` (TlApp on `FakeClient`, `seed_correspondence(client)` and `seed_domains(client)`; for Enter use
`client.add_stored_record(<view id>, <number or clock key>, "correspondence.Correspondence" | "correspondence.ResponseClock", <title>)`; a clock record's `id` is `CLK-1`):
- `test_enter_on_a_register_row_opens_the_item_and_escape_returns_to_the_same_row`.
- `test_enter_in_the_inbox_and_in_the_clocks_view_opens_the_record_screen` (modes 2 and 3).
- `test_a_row_the_viewer_cannot_read_opens_as_no_record` (no stored record; no id in the text).
- `test_plain_text_has_domain_labels_and_no_clock_key_or_calendar` (`Letter`; none of `general/letter`, `P123-COR-0003-C01`, `P123-default@1`, `user:`; `find_technical(text, labels) == []` in register, inbox, clocks and the item panel).
- `test_technical_mode_restores_the_clock_key_and_the_calendar_and_back` (flag on, `refresh_for_display_mode()`, then off).
- `test_the_item_and_clock_renderers_give_labelled_rows` (call `details_for` with the stored record dicts; labels present, no `Calendar`/`Clock key` row in plain, both in technical).

## Report requirements
Standard report. List existing assertions changed and why (one line each).

## Escalation triggers
- `add_stored_record` does not make the record screen open (fix would be in `fakes.py`): stop.
- `get_clock` in the fake does not accept a record id: report; do not change the fake file.
- Plain text still shows an id, hash, `x@1.2.3` or `svc:`: list it; fix only inside Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
