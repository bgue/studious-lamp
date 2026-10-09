# Runbook — change a schema package and record the new effective schema

Purpose: edit a company or project package, check it, and record `Schema.EffectiveChanged` so clients refresh. Brief: §27.3, §27.5.

## When to use
- Trigger: a schema steward or project data manager edits a file in the package directory (`schema/fixtures/` in development, `TL_SCHEMA_DIR` elsewhere).
- Trigger: `tl schema validate` fails after someone else's edit.

## Before you start
- Access needed: read and write access to the package directory and the ledger file (`TL_DB`).
- Safe to run during business hours: yes. Readers pick up an edited file on their next call; a file that does not compile makes that call fail until it is fixed, so validate before saving into a live directory.

## Steps
1. Edit the package file (file name `<package>@<version>.yaml`). Constraining changes need a new version number and project pins.
2. Check it:
   ```
   uv run tl schema lint
   uv run tl schema validate
   ```
   Expected: `0 errors, N warnings`, then one `ok <scope> <hash>` line per scope. A failure prints `error: <scope>: <rule>: <message>`; the rule codes are listed in `packages/tl-schema/src/tl_schema/compile.py`.
3. Compare the hash with the one before the edit:
   ```
   uv run tl schema hash P123
   ```
   Expected: a different 64-hex hash when the effective schema changed.
4. Record the change in the ledger:
   ```
   uv run tl schema reload
   ```
   Expected: `recorded <scope> <hash>` for each scope that changed, or `unchanged`.

## Verify
- `uv run tl events tail --project P123 -n 3` shows a `Schema.EffectiveChanged` event whose payload names the new hash and the previous one.
- New writes carry the new `effective_schema_hash`: `uv run tl pset get --project P123 KEY`.
- Existing records keep the hash they were written under; their live conformance is evaluated against the new schema.

## Roll back
- Restore the previous file content (version control) and run steps 2 to 4 again. The ledger keeps both `Schema.EffectiveChanged` events; nothing is rewritten (§5.2).

## Related
- `docs/runbooks/rebuild-projections.md`, `docs/tickets/P0-I2/README-A.md`
