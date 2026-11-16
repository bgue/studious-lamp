# P2-PTW-S2 — Permit lifecycle: ten commands with guards, the hooks, the three subject rows

kind: piece
review: full
branch: p2/ptw-s2-lifecycle
worktree: /home/user/wt/ptw/s2
Base: `p2/ip` with `p2/x4` merged (`p2/ip-x4`, made by the orchestrator). Merge note: **waits for X4 on trunk**. Order: third of three S2s (after QR S2 and INSP S2: merge them, or `p2/ip` after them, before your row commit).
Depends on: PTW S1 and T00 (merged: `names.py`, `types_table.py`, `rules.py`, projectors, words, settings). Read first: `docs/tickets/P2-IP/S2-common.md`.
Gated: access-worded commands, separation of approver, issuer and verifier, `confidentiality.py` subject parts (APPROVALS lines at merge). Labels: core, access, confidentiality, security, safety.

## Why
`docs/build-spec/module-designs/permits.md` §3-§5, §9 and `docs/tickets/P2-PTW/README.md`. The records, workflows, words, settings, type table, projectors and the pure rules exist. Nothing runs a permit. S3, S5, T01, T04-T09 are written against the names this piece freezes.

## Goal (every model has the base envelope, `extra="forbid"`, `expected_version: int | None` on state commands, texts cleaned with `tl_core.text`; actor fields come from the context, never an input)
| Command | Word (table word) | Rule |
|---|---|---|
| `RequestPermit` | `permits.request` (user) | `permit_type`, `for_record_id` (readable by the actor; hidden, missing, other project: one text `no record with that id`), `area`, `location_text`, `work_description`, `holder`, `needed_from`, `needed_until`; key by the numbering pattern; state Requested |
| `ApprovePermit`, `RejectPermit` | `permits.approve` (controller) | Requested only; never the requester (fixed message); reject needs a reason |
| `IssuePermit` | `permits.issue` (controller) | Approved only; `rules.issue_blockers` over the type table, the linked isolations' states, the gas tests and `permits.gas_test.valid_minutes`; refused with a fixed text naming the blocker codes; `valid_until` = `rules.shift_end(now, permits.shift_start, permits.shift_hours)`, or `needed_until` if sooner; ticked precautions stored |
| `RevalidatePermit` | `permits.revalidate` (user) | Active or Lapsed (`rules.effective_state`); holder or a holder of a controller word; a gas-test type needs a fresh passing test first (the issue guard again); `valid_until` moves to the end of the next shift and never past the type's `max_days` from issue; `revalidation_count` + 1 |
| `SuspendPermit` | `permits.suspend` (user) | Active or Lapsed, `reason` 1..300; anyone with the word |
| `ResumePermit` | `permits.resume` (controller) | Suspended only; **the same issue guards run again** (one function, not a copy) |
| `HandBackPermit` | `permits.handback` (user) | Active, Lapsed or Suspended; holder or a controller; `handback_note` required |
| `ClosePermit` | `permits.close` (controller) | Handed back only |
| `CancelPermit` | `permits.close` (controller) | Requested or Approved, `reason` |
The clock is a parameter: handlers take `now` from the unit of work's clock (`tl_core.util.utcnow` as other handlers do), tests pass a fixed clock; the settings are read with `tl_core.settings.resolver.value_of` per project scope. A Lapsed permit is
never a workflow state (S5's job flags it). A wrong state is a fixed message naming the states the command needs. Each move is one unit of work, `by_module=True`, through the workflow engine.
Closed, Rejected and Cancelled accept nothing.

1. **Code** in `tl_mod_permits/`: `commands.py`, `handlers/permit.py` (+ `handlers/common.py`; copy the shape of `tl_mod_quality/handlers/`), `guards.py` (`issue_guards(conn, permit, now) -> list[str]`: read type rule, linked isolation states, gas tests;
   used by Issue and Resume and Revalidate), `errors.py` (subclasses of core error classes, common rules), `actions.py` only if the quality `actions` hook pattern fits (otherwise say so; not required).
2. **Hooks and surfaces** per the common rules: `module.py` `COMMANDS` (ten rows, one row class with `meta`), `PROPOSABLE = (ProposableCommand("propose_permit", RequestPermit, handle_request_permit, "user"),)`,
   `commands="tl_mod_permits.module:COMMANDS"`, `read_routers=("tl_mod_permits.routes:router",)`, `tools=("tl_mod_permits.tools:register_tools",)`, and **three CLI groups**
   `cli_groups=("tl_mod_permits.cli:permit_app", "tl_mod_permits.cli:isolation_app", "tl_mod_permits.cli:gastest_app")` (group names `permit`, `isolation`, `gastest`; T04 and T05 share `permit_app` in two files: stub `cli.py` here
   imports nothing from them; say in the report how the later split is made without both tickets editing `cli.py`: the recommended shape is `cli.py` holding the three `Typer` objects and each ticket adding commands in its own file that registers on them by import at the bottom of `cli.py`, which S2 pre-writes as three one-line imports of modules it creates empty).
   Check `tl permit`, `tl isolation`, `tl gastest` clash with no existing group. `pyproject.toml`: `fastapi`, `mcp`, `typer` only.
3. **Marks and decided** (module outside `IN_TREE_SURFACES`: marks in the row `meta`): all ten `excluded:reserved` (decision D-PTW1: permits are safety acts; a policy that auto-accepts a permit request is an owner decision, so `RequestPermit` has its
   agent proposable row and is still `excluded:reserved`; flipping it is a one-line `meta` change). `tests/tools/proposable_exclusions.toml` (append): the nine other commands, reasons "act: a permit decision is the controller's" or "person acts directly".
4. **Subject rows** in `tl_core/confidentiality.py` (this piece adds all three PTW rows so S3 never touches the file), appended after INSP's: `("permits.Permit", "cur_permits_permit", "id", "for_record_id")`,
   `("permits.Isolation", "cur_permits_isolation", "id", "point_record_id")`, `("permits.GasTest", "cur_permits_gas_test", "id", "permit_id")`. Comment: a gas test is hidden through its permit (second hop reaches the permit's `for_record_id`);
   an isolation with no `point_record_id` is its own subject and stays at the lowest class. Test `tests/confidentiality/test_ptw_rows.py` (rows seeded through ledger events as the S1 projector tests do): a permit and its gas test on a
   restricted record are absent for the five readers in reads, counts and feed; present for the cleared; a hidden permit and a missing id answer the same text on `RequestPermit`-style lookups and on `ApprovePermit`; the join-budget test still passes on both adapters.
5. **Provided test of T01** (plan-check F8): write `docs/tickets/P2-PTW/provided/T01_test_views.py` for `tl_mod_permits/views.py`, lint-clean at `packages/tl-modules/permits/tests/test_views.py` (ruff format, ruff check, pyright run there).
   Pin: `permit_list`, `permit_detail`, `permit_counts`, `permit_board(area)`, `permits_for(conn, record_id, *, viewer=LOWEST)`, `export_rows(rows, fmt)` for `csv` and `jsonl`; `Lapsed` shown in place of `Active` through `rules.effective_state` with the clock a parameter;
   viewer defaults to the lowest clearance; the hidden filter before LIMIT and before counting, **the board's counts included**; a hidden record reads as no rows and zero counts. `views.py` is a stub (names raise `NotImplementedError`); red until T01.

## Provided tests (copy byte-identical)
`docs/tickets/P2-IP/provided/S2_ip_rules.py` to `tests/services/ip_rules.py` (identical to the copy of the earlier S2s: `cmp` it if present); `S2_test_ptw_rules.py` to `tests/services/test_ptw_s2_rules.py` (S3 adds its six names to that test in its own piece).
Own tests in `packages/tl-modules/permits/tests/`: `test_permit_commands.py` (one behaviour per table row; approver differs from requester; issue refused by each blocker code and passes when clean; revalidate bounded by `max_days`; resume re-runs the guards;
suspend by any user; hand back needs the note; wrong states), `test_issue_guards.py`, `test_permit_visibility.py`, `test_permit_exclusions.py`, `test_module_spec.py` (updated: ten commands, four hook kinds, refs start with `tl_mod_permits`), a `permit_world.py` helper.

## Allowed paths
- `packages/tl-modules/permits/**` (source, tests, `pyproject.toml`; README and AGENTS lines for the new files)
- `packages/tl-core/src/tl_core/confidentiality.py` (the three tuples and their comment), `tests/confidentiality/test_ptw_rows.py`
- `tests/services/{ip_rules.py,test_ptw_s2_rules.py}`, `tests/tools/proposable_exclusions.toml` (append), `docs/tickets/P2-PTW/provided/T01_test_views.py`
- the three baseline pins and `uv.lock` of the common rules, `docs/reports/P2-PTW/S2.md`, `dev/accept/P2-PTW/S2.py` (SQLite, `PASS <check>` lines, final `S2 ok`, clock fixed)
Read-only: schema, `tl_api`, `tl_cli`, `tl_mcp`, other modules.

## Acceptance (once each, one at a time)
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-modules/permits/tests/test_permit_commands.py packages/tl-modules/permits/tests/test_issue_guards.py
just gate packages/tl-modules/permits/tests/test_permit_visibility.py packages/tl-modules/permits/tests/test_permit_exclusions.py packages/tl-modules/permits/tests/test_module_spec.py packages/tl-modules/permits/tests/test_rules.py
just gate tests/services/test_ptw_s2_rules.py tests/services/test_module_conformance.py tests/services/test_module_hooks.py tests/tools/test_registry_by_hooks.py
just gate tests/confidentiality/test_ptw_rows.py tests/confidentiality/test_forms_rows.py
just gate packages/tl-cli/tests/test_module_cli_groups.py packages/tl-mcp/tests/test_module_tool_hooks.py
just gate packages/tl-api/tests/test_module_hooks_api.py
just gate-pg packages/tl-modules/permits/tests/test_permit_commands.py tests/confidentiality/test_ptw_rows.py
uv run python dev/accept/P2-PTW/S2.py
```

## Mutation (sentinel and at most 5, in this worktree, 3 lines in the report)
Sentinel: `IssuePermit` allowed from Requested. Targets: approver may equal requester; `issue_blockers` skipped on resume; `valid_until` not capped by `max_days` on revalidate; the `GasTest` row removed from `SUBJECT_LINKS`; a hidden `for_record_id` refusal names the record.

## Report
`docs/reports/P2-PTW/S2.md` (<= 60 lines): deviations first; pins changed with old and new count; the CLI file split; marks and exclusions; gate output (<= 5 lines per command); mutation 3 lines; final names the tickets need (`COMMANDS`, command models,
handler names, `issue_guards`, `permit_world`). Builder return <= 15 lines. Commit `P2-PTW-S2: ...`.
