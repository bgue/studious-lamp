# Owner decisions on the module designs (2026-10-30)

Answers to the three open questions of `README.md`, given by the owner in conversation. Spec writers apply them.

1. **Roles: MVP per module.** Each module has three roles: `viewer` (read), `user` (create and work records),
   `superuser` (approve, sign off, configure, void). Roles are granted per project and per module. Admin keeps the
   platform-wide powers it has today; the existing document-controller role maps to `superuser` of documents. The
   richer project-role model (planner, cost controller, QA/QC inspector, external party) is deferred and must stay
   possible: specs name the action's access word, and the role-to-word table is data, not code.
2. **Offline: a per-type table.** Every record type declares `offline: full | draft_only | none` (full: create and
   edit offline, merged on sync; draft only: drafts offline, issue/number/sign centrally; none: online only). A site
   server may be the authority for its own project scope when no central node exists ("authority per scope"). Specs
   state the offline class of each record type they add and why.
3. **Web client: starts in Phase 2.** The first web increment covers the everyday screens (RFI, correspondence and
   document logs, the record screen with full PDF preview), reusing the log standard and server actions. New modules
   from then on ship terminal and web together.
4. **Phase 3 re-sequenced.** Inspections, deficiencies and calibration come before the shared Issue engine, which
   then generalises them.
