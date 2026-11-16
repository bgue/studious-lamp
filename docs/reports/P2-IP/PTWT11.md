# Report — P2-PTW-T11 (dispatched as P2-IP-PTWT11)

Branch: `p2/ptw-t11-terminal`   Commit(s): `0f10396c` (code), then this report's commit.

## Deviations
- Commit subject is `P2-IP-PTWT11: ...` as the dispatch names it, not the ticket's `P2-PTW-T11: ...`.
- The trailer names my own model (Haiku 5.5), as the dispatch asks ("naming your own model"); the dispatch text said Opus 5.5.
- Worktree is `/home/user/wt/ip4/ptwt11` on `p2/ptw-t11-terminal` from `79e41ff0`, as the dispatch names it, not `/home/user/wt/ptw/t11` from `p2/ip-r3`.
- Base `79e41ff0` already holds PTW-T10 (client methods, `FakePermitSupport`), so the dependency is met.
- Read beyond the Context list, read-only: `details/`, `log_screen.py`, `layout.py`, `display.py` (signatures), `receipt_entry_text.py` (the envelope is built inline, as INSP-T10 does).
- Empty `Valid until` cell shows `-` as the ticket states; `tui-layout` says never `-` (see Open questions). Other empty values show `—`.
- `_send` also catches pydantic `ValidationError` (a blank reason passes the form, then fails `_text`) and shows it on the status line. The ticket does not name this; without it the screen would crash.
- The `a` area cycle takes its areas from unfiltered loads only, so filtering by state or type does not shrink the cycle.

## Changed files
- `packages/tl-tui/src/tl_tui/permit_text.py` (new): `PERMIT_COLUMNS`, `PERMIT_DROP`, `PERMIT_RIGHT`, `ACTIONS` (the state table), `permit_cells`, `permit_summary`, `permit_page`, `permit_count`.
- `packages/tl-tui/src/tl_tui/widgets/permit_log.py` (new): `PermitLogScreen`, `PermitScreen`, `permit_types()`.
- `packages/tl-tui/src/tl_tui/commands.py`: one `permits` `AppCommand` row.
- `packages/tl-tui/src/tl_tui/app.py`: import, `permits` entry in the `_push_awp` screens dict, `action_permits`.
- `packages/tl-tui/tests/test_permit_text.py` (new, 15 tests), `test_permit_screens.py` (new, 18 tests), `test_permit_nav.py` (new, 2 tests).
- Pins: `test_palette.py` and `test_awp_nav.py` pass unchanged; no pin edits were needed.

## Commands and output
```
$ uv run ruff format --check <the four paths>
176 files already formatted
$ uv run ruff check <the four paths>
All checks passed!
$ uv run pyright <seven files>
0 errors, 0 warnings, 0 informations
$ uv run pytest -q packages/tl-tui/tests/test_permit_text.py
15 passed in 1.12s
$ uv run pytest -q packages/tl-tui/tests/test_permit_screens.py packages/tl-tui/tests/test_permit_nav.py
19 passed in 13.19s
$ just gate <five test files>
part 1: exit 0, 77 passed in 32.14s
gate: PASS
```

## Tests added
- `test_permit_text.py`: columns and drop order; cells per state (type humanized, `Valid until`, holder by name); summary by state with STOP and with a filter; identity and state line per state; STOP in Lapsed and Suspended; no 32-hex id; gas tests newest first, no readings, `none taken`, at most five; approvals and history lines; the state table equals the command docstrings.
- `test_permit_screens.py`: 80 and 170 columns without overflow (Subject left of State); `s`, `t`, `a`, `m` counts; Enter pushes `PermitScreen`; `a` on Requested asks and sends `ApprovePermit` (`PTW-1`, version 1); `s` on Requested does nothing; `s` on Active asks and sends `SuspendPermit`; `a` on Active does nothing; `r` on Suspended sends `ResumePermit`; blank reason sends nothing; refusal on the status line; unknown key gives `! ` status, no traceback.
- `test_permit_nav.py`: palette lists `permits`; choosing it shows `PermitLogScreen`.

## tui-layout checklist
1. Glance: where, which permit, state (with STOP for a stop), what next: yes.
2. Identity line first (`key · subject`), state line second: yes.
3. Sections named (Where, Work, Approvals, Gas tests, History), in need order, one blank line apart: yes.
4. Tiers: version is technical only; everyday facts are property lines; no extended properties on this screen: yes.
5. Log columns: Number, Subject, State first; Subject before State at 80 and 170; no constant or duplicate column; short type names: yes.
6. Panel: summary line (holder, area, for) under the state line; repeats only the holder (in Work, as on the punch page): yes.
7. Empty values: `—` in fixed sections, `none taken` in the gas list; `Valid until` is `-` (ticket): partly, see Open questions.

## Learnings (proposed)
- The ticket's `-` for an empty `Valid until` conflicts with `tui-layout` ("never show `-`"); INSP-T10 hit the same conflict for `Result`. A ticket template should name one dash.
- `FakeClient.permit_command` records into `punch_commands` (PTW-T10 said so too); the name misleads, a `permit_commands` list would be clearer.

## Open questions / Blocked
- `Valid until` empty cell: ticket says `-`, `tui-layout` says `—`. I followed the ticket. Supervisor to choose one and pin it in both places.
- State line: Lapsed and Suspended omit type and time (ticket example); Active shows both; other states show `State · type`. Confirm for those.
