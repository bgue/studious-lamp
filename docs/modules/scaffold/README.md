# Module spec: scaffold (scaffold register)

Status: as built for P2-I4B. Written by: P2-I4B-T12 implementer, from the as-built reports S1, T01, T05a, T05b, T07a, T07b, T09a,
T09b1 and T09b2. Brief sections: §9 (M9), §18, §24.
Package README: `packages/tl-modules/scaffold/README.md`. Runbook: [scaffold.md](../../runbooks/scaffold.md).
Build spec (contracts): `docs/build-spec/phase2-contracts-draft.md` §3, As built.

## Purpose
A scaffold is the temporary structure a work package needs before its work can start. The register records each scaffold
from its request, through design, erection, inspection and tagging, to release for use, change, dismantling and removal.
A green tag is the condition for release. Standing scaffolds are flagged when their next inspection is due. Two readiness
checks use the register: `scaffold_tagged` and `labour_requested`.

## Record types
| Type | Table | Purpose | Workflow |
|---|---|---|---|
| `scaffold.Scaffold` | `cur_scaffold_scaffold` | One scaffold, one per requisition request | `scaffold.scaffold`: Requested, Designed, Erecting, Inspected, In Use, Modify, Dismantle, Removed |
| `scaffold.ScaffoldInspection` | `cur_scaffold_scaffold_inspection` | One inspection of a scaffold (a fact; no generic commands) | none |

Both record types are offline class `none`: a register entry, a tag and a release are acts on the authority, not drafts.

## Events
| Event type | Meaning |
|---|---|
| `Scaffold.Registered` | A request became a scaffold (elevation, gridline, load class from the request) |
| `Scaffold.Designed` | The design is recorded |
| `Scaffold.Erecting` | Erection started; carries the next due day |
| `Scaffold.Inspected` | A pass (green tag) or a conditional result |
| `Scaffold.Released` | Released for use with a green tag |
| `Scaffold.Modified` | A change, or a failed inspection of an Inspected or In Use scaffold |
| `Scaffold.DismantleStarted` | Dismantling started |
| `Scaffold.Removed` | Ended (final) |
| `Scaffold.InspectionDue` | Appended by the inspections-due job once per due day; changes no tag or state |

Every event carries an optional valid-time tag `at`.

## Commands and who may run them
Nine module commands. Each is one access word from `schema/settings/access-words.yaml`.

| Command | Word | Table word | Moves |
|---|---|---|---|
| `RegisterScaffold` | `scaffold.register` | user | request → Requested |
| `DesignScaffold` | `scaffold.design` | user | Requested → Designed |
| `ErectScaffold` | `scaffold.erect` | user | Designed → Erecting |
| `InspectScaffold` | `scaffold.inspect` | user | conditional or fail only; a fail on Inspected or In Use moves to Modify |
| `TagScaffoldGreen` | `scaffold.tag.green` | controller | a pass: green tag; Erecting or Modify → Inspected |
| `ReleaseScaffold` | `scaffold.release` | user | Inspected → In Use; needs a green tag |
| `ModifyScaffold` | `scaffold.modify` | user | Inspected or In Use → Modify |
| `DismantleScaffold` | `scaffold.dismantle` | user | Inspected, In Use or Modify → Dismantle; refused by the dismantle check |
| `RemoveScaffold` | `scaffold.remove` | user | Requested, Designed or Dismantle → Removed |

Reads need `scaffold.view` (table word `read`). `TagScaffoldGreen` is the one controller word; no new account role was added.

## Dismantle check
`rules.dismantle_blockers` refuses dismantling while an IWP that holds the scaffold (a live `requires` link) is Issued,
In progress or On hold, or while another open scaffold request of such an IWP exists. The scaffold's own request is left out.
A work package the reader cannot see still blocks, and is named only as "a work package you cannot see". No hire quantities
are checked here (W3-3).

## Inspections due
The job kind `scaffold.inspections_due` runs per project and day (job id `inspdue:<project>:<YYYY-MM-DD>`). It reads the
interval `scaffold.inspection.interval_days` (default 7; `schema/settings/platform.yaml`). It flags each standing scaffold
(Inspected, In Use or Modify) whose inspection is due or overdue, once for each due day. It never changes a tag or a state.

## Readiness checks
| Check | Replaces or adds | Rule (short) |
|---|---|---|
| `scaffold_tagged` | adds (decision D9) | Every scaffold that a work package requires is Inspected or In Use, green and not overdue |
| `labour_requested` | replaces the `n_a` placeholder of the same name in `tl_mod_awp` (decision D10) | An approved labour requisition serves the work package and covers its planned window |

Each check reads its data in one SELECT. `labour_requested` runs with no viewer (a job runs it) and answers `unknown` with a fixed detail when its read fails.

## Reads and the viewer
Views: `scaffold_list`, `scaffold_detail`, `due_list`, `export_rows`. They take `viewer=` (default `confidentiality.LOWEST`).
The API routes pass the caller's viewer. Export is CSV with a formula guard (a cell that starts with `=`, `+`, `-` or `@` gets
a leading quote) or JSON lines; the CSV carries no `id` column.

## Visibility
A scaffold is hidden when its source is hidden: two `SUBJECT_LINKS` rows in `tl_core.confidentiality` (scaffold over
`for_record_id`; inspection over `scaffold_id`). A hidden scaffold reads as a missing one. An inspection has no class of its own.

## Surfaces
| Surface | As built | Not yet |
|---|---|---|
| API | Nine commands at `POST /commands/<Command>`; reads `GET /projects/{project}/scaffolds`, `/scaffolds/{key}`, `/scaffold-due`, `/scaffold-export` | — |
| TUI | Palette `scaffolds`; register screen (`s`, `o`, `x`, `X`); record screen (`Esc`, `F5`); both read-only | Writes from the TUI |
| `tl` CLI | — | No scaffold group |
| MCP | — | No scaffold tools |

The CLI and MCP surfaces wait for the extension hooks (the command splat in `tl_api/commands.py` and the router line in
`tl_api/app.py`, which move into `module.py`).

## Access words
Ten words: `scaffold.view`, eight `user` words (`register`, `design`, `erect`, `inspect`, `release`, `modify`, `dismantle`,
`remove`) and `scaffold.tag.green` (controller). The pinned list is in `packages/tl-core/tests/auth/test_access_words.py`.

## Record shape and Phase 3 compatibility
Tables and views are generated from `schema/modules/scaffold/`; no hand-written DDL. A later phase may add a CLI group and MCP
tools without changing the events above.
