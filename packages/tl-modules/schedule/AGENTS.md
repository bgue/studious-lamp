# AGENTS.md — tl-mod-schedule

Read the root `AGENTS.md` first. These rules add to it.

- The tables `cur_schedule_*` are generated from `schema/modules/schedule/` and written only by the projectors. The `sched_*` tables are **operational**: written by the build's settle (`typed_store`) and by `reconcile`, never by an event projection, never cleared by a rebuild, never read by the archive or the webhooks. A snapshot's typed rows are written once and never updated.
- Create records through `create_module_record` (ADR-0010). Publish, define, void, open, start and link are module commands on the ADR-0010 seam; never `CreateRecord`, never a generic `TransitionWorkflow` on a snapshot (the guards in `guards.py` refuse them). `by_module=True` is for this module's own code paths only.
- Access is at the entry point, not in the handler: `DefineSchedule`, `PublishScheduleSnapshot` and `VoidScheduleSnapshot` are `controller`; open, start and link are `user`; `tl xer worker` and `reconcile` are admin. A new command goes into `API_COMMANDS` and the walk test. Agents propose only.
- The build reads an untrusted file only through `tl_xer.run.read_xer_file` (the envelope). Settle writes in one transaction and first checks the claim is still this worker's. Keep `BUILD_LEASE_S` above the envelope clock plus the measured settle time.
- **Flagging is a job, not part of publish.** Publish appends its events and queues `schedule.flag_orphans`; `orphans.run_once` does at most `FLAG_BATCH` operations and is derived from state, so a lost or repeated run changes nothing wrong. A flag it writes has actor and source `svc:schedule`, and it restores only links whose latest `Link.Flagged` came from that source. A person's flag is never restored. Bound anything new that scales with links or references.
- Caps (`MAX_LINKS_PER_ACTIVITY`, `MAX_REFS_PER_SCHEDULE`) and the data-date allowance exist because anyone signed in can link or upload; each has a test that fails when it is removed.
- Dates are compared as dates (`common.stamp`), never as text. A number in a pin or an as-of date is ASCII digits and at most 9 of them.
- Every read takes the project scope and finds a schedule only within it; a code in another project finds nothing.
- Text of a command goes through `tl_core.text.clean_text`. Messages are fixed text and do not echo a file's content.
- A projector test replays the events and compares the rows; tests use the shared `world` fixture so they run on both databases. Postgres is the slow one: test the settle with the real `typed_store`, not a stub.
- Never name a module `types.py` (L-P0-I5-B1).
