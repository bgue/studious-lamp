# P1-UX-T04 — Domain screen: plain words, Enter opens the record screen, RFI Details

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: T00, S2, S3, T05 (merged at 806c519)
Branch: `p1/ux-t04-domain-screen`

## Goal
The RFI log, Commercial register and Evidence views (Ctrl+G) speak plain language and Enter on a row opens the full record screen (Esc returns on the same row).
T05 made the text functions plain; this ticket wires them: the screen loads labels, passes `labels` and the mode to every call, redraws when Technical details toggles, and
gets an RFI Details renderer (`details/technical.py`). Evidence panel/line also humanize the link label in plain (T05 review LO F1).

## Brief references (pasted)
> SCOPE clause 1: Enter on any row opens the full record view; Esc returns on the same row. Clause 2: plain words; no internal keys, ids, hashes. Clause 3: technical mode shows what plain hides.
> D14: define `refresh_for_display_mode(self) -> None`. D22: registers open records on `DataTable.RowSelected`, never a priority Enter binding.
> D24/D27: the cell functions default `technical=True` (raw), the lines functions default plain: the screen must pass both `labels` and `technical=` explicitly on every call.
> D26: COMMERCIAL_COLUMNS is 11 wide in both modes (no Status). Column tuples are identical in plain and technical.

## Interfaces (verbatim from repo)
```python
# tl_tui/rfi_text.py / commercial_text.py / evidence_text.py (merged T05)
def rfi_cells(line: RfiLogLine, labels: Labels | None = None, *, technical: bool = True) -> tuple[str, ...]
def rfi_lines(view: TechnicalView, labels: Labels | None = None, *, technical: bool = False) -> list[str]
def commercial_cells(line: CommercialLine, labels: Labels | None = None, *, technical: bool = True) -> tuple[str, ...]
def commercial_lines(view: CommercialView, labels: Labels | None = None, *, technical: bool = False) -> list[str]
def node_cells(node: EvidenceNode, labels: Labels | None = None, *, technical: bool = True) -> tuple[str, ...]
def node_lines(node: EvidenceNode, labels: Labels | None = None, *, technical: bool = False) -> list[str]
def node_line(node: EvidenceNode, labels: Labels | None = None, *, technical: bool = False) -> str
# evidence_text.py today (the F1 fix): node_cells does `label = node.via.label if technical else humanize(node.via.label)`;
#   node_lines:  f"reached by {node.via.label} ({node.via.status}{pin}) since ..."   <- raw in both modes
#   node_line:   f" <- {node.via.label} ({node.via.status}{pin}, since ...)"          <- raw in both modes
# tl_tui/widgets/record_screen.py: open_record(screen, client, scope, project, actor, record_id) -> None
# tl_tui/labels_load.py: load_labels(client, scope, record_types=("core.Record",)) -> Labels;  tl_tui/display.py: mode_of(app).technical, Labels, humanize, type_label, code_label, domain_label
# tl_tui/details/__init__.py: DetailRow(label, value, technical=False); @register("correspondence.TechnicalItem") renderer(client, project, record, labels) -> list[DetailRow]
# details/commercial.py is the model (merged T05); technical_rows(record) from details/generic.py; EMPTY, timestamp from tl_tui.text
# client.get_rfi(project, number) -> TechnicalView: ItemView fields (number subject subtype state confidentiality issued_on ...) plus question proposed_solution discipline required_by
#   potential_cost_impact potential_schedule_impact answer answered_on answer_cost_impact answer_schedule_impact answer_item_number review_decision reviewed_on review_note escalations[EscalationView(number subtype state)]
# widgets/domain_screen.py (today): DomainScreen(client, project, actor, *, is_controller, mode); table "#dom-table" (row key = record id); self.rfi_log.lines / self.notices.lines (rows have .id .number) / self.trail.nodes (.record_id);
#   reload() calls rfi_cells(x) / commercial_cells(x) / node_cells(n); _describe() calls rfi_lines(view) / commercial_lines(view) / node_lines(node); on_mount calls reload.
# tests: seed_domains(client) in fakes_correspondence.py; FakeClient.add_stored_record(record_id, key, record_type, title) makes a row openable.
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/domain_screen.py`, `evidence_text.py`, `details/commercial.py`
- `packages/tl-tui/tests/test_domain_screen.py` (lines 1-100: `world()`, `scenario()`, `WORLD_DAY`), `test_record_screen.py` (Enter/Esc pattern, lines 1-120)
- `packages/tl-tui/tests/fakes_correspondence.py` (read-only: `seed_domains`, ids on the lines it seeds: read them from `client.list_rfis("P123").lines[0].id`)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/domain_screen.py`, `packages/tl-tui/src/tl_tui/evidence_text.py`
- `packages/tl-tui/src/tl_tui/details/technical.py` (create)
- `packages/tl-tui/tests/test_domain_screen.py`, `test_evidence_text.py` (update pinned expectations only)
- `packages/tl-tui/tests/test_domain_plain.py` (create)
- `docs/reports/P1-UX/T04.md` (create)

## Steps
1. `domain_screen`: `self.labels = Labels()` in `__init__`; `on_mount` sets `self.labels = load_labels(self.client, f"project:{self.project}", ("correspondence.TechnicalItem", "correspondence.CommercialItem"))` before `reload()`.
2. `reload()` and `_describe()` read `technical = mode_of(self.app).technical` and pass `self.labels, technical=technical` to all six text calls (cells and lines). Columns unchanged.
3. `on_data_table_row_selected(self, event)`: `event.stop()`; id by mode: rfi `self.rfi_log.lines[row].id`, commercial `self.notices.lines[row].id`, evidence `self.trail.nodes[row].record_id`; guard the index and a `None` source;
   `open_record(self, self.client, f"project:{self.project}", self.project, self.actor, record_id)`. Add `refresh_for_display_mode(self) -> None: self.reload()`.
4. `evidence_text`: in `node_lines` and `node_line` the link label is `node.via.label` when technical, else `humanize(node.via.label)`. Nothing else changes in that file.
5. `details/technical.py`: `@register("correspondence.TechnicalItem")` reads `client.get_rfi(project, str(record["key"]))`. Rows: Type (`type_label`), Number, Subject, Kind (`domain_label(labels, "technical", subtype)` or EMPTY),
   State (`humanize`), Confidentiality (`code_label(labels, "confidentiality", ...)`), Discipline, Needed by, Issued, Question, Proposed solution, `Raiser expects cost`, `Raiser expects schedule` (the two potential impacts, `humanize`),
   then only if answered: Answer, `Answered on`, `Answerer says cost`, `Answerer says schedule`, `Answered by item`; only if reviewed: Review (`humanize(decision)` plus date and note); only if escalated: `Escalated to` (`number (humanize(state))`, comma-separated);
   Created, Updated, then `technical_rows(record)`. Use `_or_empty`-style helpers as `details/commercial.py` does.
6. Update pinned expectations in `test_domain_screen.py`/`test_evidence_text.py` that now read plain (list each in the report).

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_domain_screen.py packages/tl-tui/tests/test_domain_plain.py packages/tl-tui/tests/test_evidence_text.py packages/tl-tui/tests/test_rfi_text.py packages/tl-tui/tests/test_commercial_text.py packages/tl-tui/tests/test_commercial_plain.py packages/tl-tui/tests/test_embedded_domains.py packages/tl-tui/tests/test_details_registry.py packages/tl-tui/tests/test_record_screen.py packages/tl-tui/tests/test_technical_toggle.py
```
Gate paths: all exist at dispatch except `test_domain_plain.py` (new, this ticket creates it). Expected `gate: PASS`. No snapshot test shows this screen. Do not run the whole suite.

