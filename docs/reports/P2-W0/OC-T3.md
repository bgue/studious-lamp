# Report — P2-W0-OC-T3 (workflow id T06)

Branch: `p2/w0-t06-scaffold-offline`   Commit(s): see final commit on branch

## Deviations
Report path: the workflow asked for `docs/reports/P2-W0/T06.md`; the ticket's Allowed paths name `docs/reports/P2-W0/OC-T3.md`. I wrote the ticket's path, since Allowed paths is the write boundary. No other deviations.

## Changed files
- `packages/tl-cli/src/tl_cli/scaffold/templates/record_type/schema.yaml.tmpl` — added the TODO comment and `tl:offline: none` as the first two lines of the class `annotations:` block.
- `packages/tl-cli/tests/expected/record_type/weld_inspection.yaml` — the same two lines (consequential pin), rest byte-identical.
- `docs/reports/P2-W0/OC-T3.md` — this report.

## Commands and output
```
$ just check
All checks passed!
1883 files already formatted
0 errors, 0 warnings, 0 informations
generated files are up to date (641 files)
licences ok
exit 0

$ T=$(mktemp -d); uv run tl new module demo --root $T && uv run tl new record-type demo.Weld --root $T
(exit 0; scaffold printed its "next:" hints)

$ grep -n -B1 "tl:offline" $T/schema/modules/demo/weld.yaml
23-      # TODO: why this class? full = edited offline and merged; draft_only = drafted offline, issued online; none = online only.
24:      tl:offline: none

$ diff <(sed 's/Weld/WeldInspection/g;s/demo/inspection/g;s/weld/weld_inspection/g' $T/schema/modules/demo/weld.yaml) packages/tl-cli/tests/expected/record_type/weld_inspection.yaml | head
(empty output, exit 0)
```
No pytest was run (deferred to the increment's end run, per ticket).

## Tests added
None (ticket: none; `test_cli_new_record_type.py` not edited).

## Learnings (proposed)
- The workflow task text named a different report path and a different trailer model than the ticket; I followed the ticket. The trailer names the running model, as the session attribution requires. A ticket-ID alias (T06 vs OC-T3) in the workflow would avoid this mismatch.
- `uv sync --all-packages` printed the normal dependency list; the `UV_NATIVE_TLS` deprecation warning appears on every `uv run`, which is noise, not a failure.

## Open questions / Blocked
none
