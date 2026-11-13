# Build spec 12 — Extension plan: agent-run mutation and agent-built extensions

Status: DRAFT v0.1, 2026-11-13. Plan only. Source: `docs/reports/ARCH-CRITIQUE-2026-11-11.md` (A1-A5, B1-B8, owner
answers 2026-11-12). Format follows `08-phase2-plan.md` Increment 6.
Increments are named `P2-X1` to `P2-X5`; ticket IDs `P2-X<n>-T<nn>`, pieces `S<n>`.

Tier letters: **H** ticket (`lite`/`full` review), **B** builder piece (`full`), **O** orchestrator. Sec `Y`: in the wave's security scope.

## 0. Scope, order and rules
Owner decisions (2026-11-12, all yes): agents file proposals in the pilot; accept-by-policy is a first-year goal; the
owner's own agents extend the system first (full modules, and property sets on existing modules); a company admin may
change a module's workflow states. Order, kept as the owner's unless a seam forces a change:

| Inc | Critique items | One line | Needs before start |
|---|---|---|---|
| P2-X1 | B1, A2 | Idempotency key that works; OpenAPI compatibility gate | none |
| P2-X2 | B6 | Agent filing check, per-project queue cap, per-agent stop switch | X1 merged (both touch `proposals.submit`) |
| P2-X3 | B5 | Delegation ADR, shadow mode first (ADR only) | none; X4 needs it merged |
| P2-X4 | A1 | Modules supply their own commands, read routes and agent tools (API, CLI, MCP; TUI note) | X3 ADR merged |
| P2-X5 | A4 (A3 if needed) | Types, property sets and company-editable workflow states through schema packages | X4 C1 (ModuleSpec fields) |

Rules for every increment:
- Additive only. No existing event changes. No data migration. New event types and optional fields only.
- Hidden looks exactly like missing (phrase 140): status, text and counts match, for every new read route, tool,
  refusal and count. The visibility filter runs before LIMIT and before counting (141). A new route or tool carrying
  record text gets a walking test as five kinds of reader (`AGENTS.md`).
- Authorization stays closed for agents: a new route or tool is denied until someone allows it (ADR-0009).
- Agent-written extensions are code in the repository (a module) or data through a ledgered package. Nothing loads
  code from the ledger or from an upload. A module ships through a ticket, a review and a release; a data extension
  goes through draft, approve by a different admin, publish, adopt (`docs/runbooks/schema-package-change.md`).
- Every schema, setting and core-interface change below needs an APPROVALS line before its merge (listed in §5).
- Anything over about 10 tickets, and every core-interface ADR, gets a planner-tier check first (skill rule 8).

## 1. Increments

### P2-X1 — Idempotency key and OpenAPI compatibility gate

**Goal:** a retry after a timeout never files a second proposal or creates a second record; a renamed or removed API
field fails `just check` before release.
**Seams (sized):** `Command.idempotency_key` is accepted and ignored (`tl_core/services/commands.py:46`); proposals set
it to `None` (`services/proposals.py:499,573,636`); no header in `tl-api`. `compat.py` already diffs events; OpenAPI is
only drift-checked.
**Demo** (`just demo P2-X1`, both adapters):
1. Same actor sends one command twice with one `Idempotency-Key`: one event set, the second answer equals the first.
2. The same key with a different body is refused with a fixed message; nothing is written.
3. An agent files a proposal twice with one key (API and MCP): one proposal row.
4. Another actor with the same key value does not see or collide with the first actor's entry.
5. After the actor's clearance drops, a replay returns ids that the viewer filter hides as absent (140).
6. A removed response field in a scratch `openapi.json` fails `just check`; an added optional field passes.
**Builder pieces (2):** S1 operational table `idempotency_key` (actor, key, command name, body hash, result ids,
created), the replay and mismatch rule inside the command service and `proposals.submit`, one transaction with the
write; S2 purge job kind with a retention setting (bounded run, derives work from state).
**Checkpoints:** C1 = S1 merged; C2 = S2 and the route, client and tool tickets merged; C3 = gate and docs merged;
C4 = demo green, SR-X1 closed.
**Design notes:** the key is per actor, ASCII, at most 128 characters, never logged or put in an error text. Store ids
and the command hash, not response text; a replay re-reads through the viewer filter. The dispatcher (later) moves the
check into one place; X1 puts it in the service so that move is a call-site change.

