# Runbook — engineering standards, tag classes and tag lists

Purpose: load the company standards, change a tag class, import a legacy tag list and read the reports. Brief: §6.4, §9 M2, §24.6.

## When to use
- A new company edition of the standards, or a first load on a new ledger.
- A tag class gains or loses a required property set, or a class is retired.
- A project brings a tag list from another system.
- A report says tags are non-conformant, or a tag number was refused.

## Before you start
- Access needed: an admin session (`tl login <name>`) for everything that changes the registry or applies an import. A signed-in person may create tags, add a project code value to an extensible list, preview an import and read.
- Safe to run during business hours: yes. A load or an apply is one unit of work: it happens completely or not at all.
- Commands take the ledger from `--db` or `TL_DB` (a SQLite file or a `postgresql://` URL).

## Steps
### Load the standards
1. Preview: `uv run tl standards load schema/fixtures/standards/co.acme.standards@1.0.0.yaml --dry-run`. Expected: `plan <edition>` and one `create=N skip=M` line per kind.
2. Load: the same command without `--dry-run`. Expected: `loaded <edition>`. Run it again to see `create=0` everywhere.
3. A tag class that names a pset the company schema lacks stops the load with `cannot be loaded` and writes nothing: add the pset to the schema package first (`docs/runbooks/schema-package-change.md`).

### Change a tag class
1. `uv run tl standards class show ControlValve` to see its psets, then `uv run tl standards class revise ControlValve --pset valve_data --pset safety_data --reason "..."` (a list option replaces the whole list).
2. This is a constraining change (§27.5): tags of the class that lack the new pset become non-conformant on their next evaluation; nothing is rewritten. See what is lacking with `uv run tl tag report missing --project P123`.
3. Retire with `tl standards class close <code> --reason "..." [--superseded-by <code>]`. Tags already of that class keep it.

### Import a tag list
1. Write or pick a mapping template (`dev/seed/templates/tag-list-instrument-index.yaml`).
2. Preview: `uv run tl tag import list.csv --mapping template.yaml --project P123`. Read the counts and the `!` lines: every invalid row says why.
3. Fix the file, or apply with `--skip-invalid` to leave those rows out: `uv run tl tag import list.csv --mapping template.yaml --project P123 --apply --job <name>` (admin).
4. A number held by a superseded tag cannot be reused: renumber the row in the file.

### Read the reports
`uv run tl tag report summary|missing|violations --project P123` (`--json` for a list of objects). The TUI shows the same tags with `F8`.

## Verify
- `uv run tl standards ls` and `tl tag ls --project P123` show what you expect; `tl tag show <number> --project P123` shows the segments, the class and what is lacking.
- Every event of an import has source `import:<job>` and one correlation id.

## Roll back
- Nothing is edited in place. Close an entry (`tl standards close`, `close-value`, `class close`) or replace a tag (`tl tag rename|split|merge`). A wrong import is corrected by a new import or by those commands; the history stays.

## Related
- ADR-0010 (module record storage, with the generic-command addendum), `docs/modules/engineering/`.
- `docs/runbooks/schema-package-change.md`, `docs/runbooks/workflow-link-numbering-config.md`, `docs/runbooks/accounts-and-access.md`.
