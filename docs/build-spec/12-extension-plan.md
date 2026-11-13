# Build spec 12 — Extension plan: agent-run mutation and agent-built extensions

Status: DRAFT v0.2, 2026-11-13 (plan check answered). Plan only. Source: `docs/reports/ARCH-CRITIQUE-2026-11-11.md` (A1-A5, B1-B8, owner answers 2026-11-12). Format follows `08-phase2-plan.md`
Increment 6.
Increments are named `P2-X1` to `P2-X4`, `P2-X5a`, `P2-X5b`; ticket IDs `P2-X<n>-T<nn>`, pieces `S<n>`.

Tier letters: **H** ticket (`lite`/`full` review), **B** builder piece (`full`), **O** orchestrator. Sec `Y`: in the wave's security scope.

## 0. Scope, order and rules
Owner decisions (2026-11-12, all yes): agents file proposals in the pilot; accept-by-policy is a first-year goal; the owner's own agents extend the system first (full modules, and property sets on
existing modules); a company admin may change a module's workflow states. Order, kept as the owner's unless a seam forces a change. The web increment starts after X4 C4 and X5a C4 (owner answers
2026-11-12, ARCH-CRITIQUE); `roadmap-2026-11-07.md` order lines 6a, 7 and 8 say so:

| Inc | Critique items | One line | Needs before start |
|---|---|---|---|
| P2-X1 | B1, A2 | Idempotency key that works; OpenAPI compatibility gate | P2-I5 and P2-PUNCH merged to trunk |
| P2-X2 | B6 | Agent filing check, per-project queue cap, per-agent stop switch | X1 merged (both touch `proposals.submit`) |
| P2-X3 | B5 | Delegation ADR, shadow mode first (ADR only) | none; X4 S1 needs the ADR merged |
| P2-X4 | A1 | Modules supply their own commands, read routes and agent tools (API, CLI, MCP; TUI note) | X3 ADR merged; I6 T03 merged (registry audit) |
| P2-X5a | A4 | Types and property sets through schema packages | X2 C2 (S5 filing check) |
| P2-X5b | A4 | Company-editable workflow states (company layer only) | X5a C4, X4 C1, owner signs the lock list |

Rules for every increment:
- Additive only. No existing event changes. No data migration. New event types and optional fields only.
- Hidden looks exactly like missing (phrase 140): status, text and counts match, for every new read route, tool, refusal and count. The visibility filter runs before LIMIT and before counting (141). A
new route or tool carrying record text gets a walking test as five kinds of reader (`AGENTS.md`).
- Authorization stays closed for agents: a new route or tool is denied until someone allows it (ADR-0009).
- Agent-written extensions are code in the repository (a module) or data through a ledgered package. Nothing loads code from the ledger or from an upload. A module ships through a ticket, a review and
a release; a data extension goes through draft, approve by a different admin, publish, adopt (`docs/runbooks/schema-package-change.md`).
- Every schema, setting and core-interface change below needs an APPROVALS line before its merge (listed in §5).
- Anything over about 10 tickets, and every core-interface ADR, gets a planner-tier check first (skill rule 8).

## 1. Increments

### P2-X1 — Idempotency key and OpenAPI compatibility gate

**Goal:** a retry after a timeout never files a second proposal or creates a second record; a renamed or removed API field fails `just check` before release.
**Seams (sized):** `Command.idempotency_key` is accepted and ignored (`tl_core/services/commands.py:46`); proposals set it to `None` (`services/proposals.py:499,573,636`); no header in `tl-api`.
`compat.py` already diffs events; OpenAPI is only drift-checked.
**Demo** (`just demo P2-X1`, both adapters):
1. Same actor sends one command twice with one `Idempotency-Key`: one event set, the second answer equals the first.
2. The same key with a different body is refused with a fixed message; nothing is written. Two concurrent sends of one key write once; the other answers as a replay or a fixed in-progress refusal,
never a 500.
3. An agent files a proposal twice with one key (API and MCP): one proposal row.
4. Another actor with the same key value does not see or collide with the first actor's entry.
5. After the actor's clearance drops, a replay returns ids that the viewer filter hides as absent (140).
6. A removed response field in a scratch `openapi.json` fails `just check`; an added optional field passes.
**Builder pieces (1):** S1 operational table `idempotency_key` (actor, key, command name, body hash, result ids, created) and setting `idempotency.retention_days` (default 7). The helper
`tl_core.services.idempotency` owns the replay and mismatch rule; there is no command service, so S1 names its call sites: `tl_api/commands.py:359` and `:503`, `proposals.submit`
(`proposals.py:499,573,636`); embedded and CLI paths pass `None` as today. One transaction with the write. A concurrent insert of the same (actor, key) answers as a replay or the fixed in-progress
refusal. The purge job (old S2) is deferred (DEFERRED.md); the setting stays, rows are kept until it ships.
**Checkpoints:** C1 = S1 merged; C2 = route, client and tool tickets merged; C3 = gate and docs merged; C4 = demo green, SR-X1 closed.
**Design notes:** the key is per actor, ASCII, at most 128 characters, never logged or put in an error text. Store ids and the command hash, not response text; a replay re-reads through the viewer
filter. The dispatcher (later) moves the check into one place; X1 puts it in one helper so that move is a call-site change. A retry after expiry files anew.

