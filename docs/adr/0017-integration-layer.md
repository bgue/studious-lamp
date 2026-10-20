# ADR-0017 — Integration layer: actions, rules, inbound endpoints, enrichment

Status: accepted (by the orchestrator after two security passes and a re-check, 2026-10-19)
Date: 2026-10-17
Deciders: orchestrator (fanout plan `docs/tickets/P1-I7/FANOUT.md`, decisions D1 to D20); WS-A supervisor drafted this record
Brief sections: §18.5 (inbound), §18.7 (actions), §18.8 (rules), §18.9 (enrichment), §18.13 (governance, kill switch), §19.2, §19.3, ADR-0008 decisions 6 and 8, ADR-0010 second addendum, ADR-0011, ADR-0013, ADR-0014

## Context
P1-I7 lets external systems, rules and enrichers act on the ledger through one guarded seam. Four engines share it: actions (§18.7), rules (§18.8), inbound endpoints (§18.5) and enrichment (§18.9). Each runs as a declared service actor, is bounded per event and per request, and writes only through the existing commands. The shapes are frozen in `tl_core/integration/contract.py`; the fanout plan fixed the design. This record keeps the decisions that change a permission, an event shape, a table or an existing rule, so that a later reader finds them in one place.

## Decision

### 1. Records are streams of their own
`IntegrationApp`, `ActionDefinition`, `ActionInvocation`, `Rule`, `InboundEndpoint`, `Enricher` and `EnrichmentValue` are LinkML classes in `schema/core/integration.yaml`, each a ledger stream with its own `cur_*` projection (as `core.WebhookSubscription`). They are configuration and activity, not project records: no `cur_core_record` row, no psets, no workflow. A test compares the slot names with the contract models. Inbound delivery bookkeeping (`Inbound.*`) is on a stream per delivery (`core.InboundDelivery`) and has no projection; its state is the operational row `int_delivery`.

### 2. Operational tables (`schema/core/integration_ops.yaml`)
`int_secret`, `int_replay`, `int_delivery`, `int_counter`, `rule_cursor`, `rule_firing`, `enrich_cursor`. They are not projections: a rebuild never clears them, and the archive, the lake and webhooks never read them. A restored ledger re-issues its secrets. `int_secret.secret` is a credential: it is in no event, log, error text or API answer, and the dev query tools refuse the table.

### 3. Events
Thirty-three event types (`tl_core.integration.streams`). Webhooks deliver `Action.Requested`, `Action.Completed`, `Action.Failed`, `Enrichment.Proposed` and `Enrichment.Accepted`. The configuration events and the inbound bookkeeping are in the catalog and the ledger but the webhook dispatcher never delivers them (`SubscriptionRow.receives`).

### 4. Reserved identifiers
The sources `inbound:`, `rule:`, `enricher:`, `action:`, `thread:` and the correlation and causation prefixes `inbound:`, `rule:`, `action:`, `dispatch:` are the server's. `tl_core.services.reserved` refuses them from every client command, upload and proposal (the body model `request_model` applies it to every route). `thread_dispatch` joins the system link sources (an amendment to ADR-0010 second addendum item 3).

Automation does not use `by_module`: that keyword also lifts the module allow-list, the reserved `supersedes` relation and the pipeline-owned targets. `handle_add_link` and `handle_suggest_link` take a second Python-only keyword, `system_source`, that lets the command carry that one system link source and lifts nothing else.

### 5. Service actors and access
Rules, endpoints, enrichers and action executors act as `svc:<kind>-<slug>`. A rule, endpoint or enricher declares `access` as `user` or `controller`; automation never runs an `admin` command. A command automation runs must be in `AUTOMATION_COMMANDS`, in the record's own list, covered by the declared access, and pass the handler's own allow-lists and guards. A service actor is cleared for no restricted confidentiality class (wired when the confidentiality filters of P1-I5 are on the trunk).

### 6. Rules in propose mode
A rule in `propose` mode proposes as `svc:rule-<slug>` (`proposals.propose_for_rule`). The proposal's `tool` is `rule`, which is no MCP tool; no agent can name it. The stored command carries the source `rule:<slug>`. Accepting needs a person and the access of the command (ADR-0014 section 8); the command then runs as that person with that source. A rule has the same daily proposal budget as an agent. `PROPOSABLE_TOOLS` is unchanged.

### 7. The command runner
`tl_api.commands.command_runner()` builds a `CommandRunner` from `COMMANDS`; `tl_core` never imports `tl_api`. A command whose access is `company` counts as `admin` for automation, so it can never run.

