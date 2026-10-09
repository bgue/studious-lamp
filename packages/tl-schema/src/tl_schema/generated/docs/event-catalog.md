# Throughline event catalog

Every ledger event type that can reach a webhook subscriber, generated from the LinkML event classes. Each event arrives as a CloudEvents 1.0 JSON message signed with Standard Webhooks headers; the payload modes are `thin`, `delta` and `full`. Receivers dedupe on the event `id`. A request sent by `tl webhook test` carries the extra header `webhook-test: 1`; real deliveries never do.

## Event types

| Event type | CloudEvents type | Summary |
|---|---|---|
| [`File.Processed`](#fileprocessed) | `tl.core.File.Processed.v1` | A file passed its scan and is available. |
| [`File.Rejected`](#filerejected) | `tl.core.File.Rejected.v1` | A file failed its scan and was rejected. |
| [`File.Uploaded`](#fileuploaded) | `tl.core.File.Uploaded.v1` | A file was uploaded and attached to a record; it is quarantined until its scan finishes. |
| [`Link.Accepted`](#linkaccepted) | `tl.core.Link.Accepted.v1` | A suggested link was accepted and is now active. |
| [`Link.Added`](#linkadded) | `tl.core.Link.Added.v1` | A link between two records became active. |
| [`Link.Declined`](#linkdeclined) | `tl.core.Link.Declined.v1` | A suggested link was declined; it will not be suggested again. |
| [`Link.Flagged`](#linkflagged) | `tl.core.Link.Flagged.v1` | A link was flagged stale or broken. |
| [`Link.Repinned`](#linkrepinned) | `tl.core.Link.Repinned.v1` | The pin of a link was set to another revision. |
| [`Link.Retracted`](#linkretracted) | `tl.core.Link.Retracted.v1` | A link was retracted. |
| [`Link.Suggested`](#linksuggested) | `tl.core.Link.Suggested.v1` | A link was suggested and waits for a person to accept or decline. |
| [`Link.Verified`](#linkverified) | `tl.core.Link.Verified.v1` | A person verified an active link. |
| [`Numbering.Allocated`](#numberingallocated) | `tl.core.Numbering.Allocated.v1` | A number was allocated from a counter. |
| [`Pset.ValuesSet`](#psetvaluesset) | `tl.core.Pset.ValuesSet.v1` | Values of a property set were written on a record. |
| [`Record.Corrected`](#recordcorrected) | `tl.core.Record.Corrected.v1` | A recorded value was corrected after the fact; history keeps the original. |
| [`Record.Created`](#recordcreated) | `tl.core.Record.Created.v1` | A record was created. |
| [`Record.Updated`](#recordupdated) | `tl.core.Record.Updated.v1` | One or more fields of a record changed. |
| [`Record.Voided`](#recordvoided) | `tl.core.Record.Voided.v1` | A record was voided. |
| [`Schema.EffectiveChanged`](#schemaeffectivechanged) | `tl.core.Schema.EffectiveChanged.v1` | The effective schema of a scope changed. |
| [`SchemaPackage.Published`](#schemapackagepublished) | `tl.core.SchemaPackage.Published.v1` | A schema package version was published. |
| [`WebhookSubscription.Created`](#webhooksubscriptioncreated) | `tl.core.WebhookSubscription.Created.v1` | A webhook subscription was created. |
| [`WebhookSubscription.Disabled`](#webhooksubscriptiondisabled) | `tl.core.WebhookSubscription.Disabled.v1` | A subscription stopped receiving events. |
| [`WebhookSubscription.Enabled`](#webhooksubscriptionenabled) | `tl.core.WebhookSubscription.Enabled.v1` | A disabled subscription started receiving events again, from this event on. |
| [`WebhookSubscription.SecretRotated`](#webhooksubscriptionsecretrotated) | `tl.core.WebhookSubscription.SecretRotated.v1` | A new signing secret was issued; the previous one keeps signing until the overlap ends. |
| [`WebhookSubscription.Updated`](#webhooksubscriptionupdated) | `tl.core.WebhookSubscription.Updated.v1` | A subscription's name, target, filter or payload mode changed. |
| [`Workflow.Transitioned`](#workflowtransitioned) | `tl.core.Workflow.Transitioned.v1` | A record moved from one workflow state to another. |

## File.Processed

A file passed its scan and is available.

- CloudEvents type: `tl.core.File.Processed.v1`
- Ledger payload class: `FileProcessedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `file_id` | string | yes | File id. |
| `report` | any | no | Scan report. |
| `status` | string or null | no | available. |
| `supersedes` | any | no | Ids of the files this one replaced in a single-file slot. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P8",
      "report": {
        "scanner": "stub"
      },
      "status": "available",
      "supersedes": []
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/File.Processed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.File.Processed.v1"
}
```

## File.Rejected

A file failed its scan and was rejected.

- CloudEvents type: `tl.core.File.Rejected.v1`
- Ledger payload class: `FileRejectedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `file_id` | string | yes | File id. |
| `reason` | string | yes | Why it was rejected. |
| `report` | any | no | Scan report. |
| `status` | string or null | no | rejected. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P8",
      "reason": "malware signature",
      "report": {
        "scanner": "stub"
      },
      "status": "rejected"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/File.Rejected/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.File.Rejected.v1"
}
```

## File.Uploaded

A file was uploaded and attached to a record; it is quarantined until its scan finishes.

- CloudEvents type: `tl.core.File.Uploaded.v1`
- Ledger payload class: `FileUploadedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `content_type` | string | yes | Media type. |
| `deduplicated` | boolean or null | no | True when the bytes already existed. |
| `file_id` | string | yes | File id. |
| `filename` | string | yes | Original file name. |
| `record_id` | string | yes | The record the file is attached to. |
| `revision` | integer or null | no | Position in the slot. |
| `sha256` | string | yes | SHA-256 of the bytes. |
| `size` | integer | yes | Size in bytes. |
| `slot` | string or null | no | File slot; null for a generic attachment. |
| `status` | string or null | no | quarantined. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "content_type": "application/pdf",
      "deduplicated": false,
      "file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P8",
      "filename": "mtr.pdf",
      "record_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "revision": 1,
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "size": 1024,
      "slot": "mtr",
      "status": "quarantined"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/File.Uploaded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.File.Uploaded.v1"
}
```

## Link.Accepted

A suggested link was accepted and is now active.

- CloudEvents type: `tl.core.Link.Accepted.v1`
- Ledger payload class: `LinkAcceptedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `note` | string or null | no | Free-text note. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "note": "Confirmed on site"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Link.Accepted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Link.Accepted.v1"
}
```

## Link.Added

A link between two records became active.

- CloudEvents type: `tl.core.Link.Added.v1`
- Ledger payload class: `LinkAddedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `confidence` | number or null | no | Confidence of a suggested link, 0 to 1. |
| `from_ref` | string | yes | Record id at the start of the link. |
| `note` | string or null | no | Free-text note. |
| `pin` | string or null | no | Revision the link is pinned to; null for a floating link. |
| `relation` | string | yes | Relation code. |
| `source` | string or null | no | Who or what made the link: manual, rule, ai or import. |
| `to_ref` | string | yes | Record id at the end of the link. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "confidence": null,
      "from_ref": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "note": null,
      "pin": null,
      "relation": "raised_against",
      "source": "manual",
      "to_ref": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
    },
    "links": [
      {
        "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
        "rel": "raised_against"
      }
    ],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Link.Added/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Link.Added.v1"
}
```

## Link.Declined

A suggested link was declined; it will not be suggested again.

- CloudEvents type: `tl.core.Link.Declined.v1`
- Ledger payload class: `LinkDeclinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string or null | no | Why it was declined. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Different valve"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Link.Declined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Link.Declined.v1"
}
```

## Link.Flagged

A link was flagged stale or broken.

- CloudEvents type: `tl.core.Link.Flagged.v1`
- Ledger payload class: `LinkFlaggedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string or null | no | Why it was flagged. |
| `status` | string | yes | stale or broken. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "revision B issued",
      "status": "stale"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Link.Flagged/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Link.Flagged.v1"
}
```

## Link.Repinned

The pin of a link was set to another revision.

- CloudEvents type: `tl.core.Link.Repinned.v1`
- Ledger payload class: `LinkRepinnedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `pin` | string or null | no | The new pin; null makes the link floating. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "pin": "B"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Link.Repinned/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Link.Repinned.v1"
}
```

## Link.Retracted

A link was retracted. Its row and history stay.

- CloudEvents type: `tl.core.Link.Retracted.v1`
- Ledger payload class: `LinkRetractedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string or null | no | Why it was retracted. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Wrong record"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Link.Retracted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Link.Retracted.v1"
}
```

## Link.Suggested

A link was suggested and waits for a person to accept or decline.

- CloudEvents type: `tl.core.Link.Suggested.v1`
- Ledger payload class: `LinkSuggestedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `confidence` | number or null | no | Confidence, 0 to 1. |
| `from_ref` | string | yes | Record id at the start of the link. |
| `note` | string or null | no | Free-text note. |
| `pin` | string or null | no | Revision the link is pinned to. |
| `relation` | string | yes | Relation code. |
| `source` | string or null | no | Origin of the suggestion: rule, ai or import. |
| `to_ref` | string | yes | Record id at the end of the link. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "confidence": 0.82,
      "from_ref": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "note": null,
      "pin": null,
      "relation": "references",
      "source": "ai",
      "to_ref": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
    },
    "links": [
      {
        "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
        "rel": "references"
      }
    ],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Link.Suggested/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Link.Suggested.v1"
}
```

## Link.Verified

A person verified an active link.

- CloudEvents type: `tl.core.Link.Verified.v1`
- Ledger payload class: `LinkVerifiedPayload`
- Version: 1

### Payload fields

No fields.

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {},
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Link.Verified/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Link.Verified.v1"
}
```

## Numbering.Allocated

A number was allocated from a counter.

- CloudEvents type: `tl.core.Numbering.Allocated.v1`
- Ledger payload class: `NumberingAllocatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `key` | string | yes | The key built. |
| `pattern` | string | yes | Numbering pattern id. |
| `prefix` | string or null | no | The key without its sequence. |
| `record_id` | string or null | no | The record the number was allocated for. |
| `record_type` | string or null | no | Record type. |
| `sequence` | integer | yes | The sequence number. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "key": "P123-REC-0001",
      "pattern": "rec",
      "prefix": "P123-REC-",
      "record_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "record_type": "core.Record",
      "sequence": 1
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Numbering.Allocated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Numbering.Allocated.v1"
}
```

## Pset.ValuesSet

Values of a property set were written on a record.

- CloudEvents type: `tl.core.Pset.ValuesSet.v1`
- Ledger payload class: `PsetValuesSetPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `conformance` | string or null | no | Conformance after the write: ok, warning, nonconformant or waived. |
| `effective_schema_hash` | string or null | no | Hash of the effective schema in force. |
| `layer` | string | yes | Pset layer: standard, custom or project. |
| `pset` | string | yes | Property-set name. |
| `units` | any | no | Units of the written properties, when the schema declares them. |
| `values` | any | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "psets.valve_data.size_in": [
        null,
        4
      ]
    },
    "detail": {
      "conformance": "ok",
      "effective_schema_hash": "9f2c",
      "layer": "standard",
      "pset": "valve_data",
      "units": {
        "size_in": "in"
      },
      "values": {
        "size_in": 4
      }
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Pset.ValuesSet/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Pset.ValuesSet.v1"
}
```

## Record.Corrected

A recorded value was corrected after the fact; history keeps the original.

- CloudEvents type: `tl.core.Record.Corrected.v1`
- Ledger payload class: `RecordCorrectedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `changes` | any | yes |  |
| `reason` | string | yes | Why it was corrected. |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "title": [
        "Gate vlave",
        "Gate valve"
      ]
    },
    "detail": {
      "changes": {
        "title": [
          "Gate vlave",
          "Gate valve"
        ]
      },
      "reason": "Typo"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Record.Corrected/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Record.Corrected.v1"
}
```

## Record.Created

A record was created.

- CloudEvents type: `tl.core.Record.Created.v1`
- Ledger payload class: `RecordCreatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `description` | string or null | no | Description. |
| `key` | string or null | no | Human-readable key; null until numbering assigns one. |
| `psets` | any | no | Initial property-set values keyed by pset name. |
| `record_type` | string | yes | Fully qualified record type. |
| `title` | string | yes | Title. |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "key": [
        null,
        "P123-REC-0001"
      ],
      "title": [
        null,
        "Gate valve 47-1234"
      ]
    },
    "detail": {
      "description": null,
      "key": "P123-REC-0001",
      "psets": {},
      "record_type": "core.Record",
      "title": "Gate valve 47-1234"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Record.Created/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Record.Created.v1"
}
```

## Record.Updated

One or more fields of a record changed.

- CloudEvents type: `tl.core.Record.Updated.v1`
- Ledger payload class: `RecordUpdatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `changes` | any | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "title": [
        "Gate valve",
        "Gate valve 47-1234"
      ]
    },
    "detail": {
      "changes": {
        "title": [
          "Gate valve",
          "Gate valve 47-1234"
        ]
      }
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Record.Updated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Record.Updated.v1"
}
```

## Record.Voided

A record was voided. The record stays in the ledger.

- CloudEvents type: `tl.core.Record.Voided.v1`
- Ledger payload class: `RecordVoidedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | Why it was voided. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Entered in error"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Record.Voided/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Record.Voided.v1"
}
```

## Schema.EffectiveChanged

The effective schema of a scope changed.

- CloudEvents type: `tl.core.Schema.EffectiveChanged.v1`
- Ledger payload class: `SchemaEffectiveChangedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `effective_schema_hash` | string | yes | New hash. |
| `packages` | array or null | no | Adopted packages as name@version. |
| `previous_hash` | string or null | no | Previous hash; null the first time. |
| `scope` | string | yes | Scope id. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "effective_schema_hash": "9f2c",
      "packages": [
        "co.acme.engineering@3.2.0"
      ],
      "previous_hash": null,
      "scope": "project:P123"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Schema.EffectiveChanged/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Schema.EffectiveChanged.v1"
}
```

## SchemaPackage.Published

A schema package version was published.

- CloudEvents type: `tl.core.SchemaPackage.Published.v1`
- Ledger payload class: `SchemaPackagePublishedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `package` | string | yes | Package name. |
| `version` | string | yes | Package version. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "package": "co.acme.engineering",
      "version": "3.2.0"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/SchemaPackage.Published/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.SchemaPackage.Published.v1"
}
```

## WebhookSubscription.Created

A webhook subscription was created. The signing secret is held outside the ledger.

- CloudEvents type: `tl.core.WebhookSubscription.Created.v1`
- Ledger payload class: `WebhookSubscriptionCreatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `event_schema_version` | string or null | no | Schema pin. |
| `expires_at` | string or null | no | ISO-8601 time after which the subscription stops. |
| `filter` | any | yes |  |
| `integration_app` | string or null | no | Integration app. |
| `name` | string | yes | Label. |
| `owner` | string | yes | Owner actor. |
| `payload_mode` | string | yes | thin, delta or full. |
| `secret_id` | string | yes | Id of the first signing secret (not the secret). |
| `subscription_id` | string | yes | Subscription id. |
| `target_url` | string | yes | Receiver URL. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "event_schema_version": "v1",
      "expires_at": null,
      "filter": {
        "event_types": [
          "Workflow.Transitioned"
        ],
        "transitions": [
          "* -> Issued"
        ]
      },
      "integration_app": null,
      "name": "NDE requests",
      "owner": "user:jsmith",
      "payload_mode": "delta",
      "secret_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB",
      "subscription_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA",
      "target_url": "https://nde.example.net/hooks/tl"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/WebhookSubscription.Created/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.WebhookSubscription.Created.v1"
}
```

## WebhookSubscription.Disabled

A subscription stopped receiving events.

- CloudEvents type: `tl.core.WebhookSubscription.Disabled.v1`
- Ledger payload class: `WebhookSubscriptionDisabledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `detail` | string or null | no | Free-text detail, for example the failure counts. |
| `reason` | string | yes | owner or sustained_failure. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "detail": "5 deliveries dead-lettered since the last success",
      "reason": "sustained_failure"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/WebhookSubscription.Disabled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.WebhookSubscription.Disabled.v1"
}
```

## WebhookSubscription.Enabled

A disabled subscription started receiving events again, from this event on.

- CloudEvents type: `tl.core.WebhookSubscription.Enabled.v1`
- Ledger payload class: `WebhookSubscriptionEnabledPayload`
- Version: 1

### Payload fields

No fields.

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {},
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/WebhookSubscription.Enabled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.WebhookSubscription.Enabled.v1"
}
```

## WebhookSubscription.SecretRotated

A new signing secret was issued; the previous one keeps signing until the overlap ends.

- CloudEvents type: `tl.core.WebhookSubscription.SecretRotated.v1`
- Ledger payload class: `WebhookSubscriptionSecretRotatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `previous_expires_at` | string or null | no | ISO-8601 time when the previous secret stops signing. |
| `previous_secret_id` | string or null | no | Id of the secret that is being replaced. |
| `secret_id` | string | yes | Id of the new secret (not the secret). |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "previous_expires_at": "2026-10-10T03:14:07.000000Z",
      "previous_secret_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PC",
      "secret_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/WebhookSubscription.SecretRotated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.WebhookSubscription.SecretRotated.v1"
}
```

## WebhookSubscription.Updated

A subscription's name, target, filter or payload mode changed.

- CloudEvents type: `tl.core.WebhookSubscription.Updated.v1`
- Ledger payload class: `WebhookSubscriptionUpdatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `changes` | any | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "changes": {
        "payload_mode": [
          "thin",
          "delta"
        ]
      }
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/WebhookSubscription.Updated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.WebhookSubscription.Updated.v1"
}
```

## Workflow.Transitioned

A record moved from one workflow state to another.

- CloudEvents type: `tl.core.Workflow.Transitioned.v1`
- Ledger payload class: `WorkflowTransitionedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `conformance` | string or null | no | Conformance after the transition. |
| `effective_schema_hash` | string or null | no | Hash of the effective schema in force. |
| `from_state` | string | yes | State before. |
| `guards_evaluated` | any | no | List of {kind, passed, message} for each guard that ran. |
| `reason` | string or null | no | Free-text reason. |
| `signature` | any | no | Signature data when the transition was signed. |
| `to_state` | string | yes | State after. |
| `transition` | string | yes | Transition name. |
| `workflow` | string | yes | Workflow id. |
| `workflow_version` | integer or null | no | Workflow version. |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "status": [
        "InReview",
        "Issued"
      ]
    },
    "detail": {
      "conformance": "ok",
      "effective_schema_hash": "9f2c",
      "from_state": "InReview",
      "guards_evaluated": [
        {
          "kind": "required_pset",
          "message": "",
          "passed": true
        }
      ],
      "reason": null,
      "signature": null,
      "to_state": "Issued",
      "transition": "issue",
      "workflow": "document",
      "workflow_version": 1
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Workflow.Transitioned/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Workflow.Transitioned.v1"
}
```