| ID | Title | Tier | Depends | Sec |
|---|---|---|---|---|
| S1 | Idempotency store, helper, replay and mismatch rule at the named call sites; retention setting (schema, settings: gated) | B | — | Y |
| T01 | `Idempotency-Key` header on command routes and the proposal route (validate, pass through) | H full | S1 | Y |
| T02 | `ApiClient` and remote TUI client send a key on retry; helper with a provided test | H full | T01 | — |
| T03 | MCP write and proposal tools take an optional `idempotency_key` | H full | S1 | Y |
| T04 | OpenAPI diff function in `compat.py`: removed operation, removed or newly required field, narrowed enum | H full | — | — |
| T05 | `docs/reference/openapi.baseline.json`, `just openapi-baseline`, step in `just check` | H full | T04 | — |
| T06 | `docs/reference/api-compat.md`: the deprecation rule on one page | H lite | T04 | — |
| T07 | Walking tests: replay as five kinds of reader; cross-actor key isolation | H full | S1, T01, T03 | Y |
| T08 | Demo driver `dev/demos/P2-X1.sh` from the clause list | H full | T02, T03, T05 | — |
| T09 | Runbook and `AGENTS.md` rows (`docs/runbooks/api-retries.md`) | H lite | T08 | — |

### P2-X2 — Agent scope: filing check, queue cap, stop switch

**Goal:** an agent in the pilot can file only where it may propose, cannot flood a project queue, and an admin can stop one agent and hold what it filed.
**Seams (sized):** one cap, 500 per agent per UTC day (`proposals/types.py:101`); agent tokens carry no scope (`tl_core/auth/types.py:101-108`); ADR-0027 F1 decided the filing check is the module's
`user` word on the scope.
**Demo** (`just demo P2-X2`, both adapters):
1. An agent without the module `user` word on the scope files a proposal: refused, the same as a scope that does not exist.
2. With the word it files; the person who accepts still needs the command's own access word. A pilot agent that lacks the grant is refused until an admin runs the module-role grant
(`GrantModuleRole`); no data migration.
3. A project pending-queue cap (setting) is reached: the next filing is refused with a fixed text that shows no counts.
4. An admin runs `tl agent stop`: new filings are refused; pending ones show as held; accept is refused while stopped.
5. `tl agent resume` lifts both; the ledger shows `Agent.Stopped` then `Agent.Resumed`, nothing rewritten.
6. The held count and the stopped list, read as five kinds of reader, name no hidden record and count none (140, 141).
**Builder pieces (3):** S1 filing check in `proposals.submit` (word on scope, hidden equals missing); S2 per-project queue cap (setting, counted before the cap text, fixed message); S3 stop switch
(two additive event types, a projection, `StopAgent` and `ResumeAgent` as `admin` commands, the check at filing and at accept). Agent tokens carry no scope (`auth/types.py:101-108`), so S1 starts
refusing agents without a module `user` grant: the I6 scenario agents are granted before I6 T04, and T06 holds the grant checklist.
**Checkpoints:** C1 = S1 merged; C2 = S2, S3 merged; C3 = surfaces and tests merged; C4 = demo green, SR-X2 closed.

| ID | Title | Tier | Depends | Sec |
|---|---|---|---|---|
| S1 | Filing check: module `user` word on the scope; uniform refusal | B | X1 C1 | Y |
| S2 | Project pending-queue cap and fixed refusal text (gated setting) | B | S1 | Y |
| S3 | Agent stop switch: events, projection, admin commands, filing and accept checks (schema: gated) | B | — | Y |
| T01 | API routes and `ApiClient` methods for stop, resume, list stopped | H full | S3 | Y |
| T02 | `tl agent stop`, `resume`, `stopped` (CLI `require_admin`) | H full | S3 | Y |
| T03 | Accounts screen shows an agent's stopped flag and held count; the count is filtered before counting (141) | H full | T01 | Y |
| T04 | Walking tests: refusals look like missing; cap text carries no counts; five-reader walk of the held count and the stopped list (an admin is not clearance, ADR-0016); `AGENT_MAY_NOT` rows | H full | S1, S2, S3, T03 | Y |
| T05 | Demo driver `dev/demos/P2-X2.sh` | H full | T02, T04 | — |
| T06 | Runbook `accounts-and-access.md` with the agent grant checklist (existing `GrantModuleRole`); settings reference | H lite | T05 | — |