`run(uow, command)` also checks the access the table declares against what **the command's own actor holds**, resolved from the ledger in the same unit of work (`tl_core.integration.actor_access`), and fails closed (`CommandAccessError`):
- a person holds what their active account's roles give (`admin`, `controller` for a document controller, else `user`); the actor must be exactly `user:<username>` of the account (no look-alike spelling), and an account with no role holds nothing;
- a service actor holds the access declared on the rule, endpoint or enricher that owns it, **only while that owner is switched on and its app is on**; the actor name is unique to its owner (a unique index on `service_actor` in the three tables), so a name with more than one owner holds nothing;
- an `agent:` actor runs only the commands an agent may run directly (`AGENT_DIRECT_COMMANDS`: the feed commands); everything else it proposes;
- `svc:action-*`, `system:*` and any unknown name hold nothing.
A handler that takes `holds` (`InvokeAction`) gets it from the same resolved access. The inbound service actor is `svc:inbound-<app>.<endpoint>`: a name is a slug without a dot, so two paths never share an actor (the first form joined with `-` and let app `a` + endpoint `b-c` borrow app `a-b` + endpoint `c`). Rule and enricher actors are named by their one key or name and were already injective.

### 7a. What automation may and may not put in a command
`plan_command` refuses `actor_roles` and `accept_risk` by name (as the propose path does): external input never supplies the roles a guard sees or acknowledges a risk. A rule's `AddLink` or `SuggestLink` proposal carries the link source `rule`; accepting it applies that one system source server-side (`system_source`), only for a proposal a rule made. The rules engine is never offered account events or the layer's own bookkeeping events (`INTEGRATION_INTERNAL_EVENT_TYPES`), the set the webhook dispatcher skips, and a firing re-reads the rule inside its unit of work, so switching a rule off stops it at the next event.

### 7b. The `hashtags` of the outbox
`Feed.Posted` and `Feed.Edited` carry `tags` (kind and text), not a `hashtags` list, so a `hashtags` filter never matched a real post. The outbox now reads both: every tag that is not a mention is a hashtag. Rule `when` filters need it (D7); the change also makes existing webhook subscriptions with a `hashtags` filter match real posts, which is what their authors meant. Pinned by `test_existing_webhook_filters_keep_their_meaning_and_hashtags_now_match_real_posts`.

### 7c. Mapping runtime
The server never parses an expression. `check` and `evaluate` hand it to the child of the ADR-0014 envelope, which parses it, walks its tree against the profile (`inbound/profile.py`: at most 2000 characters, 500 nodes, depth 60, an allow-list of node types and function names) and runs it. An authoring check is cached by the hash of the expression.

