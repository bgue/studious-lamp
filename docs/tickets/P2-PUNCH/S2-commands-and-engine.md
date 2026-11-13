# P2-PUNCH-S2 — punch commands: raise, edit, clear, verify, reopen, void; the subject join

Status: ready after S1 merges
Tier: builder
Kind: piece
Review: full
Labels: core, access, confidentiality
Depends on: S1
Branch: `p2/punch-s2-engine`
Worktree: `/home/user/wt/punch-s2`
Approver (access words, confidentiality join): orchestrator (P2-Q10; APPROVALS line at merge)

## Goal
After this piece the six commands exist as module commands with access words, handlers, state guards and the confidentiality rule (a
punch item is hidden when its source record is); `tl_mod_quality.api` gives `open_punch_for`; every command is a `ProposableCommand` row or an exclusion;
the actions table says which action shows in which state; `tests/punch_world.py` is the shared test helper. No view, route, CLI, screen or tool (tickets).

## Brief references (pasted; `docs/tickets/P2-PUNCH/README.md` is authoritative)
Commands (model, word, effect). Every model carries the base envelope (`actor`, `source`, `scope`, optional `intent` by the dispatcher) and is `extra="forbid"`;
a state command takes optional `expected_version: int | None` (stale is refused with a fixed message; `None` skips the check); texts are bounded and cleaned with `tl_core.text`.
| Command | Word | Effect |
|---|---|---|
| `RaisePunchItem` | `quality.punch.raise` | fields `subject` (1..200), `description` (<= 1000, optional), `area`, `system` (<= 64), `due_on`, `assignee` (<= 120), `category` (A/B/C, default B), `from_record_id` (any record id, optional). Creates the record in `Open`, key `P123-PUN-0001` by the numbering pattern, `raised_by` = the context actor (never an input: `raised_by` in the body is refused as an unknown field), and, when `from_record_id` is set, the link `raised_against` from the item to it (`by_module`) and `source_id`. A hidden or unknown source answers one text, the same as unknown (`no record with that id`) |
| `EditPunchItem` | `quality.punch.edit` | `Open` only; at least one of `subject`, `description`, `area`, `system`, `due_on`, `assignee`, `category` (none is a validation error); the raiser, the current assignee or a holder of `quality.punch.verify` may edit, anyone else gets a fixed message; `PunchItem.Edited` carries `changes {field: [old, new]}`; the source cannot be changed |
| `ClearPunchItem` | `quality.punch.clear` | `Open -> Cleared`; `note` required (1..300); optional `at` (valid time: not in the future, not before the raise day); stores `cleared_by` = the actor |
| `VerifyPunchItem` | `quality.punch.verify` | `Cleared -> Verified`; the actor must differ from `cleared_by` (fixed message `the person who cleared a punch item may not verify it`); optional `at` as above |
| `ReopenPunchItem` | `quality.punch.reopen` | `Cleared` or `Verified -> Open`; `reason` required (1..300); `reopen_count` + 1; cleared and verified columns reset |
| `VoidPunchItem` | `quality.punch.void` | `Open` or `Cleared -> Void`; `reason` required (1..300) |
Rules: each move is one unit of work, `by_module=True`, through the workflow engine (`Workflow.Transitioned` in `quality.punch_item`); a `Void` item accepts no command (fixed
message `a void punch item accepts no further change`); a wrong state is a fixed message naming the state and the states the command needs; ids are resolved through a viewer-filtered
lookup that answers "unknown" for a hidden or missing id (same text); no password, hash or token appears in any text.
**Confidentiality (ADR-0016 section 5, ADR-0024 pattern):** add the generic subject part to `tl_core/confidentiality.py` `hidden_sql`: a record type that names a subject is hidden when
its subject is. Do not invent the shape: `git show p2/i4a:packages/tl-core/src/tl_core/confidentiality.py` already holds it (`SUBJECT_LINKS`, `_subject_chain`, `_HOPS = 2`, import
`is_module_record_type`). Port it with **only the punch row** `("quality.PunchItem", "cur_quality_punch_item", "id", "source_id")` and none of the requisitions rows, keeping names, order and
comments identical where they do not mention requisitions, so that the later merge of `p2/i4a` is a union of tuple rows. A null or dangling source falls back to the item's own class.
If `p2/i4a` is unreadable, build the same shape from the constraint join already in the file and say so in the report.
`api.py` (imports only `tl_core` and this module's tables): `open_punch_for(conn, record_id, *, categories=None, viewer=confidentiality.LOWEST) -> list[PunchRef]` (non-terminal items
raised from `record_id`, states `Open` and `Cleared`; `PunchRef(id, key, state, category, due_on)`; at most 500, a fixed `ValueError` over; the hidden filter before the limit). The default
viewer is the lowest clearance on every read, never widened.
ADR-0027 row-or-exclusion: `module.py` `PROPOSABLE = (ProposableCommand("propose_punch_item", RaisePunchItem, handle_raise_punch_item, "user"),)`; the other five commands go in
`tests/tools/proposable_exclusions.toml` (`ClearPunchItem`, `EditPunchItem`: "person acts directly"; `VerifyPunchItem`, `ReopenPunchItem`, `VoidPunchItem`: acts). Grep first: if the file or
its test is absent, create the file in the shape of `git show p2/i4a:tests/tools/proposable_exclusions.toml` (`[commands]`, name = reason) with only these five lines, and add a package
test that every command of `PUNCH_COMMANDS` is a row or an exclusion; say which in the report.
`ModuleSpec`: `commands=PUNCH_COMMANDS`, `actions` hook (below), `generic_commands` for `quality.PunchItem`: `SetPsetValues`, `AddLink`, `AttachFile` and the link-life commands only (not
`UpdateRecord`, `VoidRecord`, `TransitionWorkflow`: the envelope and the state change only through the module's commands, ADR-0010 addendum 1), guard `not_void` on each; `offline_drafts`
lists `RaisePunchItem` (its type is `draft_only`).
`actions.py` (ADR-0010 addendum 2026-10-21): `RULES` rows (command, label, level, record types, states) for Edit (`Open`), Clear (`Open`), Verify (`Cleared`), Reopen (`Cleared`, `Verified`),
Void (`Open`, `Cleared`); a test holds each row's level equal to the command's access word.
Intent (ADR-0025): commands inherit the slot; `S2.py` asserts an `intent` sent with `RaisePunchItem` and `VerifyPunchItem` is stored (`events.intent`) and read back, and that a 501-character `why` refuses with no event written.

## Interfaces (verbatim shapes to copy; open these)
- Command model, spec and handler shape: `packages/tl-modules/awp/src/tl_mod_awp/{commands,module,actions}.py`, `packages/tl-modules/awp/src/tl_mod_awp/handlers/` (one IWP handler), `packages/tl-modules/materials/src/tl_mod_materials/{commands,guards}.py`; the I4A shape is on branch `p2/i4a` (`git show p2/i4a:packages/tl-modules/requisitions/src/tl_mod_requisitions/commands.py`, `.../handlers/requisitions.py`, `.../actions.py`, `.../api.py`).
- Numbering allocation: `tl_core.numbering` as `handlers/iwp.py` uses it (`allocate_key`); module record creation: `tl_core.services.records.create_module_record`; links: `tl_mod_awp/linking.py`.
- Test helper: `packages/tl-modules/awp/tests/awp_world.py` (`World.call(who, name, **fields)`: access word first via `require_command_access`, then the handler, one unit of work each) and `git show p2/i4a:packages/tl-modules/requisitions/tests/req_world.py` (intent check, grants).

## Context (<= 14 files)
The files above; `schema/modules/quality/*.yaml`, `schema/settings/access-words.yaml` (from S1); `docs/adr/0027-agent-first-layer.md` decisions 4 and 5 (abridged);
`docs/reports/P2-PUNCH/S1.md`. may explore: `docs/reports/P2-I4A/S2.md` (branch `p2/i4a`), `packages/tl-core/src/tl_core/services/commands.py`.

## Allowed paths
- `packages/tl-modules/quality/src/tl_mod_quality/**` (create `commands.py`, `handlers/`, `actions.py`, `api.py`, `guards.py`, `errors.py`, `views.py` empty stub for T01; edit `module.py`, `names.py`)
- `packages/tl-core/src/tl_core/confidentiality.py` (the generic subject part only) and the confidentiality test file `tests/confidentiality/test_core.py` (tests added)
- `packages/tl-modules/quality/tests/{punch_world.py, test_punch_commands.py, test_punch_visibility.py, test_exclusions.py}` (create; `test_exclusions.py` only if no repo-wide test exists), `packages/tl-modules/quality/pyproject.toml` (a dependency S1 omitted; name it)
- `tests/tools/proposable_exclusions.toml` (create or append)
- pinned lists (rule 12) as union: command lists, proposable lists, `packages/tl-modules/quality/tests/test_module_spec.py` (0 -> 6 commands), `tests/services/test_modules.py`
- `dev/accept/P2-PUNCH/S2.py`, `docs/reports/P2-PUNCH/S2.md` (create)
Not allowed: schema, other `tl_core/**` files, other modules, any `tl-api`, `tl-cli`, `tl-tui`, `tl-mcp` file (their registrations are in the tickets).

## Steps
1. Models, handlers and guards per command; `module.py` exports `PUNCH_COMMANDS` and `PROPOSABLE`; `names.py` constants.
2. `api.py`; `actions.py`; exclusions; the subject join.
3. `punch_world.py` (people `ada` admin, `uma` and `rob` users, `sue` the quality superuser by `grant_module_role`, `dora` the document controller, `vera` viewer; `World.call`, `scalar`, `rows`, `state`, `version`, a helper that makes a restricted correspondence item through `tl_mod_correspondence.handlers.create.create_item` plus `handle_set_confidentiality`, never a projection write).
4. Tests, then the acceptance script; one mutation pass.

## Acceptance (once each; one package per gate)
```
just check
uv run python dev/accept/P2-PUNCH/S2.py
just gate packages/tl-modules/quality/tests tests/services/test_modules.py tests/tools
just gate tests/confidentiality/test_core.py
just gate packages/tl-mcp/tests/test_mcp_server.py packages/tl-mcp/tests/test_intent_param.py
```
(`tests/tools` takes about 10 minutes: background.) `S2.py` (SQLite, one `PASS <check>` line per check, final `S2 ok`): a punch item raised by `uma` from an IWP has key `P123-PUN-0001`, state `Open`, `raised_by` `user:uma`, `source_id` the IWP and
one `raised_against` link; `raised_by` in the body is refused; a free-standing raise (no source) works; an unknown source and a restricted one (for `uma`) answer the same text and write nothing; edit by a stranger is refused, by the assignee works,
`Edited` carries `changes`; clear needs a note; `rob` clears, `rob` verifying is refused with the fixed message, `uma` (no word) is `forbidden`, `sue` verifies; `Open -> Verified` is refused; reopen needs a reason and resets the cleared
columns and counts 1; a verified item can be reopened; void works from `Open` and `Cleared`, a `Void` item refuses every command with the fixed message; a stale `expected_version` is refused; an `at` in the future is refused; a punch item
raised from a restricted correspondence item (by `dora`) is absent from `open_punch_for` for the default viewer and present for a cleared one, and `uma`'s `ClearPunchItem` on it answers as unknown; a constraint raised on a punch item
(core `RaiseConstraint`, advisory) is hidden when the source is; an intent round-trips on Raise and Verify and a bad one refuses; two threads raising 20 items get `-0001..-0020` with no gap and no repeat; `open_punch_for` returns only `Open`
and `Cleared` items; every command is a row or an exclusion.

## Mutation (<= 5 mutants + sentinel, in this worktree, 3 lines in the report)
Guards: verifier differs from clearer; the subject-join row; the `expected_version` check; the `Void` refusal; the state table (`Open -> Verified`).

## Report requirements
Standard piece report (<= 60 lines): deviations first; files; pinned lists changed; acceptance output (<= 5 lines per command); the join (ported from `p2/i4a` or rebuilt); exclusion-file outcome; intent outcome; mutation 3 lines; names the later tickets need (`PunchRef`, `PUNCH_COMMANDS`, the world helper API); candidate learnings.

## Commit
`P2-PUNCH-S2: <imperative summary>`; body says what and why; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not merge; do not push.

## Escalation triggers
- Blocked if: a command needs a table word not in `access-words.yaml`; the numbering allocator is not gap-free under two threads; any `tl_core` edit beyond the generic subject part looks necessary; the shape on `p2/i4a` cannot be reduced to the punch row without behaviour change.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
