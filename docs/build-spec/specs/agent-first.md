# Agent-first construction management (design note)

Status: proposed, design only (2026-11-07). Nothing here is built. Related: ADR-0005, 0014, 0016, 0021, 0025
(proposed), 0026 (proposed); ADR-0027 (proposed) holds the core changes. Brief: §8, §11.3, §18.12, §21.3.
DEFERRED row "Agent-first layer" (Phase 3 to 4). Owner limits: build deferred; waves 2 and 3 not delayed; schema or
core-interface change is an orchestrator gate with an APPROVALS line; existing events never change; no migration.

## 1. In one line
An agent reads what its account may read and files proposals with reasons; people decide, in bulk if they wish.
## 2. What the code does today (checked on trunk)
| Fact | Where |
|---|---|
| Agent accounts exist (`agent:<name>`, no password, never admin); a token is checked on every MCP call | ADR-0009, `tl_mcp/identity.py` |
| Module roles per project and module; agents may hold only `viewer` or `user`, never `superuser` | `roles-mvp.md` s.2 (role table), ADR-0021; `auth/module_grants.py` |
| An agent runs only feed and thread-message commands directly; everything else is a proposal | `tl_api/auth.py` `AGENT_DIRECT_COMMANDS` |
| A proposal is its own ledger stream: Created, then one of Accepted, Rejected, Failed | `schema/core/proposals.yaml`, `services/proposals.py` |
| Accepting runs the stored command as the person: actor = person, source `mcp:<agent>`, cause = Created event; the person's module access is checked; a refusal (stale version, guard) rolls back and writes Failed | `accept_proposal`, `accept_or_fail` |
| `cur_proposals` keeps agent, status, created and decided time, deciding person, reason; daily budget per agent (default 500) is the setting `ai.agents.daily_proposals` | `projection/proposals.py` |
| An agent reads `internal` records only; a hidden record answers as missing; `/proposals` hides one that names a record the viewer cannot read | ADR-0016 |
| The proposable path is **not generic**: a module lists a `ProposableCommand` row, a hand-written MCP tool wraps it, and `mcp.<tool>` is added to the closed `MCP_ACTIONS` list. Eight rows exist in five modules (awp 1, correspondence 2, documents 3, materials 1, schedule 1; one is rule-only) | `modules.py`, `tl_mcp/identity.py` |

## 3. The six asks
| # | Ask | Have | Gap | Build |
|---|---|---|---|---|
| 3.1 | Agent accounts, module roles | grants, role table, `agent_roles`, token per call | agent's own role is not checked when it files; agent reads are not scoped by project | check at filing; read scoping with the read word |
| 3.2 | Rationale and evidence | `summary`; command stored whole; intent (ADR-0025, proposed) | no evidence refs; review shows `summary` only | one `evidence` key in intent; show it in review |
| 3.3 | Batch review | list, accept, reject one at a time (API, CLI) | no batch, no edit, no TUI queue | `accept_many`, edit-then-accept, queue screen |
| 3.4 | Delegation, escalation | settings layers; budget; rule `propose` mode | no auto-apply by design (ADR-0005); no thresholds | policies as settings data (Phase 4, own ADR) |
| 3.5 | Proposable path for wave 3 | row mechanism; tool wrappers | three places to touch per command; no check that a command was considered | module-standard line; one test; generic tool (ADR-0027) |
| 3.6 | Activity and acceptance view | all the data in `cur_proposals` | not exposed (view has no created or decided time); no screen | read query, TUI log, CLI |

### 3.1 Accounts and roles (least privilege)
- One agent account per job (`agent:triage`). An admin grants module roles with `GrantModuleRole` (project, module or
  `*`, role). No grant means no role. An agent never derives roles from an account role.
- An agent may hold `viewer` or `user` only. `superuser` is not in `agent_roles`, so its words (`controller` acts:
  approve, sign off, issue, void, configure) can never be granted. This keeps "never more than a person in the same
  role" true by table. Pin it with one test: no word an agent can hold is outside the `user` role's words.
- Access words apply twice. (a) **At filing** the agent needs the command's word for that module and project. Today
  this is not checked (`precheck` calls the handler directly), so an ungranted agent can file anywhere. Build: call
  `require_command_access` for the agent in `submit`. (b) **At accepting** the person needs the word (have).
