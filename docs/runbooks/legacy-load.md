# Runbook — load a legacy export into a project

Purpose: bring the tag list, document register or another export of an incumbent system into a project, check it, and take it back if it was wrong. Brief: §29.6.

## When to use
- Trigger: a project starts from a spreadsheet or an export, or a re-export of the same list has new rows.

## Before you start
- Access needed: the administrator role (every `tl load` command), the ledger (`TL_DB`) and the object store (`TL_OBJECT_ROOT`) of the environment.
- The company's standards are loaded (tag classes, document type codes and the document number pattern); a row that names a class or a type the standards do not have is counted invalid.
- Safe to run during business hours: yes for open, extract, profile and plan; load writes records in one transaction (a few thousand rows take seconds) and compensate takes them back in one.
- A load writes new rows only. A row whose key the project holds is left alone; to change records, use the import commands (`tl tag import`, `tl doc import`).

## Steps
1. See which loaders are installed.
   ```
   tl load loaders
   ```
   Expected: one line per loader: name, system/table, target, file kinds.
2. Keep the file and record the run.
   ```
   tl load open export.xlsx --project P123 --loader <name>
   ```
   Expected: `opened <system>/<table>#<n> <id>`.
3. Read it, profile it, and look at the profile.
   ```
   tl load extract <run> --project P123
   tl load profile <run> --project P123
   tl load profile <run> --project P123 --show
   ```
   Expected: the row and column counts, then one line per column. A file the reader refuses (too large, too many columns, not a workbook) gives `error:` and the run stays Opened; open a new run with a fixed file and void this one.
4. Plan and read the counts.
   ```
   tl load plan <run> --project P123
   ```
   Expected: `planned <run> new N existing M invalid K` and the first invalid lines with fixed reasons (no cell). Fix the file or the mapping and open a new run when K is not acceptable; invalid rows are skipped by the load.
5. Load, naming the new rows you saw.
   ```
   tl load load <run> --project P123 --expect-new N
   ```
   Expected: `loaded <run> created N ... correlation load:<id>`. `error: the project changed since the plan` means someone loaded or imported in between: plan again.
6. Reconcile.
   ```
   tl load reconcile <run> --project P123
   tl load show <run> --project P123 --report
   ```
   Expected: `mismatches 0`. A mismatch names a line and a field.
7. Optional: copy the rows to the lake for analysis. Every reader of the lake can read the copy, so only for a file with nothing restricted.
   ```
   tl load bronze <run> --project P123
   ```

## Verify
- `tl load show <run> --project P123` is Reconciled with `mismatches 0`.
- `tl tag ls --project P123` or `tl doc ls --project P123` lists the new records; their `src.legacy-<system>.<table>` property set holds every column of the file.

## Roll back
- Before the load: `tl load void <run> --project P123 --reason "..."`.
- After the load: `tl load compensate <run> --project P123 --reason "..."` ends exactly the records the run created (tags are deleted, documents voided). It refuses, naming each record, when one was changed after the load, is no longer in a state that can be ended, or a document has a revision; nothing is changed then. Settle those records by hand and run it again.
- The lake copy is not in the ledger: `tl lake rebuild` drops it, and `tl load bronze` writes it again.

## Related
- `docs/modules/legacy/README.md`, ADR-0014 (the resource envelope), `docs/runbooks/lake-sync.md`, `docs/runbooks/engineering-standards-and-tags.md`.
