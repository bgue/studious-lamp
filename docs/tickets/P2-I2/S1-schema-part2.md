# P2-I2-S1 — awp schema part 2: IWP, scope items, constraints, readiness tables and events, `iwp_facts`

Status: ready (dispatch after the plan check)
Tier: builder
Kind: piece
Review: full
Labels: schema, core
Depends on: — (M3 part 1 is on the trunk)
Branch: `p2/i2-s1-schema-part2`
Worktree: `/home/user/wt/i2-s1`
Approver (schema): owner, or the orchestrator where P2-Q10 delegates (line in `docs/reports/APPROVALS.md` at merge)

## Goal
After this piece the awp LinkML holds `IWP`, `ScopeItem`, `Constraint`, `IWPCloseout` (schema only), the readiness
tables and the IWP events; three workflows, three numbering patterns and the IWP expected link are fixtures; the
generated models, DDL and every pinned list are current; and `tl_mod_awp.facts.iwp_facts(conn, iwp_id)` returns the
frozen `IwpFacts`. No command exists yet (S2, S3, S5 build them). WS-B and the readiness engine start from this.

## Brief references (pasted; `field-work-packaging.md` "Records and states" and `08-phase2-plan.md` I2 are authoritative)
All records project scope, confidentiality `internal`, no `ConfidentialSource`. Decimals are text, ASCII digits; dates
`YYYY-MM-DD`. Copy conventions from `schema/modules/awp/cwp.yaml` (identifier `id`, `scope`, `last_seq`, `tl:table`, `tl:ix_*`).

| Type | Key | Typed fields (table) | Workflow | `tl:offline` |
|---|---|---|---|---|
| `awp.IWP` | allocator `P123-IWP-PIP-0042`: `{project}-{type}-{discipline}-{seq:4}`, `type_code: IWP`, `gap_free: true`, counts per discipline | `cur_awp_iwp`: `discipline` (list `Discipline`), `cwp_id` (awp.CWP, null until set), `planned_start`, `planned_finish`, `foreman` (actor text `user:<name>`, <= 64), `estimated_hours` (text, 1 dp, 0.0..10 000 000.0), `crew_text` (<= 120), `signoffs_json` (list of `{by, role, at, record_hash}`, <= 4) | `awp-iwp.yaml` | `draft_only` |
| `awp.ScopeItem` (P2-Q7 A) | allocator `{project}-SCI-{seq:6}`, `gap_free: false` | `cur_awp_scope_item`: `commodity` (list `Commodity`), `description` (<= 200), `qty` (text), `uom` (list `UnitOfMeasure`), `est_hours` (text, 1 dp), `cwp_id` (null ok) | `awp-scope-item.yaml`: Planned -> Installed -> Verified; Installed -> Planned (return); any but Verified -> Void | `draft_only` |
| `awp.Constraint` | allocator `{project}-CON-{seq:4}`, gap-free | `cur_awp_constraint`: `iwp_id`, `constraint_type` (list `ConstraintType`), `source` (`manual`, `check`, `rule`, `feed_hold`, `thread_hold`), `owner` (actor text, required), `need_by`, `description` (<= 500), `check_name` (<= 64, only for `check`), `raised_at`, `cleared_at`, `cleared_by`, `clear_reason` (<= 300), `suppress_hash` (sha256 text, R-P2-11) | `awp-constraint.yaml`: Open -> Assigned -> Cleared; Open -> Cleared; any but Cleared -> Void | `draft_only` |
| `awp.IWPCloseout` | none (one per IWP, composed key `<iwp key>-CLOSE`, `composed_key=True`) | `cur_awp_iwp_closeout`: `iwp_id`, `actual_hours` (text), `remaining_punch` (int >= 0), `feedback` (<= 1000), `actuals_file_id` | none (I5 adds commands) | `none` |
| readiness tables | — | `cur_awp_readiness`: `iwp_id`, `evaluated_at`, `today`, `ready` (bool), `facts_hash`, `as_of_seq`; child `cur_awp_readiness_check`: `iwp_id`, `name`, `version`, `state` (ok, blocked, pending, n_a, unknown), `detail`, `count_ok`, `count_total`, `resolve_via_json`. Non-record classes, written by the S5 projector only | — | — |

