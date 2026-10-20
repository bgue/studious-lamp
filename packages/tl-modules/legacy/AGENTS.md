# AGENTS.md — tl-mod-legacy

Read the root `AGENTS.md` first. These rules add to it.

- A file is untrusted. It is read only by `extract.read_grid` (a child process with limits); nothing here opens a workbook or a CSV in the calling process. Every name and value from a file is bounded before it is used as a column name, a property name or a lake table name; a name never reaches SQL as an identifier (`c0`, `c1` in the profile; folded names in bronze).
- An event, an error message and a report carry counts, hashes, ids, line numbers and field names. Never a cell, a path of the file, or a value from it.
- The load is create-only and writes with the module's own commands under the source `legacy:<system>` and one `load:<ulid>` correlation id. Compensation reverses the ids the run recorded in `LoadRun.Loaded`, never "the events with this correlation id".
- `tl_core.services.reserved` reserves the source prefix `legacy:` and the correlation prefix `load:` so a client cannot pose as a load. Do not widen what a client may set.
- Every stage moves the run with `common.transition` (`by_module=True`); the run takes no generic command. A stage that fails after the file was read appends `LoadRun.Failed` and leaves the state.
- Files of a run are written by the module only (`store.RunFiles`, `by_module=True`, actor `svc:legacy`, which is the only reader of a file that is still in quarantine).
- Bronze is a copy every lake reader can read and is a stage of its own; do not call it from another stage.
- Every `tl load` command is the administrator's. No API route or MCP tool exposes a run (the profile and the report quote the file).
- A loader is a `LoaderDef` from an entry point of `throughline.loaders`; its mapping is a template of the existing imports. A new loader brings a sample file with synthetic data and a test that loads it on both databases.
- Tests use `LegacyWorld` and run on both databases. Synthetic data only.
