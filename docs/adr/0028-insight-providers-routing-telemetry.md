# ADR-0028 — Insight providers, a router, insights as a derived projection, mining, and telemetry of need

Status: proposed (2026-11-07, design only; the plan check is run by the orchestrator, see the end)
Date: 2026-11-07. Deciders: repository owner (request of 2026-11-07, part B); orchestrator (acceptance, with APPROVALS lines)
Brief sections: §5.1, §8, §11.3, §18.12, §22. Related: ADR-0010, 0014, 0016, 0024, 0025, 0026, 0027
Spec: `docs/build-spec/specs/insights-and-activity.md`. Only the telemetry stub (section 7) is built now.

## Context
The owner wants an Insights tab on every record: checks, suggestions, analyses and a record-scoped Ask. That needs a way
to add providers, route each request to the right kind, store results, mine data, and record what nobody could answer.
Paid calls are a spend decision and a stop condition.

What the code has today:
| Need | Have | Gap |
|---|---|---|
| Plug-ins by entry point | `throughline.readiness_checks` (loader refuses a bad or repeated name), `.enrichers`, `.action_jobs`, `.extractors` | No insight group |
| Event subscription | `outbox_events` (a projection, one row per event, indexed `subject_id`), `rule_cursor` (a consumer's position), the rules engine and webhooks read it | No insight reader |
| Background work | `job_queue` (ADR-0014), kinds `awp.readiness`, `action`, `inbound.map`, derivation | No insight kinds |
| Viewer filter | `tl_core.confidentiality` (classes `internal`, `restricted`, `privileged`; lowest clearance by default) | Nothing for derived data |
| Operational tables outside the hashed ledger | `auth_audit` (90 days), `wh_*`, `job_queue`, `rule_cursor`: generated DDL from `schema/core/*.yaml`, both dialects | No telemetry table |

## Decision
1. **Providers are plug-ins.** Entry-point group `throughline.insight_providers`; each entry returns an object with a
   declaration, loaded like `readiness/registry.py` (a bad plug-in, a repeated name or more than 32 raises a load error,
   never a silent gap; the registry takes injected entry points for tests). Declaration:
   `name`, `version`; `kind` (`check`, `suggestion`, `analysis`, `ask`); `triggers` (`event:<EventType>`,
   `screen:<name>`, `request`); `reads` (record types); `cost` (`free` in-process rules, `local` a model on the
   server's own machine, `paid`); `speed` (`instant`, `seconds`, `queued`); `max_class` (highest class it may see).
   Defaults: a check sees `privileged` (in-process, under the viewer); a local provider `restricted`; a paid provider
   `internal`, and nothing raises that without an owner decision (roadmap question 2).
2. **The router picks one provider per request** by kind and policy, in this order:
   | Condition | Result |
   |---|---|
   | Provider `max_class` is below a source record's class | The record is left out of what the provider is given, as a hidden record is; never "refused" with a reason that names it |
   | Request touches `restricted` or `privileged` data | `free` or `local` providers only |
   | Node is an offline replica | `free` and `local` only; `analysis` and `ask` are queued until reconnect and the screen says so |
   | Provider is `paid` and spend is not approved | Refused. Spend is a stop condition; the refusal is a fixed line, not an error |
   | No provider can answer | Checks only, the screen says so, and an `unmet` telemetry row is written |
   A refused request is never retried on a looser provider. Policy is code plus settings.
3. **Insights are a derived projection, not ledger events.** `cur_insights` (generated DDL, rebuildable like any
   projection, orchestrator gate): `insight_id`, `kind`, `subject_id`, `confidence` (`High`, `Medium`, `Low`; checks
   have none), `text`, `source_ids` (record and event ids), `facts_hash`, `expires_at`, `provider` (name and kind),
   `computed_at`. Rules:
   - Recomputed when a source event changes (the miner follows the outbox with its own cursor, like `rule_cursor`) and
     dropped at `expires_at`.
   - Rebuild means recompute from the current ledger: checks give the same rows, an opinion may differ.
   - **An insight is hidden whole for a viewer who cannot read any one of its sources.** No partial text, no count.
   - Dismissal is neither ledger nor telemetry (telemetry is demand data with no reader). A small operational table
     `insight_dismissal` (`facts_hash`, actor, `until`) stops a recompute showing it again to that person. This adds to
     the owner's design (roadmap item 3).
4. **Where an insight reaches the ledger: only by acceptance, and the insight id never does.** Accepting files a
   proposal (agent-made) or a command (person-made) whose intent `why` says it came from the insight. Fit with the
   other ADRs, checked against their plan-check answers:
   - ADR-0025: `why` is plain text (500 characters), which carries the reason on its own. No new intent key is needed.
   - ADR-0027 (answers F8, F9): `evidence` is deferred to Phase 3 and has two kinds, `{record}` and `{event}`. When it
     lands, an accepted insight copies its `source_ids` into `evidence`. Before it, the `why` names the source keys.
   - `insight_id` is never stored: a projection can be rebuilt with new ids, and the ledger must not point at a row that
     may not exist. The sources are what the ledger keeps.
5. **Mining sources**, each read through the viewer: records and links (`cur_*`, `cur_links`); later the graph (ADR-0026
   `cur_facts`); the event stream through an internal outbox subscription (a cursor, not a webhook); a best-practice
   library (versioned schema packages, roadmap 5); actions with their intents as they happen (ADR-0025 chains).
6. **Retrieval index.** Derived from the ledger and rebuildable; never a source of truth. Either one index per
   clearance level, or one index filtered at query time by `not_hidden`; the choice is made in roadmap 6 with the
   walking test as the deciding evidence. In both, no snippet of a record the viewer cannot open is returned, and the
   index is filtered before ranking, so a score cannot leak a hidden record. A model runs on the server's own machine
   unless spend is approved; its licence is checked (no copyleft) before it is chosen.
7. **Telemetry of need: stub now.**
   - **Where it lives.** An operational table in the main database, outside the hashed ledger, like `auth_audit` and the
     `wh_*` tables: `schema/core/telemetry.yaml` generates the DDL for both dialects, no adapter code. It is not a
     projection, is never rebuilt, and is not read by the archive, the lake, the outbox, webhooks or sync. On a replica it
     is node-local; merging it is not designed.
   - **Rows.** Append-only, ids only, no content: `need_id` (ties a request to its later outcomes), `scope`,
     `recorded_at`, `request_kind`, `trigger`, `record_id`, `record_type`, `viewer_role`, `provider_kind` (null while
     unanswered), `duration_ms`, `outcome` (`shown`, `accepted`, `dismissed`, `expired`, `unmet`), `why` (reuses the
     intent why shape; written null until a reader and its privacy review exist). One row per state change, never an UPDATE.
   - **Retention.** Setting `telemetry.retention_days`, default 365; older rows are pruned in the write transaction, as
     `auth_audit` does (not the ledger, so deletion is allowed).
   - **Write path.** `tl_core.telemetry.note_need(conn, *, request_kind, trigger, record_id, viewer_role, outcome,
     provider_kind=None, duration_ms=None)`. It never takes content, never raises into the caller's transaction, and
     writes nothing for a read of Activity. Called now from one place: opening a "not available yet" subtab.
   - **Stub:** table, function, retention, a parity test on both adapters; no reader, route, CLI or screen. The later
     reader (roadmap 4) is admin-only, drops rows whose `record_id` it cannot open, and shows free text only after a review.
8. **Confidentiality, in one rule.** A provider is given, and an insight shows, only what the requesting viewer can
   read, capped by the provider's `max_class`. A job that runs an analysis carries the requester's viewer, not a system
   viewer (ADR-0027 reads under the lowest viewer; this needs a carried viewer, a gated piece in roadmap 11).

## Consequences
Gates (orchestrator, each with an APPROVALS line; Sec rows for the router, the retrieval filter, the carried viewer):
| Item | Kind | When |
|---|---|---|
| Telemetry table `schema/core/telemetry.yaml` | schema | now (INS-T1) |
| `ClientInterface.note_need`, `.checks`, `.activity`, `.attention_counts`; routes | core interface | now (INS-A1, B1, T2) |
| `cur_proposal_subjects` | schema (projection) | now (INS-A1) |
| Entry-point group, registry, router | core interface (new contract, frozen on acceptance) | roadmap 2 |
| `cur_insights`, `insight_dismissal`, insight job kinds | schema | roadmap 3, 11 |
| Retrieval index and its store in both adapters | adapters, security review | roadmap 6 |
| Carried viewer in analysis jobs | auth and confidentiality, human gate (§25.5) | roadmap 11 |
No existing data, event, hash, archive or sync change. Agents cannot write telemetry or insights.

## Effort
| Item | S | H |
|---|---|---|
| Stub now: T1 and T2 (inside the spec's part C) | 0 | 2 |
| Registry and router (roadmap 2) | 1 | 4 |
| Projection, dismissal, recompute (roadmap 3) | 1 | 2 |
| Items 4 to 13 | see `roadmap-2026-11-07.md` | |

## Cheap now, expensive later
Only what cannot be added once data exists or readers depend on it:
1. **Telemetry shape**: append-only rows tied by `need_id`. A mutable row model would need a rewrite once a reader exists.
2. **Write unmet needs from the first screen that cannot answer** (the three "not available yet" subtabs): demand not
   recorded now cannot be rebuilt. The `why` column exists but stays null until the privacy review.
3. **Reserve the names**: entry-point group `throughline.insight_providers`, tables `cur_insights`, `insight_dismissal`,
   record tab key `9`. Free now; a collision later costs a rename.
Not now: provider code, `cur_insights`, an index, the router (each is cheap later and needs the registry first).

## Alternatives considered
| Option | Why not |
|---|---|
| Insights as ledger events | They are opinions, not facts; they would be immutable and hashed, and each recompute would add events |
| Dismissals in telemetry | Telemetry is demand data with no reader; losing it must not bring dismissed items back |
| Cite the insight id in the intent | A rebuilt projection may not hold that id; the sources are stable |
| Telemetry rows updated in place | Loses the time from shown to accepted; the shape is dear to change once a reader exists |
| Telemetry inside the ledger | It would be hashed, replicated and archived: content-free ids still reveal who looked at what |

## Stubs for the knowledge graph
`source_ids` are record and event ids, so a graph can join an insight to its facts without parsing text.
## Plan check
To be run by the orchestrator. Test: a class lowered while an insight exists (hide at read); the carried viewer in jobs;
whether `insight_dismissal` leaks a dismissal; telemetry `record_id` of a hidden record at read time.
