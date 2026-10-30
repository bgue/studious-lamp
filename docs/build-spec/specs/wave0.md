# Spec — Phase 2 wave 0: roles, offline classes, readiness contract, targets by entry point, tools (P2-W0)

Status: v0.1, 2026-10-30, planner tier. Sources: `08-phase2-plan.md` §0.2 wave 0; `specs/roles-mvp.md` (P2-RM);
`specs/offline-classes.md` (P2-OC); `phase2-contracts-draft.md` §1, §7; skill `subagent-throughput-process` rules 8,
12 and Appendix A1–A3; `module-designs/OWNER-DECISIONS-2026-10-30.md` (answers 1–18); plan check (Code 92) of
`m3-wbs-cwp.md` and `m4-materials.md`, F1–F11. One increment, `docs/tickets/P2-W0/STATE.md`, two streams and a ticket
slot. **Where this file and the roles or offline spec differ, this file wins** (it carries the owner answers).

## 1. Why this wave, what it unblocks
The plan check found none of wave 0 in the tree (F1): no `tl_core/readiness`, no `awp.*`/`materials.*` keys, no A1–A3
tools, roles and offline specs unbuilt. M3 (P2-I1) and M4 (P2-I3) both depend on all of it, and M4 also depended on
M3's load targets (F2). After P2-W0 is DONE: per-module roles decide every command; every record type carries an
offline class; the frozen readiness contract, its loader and its contract harness exist; Phase 2 reserved prefixes
and settings keys are in; loader and publish targets are found by entry point; the three relay tools exist. Wave 1
(M3, M4, web increment 1) then starts on one trunk with no shims.

## 2. Owner answers applied to the core specs
- **Roles** (answers 1–4): `document_controller` derives `superuser` of documents, correspondence and schedule (no
  longer proposed); a superuser grant gives no restricted read (ADR-0016 unchanged); module roles do not filter reads;
  only admins grant. `roles-mvp.md` §12 is closed.
- **Fine access words as data** (decision 1, plan check F1): module specs name words such as `awp.cwp.release`.
  `schema/settings/access-words.yaml` (W0-B1) maps each to a role-table word: `{version: 1, words: {awp.view: read,
  awp.cwp.edit: user, awp.cwp.release: controller, …}}`, one row for every word of `m3-wbs-cwp.md` §3 and
  `m4-materials.md` §3. `tl_core.auth.access_words.load_access_words()` and `table_word(word)`; an unknown or duplicate
  word is an `AccessWordError` at start-up (fail closed). `ModuleSpec.command_words` values are a table word
  (`user`, `controller`) or a fine word listed there. **Plan check F1:** fine words are read in many places (`tl_api.commands`
  `Access` literal and `action_for`/`controller_actions`/`access_of`, OC `capture_allowed`, CLI `require_command`, the
  embedded gate), so RM-S2 normalises fine → table word **once**, in `command_index()` (every other reader gets a table
  word and never sees a fine one), and widens `Access` to accept a fine word at declaration.
  The richer role model later grants fine words directly, with no schema or event change.
- **Company grants for materials** (answer 14): `GrantModuleRole.project` also takes `company`, accepted only for a
  module whose `ModuleSpec.company_roles` is true (materials only in Phase 2; otherwise 422 `no_company_roles`).
  Precedence step 3 of `roles-mvp.md` §4 becomes: scope `company` → explicit `company` grants for that module when
  it declares `company_roles`, else derived (registry and schema commands unchanged). RM-S1 builds it.
- **Add property** (same-day decision): after RM-S2 the unadopted-set gate asks `holds_word(…, "controller")` on the
  record's module and project instead of `admin`; a one-line change for whoever owns that work (NEXT item, no ticket).
- **Offline** (answers 5–6): the class table of `offline-classes.md` §4 is approved as written (`core.Record` and
  `engineering.Tag` `full`, `documents.ReviewCycle` `none`); "a `controller`, `admin` or `company` command is never
  captured offline" is firm. Owner answer 17 needs no new mechanism: `materials.StockLot` is `draft_only` with
  `offline_drafts = {IssueStock, TransferStock, ReturnStock}` (wave 1 declares it).
