# P2-I1-S4 — CWP and external package commands, workflow, actions, API glue, and the S3 follow-ups

Status: ready
Tier: builder
Kind: piece
Review: full
Labels: core
Depends on: S3 (merged @f482aad)
Branch: `p2/i1-s4-awp-cwp`
Worktree: `/home/user/wt/i1-s4` (from `p2/i1` head)

## Goal
After this piece a person with the right word creates, allocates, links and moves CWPs through the workflow, records
and updates EWP/PWP mirrors, the module's rules table covers every type, the awp commands and errors are served by
`tl_api`, and awp record keys are namespaced per type. It leaves the seed ledger `.accept/p2-i1.db`
(WBS, 4 CWAs, path v1, 6 CWPs) that T10, T04 and T07 run against. S5 (rollup run) and T02 (load targets) are built
beside it and do not touch your files.

## Step order (commit each step on its own)
1. **S3 follow-ups** (below, D-a, D-b, D-e, F4). 2. CWP, packages, workflow, projector. 3. `RULES`, `propose_cwp`.
4. `tl_api` glue (D-d). 5. Acceptance script and seed ledger.

## Step 1. S3 follow-ups (decisions D-a, D-b, D-e, F4; owner policy: no new pytest)
- **D-a key namespace (closes review finding F1, a hidden key answered "already used").** Every awp record key becomes
  `<ns>@<code>` with the module-built form: `awp.wbs@<code>`, `awp.cwa@<code>`, and for this piece `awp.ewp@<no>`,
  `awp.pwp@<no>` (`composed_key=True` in `create_module_record`; a typed key cannot hold `@`, so no other module's typed
  record can ever equal one; you may choose another prefix that holds `@` and starts with `awp.`). One helper
  `record_key(kind, code)` in `common.py`, the prefixes in `names.py`. The displayed code stays the typed `code` column
  and the title; screens never show the key. `resolve_code`/`require_code` take the bare code and add the prefix for
  their type. The "key taken" checks (`handlers/wbs.py` `_require_free_code`, `handlers/cwa.py` `_KEY_TAKEN_SQL`, and yours
  for packages) now ask for the prefixed key with `AND type = :type`, so they see same-type awp records only; core's own
  duplicate-key error on a collision with a module-built key is mapped to the same fixed duplicate message. Update
  `dev/accept/P2-I1/S3.py` where it spells keys. Guard named for T11: a node `1` and a cost code `1` coexist; a hidden
  other-type record with key `1` does not change the answer.
- **D-b**: `MapWbsToCostCodes` accepts 0 allocation lines = clear the allocation (retract every module link of the node,
  `WBSNode.CostCodesMapped` with an empty list, `rollup.request()`); 1 to 20 lines otherwise. Change the model bound and
  the sum rule (sum 100.00 only when lines exist).
- **D-e**: `reason_code` of `MoveCwaInPath` and `DefinePathOfConstruction` steps is validated against the `PathReason`
  list of the standards edition (`co.acme.awp@1.0.0`) through the code-list reader the cost module uses for its lists
  (grep `code_list` / `CodeList` in `packages/tl-core/src`); an unknown code is refused with a fixed message.
- **F4**: a cost code link that is missing for an existing allocation line is re-added on the next change of that node
  (the "kept in step" rule compares live links with the typed lines both ways, add and retract). Find the gap in
  `handlers/wbs.py` (the link step of `MapWbsToCostCodes`) and close it.

## Step 2-3. Brief references (pasted; spec `docs/build-spec/specs/m3-wbs-cwp.md` §2, §3, §7 is authoritative)
Record types: `awp.CWP` (allocator key `{project}-{type}-{discipline}-{seq:4}`, pattern line already in
`schema/fixtures/numbering/patterns.yaml`, gap-free per discipline), `awp.EWPRef`, `awp.PWPRef` (typed package number,
unique per type and project). Tables `cur_awp_cwp`, `cur_awp_cwp_allocation`, `cur_awp_ewp_ref`, `cur_awp_pwp_ref`
(`schema/modules/awp/cwp.yaml`, `external_package.yaml`; events `events.yaml`).

