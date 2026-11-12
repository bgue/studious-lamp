# Architecture critique, 2026-11-11: API-first and agent-run

Outside reviewer (planner tier), read-only, at the owner's request ("what is missing for API-first, AI-run
software, for extensibility and for agent-driven mutation"). Evidence was read on the trunk at f5e4ca10; `path:line`
references were checked unless marked "not traced" (the orchestrator re-checked B1 and A2). Sizes are points (1 point
is about 1 agent-day). Findings already in `docs/reports/OUTSIDE-REVIEW-2026-11-09.md` are cited as "OR §n" and not
repeated.

## Verdict

1. The ledger, the proposal queue, intent on commands, the settings layers and the integration seam are a sound base
   for agent-run software; none of it needs rebuilding.
2. Today the system is API-first for people and propose-only for agents, and the agent's reach is narrow: about 15 of
   225 commands can be proposed.
3. The largest missing pieces for agents are a working idempotency key, a command catalog an agent can plan against,
   a preview that shows the effect, and a delegation design.
4. The largest missing piece for extensibility is the module boundary: a module plugs into the core by entry point,
   but every surface (API, MCP, CLI, TUI, web) imports each module by name.
5. Most agent-layer work is already planned for Phase 3 (ADR-0027). The advice is about order: three small items
   before the pilot, and the catalog and delegation design riding with the dispatcher (OR §3), not after it.

## Part A. Extensibility and adaptability (ranked)

**A1 HI. A module is a plug-in to the core but not to the surfaces.**
`packages/tl-api/src/tl_api/commands.py:101-108` imports each module's command table by name; `tl_api/app.py:325-349`
lists routers by hand; `packages/tl-mcp/src/tl_mcp/server.py:38-53`, `:140-151` register tool files by hand. Files
importing `tl_mod_*`: tl-api 24, tl-cli 55, tl-mcp 10, tl-tui 63, tl-web 16. `ModuleSpec`
(`packages/tl-core/src/tl_core/modules.py:199-238`) carries projectors, words, actions and proposable rows, but not
the command table, read routes or tools. Adding a module means editing five packages and cutting a release, and every
module multiplies the pinned lists (OR §4.1). Change: add `commands` and optional `read_router` and `tools` hooks to
`ModuleSpec`; build the API command table and MCP registration from `load_modules()`; CLI and TUI later.
4-5 points, best inside the dispatcher extraction (OR §3). Planned in part (`DEFERRED.md`, pinned lists from registries).

**A2 MD. The HTTP API has no version or compatibility rule; events do.**
`tl_api/app.py:87` (`API_VERSION = "0.1.0"`, no path or header version); `just check` runs the additive-only event
guard (`packages/tl-schema/src/tl_schema/compat.py`) but checks OpenAPI only for drift. Agents and integrations cache
request shapes; a renamed field breaks them silently. Change: reuse the `compat.py` diff on
`docs/reference/openapi.json` against a per-release baseline (removed operation, removed or newly required field,
narrowed enum fail the gate) and one page of deprecation rule. 1.5 points. Not planned.

**A3 MD. Event versions exist as a number, with no path for a non-additive change.**
`packages/tl-core/src/tl_core/ledger/types.py:18` (`schema_version: int = 1`); no version-2 event and no upcaster;
163 of 252 event types still have no payload class. The first real payload correction has no mechanism, and the
alternative is a permanent special case in every projector. Change: an ADR and one read-side hook
`(event_type, version) -> payload` in projection and rebuild, with a rebuild-equality test. 2 points. Not planned.

**A4 MD. Company-defined types and workflows are data, but data on the server's disk.**
Extension types load only from `file://` (`tl_core/extypes/loader.py:10`, `:113`) after `tl types sync`; workflow
definitions are YAML under the schema directory (`tl_core/workflow/loader.py:3`); module state tables are code
(`tl_mod_awp/actions.py:64`, `:183`). Property sets change through ledgered schema packages, which is the right
pattern. Adding a type or state needs shell access, so neither an agent nor an admin can propose it. Change: carry type
packages and workflow definitions through the schema-package mechanism (publish, pin, waive) so the proposal path
covers them; keep the file watcher for development. 3-4 points. Not planned.

