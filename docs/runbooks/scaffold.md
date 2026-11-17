# Runbook — scaffold register: request, erect, inspect, tag, release, modify, dismantle, and what the refusals mean

Purpose: run a scaffold from its request to removal, read the register, and act on the inspections-due flags.
Module: [scaffold](../modules/scaffold/README.md). Package: `packages/tl-modules/scaffold/README.md`. Brief: §9 M9.

## When to use
- A scaffold is requested for an IWP, designed, erected, inspected, released for use, changed, dismantled or removed.
- The register must show what stands, its state and its next inspection.
- A scaffold is flagged `inspection due` or `overdue` and an inspection is needed.
- A work package cannot be released and the readiness check `scaffold_tagged` says a requiring scaffold is not tagged green.

## Before you start
- Access: reads need `scaffold.view`. Register, design, erect, inspect, release, modify, dismantle and remove need the
  `user` table word. Tagging green needs the `controller` table word (`scaffold.tag.green`); no other role is needed.
  The words are in `schema/settings/access-words.yaml`.
- There is no `tl` command for scaffolds in this build. Writes go through the API command door; reads go through the API,
  the TUI register, or the API client.
- Safe to run during business hours: yes.

## Steps

### Write a scaffold move (API)
1. Send the move as `POST /commands/<Command>` with the command's body. The nine commands are `RegisterScaffold`,
   `DesignScaffold`, `ErectScaffold`, `InspectScaffold`, `TagScaffoldGreen`, `ReleaseScaffold`, `ModifyScaffold`,
   `DismantleScaffold` and `RemoveScaffold`. The body fields are in `docs/reference/openapi.json`.
2. Order of a normal life: `RegisterScaffold` (Requested) → `DesignScaffold` (Designed) → `ErectScaffold` (Erecting) →
   `TagScaffoldGreen` (a pass: the tag is green and the scaffold is Inspected) → `ReleaseScaffold` (In Use).
3. A failed inspection is `InspectScaffold` with a fail result. On an Erecting scaffold it stays Erecting; on an Inspected or
   In Use scaffold it moves to Modify. A conditional inspection is recorded with `InspectScaffold`.
4. `ModifyScaffold` moves an Inspected or In Use scaffold to Modify. `DismantleScaffold` starts dismantling.
5. `RemoveScaffold` ends the scaffold. It withdraws a request that never stood (Requested, Designed) and ends a dismantled one.

### Read the register (TUI)
1. Start the TUI with `just tui` (project from `TL_PROJECT`, default `P123`), then open the command palette and choose `scaffolds`.
2. The register lists the scaffolds. Keys: `s` cycles the state filter, `o` shows only the overdue scaffolds, `x` writes the
   visible list as CSV to `scaffolds-<project>.csv`, `X` writes it as JSON lines to `scaffolds-<project>.jsonl`.
3. The record screen shows one scaffold. `Esc` closes it and `F5` reads it again. The TUI writes nothing from these screens:
   use the API for moves.

### Read the register (API)
1. `GET /projects/{project}/scaffolds` lists the visible scaffolds.
2. `GET /projects/{project}/scaffolds/{key}` reads one scaffold with its inspections. A hidden scaffold answers as not found.
3. `GET /projects/{project}/scaffold-due` lists the standing scaffolds due for inspection today or earlier.
4. `GET /projects/{project}/scaffold-export` exports the visible list as CSV or JSON lines.

### Inspections due
1. The job `scaffold.inspections_due` runs once per project and day (job id `inspdue:<project>:<YYYY-MM-DD>`). For each standing
   scaffold past its interval it appends one `Scaffold.InspectionDue`. The interval is `scaffold.inspection.interval_days`
   (default 7).
2. The job never changes a tag or a state. A second run on the same day writes nothing.
3. This build has no command to queue the job. Confirm with the platform owner how it is queued in your deployment (see the
   open question in the package report).

## Refusals and what they mean
The exact texts are in the module code (`errors.py`, `handlers/`, `guards.py`); the API returns them in the error body.
This table gives the meaning only.

| Refusal | Meaning | What to do |
|---|---|---|
| Forbidden for the command | Your account lacks the word for this command | Ask a person with the word |
| Tag refused for the word | `TagScaffoldGreen` needs `scaffold.tag.green` (controller) | Ask a controller |
| Release refused | `ReleaseScaffold` needs an Inspected scaffold with a green tag | Tag it green first |
| Dismantle refused, work package named | An IWP with a live `requires` link is Issued, In progress or On hold, or another open scaffold request of such an IWP exists | Wait until the work package is released or closed; the refusal names it |
| Dismantle refused, "a work package you cannot see" | A holding work package is hidden from you; it still blocks | Ask someone who may see it |
| Refused on a Removed scaffold | Removed is final; generic commands (`guards.not_removed`) are refused | Register a new request |

## Roll back
- Events are immutable. There is no undo. Correct a wrong move with the next command the state allows: for example, a wrong
  request is withdrawn with `RemoveScaffold` (from Requested or Designed); a wrong inspection is answered by a new inspection.
- Do not edit the database rows. The projection is rebuilt from the events (`just rebuild-projections`).

## Related
- Module page: `docs/modules/scaffold/README.md`; package README and rules: `packages/tl-modules/scaffold/`.
- Requisitions (the scaffold request and its `requires` links): `docs/runbooks/requisitions.md`.
- Weekly cycle and readiness of a work package: `docs/runbooks/iwp-readiness.md`.
- API client and retries: `docs/runbooks/api-retries.md`.
