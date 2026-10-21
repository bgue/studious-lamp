# P1-UX-T05 — Commercial, RFI and evidence text in plain words; commercial Details

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: tui, tests
Depends on: T00, S2, S3, T03 (merged)
Branch: `p1/ux-t05-commercial-evidence-text`

## Goal
The text modules behind the RFI log, the Commercial register and the evidence trail speak plain words by default and give the
internal form back when asked. Text only: `domain_screen.py` is NOT touched (T04 wires it, D24), so every new kwarg is optional and
the cell functions keep today's output when called without them. Also: the commercial `Status` column goes (it repeats `State`: an
assessment moves the item to Agreed, Disputed or Partially agreed); trunk is red on one RFI pin that T03's clock formatter moved; a
Details renderer for commercial items.

## Brief references (pasted)
> SCOPE clause 2: domain labels, not internal keys; no clock ids, calendar ids, actor ids, record ids, schema versions. Clause 3: technical mode shows what plain hides.
> D21: plain clock lines lead with the words (`expired due 2026-10-19 left -1 (10 working days) Answer required`); technical leads with the clock key and shows `, calendar <code>`.
> D24: T05 is text only; T04 wires domain_screen. D22/D14: nothing here is a screen.
> F8: the commercial State/Status duplicate column is dropped.
> Gate red on trunk (orchestrator, 31): `test_rfi_text.py::test_the_panel_shows_the_question_the_answer_the_escalation_and_the_clocks` pins `  P123-RFI-0002-C01 expired due 2026-10-19 left -1`.

## Interfaces (verbatim from repo)
```python
# tl_tui/correspondence_text.py (merged, do not edit)
def clock_line(clock: ClockView, *, technical: bool = False) -> str   # plain: "expired due 2026-10-19 left -1 (10 working days) Answer required"
# tl_tui/display.py: Labels, humanize(name), type_label(labels, record_type), code_label(labels, list, code),
#   domain_label(labels, domain, subtype=None) -> "Letter", actor_label(labels, actor), mode_of(app).technical
# tl_tui/details/__init__.py: DetailRow(label, value, technical=False); @register("module.Type")
#   renderer(client, project, record, labels) -> list[DetailRow]; modules in details/ load by themselves.
# tl_tui/details/documents.py is the model (_or_empty, technical_rows(record) from details/generic.py, EMPTY, timestamp from tl_tui.text)
# commercial_text.py today
COMMERCIAL_COLUMNS = ("Number","State","Kind","Aware","Bar due","Left","Bar","Cur","Estimated","Assessed","Status","Subject")   # 12
def bar_text(line) -> str; def commercial_cells(line: CommercialLine) -> tuple[str, ...]   # 12 cells; Kind = line.subtype raw; State raw
def commercial_summary(register, *, only_open=False, time_bars_only=False) -> str          # no internal words; unchanged
def commercial_lines(view: CommercialView) -> list[str]   # line 0: f"{number}  {state}  {subtype or '-'}  class {confidentiality}"; clocks via clock_line(c)
# rfi_text.py today
def rfi_cells(line: RfiLogLine) -> tuple[str, ...]        # State and Kind (line.subtype) raw
def rfi_lines(view: TechnicalView) -> list[str]           # line 0 f"{number}  {state}  {subtype or '-'}  class {confidentiality}"; clocks via clock_line(c)
# evidence_text.py today
def node_cells(node: EvidenceNode) -> tuple[str, ...]     # (indented key or record_id, type.rpartition(".")[2], state + VOID, via, title)
def node_lines(node) -> list[str]; def node_line(node) -> str   # node_line prints "[{node.type}]", facts "k=v", pin; node_lines prints "k: v"
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/commercial_text.py`, `rfi_text.py`, `evidence_text.py`, `details/documents.py`
- `packages/tl-tui/tests/test_commercial_text.py`, `test_rfi_text.py`, `test_evidence_text.py`, `test_domain_screen.py`
- `packages/tl-tui/tests/fakes_correspondence.py` (read-only: `seed_domains`; commercial `P123-EW-0001`, `P123-CN-0001`; RFIs `P123-RFI-0001..3`)

## Allowed paths
- `packages/tl-tui/src/tl_tui/commercial_text.py`, `rfi_text.py`, `evidence_text.py`
- `packages/tl-tui/src/tl_tui/details/commercial.py` (create)
- `packages/tl-tui/tests/test_commercial_text.py`, `test_rfi_text.py`, `test_evidence_text.py`, `test_domain_screen.py` (update pinned expectations; add the technical counterparts)
- `packages/tl-tui/tests/test_commercial_plain.py` (create)
- `docs/reports/P1-UX/T05.md` (create)