| ID | Title | Tier | Depends | Sec |
|---|---|---|---|---|
| S1 | Idempotency store, replay and mismatch rule in command service and `proposals.submit` (schema: gated) | B | — | Y |
| S2 | Purge job kind and retention setting (gated setting) | B | S1 | — |
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

**Goal:** an agent in the pilot can file only where it may propose, cannot flood a project queue, and an admin can
stop one agent and hold what it filed.
**Seams (sized):** one cap, 500 per agent per UTC day (`proposals/types.py:101`); agent tokens carry no scope
(`tl_core/auth/types.py:101-108`); ADR-0027 F1 decided the filing check is the module's `user` word on the scope.
**Demo** (`just demo P2-X2`, both adapters):
1. An agent without the module `user` word on the scope files a proposal: refused, the same as a scope that does not exist.
2. With the word it files; the person who accepts still needs the command's own access word.
3. A project pending-queue cap (setting) is reached: the next filing is refused with a fixed text that shows no counts.
4. An admin runs `tl agent stop`: new filings are refused; pending ones show as held; accept is refused while stopped.
5. `tl agent resume` lifts both; the ledger shows `Agent.Stopped` then `Agent.Resumed`, nothing rewritten.
**Builder pieces (3):** S1 filing check in `proposals.submit` (word on scope, hidden equals missing); S2 per-project
queue cap (setting, counted before the cap text, fixed message); S3 stop switch (two additive event types, a
projection, `StopAgent` and `ResumeAgent` as `admin` commands, the check at filing and at accept).
**Checkpoints:** C1 = S1 merged; C2 = S2, S3 merged; C3 = surfaces and tests merged; C4 = demo green, SR-X2 closed.

| ID | Title | Tier | Depends | Sec |
|---|---|---|---|---|
| S1 | Filing check: module `user` word on the scope; uniform refusal | B | X1 C1 | Y |
| S2 | Project pending-queue cap and fixed refusal text (gated setting) | B | S1 | Y |
| S3 | Agent stop switch: events, projection, admin commands, filing and accept checks (schema: gated) | B | — | Y |
| T01 | API routes and `ApiClient` methods for stop, resume, list stopped | H full | S3 | Y |
| T02 | `tl agent stop`, `resume`, `stopped` (CLI `require_admin`) | H full | S3 | Y |
| T03 | Accounts screen shows an agent's stopped flag and held count | H full | T01 | — |
| T04 | Walking tests: refusals look like missing; cap text carries no counts; `AGENT_MAY_NOT` rows for the new commands | H full | S1, S2, S3 | Y |
| T05 | Demo driver `dev/demos/P2-X2.sh` | H full | T02, T04 | — |
| T06 | Update `docs/runbooks/accounts-and-access.md` and the platform settings reference | H lite | T05 | — |

### P2-X3 — Delegation ADR (accept by policy), shadow mode first

**Goal:** an accepted core-interface ADR, so the dispatcher, the command catalog and A1 are built with policy accept in
mind. ADR only; the build (about 4 points) is listed under later work.
**Content the ADR must settle (B5):** a policy record (agent, command type, scope, field bounds, daily cap, expiry,
granted by); a policy accept is a normal `Proposal.Accepted` with an optional `policy` key (additive); shadow mode:
evaluate at filing, record "would have accepted", compare with people's decisions, never accept; who may grant
(admin plus one other admin); the stop switch of X2 overrides every policy; viewer-filtered scope resolution; policy
never covers commands whose word is `admin`, money, access or schema publication (a closed exclusion list).
**Demo (document check, no code):** 1. ADR merged with an APPROVALS line. 2. A trace table in the ADR maps each clause
to X2's stop switch, A1's `meta` field and the later catalog (B3) and compensation read (B7). 3. Plan check returned
and answered.
**Checkpoints:** C1 = draft ADR; C2 = plan check answered; C3 = ADR merged; C4 = X4 plan re-read against it.