- Reads: confidentiality is by class, not project (ADR-0016 limit) and the `read` word is not enforced (roles-mvp s.7),
  so an agent reads `internal` records of any project. Build read scoping for people and agents together. Hidden = missing.
  Kill switches (have): revoke the token, disable the account, budget 0.

### 3.2 Rationale and evidence
- Reuse intent (ADR-0025, same shape for people and agents): `why` (500 chars), `next`, `toward`, `goal_ref`. The
  proposal already stores the whole command, so the intent travels with it and lands in the hashed event on accept,
  unchanged. No new proposal field.
- Evidence: add one optional key `evidence` to intent, up to 10 references: a record or document id, a revision, or a
  check result (`{check_name, facts_hash}` as constraints use). Validated like link ends: it must resolve for the actor;
  unknown and hidden fail the same way. A viewer who cannot read a referenced record sees "not available". This
  amends ADR-0025 **before** it is built, when it costs almost nothing (ADR-0027 d.2).
- The reviewer sees the change (field, from, to) computed from the stored command and the record now, then "agent says:
  why" and the evidence resolved from the records. `summary` stays for lists. An intent grants no authority.

### 3.3 Batch review queue
| Question | Answer |
|---|---|
| What is one unit | One proposal: its command and its Accepted event commit together (have). A batch is an ordered loop by `seq` over units, not one big transaction |
| A failure in a batch | That proposal writes Failed in a fresh unit and the loop goes on (option `stop_on_failure`). Reject many writes one reason on every Rejected event. The result lists every item |
| Edit then accept | The person changes named fields of the stored command, the command is validated again, and the same unit runs it. `Proposal.Accepted` records the edits (field, from, to). The original Created event stays as filed (ADR-0027 d.3) |
| What the ledger records | Per proposal: Created (agent), the command's events (actor = person, source `mcp:<agent>`, cause = Created), Accepted or Rejected or Failed (by = person, source = the surface). No batch record: each decision stands alone and an auditor reads it without the batch |
| Access, confidentiality | Each item uses the person's own module access; one they may not decide stays pending, listed as "needs another role". Only readable proposals appear; counts equal rows shown |
| Stale | The queue marks "record changed since filed" by comparing the command's `expected_version` with the stream now. It sorts these into their own group; accepting one still ends in Failed, as today |
Surfaces: API `accept_many`/`reject_many`, CLI `tl proposal accept --agent X`, a TUI queue grouped by agent, command and record. No logic in the TUI.

### 3.4 Delegation and escalation (Phase 4, own ADR and human gate)
ADR-0005 says deciding who may write without a person is a human gate. So this is a sketch, not a promise.
- **Default is queue**, as today. An agent in a policy still sees only what its account sees.
- **A policy is data**, a settings key (company or project layer) so it is versioned by `ChangeSetting` events and a
  person accepts the risk (`dangerous`). A row: agent, module, command type, mode (`queue` or `auto`), thresholds
  (count per day, a field limit such as quantity or amount, allowed target states), `escalate_to` (a module role),
  and `delegator` (a named person who holds the word). No policy code runs outside the existing accept path.
- **Auto means "accepted on a standing instruction"**: the accept runs as the delegator, source `mcp:<agent>`, and
  `Proposal.Accepted` names the policy and its version. Guards, access words, `expected_version` and the viewer all
  run. A refusal leaves the proposal pending and escalated, not failed. If the delegator loses the word, auto stops.
- **A fixed deny list in code, not data**: sign-off, approve, issue, void, configure, class and clearance changes,
  role grants, settings. Policy can only move a command toward the queue relative to this list.
- **Escalation**: over a threshold, or pending too long, a proposal shows in the named role's queue as "escalated".
  A flag in the read model, not a new event.

### 3.5 The proposable path for every new wave 3 command
Verified: **not generic**. Per command, three things must exist:
1. a `ProposableCommand(tool, model, handler, access)` row in the module's `PROPOSABLE`;
2. a hand-written MCP tool that builds the command (`write_tools.py` style);
3. `mcp.<tool>` in the closed `MCP_ACTIONS` list (a missing entry is closed by design; a test fails on a mismatch).
Rule for module standard (one line, in each module README and in the wave 3 tickets): *every command is either
proposable (a row, `expected_version` where it changes an existing record) or listed in the exclusion file with a
reason.* Excluded by default: sign-off, approve, issue, void, tag green, inspect pass, release, configure. An agent
that wants those done raises a constraint or posts to a thread (both proposable or direct), and the approver acts.
The test (one H ticket): each name in `command_index()` is in `module_proposables()` or in `tests/tools/proposable_exclusions.toml`
with a reason; both or neither fails. The generic `propose_command` tool (ADR-0027 d.4) removes step 2 (about 20 wrappers in
wave 3). Without it each proposable wave 3 command costs one extra H ticket.

