# P1-UX-S2 — Record screen for module types, Details registry, Properties for every type

Status: ready (dispatch after S3 merged: needs generated type_labels.py)
Tier: sonnet
Kind: piece
Review: full
Labels: tui, api, tests
Depends on: T00 (display helper), S3 (type labels, example sets)
Branch: `p1/ux-s2-record-screen`

## Goal
Any register can open the full record screen from a row with one call, and the screen shows labelled Details and a
working Properties tab for module record types. Hidden looks like missing. After this piece the screen tickets
(T01-T09) only add an Enter binding, plain text and one Details module each.

## Brief references (pasted, abridged)
> SCOPE clause 1: Enter on any row opens the full record view with the tabs Details, Properties, Links, History and
> Thread. Details shows the module's own fields (side table, ADR-0010) with labels. Properties shows the sets that
> apply to the record's type (the Phase 0 psets tab). Escape returns to the list on the same row.
> ADR-0016: a hidden record answers as one that never existed; `get_record_by_id` already filters by the viewer.
> ADR-0010 decision 5: a record's class can bind sets; `psets.form_metadata(uow, scope, record_type, record_id)`
> takes the record id, the TUI client and `GET /schema/forms` do not pass it.
> Decisions D1, D2, D6 of the plan README.

## Interfaces
```python
# tl_tui/widgets/record_screen.py (new)
class RecordScreen(ModalScreen[None]):
    def __init__(self, client, scope: str, project: str, record_id: str, actor: str) -> None
    # hosts RecordView(client, scope, key). Esc and CloseRecord -> self.dismiss(None) (not pop_screen, L-P1-I8-15).
    # OpenRecord with follow=True (Links, Trace tabs) re-targets the hosted view; the app's own handler is not reached.
    # StepRecord is ignored (no neighbour list). Hidden or unknown id: shows "No record" with no id in the text.

def open_record(screen: Screen, client, scope, project, actor, record_id: str) -> None
    # the one call a register makes on Enter: screen.app.push_screen(RecordScreen(...))

# tl_tui/details/__init__.py (new package)
@dataclass(frozen=True)
class DetailRow: label: str; value: str; technical: bool = False   # technical rows only in technical mode
DetailRenderer = Callable[[ClientInterface, str, dict[str, Any], Labels], list[DetailRow]]  # (client, project, record, labels)
def register(*record_types: str) -> Callable[[DetailRenderer], DetailRenderer]
def details_for(client, project, record, labels, mode: DisplayMode) -> list[DetailRow]
    # imports every module of the package once (pkgutil), picks by record["type"], else generic_rows(record, labels)
# tl_tui/details/generic.py (new): envelope rows with labels: Type (type_label), Title, Status, Created, Updated,
#   Conformance; technical rows: Key, Version, Scope, Schema hash.
# tl_tui/details/documents.py (new, the one bespoke renderer, extended by T01): Document rows from
#   client.get_document(project, record["key"]) with labels. Every other type stays on generic rows here (F12).

# Labels loader (new, in tl_tui/labels_load.py): load_labels(client, scope) -> Labels
#   type_titles from tl_schema.generated.type_labels.TYPE_LABELS; code_labels from the effective schema's
#   code lists (existing client reads: form_metadata enum_values); domains and subtypes from
#   client.list_correspondence_domains(project); services from the accounts/agents the client can list (empty on error).

# ClientInterface.form_metadata gains an optional trailing argument, nothing else changes:
def form_metadata(self, scope: str, record_type: str, record_id: str | None = None) -> FormMetadata
```
API: `GET /schema/forms` (routes/reference.py `get_form_metadata`, operation `get_form_metadata`) gains optional
query `record_id`; it calls `psets.form_metadata(uow, scope, record_type, record_id)` only when the record is
visible to the viewer, otherwise exactly as without. Response shape unchanged. The remote client (`tl_api/client/links.py`, reached by `RemoteClient` via `__getattr__`) sends the
parameter, with a client test that the query carries `record_id`; embedded passes it; `tests/fakes.py` accept it.

Display mode (D10, r3): technical mode is read with `mode_of(widget)` from `tl_tui.display`, which reads `app.display_mode`
(never `app.display`: Textual owns it). T00 is merged; T10 adds the app attribute and the key. Any widget that renders
mode-dependent text defines `refresh_for_display_mode(self) -> None` (re-render with the current mode, keep the cursor/tab);
T10's toggle calls it on every widget of every screen in the stack that has it. `RecordView` and `RecordScreen` define it
(Details and Properties re-render). Tests set `app.display_mode = DisplayMode()` and `.technical = True` directly.
`display.py` is not touched by S2 (the T00 LO nit F1, find_technical dedupe, rides T10).

Record view changes (`widgets/record_view.py`): the tab label "Psets" becomes "Properties"; `PsetsTab` passes
`record["id"]`; `details_text` is replaced by `details_for` rows (plain by default, technical rows only when
`mode_of(self).technical`); the Properties tab also takes over the words that belong to it (plan check F2): the rule
column uses `rule_phrase` (no `required@Design/Installed`), the group header uses `pset_label` (no `name@version`),
and the `Effective schema #…` line (psets_tab.py:84) shows only in technical mode; `TABS` keys stay (`psets`) so key bindings and tests keep working.