### P2-X3 — Delegation ADR (accept by policy), shadow mode first

**Goal:** an accepted core-interface ADR, so the dispatcher, the command catalog and A1 are built with policy accept in mind. ADR only; the build (about 4 points) is listed under later work.
**Content the ADR must settle (B5):** a policy record (agent, command type, scope, field bounds, daily cap, expiry, granted by); a policy accept is a normal `Proposal.Accepted` with an optional
`policy` key (additive); shadow mode: evaluate at filing, record "would have accepted", compare with people's decisions, never accept; who may grant (admin plus one other admin); the stop switch of X2
overrides every policy; viewer-filtered scope resolution; policy never covers commands whose word is `admin`, money, access or schema publication (a closed exclusion list).
**Demo (document check, no code):** 1. ADR merged with an APPROVALS line. 2. A trace table in the ADR maps each clause to X2's stop switch, A1's `meta` field and the later catalog (B3) and
compensation read (B7). 3. Plan check returned and answered.
**Checkpoints:** C1 = draft ADR; C2 = plan check answered; C3 = ADR merged; C4 = X4 plan re-read against it.

| ID | Title | Tier | Depends | Sec |
|---|---|---|---|---|
| O1 | ADR (next free number) delegation by policy, shadow mode first; cites the X2 S3 piece spec (stop switch) | O | — | — |
| O2 | Planner-tier check of the ADR (skill rule 8), findings under its `## Plan check` | O | O1 | — |
| T01 | Index the ADR in `docs/adr/README` and `AGENTS.md` pointers | H lite | O1 | — |

### P2-X4 — Module-supplied commands, read routes and agent tools (A1)

**Goal:** a new module adds its API commands, read routes and agent tools, and its CLI group, by declaring them on its `ModuleSpec`. No edit to `tl-api`, `tl-mcp` or `tl-cli` source, no release of
those packages.
**Seams (sized):** `tl_api/commands.py:101-108` imports each module table by name; `tl_api/app.py:325-349` lists routers by hand; `tl_mcp/server.py:38-53,140-151` register tool files by hand;
`ModuleSpec` (`tl_core/modules.py:199-238`) holds projectors, words, actions and proposable rows, not commands, routes or tools. Files importing `tl_mod_*`: tl-api 24, tl-cli 55, tl-mcp 10, tl-tui 63,
tl-web 16.
**Design rule:** the hooks are lazy dotted references, resolved at load (fail fast) and refused outside the module's own top-level package (Q1), so `tl-core` imports no FastAPI, Typer or MCP code. S1
declares the hooks for all 8 modules; S2, S3 and the CLI ticket each switch their own surface under an equality test (the table built from `load_modules()` equals the old table: names, words, models).
**Demo** (`just demo P2-X4`, both adapters): 1. `tl new module` scaffolds a module with one command, one read route and one tool; no other package is edited. 2. After install it appears: a
`/commands/<Name>` route, `tl <module>` group, MCP tool listed. 3. The command runs through API and CLI; its access word is enforced (refused for a person without it). 4. An agent calls the tool:
refused until allowed; after an allow row, it files a proposal. 5. The read route and tool answer a hidden record exactly as a missing one, for the five readers. 6. A module whose hook names a missing
object fails at load with a fixed message, and the other modules still load. 7. `openapi.json` gains the routes additively; the X1 compatibility gate passes.
**Builder pieces (4):** S1 `ModuleSpec` hooks (`commands`, `read_router`, `tools`, `cli_group`) declared for all 8 modules, loader checks; S2 API: command table, routers and error rows from
`load_modules()`, equality test; S3 MCP: tool registration, the closed allow list for module tools, equality test; S4 conformance: runs the existing walks (`tl-api` and `tl-mcp`
`test_confidentiality_walk.py`, P2-TWIN) over `load_modules()`, adds the row-or-exclusion rule and the access-word check, and holds the registry drift check (old T05). No new harness.
**Must not preclude (later work):** the hook returns the same `CommandSpec` the dispatcher will own, plus an optional `meta` mapping (empty now) for B3 (record types, from-states, events, proposable,
`compensated_by`); handlers keep their present signature so B4 dry run and the dispatcher wrap them; proposable rows stay contributed by the module (B2); policy accept (X3) keys on the command name,
so names stay unique across modules (load refuses a clash).
**TUI note:** screens call `ClientInterface` and import modules by name (63 files). X4 does not change them. A module without screens reads through the generic record views. A TUI hook is a later
increment; the registry lines for the TUI stay supervisor glue until then.
**Checkpoints:** C1 = S1 merged (hooks, gated); C2 = S2, S3, T01 merged; C3 = S4, scaffold merged; C4 = demo green, SR-X3 closed.

