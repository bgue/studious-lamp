# P2-W0-OC-S2 — Offline classes: the capture hook, module-load validation and the node-kind start-up check

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: core, api, tui
Depends on: OC-S1 (merged: `generated/offline_classes.py`, `OFFLINE_CLASSES`, `OFFLINE_STREAMS`), RM-S2 (merged: `ModuleSpec.command_words` filled in all 7 `module.py`)
Branch: `p2/w0-oc-s2`
Approver: none (no schema, no permission path); Sec: not a review row

## Goal
The core can answer, for any record type and command, whether a node of kind `authority`, `site` or `device` may capture it
while offline, and refuses to start as a node kind whose replica layer does not exist yet. Nothing writes through the hook in
Phase 2 (it is pure and unwired); it is the contract Phase 3 plugs into, validated at module load so a module cannot
declare an inconsistent offline behaviour.

## Brief references
Interface: `docs/build-spec/specs/offline-classes.md` **§5 items 2 to 5 in full** (module-load validation, the hook with its
signatures and the rule of `capture_allowed` in order, node kind fails closed, `is_authority`) and §7 row S2; classes of every
type are §4 and are already generated. Deltas (`specs/wave0.md` wins):
1. **`offline_drafts` (all seven modules).** `ModuleSpec.offline_drafts: Mapping[str, frozenset[str]]` (record type to
   its drafting commands, default empty). Fill exactly the §4 table, nothing else:
   - `documents`: `documents.Document` {RegisterDocument, UpdateDocument}; `documents.Revision` {CreateRevision, VoidRevision};
     `documents.Rendition` {AttachRendition}; `documents.Transmittal` {CreateTransmittal, VoidTransmittal}
   - `correspondence`: `correspondence.Correspondence` {DraftCorrespondence, UpdateCorrespondence, VoidDraft};
     `correspondence.TechnicalItem` {RaiseTechnical, UpdateTechnical}
   - other modules: empty. All twelve names are in `command_words` with the word `user` (checked at `9563763`); place the
     line **after** the `command_words` line RM-S2 wrote, one line per module, no other edit to `module.py`. If a name has
     stopped being `user`, do not list it; say so under *Open questions*.
2. **Load checks** (`ModuleLoadError`, one message naming the module and the item): every record type of every module is a key
   of `OFFLINE_CLASSES` (undeclared type); an `offline_drafts` key is a type the module owns whose class is `draft_only`
   (a drafting entry on a `full` or `none` type); every listed command is in `command_words` with the word `user` (a
   `controller`, `admin` or `company` command listed). Three errors, each with a message test case in the acceptance script.
3. **Extension types.** `type.yaml` gets an optional class-level key `offline` (`full | draft_only | none`, default `none`; any
   other value is a compile error with the usual `TypeIssue` style) read in `tl_core/extypes/` where the type compiles;
   `offline_class()` returns it for a registered extension type. `offline_class` should stay free of IO: use what the attached
   provider already holds. If that is impossible, take an optional keyword `conn` and say so as a deviation; do not add a table.
4. **`OnlineOnlyError`** (409 `online_only`) lives in `offline.py` as a `ServiceError`; add its row to `tl_api/errors.py`.
   `NodeKindNotBuiltError` (message: `offline replicas arrive in Phase 3`) likewise. `node_kind()` reads `TL_NODE_KIND`
   (unset or empty = `authority`; any value outside the three is a `ValueError` naming the variable).
5. **Start-up check.** One function `require_node_built()` in `offline.py` (raises `NodeKindNotBuiltError` unless
   `node_kind() == "authority"`), called at the top of `tl_api.main.main` and `tl_tui.main.run`, before any ledger is opened.
   Both mains turn it into `error: ...` on stderr and exit 2, like their other start-up errors. `tl serve` and `tl tui` wrap those
   mains, so they need no change.
6. **`capture_allowed` and the generic commands** (spec item 3 last sentence, **proposed**): `AddLink`, `AttachFile`,
   `SetPsetValues`, `TransitionWorkflow` follow the record's type class: `full` allowed, `draft_only` refused as `not_drafting`
   (they are not in `offline_drafts`), `none` refused. They are *not* `central_act`. Implement the rule exactly in the order of §5
   item 3; the acceptance script prints the full decision table.
