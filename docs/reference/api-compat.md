# Reference: API compatibility

Purpose: what may change in the HTTP API between releases, what never changes without notice, and how a change is
announced. For API consumers and contributors.
Related: [punch list reference](punch.md) (an example of a route and tool list), [access words](access-words.md).

## What may change

Additive changes are allowed at any time, without notice:

| Change | Example |
|---|---|
| New route | a new `GET /projects/{project}/...` path |
| New optional request field | a body field a client may omit |
| New optional header or query parameter | `Idempotency-Key`, a new filter |
| New response field | an extra key in a JSON response |
| New error code | a new `error.code` value for a new failure |

## What never changes unannounced

These are breaking. The compatibility checks refuse them: `tl_schema.compat.diff_openapi` for the HTTP schema, and the
error-code check. Both are wired into `just check` by ticket P2-X1-T05 in this increment:

- a removed route or a removed method;
- a removed or renamed response field;
- a changed field type;
- a new required request field or parameter;
- an optional parameter that became required;
- a removed or re-statused error code.

A breaking change between releases needs two things: a line in `APPROVALS.md` naming what breaks, and a note on this page.
Removals are deprecated first (see Deprecated below).

## Event payloads

Event payloads are separate from the HTTP schema. They change only additively over
`packages/tl-schema/compat/event-schemas.json`. Refresh that baseline with `just compat-update`; it refuses a change that
is not additive.

## The baseline and how it is refreshed

- The OpenAPI baseline is `docs/reference/openapi.baseline.json`.
- It is refreshed only as a release step, with `just openapi-baseline`. Do not edit it by hand, and do not refresh it in a
  feature change.
- `just openapi-baseline` is created by ticket P2-X1-T05 in this increment. Until T05 lands, the command does not exist.
- Between releases the baseline stays fixed, so every change since the last release is checked against it.

## Deprecated

A removal is announced for at least one release before it happens. The field stays in responses during that time.

| Item | Deprecated in | Removed in |
|---|---|---|
| (none) | | |

When an item is deprecated, add a row here with the release it was deprecated in. When it is removed, fill in the release
in the last column.

## Retries and `Idempotency-Key`

Command writes (`POST /commands/{Name}`) accept an idempotency key so that a retried request does not run twice.

- Send the key in the `Idempotency-Key` header. The body field `idempotency_key` is also accepted.
- If both are given and they differ, the request fails with `422 invalid_idempotency_key`.
- A key is scoped to the actor. It is printable ASCII without spaces, 1 to 128 characters long.
- Same key and same body: the server replays the first answer.
- Same key and a different body: `409 idempotency_mismatch`.
- Same key while the first send is still running: `409 idempotency_in_progress`.
- MCP proposing tools take an optional `idempotency_key` argument with the same rules.