| ID | Title | Tier | Depends | Sec |
|---|---|---|---|---|
| O1 | ADR (next free number) delegation by policy, shadow mode first | O | X2 C1 | — |
| O2 | Planner-tier check of the ADR (skill rule 8), findings under its `## Plan check` | O | O1 | — |
| T01 | Index the ADR in `docs/adr/README` and `AGENTS.md` pointers | H lite | O1 | — |

### P2-X4 — Module-supplied commands, read routes and agent tools (A1)

**Goal:** a new module adds its API commands, read routes and agent tools, and its CLI group, by declaring them on
its `ModuleSpec`. No edit to `tl-api`, `tl-mcp` or `tl-cli` source, no release of those packages.
**Seams (sized):** `tl_api/commands.py:101-108` imports each module table by name; `tl_api/app.py:325-349` lists
routers by hand; `tl_mcp/server.py:38-53,140-151` register tool files by hand; `ModuleSpec`
(`tl_core/modules.py:199-238`) holds projectors, words, actions and proposable rows, not commands, routes or tools.
Files importing `tl_mod_*`: tl-api 24, tl-cli 55, tl-mcp 10, tl-tui 63, tl-web 16.
**Design rule:** the hooks are lazy references (dotted path, resolved by each surface), so `tl-core` imports no
FastAPI, Typer or MCP code. Existing modules keep working by name until their ticket switches them, with an equality
test (the table built from `load_modules()` equals the old table: names, words, models).
**Demo** (`just demo P2-X4`, both adapters): 1. `tl new module` scaffolds a module with one command, one read route
and one tool; no other package is edited. 2. After install it appears: a `/commands/<Name>` route, `tl <module>` group,
MCP tool listed. 3. The command runs through API and CLI; its access word is enforced (refused for a person without
it). 4. An agent calls the tool: refused until allowed; after an allow row, it files a proposal. 5. The read route and
tool answer a hidden record exactly as a missing one, for the five readers. 6. A module whose hook names a missing
object fails at load with a fixed message, and the other modules still load. 7. `openapi.json` gains the routes
additively; the X1 compatibility gate passes.
**Builder pieces (5):** S1 `ModuleSpec` hooks (`commands`, `read_router`, `tools`, `cli_group`) and loader checks;
S2 API: command table, routers and error rows built from `load_modules()`; S3 MCP: tool registration and the closed
allow list for module tools; S4 conformance harness that finds every module surface and runs the five-reader walk,
the row-or-exclusion rule and the access-word check; S5 CLI group loading from the hook.
**Must not preclude (later work):** the hook returns the same `CommandSpec` the dispatcher will own, plus an optional
`meta` mapping (empty now) for B3 (record types, from-states, events, proposable, `compensated_by`); handlers keep
their present signature so B4 dry run and the dispatcher wrap them; proposable rows stay contributed by the module
(B2); policy accept (X3) keys on the command name, so names stay unique across modules (load refuses a clash).
**TUI note:** screens call `ClientInterface` and import modules by name (63 files). X4 does not change them. A module
without screens reads through the generic record views. A TUI hook is a later increment; the registry lines for the
TUI stay supervisor glue until then.
**Checkpoints:** C1 = S1 merged (hooks, gated); C2 = S2, S3, S5 merged; C3 = S4, module switches, scaffold merged;
C4 = demo green, SR-X3 closed.