- **Web** (answers 7–9) shape wave 1 (`phase2-wave-plan.md`); nothing in wave 0.

## 3. W0-B1: readiness contract, reserved prefixes, settings keys, access words
- `packages/tl-core/src/tl_core/readiness/{__init__,types,registry}.py`: `types.py` is `phase2-contracts-draft.md` §1
  verbatim (frozen; change only by orchestrator decision); `registry.load_checks() -> dict[str, ReadinessCheck]`
  (entry-point group `throughline.readiness_checks`; a plugin that fails to load raises at first use; two checks with
  one name raise). `tl_core/readiness/harness.py::check_readiness_contract(check, world)` (plan check F6: exported from the package, not from
  a test module) ships as the harness the contract names (no write on a read-only connection, bounds, fixed detail, `n_a` for a missing
  dependency, `watches` names existing types) and `tests/contract/test_readiness_contract.py` calls it on one inline `n_a` sample check (written by W0-B1, run at the end).
- `tl_core/services/reserved.py`: correlation prefixes `ready:`, `rollup:`, `progress:`; source prefix `job:`
  (contracts §7). The body-model check and the API walk pick them up unchanged.
- `schema/settings/platform.yaml` (one gated change): `awp.iwp.ready_lead_weeks` (4), `awp.backlog.target_weeks` (4),
  `awp.iwp.size_hours` ([60, 850]), `awp.release.signoff_roles` (`[superuser]`, roles of the role table; proposed,
  P2-Q2 superseded by decision 1), `awp.release.allow_unknown_checks` (false), `awp.rules_of_credit.set` (empty),
  `awp.constraint.aging_days` (14), `awp.constraint.auto_raise` (true), `awp.constraint.default_owners` ([]),
  `materials.receipt.mtr_required_categories` ([]; a project lists `ItemCategory` codes),
  `scaffold.inspection.interval_days` (7); scopes and `lockable` per brief §30.1 (P2-Q9 option A); defaults the brief does not give are proposed.
- `schema/settings/access-words.yaml` and `tl_core/auth/access_words.py` (§2).
- **R-P2-3 is already closed** by P1-SEC1 (ADR-0013 addendum): `request_model` refuses `actor_roles` through
  `refuse_role_claim`, walked by `packages/tl-api/tests/test_api_workflow_roles.py`. W0-B1 re-runs that file only.
- Contracts §2, §3, §5 skeletons are not built here: their first users (P2-I2, P2-I4-A, P2-I5) build them against the
  frozen draft (divergence from plan §0.2, which put all of §1–§5 in W0-B1).

## 4. W0-B2: targets by entry point (load and publish)
- Load (`tl_mod_legacy`): `TargetKind` becomes a registered name; group `throughline.load_targets`; built-ins `tags`
  and `documents` registered by the legacy package's own `pyproject.toml` entry points (plan check F4: W0-B2 does not
  touch `tl_mod_legacy/module.py`, which RM-S2 owns for the `command_words` line); a target declares `scope: project | company`
  (`tl load open --company` for company targets; loads stay admin-only, answer 12); a generic column-mapping form for
  module targets; a duplicate name is a `ModuleLoadError`; `tl load targets` lists name, module, scope.
- Publish (`tl_mod_documents.derivation`): `publish.py` refactored to targets found by `throughline.publish_targets`
  with the same shape; built-ins `tags`, `documents`; create-only and exact compensation unchanged (ADR-0014).
- Proof that nothing in Phase 1 moved: the P1-I3 and P1-I8 demos rerun green on both adapters.

