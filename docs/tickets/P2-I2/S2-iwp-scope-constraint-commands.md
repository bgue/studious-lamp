# P2-I2-S2 — IWP, scope item and constraint commands, guards, sizing warning

Status: ready after S1 merged (stage; dispatch r3)
Tier: builder
Kind: piece
Review: full
Labels: core, access
Depends on: S1 (merged)
Branch: `p2/i2-s2-iwp-commands`
Worktree: `/home/user/wt/i2-s2` (from `p2/i2` head)

## Goal
After this piece a person with the right word creates an IWP (numbered `P123-IWP-PIP-0001`), creates scope items, adds
and removes scope, pins documents, splits an oversize IWP, and raises, assigns and clears constraints (five sources,
need-by from settings, `blocks` and `resolves` links, aging, suppress after a person's clear of a check-raised one). It merges
the old S2 and S3 (plan check F5): one owner of `module.py`, `names.py`, `commands.py` and `AWP_COMMANDS`. S4 (engine)
and T04a read what this leaves; T06a1/T06a2 test their checks with its pin command. It leaves a seed ledger
`.accept/p2-i2.db` (3 IWPs, 40 scope items, 2 pinned documents, 3 constraints).

## Brief references (pasted; `docs/build-spec/module-designs/field-work-packaging.md` "Records and states", "Constraints" and `08-phase2-plan.md` I2 T02/T03 are authoritative)
| Command | Word (new, in `schema/settings/access-words.yaml`; S2 adds, no other settings change) | Events |
|---|---|---|
| `CreateIwp` {discipline, title, cwp_id?, planned_start?, planned_finish?, foreman?, estimated_hours?, crew_text?} | `awp.iwp.edit` = user | `Numbering.Allocated`, `Record.Created`, `IWP.Created`, `Link.Added` (belongs_to CWP when given) |
| `CreateScopeItem` {commodity, description, qty, uom, est_hours, cwp_id?} | `awp.iwp.edit` | `Numbering.Allocated`, `Record.Created`, `ScopeItem.Created` |
| `AddIwpScope` {iwp, items[<= 200 ids: ScopeItem or engineering.Tag]}; `RemoveIwpScope` {iwp, items} | `awp.iwp.edit` | `IWP.ScopeAdded` / `.ScopeRemoved`, `Link.*` (`contains`, source `rule`, by_module) |
| `PinIwpDocument` {iwp, document, pin?} | `awp.iwp.edit` | `IWP.DocumentPinned`, `Link.Added` (the documents-module pin link, `references` with pin; floating when pin omitted) |
| `StartIwpDevelopment`, `SendIwpToConstraintCheck`, `ReturnIwpToDevelopment` {iwp, reason?} | `awp.iwp.edit` | `Workflow.Transitioned` (by_module) |
| `SplitIwp` {iwp, mode: `by_hours`\|`by_scope`, groups?: list of scope-id lists (by_scope), reason} | `awp.iwp.edit` | two `Record.Created` (+ `IWP.Created`), `IWP.Split` {new_ids}, `Workflow.Transitioned` (Split) |
| `CancelIwp` {iwp, reason} | `awp.void` (existing, controller) | `Workflow.Transitioned` (Cancelled) |
| `RaiseConstraint` {iwp, constraint_type, source, owner, description, need_by?, check_name?, facts_hash?} | `awp.constraint.edit` = user | `Numbering.Allocated`, `Record.Created`, `Constraint.Raised`, `Link.Added` (`blocks` Constraint -> IWP, module) |
| `AssignConstraint` {constraint, owner} | `awp.constraint.edit` | `Constraint.Assigned`, `Workflow.Transitioned` (Assigned) |
| `ClearConstraint` {constraint, reason, resolved_by?: record id} | `awp.constraint.edit` | `Constraint.Cleared`, `Link.Added` (`resolves` resolved_by -> Constraint when given), `Workflow.Transitioned` (Cleared) |
| `VoidConstraint` {constraint, reason} | `awp.constraint.edit` | `Workflow.Transitioned` (Void) |
Every state-moving command is a `by_module=True` transition; the workflows carry no `roles` guard (S1). `IWP.Ready` moves
(Constraint check <-> Ready) are S4's, `SignOffIwp`/`IssueIwp`/`HoldIwp` are S3's: do not build them.

Rules (fixed messages, never cell text): IWP fields editable in Draft, In development, Constraint check; frozen from Ready
(only S4's red move reopens them, as CWP freezes at Released). `planned_finish >= planned_start`; `estimated_hours` 1 dp
0.0..10 000 000.0 (default: sum of the `est_hours` of the scope items, when none given; a sum over the bound is refused);
`crew_text` <= 120; foreman `user:<name>` <= 64 and an existing account name. Scope: items only while the IWP is Draft, In
development or Constraint check (the S1 generic guard refuses later); an item belongs to at most one non-terminal IWP
(second add refused with a fixed message naming the key of the IWP, not its title); a Verified or Void item is refused;
`estimated_hours` is recomputed on add/remove when it was derived. The sizing warning: when `estimated_hours` is outside
`awp.iwp.size_hours` [low, high] the command still succeeds and the result carries a fixed warning code (`iwp_oversize`,
`iwp_undersize`) through the same channel `ReleaseCwp` uses for an `expected_links` miss; the value is read through the
settings reader (`tl_core.settings`; see how `ReleaseCwp` or the cost module reads one). `SplitIwp by_hours`: scope items
in key order are cut into the fewest groups each `<= high`; `by_scope`: the given groups, each non-empty, together exactly
the scope; the source goes to Split (terminal), two or more new IWPs of the same discipline take the groups, pins and
foreman are copied, open constraints on the source are voided with reason `split`, `contains` links move. Constraints: `owner` required (`user:<name>` or a module-role actor, existing);
`constraint_type` from the `ConstraintType` list; `need_by` default = planned start minus `awp.iwp.ready_lead_weeks`
weeks (refuse when neither need_by nor planned start exists); sources `check`, `rule`, `feed_hold`, `thread_hold` need
`by_module` or an explicit module caller (S4 calls `raise_constraint(uow, ...)` as a plain function exported from
`tl_mod_awp.constraints`; a person's `RaiseConstraint` accepts source `manual` only; the other four are refused with a
fixed message when the caller is not a module); `check` needs `check_name` and `facts_hash`. R-P2-11 (`phase2-risks.md`):
a person's clear of a source-`check` constraint requires a reason and stores `suppress_hash = facts_hash` of the raise;
`raise_constraint` for the same IWP and `check_name` with an equal `facts_hash` is a no-op returning the cleared one
(fixed code `suppressed`); a different hash raises a new one. A check clears only what a check raised
(`clear_constraint(uow, ...)` exported the same way, source-checked). Aging: `constraint_age_days(row, today)` pure
function and a flag `aging` when open longer than `awp.constraint.aging_days`. `resolved_by` must be a record the actor can
see; a hidden id answers as missing (ADR-0016).
Generic allow-list: IWP `{SetPsetValues, AddLink, SuggestLink, AttachFile} ∪ LINK_LIFE` with guard `not_closed`
(Closed, Split, Cancelled); ScopeItem and Constraint `{AddLink, SuggestLink} ∪ LINK_LIFE`; `TransitionWorkflow`,
`UpdateRecord`, `VoidRecord` on none of the three. Module-written links (`contains`, `blocks`, `resolves`) are not
retractable by a person. `propose_constraint` and `propose_iwp_scope` proposable commands are T09b's, not here. `RULES` rows
for every state and command, word equal to the command's word.

## Interfaces (open these)
- Frozen contract and facts: `packages/tl-core/src/tl_core/readiness/types.py`, `packages/tl-modules/awp/src/tl_mod_awp/facts.py` (S1).
- Pattern to copy command for command: `packages/tl-modules/awp/src/tl_mod_awp/{commands,handlers/cwp,projectors/cwp,module,names,common,linking,guards,limits,errors}.py`.
- Pin link: `packages/tl-modules/documents/src/tl_mod_documents/resolver.py` (`resolve_pin`) and how `LinkActivity`/`AddLink` store a pin (`tl_core.links`; grep `pin`). awp may not import `tl_mod_documents`: write the link through `tl_core`.
- Settings reader and warning channel: `ReleaseCwp` in `handlers/cwp.py`.

## Context (<= 10 files)
`docs/build-spec/module-designs/field-work-packaging.md` ("Records and states", "Constraints"); `docs/reports/P2-I2/S1.md`;
the awp files above (`commands.py`, `handlers/cwp.py`, `projectors/cwp.py`, `module.py`); `schema/settings/access-words.yaml`;
`docs/build-spec/phase2-risks.md` R-P2-11 row.

## Allowed paths
- `packages/tl-modules/awp/**` (not `targets.py`, `pyproject.toml`, `rollup.py`, `worker.py`; not `readiness/**` (S4's); new files `handlers/{iwp,scope,constraint}.py`, `projectors/{iwp,scope,constraint}.py`, `constraints.py`)
- `schema/settings/access-words.yaml` (two words: `awp.iwp.edit` user, `awp.constraint.edit` user; no other change)
- `packages/tl-api/src/tl_api/errors.py` (rows for the new `AwpError` subclasses; status and stable code as the CWP rows)
- consequential pins (rule 12): tests that count commands, access words, routes or error rows and break only for this; list each, union form
- `dev/accept/P2-I2/S2.py` (create), `docs/reports/P2-I2/S2.md` (create)
Not allowed: any `schema/**` except the settings file above, generated files (a schema gap is *Blocked*), `tl_core`, other modules, `AWP_COMMANDS` registration in `tl_api` (C2 glue), new pytest.

## Acceptance (run once each; one package per gate; `NODE_OPTIONS=--max-old-space-size=6144` for check)
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/S2.py --keep .accept/p2-i2.db
just gate packages/tl-modules/awp/tests tests/services/test_modules.py
just gate packages/tl-api/tests/test_commands.py
```
`S2.py` (SQLite tmp db, accounts at `viewer`, `user`, `controller`; one `PASS <check>` per check; final `S2 ok`; <= 70 lines):
IWP numbers gap-free per discipline; fields frozen at Ready (state set by hand in the script); `viewer` refused every command;
scope add/remove with `contains` links, second IWP refused for an owned item, Verified item refused, `estimated_hours`
derived and recomputed; oversize and undersize warning codes; `SplitIwp` both modes (counts, copied pins, voided open
constraints, source Split); pin with and without a pin code; need-by default and refusal when neither date exists; `manual`
accepted from `user`, the four module sources refused from `user` and accepted through `raise_constraint`; `suppressed`
after a person's clear with equal hash, new constraint with a different hash; `resolves` link on clear; a hidden
`resolved_by` answers as missing; aging flag; `RULES` word per row equals command word; rebuild equals incremental.
`--keep` seed: 3 IWPs (one Draft, one In development, one Constraint check), 40 scope items, 2 pinned documents (create the
document records by `tl_core` writes in the script), 3 constraints (manual, assigned, cleared).

## Guards T11 (S5) will mutate (name file:line in the report; run no mutants here)
Frozen fields at Ready; one-IWP-per-item rule; `estimated_hours` bound; sizing bounds; `check`-source refusal for non-modules;
suppress hash equality; need-by arithmetic; the word per `RULES` row; `not_closed`.

## Report requirements
`docs/templates/haiku-report.md` shape, <= 60 lines: deviations first; files; pins updated (each, why); acceptance output
(<= 5 lines per command); guards file:line; how the sizing warning travels; candidate learnings. Builder return <= 15 lines.

## Commit
Subject `P2-I2-S2: <imperative summary>`; body says what and why; end with the harness attribution line, then
`Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not merge; do not push.

## Escalation triggers
- *Blocked* if: the generated schema lacks a column or event a command needs; the pin link cannot be written without importing the documents module; a module-source check needs a `tl_core` change; an access word beyond the two named is needed; a pinned list changes by more than a name.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)

Builder-recorded deviations awaiting a Decision (second attempt, review F3/F4):
- F3 (open, blocks merge): scope is stored as `belongs_to` item -> IWP (source `rule`), not forward `contains`
  (core vocabulary holds `contains` only as the inverse; `handle_add_link` refuses it); `facts.py` reads both
  directions. Decide: keep `belongs_to` (S3/S4/T04a read it) or a core change to allow `contains`.
- F4: `RaiseConstraint` field is `source_kind` (not `source`: `Command.source` is the caller); `owner` accepts
  `user:<name>` only (the column pattern fits no module-role actor text). Decide: accept, or schema/pattern change.
