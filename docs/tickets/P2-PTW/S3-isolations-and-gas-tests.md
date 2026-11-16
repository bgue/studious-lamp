# P2-PTW-S3 — Isolations and gas tests: six commands

kind: piece
review: full
branch: p2/ptw-s3-isolations-gas
worktree: /home/user/wt/ptw/s3
Base: `p2/ip-r3` (PTW-S2 merged; hooks in the tree). Merge note: **waits for X4 on trunk** like every merge into `p2/ip` (D8); build, gate and review may start now.
Depends on: PTW S1, T00, S2 (merged: `names.py`, `rules.py`, `guards.py`, `handlers/common.py`, `handlers/permit.py`, projectors `isolation.py`, `gas_test.py`, `tests/permit_world.py`).
Gated: access-worded commands, separation of applier and verifier, a safety rule (a failing gas test stops work), confidentiality of a shared record (APPROVALS lines at merge). Labels: core, access, confidentiality, security, safety.

## Why
`docs/build-spec/module-designs/permits.md` §4-§5, §9 and `docs/tickets/P2-PTW/README.md`. S2 runs the permit; `guards.issue_guards` already reads linked isolations from the permit's own `Permit.IsolationLinked` and `Permit.IsolationUnlinked` events and gas tests from `cur_permits_gas_test`; nothing writes those records yet (the world helper seeds them through ledger events). T02, T03, T06 and the demo are written against the names this piece freezes.

## Goal (base envelope, `extra="forbid"`, `expected_version: int | None` on state commands, texts cleaned with `tl_core.text`; the actor is always the context actor, never a field)
| Command | Word (table word) | Mark | Rule |
|---|---|---|---|
| `ApplyIsolation` | `permits.isolation.apply` (user) | `excluded:reserved` | `point_text` (<= 120), `energy` (`names.ENERGY_KINDS`), `method` (<= 120), `lock_number`, `tag_number`, optional `point_record_id` (readable by the actor; hidden, missing, other project: one text `no record with that id`). Key `P123-ISL-0001` by the S1 pattern; state Applied; `applied_by`, `applied_at` from the context and the clock of `handlers.common.now()` |
| `VerifyIsolation` | `permits.isolation.verify` (controller) | `excluded:reserved` | `isolation`; Applied only; never the person who applied it (fixed message); `verified_by`, `verified_at` |
| `RemoveIsolation` | `permits.isolation.apply` (user) | `excluded:reserved` | `isolation`; Applied or Verified; **dependency check**: refused while any permit whose events link it (and not unlink it) is Approved, Active or Suspended (shown Lapsed counts as Active). The refusal names a visible permit by key and a permit the actor cannot see only as `a permit you cannot see` (no key, count or type), same text however many hidden ones |
| `LinkIsolation`, `UnlinkIsolation` | `permits.isolation.apply` (user) | `excluded:reserved` | `permit`, `isolation`; appends `Permit.IsolationLinked` / `Permit.IsolationUnlinked` on the permit's stream; the permit and the isolation must both be readable by the actor (one text for a hidden or missing one); refused while the permit is Active or Lapsed (fixed message); link to a Removed isolation refused; linking twice or unlinking an unlinked one is a fixed message, not a second event |
| `RecordGasTest` | `permits.gastest.record` (user) | `excluded:reserved` | `permit`, `instrument_text` (<= 64), optional `taken_at` (default the clock; not in the future), readings `o2_pct`, `lel_pct`, `h2s_ppm`, `co_ppm` (at least one; Decimal, not negative, bounded), `note`. `result` is computed by `rules.gas_result` against the five limits read from the settings `permits.gas.*` with `value_of` (project scope); a `result` field is refused as an unknown field. Key `P123-GAS-0001`. Permit must be Approved, Active, Lapsed or Suspended (not final). **On `fail` against an Active or Lapsed permit whose type needs a gas test (`guards.NEEDS`) the permit is suspended in the same unit of work** (`Permit.Suspended` with the fixed reason `gas test failed`, through `handlers.common.move`), without the suspend word: the safety rule outranks the actor's words; a fail on any other permit state records the test only |
Marks: the six are `excluded:reserved` in the row `meta` (safety acts; same decision as D10); `tests/tools/proposable_exclusions.toml` gets six entries (append, one commented block). No agent proposable row. `RecordGasTest` is also refused for an agent token by the common path (`agent_must_propose`).

