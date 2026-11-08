# P2-INT — Intent on commands (ADR-0025 thin slice) and the world-date tag stub (ADR-0026 F5)

Status: planning (round 1). Branch `p2/int`, from `p2/wave2-close`. Board and next steps: `STATE.md`.
Specs: `docs/adr/0025-intent-on-commands.md` (Decision, Thin slice; the "Plan check and answers" F3-F6, F13, F14 win over the body),
`docs/adr/0026-attested-bitemporal-graph.md` (answer F5), `docs/adr/0027-agent-first-layer.md` (answer F9). ADR-0028: nothing now.
Slot (F13): after the wave 2 close, before wave 3 (wave 3 is where new commands arrive).

## Objective
After P2-INT every command can carry an optional `intent` (`why`, `next`, `toward`, `goal_ref`). It is validated once at the command
boundary, stored in a nullable TEXT column `events.intent` of every event the command appends, and covered by the event hash through an
optional last hash part that exists only when an intent exists, so no existing chain, segment or restore changes. People and agents use it
the same way; an agent proposal keeps its intent in the `Proposal.Created` event's `intent` column (never the payload, ADR-0027 F9) and
accepting runs the command with it. The API returns `intent` on event, history and trace reads. Nothing reads an intent to decide
anything. Separately, the annotation `tl:valid_time` (`at|from|to`) is declared and a lint makes wave 3 event classes carry it.
No intent is filled by any face until the soon tickets; the thin slice is empty everywhere without them.

## Demo (`just demo P2-INT`, SQLite then Postgres; driver `dev/demos/P2-INT.sh`, ticket T05)
1. A command with `intent {why, toward}` appends an event whose `intent` column holds the canonical JSON; the same command without intent leaves it NULL.
2. A chain with intents and without verifies (`tl archive verify`); the intent event's hash differs from the hash it would have had without the intent; an old sealed segment re-seals byte-identical.
3. Seal, restore into an empty database, verify: intents survive; lake sync lands the `intent` bronze column.
4. A bad intent (too long, bad `next` command name, unknown `toward` target) refuses the whole command with `intent_invalid`; an unknown id and a hidden id both give `intent_reference_unknown` with the same text.
5. `{}` and all-null intents store NULL.
6. An agent proposes with an intent; the `Proposal.Created` payload has no `intent` key, its column has; accepting appends events carrying the same intent, actor = the accepting person, agent named as today.
7. The API event, history and trace routes return `intent`; a viewer without access to a referenced record sees "not available", identical to a missing one.
8. CLI `--why/--next/--toward`, the MCP `intent` parameter and the TUI History display show it (T02-T04, staged).

## Pieces and tickets
| ID | File | Kind | Review | Depends | Approver / Sec |
|---|---|---|---|---|---|
| S1 | `S1-event-intent.md` | piece: model, column, hash extension, archive, restore, bronze | full | wave 2 close | orchestrator, APPROVALS line (core interface, hash extension, nullable column); Sec: hash extension |
| S2 | `S2-intent-boundary.md` | piece: validation, carrier, API, proposals, walk | full | S1 merged | orchestrator, APPROVALS line; Sec: intent references |
| T01 | `T01-valid-time-tag.md` | ticket (schema label): annotation, module-standard rule, lint | full | — | orchestrator, APPROVALS line |
| T02 | `T02-cli-intent-flags.md` | ticket, staged | full | S2 | — |
| T03 | `T03-mcp-intent-param.md` | ticket, staged | full | S2 | — |
| T04 | `T04-tui-intent-display.md` | ticket, staged | full | S2 | — |
| T05 | `T05-demo.md` | ticket, staged | lite | S1, S2, T02-T04 | — |
Effort matches ADR-0025 (2 pieces, 1 ticket thin slice, 3 soon) plus T01 (ADR-0026 F5) and the demo driver: 2 S, 5 H. Under 10 tickets: no PLANCHK
of the plan itself (the ADRs were plan-checked, answers F3-F6, F13, F14 above).

## Order of work
1. Batch 1 (disjoint paths): S1 and T01. 2. After S1 merges (C1): S2. 3. After S2 merges (C2): T02, T03, T04 (disjoint, one workflow of 3).
4. T05 last (C3). C4 = demo green both adapters; orchestrator runs the full gate and `gate-pg` on the touched directories and a short security review on S1+S2 (Sec rows).
Wave 3 must not start before C2 (command tickets there assume the field exists); T02-T04 may overlap wave 3.

## Risks and escalation
- S1 changes `event_hash` and the events DDL: ledger code, human gate. A pre-change segment must re-seal byte-identical; this is S1's first test.
- Handlers pass append arguments explicitly in ~87 files; the carrier (ContextVar set by the dispatcher) is the only way modules stay untouched. Any entry that runs a handler without the dispatcher (simulator, rules, integration actions, jobs) writes NULL intent; S2 lists each such entry in its report and does not extend them.
- Postgres `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` and SQLite (no IF NOT EXISTS: probe `PRAGMA table_info`) differ; both inside `tl_adapters`.
- Downgrade across the change on a ledger holding intents shows as a plain hash mismatch (F14); no downgrade guard is built.