## 5. Tools A1–A3 (skill Appendix A, Haiku, `review: lite`)
`dev/state.sh` (A1), `dev/review-pack.sh` (A2), `dev/relay-lint` (A3), each with its own test under **`tests/tools/`** (plan check F5: `dev/tests/` is outside `testpaths`) that
pins the output on a fixture git repository in `tmp_path` (Appendix A is the acceptance). The ticket writes the test
file; it runs in the end run (tests are deferred), and the ticket's own acceptance is `just check` plus a smoke command. The `just state|review-pack|relay-lint` recipe lines are supervisor glue (one shared `justfile`).

## 6. Pieces and tickets
B = builder piece (Sonnet, one shot, `review: full`); H = Haiku ticket. Every row's Allowed paths include
`docs/reports/P2-W0/<id>.md` and its acceptance script `dev/accept/P2-W0/<id>.py` (SQLite, one `PASS` per check, exit
0). **Tests are deferred** (owner, r1): pieces leave reference, stub, acceptance script and, where a row says so, a test
file that is **written but not run**; the tests come in **TA** and **TB** at C3, one per stream, and everything runs
once at the end (`just gate`). A piece's own acceptance is therefore `just check` plus its `dev/accept` script and named
smoke commands; `pytest`/`just gate` commands in the last column run at the end run, not in the piece. **Gate**: owner;
"owner/orch" = the orchestrator approves under P2-Q10 (line in `APPROVALS.md`). **Sec**: review rows, range
`<trunk at wave-0 base>..<P2-W0 head>`, run only if the owner asks (recorded, not run).