### 7d. Found after the second review and by the demo
- **A record version is read when the command runs.** Automation is last-writer-wins: that is acceptable for `SetPsetValues` (it merges keys) and for a workflow transition (its guards run on the current state). `UpdateRecord` replaces the whole psets object, so automation may change only the title and description with it (`psets_not_automated`); psets are set with `SetPsetValues`. A proposal a rule made reads the version when a person accepts it, for the same reason. `SetPsetValues`, `UpdateRecord` and a workflow transition need `expected_version`; a payload or a rule step cannot know it. `plan_command` refuses a step that names one (`expected_version`) and shows none in the preview; `run_automation_command` reads the stream version in the unit of work (so a second command on the same record in one delivery sees the first). The append still checks it.
- **The enrichment and source layers are written by one path.** `CreateRecord` and `UpdateRecord` refuse a pset under `enrich` or `src` (an update may send the record's own values back unchanged), as `SetPsetValues` always did. The enricher pipeline writes only through `layer.py`, and only while its service actor still holds access (`held_access`: its switch, its app and its owner are on); the dispatcher asks again per event, as the rules worker does.
- **Shadow values are the admin's.** The registry reads, the API and `tl enrich` leave out `acceptance_state = shadow` unless the caller is an admin. The event that carries the value (`Enrichment.Proposed` with state `shadow`) is hidden by the change-feed filter (`/events`, `/stream`, `tl events`; `show_shadow` only for an admin), never sent by a webhook, and makes no feed card.
- **Dry-run is an emergency stop.** The inbound worker reads the endpoint's mode when it applies a delivery: an endpoint put back to dry-run applies nothing, whatever mode the delivery was accepted under.
- **A message holds nothing of a payload.** A failed key lookup names the key's length; an unknown argument is counted, not named; a validation error names the model's field and nothing below it. A replayed message is refused before its body is stored.
- **A deadline covers the whole exchange.** The webhook transport has a watchdog that closes the client when `timeout_s` is spent, header phase included.
- **Gates fail closed.** `admin_gate` allows a missing session only on a ledger file in a dev, test or ci setup. Server-set fields (`SERVER_SET_FIELDS`) in a rule file or a screen command are refused.
- Accepted trade-offs, documented in the runbook: the pre-authentication rate counters, the proxy-header lock-out and the missing read deadline of the body.

### 7e. After trunk 61717ad (ADR-0016 confidentiality, P1-SEC1 roles)
- **Automation holds no workflow roles.** `TransitionWorkflow` takes its roles as an argument, derived by `workflow_roles(principal)` (P1-SEC1); a body that names roles gets 422. A rule, a mapping, an enricher, an action and a thread dispatch that transitions a workflow runs as a service actor, which has no account roles (`workflow_roles_of(conn, actor)` is empty for `svc:`), so a transition guarded by a role fails closed (`workflow_guard_failed`). That is the intended behaviour: a rule cannot move a workflow past a role gate, and a person who wants the move accepts a proposal (the transition then runs with that person's roles). A rule's proposal carries no roles. The reserved source prefix `svc:` joins the others.
- **One rule for what automation reads: the lowest viewer.** `viewer_of(conn, actor)` gives every service actor (`svc:`) the viewer of level 0 (`internal`), named by no clearance row, whatever access it declares (`user` or `controller`) and whether or not it is switched on. This matches section 5 (a service actor never holds more than `controller` to run commands, and no person's clearance) and the thin policy of the webhooks. What an actor may *run* (`held_access`) and what it may *read* are separate questions; a controller-access rule may run controller commands on internal records and still cannot read a restricted one. Controller-level automation over restricted records is a Phase 2 question (it needs its own approval, audit and clearance model). A person is the viewer `viewer_for_actor` says.
- **Where it applies.** The rules worker (`_fire`) and the dry run, the enrichment dispatcher, the enricher pipeline and `RunEnricher`, the inbound worker's mapping (including `RecordKeyLookup`), the action target resolution, the integration registry, and the thread service's reminders read under that viewer. An event whose subject (or whose stream, or whose payload, for the scanned stream types) the actor cannot read is passed over and counted (`RuleStats.hidden`, `EnrichStats.hidden`), never replayed: a rule or an enricher neither reads nor acts on a restricted or privileged record, and `${subject_key}` and `${subject_title}` of such a record never reach a post or a proposal. A mapped key that names a record the endpoint's actor cannot read is `key_not_found`, as for a missing one.
- **A job is not a free pass.** The job runner wraps a whole job in `system_view` (jobs are system work), so a job kind that calls a shared parser or resolver narrows to its actor's viewer around that call: a reminder posts its note as the person who set it (`#KEY` tags resolve as that person); an action's `post_to_feed` posts as the action's service actor. A reminder on a record that is not `internal` (the thread service is a service actor), or one the setter can no longer read, ends with the code `record_not_readable` and posts nothing; it is not retried.
- **The change feed hides what the record hides.** `hidden_event_streams` also covers enrichment values and action invocations (by their target) and record threads (`core.Thread`, `thread:<record_id>`). `core.Thread` is also a scanned stream type: a message or dispatch card whose payload names a record the reader cannot read (`record_refs`) is not given to that reader on `/events`, `/stream`, `tl events` or a webhook, and `read_thread` drops such references and cards. The shadow filter and the confidentiality filter compose: an event must pass both. The registry lists only the enrichment values and invocations whose targets the viewer can read (filtered in SQL, before the limit).

### 8. Kill switch
`integration.kill_switch` (platform and company, lockable). When on: inbound answers the fixed 404; the rules worker and the enrichment dispatcher record the events they pass over as `killed` and do not replay them; action jobs fail with `killed` and are not retried. Every engine reads it per batch or per delivery, never once at start.

### 9. Dependencies
`jsonata-python==0.7.0` (Apache-2.0, no dependencies) for the mapping runtime, and PyJWT (MIT) as a direct dependency of the package that verifies JWTs. The licence gate passes; neither is copyleft or costs money. Fallback if the security review rejects the library: a declarative mapping subset behind the same `MappingRuntime` protocol, decided by the orchestrator.

## Consequences
- Contracts changed: none of the frozen contract; the addenda above (link source, `system_source`, rule proposer, reserved prefixes) are additive to existing services.
- Tickets re-issued: none.
- Gates affected: pinned lists (command table, event catalog, DDL file lists, settings keys, webhook scenario) grow with each increment piece; `JobKind.run`'s "no network" note is amended for the kind `action` only (network only through the egress-checked transport).

## Alternatives considered
| Option | Why not |
|---|---|
| Use `by_module=True` for automation links | It also skips the module allow-list and guards; a rule could link from a closed module record. |
| Make rule and inbound sources free text | A client could pose as automation, and loop protection reads the depth from the source. |
| Run rules inside the writing transaction | A rule would block or fail a person's write; the worker follows the ledger instead. |
| One stream for all inbound deliveries | Concurrent deliveries would contend on one stream version. |
