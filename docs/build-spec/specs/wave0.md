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
  (`user`, `controller`) or a fine word listed there; RM-S2's `require_command_access` maps fine → table word.
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
  one name raise). `tests/contract/test_readiness_contract.py::check_readiness_contract(check, world)` ships as the
  harness the contract names (no write on a read-only connection, bounds, fixed detail, `n_a` for a missing
  dependency, `watches` names existing types) with one self-check on an inline `n_a` sample check.
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
  and `documents` registered by the legacy package's own entry points; a target declares `scope: project | company`
  (`tl load open --company` for company targets; loads stay admin-only, answer 12); a generic column-mapping form for
  module targets; a duplicate name is a `ModuleLoadError`; `tl load targets` lists name, module, scope.
- Publish (`tl_mod_documents.derivation`): `publish.py` refactored to targets found by `throughline.publish_targets`
  with the same shape; built-ins `tags`, `documents`; create-only and exact compensation unchanged (ADR-0014).
- Proof that nothing in Phase 1 moved: the P1-I3 and P1-I8 demos rerun green on both adapters.

## 5. Tools A1–A3 (skill Appendix A, Haiku, `review: lite`)
`dev/state.sh` (A1), `dev/review-pack.sh` (A2), `dev/relay-lint` (A3), each with its own test under `dev/tests/` that
pins the output on a fixture git repository in `tmp_path` (Appendix A is the acceptance; these tickets keep their
tests). The `just state|review-pack|relay-lint` recipe lines are supervisor glue (one shared `justfile`).

## 6. Pieces and tickets
B = builder piece (Sonnet, one shot, `review: full`); H = Haiku ticket. Every row's Allowed paths include
`docs/reports/P2-W0/<id>.md` and its acceptance script `dev/accept/P2-W0/<id>.py` (SQLite, one `PASS` per check, exit
0). **Tests are deferred** (owner): pieces leave reference, stub and acceptance script; tests come in **TA** and
**TB** at C3, one per stream because wave 0 is two increment-sized streams, before the demo. Every acceptance starts
with `just check` and ends with `just gate <existing test dirs touched>` (consequential pins, rule 12). **Gate**:
owner; "owner/orch" = the orchestrator approves when P2-Q10 delegates (line in `APPROVALS.md`). **Sec**: review rows,
range `<trunk at wave-0 base>..<P2-W0 head>`, run only if the owner asks.

| ID | Kind | Gate | Sec | Depends | Allowed paths | Acceptance commands |
|---|---|---|---|---|---|---|
| RM-S1 | B | owner | Y | — | `roles-mvp.md` §9 S1 paths, plus `company_roles` in `tl_core/modules.py` and company grants (§2) | `uv run python dev/accept/P2-W0/RM-S1.py` (table loads; bad word fails closed; grant, revoke, precedence 1–7 incl. company) |
| RM-S2 | B | owner/orch | Y | RM-S1, W0-B1 | `roles-mvp.md` §9 S2 paths, plus `tl_core/auth/module_roles.py` (fine-word lookup) | `uv run python dev/accept/P2-W0/RM-S2.py` (every module command × viewer, user, superuser, admin, agent on two projects; matrix equals the table) |
| RM-S3 | B | owner/orch | Y | RM-S1 | `roles-mvp.md` §9 S3 paths plus the T1 paths (module roles log folded in, rule 12) | `uv run tl admin roles grant alice --project P1 --module documents --role superuser --reason demo`; `… effective alice --project P1`; `uv run python dev/accept/P2-W0/RM-S3.py` (log at 80 and 170 columns) |
| RM-S4 | B | owner/orch | Y | RM-S2 | `roles-mvp.md` §9 S4 paths | `uv run python dev/accept/P2-W0/RM-S4.py` (AST: every `tl_mod_*` handler call in `tl_cli` and `embedded.py` gated; counts printed) |
| W0-B1 | B | owner (access words); owner/orch (keys) | Y | — | `packages/tl-core/src/tl_core/readiness/**`, `tl_core/services/reserved.py`, `tl_core/auth/access_words.py`, `schema/settings/{platform,access-words}.yaml`, `tests/contract/test_readiness_contract.py`, pinned settings lists | `uv run python -c "from tl_core.readiness.registry import load_checks; print(load_checks())"` → `{}`; `uv run pytest tests/contract/test_readiness_contract.py`; `uv run python dev/accept/P2-W0/W0-B1.py` (`rollup:x` body → 422; 11 keys at defaults); `just gate packages/tl-api/tests/test_api_workflow_roles.py` |
| W0-B2 | B | — | Y | — | `packages/tl-modules/legacy/**`, `packages/tl-modules/documents/src/tl_mod_documents/derivation/**`, both packages' `pyproject.toml`, `packages/tl-cli/src/tl_cli/load.py` | `uv run tl load targets`; `just gate packages/tl-modules/legacy packages/tl-modules/documents`; `just demo P1-I3`; `just demo P1-I8` |
| OC | B | owner/orch (values approved, answer 5) | — | RM-S2 | `offline-classes.md` §7 S1 and S2 paths, one piece (rule 12) | `uv run python dev/accept/P2-W0/OC.py` (every branch of `capture_allowed`; three module-load errors; a copy without one `tl:offline` fails `just gen` naming the class); `TL_NODE_KIND=device uv run tl serve` stops with the Phase 3 message |
| OC-T1 | H | — | — | OC | `offline-classes.md` §7 T1 paths (read route, client) | `uv run python dev/accept/P2-W0/OC-T1.py` (`GET /record-types`: `engineering.Tag` `full`) |
| OC-T2 | H | — | — | OC-T1 | `offline-classes.md` §7 T2 paths (record screen row) | `uv run python dev/accept/P2-W0/OC-T2.py` (line in technical mode, absent in plain) |
| OC-T3 | H | — | — | OC | `offline-classes.md` §7 T3 paths (scaffold) | `tl new record-type` in a temp copy writes `tl:offline: none` and the reason comment |
| A1 | H lite | — | — | — | `dev/state.sh`, `dev/tests/test_state.py` | `uv run pytest dev/tests/test_state.py` |
| A2 | H lite | — | — | — | `dev/review-pack.sh`, `dev/tests/test_review_pack.py` | `uv run pytest dev/tests/test_review_pack.py` |
| A3 | H lite | — | — | — | `dev/relay-lint`, `dev/tests/test_relay_lint.py` | `uv run pytest dev/tests/test_relay_lint.py` |
| TA | tests (Sonnet) | — | — | RM-S1–S4 | the test files of `roles-mvp.md` §9 S1–S4 and T1, plus `packages/tl-core/tests/auth/test_access_words.py`, `test_company_grants.py`; mutants of `roles-mvp.md` §9 | `just gate packages/tl-core packages/tl-api packages/tl-cli packages/tl-tui tests/services`; `just gate-pg packages/tl-core/tests/auth`; 3-line mutation report |
| TB | tests (Sonnet) | — | — | W0-B1, W0-B2, OC, OC-T1–T3 | the test files of `offline-classes.md` §7, plus `packages/tl-modules/legacy/tests/test_load_targets.py`, `packages/tl-modules/documents/tests/test_publish_targets.py`, `tests/contract/test_reserved_prefixes.py`, `packages/tl-core/tests/settings/test_phase2_keys.py`; mutants: OC §7 guards, duplicate target name, unknown target, `job:` prefix | `just gate packages/tl-schema packages/tl-core packages/tl-modules/legacy packages/tl-modules/documents tests/contract tests/services`; 3-line mutation report |
| DOC | H lite | — | — | TA, TB | `docs/runbooks/accounts-and-access.md`, `docs/reference/access-words.md` (new), `docs/runbooks/legacy-load.md`, `packages/tl-core/README.md`, `docs/build-spec/module-designs/README.md` §3 row "Offline" | — |
| DEMO | H lite | — | — | TA, TB, OC-T2, RM-S3 | `dev/demos/P2-W0.sh`, `dev/demos/p2_w0_demo.py` (§8) | `just demo P2-W0` |