Links (relation words, no schema class needed; S2/S3 write them): `contains` IWP -> ScopeItem and IWP -> `engineering.Tag`;
`blocks` Constraint -> IWP; `resolves` record -> Constraint; document pins use the existing link pin (documents module).

**IWP workflow** `schema/fixtures/workflows/awp-iwp.yaml` (no `roles` guard; every move is a module command with
`by_module=True`, state the transitions only): Draft -> In development -> Constraint check -> Ready -> Issued ->
In progress -> Field complete -> Closed; Constraint check -> In development (return); Ready -> Constraint check
(readiness turned red); On hold from Ready, Issued, In progress, and On hold -> Constraint check (D5: the hold is lifted
into a re-check, no prior-state memory); Split from Draft, In development, Constraint check (terminal); Cancelled from
every non-terminal state. Terminal: Closed, Split, Cancelled. `generic_guards`: scope links (`contains`) refused from
Issued onward (find how `generic_guards` is declared in `tl_core/workflow/definition.py`; same rule P2-I1 used for CWP).
`expected_links` at Issued: `relation: requires`, `direction: out`, label `permit to work`, target type reserved name
`permit.PermitToWork` (no class exists; P2-Q8 A: reported missing, never blocking). If the validator refuses a target
type with no class, STOP and write it under Blocked (do not invent a class).

**Events** (`schema/modules/awp/iwp_events.yaml`, each with `tl:event_type`): `IWP.Created`, `.Revised`, `.ScopeAdded`,
`.ScopeRemoved`, `.DocumentPinned`, `.Split` {new_ids}, `.SignedOff` {by, role, record_hash}, `.Issued` {by, foreman},
`.Held` {by, reason}, `.HoldReleased`; `ScopeItem.Created`, `.Revised`; `Constraint.Raised`, `.Assigned`, `.Cleared`
{by, reason, resolved_by}; `IWP.ReadinessEvaluated` {iwp_id, evaluated_at, today, ready, checks[<= 32 CheckResult shape],
facts_hash}; `IWP.Ready` {iwp_id, evaluated_at}. Feed policy `none` on `IWP.ReadinessEvaluated`, `ScopeItem.*`,
`IWP.ScopeAdded/Removed`; `IWP.Ready`, `.SignedOff`, `.Issued`, `.Held`, `Constraint.Raised` are ordinary feed cards.
`IWP.Ready`, `.Issued` and `.ReadinessEvaluated` (low importance) are webhook-visible through `tl:event_type`
(brief `field-work-packaging.md` "Integrations"). `Record.*`, `Link.*`, `Workflow.Transitioned` are core events.

**`iwp_facts(conn, iwp_id) -> IwpFacts`** in `packages/tl-modules/awp/src/tl_mod_awp/facts.py`: one read, no write; fills
`scope_ids` (by record type, from active `contains` links, at most 5 000 ids in all, over that raises `ValueError` with a
fixed text) and `pinned_document_links` (active links from the IWP that carry a pin), status "Draft" when the record never
moved (L-P1-I2-3). Imports only `tl_core` and awp's own tables; never another module.

## Interfaces (verbatim shapes to copy; open these)
- Frozen contract: `packages/tl-core/src/tl_core/readiness/types.py` (`IwpFacts`, `CheckResult`, bounds).
- Record, child table, event, workflow, numbering: `schema/modules/awp/{cwp,events}.yaml`,
  `schema/fixtures/workflows/awp-cwp.yaml`, `schema/fixtures/numbering/patterns.yaml`.
- Expected link declaration: `cwp.yaml` `tl:expects_link` (P2-I1-S6 report `docs/reports/P2-I1/S6.md`).

