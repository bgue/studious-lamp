# Runbook — extension record types

Purpose: add, check, change and retire a company record type (a package of files), and repair a record whose stored body failed verification. Brief: §31, §27.3, §27.4.

## When to use
- A new record type is wanted (`co.acme.LiftPlan`): publish a package and register it.
- `tl types sync` printed `quarantined` or `conflict`.
- A running server does not list a type that was just registered.
- A read answered `body_hash_mismatch` (502) or `body_quarantined` (403).
- A type is replaced by a newer one and must take no new records.

## Before you start
- Access needed: write access to the type root (a directory of packages) and to the ledger (`TL_DB`); for bodies, the object store the servers use (`TL_OBJECT_ROOT` and `TL_OBJECT_SECRET`, or `TL_ENV=dev`).
- Safe to run during business hours: yes. `sync` only appends events; nothing is deleted. A registered package directory must stay where it is (the registry stores its `file://` location).

## A package
`<root>/<namespace>/<Name>/<version>/` with `type.yaml` (LinkML, `is_a ExtensionRecord`), optional `form.yaml`, `workflow.yaml`, `settings.yaml`, `examples/`, `README.md`, and `type.lock`. Examples: `schema/fixtures/types/co.acme/`.
- `tl:storage_mode` on the class: `managed` (every value is a pset value in the ledger) or `object-backed` (the body is an object in the store; only `tl:index` slots are pset values and queryable).
- The namespaces `core`, `tl` and `throughline` are reserved. Imports are limited to `linkml:types`, `throughline/core/extension` and files in the package.

## Steps
### Register a type
1. Check a package without registering it.
   ```
   tl types validate <root>/co.acme/LiftPlan/1.0.0
   ```
   Expected: `ok co.acme.LiftPlan@1.0.0 object-backed 4 index fields`, or one line per issue and exit 1.
2. Write the lock after any edit. It hashes every file (hidden files too; links and `__pycache__` are refused).
   ```
   tl types lock <root>/co.acme/LiftPlan/1.0.0
   ```
3. Register every package under the root. Running it again changes nothing.
   ```
   tl types sync <root>
   ```
   Expected: `registered <type_ref>` per new package, `up to date (<n> packages)` on a repeat. `--strict` exits 1 when anything is quarantined.
4. Optional: keep the root watched; a change is synced within one interval.
   ```
   tl types watch <root> --interval 2
   ```

### A package was quarantined
`tl types sync` prints `quarantined <type_ref>` and the issues (`layout`, `lock`, `lint`, `compile`, `example`, `settings`, `conflict`, `unsupported`). The other packages are unaffected.
1. `tl types quarantine ls` repeats the report; `tl types show <type_ref>` shows one version.
2. Fix the files, run `tl types lock`, then `tl types sync <root>`: the version registers.

### `conflict <type_ref> (kept <hash>)`
The files of a registered version were edited. The registration stays and the edit is refused; a version is immutable.
1. Put the files back (the version registers cleanly again), or publish the change as a new version directory (`1.1.0`) and sync.
2. Retire the old version when nothing should use it (below).

### A running server does not list the type
Servers and the TUI read the registry through the schema provider, which asks the database at most once a second. Wait a few seconds and list again (`GET /types`, `list_record_types`, `tl types ls`). If it is still missing, `tl types show <type_ref>` says whether the version is `quarantined`, or `unavailable` (its directory moved or its files no longer hash to the registered `content_hash`: put them back).

### A stored body failed verification
A read recomputes the object's hash. A mismatch (or a missing object) answers 502 `body_hash_mismatch`, records the record in `tl_body_quarantine` and later reads answer 403 `body_quarantined`. Other records are unaffected.
1. List what is damaged.
   ```
   tl types quarantine ls
   ```
   Expected: `body <record id> <type> hash mismatch` (or `object missing`).
2. Restore the object from a backup of the object store, then verify again.
   ```
   tl types quarantine recheck <record id>
   ```
   Expected: `restored <record id>`; `still failing <record id>` (exit 1) while the object is wrong.
3. Without a backup, store the intended body again (TUI `e`, or `PUT /records/<id>/body`): the same content is written back as a verified object and the quarantine clears.

### Retire a version
```
tl types deprecate <type_ref> --reason "replaced by 2.0.0"
```
Expected: `deprecated <type_ref>`. Existing records stay readable and editable; creating one answers 409 `type_not_active`.

### Use a type
- API: `GET /types`, `POST /types/<ns.Name>/records` (`body` for an object-backed type, `psets` for a managed one), `GET|PUT /records/<id>/body`.
- CLI: `tl record create --type <ns.Name> ...` for a managed type; an object-backed type needs a body, so use the API or the TUI.
- TUI: `tl tui --type <ns.Name>` (or `TL_TYPE`): the grid shows the columns of `form.yaml`, `n` opens the generated form, `e` on a record edits its body. A status-line warning says when the type has no active version.
- MCP: `list_record_types`, `get_record_type`, `get_record_body`; `create_record` proposes a managed instance. An agent cannot write bodies.

## Verify
- `tl types ls` lists the version as `active`; `tl types quarantine ls` prints `nothing quarantined`.
- `just demo P0-I8-B` runs the whole path on a scratch ledger.

## Roll back
- A registration is never deleted. Retire it (`tl types deprecate`) and register a corrected version.
- Edits to a registered version's files are refused, so there is nothing to undo; restore the files from version control.

## Related
- Plan and decisions B1 to B14: `docs/tickets/P0-I8/README-B.md`. Object store: `docs/runbooks/object-store-reconciliation.md`. Rebuilding projections keeps `tl_body_quarantine`: `docs/runbooks/rebuild-projections.md`.
- Known limits (v0): directory-backed storage and external writers, `type.lock` signing, a change-classification gate between versions, activating `workflow.yaml`, proposable bodies for agents.
