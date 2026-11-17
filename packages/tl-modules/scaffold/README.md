# tl-mod-scaffold (`tl_mod_scaffold`)

Purpose: the scaffold register (brief §9 M9, as built for P2-I4B). A scaffold runs from request to removal through nine module
commands; a job flags erected scaffolds that are due for inspection; two readiness checks read the scaffold and the labour
requisitions of a work package. Human docs: `docs/modules/scaffold/README.md` and the runbook `docs/runbooks/scaffold.md`.

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_mod_scaffold.module:spec` | entry point `throughline.modules` | `ModuleSpec`: record types, projector, generic commands, command words |
| `module.SCAFFOLD_COMMANDS` | tuple of 9 `ScaffoldCommand` | model, handler and access word of each command (the API command door reads it) |
| `commands.py` | 9 command classes | `RegisterScaffold`, `DesignScaffold`, `ErectScaffold`, `InspectScaffold`, `TagScaffoldGreen`, `ReleaseScaffold`, `ModifyScaffold`, `DismantleScaffold`, `RemoveScaffold` |
| `views.py` | read functions | `scaffold_list`, `scaffold_detail`, `due_list`, `export_rows` (CSV with formula guard, or JSON lines) |
| `readiness.py` | readiness check `scaffold_tagged` | the work package's requiring scaffolds are tagged green, in use and not overdue |
| `labour.py` | readiness check `labour_requested` | an approved labour requisition serves the work package and covers its window |
| `rules.py` | pure functions | `tag_for`, `next_due`, `due_state`, `dismantle_blockers` |
| `inspections_due.py` | job kind `scaffold.inspections_due` | `job_id(project, today)`; one `Scaffold.InspectionDue` per due scaffold and day |
| `names.py` | constants | record types, table names, event types, access words, job kind |

## Depends on / used by
- Depends on: `tl-core`, `tl-schema`, `tl-adapters`, and `tl-mod-requisitions` (its `names`, and `api.open_requisitions_for`
  with `viewer=LOWEST`). The module never runs a requisitions handler.
- Reads one table of requisitions directly: `cur_requisitions_scaffold_request`, because the requisitions api has no
  single-request read (decision S1-F4; `docs/build-spec/phase2-contracts-draft.md` §3, As built).
- Used by: `tl-api` (the nine command routes at `POST /commands/<Command>`, and the read routes
  `GET /projects/{project}/scaffolds`, `/scaffolds/{key}`, `/scaffold-due`, `/scaffold-export`); `tl-tui` (palette `scaffolds`,
  the register and the record screen); the readiness registry (`scaffold_tagged`, and `labour_requested`, which replaces the
  `n_a` placeholder of the same name in `tl_mod_awp`).
- Not yet: no `tl` CLI group and no MCP tools. They wait for the extension hooks (see `AGENTS.md`).

## Commands
```
just test -- packages/tl-modules/scaffold
```

## Configuration
| Setting | Default | Notes |
|---|---|---|
| `scaffold.inspection.interval_days` | 7 | Days between inspections of an erected scaffold (`schema/settings/platform.yaml`). The inspections-due job reads it. |

Access words (`schema/settings/access-words.yaml`): `scaffold.view` (read); `scaffold.register`, `.design`, `.erect`,
`.inspect`, `.release`, `.modify`, `.dismantle`, `.remove` (user); `scaffold.tag.green` (controller). Ten words in all.

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P2-I4B (schema, rules and commands S1; readiness T05a, T05b; API T09a, T09b1; screens T07b). Last interface
change: P2-I4B (the read routes and the client methods).
