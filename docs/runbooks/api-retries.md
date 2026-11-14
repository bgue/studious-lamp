# Runbook — Retried writes (`Idempotency-Key`) and the OpenAPI compatibility gate

Purpose: make a retried command write safe, and tell an operator or an integrator what each answer means. Also: how the
OpenAPI compatibility gate is run and what to do when it refuses. Reference: `docs/reference/api-compat.md`. Demo:
`just demo P2-X1` (`dev/demos/P2-X1.sh`). Decisions: P2-X1 `STATE.md` D1, D4, D5.

## When to use
- A client retried `POST /commands/{Name}` after a timeout or a dropped connection, and needs to know what it gets back.
- An agent calls an MCP proposing tool again after a failure.
- `just check` fails on the `openapi --compat` step.

## Sending a key (integrator)
- Send the key in the header `Idempotency-Key`, or in the body field `idempotency_key`. Either is accepted.
- If both are sent and they differ: `422 invalid_idempotency_key`, nothing written.
- A key is scoped to the actor. Another actor sending the same key gets its own result (demo clause 4).
- Rules: printable ASCII without a space, 1 to 128 characters. A malformed key is refused with a 422 (the generic
  validation code, not `invalid_idempotency_key`; see the T01 report).
- Keep one key per logical request and reuse it on every retry of that request.
- Agents have no HTTP create route. An agent's HTTP create of a record is refused: `403 agent_must_propose`, nothing stored.
  An agent creates records through the MCP proposing tools.
- MCP: the five tools in `packages/tl-mcp/src/tl_mcp/write_tools.py` take an optional `idempotency_key` with the same rules.
  The module tools (punch, requisition, awp and the others) do not take one yet (deferred, `docs/build-spec/DEFERRED.md`).
  Proposal rules and actions keep the key unset.

## What the answers mean
| Situation | Answer | What is written |
|---|---|---|
| First send | the command's normal answer | one event set |
| Same key, same body, after the first send finished | the first answer, replayed (same ids) | nothing new |
| Same key, other body or other command | `409 idempotency_mismatch`; the key is not echoed | nothing |
| Same key while the first send is still running | `409 idempotency_in_progress` | nothing |
| Same key, first send was refused | the refusal is not kept; the key is free for a new send | nothing from the refusal |
| Header and body key differ | `422 invalid_idempotency_key` | nothing |

- A replay rebuilds the answer from the ledger: the result ids are the stream id and the event ids.
- Two concurrent sends with one key make one record and no 500 (demo clause 2).
- Integrator steps: wait and resend the same request with the same key on `409 idempotency_in_progress`. On
  `409 idempotency_mismatch`, do not reuse the key: send the new body with a new key.

## A replay after a clearance drop
A replay checks the viewer again. If the viewer can no longer see the record, the replay answers as if the id never
existed: `404` with the text of a missing id, and no title or record id. An agent's MCP replay gets the same error type
and text as a call that names a missing id. This is by design (ADR-0016): do not work around it in a client.

## One key, one intent
A key names one intent, not one record version. `expected_version` is not part of the request hash, so a reused key
replays the first answer even if the record has changed since. To re-apply after someone else changed the record, read
the record again and send the change with a new key.

## Retention
- Setting `idempotency.retention_days`: default 7, range 1 to 90 (`schema/settings/platform.yaml`).
- The window is not enforced yet. The purge job is deferred (P2-X1 D1; `docs/build-spec/DEFERRED.md`), so rows are kept,
  and a same-key retry replays the first answer at any age. The lookup has no age filter.
- Do not rely on expiry. Use a new key for a new request.
- A key is a credential-like value of the client. It is never logged and never put in an error text.

## The OpenAPI compatibility gate
- `just check` runs `uv run python -m tl_api.openapi --compat`. It exits 1 on a breaking change against
  `docs/reference/openapi.baseline.json`, and names the change in one line.
- Breaking changes (refused): a removed route or method; a removed or renamed response field; a changed field type; a new
  required request field or parameter; an optional parameter made required; a removed or re-statused error code.
- Additive changes pass: a new route, an optional request field, a new response field, a new error code.
- The baseline is refreshed only as a release step with `just openapi-baseline`, which refuses a breaking change. Do not
  edit the baseline by hand, and do not refresh it in a feature change.
- A breaking change between releases needs a line in `docs/reports/APPROVALS.md` naming what breaks, and a note in
  `docs/reference/api-compat.md`. Removals are deprecated for at least one release first.
- `just compat-update` is a different gate: it refreshes the event payload baseline, not the OpenAPI one.

## Where errors show
- The client gets the status and the `error.code` in the body. The key is not echoed in the answer.
- Server errors go to the `tl_api` logger on the `just serve` terminal. A key is never logged.

## Troubleshooting
- **`409 idempotency_in_progress` does not clear.** Resend later with the same key and body. If it stays, escalate to the
  supervisor with the endpoint and the time. Do not edit the `idempotency_key` table by hand.
- **`409 idempotency_mismatch` after a retry.** The body changed between sends. Send the original body, or use a new key
  for the new request.
- **`404` on a replay.** The viewer lost clearance on the record. By design; see above.
- **`just check` fails on `openapi --compat`.** The message names the change. A removed field or route needs deprecation
  first. An additive change should pass; if it does not, check the message for the field name.
- **The gate says the baseline is missing.** The baseline is written only by `just openapi-baseline` as a release step.
  Do not create it in a feature branch.

## Demo
`just demo P2-X1` runs `dev/demos/P2-X1.sh` on SQLite and Postgres (`TL_DEMO_BACKENDS` picks the backends). Each of its six
clauses ends in a PASS line, and the script ends with `P2-X1 demo OK on: <backend>`.

## Roll back
- Retries: nothing to roll back; idempotency rows are operational and are not events.
- Compatibility: revert the change that broke the gate. Do not refresh the baseline to make the gate pass.
- Dev ledger: as in `docs/runbooks/web-client.md` (delete `dev/data/tl.db` and run `uv run tl init --dev`).