| ID | Title | Tier | Depends | Sec |
|---|---|---|---|---|
| S1 | `ModuleSpec` hooks as lazy references for all 8 modules; load-time checks; unique command names (core interface: gated) | B | X3 C3, I6 T03 | Y |
| S2 | API command table, routers and error rows from `load_modules()`; equality test | B | S1 | Y |
| S3 | MCP tool registration from modules; module tools closed until allowed; equality test | B | S1 | Y |
| S4 | Conformance: existing walks over `load_modules()`, row-or-exclusion, word check, registry drift check | B | S2, S3 | Y |
| T01 | CLI group loading from the hook: `main.py` loop and equality test (§6 passes) | H full | S1 | Y |
| T02 | `tl new module` scaffold emits the hooks, an example read route and an example tool | H full | S2, S3, T01 | — |
| T03 | Fixture module `ext_demo` under `tests/` for the conformance run and the demo | H full | S4 | — |
| T04 | TUI note and module-author guide `docs/runbooks/new-module.md` | H lite | T02 | — |
| T05 | Demo driver `dev/demos/P2-X4.sh` | H full | T02, T03 | — |
| T06 | `AGENTS.md` "Where things go" rows; module README template update | H lite | T05 | — |

### P2-X5a and P2-X5b — Types, property sets and workflow states through schema packages (A4)

**Goal:** an admin, or an agent's proposal approved by an admin, adds a type or a property set on an existing module type (X5a), and later a workflow state (X5b), through the package registry (draft,
approve, publish, adopt). No shell.
**Seams (sized):** extension types load only from `file://` (`tl_core/extypes/loader.py:10,113`) after `tl types sync`; workflows are YAML under the schema directory (`tl_core/workflow/loader.py:3`);
module state tables are code (`tl_mod_awp/actions.py:64,183`). Property sets already move by ledgered package.
**Design rules:** a package gets a `kind` (`schema` today, `type`, `workflow`; optional, additive). A workflow package adds states and transitions and relabels. A state is never deleted: it becomes
`retired`, records keep it, new moves into it are refused. A module declares `locked_states` and `locked_transitions` (Q3); an admin may not retire or rewire those. Classification
(`tl_schema/classify*.py`) calls adding a state additive and retiring one constraining; the impact digest names the records in each retired state. The effective definition is the module base plus the
company package only: no project override layer (it exceeds the owner answer and no clause uses it).
**A3 (upcast hook): not planned here.** New states, types and property sets only add; a rename is a new state plus a retired one. Trigger to plan A3: a package change that must reinterpret an old
event payload.
**Demo X5a** (`just demo P2-X5`, clauses 1, 2, 7, both adapters): 1. An agent proposes a property set on `awp.IWP`; a different admin approves and publishes; a project adopts; conformance shows on an
existing IWP. 2. A new record type from a `type` package is created, listed and read without `tl types sync`. 7. An agent token cannot approve, publish or adopt (refused as today).
**Demo X5b** (same driver, clauses 3-6 added): 3. A `workflow` package adds a state after "Ready"; an IWP moves into it; the log shows the transition. 4. A package that retires a locked state is
refused at classification. 5. Retiring an unlocked state with 2 records needs an impact digest naming them; they stay readable. 6. `just rebuild-projections` gives the same state.
**X5a pieces (3):** S1 package kinds and classification (type, workflow) with the impact digest; S2 ledger-backed type loader (`ledger:` location, hash checked as for `file://`); S5 proposal row
`propose_schema_package` (draft only, filing check of X2). **X5b pieces (2):** S3 workflow ledger source, effective definition, `locked_states` on `ModuleSpec`; S4 `awp` and `requisitions` state
tables read from the effective definition.
**Checkpoints:** X5a C1 = S1, S2 merged; C2 = S5 merged; C3 = tickets merged; C4 = demo clauses 1, 2, 7 green, SR-X3 closed. X5b C1 = S3 merged; C2 = S4 merged; C3 = tickets merged; C4 = demo green,
SR-X4 closed. X5b has its own plan check row (§5) before its round 1.

