# P0-I2-T14 — Record view: header, Details and History tabs

Status: ready
Tier: haiku
Labels: tui
Depends on: P0-I2-T11, P0-I2-T12 skeleton (all merged on `p0/i2b`; this ticket does not need T12/T12b/T13b to land)
Branch: `p0/i2b-t14-record-view`

## Goal
Pressing Enter on a grid row opens a record view: a two-line header (key, title, status, version, conformance) over tabs
Details · Psets · History. Details lists the envelope fields; History lists the record's ledger events newest first;
Psets hosts the existing `PsetsTab` stub (a later ticket fills it). Esc goes back, `[` and `]` step to the previous and
next record, `h` jumps to History, and a `RecordChanged` message reloads the view. `RecordView` exists as a stub with
its final constructor; this ticket replaces its content.

## Brief references (pasted)
> Record view: Header (key, title, status, badges, workflow actions), tabs: Details · Psets · Links · Files · Thread (if enabled) · Feed · History · Trace  (§10.2)
> Keys: `Esc` Back / close overlay · `Enter` Open record · `[` / `]` Previous / next record in current list · `h` History  (§10.4)
> History and audit come from the ledger.  (§4)
> Meaning never rides on colour alone: pair status with a symbol (§10.3).

Sketch 2 (§10.6), header and tab bar (this increment shows Details, Psets and History only):
```text
┌─ 47-FV-1001 · Control valve · FCV on 6"-P-1234-A1 discharge ─────────── Design ▸ [w] transition ─┐
│ Details   [Psets]   Links 14   Files 3   Feed 6   History 23   Trace   Model                     │
```

Learnings that apply:
- `uv` prints a harmless "UV_NATIVE_TLS is deprecated" warning on every call; ignore it.
- ruff `E501` is 100 columns, docstrings and comments included. Before `just check`, run
  `uv run ruff format packages/tl-tui` and `uv run ruff check --fix packages/tl-tui`.
- Textual `Static` parses `[...]` as markup and record text can contain brackets: every `Static` here takes `markup=False`,
  and every `DataTable` cell is a `rich.text.Text` object.
- Do not name an attribute after a Textual `Widget` attribute (`visible`, `size`, `region`, `id`...).
- A screen never imports `tl_core.services` handlers or SQL: read through `self.client` only. Catch `CLIENT_ERRORS`, post
  `StatusMessage(describe_error(exc), "error")`, and keep the previous state.
- Tests have no async plugin: use `helpers.run_pilot` and `helpers.screen_text`.
- The key names for `[` and `]` in a Textual `Binding` are `left_square_bracket` and `right_square_bracket`.

## Interfaces (verbatim from repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/widgets/record_view.py  (stub today; keep this constructor)
class RecordView(Vertical, can_focus=True):
    def __init__(self, client: ClientInterface, scope: str, key: str, *, id: str | None = None) -> None: ...
    # attributes: client, scope, key, record (dict | None, set by reload)
# NEW in record_view.py
def details_text(record: dict[str, Any]) -> str: ...
def event_summary(event: Event) -> str: ...
# on RecordView: def reload(self) -> None   (re-reads the record and its history and redraws everything)

# packages/tl-tui/src/tl_tui/client.py (existing)
class ClientInterface(Protocol):
    def get_record(self, scope: str, key: str) -> dict[str, Any] | None: ...
    def history(self, record_id: str) -> list[Event]: ...   # oldest first

# packages/tl-tui/src/tl_tui/widgets/psets_tab.py (existing stub; use as is)
class PsetsTab(VerticalScroll, can_focus=True):
    def __init__(self, client: ClientInterface, scope: str, *, id: str | None = None) -> None: ...
    def show_record(self, record: dict[str, Any]) -> None: ...

# packages/tl-tui/src/tl_tui/messages.py (existing)
class CloseRecord(Message): ...
class StepRecord(Message):  def __init__(self, delta: int) -> None
class RecordChanged(Message):  def __init__(self, record_id: str) -> None   # .record_id
class StatusMessage(Message):  def __init__(self, text: str, severity: Severity = "info") -> None

# packages/tl-tui/src/tl_tui/errors.py (existing)
CLIENT_ERRORS: tuple[type[Exception], ...];  def describe_error(exc: BaseException) -> str

# packages/tl-tui/src/tl_tui/text.py (existing)
EMPTY = "—"; def short_hash(v: str | None) -> str; def timestamp(v: str | None) -> str; def conformance_mark(v: str | None) -> str

