# Runbook — build an IWP, read and clear its constraints, read readiness, sign off, issue and hold

Purpose: take an interim work package (IWP) from a draft to an issued package to a foreman: its scope and pins, the constraints that hold it, the readiness checks, the two sign-offs, the issue, and a hold when the work must stop. Brief: field work packaging (`docs/brief-v0.4.md`, §8 and §9 for the packaging context). Constraints: ADR-0024 (`docs/adr/0024-constraints-on-any-record.md`). Module interface and rules: `packages/tl-modules/awp/README.md`, `packages/tl-modules/awp/AGENTS.md`.

Examples use project `P123`. Replace the IWP number, keys and actors with yours. Never paste a database URL into a ticket; give `--db` or set `TL_DB`.

## When to use
- Trigger: a foreman needs a package for next week's work and the scope is not yet packaged.
- Trigger: `tl awp readiness ls` shows an IWP that is not Ready, and someone asks why.
- Trigger: an IWP must be signed off, issued, or stopped on site.

## Before you start
- Access needed, per command (words are in `schema/settings/access-words.yaml`):
  | Work | Word | Who holds it |
  |---|---|---|
  | create, scope, pin, split, move (start-development, constraint-check, return-to-development) | `awp.iwp.edit` | user |
  | cancel | `awp.void` | the project's void holders |
  | sign off | `awp.iwp.signoff` | controller |
  | issue | `awp.iwp.issue` | controller |
  | hold, release the hold | `awp.iwp.hold` | controller |
  | raise, assign, clear, withdraw a constraint | `core.constraint.edit` | user |
  | read constraints (`constraint ls`, `show`, `groups`) | `core.constraint.view` | read |
- The sign-off roles are the project setting `awp.release.signoff_roles`. Two distinct people with one of those roles must sign off. Ask the project administrator which roles it holds before the sign-off day.
- The `--actor` flag names the person recorded on the events. On a dev ledger file any `user:X` may be given; on a Postgres ledger or a signed-in session the actor is the signed-in account (`docs/runbooks/accounts-and-access.md`). The examples below use `user:` names for a dev ledger.
- The readiness job runs in the worker. Run `uv run tl awp worker --once` after a change, or keep `uv run tl awp worker` running.
- Safe to run during business hours: yes for every step below.
- `tl awp iwp ls`, `show`, `scope`, `hash`, `readiness ls` and `readiness show` check no access word in the CLI; the module's class filter decides what is shown. A hidden record is absent, not marked hidden.

## Steps

### 1. Build the IWP
1. Create the IWP. It prints `created IWP <number>`.
   ```
   uv run tl awp iwp create --project P123 --discipline PIP --title "Level 2 pipe supports" --cwp P123-CWP-PIP-0001 --planned-start 2026-11-16 --planned-finish 2026-11-20 --foreman user:foreman-a --hours 40 --actor user:planner-a
   ```
   Expected: `created IWP P123-IWP-PIP-0001` (the number format is project, `IWP`, discipline, sequence).
2. Create each scope item. It prints `created scope item <key>`; keep the key.
   ```
   uv run tl awp iwp item-create --project P123 --commodity PIPE-6IN --description "6 in pipe spool" --qty 12 --uom M --hours 6 --cwp P123-CWP-PIP-0001
   ```
3. Add the scope items to the IWP, then pin the documents it needs. Pinning with no `--pin` pins the current revision.
   ```
   uv run tl awp iwp add-scope P123-IWP-PIP-0001 <scope-item-key> --project P123
   uv run tl awp iwp pin P123-IWP-PIP-0001 <document-key> --project P123
   uv run tl awp iwp scope P123-IWP-PIP-0001 --project P123
   ```
   Expected: `add-scope P123-IWP-PIP-0001 1 items version <v>`; `pin P123-IWP-PIP-0001 version <v>`; the scope lists the item.
4. Start development, then send the package to the constraint check. The check is what readiness evaluates.
   ```
   uv run tl awp iwp move P123-IWP-PIP-0001 start-development --project P123
   uv run tl awp iwp move P123-IWP-PIP-0001 constraint-check --project P123 --reason "scope complete"
   ```
   Expected: `move P123-IWP-PIP-0001 version <n>` each time.

### 2. Read and clear constraints
1. List the open blocking constraints on the project, then the ones on this IWP.
   ```
   uv run tl constraint ls --project P123 --blocking
   uv run tl constraint ls --project P123 --subject P123-IWP-PIP-0001
   ```
   Expected: one line per constraint with its key, category, owner and state. The total is the count the viewer may see.
2. Show one constraint, then group the list if the owner or the age is the question.
   ```
   uv run tl constraint show <constraint-key> --project P123
   uv run tl constraint groups --project P123 --by owner
   ```
3. Raise a manual constraint when something is missing that no check sees. The phase `ready` blocks the Ready move; the category is from the closed list (`materials`, `labour`, `scaffold`, `equipment`, `permit`, `engineering`, `rfi`, `predecessor`, `other`).
   ```
   uv run tl constraint raise --project P123 --subject P123-IWP-PIP-0001 --phase ready --severity blocking --category permit --owner user:planner-a --description "permit to work not yet issued" --due 2026-11-13
   ```
   Expected: `raised <key> version <v>`.
4. Assign an open constraint to its owner, then clear it when it is resolved. Clear needs a reason.
   ```
   uv run tl constraint assign <constraint-key> --project P123 --owner user:planner-a
   uv run tl constraint clear <constraint-key> --project P123 --reason "permit issued, reference PTW-0042" --cleared-at 2026-11-12
   ```
   Expected: `assign <key> version <v>`; `clear <key> version <v>`.
5. A constraint on a record you may not read is not listed. Do not ask for a wider viewer to see it; ask the owner of the record.