7. **`is_authority(scope)`** returns `node_kind() == "authority"`; no scope data is read.

## Context (<= 10 files)
- `docs/build-spec/specs/offline-classes.md` §4, §5, §7; `docs/reports/P2-W0/OC-S1.md`, `RM-S2.md`
- `packages/tl-schema/src/tl_schema/generated/offline_classes.py`; `packages/tl-core/src/tl_core/modules.py` (`ModuleSpec`, `load_modules`)
- `packages/tl-core/src/tl_core/extypes/{model.py,compile.py,validate.py,provider.py}`; `packages/tl-api/src/tl_api/{main.py,errors.py}`; `packages/tl-tui/src/tl_tui/main.py`
may explore: `packages/tl-core/src/tl_core/auth/module_roles.py` (`command_index`), one `module.py`

## Allowed paths
- `packages/tl-core/src/tl_core/offline.py` (create); `packages/tl-core/src/tl_core/modules.py` (`offline_drafts` field and the three load checks only); `packages/tl-core/src/tl_core/extypes/**` (the `offline` key only)
- the `offline_drafts` line of `packages/tl-modules/{documents,correspondence,cost,engineering,legacy,schedule,schemareg}/src/*/module.py` (one line each; documents and correspondence non-empty)
- `packages/tl-api/src/tl_api/main.py` (call `require_node_built()`), `packages/tl-api/src/tl_api/errors.py` (the two rows), `packages/tl-tui/src/tl_tui/main.py` (call it)
- `dev/accept/P2-W0/OC-S2.py` (create), `docs/reports/P2-W0/OC-S2.md` (create)
Not allowed: `schema/**`, `tl_schema/**` (generated data is read only), `tl_core/auth/**`, `tl_api/commands.py`, `tl_api/routes/**`, `tl_cli/**` (RM-S3 and RM-S4 run in parallel and own them), `docs/reference/openapi.json` unless `just check` says it drifted (then `python -m tl_api.openapi`, one line).

## Acceptance (run these, once; no pytest, no `just gate`)
```
just check
uv run python dev/accept/P2-W0/OC-S2.py
TL_NODE_KIND=device uv run tl serve     # exit 2, stderr: error: offline replicas arrive in Phase 3 (no ledger needed to reach it)
TL_NODE_KIND=site uv run tl tui         # same
```
`dev/accept/P2-W0/OC-S2.py` (no database for the pure parts, exit 0, one `PASS <check>` per check, decision table printed): every
branch of `capture_allowed` in the order of §5 item 3, for all three node kinds, over every record type of `OFFLINE_CLASSES` x
every command of its module (`command_words`) plus the four generic commands, printing the count of allowed and refused per
reason and 6 sample rows; authority allows everything including an unknown type; unknown type refused on site; `controller`
refused before the class is read (a `full` type with a controller command); the `offline_drafts` of §4 equal the module values;
`require_capture_allowed` raises `OnlineOnlyError` (and its API row is 409 `online_only`); the three module-load errors,
each raised by a stand-in `ModuleSpec` passed to the load check; an extension type with `offline: draft_only` in a temp
`type.yaml` compiles and `offline_class` returns it, a bad value is a compile issue, a missing key is `none`; `node_kind()`
default, `device`, and a bad value; `stream_class("core.ActivityPost") == "full"` and an unknown stream is `none`.

## Tests for the end run (TA/TB write them; this piece writes none)
`packages/tl-core/tests/test_offline_capture.py` (every branch; authority always allowed), `tests/services/test_modules_offline.py`
(the three load errors), `tests/extypes/test_extype_offline.py` (existing dir; the spec's `packages/tl-core/tests/extypes/` does not exist). Report guard sites (file:line) for TB's mutants:
`central_act` checked before the class; `authority` short-circuit; unknown type refused; `draft_only` without listing refused.

## Report requirements
Standard piece report (<= 60 lines): deviations first; changed files; the decision-table summary line; how the extension class is
read (and whether `conn` was needed); acceptance output (<= 5 lines per command).

## Escalation triggers
- *Blocked* if: a module record type has no class in `OFFLINE_CLASSES`; a listed drafting command cannot be a `user` word; the
  extension compile path cannot carry the key without a schema or ledger change.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