**A5 MD. No report or view definitions as data.** A query language exists (`tl_core/query/`), but no saved view or
report record type. Roadmap 7a reads as code per report; agents could not add one. Change: one core record type
holding a query, columns and grouping, run by the 7a export framework for CLI, API and MCP. 2 points inside 7a.

**A6 LO. Semantic outputs and the vocabulary address.** Planned (roadmap 6b). Serve them from the API at a versioned
path, not only as repository files.

## Part B. Agent-driven mutation (ranked)

**B1 HI. The idempotency key is accepted and ignored.**
`tl_core/services/commands.py:46` ("accepted and ignored in this increment"); other uses set it to `None`
(`services/proposals.py:499`, `:573`, `:636`); no `Idempotency-Key` header in tl-api. An agent that retries after a
timeout files a second proposal or creates a second record; create commands have no `expected_version`. Change: an
operational table keyed by (actor, key), unique, storing the command hash and result; a repeat returns the stored
result, a different body under the same key is refused. In the API command route and `proposals.submit` now, in the
dispatcher later. 2 points. Not planned.

**B2 HI. Agents can propose about 15 of 225 commands.** Six core tools (`proposals/types.py:37-46`) plus nine module
rows, against 225 `/commands/*` operations; `/records/{id}/actions` offers an agent nothing (`tl_core/actions.py:84`).
Each new proposable command costs three hand-made parts. Change: ADR-0027 decision 4 (generic `propose_command`,
authorised per command type from a closed list, viewer-filtered id resolution, envelope fields forbidden) plus the
row-or-exclusion test. 3 points. Planned Phase 3; pull forward to follow the dispatcher.

**B3 HI. No command catalog an agent can plan against.** OpenAPI has body schemas and no extension keys; access word,
record types, from-states, events emitted and proposable status live in Python (`tl_api/commands.py:129-145`,
`ModuleSpec.actions`). MCP resources cover records, form schemas and relations only (`tl_mcp/resources.py:3-4`). An
agent learns a command is refused only by trying. Change: generate `commands.json` beside the event catalog (name,
module, word, record types, from-states, events, proposable, compensated-by), serve it as `GET /commands` and an MCP
resource, and let `/records/{id}/actions` answer agents. 3 points. Not planned.

**B4 MD. Preview is pass or fail, and only for proposals.** `precheck` runs the handler in a rolled-back unit of work
and discards the result (`services/proposals.py:670-704`); commands have no dry-run. Change: return the rolled-back
events, viewer-filtered, as `preview` on the proposal and as `?dry_run=true` in the dispatcher (an allocated number may
differ at accept). 2 points. Not planned.

**B5 MD. Delegation (accept by policy) has no design.** `ToolMode = Literal["propose"]` (`proposals/types.py:33`);
write mode refused (`tl_mcp/modes.py:48`); Phase 4. Without it people are the throughput limit and the pressure is to
bypass the queue; the design constrains B3 and B7. Change: an ADR now: a policy record (agent, command type, scope,
field bounds, daily cap, expiry, granted by); a policy accept is a normal `Proposal.Accepted` with a `policy` key;
start in shadow mode ("would have accepted") compared with people's decisions. ADR 1 point; build about 4.

**B6 MD. Scope and blast radius of an agent are thin.** One cap, 500 proposals per agent per UTC day
(`proposals/types.py:101`); an agent token carries no project or module scope (`tl_core/auth/types.py:101-108`);
filing does not check the agent's module role. Change: the filing check (module `user` word on the scope, ADR-0027 F1),
a per-project pending-queue cap as settings, and a per-agent stop switch that also holds its pending proposals.
2 points. Planned Phase 3; pull forward if an agent runs in the pilot.