# Event (tl_core.ledger.Event) fields you use: event_id, event_type, stream_version, actor, recorded_at (datetime), payload (dict)
```
Record envelope keys: `id, key, type, scope, title, description, status, psets, voided, version, last_seq,
effective_schema_hash, conformance, created_at, updated_at`.

Layout and ids (the provided test queries these):
- `Static` id `rv-header` (2 lines, `markup=False`):
  line 1 `f"{key} · {title}"`; line 2 `f"{status or '—'} · v{version} · {conformance_mark(conformance)}"` plus `" · voided"` when `voided`.
  When the record is not found: `f"{self.key} · not found"` and post `StatusMessage(f"No record {self.key}", "error")`.
- `TabbedContent` id `rv-tabs`, `initial="tab-details"`, with `TabPane("Details", id="tab-details")`, `TabPane("Psets", id="tab-psets")`,
  `TabPane("History", id="tab-history")`.
- Details pane: a `VerticalScroll` holding a `Static` id `rv-details` showing `details_text(record)`.
- Psets pane: `PsetsTab(self.client, self.scope, id="psets-tab")`; call its `show_record(record)` after each successful reload.
- History pane: `DataTable[Text]` id `rv-history`, `cursor_type="row"`, columns `"#", "When", "Event", "Actor", "Summary"` (added in `on_mount`).
  One row per event, newest first (`reversed(events)`), cells `Text(str(stream_version))`, `Text(recorded_at.strftime("%Y-%m-%d %H:%M:%S"))`,
  `Text(event_type)`, `Text(actor)`, `Text(event_summary(event))`, row key `event_id`. `reload` clears the table first.
- `on_mount` adds the columns and calls `reload()`.

`details_text(record)`: eleven lines, each `f"{label:<13}{value}"`, in this order:
`Key` key · `Type` type · `Title` title · `Description` description or `—` · `Status` status or `—` · `Scope` scope · `Version` version ·
`Created` `timestamp(created_at)` · `Updated` `timestamp(updated_at)` · `Conformance` `conformance_mark(conformance)` · `Schema` `short_hash(effective_schema_hash)`.

`event_summary(event)` by `event_type` (use `.get` with empty defaults; sort lists alphabetically):
- `Record.Created` -> `created: {title}` · `Record.Updated` -> `changed: {comma-separated keys of payload["changes"]}` ·
  `Record.Corrected` -> `corrected: {same}` · `Record.Voided` -> `voided: {reason}` ·
  `Pset.ValuesSet` -> `{pset} ({layer}): {comma-separated keys of payload["values"]}` · any other type -> `""`.

Behaviour:
- Bindings (all `show=False`): `escape` posts `CloseRecord()`; `left_square_bracket` posts `StepRecord(-1)`;
  `right_square_bracket` posts `StepRecord(1)`; `h` sets `rv-tabs.active = "tab-history"`.
  `KEY_HINTS: ClassVar[str] = "Esc back  [ ] prev/next  h history"`.
- `reload()`: `record = client.get_record(scope, key)`; `events = client.history(record["id"])` when found, else `[]`. On `CLIENT_ERRORS`
  post `StatusMessage(describe_error(exc), "error")` and return without touching the display.
- `on_record_changed(message)`: when `self.record` is set and `message.record_id == self.record["id"]`, call `reload()`; ignore other ids.
  Do not stop the message (it must keep bubbling so the app can refresh the grid).

## Context (read these, nothing else)
- `AGENTS.md`, `packages/tl-tui/AGENTS.md`
- `packages/tl-tui/src/tl_tui/widgets/record_view.py`
- `packages/tl-tui/src/tl_tui/widgets/main_area.py` and `packages/tl-tui/src/tl_tui/app.py` (read only: how the app mounts the view)
- `packages/tl-tui/tests/fakes.py` (read only; `FakeClient`, seeded data used by the test)
- `docs/tickets/P0-I2/provided/test_record_view.py.txt` (the test you must make pass)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/record_view.py` (edit: replace the stub content)
- `packages/tl-tui/tests/test_record_view.py` (create by copying the provided file; do not edit it)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_record_view.py.txt packages/tl-tui/tests/test_record_view.py`
2. Implement `details_text`, `event_summary`, and `RecordView` as specified.
3. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_record_view.py -q
uv run pytest packages/tl-tui -q
```
Expected: all pass (`test_app_shell.py::test_open_close_and_step_records` must still pass unchanged).

## Tests to add
None beyond the provided file. It covers `details_text` and `event_summary` output, header/tabs/history ordering, `h`, the
three messages, the not-found path, reload on `RecordChanged` with literal brackets, and open/step/close through `TlApp`.

## Report requirements
Standard report. State that the provided test file is byte-identical to the `.txt`.

## Escalation triggers
- Stop and report *Blocked* if a provided test cannot pass without changing a file outside *Allowed paths*.
- Stop if `PsetsTab` (the stub) lacks something you need: do not edit it; a later ticket owns it.

## Blocked

## Decision