| ID | Title | Tier | Depends | Sec |
|---|---|---|---|---|
| X5a S1 | Package kinds `type` and `workflow`; classify; impact digest by state (schema: gated) | B | — | Y |
| X5a S2 | Ledger-backed type loader (`ledger:` location) | B | S1 | Y |
| X5a S5 | Proposal row `propose_schema_package`; draft only | B | S1, X2 C2 | Y |
| X5a T01 | `tl schema package draft --kind type\|workflow`; `tl types list` reads the ledger | H full | S1, S2 | — |
| X5a T04 | Fixture company package: a property set on `awp.IWP` (gated fixture) | H full | S1 | — |
| X5a T07 | Walking tests: agent refused approve, publish, adopt; hidden type reads as missing | H full | S2, S5 | Y |
| X5a T08 | Pins: `file://` loader and watcher still pass their tests | H full | S2 | — |
| X5a T12 | Demo driver `dev/demos/P2-X5.sh`, clauses 1, 2, 7 | H full | T04, T07 | — |
| X5b S3 | Workflow ledger source, effective definition (company layer), `locked_states` on `ModuleSpec` (core interface: gated) | B | X5a S1, X4 C1, lock list signed | Y |
| X5b S4 | `awp` and `requisitions` state tables read from the effective workflow | B | S3 | Y |
| X5b T02 | Schema workbench screen shows package kind and retired states | H full | X5a S1 | — |
| X5b T03 | Read route and client method: effective workflow of a type (no record text; any signed-in person) | H full | S3 | Y |
| X5b T05 | Fixture workflow package: one added state after "Ready" (gated fixture) | H full | S3 | — |
| X5b T06 | Rebuild-equality property test with an added and a retired state | H full | S4 | Y |
| X5b T09 | Lake marts and reports accept state names they have not seen (read-only check) | H full | S4 | — |
| X5b T10 | Demo driver adds clauses 3-6 | H full | T05, T06 | — |
| X5b T11 | Update `schema-package-change.md` and the language reference; ADR addendum for retired states | H lite | T10 | — |

## 2. Later work (not in this plan)

| Item | Needs | A1 must not preclude |
|---|---|---|
| Dispatcher (OR §3, about 17) | X1, X4 | one command table built from modules; the service already owns idempotency |
| B3 command catalog (3) | X4 `meta` | per-command record types, from-states, events, proposable, `compensated_by` |
| B2 generic propose tool (3) | B3, X3 | module-contributed proposable rows; closed per-command list |
| B4 preview and `dry_run` (2) | dispatcher | handler signatures unchanged |
| B7 compensation read (2) | B3 | optional `compensated_by` in `meta` |
| Delegation build, shadow first (about 4) | X3, B3 | policy keys on unique command names |
| B8 reason codes and stats (1.5), B9 stale queue (1), A5 saved views inside 7a, A6 versioned semantic outputs | — | — |

## 3. P2-I6 and shared registries

P2-I6 splits. Its prep (B2 marts sync, T02 gold marts, T03 reports audit) runs in wave 1 beside X1; it touches `tl_sim`, `tl_lake`, docs and reports. I6 B1 and T01 are re-scoped without scaffold: B1
carries `material_late` and `design_revision`, `scaffold_failed` waits for the I4-B scaffold actor (08 Increment 6 carries a note). The I6 exit (T04, T05) stays at roadmap item 8, after the web
increment; it does not wait for X2 C3 or any X item. X1 needs I5 and P2-PUNCH merged to trunk (T03 needs I5). X4 starts after I6 T03 merged, because X4 rewrites how registry lists are built. The web
increment starts after X4 C4 and X5a C4. X5b is the extension tail beside the phase report.

| Registry | Collides | Rule |
|---|---|---|
| `proposals.submit` and `proposals/types.py` | X1 S1, X2 S1-S3, X5a S5 | X1 merges first, X2 second, X5a last; each rebases |
| `schema/core/*.yaml`, `platform.yaml`, generated artefacts | X1 S1, X2 S2-S3 | one gated schema merge per increment; later side runs `just gen` |
| `tl_api/commands.py`, `app.py`, `openapi.json`, X1 baseline | X4 S2, I6 T03 | I6 T03 audits from `openapi.json` and merges first; X4 owns the registry; baseline refreshed in X4 and X5a |
| `tl_mcp` lists, `AGENT_MAY_NOT`, pinned test lists | X1 T03, X2 T04, X4 S3-S4, X5a T07 | X4 S4 holds the generated-list drift check |
| `ModuleSpec` (`tl_core/modules.py`) | X4 S1, X5b S3 | X5b S3 waits for X4 C1 |
| Workflow fixtures and mart state names | X5b S4, T05, I6 T02 | X5b T09 checks marts; I6 marts read states as text |
| Simulator roster | I6 only | unchanged; I6 scenario agents get module `user` grants before I6 T04 |

## 4. Waves (3 slots) and security review

Slots: supervisor round, builder, security reviewer, plan check and a ticket workflow are one each. Two streams in a wave alternate rounds. At most 2 builders gating at once; X4 S4 runs alone; the
DONE gate never runs next to a builder gate. Wave 3 holds up to 5 pieces: they start as slots free, X4 S1 first.
Every SR names the range `<trunk before wave>..<head>`.