| Command | Word | Events |
|---|---|---|
| `CreateCwp` {discipline, title, cwa_code, planned_start?, planned_finish?, budget_hours?, quantities?, contractor_text?} | `awp.cwp.edit` | `Numbering.Allocated`, `Record.Created`, `CWP.Defined`, `Link.Added` (belongs_to CWA) |
| `ReviseCwp`; `AllocateCwpToWbs` {cwp, allocations[{wbs_code, percent}]} | `awp.cwp.edit` | `CWP.Revised` (+ `Record.Updated` on a title change); `CWP.AllocatedToWbs` (no card), `Link.*` |
| `StartCwpDevelopment`, `StartCwpExecution`, `CompleteCwp` | `awp.cwp.edit` | `Workflow.Transitioned` (`by_module=True`) |
| `ReleaseCwp` {cwp, expected_version}; `ReturnCwp` {cwp, reason} | `awp.cwp.release` | `CWP.Released` {by, record_hash} + `Workflow.Transitioned`; `Workflow.Transitioned` |
| `CloseCwp`; `ReopenCwp` {reason} | `awp.cwp.close` | `Workflow.Transitioned` |
| `VoidCwp`, `VoidExternalPackage` {id, reason} | `awp.void` | `Record.Voided` |
| `RecordExternalPackage` {package_type, package_no, title, status_text?, forecast_date?, actual_date?, constraint_source, source_system?} | `awp.package.edit` | `Record.Created`, `EWPRef.Defined`/`PWPRef.Defined` |
| `UpdateExternalPackage` {id, status_text?, forecast_date?, actual_date?, constraint_source?} | `awp.package.edit` | `EWPRef.Updated`/`PWPRef.Updated` |
| `RequestRollup` {} | `awp.cwp.edit` | none (`rollup.request()`) |

Rules (fixed messages, never cell text): workflow Planned -> In development -> Released for IWP development -> Executing
-> Complete -> Closed; Released -> In development (return); Complete -> Executing (reopen); any state but Closed -> Void
(`schema/fixtures/workflows/awp-cwp.yaml`, no `roles` guard; every move is a module command). `planned_finish >=
planned_start`; budget hours 1 dp, 0..10 000 000; quantities <= 50 rows with `Commodity`/`UnitOfMeasure` list codes;
`contractor_text` <= 120; a retired CWA or WBS node takes no new CWP or allocation; allocations <= 20 rows, each
0.01..100.00, no repeat, sum exactly 100.00, leaf nodes only (the `common.py`/`handlers/wbs.py` helpers S3 left);
fields frozen from Released (only `ReturnCwp` reopens them); `ReleaseCwp` needs a CWA, budget hours > 0, both dates and
allocations summing to 100, and compares `expected_version`; `CWP.Released` carries the record hash of the fields as
released. Release reports a missing `awp.EWPRef` link at `Released` as an `expected_links` miss, never a refusal. Every
change of a budget, an allocation, a retirement or a void calls `rollup.request()`. Links `belongs_to` CWA and each
allocated WBS node are module-written (`by_module=True`, source `rule`), kept in step, not retractable by a person.
Generic allow-list: CWP `{SetPsetValues, AddLink, SuggestLink, AttachFile} ∪ LINK_LIFE` with guard `not_closed`; EWPRef,
PWPRef `{AddLink, SuggestLink} ∪ LINK_LIFE`; `TransitionWorkflow`, `UpdateRecord`, `VoidRecord` on nothing.
`propose_cwp` (ADR-0014 §8) proposes `CreateCwp`; the accepting person needs `awp.cwp.edit` (copy how
`tl_core/modules.py` and the cost or correspondence module declare proposable commands). Verify a `LinkActivity` from a
CWP passes the source-end check with this allow-list (L-P1-I1-8); note the result in the report.
`RULES` rows: spec §7 table, one row per state and command; the word of each row equals the command's access word.

## Step 4. API glue (D-d)
- `packages/tl-api/src/tl_api/errors.py`: a row for `AwpError` and each subclass in `tl_mod_awp/errors.py`
  (status and stable code, as the `cost` rows; 404 for not-found, 409 for duplicate/in-use, 422 otherwise).
- `packages/tl-api/src/tl_api/commands.py`: `*_module_specs("awp", AWP_COMMANDS)` in `COMMANDS`;
  `packages/tl-api/pyproject.toml` and root `uv.lock` name the workspace dependency (`uv sync`).
- Consequential pins (rule 12): any test or snapshot under `packages/tl-api/tests/` that counts commands, routes or
  error rows and breaks only for this; list each in the report. No new pytest.