Known limit: a new blocking constraint on an IWP that is already Issued does not put it On hold. The brief's rule (Q1 in `docs/tickets/P2-I2/STATE.md`; `docs/build-spec/DEFERRED.md`) is not built. Hold it by hand (step 6) if the work must stop.

### 3. Read readiness
1. Run the readiness job, then read the last evaluation.
   ```
   uv run tl awp worker --once
   uv run tl awp readiness show P123-IWP-PIP-0001 --project P123
   uv run tl awp readiness ls --project P123
   ```
   Expected from `show`: `readiness P123-IWP-PIP-0001`, `ready yes` or `ready no`, `checks <passing>/<total>`, then one line per check.
2. Read the checks that are not passing. A `blocked` check names the record to resolve. An `unknown` check stops Ready unless `awp.release.allow_unknown_checks` is true.
3. The nine checks: `documents_current`, `rfis_answered`, `materials_reserved` and `constraints_cleared` are real. `permits_planned`, `inspections_planned`, `labour_requested`, `predecessors_handed_over` and `model_slice_available` answer `n_a` in this release and count as passing (D9).
4. The IWP moves to `Ready` only when every check passes. The job then writes `IWP.Ready`. A webhook subscribed to that event receives it (`docs/runbooks/webhook-operations.md`).

Note: one worker run takes one batch of 100 outbox events. After a large setup, run the worker several times before an IWP event is seen.

### 4. Sign off
1. Read the record hash. The sign-off carries it; a stale hash is refused.
   ```
   uv run tl awp iwp hash P123-IWP-PIP-0001 --project P123
   ```
   Expected: `record hash <sha256>`.
2. Each of two distinct controllers signs off with that hash. The IWP must be `Ready`.
   ```
   uv run tl awp iwp sign-off P123-IWP-PIP-0001 --project P123 --hash <sha256> --actor user:controller-a
   uv run tl awp iwp sign-off P123-IWP-PIP-0001 --project P123 --hash <sha256> --actor user:controller-b
   ```
   Expected: `sign-off P123-IWP-PIP-0001 version <n>` each time.
3. If the scope or a pin changes after a sign-off, the hash changes. Read the hash again and have both signers sign again.

### 5. Issue
1. Issue to the foreman with the hash of the current record.
   ```
   uv run tl awp iwp issue P123-IWP-PIP-0001 --project P123 --hash <sha256> --foreman user:foreman-a --actor user:controller-a
   ```
   Expected: `issue P123-IWP-PIP-0001 version <n>`.
2. Read the result: `uv run tl awp iwp show P123-IWP-PIP-0001 --project P123` shows the state `Issued`, the foreman, and the two sign-offs.

### 6. Hold and release the hold
1. Put the IWP on hold, with a reason that a foreman can read.
   ```
   uv run tl awp iwp hold P123-IWP-PIP-0001 --project P123 --reason "crane unavailable" --actor user:controller-a
   ```
   Expected: `hold P123-IWP-PIP-0001 version <n>`. A hold is allowed from `Ready`, `Issued` or `In progress`.
2. Lift the hold when the reason is gone.
   ```
   uv run tl awp iwp release-hold P123-IWP-PIP-0001 --project P123 --reason "crane back" --actor user:controller-a
   ```
   Expected: `release-hold P123-IWP-PIP-0001 version <n>`.

### 7. Reports
```
uv run tl awp report iwp_status --project P123
uv run tl awp report iwp_readiness --project P123 --csv
uv run tl awp report constraints_by_owner --project P123
uv run tl awp report constraints_by_age --project P123
```
Expected: one line per row, fields two spaces apart; with `--csv` a header line, then one line per row.

## Verify
- `uv run tl awp iwp ls --project P123` lists the IWP with its state.
- `uv run tl awp readiness show P123-IWP-PIP-0001 --project P123` shows `ready yes` only after every check passes.
- After the second sign-off, `uv run tl awp iwp show P123-IWP-PIP-0001 --project P123` lists two signatures.

## Roll back
- A wrong scope item or pin: remove it with `uv run tl awp iwp remove-scope P123-IWP-PIP-0001 <key> --project P123`, or pin the right revision. Nothing is deleted; the earlier state stays in the history.
- A wrong constraint: withdraw it with `uv run tl constraint withdraw <constraint-key> --project P123 --reason "..."`. Do not edit it.
- An IWP that should not go ahead: cancel it with `uv run tl awp iwp cancel P123-IWP-PIP-0001 --project P123 --reason "..."` (access `awp.void`). Cancel is allowed only from the live states (`IWP_LIVE_STATES` in `packages/tl-modules/awp/src/tl_mod_awp/actions.py`).
- Events are never edited. Corrections are new events (ADR-0024; `packages/tl-modules/awp/AGENTS.md`).

## Known limits
- Q1 (`docs/tickets/P2-I2/STATE.md`): a new blocking constraint on an Issued IWP does not put it On hold. Hold it by hand.
- D33: list-level counts (Ready and Constraints per IWP row) are a follow-up read. Use `readiness ls` and `constraint ls --subject` for them.
- WBS constraint opt-in is deferred (`docs/build-spec/DEFERRED.md`; D18 in `docs/tickets/P2-I2/STATE.md`). Do not expect a constraint on a WBS node.
- D37: agents hold no `core.constraint.*` word. An agent reads IWPs and readiness through MCP but raises no constraint.

## Related
- `packages/tl-modules/awp/README.md` (interface), `packages/tl-modules/awp/AGENTS.md` (rules), `docs/runbooks/awp.md` (WBS, CWAs and the rollup), `docs/runbooks/webhook-operations.md` (the `IWP.Ready` subscription), `docs/adr/0024-constraints-on-any-record.md`, `docs/reference/awp.md` (the command and read reference).
