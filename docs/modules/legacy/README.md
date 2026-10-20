# Module spec: legacy (the legacy loaders, brief 29.6)

Status: accepted (built in P1-I8). Brief sections: §29.6 (loading from the incumbent systems: land, profile, map, load, reconcile), §9 M1 and M2 (document register and tag list imports), §28.2 (the lake bronze layer). Decisions: FANOUT `docs/tickets/P1-I8/FANOUT.md` D6 to D9, ADR-0010 (module storage), ADR-0014 (the file reader runs in a limited child process).

## Purpose
A company that moves to the platform has its tag list, its document register and its line list in spreadsheets and in the exports of other systems. A *load run* takes one such file through fixed stages, keeps what each stage found, and can be taken back. The loaders themselves are small (a name, a mapping template and the kind of record they write); the stages are this module's.

## Record type
| Type | Key | Table | Workflow |
|---|---|---|---|
| `legacy.LoadRun` | `<system>/<table>#<n>` (`dms/register#1`) | `cur_legacy_load_run` | `legacy.load-run`: Opened, Extracted, Profiled, Planned, Loaded, Reconciled, Compensated, Void |

A run is the job record of a load, like a schedule snapshot. The record takes no generic command (no link, no attachment). Its files are in four slots written only by the module (`source`, `extracted`, `profile`, `report`).

## Events
| Event type | Meaning |
|---|---|
| `LoadRun.Opened` | System, table, run number, loader, the file's name, size and SHA-256 |
| `LoadRun.Extracted` | Row and column counts; the file with the rows and its SHA-256 |
| `LoadRun.Profiled` | The file with the profile and its SHA-256 |
| `LoadRun.Bronzed` | Rows copied to the lake table `legacy_<system>_<table>` |
| `LoadRun.Planned` | The mapping's name and SHA-256, and the counts new, existing, invalid |
| `LoadRun.Loaded` | The ids of the records created (at most 20 000), the counts skipped, the correlation id of the batch |
| `LoadRun.Reconciled` | The report file, its SHA-256 and the mismatch count |
| `LoadRun.Compensated` | Records reversed and the correlation id of the compensation |
| `LoadRun.Failed` | Stage, a fixed code and fixed text. The run stays where it was |
| `LoadRun.Voided` | A run abandoned before it loaded anything |

No payload holds a row, a cell or a path of the file.

## The stages
Every stage is the administrator's (D9). `tl load` runs them; `tl_mod_legacy.service.LoadService` is the one place that does.

1. **open** keeps the file (CSV or XLSX, at most 50 MiB) in the slot `source` and records the run. The loader decides which kinds it reads.
2. **extract** reads the file in the derivation envelope (`tl_core.derivation.isolated.run_isolated`: a child process with limits on memory, CPU and wall clock, the `tabular` extractor, at most 20 000 rows, 200 columns, 10 000 characters a cell). The grid is kept as JSON in the slot `extracted`. A refusal appends `LoadRun.Failed` and leaves the run Opened.
3. **profile** asks DuckDB, per column: non-empty and distinct cells, repeats, lengths, the one shape every cell has (integer, decimal, date, code, word), key candidates and the five most frequent values (cut to 60 characters). Column names never reach SQL (`c0`, `c1`, ...). The profile is kept in the slot `profile`.
4. **bronze** (optional, any time after extract) copies the rows, as text with `_run_id` and `_row_no`, to the lake table `legacy_<system>_<table>`. It is a copy outside the ledger: a `tl lake rebuild` drops it and this stage writes it again. Every reader of the lake can read it, so this is a stage of its own.
5. **plan** reads the grid with the loader's mapping template (the template of `tl tag import` or `tl doc import`; the delimiter is made a comma because the grid is handed over as CSV), plans against the project and records the counts. It may be repeated.
6. **load** plans again inside its transaction and refuses when the counts are not the ones the run recorded (`--expect-new` adds the count the caller saw). It writes the new rows with the module's own commands (`RecordTag` through the tag import, `RegisterDocument`), source `legacy:<system>`, one correlation id `load:<ulid>`, and writes the cells of every row, mapped or not, into the *source layer* `src.legacy-<system>.<table>` of the record. A row the project holds is left alone (create-only). Rows that cannot be loaded are skipped and counted. The ids created are recorded in the event.
7. **reconcile** compares the project with the file: per valid row, is the record there, and does it hold the file's values (field names, line numbers; no cell). The report is kept in the slot `report`. It may be repeated.
8. **compensate** ends the records the run created, all or nothing, by the ids the run recorded, never by correlation id (a client could set one): tags through the `delete` transition, documents through `VoidDocument`. It refuses when any record was changed after the load, has a revision, or is in a state that cannot be ended.
9. **void** abandons a run that has loaded nothing.

## The source layer
`src.legacy-<system>.<table>` is written only by this module (`SetPsetValues` refuses the root `src`). A column name is folded to `[a-z][a-z0-9_]{0,62}`, a value is text of at most 500 characters without control characters, and a record takes at most 60 columns (the first 60 in file order). A record type that does not allow `SetPsetValues` is skipped and counted. The layer keeps what the file said, whatever the mapping did with it.

## Loaders
A loader is a `tl_mod_legacy.model.LoaderDef` returned by a function named in the entry-point group `throughline.loaders` of its package; the entry-point name is the loader's name. It carries the system and table names (`[a-z][a-z0-9_]{0,30}`), the target (`tags` or `documents`), the mapping template text, the file kinds and, for documents, the class they are registered with. Loaders are code in the install, not data a client can send.

## Confidentiality
- A run has a class, `internal` (also when null) or `restricted`, set when it is opened: the administrator's `--confidentiality`, else the loader's, else `internal`. The module declares it to the platform (`ConfidentialSource`, ADR-0016), so the run's record, its four files, its events and the ids in them are hidden from every reader who may not read that class, and so is the run in the lake silver.
- The documents a run registers get the run's class; registering a restricted document needs a viewer who may read it (an administrator).
- The profile and the report quote the file (the profile shows the five most frequent values of a column). Every `tl load` command is the administrator's, and no API route or MCP tool exposes a run.
- Bronze copies the rows to the lake, which every user can query. A restricted run is never copied. For an internal run the administrator must say that the file may hold rows of records that are not open to every reader (`--include-confidential`); the choice is recorded in `LoadRun.Bronzed`.

## Not built, by plan
- Registering the reconciliation report as a controlled document (it needs a document type for reports in the company's standards); the report is a file of the run: `tl load show RUN --report`.
- A scheduled or recurring load; a load that changes records the project already holds.
- An API route, an MCP tool or a screen for runs.
