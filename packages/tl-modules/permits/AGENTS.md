# AGENTS.md: tl-mod-permits

Rules of the root `AGENTS.md` apply. Local rules:

- The three tables are generated; never hand-write DDL (use `ddl_for`). Events are immutable.
- Lapsed is a derived word, never a workflow state: no clock writes a state change. Only the job writes `Permit.Lapsed`.
- What a permit type demands is data in `schema/fixtures/permits/types.yaml`, read through `types_table.load_types()`;
  no type name is tested in code.
- A permit, an isolation (when `point_record_id` is set) and a gas test are hidden through their subject record
  (`for_record_id`, `point_record_id`, the gas test's permit); a reader uses the class filter (`tl_core.confidentiality`).
- Agents never approve, issue, revalidate, resume or close.
- Tests live in `tests/`; projector tests append through the ledger, never write a projection.
- Every command row is `excluded:reserved` (row `meta`); `RequestPermit` keeps its agent row `propose_permit`.
- `guards.issue_guards` is the one place the issue blockers are read: Issue, Resume and Revalidate call it, nothing copies it.
- The clock is `handlers.common.now`; no handler reads the time elsewhere. Linked isolations are read from the permit's own
  `Permit.IsolationLinked` and `Permit.IsolationUnlinked` events.
