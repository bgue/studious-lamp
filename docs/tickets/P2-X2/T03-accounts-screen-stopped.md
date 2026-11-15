# P2-X2-T03 — Accounts screen: an agent's stopped flag and held count

Status: ready
Tier: haiku
kind: ticket
review: full
Labels: tui
Depends on: T01 (merged @a9dc1eca)
Branch: `p2/x2-t03-accounts-screen`
Worktree: `/home/user/wt/x2/t03`

## Goal
The accounts screen (`F10`) shows, in the panel under the table, whether the highlighted agent may file (`Filing`) and, for a stopped agent, since when, by whom, why and
how many of its proposals are held. The screen only displays what the client returns; it counts nothing and filters nothing (141: the service filtered before it counted).
The client gains one read method that mirrors `ApiClient.list_stopped_agents` and the embedded client calls `agent_stop.list_stopped` with the current viewer.

## Brief references (pasted)
> P2-X2 T03: accounts screen shows an agent's stopped flag and held count; the count is filtered before counting (141). AGENTS.md: no business logic in the TUI; a hidden
> record is neither named nor counted. tui-layout: property lines `Label  value`; show a field only if it can apply; a state has a symbol, not only a colour (`■ locked until ...`).

## Interfaces (verbatim)
```python
# tl_core/services/agent_stop.py
class StoppedAgent(BaseModel):
    agent: str; stopped_at: str | None; stopped_by: str | None; reason: str | None; held: int   # agent is "agent:<username>"
def list_stopped(conn: Connection, viewer: confidentiality.Viewer, *, limit: int = 200) -> list[StoppedAgent]
# tl_api/client/agent_stop.py (merged): ApiClient.list_stopped_agents(self, limit=200) -> list[StoppedAgent]   (positional ok)
# tl_tui/admin_text.py (today)
def detail_lines(view: AccountView, tokens: Sequence[AgentTokenView], now: str) -> list[str]
#   pairs list ends, for an agent, with ("Tokens", f"{live} live, {revoked} revoked"); lines are f"{label:<10}{value}"
# tl_tui/embedded.py pattern (admin gate, read-only uow, viewer):
def list_agent_tokens(self, account_id=None, *, include_revoked=True):
    with self._uow(True) as uow:
        self._admin_gate(uow)
        return account_queries.list_agent_tokens(uow.conn(), ...)
# viewer elsewhere in embedded.py: confidentiality.current_viewer()
# tests/fakes_admin.py pattern: self._gate("list_agent_tokens", ...) records the call and raises ForbiddenError when is_admin is False
```

## Steps
1. `tl_tui/client.py`, `ClientInterface`, next to `list_agent_tokens`: `def list_stopped_agents(self, limit: int = 200) -> list[StoppedAgent]` with a one-line docstring
   ("Agents stopped now with the held count the viewer may see; admin only"). Same name and signature as `ApiClient`.
2. `tl_tui/embedded.py`: `from tl_core.services import agent_stop` (module import, so a test can patch `agent_stop.list_stopped`); the method opens `self._uow(True)`, calls
   `self._admin_gate(uow)`, returns `agent_stop.list_stopped(uow.conn(), confidentiality.current_viewer(), limit=limit)`. No count, no filter of your own.
3. `tests/fakes_admin.py`: `self.stopped_agents: list[StoppedAgent] = []` in `_init_admin` (tests set it); `list_stopped_agents(self, limit=200)` calls `self._gate("list_stopped_agents", limit=limit)`
   and returns `self.stopped_agents[:limit]`.
4. `tl_tui/admin_text.py`: `detail_lines(view, tokens, now, stopped: StoppedAgent | None = None)`. For `kind == "agent"` append after `Tokens`:
   `("Filing", "allowed")` when `stopped is None`; else `("Filing", "■ stopped since <moment(stopped_at)> UTC")` (the `—` mark from `tl_tui.layout.EMPTY` when `stopped_at` is None),
   then `("Held", f"{stopped.held} pending")`, then `("Reason", stopped.reason)` only when a reason exists, then `("By", stopped.stopped_by)` only when it exists. Non-agents get none of these.
   The label column is 10 wide today; `Filing` and `Held` fit.