## Tests to add
`packages/tl-tui/tests/test_domain_plain.py` (reuse `world()` and `scenario()` from `test_domain_screen` by import or copy; `add_stored_record(<id from the seeded line>, number, type, subject)`):
- `test_enter_on_an_rfi_row_opens_the_record_and_escape_returns_to_the_same_row`; same for a commercial row (press `2`) and an evidence row (press `e`, then `3`-view row 0).
- `test_a_row_the_viewer_cannot_read_opens_as_no_record` (no stored record; no id in the screen text).
- `test_plain_screen_text_has_no_technical_tokens` (table + panel text of all three views: `find_technical(text, labels) == []`, no `early_warning`, no `user:`).
- `test_technical_mode_restores_raw_cells_and_back` (flag on, `refresh_for_display_mode()`, raw state/kind visible, then off).
- `test_the_rfi_details_rows_are_labelled` (`details_for` on an answered RFI record dict; `Answer` row only when answered; `Key` only in technical).

## Report requirements
Standard report. List existing assertions changed and why (one line each).

## Escalation triggers
- `add_stored_record` does not make the record screen open (fix would be in `fakes.py`): stop.
- A text function needs a change beyond step 4 (T05's files): stop and report.
- Plain text still shows an id, hash, raw key or `user:`/`svc:`: list it; fix only inside Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
