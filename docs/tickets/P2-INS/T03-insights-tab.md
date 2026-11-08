# P2-INS-T03 — Insights tab: four subtabs, Checks list, three "not available yet" lines that note the need (INS-B2)

Status: ready after T02b merged (round 3 or 4 dispatches it); written round 2 against merged S2 @2fbcdcf
Tier: haiku
review: full
Labels: tui, tests
Depends on: S2 merged (yes), T02 and T02b merged (`InsightsTab` stub in `widgets/insights_tab.py`; the `9` key and the pane in `record_view.py`)
Branch: `p2/ins-t03-insights-tab`
Worktree: `/home/user/wt/ins-t03`

## Goal
`widgets/insights_tab.py` is the Insights tab: four subtabs Checks, Suggestions, Analysis, Ask (Left and Right switch them; digit keys stay record tabs). Checks shows the record's findings grouped by source,
or "Nothing needs attention." Each of the other three shows one plain line and, the first time it is opened in a session, calls `client.note_need(request_kind=..., trigger="screen:insights.<subtab>", record_type=<the record's type>)`.
Text lives in `tl_tui/insights_text.py` (pure). `record_view.py` gets only the one `compose` line for the new constructor (T02b owns the file; it is merged first).

## Brief references (pasted; spec A2, A2.1, A3; plan check F7)
- Lines, exactly: "Suggestions are not available yet." / "Analyses are not available yet." / "Ask is not available yet."
- Opening one of these three writes one `unmet` row through `note_need(request_kind="suggestion"|"analysis"|"ask", ...)`: the screen sends **record type only, never the record id** (F7); the tab remembers `(record_type, subtab)` pairs already noted for this app session and does not repeat them; `note_need` never raises into the screen (client contract), so a refusal changes nothing on screen. Reads of Checks write nothing.
- Checks list: one block per source in the order readiness, constraints, expected_links, clocks, shortages, headed by a plain source word ("Readiness", "Constraints", "Expected links", "Response clocks", "Shortages"); each finding is `state word  text  (since <date>)` with a `!` before blocking ones; keys of related records are shown as `resolve_via` give them (display keys). Checks are never labelled suggestions, machine output or by a model or provider name.
- Plain by default (`display.find_technical` clean); technical mode adds the source name and `subject_id`. `load` runs off the UI thread; a client error keeps the display and posts a status line.
- Enter on a finding that has `resolve_via` opens the first referenced record (`open_record`).
- Keys: Left, Right on the tab only; the keymap test ties each row to a real binding. `9` and the pane are T02's.

## Interfaces (verbatim at @2fbcdcf)
```python
# tl_tui/client.py (ClientInterface; FakeClient has both: `findings: dict[record_id, list[CheckFinding]]`, `needs: list[(request_kind, trigger, record_type, record_id)]`, both append to `calls`)
def checks(self, record_id: str) -> list[CheckFinding]: ...
def note_need(self, *, request_kind: str, trigger: str, record_type: str, record_id: str | None = None) -> None: ...  # never raises
# tl_core.insights.types
class CheckFinding(BaseModel):
    source: str; subject_id: str; state: str; text: str; since: str | None = None
    severity: Literal["blocking", "warning"]; resolve_via: list[RecordRef] = []
class RecordRef(BaseModel):  # tl_core.readiness.types
    record_id: str; record_type: str; key: str
# tl_core.insights.checks.SOURCE_ORDER = ("readiness", "constraints", "expected_links", "clocks", "shortages")
# states a source gives: blocked, pending, unknown (readiness), open (constraints), missing (expected_links), overdue (clocks), short (shortages)
# telemetry accepts request_kind in ("check", "suggestion", "analysis", "ask"); trigger `screen:insights.<[a-z_]{1,32}>`; record_type a type name; the server refuses agents (204 to people)
# widgets/insights_tab.py (T02 stub): class InsightsTab(Vertical): compose yields Static(id="insights-body"); show_record(self, record: dict[str, Any]) -> None
```
Subtab ids for the three lines: trigger `screen:insights.suggestions` with kind `suggestion`, `screen:insights.analysis` with `analysis`, `screen:insights.ask` with `ask`. The record dict has `id`, `key`, `type`. Open a record with `OpenRecord(self.scope, key, follow=True)` (`messages.py`); the tab gets `scope` from `show_record`'s owner as `ThreadTab` does (constructor `InsightsTab(client, scope, *, id=None)`: this ticket changes the stub's constructor and `record_view.py` `compose` passes it: the one allowed edit there is the one line in `compose`, listed as a pin).

## Context (<= 7 files)
`widgets/insights_tab.py` (T02's stub); `widgets/thread_tab.py` (pattern); `readiness_text.py` (grouping pattern); `display.py`; `tests/test_keymap.py`; `tests/test_activity_tab.py` (Host pattern).

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/insights_tab.py` (modify the stub), `insights_text.py` (create), `keymap.py` (Left and Right rows for the tab, context `Record view`, owner `InsightsTab`), `widgets/record_view.py` (one `compose` line)
- `packages/tl-tui/tests/test_insights_tab.py`, `test_insights_text.py` (create), `test_keymap.py` (add `InsightsTab` to `OWNERS`; consequential pin, listed)
- `packages/tl-tui/README.md` (one row: Insights tab, keys, the three lines), `docs/reports/P2-INS/T03.md`
Not allowed: the rest of `record_view.py`, `client.py`, `embedded.py`, `remote.py`, `fakes.py` (it already has `findings` and `needs`).

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_insights_tab.py packages/tl-tui/tests/test_insights_text.py packages/tl-tui/tests/test_keymap.py packages/tl-tui/tests/test_record_activity_wiring.py
```

## Tests to add
`test_insights_text.py`: group order, blocking mark, empty text, plain vs technical, no key or id in plain text. `test_insights_tab.py` on `FakeClient`: Checks list for a record with findings and for one without; Left and Right cycle the four subtabs; opening each of the three records exactly one call with `record_id` absent and the right `request_kind`; reopening makes no second call; a `note_need` that raises (wrap the fake in the test) or is refused does not break the screen; a hidden `resolve_via` never appears (the fake returns none); no "AI", "model" or provider word in any text (`find_technical` and a literal scan).

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