5. `tl_tui/widgets/admin_screen.py`: `self.stopped: list[StoppedAgent] = []`; `reload` reads `self.client.list_stopped_agents()` in the same `try` as the two lists (and clears it in the `except`);
   `_describe` passes the entry whose `agent == f"agent:{view.username}"` (or None) to `detail_lines`. Nothing else on the screen changes.
6. Consequential pins: a snapshot in `packages/tl-tui/tests/__snapshots__/test_admin_screen/` that shows an agent's panel now has the `Filing` line; update it (`uv run pytest <file> --snapshot-update`,
   then re-run without the flag) and list it in the report. Any other test that breaks only because an agent's panel gained the lines: update and list.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/admin_text.py` (lines 1-25 and 78-112)
- `packages/tl-tui/src/tl_tui/widgets/admin_screen.py` (lines 81-200)
- `packages/tl-tui/src/tl_tui/embedded.py` (lines 2452-2475 only) and `packages/tl-tui/src/tl_tui/client.py` (lines 1440-1450 only)
- `packages/tl-tui/tests/fakes_admin.py` (lines 50-110 and 205-230)
- `packages/tl-tui/tests/test_admin_screen.py` (lines 1-100) and `packages/tl-tui/tests/test_admin_text.py` (lines 110-145)
may explore: `.claude/skills/tui-layout/SKILL.md` (property lines, empty values)

## Allowed paths
- `packages/tl-tui/src/tl_tui/admin_text.py`, `packages/tl-tui/src/tl_tui/widgets/admin_screen.py`
- `packages/tl-tui/src/tl_tui/client.py` (the one protocol method), `packages/tl-tui/src/tl_tui/embedded.py` (the import and the one method)
- `packages/tl-tui/tests/fakes_admin.py`, `packages/tl-tui/tests/test_admin_text.py`, `packages/tl-tui/tests/test_admin_screen.py`, `packages/tl-tui/tests/test_embedded_admin.py`
- `packages/tl-tui/tests/__snapshots__/test_admin_screen/` (consequential pin only)
- `docs/reports/P2-X2/T03.md` (create)

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-tui/tests/test_admin_text.py packages/tl-tui/tests/test_admin_screen.py packages/tl-tui/tests/test_admin_plain.py packages/tl-tui/tests/test_embedded_admin.py packages/tl-tui/tests/test_app_admin.py packages/tl-tui/tests/test_account_forms.py packages/tl-tui/tests/test_fakes_types.py
```
Expected: all pass; `just check` clean (pyright accepts the fake and the embedded client as `ClientInterface`).

## Tests to add
- `test_admin_text.py`: an agent with `stopped=None` shows `Filing    allowed` and no `Held`; a stopped agent shows `Filing    ■ stopped since 2026-10-11 12:15 UTC`, `Held      2 pending`, `Reason` and `By`
  lines; with no reason there is no `Reason` line; a person (kind `user`) gets none of the four lines even when a `StoppedAgent` is passed.
- `test_admin_screen.py` (fake client, `stopped_agents` set, agent highlighted): the panel shows the flag and the held count exactly as the fake returned them (held 0 shows `0 pending`; no arithmetic);
  an agent not in the list shows `allowed`; `reload` calls `list_stopped_agents` once (`admin_calls`); a non-admin fake (`is_admin = False`) leaves the screen with the same error line the other lists give.
- `test_embedded_admin.py`: the embedded client's `list_stopped_agents()` returns `[]` on a fresh ledger and equals `agent_stop.list_stopped(conn, confidentiality.current_viewer())` (as
  `test_the_listing_agrees_with_the_services`); a non-admin actor is refused with `ForbiddenError`; with `agent_stop.list_stopped` patched by `monkeypatch`, the call receives
  `confidentiality.current_viewer()` and the `limit` it was given (141: the viewer is passed down, the TUI counts nothing); add `list_stopped_agents()` to the fake-versus-embedded `script` (one step, `[]` on both).
  Do not file a proposal in these tests (filing needs the agent grant that S1 introduces); the held count under a hidden record is walked in T04.

## Report requirements
Standard report plus: the snapshot pins; output of both commands (<= 5 lines each); one line saying the screen holds no count or filter of its own.

## Escalation triggers
Stop and write *Blocked* if the screen would need a count or a filter of its own; if `ApiClient.list_stopped_agents` differs from the interface above; if more than two snapshots change.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
