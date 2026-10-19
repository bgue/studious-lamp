# ADR-0018 — Record threads and dispatch

Status: accepted
Date: 2026-10-18
Deciders: P1-I7 workstream B supervisor (draft); orchestrator accepted under ADR-0008 decision 6 when WS-B reported done
Brief sections: §21.5, §10.6 sketch 13, §8 (permissions), §18.12 (agents propose), §7.1 (links)

## Context
P1-I7 adds optional message threads on records, with slash commands that dispatch work. The fanout plan
(`docs/tickets/P1-I7/FANOUT.md` D9, D10, D12) fixes the shape. This ADR records the choices the build had to make
inside it, and the places where it refines the plan.

## Decision
A thread is the ledger stream `thread:<record id>` (`core.Thread`, the record's scope), created by its first
message, so messages never bump the record's version. A slash command is parsed (pure), planned with the caller's
own access, previewed, and confirmed with a token; the confirmation runs exactly the previewed commands, in one unit
of work, with the server-set source `thread:<record id>` and correlation id `dispatch:<message id>`.

1. **Gate.** A thread exists for a record when `threads.enabled` is on and the record's type is in
   `threads.enabled_types` (an empty list lists no type: fail closed). Dispatch needs `threads.dispatch.enabled`
   and a caller whose access matches `threads.dispatch.roles` (empty: any signed-in person; `user` is any person,
   `document_controller` is `holds("controller")`, `admin` is `holds("admin")`). Roles are never data in a
   request: `holds(level)` comes from the client layer (ADR-0014 section 8). `threads.agents.can_dispatch = none`
   refuses `propose_dispatch`.
2. **Visibility is the record's.** Every thread read and write loads the record through
   `tl_core.threads.visibility.readable_record`; an unreadable record is the record route's 404. P1-I5's
   confidentiality filters plug in at that one function when the workstreams integrate.
3. **Messages never dispatch.** `PostThreadMessage` stores a body that starts with `/` as the text it is.
   Dispatch is `DispatchFromThread`, reached only through the preview and confirm routes (no entry in the generic
   command table) and, for agents, through a proposal. Edit and retract are the author's, and only for messages of
   kind `message`; dispatch, summary and reminder messages are history.
4. **Targets.** A `DispatchTarget` only builds commands. The planner sets `access` from the runner (a target
   cannot grant itself any), `permitted` from `holds`, refuses a command that names a server-set field, validates
   with the command's model, and dry-runs the plan in a unit of work it rolls back. Lookup is most specific
   first: `raise` takes the alias exactly (`record` now; `rfi` when P1-I6 registers it), `dispatch` the request type
   then `*`, the other verbs the record type then `*`. `assign`, `due`, `hold` and `release` have no target in
   Phase 1 and answer `dispatch_unavailable`. A module registers targets under the entry-point group
   `throughline.dispatch_targets`; a clash is refused and a target that fails to load is logged and skipped.
5. **Preview token.** SHA-256 of the canonical JSON of the record id, the record version, the command line and the
   planned commands (type and fields only). It leaves out `permitted`, `access`, summaries and the dry run's
   findings: who may run a plan and what the dry run said can differ between a preview and an acceptance without
   the plan changing. A reminder's time stays as typed (`+2h`) in the plan and is resolved when it runs, so the
   token does not depend on the clock. `expires_at` (ten minutes) is a courtesy check on the confirmation, not a
   secret: the token is a hash of public data, and the protection is that the plan is made again and must match.
6. **Results between commands.** The exact string `$result:<n>` in a planned command is replaced by the stream id
   item `n` produced. `/raise` uses it to link the record it creates. After any item that created a record the
   engine adds the `dispatched_from` link to the thread's record, link source `thread_dispatch`, with the message
   id as the note. This is the only use of `by_module=True` in the dispatch: it sets the system link source on a
   link whose from end is new.
7. **`/link` is the person's link.** The planned `AddLink` has the default link source (`manual`), not
   `thread_dispatch` as D2's table suggests: with `thread_dispatch` among the system link sources a person could not
   retract their own `/link`, and `by_module` would bypass the type's generic-command allow-list on the thread's
   record. The `dispatched_from` links the engine adds are the dispatch's own.
8. **Confirm.** `DispatchFromThread` (record id, text, token, optional `expires_at`) refuses an `agent:` actor, plans
   again as the caller, compares the token in constant time (`409 dispatch_stale`), refuses a plan with problems
   (`422 dispatch_refused`), then in one unit of work posts the message (kind `dispatch`), runs the commands and
   appends `Thread.Dispatched`. Any refusal rolls everything back, the message included.
9. **Agents.** `propose_dispatch(record, text)` plans the line as the agent (every command counts as permitted for
   the agent: the accepting person is held to their own access), refuses a plan with problems, and records a
   proposal of `DispatchFromThread` with the plan's token. Accepting it (`proposals.accept_proposal`, given the
   accepting person's `holds` and the command runner) plans the stored line again as that person: every planned
   command must be permitted to them and the token must match, or the proposal fails (`Proposal.Failed`). This
   extends `proposals._require_access` to a command whose access depends on its content. An agent's direct
   preview or confirm routes are closed (`thread.preview` and `command.DispatchFromThread` are not agent
   actions); its thread actions are `thread.read` and the three message commands.
10. **`/summarise` is a count, not a model** (ADR-0008 decision 8): the text is a pure function of the thread's
    last messages, posted by the caller on confirm. `/remind` queues a `thread.reminder` job whose id is the
    dispatch message's id; when it runs the job reads that message, parses its line again and posts a `reminder`
    message as `svc:threads`. `/notify` records mentions only.
11. **Webhooks.** `Thread.MessagePosted` and `Thread.Dispatched` are delivered; edits and retractions are in the
    catalog and the ledger but the dispatcher does not deliver them. A thread event's outbox subject is its record.
    Thread messages are transparent to the activity feed; the commands a dispatch runs are not.
12. **Known limit.** Dispatched workflow transitions cannot satisfy a `roles` guard until the workflow layer
    derives roles from the principal (P1-SEC1): the dispatch never passes caller-chosen roles. The preview shows
    the failed guard.
13. **The runner is WS-A's `command_runner()` (merged).** A dispatch runs each command through it, so each
    command runs only if its own actor holds the access the table declares, read from the actor's account in the
    same unit of work. A person needs an account (a dev ledger: `tl admin user add dev`); the CLI and the
    embedded TUI read `holds` from the same account, with no dev-file exception, so a preview never says "ok" for
    a command the runner then refuses. `/dispatch` plans an `InvokeAction`; the action's own `access` decides.
14. **An agent never previews, confirms or runs anything.** `ThreadPlanner.preview` and `DispatchFromThread` refuse
    every actor that is not `user:`. An agent's plan (the token of a proposal) is made with no dry run, so nothing
    runs as the agent even rolled back. A planned command never carries `actor_roles` or `accept_risk` (nor the
    server-set fields): the planner refuses it as `reserved_field`.
15. **A token runs once.** The token also hashes the number of dispatches the thread has run, so the dispatch's own
    message spends it: a replay with the same token is `dispatch_stale`. (A dispatch does not change the record's
    version, so without this a side-effecting plan could run again with the same token.) A message that is not a
    dispatch does not change the token, so chatting between a preview and its confirmation does not spoil it. The
    expiry a client sends is a time (ISO 8601; a naive one is UTC) no later than the preview's lifetime.
16. **Effects and acceptance need an account.** `/summarise` and `/remind` are not table commands, so the engine
    asks `require_access` for the actor before running one. `accept_proposal` passes the caller's `holds` through
    unchanged and refuses to run a dispatch without one; a person with no account leaves the proposal pending.
    The `dispatched_from` link is made with `system_source="thread_dispatch"`, not `by_module`: the narrow form
    lifts only the reserved link source and leaves a module's `AddLink` allow-list in force.
17. **A switched-off thread is closed.** It reads as empty, and posting, editing, retracting, dispatching and the
    delivery of a waiting reminder are refused or dropped. Reminders are capped (`threads.reminders.max_pending`,
    per thread and per person) and the server has no scheduler for the job kind (see the runbook).

## Consequences
- Contracts changed: none of the frozen two. New: `PostThreadMessage`, `EditThreadMessage`,
  `RetractThreadMessage` in the API command table (user access, agents direct); `DispatchFromThread` outside it;
  settings `threads.*`; `propose_dispatch` in `PROPOSABLE_TOOLS`; `thread.read`, the three message commands in
  `AGENT_ACTIONS`; `mcp.read_thread`, `mcp.post_thread_message`, `mcp.propose_dispatch` in `MCP_ACTIONS`;
  `proposals.accept_proposal`, `accept_or_fail`, `precheck` and `submit` take an optional `runner`.
- Schema: `schema/core/threads.yaml` (three tables, four events, `ThreadMessage`), five settings. Additive.
- Gates affected: the security review of FANOUT D18 (the parser, the planner and the token, the confirm path, the MCP
  tools and the proposal, the webhooks, thread visibility).

## Alternatives considered
| Option | Why not |
|---|---|
| Messages as feed posts with a record filter | The feed is a broadcast surface; threads must not appear in it, and a message must not bump the record |
| Thread events on the record's stream | They would bump the record's version and make every message a concurrency conflict for the record |
| A server-side preview store keyed by a random token | Needs a table and a sweep; a hash of the plan, re-planned at confirm, needs neither and cannot confirm a stale plan |
| Dispatch as a generic `/commands/DispatchFromThread` route | The generic route has no `holds`; the caller's access would have to come from the request |
| Role names in the request, checked against `threads.dispatch.roles` | Roles are the principal's, never request data |
| `thread_dispatch` as the source of `/link` | A person could not retract their own link; `by_module` would skip the module allow-list |
| Dry-running inside the caller's unit of work with a savepoint | Appended events would be published at the outer commit |
