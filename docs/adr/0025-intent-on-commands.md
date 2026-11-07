# ADR-0025 — Any command may carry an intent, and the intent is part of the hashed event

Status: proposed
Date: 2026-11-07
Deciders: repository owner (decision, paraphrased below); P2-I2 orchestrator (drafting)
Brief sections: §5.1 (hash chain), §11.3 and §18.12 (agents propose), §7.1 (links). Related: ADR-0016, ADR-0018

## Context
A ledger event says what happened, by whom and when. It does not say why, or what was meant to happen next. A person
or an agent who raises a constraint, assigns an owner and asks for an RFI is working toward one end ("WP-123
released"), but the three events look unrelated. The owner wants that reasoning recorded with the action, in the
same way for people and agents, with no planning engine behind it. More modules add commands in every increment, so
the field has to exist before the next ones are written.

What the code does today:
- `Command` (`tl_core/services/commands.py`) carries `actor`, `source`, `scope`, `correlation_id`, `causation_id`,
  `idempotency_key`. The ledger `append` takes the same names and stores them as columns of `events`.
- `ledger/hashing.py` `event_hash` covers `prev_hash`, `event_id`, stream id, stream version, event type, the
  canonical payload and `recorded_at`. **Actor, source, correlation id, causation id and `effective_at` are columns
  but are not hashed.** Only the payload is. The archive verifier recomputes the same hash (`archive/segments.py`
  `recomputed_hash`), and both adapters compute it on append.
- Agent proposals (`tl_core/proposals`) store the whole command as a dict in `Proposal.Created`, so a proposal
  already carries whatever the command carries.
- Payloads flow to the feed, webhooks, the lake and the event catalog. Columns do not; ADR-0016 filters by record.

## Decision
1. **Shape.** An optional `intent` on every command (field of `Command`), a small model, all parts optional:
   - `why`: plain text, at most 500 characters.
   - `next`: zero to 5 expected next actions, each either `{command, target}` (a command name and a record id or
     key) or `{text}` (at most 200 characters).
   - `toward`: an end state, `{target, state}` or `{target, condition}` (a record, and a workflow state or a
     short condition text of at most 200 characters), for example "start constraint on WP-123 cleared" or
     "WP-123 released".
   - `goal_ref`: an optional short code (at most 64 characters, lowercase letters, digits, `-` and `_`) that
     several actions use to name the same end state. There is no goal record yet; `goal_ref` is only a label.
   An empty or absent intent stores nothing. Total size of the canonical intent is capped at 4 000 bytes.
2. **No planning.** The platform never reads an intent to decide anything. Actions that give the same `toward`
   target and state, or the same `goal_ref`, form a chain a reader can follow in History and Trace. Nothing
   schedules, orders, retries or completes them.
3. **Where it is stored: a column of `events`, and inside the hash.** `intent` is a nullable JSON text column
   beside `payload`, carried by `NewEvent`, `Event` and `append`, and stored with every event the command appends.
   Metadata columns are not hashed today, and putting intent in the payload would send the reasoning to every
   payload reader (feed, webhooks, lake, catalog schemas) and force an `intent` field into every event schema. So
   the hash is extended instead: `event_hash` gains an optional last part, the canonical JSON of the intent, added
   only when an intent exists. Events with no intent hash exactly as before, so no existing chain, segment or
   restore changes. The two adapters and `recomputed_hash` use the same function, so they stay in step. The
   Parquet archive gains an `intent` column; a segment without it reads as empty. Adding a nullable column to
   `events` is a migration (SQLite and Postgres) and the hash change is ledger code: both are builder-tier work
   with a human gate, as the never-list requires.
4. **Validation, at the command boundary** (one function used by the API, the CLI client and the MCP tools):
   - Size limits as above; control characters and NUL refused (the existing NUL check covers it).
   - Every reference is checked like a link end: a `target` that is a key or id must resolve to a record the actor
     can see. An unknown id and a hidden id fail the same way, with the same fixed code `intent_reference_unknown`
     and message; the error never says which. A reference is stored as the record id (a key is resolved at write
     time) so a later key change does not break it.
   - `toward.state` must be a state of the target's workflow when the target has one; otherwise the condition text
     is used. A command name in `next` must be a registered command name; it is not checked for permission.
   - A bad intent refuses the whole command with a fixed code (`intent_invalid`). It never refuses silently.
5. **Confidentiality (ADR-0016).** An intent belongs to the events of its command, so it is visible exactly when
   the event is. The event is hidden when its stream or a link end is hidden, and its intent goes with it. Inside
   a visible event, a reference to a record the viewer cannot read is shown exactly as a missing one: the text
   "not available", no key, no title, no count that differs from the visible case. A `why` text is never
   filtered by its words. Webhook thin payloads and lake sync leave intent out for non-internal records, by
   the same rule as the payload.
6. **Actors.** An agent supplies an intent exactly as a person does. For an agent proposal the intent is part of
   the stored command; accepting it runs the command with the agent's intent unchanged, and the event's actor is
   the accepting human with the agent named as today, so a reader sees both. An intent never grants authority:
   access words, guards and permissions read the command, not the intent; `toward` does not check that the end
   state is allowed or reachable; a command does exactly what it did without it.
7. **Reads.** The API's event, history and trace routes return `intent` (null when none). Nothing else changes in
   a response. The generated event schema and catalog document the envelope field once, not per event type.

**Thin slice now:** the optional field on `Command`, `NewEvent`, `Event` and `append`; the column and the hash
extension; validation; acceptance by the API; storage; return on reads; the proposal path. It is empty everywhere
until a face fills it. **Soon (cheap tickets):** CLI `--why`, `--next`, `--toward`; an `intent` parameter on the
MCP write and propose tools; intent in TUI History and Trace. **Deferred:** goal records, a goal view, planning
agents, automatic intents.

## Consequences
- Contracts changed: `Command`, `NewEvent`, `Event`, `Ledger.append`, `event_hash` (one optional argument), the
  archive column list, the event read models. Event schemas are not touched.
- Chains made before this change verify without change; a chain with intents verifies only with a verifier that
  knows the extension. Downgrading code across the change on a ledger that holds intents is refused by the verifier.
- Every command in later increments gets the field for free; modules add no code to support it.
- Cost: the ledger and migration work is the single risky piece; the faces are small.

## Effort
| Item | Builder pieces | Tickets |
|---|---|---|
| Model, column, hash extension, both adapters, archive, migration, verifier test (human gate) | 1 | 0 |
| Validation, API envelope and read routes, proposal path, confidentiality walk | 1 | 1 |
| CLI flags, MCP parameter | 0 | 2 |
| TUI History and Trace display | 0 | 1 |
| **Thin slice** | **2** | **1** |
| **Soon** | **0** | **3** |

## Stubs for the knowledge graph
Intents are in the hashed event content, so a later graph (or an auditor) can attest the recorded reasoning:
`toward` and `goal_ref` are edges from an action to an end state, and `next` is an edge to an expected action.
They are stored as ids, not text, so they join to records without parsing. P2 builds no graph.

## Alternatives considered
| Option | Why not |
|---|---|
| Intent as a field in each payload | Every event schema changes; the reasoning reaches every payload reader |
| Unhashed metadata column only | A future chain would not attest the reasoning; it could be changed unnoticed |
| Put intent in a new event after the action | Two events per action; the hash does not tie them; races between them |
| Free-form text only | The chain by end state needs references that are checked like links |
| A goal record now | A planning engine in disguise; the owner deferred it |