| ID | Kind | Gate | Sec | Depends | Allowed paths | Acceptance commands |
|---|---|---|---|---|---|---|
| RM-S1 | B | owner/orch | Y | — | `roles-mvp.md` §9 S1 paths, plus `company_roles` in `tl_core/modules.py` and company grants (§2) | `just check`; `uv run python dev/accept/P2-W0/RM-S1.py` (table loads; bad word fails closed; grant, revoke, precedence 1–7 incl. company) |
| W0-B1 | B | owner/orch (access words, keys) | Y | — | `tl_core/readiness/**` (incl. `harness.py`), `tl_core/services/reserved.py`, `tl_core/auth/access_words.py`, `schema/settings/{platform,access-words}.yaml`, `tests/contract/test_readiness_contract.py` (written, not run), pinned settings lists | `just check`; `uv run python -c "from tl_core.readiness.registry import load_checks; print(load_checks())"` → `{}`; `uv run python dev/accept/P2-W0/W0-B1.py` (harness on the sample check; `rollup:x` body → 422; 11 keys at defaults; every word of M3 §3 and M4 §3 in the table) |
| A1, A2, A3 | H lite | — | — | — | `dev/state.sh` + `tests/tools/test_state.py`; `dev/review-pack.sh` + `tests/tools/test_review_pack.py`; `dev/relay-lint` + `tests/tools/test_relay_lint.py` | `just check`; smoke on the fixture repo named in each ticket (tests run at the end) |
| RM-S2 | B | owner/orch | Y | RM-S1, W0-B1 | `roles-mvp.md` §9 S2 paths, plus `tl_core/auth/module_roles.py` (fine-word lookup, F1), `tl_mod_legacy/module.py` `command_words` line (F4), and consequential pins (F7, rule 12): `packages/tl-api/tests/test_api_document_controller.py:83-90`, `test_api_schedule.py:285`, `test_commands.py:228-289` | `just check`; `uv run python dev/accept/P2-W0/RM-S2.py` (every module command × viewer, user, superuser, admin, agent on two projects; matrix equals the table; a fine word reads as its table word in `command_index()`) |
| W0-B2 | B | — | Y | — | `packages/tl-modules/legacy/**` except `module.py` (F4), `packages/tl-modules/documents/src/tl_mod_documents/derivation/**`, both packages' `pyproject.toml`, `packages/tl-cli/src/tl_cli/load.py` | `just check`; `uv run tl load targets`; `just demo P1-I3`; `just demo P1-I8` |
| OC-S1 | B | owner/orch (values approved, answer 5) | — | — | `offline-classes.md` §7 S1 paths (annotation, values, generator; no RM dependency, F3) | `just check`; `uv run python dev/accept/P2-W0/OC-S1.py` (every record type has a class; a copy without one `tl:offline` fails `just gen` naming the class) |
| RM-S3 | B | owner/orch | Y | RM-S1 | `roles-mvp.md` §9 S3 paths plus the T1 paths (module roles log folded in, rule 12) | `just check`; `uv run tl admin roles grant alice --project P1 --module documents --role superuser --reason demo`; `… effective alice --project P1`; `uv run python dev/accept/P2-W0/RM-S3.py` (log at 80 and 170 columns) |
| RM-S4 | B | owner/orch | Y | RM-S2 | `roles-mvp.md` §9 S4 paths; **cost note:** the sweep is a committed codemod `dev/tools/gate_sweep.py` (idempotent, run once, kept) plus the AST pin in `dev/accept/P2-W0/RM-S4.py`, not hand edits | `just check`; `uv run python dev/tools/gate_sweep.py --check` (exit 0, nothing left to change); `uv run python dev/accept/P2-W0/RM-S4.py` (AST: every `tl_mod_*` handler call in `tl_cli` and `embedded.py` gated; counts printed) |
| OC-S2 | B | — | — | OC-S1, RM-S2 | `offline-classes.md` §7 S2 paths (hook, module validation, `offline_drafts` lines in each `module.py` after RM-S2's `command_words`, node-kind start-up check) | `just check`; `uv run python dev/accept/P2-W0/OC-S2.py` (every branch of `capture_allowed`; three module-load errors); `TL_NODE_KIND=device uv run tl serve` stops with the Phase 3 message |
| OC-T1 | H | — | — | OC-S2 | `offline-classes.md` §7 T1 paths (read route, client) | `just check`; `uv run python dev/accept/P2-W0/OC-T1.py` (`GET /record-types`: `engineering.Tag` `full`) |
| OC-T2 | H | — | — | OC-T1 | `offline-classes.md` §7 T2 paths (record screen row) | `just check`; `uv run python dev/accept/P2-W0/OC-T2.py` (line in technical mode, absent in plain) |
| OC-T3 | H | — | — | OC-S1 | `offline-classes.md` §7 T3 paths (scaffold) | `just check`; `tl new record-type` in a temp copy writes `tl:offline: none` and the reason comment |
| TA | tests (Sonnet) | — | — | RM-S1–S4 | the test files of `roles-mvp.md` §9 S1–S4 and T1, plus `packages/tl-core/tests/auth/test_access_words.py`, `test_company_grants.py` (new dir, named, F10); mutants of `roles-mvp.md` §9 | `just gate packages/tl-core packages/tl-api packages/tl-cli packages/tl-tui tests/auth tests/services` (`packages/tl-core/tests/auth/` is the one new dir, named); `just gate-pg tests/auth packages/tl-core/tests/auth`; 3-line mutation report |
| TB | tests (Sonnet) | — | — | W0-B1, W0-B2, OC-S1, OC-S2, OC-T1–T3 | the test files of `offline-classes.md` §7, plus `packages/tl-modules/legacy/tests/test_load_targets.py`, `packages/tl-modules/documents/tests/test_publish_targets.py`, `tests/contract/test_reserved_prefixes.py`, `tests/settings/test_phase2_keys.py` (existing dir, F10); mutants: OC §7 guards, duplicate target name, unknown target, `job:` prefix | `just gate packages/tl-schema packages/tl-core packages/tl-modules/legacy packages/tl-modules/documents tests/contract tests/services tests/settings tests/tools`; 3-line mutation report |
| DOC | H lite | — | — | RM-S2, RM-S3, OC-S2, W0-B1, W0-B2 | `docs/runbooks/accounts-and-access.md`, `docs/reference/access-words.md` (new), `docs/runbooks/legacy-load.md`, `packages/tl-core/README.md`, `docs/build-spec/module-designs/README.md` §3 row "Offline" | — |
| DEMO | H lite | — | — | RM-S3, OC-T2, W0-B2, A1–A3 | `dev/demos/P2-W0.sh`, `dev/demos/p2_w0_demo.py` (§8), `dev/tour/phase1.py` (module-roles log and offline row, F8; run by `just tour 1` at C4) | `just demo P2-W0` |

Totals: **8 pieces, 11 tickets** (A1–A3, OC-T1–T3, DOC, DEMO Haiku; TA and TB Sonnet). Plan check F3 split OC into
OC-S1 and OC-S2 (the schema half has no roles dependency). Pieces per stream: A 4 (RM-S1–S4), B 4 (W0-B1, W0-B2, OC-S1,
OC-S2). Roles spec's T1 is folded into RM-S3, its T2 and T3 and the offline spec's T4 into DOC and DEMO. DEMO depends
on features, not on TA or TB (F2); DOC and DEMO are one workflow.

## 7. Waves inside wave 0 and the order of work (3 slots)
Slot A = stream A (roles), slot B = stream B (core), slot C = ticket workflow (2–3 tickets) or one extra builder. A
supervisor round (`STATE.md`, piece specs from §6 rows, glue) runs in the slot whose builder just returned.

| Round | Slot A | Slot B | Slot C | Checkpoint after |
|---|---|---|---|---|
| 1 | RM-S1 | W0-B1 | A1, A2, A3 (one workflow) | C1 (schema and settings merged; gates approved) |
| 2 | RM-S2 | W0-B2 | OC-S1 | — |
| 3 | RM-S4 | OC-S2 | RM-S3 (builder); retries | C2 (all pieces merged) |
| 4 | TA | OC-T1, OC-T3 then OC-T2 (one workflow) | — | — |
| 5 | TA (cont.) or idle | TB | DOC + DEMO (one workflow) | C3 |
| 6 | — | — | — | C4: orchestrator runs `just check`, `just gate`, `just gate-pg` on touched dirs, `just tour 1` once, the demo; security review only if the owner asks |

Critical path (5 rounds): RM-S1 → RM-S2 → OC-S2 → OC-T1 → OC-T2 → DEMO (W0-B1 must merge before RM-S2).

## 8. Demo clauses (`just demo P2-W0`, SQLite then Postgres, one PASS each)
1. Seeded ledger: `alice` (user), `dora` (document_controller), `ada` (admin). With no grant, alice registers a
   document in P1 and cannot issue it (403); dora issues it and also runs a correspondence and a schedule controller
   act (answer 1). 2. `tl admin roles grant alice --project P1 --module documents --role superuser` → alice issues in
   P1, is refused in P2, and still cannot read a restricted P1 record (answer 2). 3. dora granted `viewer` of
   documents in P2 is refused `RegisterDocument` there and still issues in P1; `GET /records/{id}/actions` in P2
   offers her nothing. 4. `tl admin roles effective alice --project P1` lists every module with its source; `GET
   /events` as alice shows no grant events, as ada it does; alice cannot grant (answer 4). 5. An agent proposal of
   `IssueRevision` accepted by alice runs; accepted by bob (plain user) is 403. 6. A grant with project `company` for
   `materials` is accepted (a stand-in test module with `company_roles` true, carrying one fine word such as `awp.cwp.release`, until P2-I3; F1) and for `documents` refused `no_company_roles`.
7. `OFFLINE_CLASSES` has one entry per record type; `capture_allowed("documents.Revision", "IssueRevision",
   node="device")` → `central_act`, `CreateRevision` → `draft`, `cost.CostCode` → `online_only`, anything on
   `authority` → allowed; `TL_NODE_KIND=device tl serve` stops. 8. `GET /record-types` lists `engineering.Tag` `full`;
   the record screen shows the offline line in technical mode only. 9. `load_checks()` is empty and
   `check_readiness_contract` passes on the sample check; a body with `correlation_id: rollup:x` or `source: job:x` is
   422; `awp.iwp.ready_lead_weeks` reads 4. 10. `tl load targets` lists `tags` and `documents`; a load through the
   `tags` target gives the same result as the P1-I8 demo; a derived document publishes through the `documents` publish
   target as in P1-I3. 11. `just state P2-W0` prints at most 40 lines; `just relay-lint` passes the skill's example
   block and fails a broken one.

## 9. Risks and open items
- **Missed entry point** (HIGH, `roles-mvp.md` R1): RM-S2's matrix script and RM-S4's AST script stand in for the
  tests until TA; the existing confidentiality and workflow-role walks run at every gate.
- **Deferred tests** (MD): defects of RM-S1–S4 surface at TA, after OC is built on them. Mitigation: acceptance
  scripts print the full matrix; TA runs in round 4, before any wave-1 work.
- **`roles-mvp` R2, dev workflows** (MD): RM-S4 lists every consequential pin it updates.
- **Orchestrator before round 1**: freeze `phase2-contracts-draft.md` §1 and §7; draft ADR-0022 (P2-Q5 B, movements as
  events; M4 needs it before its C1) and the Phase 2 decisions ADR (owner answers, P2-Q answers); accept ADR-0021;
  mark R-P2-3 closed in `phase2-risks.md`; run the plan check on this file.
- **Owner**: P2-Q10 (who approves schema and permission merges; until answered every Gate cell is the owner); confirm
  P2-Q4 A (ERP stubs), P2-Q5 B, P2-Q9 A and the `awp.release.signoff_roles` default.

## Plan check
Planner-tier check of this file, 2026-10-30 (rule 8): **go with fixes, all accepted** and applied above in P2-W0 round 1.
Cost note: RM-S4 is a committed codemod script plus an AST pin (not hand edits).

| F | Sev | Finding | Applied in |
|---|---|---|---|
| F1 | HI | Fine access words are read in many places (`tl_api.commands` `Access` literal, `action_for`/`controller_actions`/`access_of`, OC `capture_allowed`, CLI `require_command`, embedded gate) | §2: RM-S2 normalises fine → table word once in `command_index()` and widens `Access`; §8 clause 6 stand-in module carries one fine word |
| F2 | MD | DEMO depends on features, not on TA or TB | §6, §7: DOC + DEMO one workflow in round 5 slot C; critical path RM-S1 → RM-S2 → OC-S2 → OC-T1 → OC-T2 → DEMO (5 rounds) |
| F3 | MD | Split OC | §6, §7: OC-S1 (annotation, values, generator; no roles dependency) in round 2 slot C; OC-S2 round 3; RM-S3 moves to round 3 |
| F4 | MD | W0-B2 and RM-S2 both touch `tl_mod_legacy/module.py` | §4, §6: W0-B2 targets via `pyproject.toml` entry points only; RM-S2 owns the `module.py` line |
| F5 | MD | A1–A3 tests under `dev/tests/` are outside `testpaths` | §5, §6: `tests/tools/test_state.py`, `test_review_pack.py`, `test_relay_lint.py` |
| F6 | MD | The contract harness lived in a test module | §3: `check_readiness_contract` exported from `tl_core/readiness/harness.py`; the test calls it |
| F7 | LO | RM-S2 breaks existing pins | §6: consequential pins `test_api_document_controller.py:83-90`, `test_api_schedule.py:285`, `test_commands.py:228-289` (rule 12) |
| F8 | LO | DEMO must show the new screens in the tour | §6: DEMO adds the module-roles log and the offline row to `dev/tour/phase1.py` (`just tour 1`) |
| F9 | LO | `tl:offline_reason` in M3 | `m3-wbs-cwp.md` §3 Offline paragraph: dropped; the reason stays in the spec table |
| F10 | LO | TA/TB gate dirs missing | §6: TA gates `tests/auth` and the named new `packages/tl-core/tests/auth`; TB gates `tests/settings` and `tests/tools` |
