# P2-I2-T07a — readiness text module and screen

Status: staged (dispatch after T04c2 merges)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, read, confidentiality
Depends on: T04c2
Branch: `p2/i2-t07a-readiness-screen`
Worktree: harness-created under `/home/user/wt/i2/t07a` (from `p2/i2` head)

## Goal
`tl_tui/readiness_text.py` (Textual-free; TW3 reuses it) and `ReadinessScreen(client, project, number)`: the checks of one IWP as a `LogScreen`, one row per check, one row per `resolve_via` reference, Enter on a reference row opens that record. Models: P2-I1 T05a and T05d (`docs/tickets/P2-I1/`), skill `tui-layout`.

## Brief references (pasted; module design "IWP log, Readiness")
> Readiness (table Check, State, Resolve via; `n/a` counted apart).
Read: `client.get_iwp_readiness(project, number)` (T04c2) -> `iwp_id evaluated_at today ready checks` (no `facts_hash`); `CheckResult`: `name version state detail resolve_via count_ok count_total`; states `ok blocked n_a unknown`; `resolve_via` entries have `record_type`, `key` and (route model) `record_id`. D9: `n_a` counts as passing: `7/9` = 2 ok + 5 `n_a` + ... ; `readiness.engine.PASSING` is the frozenset (import it). Hidden refs are already dropped by the read (D32): the screen never filters, never looks one up.

## Interfaces (create; names exact)
```python
# readiness_text.py
READINESS_COLUMNS = ("Check", "State", "Passing", "Resolve via", "Detail")
READINESS_DROP = ("Detail", "Passing")
def readiness_rows(view, labels=None) -> list[tuple[tuple[str, ...], str | None]]   # (cells, record_id or None); a check with k refs gives k rows, the check cells on the first and `-` marks after; state text `ok`, `blocked`, `n/a`, `unknown`; Passing `<count_ok>/<count_total>` or `-`; Resolve via `<humanized type> <key>`; Detail cut 80
def readiness_summary(view) -> str      # `7/9 passing (2 ok, 5 n/a, 2 blocked) · Ready: no · evaluated 2026-11-07`; `unknown` counted when present; `Ready: yes`
def readiness_page(number, view, labels=None, technical=False, panel=False) -> Page   # identity `<number> · readiness`, state line, summary, the table as a Section; technical adds check versions
def not_evaluated_text(number) -> str   # `<number> has not been evaluated` (the screen shows it for the error too: one text for missing, hidden and never evaluated)
```
Keys: `F5` re-read, `Esc` back, Enter on a ref row -> `open_record(self, client, scope, project, actor, record_id)`; on a row with no ref: the detail in the panel. `KEY_HINTS` `Enter open  F5 reload  Esc back`.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/awp_text.py` lines 1-130, `widgets/cwp_register.py` (all), `widgets/log_screen.py` lines 96-225, `widgets/record_screen.py` (`open_record` only)
- `packages/tl-core/src/tl_core/readiness/types.py` (CheckResult, RecordRef), `packages/tl-modules/awp/src/tl_mod_awp/readiness/engine.py` (PASSING), `tests/fakes_iwp.py` (`seed_iwp`: the 9-check readiness), `tests/helpers.py` lines 1-60

## Allowed paths
- `packages/tl-tui/src/tl_tui/readiness_text.py` (create), `packages/tl-tui/src/tl_tui/widgets/readiness_screen.py` (create)
- `dev/accept/P2-I2/T07a.py` (create), `docs/reports/P2-I2/T07a.md` (create)
Palette, nav and the IWP screen key that opens this screen are glue (T07c).

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T07a.py            # no pytest
```
`T07a.py` (Textual pilot on `FakeClient` + `seed_iwp`): `PASS mount 80` and `PASS mount 170` (no overflow; Check not right of the second column; panel shows heading, state, summary at 170); `PASS counts` (seed readiness: summary says `7/9 passing (2 ok, 5 n/a, 2 blocked)`; `n/a` rows read `n/a`); `PASS refs` (a check with one ref gives its row; Enter calls `open_record` once with the ref's id: patch it); `PASS none` (`RecordNotFoundError` -> the `not_evaluated_text` line, no traceback); `PASS words` no 32-hex id and no `facts_hash` in any rendered line. Ends `T07a ok`.

## Escalation triggers
- Stop if the route model's ref lacks `record_id` (Enter cannot open it; say which model), or a fact needs a second read.

## Tests to add
None (S5 / T-screens twins hold the pytest).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; the `tui-layout` checklist answered line by line (7 lines). Subject `P2-I2-T07a: ...`; trailer is the attribution lines your harness requires, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
