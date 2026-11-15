# P2-PTW S1 — Module `permits`: schema, workflows, numbering, words, settings, type table, projectors, skeleton

kind: piece
review: full
branch: p2/ptw-s1-schema
worktree: /home/user/wt/ptw/s1
Depends on: `p2/ip` (after P2-QR S1 and P2-INSP S1 are merged there, or merge them in and regenerate). Gated: schema,
settings, access words (APPROVALS lines before merge). Labels: schema.
Merge rule (P2-QR README, fan-out): the first S1 with signed APPROVALS merges first; a later S1 merges `p2/ip`, re-runs
`just gen` and `just compat-update` and re-pins its counts. At most 2 heavy runs: PTW S1 starts when QR S1 or INSP S1 ends.

## Why
`docs/build-spec/module-designs/permits.md` §1, §3, §4, §5: a permit-to-work module does not exist. The brief expects
an IWP to link a permit (§7.1) and the readiness check `permits_planned` is a placeholder that answers `n_a`
(`packages/tl-modules/awp/src/tl_mod_awp/checks_na.py`). Four pieces and sixteen tickets are written against the
names, tables and states this piece creates. Additive only: a new module; nothing existing changes.

## Goal
1. **Schema** `schema/modules/permits/` (`module.yaml`, `permit.yaml`, `isolation.yaml`, `gas_test.yaml`,
   `events.yaml`; copy conventions from `schema/modules/quality/`). All three classes `tl:offline: none`.

   | Class | Table | Fields |
   |---|---|---|
   | `Permit` (`permits.Permit`) | `cur_permits_permit` | `permit_type` (enum `PermitType`: hot_work, confined_space, work_at_height, excavation, isolation, general; indexed), `for_record_id` (indexed; the confidentiality subject), `area` (≤ 64, indexed), `location_text` (≤ 120), `holder` (≤ 120), `requested_by`, `needed_from`, `needed_until` (dates), `approved_by`, `issued_by`, `issued_at`, `valid_until` (aware time, indexed), `precautions` (`tl:json`, default `[]`), `revalidation_count` (int ≥ 0, default 0), `last_revalidated_at`, `suspend_reason`, `handback_note`, `closed_by`, `reject_reason`, `cancel_reason` (≤ 300 each), `lapse_flagged_for` (aware time; set by the job's event) |
   | `Isolation` (`permits.Isolation`) | `cur_permits_isolation` | `point_text` (≤ 120), `point_record_id` (indexed; the confidentiality subject when set), `energy` (enum `EnergyKind`: electrical, mechanical, process, other), `method` (≤ 120), `lock_number`, `tag_number` (≤ 32 each), `applied_by`, `applied_at`, `verified_by`, `verified_at`, `removed_by`, `removed_at` |
   | `GasTest` (`permits.GasTest`) | `cur_permits_gas_test` | `permit_id` (indexed), `taken_at` (aware time, indexed), `tester` (≤ 120), `instrument_text` (≤ 64), `o2_pct`, `lel_pct`, `h2s_ppm`, `co_ppm` (decimals ≥ 0, null ok), `result` (enum `GasResult`: pass, fail), `note` (≤ 300) |

   The title and description of each record are on the envelope (the permit's description is the work description).
2. **Events** (`feed_policy: none`; every payload names `record_id`):
   `Permit.Requested` {permit_type, for_record_id, area, location_text, holder, needed_from, needed_until},
   `Permit.Approved`, `Permit.Rejected` {reason}, `Permit.Issued` {issued_at, valid_until, precautions},
   `Permit.Revalidated` {at, valid_until}, `Permit.Suspended` {reason, gas_test_id}, `Permit.Resumed` {at, valid_until},
   `Permit.HandedBack` {note}, `Permit.Closed`, `Permit.Cancelled` {reason}, `Permit.Lapsed` {valid_until} (job only),
   `Permit.IsolationLinked` {isolation_id}, `Permit.IsolationUnlinked` {isolation_id};
   `Isolation.Applied` {point_text, point_record_id, energy, method, lock_number, tag_number, applied_at},
   `Isolation.Verified` {verified_at}, `Isolation.Removed` {removed_at};
   `GasTest.Recorded` {permit_id, taken_at, tester, instrument_text, o2_pct, lel_pct, h2s_ppm, co_ppm, result, note}.
   Valid time (ADR-0026): tag `issued_at`, `at`, `applied_at`, `verified_at`, `removed_at`, `taken_at` with
   `tl:valid_time`; the rest go in `tests/tools/valid_time_baseline.toml` with a reason each.
3. **Workflows** (`schema/fixtures/workflows/`, every move `by_module`, no role guard):
   `permits-permit.yaml`: initial Requested; `approve` Requested → Approved; `reject` Requested → Rejected; `issue`
   Approved → Active; `revalidate` Active → Active; `suspend` Active → Suspended; `resume` Suspended → Active;
   `hand_back` Active → Handed back, Suspended → Handed back; `close` Handed back → Closed; `cancel` Requested →
   Cancelled, Approved → Cancelled. Final: Closed, Rejected, Cancelled. Lapsed is not a state (derived in S2).
   `permits-isolation.yaml`: initial Applied; `verify` Applied → Verified; `remove` Applied → Removed, Verified →
   Removed. Final: Removed. `GasTest` has no workflow.
4. **Numbering** (`schema/fixtures/numbering/patterns.yaml`, the `quality.PunchItem` form): `permits.Permit` `PTW`,
   `permits.Isolation` `ISL`, `permits.GasTest` `GAS`.
5. **Access words** (`schema/settings/access-words.yaml`, a `permits:` block): `permits.view: read`;
   `permits.request`, `permits.revalidate`, `permits.suspend`, `permits.handback`, `permits.isolation.apply`,
   `permits.gastest.record`: user; `permits.approve`, `permits.issue`, `permits.resume`, `permits.close`,
   `permits.isolation.verify`: controller. Twelve words.
6. **Settings** (`schema/settings/platform.yaml`; scopes `[platform, company, project]`, lockable):
   `permits.shift_hours` (int 12, 4..24), `permits.shift_start` (string `06:00`, pattern `^([01][0-9]|2[0-3]):[0-5][0-9]$`),
   `permits.gas_test.valid_minutes` (int 240, 15..1440), `permits.required_for_iwp` (bool false),
   `permits.gas.o2_min_pct` (decimal 19.5), `permits.gas.o2_max_pct` (23.5), `permits.gas.lel_max_pct` (5),
   `permits.gas.h2s_max_ppm` (5), `permits.gas.co_max_ppm` (25). Each description ends "Proposed default; the
   project's safety lead owns the value."
7. **Type table** `schema/fixtures/permits/types.yaml`: one entry per `PermitType` with `needs_gas_test` (bool),
   `needs_isolation` (bool), `max_days` (1 or 7) and `precautions` (a list of `{id, text ≤ 120}`), exactly the table
   of the design §3. Loaded by `tl_mod_permits/types_table.py` (`load_types() -> dict[str, TypeRule]`, a frozen
   pydantic model, read once from the packaged resource; an entry missing for an enum value, an unknown key or a
   duplicate precaution id is an error at load).
8. **Package** `packages/tl-modules/permits` (`tl-mod-permits`, `tl_mod_permits`; copy the skeleton of
   `packages/tl-modules/quality`): `pyproject.toml` (entry point `throughline.modules` / `permits`), `README.md`,
   `AGENTS.md`, `__init__.py` (`MODULE = "permits"`), `names.py` (record types, states, words, event names),
   `types_table.py`, `projectors/` (`permit.py`, `isolation.py`, `gas_test.py`; `Lapsed` sets `lapse_flagged_for`,
   `Revalidated` and `Resumed` set `valid_until` and clear nothing else), `module.py` `spec()` with `record_types`,
   `projectors`, `command_words={}`, `proposable=()`, no generic-command rows, no hook fields (S2 adds commands and
   hooks).
9. `just gen`, `just compat-update` (additive); commit sources and generated output together.

## Allowed paths
- `schema/modules/permits/**` (create); `schema/fixtures/workflows/permits-permit.yaml`, `permits-isolation.yaml`
  (create); `schema/fixtures/numbering/patterns.yaml` (three blocks); `schema/fixtures/permits/types.yaml` (create)
- `schema/settings/access-words.yaml` (the `permits:` block); `schema/settings/platform.yaml` (nine keys);
  `tests/tools/valid_time_baseline.toml` (lines); `docs/build-spec/specs/offline-classes.md` (three rows)
- `packages/tl-schema/src/tl_schema/generated/**` (`just gen` output only); `packages/tl-schema/compat/event-schemas.json`
- `packages/tl-modules/permits/**` (create, as listed in Goal 8, plus `tests/conftest.py`, `tests/test_module_spec.py`,
  `tests/test_projectors.py`, `tests/test_types_table.py`)
- root `pyproject.toml` (workspace source, test path, dependency line) and `uv.lock`; one dependency line
  `"tl-mod-permits"` in `packages/tl-{api,cli,mcp,tui}/pyproject.toml`
- `packages/tl-schema/tests/test_permits_schema.py` (create)
- Pinned lists, union form, each named in the report with old and new count: `packages/tl-schema/tests/test_offline_classes.py`
  (+3), `test_ddl.py`, `test_generate.py`, `test_ddl_views.py`, `packages/tl-core/tests/auth/test_access_words.py` (a
  `PERMITS` set of twelve added to the sum), `packages/tl-core/tests/test_numbering_config.py` (three patterns),
  `tests/services/test_modules.py` (module list), `tests/settings/test_phase2_keys.py` and
  `packages/tl-core/tests/test_settings_definitions.py` (nine keys), and any other test that fails only because the
  module, words or keys now exist
- `packages/tl-core/src/tl_core/feed/cards.py`: only if a test refuses the new quiet events, add their names to the
  list it names (the P2-PUNCH S1 precedent); say so in the report
- `docs/reports/P2-PTW/S1.md` (create)
Not allowed: commands, handlers, guards, rules, views, routes, CLI, MCP, TUI; `tl_core/modules.py`;
`tl_core/confidentiality.py` (S2); the awp module (S4); any other module.

## Tests to add
- `packages/tl-schema/tests/test_permits_schema.py`: three classes, tables and indexes; four enums and their values;
  seventeen event types with their payload fields; offline class `none` three times; the permit workflow loads with
  the moves above and rejects `Requested → Active`, `Suspended → Closed` and any move out of Closed, Rejected or
  Cancelled; the isolation workflow rejects any move out of Removed; keys `P123-PTW-0001`, `P123-ISL-0001`,
  `P123-GAS-0001`.
- `tests/test_types_table.py`: six entries, one per enum value; the flags equal the design's table (hot work and
  confined space need a gas test; confined space and isolation need an isolation; hot work and confined space are one
  day); a table with a missing type, an unknown key or a duplicate precaution id is refused.
- `tests/test_projectors.py` (events appended through the ledger, never a projection write): a permit through
  Requested, Approved, Issued, Revalidated, Lapsed, Suspended, Resumed, HandedBack, Closed gives the expected row at
  each step (`valid_until`, `revalidation_count`, `lapse_flagged_for`); isolation Applied, Verified, Removed; a gas
  test row; a rebuild of the three tables equals the live rows.
- `tests/test_module_spec.py`: the module loads; three record types; no commands, no proposable.

## Gate
`just check` (with `NODE_OPTIONS=--max-old-space-size=6144`); then, one run at a time:
`just gate packages/tl-schema/tests/test_permits_schema.py packages/tl-schema/tests/test_offline_classes.py packages/tl-schema/tests/test_ddl.py packages/tl-schema/tests/test_ddl_views.py packages/tl-schema/tests/test_generate.py packages/tl-schema/tests/test_compat.py packages/tl-schema/tests/test_valid_time_tag.py`
and
`just gate packages/tl-core/tests/auth/test_access_words.py packages/tl-core/tests/test_numbering_config.py packages/tl-core/tests/test_settings_definitions.py tests/settings/test_phase2_keys.py tests/services/test_modules.py tests/services/test_modules_offline.py packages/tl-modules/permits/tests`.
`just gate-pg packages/tl-modules/permits/tests`. Every existing path above was checked with `ls` on trunk @d4e92ffc;
the `permits` paths are created by this piece.

## Mutation cap
One sentinel plus at most 4 targeted mutants: the permit workflow allows `issue` from Requested; `resume` allowed
from Handed back; the projector leaves `valid_until` unchanged on Revalidated; the type table loads with a type
missing. 3 lines in the report.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines at `docs/reports/P2-PTW/S1.md`; first line: deviations or none; list
every pinned file changed with old and new count, and the final names (record types, states, events, words, setting
keys) as one table for S2 to S5 and the tickets. Commit `P2-PTW-S1: ...` with the session trailers; no model names
in committed text.
