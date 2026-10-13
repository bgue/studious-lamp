# Throughline event catalog

Every ledger event type that can reach a webhook subscriber, generated from the LinkML event classes. Each event arrives as a CloudEvents 1.0 JSON message signed with Standard Webhooks headers; the payload modes are `thin`, `delta` and `full`. Receivers dedupe on the event `id`. A request sent by `tl webhook test` carries the extra header `webhook-test: 1`; real deliveries never do.

## Event types

| Event type | CloudEvents type | Summary |
|---|---|---|
| [`Account.Created`](#accountcreated) | `tl.core.Account.Created.v1` | An account was created. |
| [`Account.Disabled`](#accountdisabled) | `tl.core.Account.Disabled.v1` | An account was disabled: it cannot sign in and its sessions and agent tokens stop working. |
| [`Account.Enabled`](#accountenabled) | `tl.core.Account.Enabled.v1` | A disabled account was enabled again. |
| [`Account.PasswordChanged`](#accountpasswordchanged) | `tl.core.Account.PasswordChanged.v1` | The password of an account was set or changed. |
| [`Account.RolesSet`](#accountrolesset) | `tl.core.Account.RolesSet.v1` | The roles of an account were replaced. |
| [`AgentToken.Issued`](#agenttokenissued) | `tl.core.AgentToken.Issued.v1` | An agent token was issued. |
| [`AgentToken.Revoked`](#agenttokenrevoked) | `tl.core.AgentToken.Revoked.v1` | An agent token was revoked and no longer authenticates. |
| [`CodeValue.Closed`](#codevalueclosed) | `tl.core.CodeValue.Closed.v1` | A code value was superseded by another or retired; it still resolves for old records. |
| [`CodeValue.Defined`](#codevaluedefined) | `tl.core.CodeValue.Defined.v1` | A value was added to a code list. |
| [`Feed.Edited`](#feededited) | `tl.core.Feed.Edited.v1` | A post was edited. |
| [`Feed.Posted`](#feedposted) | `tl.core.Feed.Posted.v1` | A post was made in a project feed. |
| [`Feed.Reacted`](#feedreacted) | `tl.core.Feed.Reacted.v1` | A reaction was set or cleared on a post. |
| [`Feed.Retracted`](#feedretracted) | `tl.core.Feed.Retracted.v1` | A post was retracted. |
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
| [`Proposal.Accepted`](#proposalaccepted) | `tl.core.Proposal.Accepted.v1` | A person accepted a proposal and its command ran in the same transaction. |
| [`Proposal.Created`](#proposalcreated) | `tl.core.Proposal.Created.v1` | An agent proposed a change. |
| [`Proposal.Failed`](#proposalfailed) | `tl.core.Proposal.Failed.v1` | A person accepted a proposal, but the command was refused (the record changed since, a guard failed). |
| [`Proposal.Rejected`](#proposalrejected) | `tl.core.Proposal.Rejected.v1` | A person rejected a proposal. |
| [`Pset.ValuesSet`](#psetvaluesset) | `tl.core.Pset.ValuesSet.v1` | Values of a property set were written on a record. |
| [`Record.BodyStored`](#recordbodystored) | `tl.core.Record.BodyStored.v1` | The body of an object-backed record was stored as a content-addressed object. |
| [`Record.Corrected`](#recordcorrected) | `tl.core.Record.Corrected.v1` | A recorded value was corrected after the fact; history keeps the original. |
| [`Record.Created`](#recordcreated) | `tl.core.Record.Created.v1` | A record was created. |
| [`Record.Updated`](#recordupdated) | `tl.core.Record.Updated.v1` | One or more fields of a record changed. |
| [`Record.Voided`](#recordvoided) | `tl.core.Record.Voided.v1` | A record was voided. |
| [`Schema.EffectiveChanged`](#schemaeffectivechanged) | `tl.core.Schema.EffectiveChanged.v1` | The effective schema of a scope changed. |
| [`SchemaPackage.Published`](#schemapackagepublished) | `tl.core.SchemaPackage.Published.v1` | A schema package version was published. |
| [`Setting.Changed`](#settingchanged) | `tl.core.Setting.Changed.v1` | One key was set, or reset to what the layer above gives, at one layer. |
| [`Setting.Locked`](#settinglocked) | `tl.core.Setting.Locked.v1` | The company locked a key for its projects, unlocked it, or changed the bounds projects must keep to. |
| [`Standard.Closed`](#standardclosed) | `tl.core.Standard.Closed.v1` | A registry entry was superseded by another or retired; it stays resolvable for history. |
| [`Standard.Defined`](#standarddefined) | `tl.core.Standard.Defined.v1` | A registry entry (a code list, a mnemonic or a numbering pattern) was defined. |
| [`Tag.Defined`](#tagdefined) | `tl.core.Tag.Defined.v1` | A tag was created, with its number parsed into segments and its class. |
| [`Tag.Reclassified`](#tagreclassified) | `tl.core.Tag.Reclassified.v1` | A tag moved to another class; the new class may bind other property sets. |
| [`Tag.Superseded`](#tagsuperseded) | `tl.core.Tag.Superseded.v1` | A tag was replaced by one or more others (a rename, a split or a merge); it stays in the ledger as history. |
| [`TagClass.Closed`](#tagclassclosed) | `tl.core.TagClass.Closed.v1` | A tag class was retired; tags already of that class keep it. |
| [`TagClass.Defined`](#tagclassdefined) | `tl.core.TagClass.Defined.v1` | A tag class was defined. |
| [`TagClass.Revised`](#tagclassrevised) | `tl.core.TagClass.Revised.v1` | A tag class changed. |
| [`TypeRegistration.Deprecated`](#typeregistrationdeprecated) | `tl.core.TypeRegistration.Deprecated.v1` | The owner retired a version. |
| [`TypeRegistration.Quarantined`](#typeregistrationquarantined) | `tl.core.TypeRegistration.Quarantined.v1` | A type package failed validation, or its files changed under a version that is already registered. |
| [`TypeRegistration.Registered`](#typeregistrationregistered) | `tl.core.TypeRegistration.Registered.v1` | A type package validated and was registered. |
| [`WebhookSubscription.Created`](#webhooksubscriptioncreated) | `tl.core.WebhookSubscription.Created.v1` | A webhook subscription was created. |
| [`WebhookSubscription.Disabled`](#webhooksubscriptiondisabled) | `tl.core.WebhookSubscription.Disabled.v1` | A subscription stopped receiving events. |
| [`WebhookSubscription.Enabled`](#webhooksubscriptionenabled) | `tl.core.WebhookSubscription.Enabled.v1` | A disabled subscription started receiving events again, from this event on. |
| [`WebhookSubscription.SecretRotated`](#webhooksubscriptionsecretrotated) | `tl.core.WebhookSubscription.SecretRotated.v1` | A new signing secret was issued; the previous one keeps signing until the overlap ends. |
| [`WebhookSubscription.Updated`](#webhooksubscriptionupdated) | `tl.core.WebhookSubscription.Updated.v1` | A subscription's name, target, filter or payload mode changed. |
| [`Workflow.Transitioned`](#workflowtransitioned) | `tl.core.Workflow.Transitioned.v1` | A record moved from one workflow state to another. |

## Account.Created

An account was created. A password, if any, is held outside the ledger. Internal: never delivered to webhooks.

- CloudEvents type: `tl.core.Account.Created.v1`
- Ledger payload class: `AccountCreatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | Account id. |
| `display_name` | string | yes | Name shown in lists. |
| `kind` | string | yes | person, agent or sim. |
| `roles` | any | yes |  |
| `username` | string | yes | Normalised username. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA",
      "display_name": "Demo User",
      "kind": "person",
      "roles": [
        "admin"
      ],
      "username": "demo"
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
  "dataschema": "https://tl.example.com/schema/events/Account.Created/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Account.Created.v1"
}
```

## Account.Disabled

An account was disabled: it cannot sign in and its sessions and agent tokens stop working. Internal: never delivered to webhooks.

- CloudEvents type: `tl.core.Account.Disabled.v1`
- Ledger payload class: `AccountDisabledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | Account id. |
| `reason` | string or null | no | Why it was disabled. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA",
      "reason": "left the project"
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
  "dataschema": "https://tl.example.com/schema/events/Account.Disabled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Account.Disabled.v1"
}
```

## Account.Enabled

A disabled account was enabled again. Internal: never delivered to webhooks.

- CloudEvents type: `tl.core.Account.Enabled.v1`
- Ledger payload class: `AccountEnabledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | Account id. |
| `reason` | string or null | no | Why it was enabled. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA",
      "reason": "returned"
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
  "dataschema": "https://tl.example.com/schema/events/Account.Enabled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Account.Enabled.v1"
}
```

## Account.PasswordChanged

The password of an account was set or changed. The event records that it happened, never the password or its hash. Internal: never delivered to webhooks.

- CloudEvents type: `tl.core.Account.PasswordChanged.v1`
- Ledger payload class: `AccountPasswordChangedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | Account id. |
| `by` | string | yes | Actor that changed it. |
| `forced` | boolean | yes | True for an admin reset or a bootstrap, false for the person changing their own. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA",
      "by": "user:demo",
      "forced": true
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
  "dataschema": "https://tl.example.com/schema/events/Account.PasswordChanged/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Account.PasswordChanged.v1"
}
```

## Account.RolesSet

The roles of an account were replaced. Internal: never delivered to webhooks.

- CloudEvents type: `tl.core.Account.RolesSet.v1`
- Ledger payload class: `AccountRolesSetPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | Account id. |
| `reason` | string or null | no | Why the roles changed. |
| `roles` | any | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA",
      "reason": "promoted to run the admin module",
      "roles": [
        "admin",
        "user"
      ]
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
  "dataschema": "https://tl.example.com/schema/events/Account.RolesSet/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Account.RolesSet.v1"
}
```

## AgentToken.Issued

An agent token was issued. The event holds its metadata; the token is shown once and stored only as a hash. Internal: never delivered to webhooks.

- CloudEvents type: `tl.core.AgentToken.Issued.v1`
- Ledger payload class: `AgentTokenIssuedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | The agent account. |
| `expires_at` | string or null | no | ISO-8601 time after which the token stops working; null for none. |
| `label` | string | yes | What the token is for. |
| `token_id` | string | yes | Token id. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB",
      "expires_at": "2027-01-09T03:14:07.000000Z",
      "label": "triage assistant",
      "token_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PC"
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
  "dataschema": "https://tl.example.com/schema/events/AgentToken.Issued/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.AgentToken.Issued.v1"
}
```

## AgentToken.Revoked

An agent token was revoked and no longer authenticates. Internal: never delivered to webhooks.

- CloudEvents type: `tl.core.AgentToken.Revoked.v1`
- Ledger payload class: `AgentTokenRevokedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | The agent account. |
| `reason` | string or null | no | Why it was revoked. |
| `token_id` | string | yes | Token id. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB",
      "reason": "rotated",
      "token_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PC"
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
  "dataschema": "https://tl.example.com/schema/events/AgentToken.Revoked/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.AgentToken.Revoked.v1"
}
```

## CodeValue.Closed

A code value was superseded by another or retired; it still resolves for old records.

- CloudEvents type: `tl.core.CodeValue.Closed.v1`
- Ledger payload class: `CodeValueClosedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `effective_to` | string or null | no | ISO date the value stops applying. |
| `lifecycle` | string | yes | superseded or retired. |
| `reason` | string | yes | Why. |
| `superseded_by` | string or null | no | Record id of the value that replaced this one. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "effective_to": null,
      "lifecycle": "retired",
      "reason": "No longer used on site",
      "superseded_by": null
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
  "dataschema": "https://tl.example.com/schema/events/CodeValue.Closed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.CodeValue.Closed.v1"
}
```

## CodeValue.Defined

A value was added to a code list.

- CloudEvents type: `tl.core.CodeValue.Defined.v1`
- Ledger payload class: `CodeValueDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `attributes` | any | no | List-specific content. |
| `code` | string | yes | The value's code. |
| `code_list` | string | yes | Code of the list. |
| `crosswalk` | string or null | no | The company code a project-added value maps to. |
| `edition` | string | yes | The standards edition that supplied the value. |
| `effective_from` | string or null | no | ISO date from which the value applies. |
| `effective_to` | string or null | no | ISO date after which it no longer applies. |
| `label` | string | yes | Display text. |
| `meaning` | string or null | no | IRI that says what the value means. |
| `origin` | string | yes | company or project. |
| `sort_order` | integer or null | no | Position in the list. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "attributes": {},
      "code": "PIP",
      "code_list": "Discipline",
      "crosswalk": null,
      "edition": "co.acme.standards@1.0.0",
      "effective_from": null,
      "effective_to": null,
      "label": "Piping",
      "meaning": null,
      "origin": "company",
      "sort_order": 10
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
  "dataschema": "https://tl.example.com/schema/events/CodeValue.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.CodeValue.Defined.v1"
}
```

## Feed.Edited

A post was edited. The payload is a full replacement of the body and its tags; the earlier text stays in the ledger, so edits are visible history (brief 21.1).

- CloudEvents type: `tl.core.Feed.Edited.v1`
- Ledger payload class: `FeedEditedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `body` | string | yes |  |
| `post_id` | string | yes |  |
| `record_ids` | array or null | no |  |
| `tags` | array or null | no |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "body": "Spool arrived, bevels damaged",
      "post_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "record_ids": [],
      "tags": []
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
  "dataschema": "https://tl.example.com/schema/events/Feed.Edited/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Feed.Edited.v1"
}
```

## Feed.Posted

A post was made in a project feed. It is the first event of the post stream. The projection derives the effective importance from `importance` and the tags.

- CloudEvents type: `tl.core.Feed.Posted.v1`
- Ledger payload class: `FeedPostedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `author` | string | yes | Actor that posted. |
| `body` | string | yes | Text of the post. |
| `importance` | string | yes | Importance the author gave. The projection derives the effective level from it and the tags. |
| `post_id` | string | yes |  |
| `record_ids` | array or null | no | Records the post references, without repeats. |
| `tags` | array or null | no | Tags found in the body, after resolution. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "author": "user:mlee",
      "body": "Spool arrived #P123-REC-0003 #hold",
      "importance": "normal",
      "post_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "record_ids": [
        "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
      ],
      "tags": [
        {
          "end": 28,
          "kind": "record",
          "namespace": null,
          "record_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
          "start": 14,
          "text": "P123-REC-0003"
        },
        {
          "end": 34,
          "kind": "signal",
          "namespace": null,
          "record_id": null,
          "start": 29,
          "text": "hold"
        }
      ]
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
  "dataschema": "https://tl.example.com/schema/events/Feed.Posted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Feed.Posted.v1"
}
```

## Feed.Reacted

A reaction was set or cleared on a post. The actor of the event sets (`on` true) or clears (`on` false) one acknowledgement. Reactions are limited to `ack`, `+1` and `resolved` (brief 21.1).

- CloudEvents type: `tl.core.Feed.Reacted.v1`
- Ledger payload class: `FeedReactedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `on` | boolean | yes | True to set the reaction, false to clear it. |
| `post_id` | string | yes |  |
| `reaction` | string | yes | One of `ack`, `+1`, `resolved`. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "on": true,
      "post_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "reaction": "ack"
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
  "dataschema": "https://tl.example.com/schema/events/Feed.Reacted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Feed.Reacted.v1"
}
```

## Feed.Retracted

A post was retracted. The projection keeps a tombstone row and drops the body.

- CloudEvents type: `tl.core.Feed.Retracted.v1`
- Ledger payload class: `FeedRetractedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `post_id` | string | yes |  |
| `reason` | string | yes | Why the post was retracted. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "post_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "reason": "Wrong project"
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
  "dataschema": "https://tl.example.com/schema/events/Feed.Retracted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Feed.Retracted.v1"
}
```

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

## Proposal.Accepted

A person accepted a proposal and its command ran in the same transaction.

- CloudEvents type: `tl.core.Proposal.Accepted.v1`
- Ledger payload class: `ProposalAcceptedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `by` | string | yes | The accepting person, `user:<id>`. |
| `proposal_id` | string | yes |  |
| `result_stream_id` | string | yes | Stream the command wrote to (the new record, the changed record, the link). |
| `result_version` | integer | yes | Stream version after the command. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "by": "user:mlee",
      "proposal_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "result_stream_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "result_version": 1
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
  "dataschema": "https://tl.example.com/schema/events/Proposal.Accepted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Proposal.Accepted.v1"
}
```

## Proposal.Created

An agent proposed a change. `command` is the command model as the agent built it, with `actor` set to the agent and `source` to `mcp:<agent>`; accepting re-runs it as the accepting person.

- CloudEvents type: `tl.core.Proposal.Created.v1`
- Ledger payload class: `ProposalCreatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `agent` | string | yes | The proposing actor, `agent:<id>`. |
| `command` | any | yes |  |
| `command_type` | string | yes | Name of the command model (`CreateRecord`, `SetPsetValues`, `AddLink`, `TransitionWorkflow`). |
| `proposal_id` | string | yes |  |
| `summary` | string | yes | One line for the review queue. |
| `tool` | string | yes | The MCP tool that was called (`create_record`, `update_psets`, `link_records`, `transition_workflow`). |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "agent": "agent:triage",
      "command": {
        "actor": "agent:triage",
        "numbering": {},
        "psets": {},
        "record_type": "core.Record",
        "scope": "project:P123",
        "source": "mcp:triage",
        "title": "Weld NCR"
      },
      "command_type": "CreateRecord",
      "proposal_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "summary": "Create record: Weld NCR",
      "tool": "create_record"
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
  "dataschema": "https://tl.example.com/schema/events/Proposal.Created/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Proposal.Created.v1"
}
```

## Proposal.Failed

A person accepted a proposal, but the command was refused (the record changed since, a guard failed). The command's own writes were rolled back; this event is written in a fresh transaction.

- CloudEvents type: `tl.core.Proposal.Failed.v1`
- Ledger payload class: `ProposalFailedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `by` | string | yes |  |
| `error` | string | yes | `<ErrorClass>: <message>` of the refusal. |
| `proposal_id` | string | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "by": "user:mlee",
      "error": "ConcurrencyError: expected version 3, stream is at 4",
      "proposal_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"
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
  "dataschema": "https://tl.example.com/schema/events/Proposal.Failed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Proposal.Failed.v1"
}
```

## Proposal.Rejected

A person rejected a proposal. Nothing else was written.

- CloudEvents type: `tl.core.Proposal.Rejected.v1`
- Ledger payload class: `ProposalRejectedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `by` | string | yes |  |
| `proposal_id` | string | yes |  |
| `reason` | string | yes | Why, for the agent and the audit trail. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "by": "user:mlee",
      "proposal_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "reason": "Duplicate of NCR-0042"
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
  "dataschema": "https://tl.example.com/schema/events/Proposal.Rejected/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Proposal.Rejected.v1"
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

## Record.BodyStored

The body of an object-backed record was stored as a content-addressed object. The body itself is never in the ledger. A new body is a new object (a new hash); the old one stays, and `previous_hash` chains the versions.

- CloudEvents type: `tl.core.Record.BodyStored.v1`
- Ledger payload class: `RecordBodyStoredPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `pointer` | any | yes |  |
| `previous_hash` | string or null | no | Hash of the body this one replaces; null for the first body. |
| `stream_id` | string | yes | The record (this stream). |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "pointer": {
        "hash": "9c1f0e3a5b7d2c4f6a8b0d1e3f5a7c9b2d4f6a8c0e1b3d5f7a9c2e4b6d8f0a1c",
        "schema_hash": "7a3b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b",
        "size": 412,
        "uri": "records/co.acme.LiftPlan/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5/9c1f0e3a5b7d2c4f6a8b0d1e3f5a7c9b2d4f6a8c0e1b3d5f7a9c2e4b6d8f0a1c.json"
      },
      "previous_hash": null,
      "stream_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"
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
  "dataschema": "https://tl.example.com/schema/events/Record.BodyStored/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Record.BodyStored.v1"
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

## Setting.Changed

One key was set, or reset to what the layer above gives, at one layer. The stream is `setting:<layer>:<key>`. A change with `applies_at` in the future takes effect then (and not before): resolution is time-based, so no job applies it.

- CloudEvents type: `tl.core.Setting.Changed.v1`
- Ledger payload class: `SettingChangedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `accept_risk` | boolean or null | no | The person confirmed "I accept the risk" (a `dangerous` key). |
| `applies_at` | string or null | no | When the change takes effect, if later than the time it was recorded. |
| `key` | string | yes | The setting key. |
| `layer` | string | yes | `company`, `project:<id>` or `user:<id>`. |
| `new_value` | any | no | The new value; null with `reset` true. |
| `old_set` | boolean or null | no | Whether the layer held a value of its own before (false: it was inheriting). |
| `old_value` | any | no | The value the layer held when the change was recorded (null when it held none). |
| `reason` | string or null | no | Why. Required for `advanced` and `dangerous` keys. |
| `reset` | boolean or null | no | True when the layer goes back to inheriting. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "accept_risk": false,
      "applies_at": null,
      "key": "feed.reactions.enabled",
      "layer": "project:P123",
      "new_value": false,
      "old_set": false,
      "old_value": null,
      "reason": null,
      "reset": false
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
  "dataschema": "https://tl.example.com/schema/events/Setting.Changed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Setting.Changed.v1"
}
```

## Setting.Locked

The company locked a key for its projects, unlocked it, or changed the bounds projects must keep to. The stream is `setting:company:<key>`.

- CloudEvents type: `tl.core.Setting.Locked.v1`
- Ledger payload class: `SettingLockedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `bounds` | any | no | Limits for project values: `minimum`, `maximum` and/or `choices`; null for none. |
| `key` | string | yes |  |
| `layer` | string | yes | Always `company`; only the company layer locks or bounds a key. |
| `locked` | boolean | yes | True when projects may not override the key. |
| `reason` | string | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "bounds": null,
      "key": "ai.agents.default_mode",
      "layer": "company",
      "locked": true,
      "reason": "Company policy: agents propose, people decide"
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
  "dataschema": "https://tl.example.com/schema/events/Setting.Locked/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Setting.Locked.v1"
}
```

## Standard.Closed

A registry entry was superseded by another or retired; it stays resolvable for history.

- CloudEvents type: `tl.core.Standard.Closed.v1`
- Ledger payload class: `StandardClosedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `effective_to` | string or null | no | ISO date the entry stops applying. |
| `lifecycle` | string | yes | superseded or retired. |
| `reason` | string | yes | Why. |
| `superseded_by` | string or null | no | Record id of the entry that replaced this one. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "effective_to": "2027-01-01",
      "lifecycle": "superseded",
      "reason": "Edition 2 replaces the pattern",
      "superseded_by": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
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
  "dataschema": "https://tl.example.com/schema/events/Standard.Closed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Standard.Closed.v1"
}
```

## Standard.Defined

A registry entry (a code list, a mnemonic or a numbering pattern) was defined.

- CloudEvents type: `tl.core.Standard.Defined.v1`
- Ledger payload class: `StandardDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `adoption` | string or null | no | mandatory, default or optional. |
| `code` | string | yes | The entry's code within its kind. |
| `data` | any | no | Kind-specific content. |
| `definition` | string or null | no | What the entry means or governs. |
| `edition` | string | yes | The standards edition that supplied it. |
| `effective_from` | string or null | no | ISO date from which the entry applies. |
| `effective_to` | string or null | no | ISO date after which it no longer applies. |
| `kind` | string | yes | code_list, mnemonic or numbering_pattern. |
| `label` | string | yes | Display name or meaning. |
| `owner` | string or null | no | Steward of the entry. |
| `value_list_policy` | string or null | no | Code lists only: closed, extensible or project_defined. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "adoption": "mandatory",
      "code": "FV",
      "data": {
        "class_hint": "ControlValve"
      },
      "definition": null,
      "edition": "co.acme.standards@1.0.0",
      "effective_from": null,
      "effective_to": null,
      "kind": "mnemonic",
      "label": "Flow control valve",
      "owner": "role:standards-steward",
      "value_list_policy": null
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
  "dataschema": "https://tl.example.com/schema/events/Standard.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Standard.Defined.v1"
}
```

## Tag.Defined

A tag was created, with its number parsed into segments and its class.

- CloudEvents type: `tl.core.Tag.Defined.v1`
- Ledger payload class: `TagDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `area` | string or null | no | The area or unit segment. |
| `bound_psets` | any | no | Pset names the class binds to the tag. |
| `class_code` | string or null | no | Code of the tag's class; null until classified. |
| `conformance` | string or null | no | Conformance of the new tag: ok, warning, nonconformant or waived. |
| `effective_schema_hash` | string or null | no | Hash of the effective schema in force. |
| `mnemonic` | string or null | no | The mnemonic segment. |
| `number` | string | yes | The tag number. |
| `number_status` | string | yes | ok or violation. |
| `origin` | string | yes | created, import, rename, split or merge. |
| `pattern_code` | string or null | no | Code of the numbering pattern the number was checked against. |
| `segments` | any | no | Every parsed segment by name. |
| `sequence` | integer or null | no | The sequence segment. |
| `supersedes` | any | no | Record ids of the tags this one replaces. |
| `violations` | any | no | The problems found in the number. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "area": "47",
      "bound_psets": [
        "valve_data"
      ],
      "class_code": "ControlValve",
      "conformance": "nonconformant",
      "effective_schema_hash": "9f2c",
      "mnemonic": "FV",
      "number": "47-FV-1001",
      "number_status": "ok",
      "origin": "created",
      "pattern_code": "tag",
      "segments": {
        "area": "47",
        "mnemonic": "FV",
        "seq": "1001"
      },
      "sequence": 1001,
      "supersedes": [],
      "violations": []
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
  "dataschema": "https://tl.example.com/schema/events/Tag.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Tag.Defined.v1"
}
```

## Tag.Reclassified

A tag moved to another class; the new class may bind other property sets.

- CloudEvents type: `tl.core.Tag.Reclassified.v1`
- Ledger payload class: `TagReclassifiedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `bound_psets` | any | no | Pset names the new class binds. |
| `conformance` | string or null | no | Conformance after the change. |
| `effective_schema_hash` | string or null | no | Hash of the effective schema in force. |
| `from_class` | string or null | no | The previous class code; null when the tag had none. |
| `reason` | string or null | no | Why. |
| `to_class` | string | yes | The new class code. |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "class_code": [
        "ManualValve",
        "ControlValve"
      ]
    },
    "detail": {
      "bound_psets": [
        "valve_data"
      ],
      "conformance": "nonconformant",
      "effective_schema_hash": "9f2c",
      "from_class": "ManualValve",
      "reason": "Actuator added",
      "to_class": "ControlValve"
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
  "dataschema": "https://tl.example.com/schema/events/Tag.Reclassified/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Tag.Reclassified.v1"
}
```

## Tag.Superseded

A tag was replaced by one or more others (a rename, a split or a merge); it stays in the ledger as history.

- CloudEvents type: `tl.core.Tag.Superseded.v1`
- Ledger payload class: `TagSupersededPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `operation` | string | yes | rename, split or merge. |
| `reason` | string | yes | Why. |
| `superseded_by` | any | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "operation": "rename",
      "reason": "P&ID revision 3 renumbers the loop",
      "superseded_by": [
        "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
      ]
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
  "dataschema": "https://tl.example.com/schema/events/Tag.Superseded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Tag.Superseded.v1"
}
```

## TagClass.Closed

A tag class was retired; tags already of that class keep it.

- CloudEvents type: `tl.core.TagClass.Closed.v1`
- Ledger payload class: `TagClassClosedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `lifecycle` | string | yes | superseded or retired. |
| `reason` | string | yes | Why. |
| `superseded_by` | string or null | no | Record id of the class that replaced this one. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "lifecycle": "retired",
      "reason": "Merged into ControlValve",
      "superseded_by": null
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
  "dataschema": "https://tl.example.com/schema/events/TagClass.Closed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.TagClass.Closed.v1"
}
```

## TagClass.Defined

A tag class was defined.

- CloudEvents type: `tl.core.TagClass.Defined.v1`
- Ledger payload class: `TagClassDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | string | yes | The class code. |
| `edition` | string | yes | The standards edition that supplied the class. |
| `family` | string | yes | instrument, valve, pump, line, equipment, cable or other. |
| `itr_templates` | any | no | ITR template references. |
| `label` | string | yes | Display name. |
| `mnemonics` | any | no | Mnemonic codes that normally identify this class. |
| `required_psets` | any | no | Pset names a tag of this class must carry. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "code": "ControlValve",
      "edition": "co.acme.standards@1.0.0",
      "family": "valve",
      "itr_templates": [
        "ITR-VALVE-01"
      ],
      "label": "Control valve",
      "mnemonics": [
        "FV"
      ],
      "required_psets": [
        "valve_data"
      ]
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
  "dataschema": "https://tl.example.com/schema/events/TagClass.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.TagClass.Defined.v1"
}
```

## TagClass.Revised

A tag class changed. Adding a required pset is a constraining change: existing tags are flagged, not rewritten.

- CloudEvents type: `tl.core.TagClass.Revised.v1`
- Ledger payload class: `TagClassRevisedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `changes` | any | yes |  |
| `reason` | string | yes | Why it changed. |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "required_psets": [
        [
          "valve_data"
        ],
        [
          "valve_data",
          "safety_data"
        ]
      ]
    },
    "detail": {
      "changes": {
        "required_psets": [
          [
            "valve_data"
          ],
          [
            "valve_data",
            "safety_data"
          ]
        ]
      },
      "reason": "SIS valves need safety data"
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
  "dataschema": "https://tl.example.com/schema/events/TagClass.Revised/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.TagClass.Revised.v1"
}
```

## TypeRegistration.Deprecated

The owner retired a version. Existing instances stay readable and editable; no new instance can be created.

- CloudEvents type: `tl.core.TypeRegistration.Deprecated.v1`
- Ledger payload class: `TypeRegistrationDeprecatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | Why. |
| `type_ref` | string | yes | The deprecated version. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "superseded by 2.0.0",
      "type_ref": "co.acme.LiftPlan@1.0.0"
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
  "dataschema": "https://tl.example.com/schema/events/TypeRegistration.Deprecated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.TypeRegistration.Deprecated.v1"
}
```

## TypeRegistration.Quarantined

A type package failed validation, or its files changed under a version that is already registered. The report lists every problem (`kind`, `path`, `detail`). A conflict never removes a registration that is already active.

- CloudEvents type: `tl.core.TypeRegistration.Quarantined.v1`
- Ledger payload class: `TypeRegistrationQuarantinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `content_hash` | string | yes | sha256 over the canonical `type.lock` form of the files as found. |
| `location_uri` | string | yes | Where the package files are. |
| `report` | any | yes |  |
| `type_ref` | string | yes | `<namespace>.<name>@<version>`, or `invalid:<relative path>` when the path is not a package path. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "content_hash": "4d1c0a0f9f43b3a0a0f3a6a6b9d3f0a5c8e5d9b2f1a7c3e6d4b8a2f9c1e7d0b3",
      "location_uri": "file:///srv/types/co.acme/LiftPlan/1.0.1",
      "report": [
        {
          "detail": "examples/bad.json: 'risk_class' is not one of ['low', 'medium', 'high']",
          "kind": "example",
          "path": "examples/bad.json"
        }
      ],
      "type_ref": "co.acme.LiftPlan@1.0.1"
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
  "dataschema": "https://tl.example.com/schema/events/TypeRegistration.Quarantined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.TypeRegistration.Quarantined.v1"
}
```

## TypeRegistration.Registered

A type package validated and was registered. The package files stay where they are; this event holds metadata only. `content_hash` is the sha256 of the canonical bytes of the package's `type.lock`.

- CloudEvents type: `tl.core.TypeRegistration.Registered.v1`
- Ledger payload class: `TypeRegistrationRegisteredPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `content_hash` | string | yes | sha256 over the canonical bytes of `type.lock`. |
| `index_fields` | array or null | no | Slots annotated `tl:index`: the query contract. |
| `location_uri` | string | yes | Where the package files are, for example `file:///srv/types/co.acme/LiftPlan/1.0.0`. |
| `name` | string | yes | Type name, UpperCamelCase, for example `LiftPlan`. |
| `namespace` | string | yes | Namespace, dotted lower-case segments, for example `co.acme`. |
| `owner` | string | yes | Actor that registered the package. |
| `schema_hash` | string | yes | Hash of the compiled class: the schema a stored body validated against. |
| `status` | string | yes | `active` for this event. |
| `storage_mode` | string | yes | `managed` or `object-backed` in v0. |
| `type_ref` | string | yes | `<namespace>.<name>@<version>`. |
| `version` | string | yes | Semantic version `MAJOR.MINOR.PATCH`. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "content_hash": "4d1c0a0f9f43b3a0a0f3a6a6b9d3f0a5c8e5d9b2f1a7c3e6d4b8a2f9c1e7d0b3",
      "index_fields": [
        "crane",
        "lift_date",
        "risk_class"
      ],
      "location_uri": "file:///srv/types/co.acme/LiftPlan/1.0.0",
      "name": "LiftPlan",
      "namespace": "co.acme",
      "owner": "user:alice",
      "schema_hash": "7a3b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b",
      "status": "active",
      "storage_mode": "object-backed",
      "type_ref": "co.acme.LiftPlan@1.0.0",
      "version": "1.0.0"
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
  "dataschema": "https://tl.example.com/schema/events/TypeRegistration.Registered/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.TypeRegistration.Registered.v1"
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