## Where
1. **Code** in `tl_mod_permits/`: `iso_commands.py` (the six models; `commands.py` of S2 is not edited), `handlers/isolation.py`, `handlers/gas_test.py` (copy the shape of `handlers/permit.py`), `errors.py` additions (subclasses of core error classes S2 already uses; fixed texts), `module.py` `COMMANDS` gains the six rows and `command_words` follows (one row class, `meta`). `guards.py` gets one helper for the dependency check (`dependent_permits(conn, isolation_id) -> list[Mapping]`) beside `linked_isolations`.
2. **No surface file is touched**: `cli*.py`, `routes.py`, `tools.py`, `views.py` belong to the tickets. The six commands reach `POST /commands/<Name>` through the hook; pins move by union (`OLD_COMMANDS`, `route_order.txt`, openapi), listed in the report.
3. **Provided test of T02** (plan-check F8): write `docs/tickets/P2-PTW/provided/T02_test_iso_views.py` for `tl_mod_permits/iso_views.py`, lint-clean at `packages/tl-modules/permits/tests/test_iso_views.py` (ruff format, ruff check, pyright run there). Pin: `isolation_list(conn, scope, *, state=None, energy=None, limit=100, viewer=LOWEST) -> IsolationPage`, `isolation_detail(conn, scope, key, *, viewer=LOWEST) -> IsolationDetail | None` (with the keys of the permits that depend on it, `depends` count only for permits the viewer can read), `gas_tests_for(conn, permit_id, *, viewer=LOWEST) -> list[GasRow]` (newest first), `gas_export_rows(rows, fmt)` and `isolation_export_rows(rows, fmt)` for `csv` and `jsonl`; an isolation with a `point_record_id` is hidden when the point is; the viewer defaults to the lowest clearance; the hidden filter before LIMIT and before counting. `iso_views.py` is a stub (names raise `NotImplementedError`); red until T02.
4. The numbering patterns, words and settings exist from S1; if one is missing, stop (escalation), do not add schema.

## Provided tests
Own tests in `packages/tl-modules/permits/tests/`: `test_isolation_commands.py` (one behaviour per row: apply, verify by another person, applier cannot verify, remove refused by each of Approved, Active, Suspended, Lapsed and allowed after Closed or unlink, the hidden-permit text is identical for one and for three hidden permits, link and unlink guards), `test_gas_commands.py` (pass and fail for each reading at, just under and just over each limit, `result` refused as a field, auto-suspend on fail for a gas-test type and not for `general`, the suspended permit then fails `ResumePermit` until a fresh pass, a test dated in the future refused), `test_iso_visibility.py` (hidden point, hidden permit, the five readers on the six commands), `test_iso_exclusions.py`, `test_module_spec.py` (updated: sixteen commands). Add the six names to `tests/services/test_ptw_s2_rules.py` only if it lists commands by name (otherwise leave it); append `S3` checks to `dev/accept/P2-PTW/S2.py`'s pattern as `dev/accept/P2-PTW/S3.py` (SQLite, `PASS <check>` lines, final `S3 ok`, clock fixed).

## Allowed paths
- `packages/tl-modules/permits/src/tl_mod_permits/{iso_commands.py,errors.py,guards.py,module.py}`, `handlers/{isolation.py,gas_test.py}`, `packages/tl-modules/permits/tests/**`
- `tests/tools/proposable_exclusions.toml` (append), `docs/tickets/P2-PTW/provided/T02_test_iso_views.py`
- the three baseline pins, `docs/reference/openapi.json`, `docs/reference/openapi.baseline.json`, `packages/tl-api/tests/expected/route_order.txt` (union lines only), `docs/reports/P2-PTW/S3.md`, `dev/accept/P2-PTW/S3.py`
Read-only: everything else (schema, `tl_core`, surfaces, other modules). `tl_core/confidentiality.py` is not edited: S2 added the three rows.

## Acceptance (once each, one at a time; whole-repo pyright is OOM-killed on this box: run `just check` only when no other heavy run is live, else ruff plus pyright on `packages/tl-modules/permits` and the named test files)
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-modules/permits/tests/test_isolation_commands.py packages/tl-modules/permits/tests/test_gas_commands.py
just gate packages/tl-modules/permits/tests/test_iso_visibility.py packages/tl-modules/permits/tests/test_iso_exclusions.py packages/tl-modules/permits/tests/test_module_spec.py
just gate packages/tl-modules/permits/tests/test_permit_commands.py packages/tl-modules/permits/tests/test_issue_guards.py
just gate tests/services/test_module_conformance.py tests/services/test_module_hooks.py tests/tools/test_registry_by_hooks.py
just gate packages/tl-api/tests/test_module_hooks_api.py
just gate-pg packages/tl-modules/permits/tests/test_isolation_commands.py packages/tl-modules/permits/tests/test_gas_commands.py
uv run python dev/accept/P2-PTW/S3.py
```

## Mutation (sentinel and at most 5, in this worktree, 3 lines in the report)
Sentinel: `RemoveIsolation` ignores a dependent Active permit. Targets: verifier may equal applier; a failing gas test does not suspend; a reading exactly at a limit judged `fail` (or over it `pass`); the hidden-permit refusal names its key; `LinkIsolation` allowed on an Active permit.

## Report
`docs/reports/P2-PTW/S3.md` (<= 60 lines): deviations first; pins changed; marks and exclusions; how the dependency check finds dependents (events versus a table) and its statement count; gate output (<= 5 lines per command); mutation 3 lines; final signatures T02, T03 and T06 need (the six models, `dependent_permits`, handler names). Builder return <= 15 lines. Commit `P2-PTW-S3: ...`.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
