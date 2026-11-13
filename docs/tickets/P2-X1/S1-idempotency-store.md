# P2-X1-S1 — Idempotency store, helper, replay and mismatch rule

Status: ready (dispatch r1; schema and settings: gated)
Tier: builder
Kind: piece
Review: full
Labels: schema, core, api
Depends on: trunk @237a1a6b
Branch: `p2/x1-s1-idempotency-store`
Worktree: `/home/user/wt/x1/s1`
Approver (schema, setting): orchestrator (line in `docs/reports/APPROVALS.md` at merge; relay line `95`)

## Goal
A retry with the same `Idempotency-Key` never writes twice. After this piece an operational table `idempotency_key`, the setting
`idempotency.retention_days` (default 7), the helper `tl_core.services.idempotency`, and its use at the three call sites exist and are
tested on both adapters. Route headers, client, MCP tool and walking tests are Haiku tickets that start after this merges (T01, T03, T07).

## Brief references (pasted from `docs/build-spec/12-extension-plan.md`, P2-X1)
- Key: per actor, ASCII, at most 128 characters, never logged and never in an error text.
- Store: (actor, key) -> command name, body hash, result ids, created. No response text. A replay re-reads the ids through the viewer
  filter (ADR-0016): an id the viewer can no longer see answers as absent (phrase 140), same status and text.
- Same key, different command name or body hash: refused with one fixed message; nothing is written.
- Concurrent insert of the same (actor, key): the loser answers as a replay of the winner, or a fixed in-progress refusal. Never a 500.
- One transaction with the write: the key row commits with the command's events, or neither does.
- Retention: setting `idempotency.retention_days`, default 7, gated. The purge job is DEFERRED (DEFERRED.md); rows are kept until it
  ships. A retry after expiry files anew (documented in the T09 runbook).
- Embedded and CLI paths pass `None` and behave as today. Additive only: no existing event changes, no data migration.

## Seams (grep, do not read whole files)
- `packages/tl-core/src/tl_core/services/commands.py:46` `Command.idempotency_key` (accepted and ignored today; keep the field, validate
  it when set: ASCII, 1..128).
- `packages/tl-core/src/tl_core/services/proposals.py:499, 573, 636` set `"idempotency_key": None` on the stored command in `propose`,
  `propose_for_rule`, `propose_action`. `propose` is the agent filing path (API and MCP). The rule and action paths are automation:
  they keep `None`; say so in the report.
- `packages/tl-api/src/tl_api/commands.py:359` (the guarded handler call in the generic command runner) and `:503` (the table runner).
  The API door is the call site; the helper wraps the handler call inside the open `uow` (look at both and choose the narrowest wrap).
- `schema/core/jobs.yaml` and `schema/core/auth.yaml`: shape of an operational table (`tl:current_state`, `tl:table`). Settings:
  `packages/tl-core/src/tl_core/settings/registry.py` (declare the setting; find where `platform.yaml` style defaults live there).

## Interfaces to deliver (names fixed; bodies are the builder's)
```python
# tl_core/services/idempotency.py
@dataclass(frozen=True)
class Replay:           # the stored answer: command name, result ids
    command: str
    result_ids: list[str]

def check(conn, actor: str, key: str | None, command: str, body: object) -> Replay | None:
    """None when the key is None or new (a claim row is inserted in the caller's transaction);
    a Replay when the same (actor, key, command, body hash) completed; raises IdempotencyMismatch
    (fixed message) for a different command or body; IdempotencyInProgress (fixed message) when a
    concurrent claim has not committed."""
def record(conn, actor: str, key: str | None, result_ids: list[str]) -> None: ...
```
The body hash is a SHA-256 of the canonical JSON of the command (sorted keys; `idempotency_key`, `correlation_id`, `causation_id`
excluded). The two error classes subclass the existing refusal base the API maps to 409 (mismatch) and 409 (in progress); reuse
the mapping in `tl_api`, no new handler style.

## Context (read these; at most 10)
- `packages/tl-core/src/tl_core/services/commands.py` (lines 1-80)
- `packages/tl-core/src/tl_core/services/proposals.py` (`propose` only, 457-528)
- `packages/tl-api/src/tl_api/commands.py` (lines 320-380, 470-525)
- `schema/core/jobs.yaml`, `schema/core/settings.yaml`, `packages/tl-core/src/tl_core/settings/registry.py`
- `packages/tl-core/src/tl_core/confidentiality.py` (viewer filter entry points)
may explore: `packages/tl-adapters/src/tl_adapters/**` for the insert-conflict form on each dialect (adapter code stays dialect-owned).

## Allowed paths
- `schema/core/idempotency.yaml` (create) and the one setting declaration; then `just gen` output
- `packages/tl-core/src/tl_core/services/idempotency.py` (create), `services/commands.py`, `services/proposals.py` (key handling only)
- `packages/tl-core/src/tl_core/settings/registry.py` (setting)
- `packages/tl-api/src/tl_api/commands.py` (call sites), `packages/tl-api/src/tl_api/errors*.py` only if the 409 mapping needs a line
- `packages/tl-adapters/src/tl_adapters/**` only for the dialect-specific insert-conflict statement, if the core cannot be neutral
- tests: `packages/tl-core/tests/test_idempotency*.py`, `packages/tl-api/tests/test_idempotency_door.py` (create)
- pinned lists a new table or setting changes (consequential pins; list them in the report)

## Tests to add (both adapters via the existing `db`/`new_db` fixtures)
Same key twice returns the first answer and one event set; same key with another body or command: fixed refusal, nothing written;
two threads, one key: one write, the other a replay or the in-progress refusal, never an error 500; another actor with the same key
value neither sees nor collides; clearance drop then replay returns ids hidden as absent; key row rolls back with a failed command;
a key of 129 characters or non-ASCII is refused with a text that does not contain the key; the key is absent from every log record
(caplog) and every error text; `propose` with one key files one proposal row; `None` key behaves as before.

## Guards the sentinel and the targeted mutants must cover (builder runs 1 sentinel + at most 5, reports in 3 lines)
1. body-hash comparison (mismatch must refuse), 2. actor part of the lookup key (cross-actor isolation), 3. replay re-read through
the viewer filter, 4. claim insert in the same transaction as the write (rollback test), 5. the key length and ASCII bound.

## Acceptance
```
just gen && just check
just gate packages/tl-core/tests packages/tl-api/tests packages/tl-schema/tests
just gate-pg packages/tl-core/tests/test_idempotency.py
```
Heavy test slots are tight on the box: run exactly these, once. Do not run the whole suite.

## Report requirements
Standard report plus: the call-site decision for `:359` and `:503`, the dialect statement used for the claim insert, the pinned
lists changed, mutation result in 3 lines, candidate learnings.

## Escalation triggers
- The wrap needs a change to `CommandSpec` or any module interface.
- The claim insert needs dialect SQL outside `tl_adapters`.
- A replay cannot be re-read through the viewer filter without touching `confidentiality.py`.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