**B7 MD. No declared way to undo.** Settings revert, links retract, records void, but no command names its
compensating command. Change: `compensated_by` in B3 and one read: events by source `mcp:<agent>` in a window with the
compensation for each. No automatic rollback. 2 points after B3.

**B8 MD. Agent work is not measured.** A rejection reason is free text (`schema/core/proposals.yaml:108`); no
acceptance-rate read. Change: an optional reason code on reject (additive) and `tl proposal stats` by agent, tool and
command (accepted, rejected by code, failed, time to decision). 1.5 points. Planned in part (Phase 3).

**B9 LO. Stale queue.** Agent proposals keep `expected_version` and fail cleanly at accept; there is no withdraw,
supersede or expiry, and a pending proposal whose target moved is not marked. About 1 point with the Phase 3 queue.

Intent lost on non-dispatcher paths and unvalidated payloads are OR §3 and OR §2. B1, B3 and B4 belong in that one
dispatcher.

## What is already strong

- Proposals: stored command, precheck by the real handler, accept runs as the person with the agent as source.
- Intent as a hashed event column, with reference checks that treat hidden and missing alike (ADR-0025).
- Settings: layered, lockable, with history, revert and risk shown to the reviewer.
- Integration seam (ADR-0017): rules in propose mode, inbound dry-run, service actors under the lowest viewer, a kill switch.
- Generated artefacts from one schema: DDL, models, event catalog with AsyncAPI, form metadata, OpenAPI, the event guard.
- Optimistic concurrency (`expected_version`, `ETag`) and closed-by-default authorisation for agent tools.

## Recommended order

1. B1 idempotency key (2). Before the pilot.
2. A2 OpenAPI compatibility gate (1.5). Before the pilot.
3. B6 filing check and queue cap (2) if an agent runs in the pilot; otherwise B8 reason codes and stats (1.5).
4. B5 delegation ADR (1), so the dispatcher is built with policy accept in mind.
5. Dispatcher (OR §3, about 17) with A1 module-supplied commands and tools (4-5) in the same pass.
6. B3 command catalog (3), then B2 generic propose tool (3).
7. B4 preview (2) and B7 compensation read (2).
8. A3 upcast hook (2) and A4 types and workflows through schema packages (3-4), with A5 inside roadmap 7a.

## Questions for the owner

1. Will any agent file proposals during the pilot? If yes, item 3 is the scope check; if no, the measurement.
2. Is accept-by-policy a goal for the first year? If so, write the delegation ADR now, shadow mode first.
3. Who is the first outside party to add a module or a type: your own agents, a customer's integrator, or nobody for a
   year? That decides whether A1 and A4 come before or after the web increment.
4. May a company admin change a module's workflow states (for example the IWP life cycle), or are they fixed by the
   product? The answer sets the scope of A4.

Not traced: CLI and TUI command paths (from OR §3), TUI handling of extension types, whether `/records` exposes the
full query language. "225" counts `/commands/<Name>` in `docs/reference/openapi.json`; "15" is 6 core tools plus 9
module rows (awp 2, correspondence 2, documents 3, materials 1, schedule 1).

## Owner answers (2026-11-12)

The owner answered yes to all four: agents file proposals in the pilot; accept-by-policy is a first-year goal; the
first outside party to extend the system is the owner's own agents; a company admin may change a module's workflow
states. In the owner's words, agents will do most extensions: full modules, and property extensions on existing
modules to make a project specific.

What this changes in the recommended order:
- Item 3 is B6 (filing check and queue cap), not B8.
- Item 4, the B5 delegation ADR, is written now, shadow mode first.
- A1 (module-supplied commands, read routes and tools) and A4 (types and workflows through schema packages) come
  before the web increment, not after it. Agent-authored modules and property sets are the main extension path.
- A4's scope includes company-editable workflow states, not only types and property sets.
- These items are planned at the next phase-plan step with a plan check (skill rule 8). In-flight increments
  (P2-I4A, P2-I5, P2-PUNCH) close first, unchanged.
