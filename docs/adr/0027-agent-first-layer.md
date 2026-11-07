# ADR-0027 — Agent-first layer: evidence in the intent, edits on accept, one generic propose tool

Status: proposed (2026-11-07, design only; nothing is built)
Date: 2026-11-07
Deciders: repository owner; orchestrator (acceptance, with an APPROVALS line). Touches the proposal contract, the MCP
tool contract and `schema/core/` (human gates, §25.5).
Brief sections: §8, §11.3, §18.12 (agents propose), §21.3. Related: ADR-0005, 0014, 0016, 0021, 0025 (proposed).
Spec: `docs/build-spec/specs/agent-first.md`. Phase 4 delegation (auto-apply) is not decided here.

## Context
The owner wants agents that work like colleagues: least privilege, a reason and evidence with every proposal, bulk
review by people, and (later) standing permission for small, safe changes. The spec checks each ask against the code.
Most of it needs no core change. Three things do:

- A proposal stores the whole command, so ADR-0025's intent (`why`, `next`, `toward`, `goal_ref`) already travels with
  it and reaches the hashed event on accept. Intent has no place to point at what the agent based its proposal on.
  ADR-0025 is proposed and not built, so its shape can still change at no cost.
- Accepting runs the stored command unchanged. A reviewer who wants to fix one field must reject, and the agent (or the
  person) files again. For a queue of fifty that is the main friction.
- The proposable path is not generic. A command becomes proposable through three hand-made parts: a `ProposableCommand`
  row, an MCP tool that builds the command, and an `mcp.<tool>` entry in the closed `MCP_ACTIONS` list. Wave 3 adds
  about 20 commands (requisitions, work orders, scaffold, toolcrib); about 20 wrappers is real work and drifts.

## Decision
1. **No change** to `Command`, the ledger envelope, the roles model or `ClientInterface`. Batch review is a loop over
   `accept_or_fail`; one proposal is one unit of work, and each decision is its own event (spec 3.3). A batch has no
   record of its own. Filing-time role checks, read scoping, caps, the review queue and the activity view are
   behaviour and read models on what exists; they need no ADR but are security-reviewed pieces.
2. **Evidence is a key of intent, not a new field.** ADR-0025 gains one optional key `evidence`: zero to 10 references,
   each `{record}` (a record or document id or key), `{revision}` or `{check_name, facts_hash}`. Same rules as the other
   references (ADR-0025 d.4, d.5): resolved to ids at write time, an unknown id and a hidden id fail the same way
   (`intent_reference_unknown`), a reference the viewer cannot read shows as "not available". It counts in the 4 000
   byte cap and in the event hash with the rest of the intent. This must land before the ADR-0025 validation piece.
3. **Edits on accept.** `Proposal.Accepted` gains an optional `edits`: a list of `{path, from, to}` (at most 20; `path`
   a field of the stored command; `actor`, `source`, `scope`, ids and `intent` are not editable). `accept_proposal`
   gains an optional `edits` argument. The edited command is validated like a new one and runs in the same unit of
   work. `Proposal.Created` is not touched, so the original stays as filed. `by` is the person, the source stays
   `mcp:<agent>`, and an edit of a field the person may not change is refused by the command's own access rules.
   Events without `edits` are exactly as before; an old reader ignores the key.
4. **One generic MCP tool.** `propose_command {command_type, command, summary}` for any `ProposableCommand` row with
   `agent_tool=True`. It checks the type against `proposable_tools()`, validates `command` with the row's own model, then
   calls the same `submit` as the named tools. The agent's actor, source and scope are set by the server, as now. The
   closed list gains one entry, `mcp.propose_command`. Named tools stay; new commands need a row and nothing else.
   The tool's schema is derived from the registered models, so a command cannot be offered that has no row.
5. **A rule for modules, enforced by one test.** Every command is either proposable (a row) or in
   `tests/tools/proposable_exclusions.toml` with a reason. Sign-off, approve, issue, void, tag green and configure
   commands are excluded: accepting the proposal would be the same act as the sign-off, so the person acts directly.
6. **Confidentiality.** `propose_command` runs under the lowest viewer like every tool. The queue shows only proposals
   the person can read, and edits cannot name a hidden record (answers as an unknown id). Evidence inherits d.2.
7. **Delegation is out of scope.** Auto-apply needs its own ADR and a human gate. This ADR keeps it possible: accept
   already takes a holder, a source and a cause, and `Proposal.Accepted` may later gain a `policy` key the same way
   it gains `edits`. Nothing for it is reserved or stored now.

## Consequences
- Contracts changed: ADR-0025's intent model (one key); `Proposal.Accepted` payload (one optional key, `schema/core/
  proposals.yaml`, a `schema` ticket with a named approver); `accept_proposal` (one optional argument); the MCP tool
  list (one tool) and `MCP_ACTIONS` (one entry). Generated event schema and catalog change for `Accepted` only.
- Existing events: unchanged. Existing data: no migration. A ledger with `edits` replays on code that predates them
  only if that code ignores unknown payload keys; the projector reads only the keys it knows, so the queue is fine.
- Wave 3 cost: the rule and test (2 H) and a row per command. With d.4 there are no wrappers; without it, one H each.
- Agents that file with the named tools keep working. `propose_command` is closed until someone adds its line to the
  authorizer, as every new tool is.
- Risk: a generic tool widens what an agent can ask for. It adds no authority: the row's access word, the person's
  access at accept, the guards and the viewer all still apply, and the exclusion test keeps sign-offs out.

## Effort
| Item | S (builder piece) | H (ticket) |
|---|---|---|
| `evidence` key (inside ADR-0025 validation piece) | 0.2 | 1 |
| `edits` on accept: schema, core function, API, CLI | 1 | 2 |
| `propose_command` tool, authorizer entry, walking test as five readers | 1 | 2 |
| Exclusion file and the one test | 0 | 1 |
| **Total** | **2.2** | **6** |
Landing: the `evidence` key and the exclusion test with wave 3; `edits` and `propose_command` with the Phase 3 review
queue, or at the start of wave 3 if the orchestrator approves d.4 (it saves about 20 H of wrappers).

## Alternatives considered
| Option | Why not |
|---|---|
| A new `evidence` field on `Proposal.Created` | A second reasoning carrier; people could not use it; the hash would not cover it |
| Links as evidence (`AddLink` beside each proposal) | Many events per proposal; a link is a fact about a record, not a pointer made by the actor; no attestation |
| Evidence as text in `why` | Not checked, not resolved, cannot be hidden by class |
| Edit by reject and re-file | Two proposals, two reviews, no tie between them for an auditor |
| Rewrite the stored command on edit | Rewrites history; events are immutable (AGENTS.md rule 3) |
| A batch record or batch id on every decision | A new event or payload key for something a filter already reproduces; decisions must stand alone |
| One MCP tool per command forever | About 20 wrappers in wave 3 and more later; each is a place to forget the closed-list entry or the access word |
| Let policy auto-apply now | ADR-0005: deciding who may write without a person is a human gate; no owner answers yet |
