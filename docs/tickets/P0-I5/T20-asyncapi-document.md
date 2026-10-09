# P0-I5-T20 — AsyncAPI 3 document builder

Status: ready
Tier: haiku
Labels: core
Depends on: — (the stub, `EventTypeInfo` and the provided test are on the base branch)
Branch: `p0/i5b-t20-asyncapi-document`

## Goal
`tl_schema.catalog_asyncapi.asyncapi_document(events, *, title, version)` turns the list of event-type descriptions the catalog
generator produces into one AsyncAPI 3.0 document: a channel, an operation and a message per event type, a shared headers schema and a
sample per message. It is a pure function of its inputs. The signature and the docstring exist in the stub; the body raises
`NotImplementedError`. A provided test file (11 tests) must pass.

## Brief references (pasted)
> **18.3 Event catalog and envelope.** Every event type is defined in LinkML, with its schema, description, semantic URI, and version.
> A browsable, generated **event catalog** is published from it: docs, JSON Schema, sample payloads, and AsyncAPI.
> **18.4 Outbound webhooks.** HMAC-SHA256 signatures (Standard Webhooks headers: id, timestamp, signature).

### Specification (the provided test checks it)
Let `ordered = sorted(events, key=lambda e: e.event_type)`. If two events share an `event_type`, raise
`ValueError("duplicate event type in the catalog")`. The result is a dict with exactly these keys, in this order:

1. `"asyncapi": "3.0.0"` (use the constant `ASYNCAPI_VERSION`).
2. `"info": {"title": title, "version": version, "description": <text>}`. The description is one fixed sentence or two that mentions
   `CloudEvents` (the test looks for that word), for example: "Events delivered by Throughline webhooks as CloudEvents 1.0 JSON, signed
   with Standard Webhooks headers. Generated from the LinkML event classes."
3. `"defaultContentType": "application/json"`.
4. `"channels"`: for each event, key = `event.event_type` (for example `Record.Created`), value
   `{"address": event_type, "title": event.title, "messages": {event_type: {"$ref": "#/components/messages/<event_type>"}}}`.
5. `"operations"`: key = `"receive" + event_type.replace(".", "")` (`receiveRecordCreated`), value
   `{"action": "receive", "channel": {"$ref": "#/channels/<event_type>"}, "summary": event.title,
   "messages": [{"$ref": "#/channels/<event_type>/messages/<event_type>"}]}`.
6. `"components"`: `{"messages": {...}, "schemas": {"WebhookHeaders": {...}}}`.
   * A message (key = `event_type`) is `{"name": event.ce_type, "title": event.title, "summary": event.title,
     "description": event.description, "contentType": "application/json", "headers": {"$ref": "#/components/schemas/WebhookHeaders"},
     "payload": <envelope schema>, "examples": [{"name": "sample", "headers": {...}, "payload": <sample envelope>}]}`.
   * `<envelope schema>` is a **deep copy** of `event.envelope_schema` without its **top-level** `"$schema"` and `"$id"` keys (nested
     keys named `$id` stay).
   * `<sample envelope>` is a **deep copy** of `event.sample_envelope`. The example `headers` has exactly three keys:
     `"webhook-id"` = `event.sample_envelope.get("id", "")`, `"webhook-timestamp"` = `"1760000047"`, `"webhook-signature"` =
     `"v1,ZXhhbXBsZS1zaWduYXR1cmU="`.
   * `WebhookHeaders` is the object schema: `{"type": "object", "description": <text>, "required": ["webhook-id", "webhook-timestamp",
     "webhook-signature"], "properties": {<the three names>: {"type": "string", "description": <non-empty text>}}}`.
7. With no events, `channels`, `operations` and `components.messages` are empty dicts and `WebhookHeaders` is still present.
8. The same events in any input order give an identical document, key order included. Inputs are never modified and the output
   shares no mutable object with them (deep copies).

Learnings that apply:
- Provided tests live in `docs/tickets/P0-I5/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- pyright is `strict` for `packages/tl-schema/src`; ruff limits lines to 100 columns. Run `uv run ruff format` on your files before
  committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail` or `grep` (you lose its exit status).
- A fresh worktree has no workspace packages installed: run `uv sync --all-packages` once before the first test.
- Remove the `STUB (P0-I5-T20)` paragraph from the module docstring when you are done.
- Commit your report file (see Allowed paths); an uncommitted report cost earlier tickets a retry.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-schema/src/tl_schema/catalog_types.py
@dataclass(frozen=True)
class EventTypeInfo:
    event_type: str            # "Record.Created"
    version: int               # 1
    ce_type: str               # "tl.core.Record.Created.v1"
    title: str                 # first sentence of description
    description: str
    payload_class: str         # "RecordCreatedPayload"
    payload_schema: dict[str, Any]   # JSON Schema of the ledger payload
    envelope_schema: dict[str, Any]  # JSON Schema of the CloudEvent a subscriber receives
    sample_payload: dict[str, Any]
    sample_envelope: dict[str, Any]
```
```python
# packages/tl-schema/src/tl_schema/catalog_asyncapi.py (stub; the signature is final)
ASYNCAPI_VERSION = "3.0.0"

def asyncapi_document(
    events: Sequence[EventTypeInfo],
    *,
    title: str = "Throughline events",
    version: str = "1.0.0",
) -> dict[str, Any]: ...
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-schema/src/tl_schema/catalog_asyncapi.py`
- `packages/tl-schema/src/tl_schema/catalog_types.py`
- `docs/tickets/P0-I5/provided/test_catalog_asyncapi.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-schema/src/tl_schema/catalog_asyncapi.py` (edit)
- `packages/tl-schema/tests/test_catalog_asyncapi.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I5/P0-I5-T20.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I5/provided/test_catalog_asyncapi.py.txt packages/tl-schema/tests/test_catalog_asyncapi.py`
2. Implement `asyncapi_document` (add `import copy` and the constants you need); delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit the code and the report.

## Acceptance
```
uv run pytest packages/tl-schema/tests/test_catalog_asyncapi.py -q
just check
just test
diff docs/tickets/P0-I5/provided/test_catalog_asyncapi.py.txt packages/tl-schema/tests/test_catalog_asyncapi.py
```
Expected: 11 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
