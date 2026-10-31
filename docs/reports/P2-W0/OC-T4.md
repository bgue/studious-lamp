# Report — T08 (ticket file `T08-delivery-class.md`, heading OC-T4)

Branch: `p2/w0-t08-delivery-class`   Commit(s): see commit `T08: tag core.InboundDelivery as offline none`

## Deviations
BLOCKED on scope: `just gen` also rewrote `packages/tl-schema/src/tl_schema/generated/models.py` (+3 lines: the two new
annotations echoed into the `InboundDelivery` annotation dict). That file is not in Allowed paths and the escalation trigger
applies, so I restored it to HEAD and did not commit it. Also: the ticket's Allowed paths and heading say `OC-T4`, the dispatch
said `T08`; I wrote this report to the Allowed path `docs/reports/P2-W0/OC-T4.md`.

## Changed files
- `schema/core/integration_ops.yaml` — added `tl:offline: none` and `tl:stream_type: core.InboundDelivery` to `InboundDelivery` annotations.
- `packages/tl-schema/src/tl_schema/generated/offline_classes.py` — `"core.InboundDelivery": "none"` in `OFFLINE_STREAMS` (generated).
- `packages/tl-schema/src/tl_schema/generated/docs/offline-classes.md` — one table row (generated).
- `docs/reports/P2-W0/OC-T4.md` — this report.
- NOT committed: `packages/tl-schema/src/tl_schema/generated/models.py` (see Blocked).

## Commands and output
```
$ just gen
uv run python -m tl_schema.generate
wrote 641 files to /home/user/wt/t08/packages/tl-schema/src/tl_schema/generated
$ git status --short        (after just gen)
 M packages/tl-schema/src/tl_schema/generated/docs/offline-classes.md
 M packages/tl-schema/src/tl_schema/generated/models.py          <- outside allowed paths
 M packages/tl-schema/src/tl_schema/generated/offline_classes.py
 M schema/core/integration_ops.yaml
$ grep -n "InboundDelivery" packages/tl-schema/src/tl_schema/generated/offline_classes.py
50:    "core.InboundDelivery": "none",
$ just check     (foreground hit the 120 s tool timeout; re-run in background, ran to completion)
All checks passed!
1883 files already formatted
0 errors, 0 warnings, 0 informations
generated files are up to date (641 files)
licences ok
exit=0           (ran with models.py regenerated in the worktree)
$ uv run python -m tl_schema.generate --check     (after restoring models.py to HEAD)
differs: models.py
codegen drift: run `just gen` and commit the result
exit=1
```
No pytest was run (ticket says tests are deferred to the increment's end run).

## Tests added
none (ticket: "None").

Stream-table pin check (read only): `packages/tl-schema/tests/test_offline_classes.py` does not exist on this branch.
No test under `packages/` or `tests/` references `OFFLINE_STREAMS` or `stream_class` outside generated code and generators,
so no count or name pin breaks from this change on this branch.

## Learnings (proposed)
- An annotation edit on a class that has a generated Python model also changes `generated/models.py` (annotation dict echo).
  The ticket's "nothing else may change" for `just gen` does not hold for this kind of edit; list `models.py` in Allowed paths.
- Ticket file name (`T08-delivery-class.md`) and content (`P2-W0-OC-T4`, report `OC-T4.md`) disagree with the dispatch (`T08`, `T08.md`).
- `just check` takes longer than the 120 s foreground tool timeout; run it with `run_in_background`.

## Open questions / Blocked
BLOCKED: `models.py` must change with this ticket or the codegen drift check fails on this branch.
Commit state: the branch has the schema and offline-class changes but not `models.py`, so `just check` (drift) fails on it.
Question for the orchestrator: (a) add `packages/tl-schema/src/tl_schema/generated/models.py` to Allowed paths and I commit
the regenerated file, or (b) decide otherwise. The 3-line change, from `git diff` of the regenerated file, is:
```
@@ -12122,6 +12122,9 @@ class InboundDelivery(ConfiguredBaseModel):
                          'tl:ix_received': {'tag': 'tl:ix_received', ...},
+                         'tl:offline': {'tag': 'tl:offline', 'value': 'none'},
+                         'tl:stream_type': {'tag': 'tl:stream_type', 'value': 'core.InboundDelivery'},
                          'tl:table': {'tag': 'tl:table', 'value': 'int_delivery'}},
```
Approver line (`docs/reports/APPROVALS.md`) is the merge gate's job, not this ticket's; not written here.