| ID | Title | Tier | Depends | Sec |
|---|---|---|---|---|
| S1 | `ModuleSpec` hooks as lazy references; load-time checks; unique command names (core interface: gated) | B | X3 C3 | Y |
| S2 | API command table, routers and error rows from `load_modules()` | B | S1 | Y |
| S3 | MCP tool registration from modules; module tools closed until allowed | B | S1 | Y |
| S4 | Conformance harness: five-reader walk, hidden equals missing, row-or-exclusion, word check, over all module surfaces | B | S2, S3 | Y |
| S5 | CLI group loading from the hook; gates unchanged | B | S1 | Y |
| T01 | Switch `awp` and `materials` to the hooks with an equality test | H full | S2, S3, S5 | Y |
| T02 | Switch `correspondence`, `documents`, `cost`, `schedule`, `engineering`, `schemareg` (one ticket per two modules if the 5-file rule bites) | H full | T01 | Y |
| T03 | `tl new module` scaffold emits the hooks, an example read route and an example tool | H full | S2, S3, S5 | — |
| T04 | Fixture module `ext_demo` under `tests/` for the harness and demo | H full | S4 | — |
| T05 | Regenerate the pinned registry lists with a script and replace hand edits with a drift check | H full | T02 | — |
| T06 | TUI note and module-author guide `docs/runbooks/new-module.md` | H lite | T03 | — |
| T07 | Demo driver `dev/demos/P2-X4.sh` | H full | T03, T04 | — |
| T08 | `AGENTS.md` "Where things go" rows; module README template update | H lite | T07 | — |

### P2-X5 — Types, property sets and workflow states through schema packages (A4)

**Goal:** an admin, or an agent's proposal approved by an admin, adds a type, a property set on an existing module
type, or a workflow state, through the package registry (draft, approve, publish, adopt). No shell access.
**Seams (sized):** extension types load only from `file://` (`tl_core/extypes/loader.py:10,113`) after `tl types sync`;
workflows are YAML under the schema directory (`tl_core/workflow/loader.py:3`); module state tables are code
(`tl_mod_awp/actions.py:64,183`). Property sets already move by ledgered package.
**Design rules:** a package gets a `kind` (`schema` today, `type`, `workflow`; an optional field, additive). A
workflow package adds states and transitions and relabels. A state is never deleted: it becomes `retired`, existing
records keep it, new moves into it are refused. A module declares `locked_states` and `locked_transitions` that its
code depends on (for example the IWP release path); an admin may not retire or rewire those. Classification
(`tl_schema/classify*.py`) calls adding a state additive and retiring one constraining, and the adoption impact
digest names the records in each retired state. The file watcher stays for development.
**A3 (upcast hook): not planned here.** New states, types and property sets only add. A rename is a new state plus a
retired one, so no stored payload is reinterpreted. Trigger to plan A3: a package change that must reinterpret an old
event payload, or the first non-additive payload correction.
**Demo** (`just demo P2-X5`, both adapters): 1. An agent proposes a property set on `awp.IWP`; an admin approves
(a different admin from the drafter) and publishes; a project adopts; the pset conformance shows on an existing IWP.
2. A new record type from a `type` package is created, listed and read without `tl types sync`. 3. A `workflow`
package adds a state after "Ready"; an IWP moves into it; the transition appears in the log. 4. A package that
retires a locked state is refused at classification. 5. Retiring an unlocked state with 2 records in it needs an
impact digest that names them; the records stay readable. 6. `just rebuild-projections` gives the same state.
7. An agent token cannot approve, publish or adopt (refused as it is today).
**Builder pieces (5):** S1 package kinds and classification (type, workflow) with the impact digest; S2 ledger-backed
type loader (a `ledger:` location, content held in the registry, hash checked as for `file://`); S3 ledger source for
workflow definitions, the effective definition (module base, company package, project override) and the
`locked_states` fields on `ModuleSpec`; S4 module state tables for `awp` and `requisitions` read from the effective
definition; S5 proposal row `propose_schema_package` (draft only, filing check of X2).
**Checkpoints:** C1 = S1, S2 merged; C2 = S3 merged; C3 = S4, S5 and tickets merged; C4 = demo green, SR-X4 closed.

