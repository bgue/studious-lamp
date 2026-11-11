# Runbook — requisitions: raise, approve, run a work order, refusals, numbering and agent proposals

Purpose: raise a requisition for labour, material, a general service or a scaffold, approve or reject it, and run the work
order that approval opens, at the terminal and in the TUI. Brief: §9 M9. Module: `docs/modules/requisitions/README.md`.
Verbs and fields are those of `tl req --help` and `tl wo --help` (P2-I4A T04d, T04e1).

## When to use
- Crew, material, a general service or a scaffold is needed for an IWP.
- A requisition needs a decision, or an approved requisition's work order must move on.
- Someone asks why a requisition or work order cannot be seen or changed.

## Before you start
- Sign in: `uv run tl login <name>` (the password is asked without echo, or read with `--password-stdin`; never put it on the command line).
- Ledger from `--db` or `TL_DB`; project from `--project P123` on every write and on `wo` reads.
- Words held by role (`schema/settings/module-roles.yaml`): `viewer` reads; `user` raises, edits, cancels, starts and completes; `superuser` also approves, rejects, schedules, assigns and closes. An active admin holds all. A missing word is refused (below). Grant: `uv run tl admin roles grant <name> --project P123 --module requisitions --role superuser --reason "..."`.
- Safe to run during business hours: yes. Each command is one unit of work.
- Confidentiality (ADR-0016): a requisition for a hidden IWP does not exist for you. Its key answers "no requisition" as a missing one does.

## Steps

### Raise a requisition
Pick the kind. The output is `raised <key>  version <v>`. Version numbers are as printed; read them, do not compute them.
1. Labour: `uv run tl req raise-labor --project P123 --subject "Pipefitters" --craft Pipefitter --headcount 6 --start 2026-11-02 --end 2026-11-13 --for P123-IWP-PIP-0001`. Also `--classification`, `--shift`, `--requirements`, `--need-by`, `--priority low|normal|high|urgent`. Headcount is 1 to 500; dates are `YYYY-MM-DD`.
2. Material: `uv run tl req raise-material --project P123 --subject "Flanges" --line FLG-WN-6-150-A105:10:ea --for P123-IWP-PIP-0001`. `--line ITEMKEY:QTY:UOM` repeats, 1 to 200 times; `--from-location` names a location. An unknown item is `error: no item <key>` (exit 1); a malformed line is `error: --line <v>: expected ITEMKEY:QTY:UOM` (exit 1).
3. General: `uv run tl req raise-general --project P123 --subject "Rack 12 lift" --type crane_lift`. `--type` is a code of `GeneralRequisitionType`.
4. Scaffold: `uv run tl req raise-scaffold --project P123 --subject "Level 3 east" --purpose "Access to the east face" --days 14`.
- `--for` names the IWP or CWP served by its number; an unknown one is `error: no IWP <number>`. It is the requisition's confidentiality subject: it inherits that record's class.
- `--need-by` is optional on every kind. A requisition starts Requested.

### Change a requisition that is still Requested
`uv run tl req edit P123-REQ-LAB-0001 --project P123 --headcount 8 --expected-version 2`. Only the fields named are changed; no field at all is a usage error (exit 2). Each change is a `Requisition.Revised` event that holds `[old, new]` per field. Once approved, a requisition is changed by its work order only.

### Approve, reject or cancel
1. Approve (superuser): `uv run tl req approve P123-REQ-MAT-0001 --project P123 --expected-version 2`. Prints `approve <key>  version <v>`. It opens the work order in the same step; the key is named by `tl req show`.
2. Reject (superuser): `uv run tl req reject P123-REQ-LAB-0001 --project P123 --reason "No budget" --expected-version 2`. `--reason` is required (missing: exit 2).
3. Cancel (requester or superuser): `uv run tl req cancel P123-REQ-LAB-0002 --project P123 --reason "Not needed" --expected-version 2`. On an Approved requisition this also cancels its Open work order.
4. Read it back: `uv run tl req show P123-REQ-MAT-0001 --project P123` prints the state, the kind's fields, `serves <IWP>`, `work order <key>` (or `-`), `approved by`.