## Interfaces (open these; copy their shape)
- Package, handlers, projectors, `module.py`, `actions.py`, `commands.py`, `rollup.request`: `packages/tl-modules/awp/` (S3).
  `projectors/cwp.py` `cwp_projectors()` is the seam: return your projectors from it (do not edit `module.py`'s
  `projectors()` or `projectors/__init__.py`; S5 uses the sibling seam).
- Numbering and workflow-by-module: `packages/tl-modules/correspondence/` (grep `handle_transition_workflow`,
  `allocate_key`), `packages/tl-modules/cost/`.
- Registries: `packages/tl-api/src/tl_api/{commands,errors}.py`.

## Context (<= 10 files)
- `docs/build-spec/specs/m3-wbs-cwp.md` §2, §3, §7
- `docs/reports/P2-I1/S3.md` (open questions 1-5 are the Step 1 and 4 items)
- `packages/tl-modules/awp/src/tl_mod_awp/{common,commands,actions,module,names}.py`, `handlers/{wbs,cwa}.py`
- `schema/modules/awp/{cwp,external_package,events}.yaml`, `schema/fixtures/workflows/awp-cwp.yaml`
may explore: the correspondence and cost modules for shapes.

## Allowed paths
- `packages/tl-modules/awp/**` (not `targets.py`, `pyproject.toml`: T02's; not `rollup.py`, `worker.py`, `projectors/rollup.py`: S5's)
- `packages/tl-api/src/tl_api/{commands,errors}.py`, `packages/tl-api/pyproject.toml`, root `uv.lock`; consequential pins under `packages/tl-api/tests/` (list each)
- `dev/accept/P2-I1/S3.py` (key spelling only), `dev/accept/P2-I1/S4.py` (create), `docs/reports/P2-I1/S4.md` (create)
Not allowed: any `schema/**` or generated file (a schema gap is *Blocked*), `tl_core`, other packages, new pytest files.

## Acceptance (run these once; `just check` needs `NODE_OPTIONS=--max-old-space-size=6144`; no pytest)
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I1/S3.py
uv run python dev/accept/P2-I1/S4.py --keep .accept/p2-i1.db
just gate packages/tl-api/tests/test_commands.py packages/tl-api/tests/test_auth_review.py
```
`S4.py` (SQLite tmp db, acting accounts at `viewer`, `user`, `controller`; one `PASS <check>` per check; final `S4 ok`;
<= 60 output lines): the Step 1 checks (node `1` and cost code `1` coexist; clear an allocation with 0 lines; bad
reason code refused; a deleted link re-added); create 3 CWPs in two disciplines (numbers gap-free per discipline);
allocate 60/40 and refuse 99.99; every workflow move with the right word and `user` refused `ReleaseCwp`; release
refused without budget/dates/allocation sum; fields frozen after release, `ReturnCwp` reopens them; stale
`expected_version` refused; `CloseCwp`, `ReopenCwp`, `VoidCwp` by word; EWP and PWP record/update/void; `RULES` word
per row equals the command word (loop in the script); `propose_cwp` accepted by `user`; hidden id answers as missing;
`LinkActivity` from a CWP accepted; rollup queued once after two changes; rebuild equals incremental. `--keep` leaves
the seed ledger: WBS (3 levels, 6 leaves, two mapped to cost codes), 4 CWAs, path v1, 6 CWPs over three states.

## Guards T11 will mutate (name file:line in the report; run no mutants here)
Release preconditions; frozen fields after Release; word per `RULES` row; `not_closed`; `expected_version`; the
namespaced key helper and the same-type key-taken check; allocation sum with the empty list.

## Report requirements
`docs/templates/haiku-report.md` shape, <= 60 lines: deviations first; files; pins updated (each, why); acceptance
output (<= 5 lines per command); guards file:line; `LinkActivity` result; candidate learnings. Builder return <= 15 lines.

## Commit
Subject `P2-I1-S4: <imperative summary>`; body says what and why; end with the harness attribution line, then the line
`Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not
merge; do not push.

## Escalation triggers
- *Blocked* if: the generated schema lacks a column or event the commands need; the CWP numbering pattern line does not
  allocate as spec §2; the key helper needs a `tl_core` change; the source-end check refuses `LinkActivity` from a CWP
  and a `tl_core` edit is the only fix.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
