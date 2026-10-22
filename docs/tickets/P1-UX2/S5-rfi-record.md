# P1-UX2-S5 — The RFI record: narrative, status timeline, clocks

Status: draft (dispatch in wave 2; needs nothing from S1)
Tier: sonnet
Kind: piece
Review: full
Labels: tui, tests
Depends on: none (the Files tab is S4's; this piece adds no file code)
Branch: `p1/ux2-s5-rfi-record`

## Goal
Opening an RFI (or a technical query or deviation request) shows what a user expects of a record, in this order:
the narrative (subject, question, proposed solution, answer with who answered and when, raiser's and answerer's cost
and schedule view, escalation), then the status timeline (every state change with date, person's plain name and
note, oldest first: Raised, Issued, Answered, Closed, re-opened, escalated, plus the clocks with their outcome), then
the register metadata. Correspondence items get the same narrative and timeline where the data exists. Files are the
generic Files tab S4 adds to every record screen; this piece adds no file code.

## Brief references (pasted, abridged)
> SCOPE §3: Narrative first. Long text wraps; nothing truncated silently. Status timeline: every state change with date,
> person (plain name) and note, oldest first, from the record's events, plus the clocks with their outcome. Files: the
> attachments and linked documents of the item, each with name, type, size and pages, with the same open/preview as the
> document log (S4's tab). Correspondence items get the same narrative/timeline/files where the data exists.
> P1-UX display rules: plain labels from `tl_tui.display` (`actor_label`, `humanize`, `domain_label`); ids, hashes,
> internal keys, clock/calendar ids and `svc:` actors never appear in plain mode (`display.find_technical`); technical
> rows follow the mode. ADR-0016: the reads are already viewer-filtered; the record screen shows "No record" for a hidden
> record and a missing one alike.

## Interfaces
```python
# tl_tui/timeline_text.py (new, pure)
@dataclass(frozen=True) class TimelineRow: when: str; who: str; what: str; note: str = ""
def timeline_rows(events: Sequence[Event], clocks: Sequence[ClockView], labels: Labels, *, technical: bool) -> list[TimelineRow]
    # oldest first by effective_at then seq; only state-changing events (Raised/Defined, Submitted, Returned, Issued, Answered,
    # Reviewed accepted/rejected, Reissued, Closed, Void, Escalated) and clock outcomes (met on, expired, cancelled);
    # Technical.Updated and property edits are NOT rows; unknown event types are skipped, never shown raw;
    # who = actor_label (plain name, "System" for svc:, agent as "name ⚙" per P1-UX D31); when = date (and time in technical mode)
def timeline_lines(rows) -> list[str]            # "2026-10-12  Amy Chen  Issued  - sent to Acme Piling"
# tl_tui/details/technical.py: rfi_rows reordered and extended: narrative block, then DetailRow("Timeline", ...) rows (one per TimelineRow,
#   label = date, value = "who: what - note"), then metadata rows; "Answered by <plain name> on <date>" from the Answered event's actor.
# tl_tui/details/correspondence.py: same narrative (body) + timeline for items; no row for data that does not exist.
```
Event reads go through `client.history(record_id)` and clocks through `client.list_clocks(project, item=...)` (existing);
no new client method. Long text: values are whole strings; wrapping is the widget's job. If `record_view.py` must change
to wrap or to show multi-line values, change ONLY its Details-rendering function (S4 owns the tabs and bindings in the same
file); keep the edit minimal and name it in the report.

## Context (≤ 10 files)
- `packages/tl-tui/src/tl_tui/details/{technical.py,correspondence.py,__init__.py,generic.py}`
- `packages/tl-tui/src/tl_tui/{rfi_text.py,correspondence_text.py,display.py}`; `widgets/record_view.py` (the Details renderer only)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/{names.py,views.py,views_domain.py}` (event names, ClockView, TechnicalView)
- `packages/tl-tui/tests/test_details_registry.py`, `test_embedded_domains.py`, `fakes_correspondence.py`, `test_record_plain.py`
may explore: `packages/tl-modules/correspondence/tests/corrworld.py` (to see real RFI event sequences), `docs/modules/correspondence/`

## Allowed paths
- `packages/tl-tui/src/tl_tui/timeline_text.py` (create), `packages/tl-tui/src/tl_tui/details/{technical,correspondence,commercial}.py`, (NOT `rfi_text.py` or `correspondence_text.py`: S3's)
- `packages/tl-tui/src/tl_tui/widgets/record_view.py` (Details renderer function only)
- `packages/tl-tui/tests/test_timeline_text.py`, `test_rfi_record.py` (create), `packages/tl-tui/tests/fakes_rfi_record.py` (create: an RFI with a history and clocks; `fakes_correspondence.py` is S3's, do not edit), existing `test_details_registry.py`, `test_record_plain.py`, `test_record_screen.py`, `test_embedded_domains.py`, record-screen snapshots that show an RFI or correspondence item
- `docs/reports/P1-UX2/S5.md` (create)
Consequential pins (rule 12): tests that break only because the Details tab now leads with the narrative are updated, with a counterpart pinning the metadata rows that remain; listed in the report.

## Steps
1. `timeline_rows` against the real event sequence of an RFI (read corrworld to see the types), with its pure tests.
2. Narrative block and timeline rows in `details/technical.py`; items in `details/correspondence.py`; clocks with outcome.
3. Embedded test with a real RFI taken through raise, issue, answer, reject, reissue, answer, accept, close and an escalation; plain-mode leak check on the whole Details text.

## Acceptance (run these, once)
```
just check
just gate packages/tl-tui | tee .gate/summary.txt
just gate-pg packages/tl-tui/tests/test_embedded_domains.py packages/tl-tui/tests/test_embedded_real_services.py
```
Expected: PASS on both adapters.

## Tests to add
- `test_timeline_text.py`: order oldest first; reject then reissue then accept reads as three rows; property edits are not rows; unknown type skipped; `svc:` actor reads as System; an agent actor reads with the gear mark; technical mode adds time, plain mode has no ULID or hash (`find_technical` empty); a clock met/expired/cancelled row.
- `test_rfi_record.py`: Details of a fake RFI start with Subject, Question, Proposed solution, Answer (3 000-character question shown whole); the answer row names who and when; timeline follows the narrative; a Draft RFI shows no Answer and a one-row timeline; the real embedded RFI walk above; a correspondence item with only a body shows narrative and no timeline noise.

## Mutation
None: not a core area (no access, state or parser logic). One check in the report: the timeline never shows a row for an event the viewer cannot read (history is viewer-filtered; a hidden item shows "No record").

## Report requirements
`docs/reports/P1-UX2/S5.md` ≤ 60 lines: deviations first, any `record_view.py` edit, consequential pins, commands, learnings.

## Escalation triggers
- The timeline needs data no existing read returns (name the field and the read).
- A record_view change beyond the Details renderer, or a new client method.
