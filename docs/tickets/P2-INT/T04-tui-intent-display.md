# P2-INT-T04 — Intent in the TUI History and Activity displays

Status: staged (release after S2 merged; load the `tui-layout` skill rules into the brief at release)
Tier: haiku
Review: full
Labels: tui
Depends on: S2 merged
Branch: `p2/int-t04-tui-intent-display`

## Goal
A reader of a record's History (and the Activity screen) sees why an event happened. After this ticket an event row that has an intent shows a `Why`, `Next` and `Toward` block under the event line; an event without intent looks exactly as before. Text comes from one pure function in the `*_text.py` style; the screen holds no logic.

## Brief references (pasted)
> ADR-0025 d7 and Soon: "intent in TUI History and Trace". d5: an unreadable reference arrives from the API as the text "not available" and is shown as is.
> Display standard: property:value lines, empty values omitted, no counts that differ for hidden items (packages/tl-tui/README.md "Plain and technical display").

## Interfaces
```python
# tl_tui/intent_text.py (create; provided test packages/tl-tui/tests/test_intent_text.py)
def intent_lines(intent: IntentView | None, *, technical: bool) -> list[str]
# None or empty -> []; "Why: <text>", "Next: <command> <target>" or "Next: <text>" (one line each), "Toward: <target> -> <state or condition>", "Goal: <goal_ref>"; technical mode adds the raw keys
```
`ClientInterface` read models already carry `intent` after S2 (check at release; if the client DTOs drop it, the fake and embedded client are in Allowed paths).

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/activity_screen.py`, the History tab widget (find: `grep -rn "History" packages/tl-tui/src/tl_tui/widgets`), `trace_tab.py` (not changed; Trace shows links, not events)
- `packages/tl-tui/src/tl_tui/client.py`, `embedded.py` (event/history read), `packages/tl-tui/tests/` fakes
- `packages/tl-tui/README.md` (display standards)

## Allowed paths
- `packages/tl-tui/src/tl_tui/intent_text.py` (create), the History tab and `activity_screen.py` (render call only), `client.py`/`embedded.py`/fakes only if the DTO drops `intent`, `packages/tl-tui/tests/test_intent_text.py` (provided), `packages/tl-tui/tests/test_history_intent.py` (create), `docs/reports/P2-INT/T04.md` (create)
Consequential pins (rule 12): screen snapshots that change only for an event with intent are updated; the no-intent snapshot is the counterpart that pins the old form.

## Acceptance
```
just check
just gate packages/tl-tui/tests
```

## Tests to add
`test_history_intent.py`: a row with intent shows the block; a row without is byte-identical to the old snapshot; "not available" shown as is.

## Report requirements
Standard plus the pins list.

## Escalation triggers
- Stop and report *Blocked* if the History widget has no per-event render hook or the DTO needs a model change outside Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