| Wave | Streams | Registry owner | Security review at wave end (one fresh reviewer, ≤ 450k tokens) |
|---|---|---|---|
| 1 | X1 ∥ I6 prep (B2, T02, T03); X3 is orchestrator work (O1 has no dependency; O2 plan check) | X1 | SR-X1: X1 S1, T01, T03, T07 plus I6 B2 and T02 (lake guard); proofs: replay as five readers, cross-actor key, key never in logs, mismatch writes nothing, concurrent insert never 500 |
| 2 | X2 | X2 | SR-X2: S1-S3, T01-T04; proofs: refusals equal missing, cap text carries no counts, held count and list filtered before counting, stop holds accept, stop events append-only, agent cannot call stop. I6 B1 stays under I6 SR5 at the exit |
| 3 | X4 ∥ X5a | X4 | SR-X3 from the wave-3 base: X4 S1-S4, T01; X5a S1, S2, S5, T07; proofs: module tools closed by default, five-reader walk of every module surface, name clash refused, a failed module does not open others, agent proposes but never publishes |
| 4 | X5b (after the lock list is signed and the X5b plan check) | X5b | SR-X4: X5b S3, S4, T03, T06; proofs: locked states cannot retire, retired state still readable, rebuild equality |

Web increment: after wave 3 closes. The X3 ADR gets its own planner-tier check (O2). Whole-suite gate once per increment DONE; `gate-pg` on touched directories.

## 5. Approvals needed (human gates)

| Item | Increment | Why | Approver |
|---|---|---|---|
| Operational table `idempotency_key` in `schema/core`; setting `idempotency.retention_days` in `platform.yaml` | X1 | schema and settings | orchestrator, APPROVALS line |
| OpenAPI baseline file and its refresh rule | X1 | release process | owner |
| Amendment to ADR-0027: the filing check moves from Phase 3 to X2 | X2 | ADR | owner |
| Setting for the project queue cap; events `Agent.Stopped`, `Agent.Resumed` and projection | X2 | schema and settings | orchestrator, APPROVALS line |
| Delegation ADR (core interface) | X3 | ADR | owner |
| `ModuleSpec` hooks and `CommandSpec.meta` (addendum to the module-seam ADR; Q1) | X4 | core interface | orchestrator, APPROVALS line |
| Package kind field, `type`/`workflow` classification, `ledger:` location; fixture packages T04 | X5a | schema, fixtures | orchestrator, APPROVALS line |
| Plan check of X5b before its round 1 | X5b | skill rule 8 | orchestrator |
| `locked_states` on `ModuleSpec`; fixture package T05 | X5b | core interface, fixtures | orchestrator, APPROVALS line |
| Per-module lock list (IWP release and issue path, requisition approve path); rule that an admin may not retire them | X5b | owner sign-off before X5b S3 (Q3) | owner |

## 6. Token cost (est.)
No Phase 2 report gives a measured per-increment figure. Yardstick: `08-phase2-plan.md` §0.2 puts a process-v2 increment at 0.15 to 0.3 B input tokens; security reviews are capped at 450k each. All
figures are est.

| Increment | Items | Rounds | Input est. | Output est. |
|---|---|---|---|---|
| X1 | 1 B, 9 H | 4 | 0.1 B | 0.7 M |
| X2 | 3 B, 6 H | 5 | 0.15 B | 1 M |
| X3 | 2 O, 1 H | 1 | 0.03 B | 0.2 M |
| X4 | 4 B, 6 H | 6 | 0.2 B | 1.5 M |
| X5a | 3 B, 8 H | 4 | 0.12 B | 1 M |
| X5b | 2 B, 9 H | 4 | 0.12 B | 1 M |
| Security reviews (4) | | | 1.8 M at the cap | — |
Total est.: about 0.75 B input, 24 rounds, 13 pieces, 39 t and 2 O (drops from about 0.95 B after the check: X5 company layer only, X4 tickets folded into pieces, X4 S4 reuses existing walks, X1 purge
deferred).

## 7. Risks

1. Idempotency replay leaks text after a clearance change. Mitigation: ids and hash only; viewer filter on replay (X1 demo 5).
2. Filing and cap refusals, held count or stopped list reveal that a scope, queue or record exists. Mitigation: one fixed text, filter before counting, five-reader walks (X2 T04).
3. A module hook loads code the reviewer did not see. Mitigation: hooks refer to installed packages in the module's own package only; conformance on every surface (X4 S4).
4. Module tools or routes ship open to agents. Mitigation: closed by default; conformance fails a new tool with no allow decision.
5. Registry collisions with in-flight increments (§3). Mitigation: owner per wave, X4 after I6 T03, scripted list drift check.
6. An admin retires or rewires a state code depends on. Mitigation: `locked_states`, classification refuses, impact digest.
7. Core-interface drift from the later dispatcher or catalog. Mitigation: X3 trace table, `meta` field.
8. The approval queue becomes the limit. Mitigation: queue cap (X2), shadow mode (later), stats (B8).
9. X2 S1 refuses agents with no module `user` grant. Mitigation: grant checklist (X2 T06), demo clause 2, grants before I6 T04.

## 8. Open questions