## Steps
1. `commercial_text`: drop `"Status"` from `COMMERCIAL_COLUMNS` (now 11) and its cell. Add `labels: Labels | None = None` to `commercial_cells` and `commercial_lines`, and
   `technical: bool = True` to `commercial_cells` (default keeps today's raw State and Kind), `technical: bool = False` to `commercial_lines`.
   `technical=False` cells: State via `humanize`, Kind via `domain_label(labels or Labels(), "commercial", line.subtype)`, Bar via `humanize` (but `LATE` stays).
   `commercial_lines(view, labels=None, *, technical=False)`: line 0 state `humanize`, kind `domain_label`, `class` via `code_label(labels, "confidentiality", …)`; assessment status `humanize`;
   clocks `clock_line(c, technical=technical)`; the `escalated from` and cost-code lines unchanged. A `record {view.id}` line only when `technical`.
2. `rfi_text`: same pattern. `rfi_cells(line, labels=None, *, technical=True)`; plain: State `humanize`, Kind `domain_label(labels, "technical", line.subtype)`.
   `rfi_lines(view, labels=None, *, technical=False)`: line 0 as above, `reviewed …: {humanize(decision)}`, clocks `clock_line(c, technical=technical)`.
3. `evidence_text`: `node_cells(node, labels=None, *, technical=True)`; plain: Type `type_label(labels, node.type)`, State `humanize`, the key shows as `node.key` or `(no number)` (never `record_id`), `Reached by` `derived from` via `humanize(via.label)`.
   `node_lines(node, labels=None, *, technical=False)` and `node_line(...)` likewise: type via `type_label` (technical: `[type]` raw), fact keys `humanize`d in plain, `pinned …` and `record_id` fallback only when `technical`.
4. `details/commercial.py`: `@register("correspondence.CommercialItem")` reads `client.get_commercial(project, str(record["key"]))`. Rows: Type (`type_label`), Number, Subject, Kind (`domain_label`), State (`humanize`), Confidentiality (`code_label`),
   Clause, `Aware on`, Issued, Estimated (`currency value`), `Estimated hours`, `Schedule impact` (`N days`), `Cost codes` (only if any), `Basis` (only if set), `Escalated from` (only if set),
   `Assessment` (humanize status, only if set), `Assessed on`, `Assessed value`, `Assessment note` (only if set), Created, Updated, then `technical_rows(record)`.
5. Tests: update `test_rfi_text` pin to `waiting[-1].startswith("  expired due 2026-10-19 left -1 ")`, and add a `technical=True` counterpart: `rfi_lines(view, technical=True)[-1]` starts `"  P123-RFI-0002-C01 expired due 2026-10-19 left -1 "` and contains `calendar `.
   Update the commercial 12-cell tests to 11 (the `Status` value `agreed` is gone from the row, present in the panel as `assessment (…): Agreed`). Existing assertions that call the cell functions with no kwargs keep their raw values.

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_commercial_text.py packages/tl-tui/tests/test_commercial_plain.py packages/tl-tui/tests/test_rfi_text.py packages/tl-tui/tests/test_evidence_text.py packages/tl-tui/tests/test_domain_screen.py packages/tl-tui/tests/test_embedded_domains.py packages/tl-tui/tests/test_details_registry.py
```
Gate paths: all exist at dispatch except `test_commercial_plain.py` (new, this ticket creates it). Expected `gate: PASS`. `domain_screen.py` builds its table from `COMMERCIAL_COLUMNS` and `commercial_cells(x)`, so the dropped column follows by itself; if `test_domain_screen` fails on anything else, say what. Do not run the whole suite.

## Tests to add
`packages/tl-tui/tests/test_commercial_plain.py` (FakeClient + `seed_domains`; `Labels` built from `load_labels` or by hand with the seeded domains):
- `test_the_register_has_eleven_columns_and_no_status_column`.
- `test_plain_commercial_cells_and_panel_use_words_and_find_technical_is_empty` (`Early warning`, `Awaiting assessment`, no `early_warning`, no `P123-EW-0001-C`, `find_technical(text, labels) == []` over cells, panel, RFI panel, evidence cells).
- `test_technical_flag_restores_the_clock_key_and_the_raw_kind`.
- `test_the_commercial_details_rows_are_labelled` (`details_for` with `add_stored_record`-free record dict `{"type": "correspondence.CommercialItem", "key": "P123-EW-0001", ...}`; plain has no `Record` row, technical has).

## Report requirements
Standard report. One line per changed existing assertion.

## Escalation triggers
- `test_domain_screen` breaks on something other than the dropped column: stop; do not edit `domain_screen.py`.
- A view field the steps name does not exist: list it; do not invent it.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