### 3.6 Agent activity and acceptance view
- Per agent and period: filed, accepted, rejected, failed, pending, accept rate, median and slowest time to
  decision, daily budget used. Drill to the proposals. A second table: by command type.
- Data is in `cur_proposals` (have); `ProposalView` lacks created and decided time (add, read-only). TUI log first (tui-layout skill), then `tl proposal stats`, web later.
- No hidden counts: figures cover proposals the viewer can read and the screen says so. No ranking or score.

## 4. Risks
| Risk | What stops it | Gap / build |
|---|---|---|
| Prompt injection through record text an agent reads | Agent only proposes; reads are `internal` only; review shows the change from the stored command, not agent prose; evidence resolved by the server; auto-apply deny list | Label agent text "agent says" and show plain text only; wave 3 text fields have the same limits as today |
| Runaway volume | Daily budget, token revoke, budget 0 | Add pending cap per agent and one pending proposal per same command and record (duplicate refused, fixed code); an hourly cap |
| Stale proposals | `expected_version` re-checked on accept, Failed on refusal | "Changed since filed" flag; wave 3 commands on existing records take `expected_version`; pending-too-long is flagged, never auto-closed |
| Policy leaks authority | Runs as a named delegator; deny list in code | Phase 4 ADR, walking test as five reader kinds (AGENTS.md) |

## 5. Phasing
| When | What | Why then |
|---|---|---|
| **Now (cheap stubs)** | Ask for the `evidence` key in the ADR-0025 validation piece. Nothing else is stored or coded | Cheap before the intent field exists; costs a schema re-gate after |
| **Wave 3** | The one-line module standard; the exclusion file and the one test; proposal rows for the commands that create or request; `expected_version` on commands that edit. Optional: generic tool (ADR-0027 d.4) if approved | The rule is free while commands are written; retrofitting 40 commands is not |
| **Phase 3** | Filing-time role check; read scoping with the read word; `accept_many`, edit-then-accept, queue screen; activity view; pending and hourly caps | Needs the role table in use and real agents |
| **Phase 4** | Policies, auto-apply, escalation (own ADR, human gate); web queue and web activity | Needs owner policy answers and a track record from the queue |

## 6. Effort (S = builder piece, H = ticket)
| Item | S | H |
|---|---|---|
| `evidence` key in intent (inside ADR-0025 validation piece) | 0.2 | 1 |
| Wave 3 rule line, exclusion file, one test | 0 | 2 |
| Per proposable wave 3 command: row plus wrapper (no generic tool) | 0 | 1 each |
| Generic `propose_command` tool, with test as an agent | 1 | 2 |
| Filing-time role check, read scoping (security) | 1 | 2 |
| `accept_many`, `reject_many`, edit-then-accept (schema gate), API, CLI | 1.5 | 3 |
| Queue screen with stale flag and grouping | 0 | 3 |
| Activity view: query, TUI log, CLI | 0.5 | 3 |
| Caps (pending, hourly, duplicate) | 0.5 | 1 |
| Policies, auto-apply, escalation, walking tests | 2 | 4 |
| **Totals: wave 3 (generic tool approved) 1.2 S, 5 H; Phase 3 3.5 S, 12 H; Phase 4 2 S, 4 H** | | |

## 7. Core interfaces touched
Yes, three, all additive and optional (ADR-0027): intent `evidence` key; `Proposal.Accepted` optional `edits` (and an `edits`
argument on `accept_proposal`); one MCP tool `propose_command`. Not touched: `Command`, ledger envelope, roles model,
`ClientInterface`. Phase 4 policies touch the accept path and need their own ADR. No event changes, no migration.

## 8. Open questions
1. May ADR-0025 gain `evidence` before its validation piece (recommended yes)? Generic `propose_command` in wave 3?
2. Refuse an ungranted agent at filing, or only warn until Phase 3? (Recommended refuse, Phase 3.)
3. Who may see another agent's activity: any reader of the records, or controllers only?