| Q | Question | Decided by | Status |
|---|---|---|---|
| Q1 | Are `ModuleSpec` hooks lazy dotted refs? | orchestrator | Decided: yes. Resolved at load, fail fast; a ref outside the module's own top-level package is refused. Needs its §5 APPROVALS line. |
| Q2 | Are modules only repo packages, with data extensions only through ledgered packages? | owner | Decided (owner 2026-11-13): yes. Agent-written modules ship only as repo packages through ticket, review, human merge and deploy; no code loads from the ledger or uploads; types and psets go through ledgered packages. |
| Q3 | Do modules declare `locked_states` and `locked_transitions` in code? | owner | Decided (owner 2026-11-13): yes. Relabel allowed; retire or rewire refused. The owner signs the per-module lock list (IWP release and issue path, requisition approve path) before X5b S3 (§5 gate row). |
| Q4 | What does an idempotency entry hold? | orchestrator | Decided: (actor, key) to command name, body hash and result ids; no response text; replay re-reads through the viewer filter; 7-day default in a gated setting; a retry after expiry files anew (runbook says so). |

## Plan check

4 PLANCHK docs/build-spec/12-extension-plan.md @6723e117
| F1 HI §3 order: X4 is placed after I6 closes, and X5 after the phase exit as an "extension tail". Roadmap item 7 (web increment) comes before item 8 (I6, roadmap-2026-11-07.md:25-26). The owner answer says A1/A4 come before the web increment, so this order breaks it -> state in §3 that the web increment starts after X4 C4 (and X5a C4), and amend the roadmap order, or record an owner waiver
| F2 HI §0/§3 I6 collision: the owner answer says I5 and PUNCH close first, but they are unmerged (branches p2/i5, p2/punch) while X1 "needs none". "I6 prep T01-T03" is wrong: I6 T01 needs B1 (scaffold_failed and the scaffold actor, and I4-B is trimmed to roadmap 3c), and T03 needs I5 on trunk -> X1 needs I5 and PUNCH merged; wave 1 I6 prep = B2, T02, T03 only; re-scope I6 B1/T01 without scaffold; if the I6 exit waits for X2 C3, add the X1/X2 clauses to the 08 I6 T04 clause list, or drop the wait
| F3 MD X3/§4 critical path: O1 depends on X2 C1, but the §0 table says X3 needs "none" and §4 puts X3 in wave 1. Also, the clause the ADR traces is X2 S3 (stop switch), not S1 -> make O1 depend on nothing (cite the X2 S3 piece spec) so the ADR merges in wave 1 and X4 S1 waits on nothing but I6/F1
| F4 MD X1 seam: there is no "command service". Handlers are called directly at tl_api/commands.py:359 and :503, in embedded.py, and in the CLI; services/commands.py:46 is only the model field -> S1 names a helper (e.g. tl_core.services.idempotency) and its call sites (those two API sites and proposals.submit). The spec also says what a concurrent insert of the same (actor, key) does: it answers as a replay or a fixed in-progress refusal, never a 500
| F5 MD X4 tiers: T01/T02 edit every module's ModuleSpec plus 4 shared registry files (8 modules, more than 5 files), and T05 touches about 10 pinned test files (08 §0.3). Both fail §6 items 1 and 4, and skill rule 12 says this should be one piece per area -> S1 declares the hooks for all 8 modules; S2/S3/S5 each switch their own surface under the equality test; fold T05 into S4; delete T01, T02, T05. S5 then becomes main.py loop + test, which passes §6 -> make it t full (4 pieces)
| F6 MD X5 scope: S3's "project override" layer goes beyond the owner answer (company admin may change states), and no demo clause uses it -> drop it or add a clause. X5 has 16 items and §6 asks for its own check, which is unscheduled -> split it. X5a: types and psets (S1, S2, S5, T01, T04, T07, T08), all in wave 3 beside X4. X5b: workflows (S3, S4, T02, T03, T05, T06, T09, T10, T11), after the owner signs the lock list
| F7 MD X2 hidden=missing: the T03 held count and the T01 "list stopped" route count pending proposals that can name hidden records, and T04 walks refusals only. Being an admin is not clearance (ADR-0016) -> add a five-reader walk of the held count and the list to T04; filter before counting (141); mark T03 Sec Y
| F8 MD X2 behaviour change: S1 starts refusing existing pilot and simulator agents that lack a module `user` grant (agent tokens carry no scope, auth/types.py:101-108) -> T06 adds a grant checklist using the existing GrantModuleRole (no data migration); add a demo clause where a granted agent files; grant the I6 scenario agents before I6 T04
| F9 MD §4 security: only SR-X1 names a commit range. SR-X4's wave-4 range misses X5 S1-S2, which merge in wave 3. I6 B1/B2 and the lake guard (old SR5) sit in no review -> every SR names `<trunk before wave>..<head>`; SR-X4 starts at the wave-3 base for X5 S1-S2; add the I6 Sec rows to SR-X1/SR-X2
| F10 MD §5 gates: no row names an approver -> add an approver column on the ADR-0027 F12 pattern. Owner: X3 ADR, locked-state list, OpenAPI baseline refresh rule. Orchestrator with an APPROVALS line: schema, settings, fixture packages. Add rows for the ADR-0027 amendment (filing check moved from Phase 3 to X2) and the X5 plan check
| F11 LO §4 waves: wave 3 can have X4 S2, S3 and S5 plus X5 S1 and S2 as builders alive at once, which breaks 3 slots and 2 heavy gate runs. §4 never states the 2-run cap -> write "at most 2 builders gating at once; X4 S4 harness runs alone; DONE gate never next to a builder gate"
| F12 LO §6 cost: about 26 rounds (X1 5, X2 5, X3 1, X4 7, X5 8), 15 pieces, 36 t + 2 O, about 0.95 B input, consistent with 08 §0.2. Top 3 and a cheaper shape for each: (a) X5 S3: company layer only, X5b after locks; (b) X4 T01/T02/T05: folded into pieces (F5); (c) X4 S4: run the existing walks (tl-api/tl-mcp test_confidentiality_walk.py, P2-TWIN) over load_modules() instead of a new harness. Also: X1 S2 purge job has no demo clause -> add "expired key files anew" or defer S2 and keep the setting only
| Q0 The Q1-Q4 questions are not in the plan file (either commit) -> add "§8 Open questions" holding the four recs below
| Q1 orch-decidable: yes, lazy dotted refs. Resolve all of them at load (fail fast) and refuse a ref outside the module's own top-level package. The ModuleSpec addendum still needs its §5 APPROVALS line
| Q2 owner: yes, modules only as repo packages (ticket, review, release); data extensions only through ledgered packages. The owner must confirm because every agent-written module then needs a human-merged PR and a deploy
| Q3 owner (per-module list) / orch (mechanism): yes to locked_states and locked_transitions declared in module code. Relabel allowed; retire or rewire refused. The owner signs the list (IWP release/issue path, requisition approve path) before X5b S3
| Q4 orch-decidable: yes, store (actor, key) -> command name + body hash + result ids, no response text; replay re-reads through the viewer filter. Default 7 days in the gated retention setting. The runbook states that a retry after expiry files anew
| 73 Additive-only rules, ids-only replay through the viewer filter, closed-by-default module tools, the X3 trace table and must-not-preclude list, the §3 registry table, and Sec rows matching the SR lists for X1, X2 and X4 are sound. Spot-checked seams are true: commands.py:46, proposals.py:499/573/636, module roles in cur_account_module_role
| 30