### Run the work order at the terminal
The work order (`P123-WO-0001`, shown by `tl req show`) moves Open, Scheduled, In progress, Done, Closed. Each step prints `<verb> <key>  version <v>`.
1. Schedule (superuser): `uv run tl wo schedule P123-WO-0001 --project P123 --start 2026-11-16 --finish 2026-11-20 --hours 40.0`. `--hours` is optional, one decimal place.
2. Assign (superuser): `uv run tl wo assign P123-WO-0001 --project P123 --to user:rob`. `--to` is `user:NAME` or free text.
3. Start (user): `uv run tl wo start P123-WO-0001 --project P123`. `--at` takes the time the work started (ISO). A blocking constraint on the work order refuses the start.
4. Complete (user): `uv run tl wo complete P123-WO-0001 --project P123 --hours 40.0`. `--hours` is the actual hours (one decimal place; `40` alone is refused); `--at` takes the finish time (ISO).
5. Close (superuser): `uv run tl wo close P123-WO-0001 --project P123`. Only a Done work order closes. Closing moves the requisition to Closed.
- Read: `uv run tl wo ls --project P123 --state Closed` (filters `--state`, `--assigned`, `--limit`) and `uv run tl wo show P123-WO-0001 --project P123`.

### Run the work order in the TUI
The TUI reads requisitions and work orders; it does not write them. Every write above is a terminal command.
1. Palette (`Ctrl+P`, the command palette): `requisitions` opens the requisition log; `work-orders` opens the work order backlog.
2. Requisition log: `k` changes the kind, `s` the state, `m` shows only mine.
3. Work order backlog: `s` the state, `m` mine, `F5` reloads, Enter opens one work order (text only), `Esc` closes.

### What a refusal means
Every refusal is one `error:` line and exit 1 unless noted. The text is fixed.
| Text | Meaning | What to do |
|---|---|---|
| `error: forbidden: ...` | Your account does not hold the word for this command or read (a plain `user` cannot approve). | Ask an admin for the module role. Do not retry as someone else. |
| `error: no requisition <key>` / `error: no work order <key>` | No such record for you: unknown, of another project, or hidden from you. The same text for all three. | Check the key and `--project`. Do not ask for the hidden record. |
| `error: no IWP <number>` / `error: no item <key>` | `--for` or `--line` names nothing you can see. | Correct the number or key. |
| `error:` with a version message | `--expected-version` is not the current version (someone else moved it). | Run `show`, read the version, and repeat the command. |
| Usage error (exit 2) | A required option is missing, such as `--reason` or `--project`. | Add the option. |
| `error:` line from a move | The state does not allow the verb (for example `wo start` before `wo schedule`). | Run `show` to see the state, then the verb that follows it. |

### Numbering
One gap-free counter per kind: `P123-REQ-LAB-0001`, `-REQ-MAT-`, `-REQ-GEN-`, `-REQ-SCF-`; the work order has its own, `P123-WO-0001`. Keys are assigned when the command is written. Read keys with `tl req ls` (in key order, with a count line first) and `tl wo ls`. `tl req ls --kind labor|material|general|scaffold --state Requested --requester user:uma --for P123-IWP-PIP-0001` filter.

### What an agent may propose
An agent (MCP `propose_requisition`, with `project`, `kind`, `subject` and the kind's fields) creates a proposal, not a requisition. Nothing changes and no row appears until a person accepts it:
1. `uv run tl proposal ls --project P123` lists pending proposals.
2. `uv run tl proposal accept <id> --actor user:uma` runs `RaiseRequisition` as that person, who needs `requisitions.raise`.
An agent never approves, rejects, schedules, assigns, starts, completes, closes, edits or cancels. Those are listed in `tests/tools/proposable_exclusions.toml`. See `docs/runbooks/proposal-review-queue.md`.

## Not built yet
Fulfilment (`tl req fulfil`), stock lots, the shortage constraint, the labour forecast, `tl req report` and the TUI write actions. See `docs/build-spec/DEFERRED.md`. Do not look for them in the verbs above.