## Context (<= 10 files)
`schema/modules/awp/{module,cwp,events}.yaml`; `schema/fixtures/workflows/awp-cwp.yaml`;
`schema/fixtures/numbering/patterns.yaml`; `schema/fixtures/standards/co.acme.awp@1.0.0.yaml`;
`packages/tl-core/src/tl_core/readiness/types.py`; `packages/tl-modules/awp/src/tl_mod_awp/{module,names}.py`;
`docs/build-spec/specs/offline-classes.md` (confirm the classes above; change one only with the reason in the report).
may explore: `docs/reports/P2-I1/S2.md`, `packages/tl-core/src/tl_core/workflow/definition.py`.

## Allowed paths
- `schema/modules/awp/**` (create `iwp.yaml`, `scope_item.yaml`, `constraint.yaml`, `closeout.yaml`, `readiness.yaml`,
  `iwp_events.yaml`; `module.yaml` imports only)
- `schema/fixtures/workflows/awp-iwp.yaml`, `awp-scope-item.yaml`, `awp-constraint.yaml` (create)
- `schema/fixtures/numbering/patterns.yaml` (three blocks added)
- `schema/fixtures/standards/co.acme.awp@1.0.0.yaml` (only if a code list above is missing; `ConstraintType` exists)
- `packages/tl-schema/src/tl_schema/generated/**` (`just gen` output only)
- `packages/tl-modules/awp/src/tl_mod_awp/{facts,names,module}.py` (facts new; names and module: record-type and table
  names only)
- pinned lists (consequential pins, rule 12): tests that enumerate record types, events, tables, workflows, numbering
  patterns or module record types and change only because these exist; write each list as the union of what the trunk
  has and what this adds; list each in the report
- `dev/accept/P2-I2/S1.py`, `docs/reports/P2-I2/S1.md` (create)
Not allowed: other modules, `tl_core/**`, `pyproject.toml`, `uv.lock`, commands or handlers, `awp.*` settings (on trunk).

## Steps
1. Write the LinkML and fixtures; `just gen`; commit schema and generated output together.
2. Write `facts.py` and the name constants; register the record types in the module spec (names only).
3. Fix pinned lists that fail only because these types exist (union form). Then the acceptance script.

## Acceptance (run once each; no pytest except the pinned-list files named in the report, one package per gate)
```
just gen
just check
uv run python dev/accept/P2-I2/S1.py
just gate packages/tl-schema/tests packages/tl-modules/awp/tests
```
`S1.py` (SQLite, dialect-neutral, one `PASS <check>` line per check, final `S1 ok`): the four record types are in
`TYPE_LABELS` and `OFFLINE_CLASSES` with the table's classes; every table above exists in the generated DDL; the three
workflows load, `Closed`, `Split`, `Cancelled` and `Verified`/`Cleared` terminal as stated, and `On hold -> Ready` is
refused; the IWP pattern allocates `P123-IWP-PIP-0001`, `-0002`, `P123-IWP-CIV-0001`; the scope-item pattern allocates
`P123-SCI-000001` and `-000002`; every event has `tl:event_type` and the stated feed policy; `iwp_facts` on a hand-written
IWP row with 3 `contains` links returns them by type, and with 5 001 returns the fixed `ValueError`.

## Tests for the end run (T11 writes them; none here)
Guards T11 will mutate: `estimated_hours` and `qty` patterns, the IWP terminal states, the hold-return transition, the
5 000-id cap, the `feed_policy: none` rows. Name file:line for each in the report.

## Report requirements
Standard piece report (<= 60 lines): deviations first; files; pinned lists updated and why; acceptance output (<= 5 lines
per command); offline classes as built; any event or field added or dropped; the permit-target outcome.

## Commit
`P2-I2-S1: <imperative summary>`; body says what and why; end with exactly the attribution trailer your harness requires,
unchanged. No model names in committed files. Do not merge; do not push.

## Escalation triggers
- Blocked if: the expected-link validator refuses the reserved target type; a non-gap-free pattern is not expressible;
  a pinned list change goes beyond a name added; `just gen` changes a non-awp generated file other than all-module registries.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