### Answers

F1 done: §0, §3 web increment starts after X4 C4 and X5a C4; roadmap order lines amended (owner answers 2026-11-12, ARCH-CRITIQUE)
F2 done: §0, §3 X1 needs I5 and PUNCH merged; wave-1 I6 prep = B2, T02, T03; I6 B1/T01 without scaffold (08 Increment 6 note); I6-exit wait on X2 dropped
F3 done: §1 X3 O1 depends on nothing, cites the X2 S3 piece spec; §4 wave 1
F4 done: §1 X1 S1 names `tl_core.services.idempotency` and its call sites; concurrent-insert rule; demo clause 2
F5 done: §1 X4 hooks for all 8 modules in S1; S2, S3, T01 switch own surface; T05 folded into S4; old T01, T02, T05 deleted; CLI loader is T01 (full); 4 pieces
F6 done: §1 X5 split; company layer only; X5a (S1, S2, S5, T01, T04, T07, T08, plus T12 demo driver) wave 3; X5b (S3, S4, T02, T03, T05, T06, T09, T10, T11) after lock list; X5b check row in §5
F7 done: §1 X2 T04 five-reader walk of held count and list; T03 filters before counting, Sec Y; demo clause 6
F8 done: §1 X2 T06 grant checklist (`GrantModuleRole`); demo clause 2; §3 grants before I6 T04; §7 risk 9
F9 done: §4 every SR names `<trunk before wave>..<head>`; SR-X3 from the wave-3 base covers X5a S1, S2, S5, T07; I6 B2 and T02 in SR-X1; I6 B1 moved to the exit wave under I6 SR5, so SR-X2 gets no I6 row
F10 done: §5 approver column; owner and orchestrator rows; ADR-0027 amendment and X5b plan check rows
F11 done: §4 2-run cap, X4 S4 alone, DONE gate never beside a builder gate
F12 done: §6 (a) company layer, X5b after locks; (b) folded tickets; (c) X4 S4 reuses existing walks; X1 S2 purge deferred (DEFERRED.md row)
Q0-Q4 done: §8 holds Q1-Q4; Q1, Q4 decided (orch), Q2, Q3 decided (owner 2026-11-13)
