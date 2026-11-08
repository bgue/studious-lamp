# P2-INS-T03 — Insights tab: four subtabs, Checks list, three "not available yet" lines that note the need (INS-B2)

Status: draft (written round 1; the next round refreshes the pasted interfaces after S2 and T02 merge)
Tier: haiku
review: full
Labels: tui, tests
Depends on: S2 merged (`ClientInterface.checks`, `.note_need`, `CheckFinding`), T02 merged (the `9` key and the `InsightsTab` stub in `record_view.py`)
Branch: `p2/ins-t03-insights-tab`
Worktree: `/home/user/wt/ins-t03`

## Goal
`widgets/insights_tab.py` is the Insights tab: four subtabs Checks, Suggestions, Analysis, Ask (Left and Right switch them; digit keys stay record tabs). Checks shows the record's findings grouped by source,
or "Nothing needs attention." Each of the other three shows one plain line and, the first time it is opened in a session, calls `client.note_need(request_kind=..., trigger="screen:insights.<subtab>", record_type=<the record's type>)`.
Text lives in `tl_tui/insights_text.py` (pure). `record_view.py` is NOT edited (T02 owns it).

## Brief references (pasted; spec A2, A2.1, A3; plan check F7)
- Lines, exactly: "Suggestions are not available yet." / "Analyses are not available yet." / "Ask is not available yet."
- Opening one of these three writes one `unmet` row through `note_need(request_kind="suggestion"|"analysis"|"ask", ...)`: the screen sends **record type only, never the record id** (F7); the tab remembers `(record_type, subtab)` pairs already noted for this app session and does not repeat them; `note_need` never raises into the screen (client contract), so a refusal changes nothing on screen. Reads of Checks write nothing.
- Checks list: one block per source in the order readiness, constraints, expected_links, clocks, shortages, headed by a plain source word ("Readiness", "Constraints", "Expected links", "Response clocks", "Shortages"); each finding is `state word  text  (since <date>)` with a `!` before blocking ones; keys of related records are shown as `resolve_via` give them (display keys). Checks are never labelled suggestions, machine output or by a model or provider name.
- Plain by default (`display.find_technical` clean); technical mode adds the source name and `subject_id`. `load` runs off the UI thread; a client error keeps the display and posts a status line.
- Enter on a finding that has `resolve_via` opens the first referenced record (`open_record`).
- Keys: Left, Right on the tab only; the keymap test ties each row to a real binding. `9` and the pane are T02's.

## Interfaces (open these)
`ClientInterface.checks(record_id) -> list[CheckFinding]`; `note_need(*, request_kind, trigger, record_type, record_id=None) -> None`; `CheckFinding` {source, subject_id, state, text, since, severity, resolve_via}; the `InsightsTab.show_record(record)` signature T02 left.

## Context (<= 7 files)
`widgets/insights_tab.py` (T02's stub); `widgets/thread_tab.py` (pattern); `readiness_text.py` (grouping pattern); `display.py`; `keymap.py`; `tests/test_keymap.py`; `tests/test_plain_walk.py`.

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/insights_tab.py`, `insights_text.py` (create), `keymap.py` (Left and Right rows for the tab)
- `packages/tl-tui/tests/test_insights_tab.py`, `test_insights_text.py` (create), `test_keymap.py`, `test_plain_walk.py` (consequential pins, listed)
- `packages/tl-tui/README.md` (one row: Insights tab, keys, the three lines), `docs/reports/P2-INS/T03.md`
Not allowed: `record_view.py`, `client.py`, `embedded.py`, `remote.py`, `fakes.py` beyond a canned `checks` list (S2 added the methods; if `FakeClient` lacks canned findings add the data only, listed as a pin).

## Acceptance
```
just check
just gate packages/tl-tui/tests
```

## Tests to add
`test_insights_text.py`: group order, blocking mark, empty text, plain vs technical, no key or id in plain text. `test_insights_tab.py` on `FakeClient`: Checks list for a record with findings and for one without; Left and Right cycle the four subtabs; opening each of the three records exactly one call with `record_id` absent and the right `request_kind`; reopening makes no second call; a `note_need` that raises or is refused does not break the screen; a hidden `resolve_via` never appears (the fake returns none); no "AI", "model" or provider word in any text (`find_technical` and a literal scan).

## Report requirements
`docs/templates/haiku-report.md`, <= 60 lines; deviations first; each pin; output of the two commands (<= 5 lines each).

## Commit
`P2-INS-T03: <imperative summary>`; trailer lines as `SUPERVISOR-PROMPT.md`; no model names. Do not merge; do not push.

## Escalation triggers
- Stop and report *Blocked* if `note_need` cannot be called without a record id; T02's stub signature differs; Left and Right collide with a binding the keymap test pins; a state word has no plain label.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