Totals: **7 pieces, 11 tickets** (9 Haiku, TA and TB Sonnet). Over 10 tickets: the plan check (rule 8) runs on this
file before dispatch. Pieces per stream: A 4 (RM-S1–S4), B 3 (W0-B1, W0-B2, OC). Roles spec's T1 is folded into
RM-S3, its T2 and T3 and the offline spec's T4 into DOC and DEMO; its S1 and S2 are one piece OC (rule 12).

## 7. Waves inside wave 0 and the order of work (3 slots)
Slot A = stream A (roles), slot B = stream B (core), slot C = ticket workflow (2–3 tickets) or one extra builder. A
supervisor round (`STATE.md`, piece specs from §6 rows, glue) runs in the slot whose builder just returned.

| Round | Slot A | Slot B | Slot C | Checkpoint after |
|---|---|---|---|---|
| 1 | RM-S1 | W0-B1 | A1, A2, A3 | C1 (schema and settings merged; gates approved) |
| 2 | RM-S2 | W0-B2 | RM-S3 (builder) | — |
| 3 | RM-S4 | OC | retries of rounds 1–2 | C2 (all pieces merged) |
| 4 | TA | OC-T1, OC-T3 then OC-T2 (one workflow) | — | — |
| 5 | TA (cont.) or idle | TB | DOC | C3 |
| 6 | — | — | DEMO | C4: orchestrator runs `just check`, `just gate`, `just gate-pg` on touched dirs, `just tour` once, the demo; security review only if the owner asks |

Critical path: RM-S1 → RM-S2 → OC → OC-T1 → OC-T2 → TB → DEMO (W0-B1 must merge before RM-S2).

## 8. Demo clauses (`just demo P2-W0`, SQLite then Postgres, one PASS each)
1. Seeded ledger: `alice` (user), `dora` (document_controller), `ada` (admin). With no grant, alice registers a
   document in P1 and cannot issue it (403); dora issues it and also runs a correspondence and a schedule controller
   act (answer 1). 2. `tl admin roles grant alice --project P1 --module documents --role superuser` → alice issues in
   P1, is refused in P2, and still cannot read a restricted P1 record (answer 2). 3. dora granted `viewer` of
   documents in P2 is refused `RegisterDocument` there and still issues in P1; `GET /records/{id}/actions` in P2
   offers her nothing. 4. `tl admin roles effective alice --project P1` lists every module with its source; `GET
   /events` as alice shows no grant events, as ada it does; alice cannot grant (answer 4). 5. An agent proposal of
   `IssueRevision` accepted by alice runs; accepted by bob (plain user) is 403. 6. A grant with project `company` for
   `materials` is accepted (a test module stands in until P2-I3) and for `documents` refused `no_company_roles`.
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
