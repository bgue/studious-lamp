# P2-PTW-T00 — Pure permit rules: shift end, effective state, gas result, issue blockers

Status: ready (dispatch after PTW S1 is merged to `p2/ip`; the provided test is committed)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, tests
Depends on: S1 (merged: package `tl_mod_permits` and its type table exist)
Branch: `p2/ptw-t00-ptw-rules`
Worktree: harness-created under `/home/user/wt/ptw/t00` (from `p2/ip` head)

## Goal
`tl_mod_permits.rules` holds the safety rules the permit handlers, the lapse job and every read share, as pure
functions: no database, no clock (the caller passes `now`), no settings read (the caller passes the values), no import
from `tl_core` or another module. A limit is never a constant in this file.

## Brief references (pasted)
> Issue is refused when the type needs a gas test and there is no passing test newer than `permits.gas_test.valid_minutes`,
> or needs an isolation and a linked isolation is not Verified, or a precaution is unticked. Lapsed: an Active permit
> whose `valid_until` has passed is shown as Lapsed (a derived word, not a state). Shifts: `permits.shift_start` (`06:00`),
> `permits.shift_hours` (12, 4..24). Gas limits (settings, caller-supplied): O2 min and max %, LEL max %, H2S max ppm, CO max ppm.

## Interfaces (final; create exactly these names)
```python
@dataclass(frozen=True)
class GasLimits: o2_min_pct: Decimal; o2_max_pct: Decimal; lel_max_pct: Decimal; h2s_max_ppm: Decimal; co_max_ppm: Decimal
def shift_end(at: datetime, shift_start: str = "06:00", shift_hours: int = 12) -> datetime
def effective_state(state: str, valid_until: datetime | None, now: datetime) -> str
def gas_result(limits: GasLimits, *, o2=None, lel=None, h2s=None, co=None) -> Literal["pass", "fail"]   # Decimal | None readings
def issue_blockers(*, needs_gas_test: bool, needs_isolation: bool, required_precautions: Sequence[str],
                   ticked_precautions: Sequence[str], gas_tests: Sequence[tuple[datetime, str]],
                   isolation_states: Sequence[str], gas_valid_minutes: int, now: datetime) -> list[str]
```
- `shift_end`: shifts are blocks of `shift_hours` counted from the most recent `shift_start` at or before `at` (same
  wall clock and tzinfo as `at`); the end is exclusive (an instant equal to an end belongs to the next shift); the last
  block before the next `shift_start` is short when `shift_hours` does not divide 24. `ValueError` for a naive `at`, a
  `shift_start` not `HH:MM` (24-hour, two digits), or `shift_hours` outside 4..24.
- `effective_state`: `"Active"` with `valid_until` at or before `now`, or with no `valid_until`, is `"Lapsed"`; every
  other state is returned unchanged. `ValueError` for a naive time.
- `gas_result`: unmeasured (None) readings are not tested; O2 fails below min or above max, the others above max;
  limits are inclusive (equal passes); `ValueError` for no readings at all or a negative reading.
- `issue_blockers` returns codes, in this order: gas (`gas_test_missing`, `gas_test_failed` when the newest test failed,
  `gas_test_stale` when the newest passing test is older than `gas_valid_minutes`, exactly equal is fresh; the newest
  test by time decides, whatever the list order), isolation (`isolation_missing` when none live, `isolation_unverified`
  when any live one is not `Verified`; `Removed` ones are ignored), then `precaution_unticked:<id>` in the order of
  `required_precautions`. Gas codes only when `needs_gas_test`; isolation codes only when `needs_isolation`.

## Context (read these, nothing else)
- `docs/tickets/P2-PTW/provided/T00_test_rules.py` (the test; copy it byte-identical)
- `schema/fixtures/permits/types.yaml`
may explore: (none)

## Allowed paths
- `packages/tl-modules/permits/src/tl_mod_permits/rules.py` (create)
- `packages/tl-modules/permits/tests/test_rules.py` (create: byte-identical copy)
- `docs/reports/P2-PTW/T00.md` (create)

## Acceptance
```
just check
just gate packages/tl-modules/permits/tests/test_rules.py
```
Expected: all pass, `gate: PASS`.

## Tests to add
The provided test only.

## Report requirements
Standard report; first line: test copy byte-identical or not (phrase 101).

## Escalation triggers
- Stop rather than change a provided test case, or hard-code a gas limit or a shift value.
- Stop if the type table has a state or precaution shape the signatures above cannot take.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