## Context (≤ 10 files)
- `packages/tl-tui/src/tl_tui/widgets/record_view.py`, `psets_tab.py`
- `packages/tl-tui/src/tl_tui/client.py` (form_metadata, get_record_by_id), `embedded.py`, `remote.py`
- `packages/tl-api/src/tl_api/client/links.py` (`form_metadata`, line ~148; `RemoteClient` reaches it through `__getattr__`, remote.py:240)
- `packages/tl-api/src/tl_api/routes/reference.py` (lines 70-100)
- `packages/tl-tui/src/tl_tui/display.py` (T00), `packages/tl-schema/src/tl_schema/generated/type_labels.py` (S3)
- `packages/tl-tui/src/tl_tui/widgets/document_register.py` (how a register holds `project`, `client`, `actor`)
- `packages/tl-api/tests/test_confidentiality_walk.py` (the five-reader walk to extend)
may explore: `packages/tl-tui/tests/fakes*.py`, `packages/tl-tui/tests/test_record_view*.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/record_screen.py` (create), `record_view.py`, `psets_tab.py`
- `packages/tl-tui/src/tl_tui/details/**` (create), `labels_load.py` (create)
- `packages/tl-tui/src/tl_tui/client.py`, `embedded.py`, `remote.py`
- `packages/tl-api/src/tl_api/client/links.py`, `packages/tl-api/src/tl_api/routes/reference.py`
- `packages/tl-tui/tests/**` (new tests, fakes, and snapshots of the record view and psets tab)
- `packages/tl-api/tests/test_confidentiality_walk.py`, `packages/tl-api/tests/test_schema_forms*.py`
- `docs/reports/P1-UX/S2.md` (create)

## Steps
1. `form_metadata(record_id)` end to end (interface, embedded, `tl_api` client, route, fakes), with its tests on both adapters.
2. `details` package with `generic` and `documents`; `labels_load`.
3. `RecordScreen`, `open_record`; wire `RecordView` to details and the Properties name.
4. A test register stand-in (a minimal ModalScreen in the test) proves: Enter-equivalent call opens the screen on
   a document row; Esc returns with the cursor on the same row; Properties lists `document_data` with labels.

## Acceptance
```
just check
just gate packages/tl-tui packages/tl-api/tests/test_confidentiality_walk.py packages/tl-api/tests/test_schema_forms.py
just gate-pg packages/tl-tui/tests/test_embedded_real_services.py packages/tl-api
```
Expected: pass on both adapters; snapshots regenerated in this piece, no other snapshot changed.

## Tests to add
- `packages/tl-tui/tests/test_record_screen.py`: `test_open_record_shows_details_with_labels_not_ids`,
  `test_escape_dismisses_and_the_register_keeps_its_row`, `test_a_hidden_record_reads_exactly_like_a_missing_one`
  (same rendered text for a restricted id as a user and a random id; run inside `use_viewer`, L-P1-I5-2),
  `test_following_a_link_inside_the_screen_retargets_it`, `test_technical_rows_appear_only_in_technical_mode`, `test_refresh_for_display_mode_rerenders_details_and_properties`.
- `packages/tl-tui/tests/test_details_registry.py`: unknown type uses the generic rows; a renderer error shows the
  generic rows plus one status line, never a traceback; every renderer module is imported once.
- `packages/tl-tui/tests/test_properties_tab.py`: the tab is named Properties; a tag shows its class-bound sets
  (needs the record id); a document shows `document_data` once S3 is merged.
- `packages/tl-api/tests/test_schema_forms.py`: `record_id` of a hidden record answers like no `record_id`; of a
  missing record likewise; response shape unchanged; the walking test lists the parameter as exercised.

## Guards for the sentinel and targeted mutants
Sentinel: make `RecordScreen` ignore Esc. Targeted: (1) route uses `record_id` without the visibility check
(five-reader walk must fail); (2) `RecordScreen` shows the id in the "No record" text; (3) technical rows shown in
plain mode; (4) `PsetsTab` drops `record_id`; (5) `open_record` uses `pop_screen`-style close (callback test).

## Report requirements
Standard report. List the record types that fall back to generic rows. State for each of the detail getters
(`get_document`, `get_tag`, `get_correspondence`, `get_rfi`, `get_commercial`, `get_clock`, `get_schedule`,
`get_schedule_snapshot`) how a record envelope (`scope`, `key`) maps to its arguments, and whether the key is the
number; this is the table the screen tickets rely on.

## Escalation triggers
- A detail getter cannot be called from `(scope, key)` without a new client or API method (contract change): write the
  mapping in the report and escalate; do not build the other renderers (F12: getters are escalated, not guessed).
- The route change needs more than the optional parameter, or `psets.form_metadata` needs a change.
- Postgres and SQLite disagree on any new read (L-P1-I5-1).

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
