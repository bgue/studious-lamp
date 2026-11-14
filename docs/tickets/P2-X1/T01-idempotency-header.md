# P2-X1-T01 — `Idempotency-Key` header on the command routes

Status: ready (dispatch r2; S1 merged on `p2/x1` @77e9b51)
Tier: haiku
Kind: ticket
Review: full
Labels: api
Depends on: S1 (merged)
Branch: `p2/x1-t01-idempotency-header`
Worktree: `/home/user/wt/x1/t01`

## Goal
`POST /commands/{Name}` reads an optional `Idempotency-Key` request header and puts it on the command, so the door that S1 added
(`run_command`, `idempotency.check` / `record`) replays or refuses. Nothing else in the door changes.

## Brief references (pasted)
- S1 already honours `command.idempotency_key` in `run_command` (commands.py:356-375) and `TableCommandRunner.run`; a bad key raises
  `InvalidIdempotencyKeyError` (422 `invalid_idempotency_key`), a reused key with another body `IdempotencyMismatch` (409), a claim not
  yet completed `IdempotencyInProgress` (409). These error rows exist in `tl_api/errors.py:83-85`; add none.
- The body model (`request_model`) already copies the `idempotency_key` body field from `Command`. Rule (decision D4): the header is the
  documented way; the body field still works. Both given and different: 422 via `InvalidIdempotencyKeyError` with the fixed text
  `"Idempotency-Key header and body idempotency_key differ"`. Both equal or only one given: use it. A header present but empty is a
  bad key (422, from the existing validator; never echo the key).
- Header spelling: `Idempotency-Key`. Additive OpenAPI change (new optional header parameter).

## Interfaces (verbatim)
```python
# tl_api/commands.py, in _make_endpoint(...).endpoint(...), after effective_at:
        effective_at: Annotated[str | None, Header(alias=EFFECTIVE_AT_HEADER, description=...)] = None,
    ) -> CommandResult:
        ctx = get_ctx(request)
        fields = body.model_dump()
        if actor.startswith("agent:"):
            fields["source"] = source_for(actor)
        command = spec.model(**fields, actor=actor)
# S1 error class: from tl_core.services.idempotency import InvalidIdempotencyKeyError  (a ServiceError; message is the text)
```

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/commands.py` (lines 379-412 only, plus imports)
- `packages/tl-api/tests/test_idempotency_door.py` (style, harness fixtures)
- `packages/tl-api/tests/test_commands.py` (lines 1-30: `post`, `create`, `harness`)

## Allowed paths
- `packages/tl-api/src/tl_api/commands.py` (edit `_make_endpoint` and imports only)
- `packages/tl-api/tests/test_idempotency_header.py` (new)
- `docs/reference/openapi.json` (regenerated; see Steps)

## Steps
1. Add the header parameter (`alias="Idempotency-Key"`, `max_length` none: the validator owns the bound) and merge it into `fields`
   before `spec.model(...)` per the rule above.
2. Regenerate the reference file with the command `just check` names for openapi drift (`uv run python -m tl_api.openapi`; read its
   `--help`); commit the changed `docs/reference/openapi.json`.

## Acceptance
```
just check
just gate packages/tl-api/tests/test_idempotency_header.py packages/tl-api/tests/test_idempotency_door.py packages/tl-api/tests/test_commands.py
```
Expected: pass. Do not run any wider directory.

## Tests to add (`test_idempotency_header.py`, both adapters via the harness if `test_idempotency_door.py` does so)
- Same header and body twice: one record, second response equals the first (`id`s equal).
- Same header, other body: 409 `idempotency_mismatch`, nothing written.
- Header only vs body field only: same effect; header and body differing: 422 `invalid_idempotency_key`, nothing written.
- Bad header (129 chars, a space, empty): 422, response text never contains the key.
- Another actor with the same header value: its own record (no replay).
- No header: unchanged behaviour (two calls, two writes where keys differ).
- The OpenAPI document lists `Idempotency-Key` as an optional header parameter on `/commands/CreateRecord`.

## Report requirements
Standard report. Say whether the 422 body for a bad key echoes input (S1 noted FastAPI may); if it does, stop (escalation).

## Escalation triggers
- Stop if a bad key comes back in any response body.
- Stop if the change needs `idempotency.py`, `errors.py` or any `tl_core` edit.
- Stop if a route other than `/commands/{Name}` seems to need the header (the accept and reject routes take none; there is no agent
  create route on the API: report it).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
