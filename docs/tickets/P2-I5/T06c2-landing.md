# P2-I5-T06c2 — Landing: `tui.landing` read at sign-in

Status: staged (needs T06c1 merged and T06b merged: `app.py` is edited by both)
Tier: haiku
Kind: ticket
Review: full
Labels: tui
Depends on: T06c1, T06b
Branch: `p2/i5-t06c2-landing`
Worktree: harness-created under `/home/user/wt/i5/t06c2` (from `p2/i5` head)

## Goal
After sign-in a person who is foreman on an IWP lands on the IWP log filtered to mine, unless they chose otherwise. W3-6 as decided (D7): there is no foreman account role; the user-scope setting `tui.landing` (`default` or `iwp_mine`, `schema/settings/platform.yaml`) decides, and while the person has not set it (origin `default`) the landing resolves to `iwp_mine` when the person is foreman on any IWP.

## Brief references (pasted)
- `tl_tui/landing.py` (create, no `textual`): `landing(client: ClientInterface, project: str, actor: str) -> Literal["default", "iwp_mine"]`. `view = client.get_setting("tui.landing", user=actor)`; `view.effective.origin` is `"default" | "company" | "project" | "user"`. Origin `"default"` (nobody set it): `"iwp_mine"` when `client.list_iwps(project, foreman=actor, limit=1)` is not empty, else `"default"`. Any other origin: the value itself (`default` lands as before, even for a foreman). A `CLIENT_ERRORS` exception from either read (`tl_tui.errors`) is `"default"`: the landing never blocks the app.
- `TlApp` (`app.py`, `on_mount`, after the existing lines): `self.call_after_refresh(self._land)`; `_land` does nothing without a project (`project_of_scope(self.scope)` is None) or when a modal is open (`self._modal_open()`); else `if landing(self.client, project, self.actor) == "iwp_mine": self.push_screen(IwpRegisterScreen(self.client, project, mine=True))` (import inside the method, as `_push_awp`). Esc returns to the grid as for any pushed screen. Runs once per app start, not on reconnect.
- The summary of the opened log says `foreman <name>` through the existing `m` path (`iwp_summary(..., foreman=actor)`); no new text.
- No auth change, no role, no write: the setting is written in `about:config` (F9) by the person.

## Interfaces (verbatim from repo)
```python
# tl_tui/client.py ClientInterface
def get_setting(self, key, *, project=None, user=None) -> SettingView          # .effective.value, .effective.origin
def list_iwps(self, project, *, state=None, discipline=None, foreman=None, limit=200) -> list[IwpRow]
# tl_tui/widgets/iwp_register.py (T06c1)
class IwpRegisterScreen(LogScreen[IwpRow]): def __init__(self, client, project, *, mine: bool = False)
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/{app.py (150-200, 700-760), errors.py (CLIENT_ERRORS), widgets/iwp_register.py (1-100)}`, `schema/settings/platform.yaml` (130-145)
- `packages/tl-tui/tests/{fakes_settings.py (the `get_setting` fake and how a test sets a user value), fakes_iwp.py, test_awp_nav.py (1-60)}`

## Allowed paths
- `packages/tl-tui/src/tl_tui/landing.py` (create), `packages/tl-tui/src/tl_tui/app.py` (`on_mount` line and `_land`)
- `packages/tl-tui/tests/test_landing.py` (create), `packages/tl-tui/tests/fakes_settings.py` (only to let a test set an origin, union form)
- `docs/reports/P2-I5/T06c2.md`; consequential pins: any app test whose `FakeClient` now has a foreman IWP and lands on the log (list them; give the fake no foreman rather than changing assertions)

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_landing.py packages/tl-tui/tests/test_awp_nav.py packages/tl-tui/tests/test_palette.py packages/tl-tui/tests/test_live_app.py
```

## Tests to add
`test_landing.py`: pure `landing` over the fake: unset and a foreman -> `iwp_mine`; unset and none -> `default`; user-set `default` and a foreman -> `default`; user-set `iwp_mine` and no IWP -> `iwp_mine`; a company-set value is honoured; a raising client -> `default`. Pilot: the app mounts on the IWP log with `mine` on for a foreman (summary names the foreman) and Esc shows the grid; a plain user's app opens as before; no project: no push.

## Escalation triggers
- The fake `get_setting` cannot return an origin other than `default` (extend `fakes_settings.py` in union form and say so).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed. Commit subjects `P2-I5-T06c2: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
