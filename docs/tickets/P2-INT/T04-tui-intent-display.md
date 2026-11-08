# P2-INT-T04 — Intent in the TUI History tab

Status: ready (S2 merged at 0fc06f1; paste the `tui-layout` rules into the brief at dispatch)
Tier: haiku
Review: full
Labels: tui
Depends on: S2 merged
Branch: `p2/int-t04-tui-intent-display`

## Goal
A reader of a record's History tab sees why an event happened. After this ticket the highlighted History row, when its event has an intent, shows `Why`, `Next`, `Toward` and `Goal` lines in a panel under the table; an event without intent, and the table itself, look exactly as before. Text comes from one pure function in the `*_text.py` style; the screen holds no logic.

## Brief references (pasted)
> ADR-0025 d7 and Soon: "intent in TUI History". d5: an unreadable reference arrives as the text "not available" and is shown as is.
> Display standard: property:value lines, empty values omitted, no counts that differ for hidden items (packages/tl-tui/README.md "Plain and technical display").

## Interfaces
Drift found at r3: (1) the Activity screen lists schedule activities, not events: it is out of scope. Trace shows links, not events (S2: trace has no intent): out of scope. (2) History is a `DataTable` of one row per event (`record_text.history_cells`, `widgets/record_view.py` `_draw_history`), so there is no block "under the event line"; the panel below the table is the design. (3) `tl_core.ledger.Event` already carries `intent` (S2); the remote client parses it from the API, which redacts. The embedded client calls `queries.record_history`, which does NOT redact, so a hidden reference would show as an id: `embedded.history` must pass its result through `tl_core.intent.redact_events(uow.conn(), events)` (the viewer is the current one).
```python
# tl_tui/intent_text.py (create; provided test docs/tickets/P2-INT/provided/test_intent_text.py: copy it to packages/tl-tui/tests/ unchanged)
def intent_lines(intent: Intent | None, *, technical: bool, names: Mapping[str, str] | None = None) -> list[str]
# None or empty (intent_json(intent) is None) -> []; order Why, Next (one per item), Toward, Goal.
# plain: "Why: <t>", "Next: <command> <name>" | "Next: <text>", "Toward: <name> -> <state or condition>", "Goal: <ref>"; names maps record id -> key, an id with no entry is shown as is ("not available" too)
# technical: keys why, next, toward, goal_ref in lower case, raw ids (names ignored); toward uses "->" for a state and "~" for a condition
```
Wiring in `record_view.py`: a `Static` `#rv-history-why` after the history table, hidden when empty; on `DataTable.RowHighlighted` of `#rv-history` (and after `_draw_history`) it shows `intent_lines(event.intent, ...)` joined by newlines for the event with that `event_id` (kept in `self._events`); `names` is built from `self.client.get_record_by_id(id)["key"]` for the ids in the intent, ignoring client errors (id shown). A mode switch redraws it.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/record_view.py` (`_draw_history`, compose, `refresh` on mode switch), `record_text.py` (`history_cells`: unchanged), `embedded.py` (`history`)
- `packages/tl-tui/tests/test_record_view.py` (pilot pattern), `fakes.py`, `packages/tl-tui/README.md` (display standards)

## Allowed paths
- `packages/tl-tui/src/tl_tui/intent_text.py` (create), `widgets/record_view.py` (compose and handler lines), `embedded.py` (the one `history` line), `packages/tl-tui/tests/test_intent_text.py` (provided, committed), `packages/tl-tui/tests/test_history_intent.py` (create), `docs/reports/P2-INT/T04.md` (create)
Consequential pins (rule 12): screen snapshots that change only because the new empty panel exists are updated and listed; the no-intent History rows stay byte-identical.

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_intent_text.py packages/tl-tui/tests/test_history_intent.py packages/tl-tui/tests/test_record_view.py packages/tl-tui/tests/test_record_plain.py packages/tl-tui/tests/test_record_screen.py
```

## Tests to add
`test_history_intent.py`: highlighting a row whose event has an intent shows the lines (plain and technical); a row without shows an empty hidden panel and its table cells equal `history_cells`; "not available" is shown as is; an embedded-client test: an intent naming a record the viewer cannot read comes back from `history` as "not available", the same as an unknown one.

## Report requirements
Standard plus the pins list.

## Escalation triggers
- Stop and report *Blocked* if the panel needs a change outside `record_view.py` and `embedded.py`, or the client DTO drops `intent`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