| ID | Title | Tier | Depends | Sec |
|---|---|---|---|---|
| S1 | Package kinds `type` and `workflow`; classify; impact digest by state (schema: gated) | B | — | Y |
| S2 | Ledger-backed type loader (`ledger:` location) | B | S1 | Y |
| S3 | Workflow ledger source, effective definition, `locked_states` on `ModuleSpec` (core interface: gated) | B | S1, X4 C1 | Y |
| S4 | `awp` and `requisitions` state tables read from the effective workflow | B | S3 | Y |
| S5 | Proposal row `propose_schema_package`; draft only | B | S1, X2 C2 | Y |
| T01 | `tl schema package draft --kind type\|workflow`; `tl types list` reads the ledger | H full | S1, S2 | — |
| T02 | Schema workbench screen shows package kind and retired states | H full | S1 | — |
| T03 | Read route and client method: effective workflow of a type (no record text; any signed-in person) | H full | S3 | Y |
| T04 | Fixture company package: a property set on `awp.IWP` (gated fixture) | H full | S1 | — |
| T05 | Fixture workflow package: one added state after "Ready" (gated fixture) | H full | S3 | — |
| T06 | Rebuild-equality property test with an added and a retired state | H full | S4 | Y |
| T07 | Walking tests: agent refused approve, publish, adopt; hidden type reads as missing | H full | S2, S5 | Y |
| T08 | Pins: `file://` loader and watcher still pass their tests | H full | S2 | — |
| T09 | Lake marts and reports accept state names they have not seen (read-only check) | H full | S4 | — |
| T10 | Demo driver `dev/demos/P2-X5.sh` | H full | T04, T05, T07 | — |
| T11 | Update `schema-package-change.md` and the language reference; ADR addendum for retired states | H lite | T10 | — |

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

P2-I6 (sim, lake marts, report audit, exit demo) runs **beside X1 and X2, not after X5**. It touches `tl_sim`,
`tl_lake`, docs and reports; X1 to X3 touch core services, one API route family, MCP write tools and settings. Its exit
demo (T04) waits for X2 C3 so the exit includes retries and filing checks; X4 starts only after I6 closes, because X4
rewrites how the registry lists are built. X5 does not delay the phase exit: the report records X4 and X5 as the
extension tail.

| Registry | Collides | Rule |
|---|---|---|
| `proposals.submit` and `proposals/types.py` | X1 S1, X2 S1-S3, X5 S5 | X1 merges first, X2 second, X5 last; each rebases |
| `schema/core/*.yaml`, `platform.yaml`, generated artefacts | X1 S1-S2, X2 S2-S3 | one gated schema merge per increment; later side runs `just gen` |
| `tl_api/commands.py`, `app.py`, `openapi.json`, X1 baseline | X4 S2, I6 T03 | I6 T03 audits from `openapi.json`; X4 owns the registry; baseline refreshed in X4 and X5 |
| `tl_mcp` lists, `AGENT_MAY_NOT`, pinned test lists | X1 T03, X2 T04, X4 S3-S4, X5 T07 | regenerate lists by script (X4 T05) |
| `ModuleSpec` (`tl_core/modules.py`) | X4 S1, X5 S3 | X5 S3 waits for X4 C1 |
| Workflow fixtures and mart state names | X5 S4-S5, I6 T02 | X5 T09 checks marts; I6 marts read states as text |
| Simulator roster | I6 only | unchanged |

## 4. Waves (3 slots) and security review

Slots: supervisor round, builder, security reviewer, plan check and a ticket workflow are one each. Two streams in a
wave alternate rounds.

