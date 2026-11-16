# Module spec: quality (punch list)

Status: as built for P2-PUNCH (first slice). Written by: P2-PUNCH-T09 implementer, from the as-built reports S1, S2, T02, T05, T06, T07, T08. Brief sections: §9 (M5), §18, §24.
Package README: `packages/tl-modules/quality/README.md`. Runbook: [punch-list.md](../../runbooks/punch-list.md). Reference: [punch.md](../../reference/punch.md).

## Purpose
The punch list is the list of defects and open works a project closes before handover. Anyone with the `user` word raises an item,
says who clears it and by when; the clearer records what was done; a different person with the `controller` word verifies it.
Each item is numbered per project (`P123-PUN-0001`), has one source record it was raised from (an IWP, a tag, a document or a
letter), and is hidden from a reader who may not read that source.

## Record types
| Type | Table | Purpose | Workflow |
|---|---|---|---|
| `quality.PunchItem` | `cur_quality_punch_item` | One punch item; numbered `<project>-PUN-nnnn` | `quality.punch-item`: Open, Cleared, Verified, Void |

## Events
| Event type | Meaning |
|---|---|
| `PunchItem.Raised` | Created, with area, system, due date, category, assignee, raiser and source |
| `PunchItem.Edited` | Changed fields (the change list is in the event) |
| `PunchItem.Cleared` | Work done: a note, who and when |
| `PunchItem.Verified` | Checked by someone other than the clearer |
| `PunchItem.Reopened` | Back to Open, with a reason; the count goes up |
| `PunchItem.Voided` | Ended with a reason; no later change |

## Commands and who may run them
Six module commands; each one is a word from `schema/settings/access-words.yaml`. A `user` word is any signed-in person with the
table word `user`; a `controller` word needs the table word `controller`, which the module superuser role grants.

| Command | Word | Table word |
|---|---|---|
| `RaisePunchItem` | `quality.punch.raise` | user |
| `EditPunchItem` | `quality.punch.edit` | user |
| `ClearPunchItem` | `quality.punch.clear` | user |
| `VerifyPunchItem` | `quality.punch.verify` | controller |
| `ReopenPunchItem` | `quality.punch.reopen` | controller |
| `VoidPunchItem` | `quality.punch.void` | controller |

Reads need `quality.view` (table word `read`). The module does not filter reads by role: a hidden source hides its item (below).

## States
`Open` → `Cleared` (clear) → `Verified` (verify, by another person). `Reopen` returns a `Cleared` or `Verified` item to `Open`. `Void`
(from `Open` or `Cleared`) is the only terminal state.

- The clearer may not verify the item they cleared (the message is fixed: `the person who cleared a punch item may not verify it`).
- Edit is open to the raiser, the assignee and a verifier. A void item accepts no change (`a void punch item accepts no further change`).
- Every state change checks the version the person read. A stale version is refused with `the record changed since it was read`.

## Visibility
A punch item is hidden when its source is hidden (ADR-0016): the subject join is one row (`quality.PunchItem` → `source_id`), followed
up to two hops. A hidden item is the same as a missing one for the reader: `no punch item <key>`, the same text, the same count, no row
in a list. Items raised from no source are visible to every reader with `quality.view`.

## Agents
An agent never clears, verifies, edits, reopens or voids. An agent may propose a new item (`propose_punch_item`); the proposal waits
until a person accepts it, and the accepting person's word decides (`quality.punch.raise`). Acceptance runs `RaisePunchItem` as that
person.

## Inspections and checklists (P2-INSP slice 1, as built)
Design: [inspections.md](../../build-spec/module-designs/inspections.md). Runbook: [inspections.md](../../runbooks/inspections.md).
Reference: [inspections.md](../../reference/inspections.md). Package: `packages/tl-modules/quality/README.md`.

| Type | Table | Purpose | Workflow |
|---|---|---|---|
| `quality.Checklist` | `cur_quality_checklist` | A question set; numbered `<project>-CHK-nnnn` | `quality.checklist`: Draft, Published, Retired |
| `quality.Inspection` | `cur_quality_inspection` | One planned inspection of a record; numbered `<project>-INS-nnnn` | `quality.inspection`: Planned, Scheduled, Done, Verified, Cancelled |

- A checklist is versioned: a Published one never changes; revise makes the next version in Draft and retires the one it replaces.
- An inspection pins the checklist version when it is scheduled. Recording computes the result (`accept`, `reject`, `conditional`);
  a `reject` or `conditional` result raises one punch item per failed question, linked to the inspection.
- The verifier is a controller who did not record the inspection. Reinspect plans a new inspection that names the first.
- Hidden through its subject, as a punch item is: a hidden inspection reads as a missing one.
- Readiness: the check `inspections_planned` on each IWP (`n_a` by default; `quality.inspections.required_for_iwp` makes it `blocked`
  when nothing is planned).
- Surfaces: CLI `tl insp` and `tl checklist`; API `GET /quality/inspections`, `/quality/inspections/{key}`,
  `/quality/inspections/export`, `/quality/checklists`, `/quality/checklists/{key}`; MCP reads and `propose_inspection`; TUI palette
  `inspections` (log and record; scheduling and recording are CLI only); demo `dev/demos/P2-INSP.sh`.
- Not built in this slice: the run-a-checklist screen, the checklist screens, the `--answers` export, and the TUI filters `o` (open),
  `d` (due), `h` (hold) and by area (the log has `s` state, `p` point, `m` mine). The runbook lists each one.

## Not built yet
Not in this slice; see [DEFERRED.md](../../build-spec/DEFERRED.md):
- the inspection runner screen and the checklist screens (follow-up slice of the inspections plan), deficiencies and ITPs;
- the Issue engine (Phase 3);
- the walkdown screen, photos, feed cards and web pages.

## Surfaces
| Surface | Where |
|---|---|
| CLI `tl punch` | `packages/tl-cli/src/tl_cli/punch.py`, `punch_write.py`, `punch_read.py` |
| API | `packages/tl-api/src/tl_api/routes/punch.py` (three GET routes) |
| MCP | `packages/tl-mcp/src/tl_mcp/punch_tools.py` (two reads, one proposal) |
| TUI | palette `punch`; `packages/tl-tui/src/tl_tui/punch_text.py`, `widgets/punch_log.py` |
| Demo | `dev/demos/P2-PUNCH.sh` (`just demo P2-PUNCH`) |
| Generator | `dev/seed/demo_project/quality.py` (`--sections quality`) |

## Related
- Access words: [access-words.md](../../reference/access-words.md) (the seven quality words).
- Offline class: `quality.PunchItem` is `draft_only` ([offline-classes.md](../../build-spec/specs/offline-classes.md)).
- Phase 3 compatibility: the table in `packages/tl-modules/quality/README.md`.
