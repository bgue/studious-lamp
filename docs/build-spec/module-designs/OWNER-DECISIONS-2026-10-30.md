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

## Answers to the spec questions (owner accepted the orchestrator's recommendations, 2026-10-30)

Roles: (1) document_controller is also superuser of correspondence and schedule; (2) a superuser grant does not
grant restricted reads (confidentiality stays by clearance, ADR-0016); (3) roles do not filter reads yet; (4) only
admins grant roles in the MVP.
Offline: (5) the class table in specs/offline-classes.md is approved (core.Record and Tag full, ReviewCycle none);
(6) controller/superuser commands are always online-only.
Web: (7) increment 1 is view and act; creating records comes in increment 2; (8) the web is off by default in
production until its security review passes; (9) current Chrome, Edge, Firefox and Safari, last two versions.
M3: (10) CWP release is a superuser act; (11) cost codes on leaf nodes only; (12) loads stay admin-only;
(13) starter commodity list (editable fixture): piping, structural steel, concrete, civil and earthworks,
electrical, instrumentation, mechanical equipment, insulation, painting.
M4: (14) the company item library is kept by a company-level materials superuser, else an admin; (15) any user
accepts a receipt, a superuser disposes of damaged or nonconforming items; (16) stock never goes negative;
(17) issue, transfer and return may be captured offline as drafts posted on sync (draft_only); (18) CatalogItem,
SerializedItem and Equipment are deferred.
Add property (same day): ad-hoc custom fields where a set allows them; unadopted sets need a superuser (admin until
the roles MVP lands); the API and MCP have parity with the terminal form.

## Phase 2 questions (owner accepted the recommendations, 2026-10-30)

P2-Q10: the orchestrator approves Phase 2 human gates (schema merges and similar) as in Phase 1 and logs each in
APPROVALS.md; spend, data migrations of existing data and copyleft licences still stop; the rules-of-credit package
goes to the owner in person (the roles part of option B is already decided above). P2-Q4: A (POLineRef by hand and by
CSV import; no outbound call). P2-Q5: B (movements are events on the stock-lot stream; lots, receipts and
requisitions are records). P2-Q9: A (keys in schema/settings/platform.yaml). Web security review at the end of web
increment 1; web off in production until it passes. `awp.release.signoff_roles` default `[superuser]`.
`RejectReceipt` is a user act; disposition of rejected items is a superuser act.