| Wave | Streams | Registry owner | Security review at wave end (one fresh reviewer, ≤ 450k tokens) |
|---|---|---|---|
| 1 | X1 ∥ I6 prep (T01-T03); X3 is orchestrator work (ADR, plan check) | X1 | SR-X1: X1 S1, T01, T03, T07; range `<trunk before wave>..<head>`; proofs: replay as five readers, cross-actor key, key never in logs, mismatch writes nothing |
| 2 | X2 ∥ I6 exit (T04, T05) | X2 | SR-X2: S1-S3, T01, T02, T04; proofs: refusals equal missing, cap text carries no counts, stop holds accept, stop events are append-only, agent cannot call stop |
| 3 | X4 ∥ X5 (S1, S2 only: they touch `tl_schema` and `extypes`, not `ModuleSpec`) | X4 | SR-X3: X4 S1-S5, T01, T02; proofs: module tools closed by default, five-reader walk of every module surface, name clash refused, a failed module does not open others |
| 4 | X5 (S3-S5, tickets) | X5 | SR-X4: X5 S1-S5, T03, T06, T07; proofs: admin-only publish by a second admin, locked states cannot retire, retired state still readable, agent proposes but never publishes |

The ADR of X3 gets its own planner-tier check (O2). Whole-suite gate once per increment DONE; `gate-pg` on touched directories.

## 5. Approvals needed (human gates)

| Item | Increment | Why |
|---|---|---|
| Operational table `idempotency_key` in `schema/core`; setting `idempotency.retention_days` in `platform.yaml` | X1 | schema and settings |
| OpenAPI baseline file and its refresh rule | X1 | release process |
| Setting for the project queue cap; event types `Agent.Stopped`, `Agent.Resumed` and their projection | X2 | schema and settings |
| Delegation ADR (core interface) | X3 | ADR |
| `ModuleSpec` hooks and `CommandSpec.meta` (core interface; addendum to the module-seam ADR) | X4 | core interface |
| Package kind field and `type`/`workflow` classification rules in `schema/modules/schemareg`; `ledger:` location; `locked_states` on `ModuleSpec`; fixture packages T04, T05 | X5 | schema, core interface, fixtures |
| Rule that an admin may not retire locked states | X5 | owner decision made 2026-11-12, scope of locks needs owner sign-off |

## 6. Token cost (est.)

No Phase 2 report gives a measured per-increment figure. Yardstick: `08-phase2-plan.md` §0.2 puts a process-v2
increment at 0.15 to 0.3 B input tokens; security reviews are capped at 450k each. All figures below are est.

| Increment | Items | Input est. | Output est. |
|---|---|---|---|
| X1 | 2 B, 9 H | 0.15 B | 1 M |
| X2 | 3 B, 6 H | 0.15 B | 1 M |
| X3 | 2 O, 1 H | 0.03 B (orchestrator and one planner pass) | 0.2 M |
| X4 | 5 B, 8 H | 0.3 B | 2 M |
| X5 | 5 B, 11 H | 0.3 B | 2 M |
| Security reviews (4) | | 1.8 M at the cap | — |
Total est.: about 0.95 B input. X4 and X5 drive cost; X5 needs a plan check before round 1.

## 7. Risks

1. Idempotency replay leaks text after a clearance change. Mitigation: store ids and the command hash only; re-read through the viewer filter (X1 demo 5).
2. Filing and cap refusals reveal that a scope or queue exists. Mitigation: one fixed text, filing check before the cap, walking tests (X2 T04).
3. A module hook loads code the reviewer did not see. Mitigation: hooks are references to installed packages only; harness runs on every surface (X4 S4).
4. Module tools or routes ship open to agents. Mitigation: closed by default, conformance test fails a new tool with no allow decision.
5. Registry collisions with in-flight increments (§3). Mitigation: owner per wave, scripted list regeneration, X4 starts after I6.
6. An admin retires or rewires a state code depends on. Mitigation: `locked_states`, classification refuses, impact digest lists records.
7. Core-interface drift: the dispatcher or catalog later disagrees with the hooks. Mitigation: X3 trace table, `meta` field, plan check on both X3 and X4.
8. Agents author many extensions and the approval queue becomes the limit. Mitigation: per-agent queue cap (X2), shadow mode (X3 build later), stats (B8, later).

## Plan check
