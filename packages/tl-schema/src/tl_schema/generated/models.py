from __future__ import annotations

import re
import sys
from datetime import (
    date,
    datetime,
    time
)
from decimal import Decimal
from enum import Enum
from typing import (
    Any,
    ClassVar,
    Literal,
    Optional,
    Union
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer
)


metamodel_version = "1.12.0"
version = "None"


class ConfiguredBaseModel(BaseModel):
    model_config = ConfigDict(
        serialize_by_alias = True,
        validate_by_name = True,
        validate_assignment = True,
        validate_default = True,
        extra = "forbid",
        arbitrary_types_allowed = True,
        use_enum_values = True,
        strict = False,
    )





class LinkMLMeta(RootModel):
    root: dict[str, Any] = {}
    model_config = ConfigDict(frozen=True)

    def __getattr__(self, key:str):
        return getattr(self.root, key)

    def __getitem__(self, key:str):
        return self.root[key]

    def __setitem__(self, key:str, value):
        self.root[key] = value

    def __contains__(self, key:str) -> bool:
        return key in self.root


linkml_meta = LinkMLMeta({'default_prefix': 'throughline',
     'default_range': 'string',
     'description': 'Root of the core schema. Generators run over this file; it '
                    'only imports. Later increments add psets, links, files, '
                    'workflow, feed, integration and settings here.',
     'id': 'https://example.org/throughline/core',
     'imports': ['linkml:types',
                 'annotations',
                 'record',
                 'ledger',
                 'psets',
                 'links',
                 'numbering',
                 'workflow',
                 'feed',
                 'proposals',
                 'files',
                 'integration',
                 'outbox',
                 'events'],
     'name': 'tl_core',
     'prefixes': {'linkml': {'prefix_prefix': 'linkml',
                             'prefix_reference': 'https://w3id.org/linkml/'},
                  'throughline': {'prefix_prefix': 'throughline',
                                  'prefix_reference': 'https://example.org/throughline/'}},
     'source_file': 'core.yaml',
     'title': 'Throughline core schema'} )

class ConformanceStatus(str, Enum):
    """
    Result of evaluating a record against its effective schema (brief 6.3).
    """
    ok = "ok"
    warning = "warning"
    nonconformant = "nonconformant"
    waived = "waived"


class PsetLayer(str, Enum):
    """
    Layer a pset value belongs to (brief 6.3).
    """
    standard = "standard"
    custom = "custom"
    project = "project"
    enrichment = "enrichment"
    source = "source"


class PsetValueType(str, Enum):
    """
    Which typed value column holds the value.
    """
    string = "string"
    number = "number"
    boolean = "boolean"
    json = "json"


class LinkStatus(str, Enum):
    """
    Lifecycle state of a link (brief 7.1).
    """
    suggested = "suggested"
    active = "active"
    stale = "stale"
    broken = "broken"
    retracted = "retracted"


class LinkSource(str, Enum):
    """
    How a link came to exist (brief 7.1).
    """
    manual = "manual"
    key_detected = "key_detected"
    tray = "tray"
    bulk = "bulk"
    model_selection = "model_selection"
    thread_dispatch = "thread_dispatch"
    rule = "rule"
    enricher = "enricher"
    import_ = "import"
    mapping = "mapping"


class LinkRelation(str, Enum):
    """
    Built-in relation codes (brief 7.1). Documentation only: the vocabulary is extensible, so link rows store the code as a string.
    """
    references = "references"
    derived_from = "derived_from"
    supersedes = "supersedes"
    responds_to = "responds_to"
    raised_against = "raised_against"
    resolves = "resolves"
    belongs_to = "belongs_to"
    requires = "requires"
    blocks = "blocks"
    verifies = "verifies"
    dispatched_from = "dispatched_from"
    attached_to = "attached_to"
    same_as = "same_as"


class FeedItemType(str, Enum):
    """
    What a row of `cur_feed_items` is.
    """
    post = "post"
    card = "card"


class TagKind(str, Enum):
    """
    Kind of a `#tag` or `@mention` (brief 21.2). Precedence when a token fits several kinds: mention, record, code, signal, topic. A record-like tag that matches no record is a topic.
    """
    record = "record"
    code = "code"
    signal = "signal"
    topic = "topic"
    mention = "mention"


class Importance(str, Enum):
    """
    Noise-control level (brief 21.3). System cards are low, posts normal, signal tags high.
    """
    low = "low"
    normal = "normal"
    high = "high"


class ProposalStatus(str, Enum):
    """
    Where a proposal is in its life.
    """
    pending = "pending"
    """
    Waiting for a person to accept or reject it.
    """
    accepted = "accepted"
    """
    A person accepted it and the command ran.
    """
    rejected = "rejected"
    """
    A person rejected it; the command never ran.
    """
    failed = "failed"
    """
    A person accepted it, but the command was refused (stale version, failed guard).
    """


class FileStatus(str, Enum):
    """
    Where a file is in its quarantine lifecycle (brief 20.2).
    """
    quarantined = "quarantined"
    """
    Stored and verified, scan not yet passed. Only the uploader can read it.
    """
    available = "available"
    """
    The scan passed (`File.Processed`). Readable by anyone who can read the record.
    """
    rejected = "rejected"
    """
    The scan or a processing step refused it (`File.Rejected`). Unreadable; terminal.
    """


class FileSlotCardinality(str, Enum):
    """
    How many current files a slot holds (brief 20.1).
    """
    one = "one"
    """
    A new available file supersedes the previous current file.
    """
    many = "many"
    """
    Every available file is current.
    """


class CaptureHint(str, Enum):
    """
    How a client should capture a file for a slot (brief 20.1).
    """
    camera = "camera"
    scan = "scan"
    file = "file"


class PayloadMode(str, Enum):
    """
    How much of the record a webhook carries (brief 18.3). Restricted confidentiality forces `thin`.
    """
    thin = "thin"
    """
    Envelope and origin only; the receiver fetches what it needs.
    """
    delta = "delta"
    """
    Thin plus `changes`, the immediate `links` and the event `detail`.
    """
    full = "full"
    """
    Delta plus the record projection (`record`) as of delivery preparation.
    """


class SubscriptionStatus(str, Enum):
    """
    Whether a subscription receives events.
    """
    active = "active"
    disabled = "disabled"
    """
    Paused by its owner or auto-disabled after sustained failure; see `disabled_reason`.
    """


class DisabledReason(str, Enum):
    """
    Why a subscription is disabled.
    """
    owner = "owner"
    """
    An owner or operator disabled it.
    """
    sustained_failure = "sustained_failure"
    """
    Dead-lettered deliveries or a long failing period; the owner is to be notified.
    """


class DeliveryStatus(str, Enum):
    """
    Where one webhook delivery is in its life.
    """
    pending = "pending"
    """
    Waiting for its first or next attempt (see `next_attempt_at`).
    """
    delivered = "delivered"
    """
    The receiver answered 2xx.
    """
    dead = "dead"
    """
    Retries are exhausted or the failure is permanent; the delivery is in the dead-letter queue.
    """
    redriven = "redriven"
    """
    A dead delivery that an operator re-enqueued; a new delivery carries on.
    """


class DeliveryOrigin(str, Enum):
    """
    Why a delivery row exists.
    """
    live = "live"
    """
    Created by the dispatcher when the event was committed.
    """
    replay = "replay"
    """
    Created by an operator's replay of a seq range.
    """
    redrive = "redrive"
    """
    Created by an operator's redrive of dead-lettered deliveries.
    """


class SecretState(str, Enum):
    """
    Whether a signing secret is still used.
    """
    active = "active"
    """
    Signs deliveries; during a rotation overlap the previous secret stays active until `expires_at`.
    """
    retired = "retired"
    """
    No longer used.
    """



class RecordEnvelope(ConfiguredBaseModel):
    """
    Fields every record type shares (brief 6.2). Mixed into each concrete record class.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True, 'from_schema': 'https://example.org/throughline/core/record'})

    id: str = Field(default=..., description="""Immutable global identifier; equals the ledger `stream_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'EventOrigin', 'EventLinkRef', 'CloudEvent']} })
    key: Optional[str] = Field(default=None, description="""Human-readable number, unique within a scope. Null until numbering assigns one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'EventOrigin',
                       'EventLinkRef']} })
    type: str = Field(default=..., description="""Fully qualified record type, for example `core.Record`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'EventOrigin', 'EventLinkRef', 'CloudEvent']} })
    scope: str = Field(default=..., description="""`company` or `project:<id>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'SchemaEffectiveChangedPayload',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'OutboxEvent']} })
    title: str = Field(default=..., description="""Short human-readable title.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'RecordCreatedPayload']} })
    description: Optional[str] = Field(default=None, description="""Longer free-text description.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'RecordCreatedPayload']} })
    status: Optional[str] = Field(default=None, description="""Workflow state; null when the record type has no workflow.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt']} })
    psets: Any = Field(default=..., description="""Property-set values keyed by pset name, stored as a JSON object.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordEnvelope', 'RecordCreatedPayload']} })
    voided: bool = Field(default=False, description="""Set by `Record.Voided`. Voided rows are never deleted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope'], 'ifabsent': 'false'} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'WebhookCursor']} })
    effective_schema_hash: Optional[str] = Field(default=None, description="""Hash of the effective schema in force at the last write; null before Increment 2.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValuesSetPayload',
                       'WorkflowTransitionedPayload',
                       'SchemaEffectiveChangedPayload']} })
    conformance: ConformanceStatus = Field(default=ConformanceStatus("ok"), description="""Conformance of the current values to the effective schema.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValuesSetPayload',
                       'WorkflowTransitionedPayload'],
         'ifabsent': 'string(ok)'} })
    created_at: datetime  = Field(default=..., description="""Timestamp of the creating event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookSecret']} })
    updated_at: datetime  = Field(default=..., description="""Timestamp of the last applied event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription']} })


class Record(RecordEnvelope):
    """
    The generic Phase 0 record type, `core.Record`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state',
                                              'value': True}},
         'from_schema': 'https://example.org/throughline/core/record',
         'unique_keys': {'scope_key': {'description': 'A key is unique within its '
                                                      'scope.',
                                       'unique_key_name': 'scope_key',
                                       'unique_key_slots': ['scope', 'key']}}})

    id: str = Field(default=..., description="""Immutable global identifier; equals the ledger `stream_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'EventOrigin', 'EventLinkRef', 'CloudEvent']} })
    key: Optional[str] = Field(default=None, description="""Human-readable number, unique within a scope. Null until numbering assigns one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'EventOrigin',
                       'EventLinkRef']} })
    type: str = Field(default=..., description="""Fully qualified record type, for example `core.Record`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'EventOrigin', 'EventLinkRef', 'CloudEvent']} })
    scope: str = Field(default=..., description="""`company` or `project:<id>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'SchemaEffectiveChangedPayload',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'OutboxEvent']} })
    title: str = Field(default=..., description="""Short human-readable title.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'RecordCreatedPayload']} })
    description: Optional[str] = Field(default=None, description="""Longer free-text description.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'RecordCreatedPayload']} })
    status: Optional[str] = Field(default=None, description="""Workflow state; null when the record type has no workflow.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt']} })
    psets: Any = Field(default=..., description="""Property-set values keyed by pset name, stored as a JSON object.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordEnvelope', 'RecordCreatedPayload']} })
    voided: bool = Field(default=False, description="""Set by `Record.Voided`. Voided rows are never deleted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope'], 'ifabsent': 'false'} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'WebhookCursor']} })
    effective_schema_hash: Optional[str] = Field(default=None, description="""Hash of the effective schema in force at the last write; null before Increment 2.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValuesSetPayload',
                       'WorkflowTransitionedPayload',
                       'SchemaEffectiveChangedPayload']} })
    conformance: ConformanceStatus = Field(default=ConformanceStatus("ok"), description="""Conformance of the current values to the effective schema.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValuesSetPayload',
                       'WorkflowTransitionedPayload'],
         'ifabsent': 'string(ok)'} })
    created_at: datetime  = Field(default=..., description="""Timestamp of the creating event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookSecret']} })
    updated_at: datetime  = Field(default=..., description="""Timestamp of the last applied event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription']} })


class Event(ConfiguredBaseModel):
    """
    One immutable ledger event.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/ledger'})

    seq: int = Field(default=..., description="""Global monotonic sequence; the ordering backbone.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'OutboxEvent',
                       'WebhookDelivery']} })
    event_id: str = Field(default=..., description="""Unique event identifier (ULID).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent', 'WebhookDelivery']} })
    stream_id: str = Field(default=..., description="""The record (aggregate) the event belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent']} })
    stream_type: str = Field(default=..., description="""Record type of the stream, for example `core.Record`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent']} })
    stream_version: int = Field(default=..., description="""Per-stream version, used for optimistic concurrency.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent']} })
    event_type: str = Field(default=..., description="""`<Class>.<PastTenseVerb>`, for example `Record.Created`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'EventCard', 'FeedItemRow', 'OutboxEvent']} })
    schema_version: int = Field(default=1, description="""Version of the event payload schema, for upcasting.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent'], 'ifabsent': 'int(1)'} })
    scope: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'SchemaEffectiveChangedPayload',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'OutboxEvent']} })
    payload: Any = Field(default=..., description="""Event payload, a JSON object validated against the event type's schema.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['Event']} })
    actor: str = Field(default=..., description="""`user:<id>`, `svc:<name>` or `agent:<id>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'EventCard', 'FeedItemRow', 'OutboxEvent']} })
    recorded_at: datetime  = Field(default=..., description="""System (transaction) time.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent']} })
    effective_at: datetime  = Field(default=..., description="""Business (valid) time.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    correlation_id: str = Field(default=..., description="""Ties a command chain, import, or automated process together.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent']} })
    causation_id: Optional[str] = Field(default=None, description="""Identifier of the event or command that caused this one; may be null.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    source: str = Field(default=..., description="""`tui`, `api`, `mcp:<agent>`, `cli`, `import:<job>` or `sim:<run>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'CloudEvent',
                       'OutboxEvent']} })
    prev_hash: Optional[str] = Field(default=None, description="""Hash of the previous event in the same scope; null for the first.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    hash: str = Field(default=..., description="""Hash of this event chained to `prev_hash`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })


class PsetValue(ConfiguredBaseModel):
    """
    One current pset value of one record, addressed by its layer-aware path.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_pset_values'}},
         'from_schema': 'https://example.org/throughline/core/psets',
         'unique_keys': {'record_path': {'description': 'A record has one current '
                                                        'value per path.',
                                         'unique_key_name': 'record_path',
                                         'unique_key_slots': ['record_id', 'path']}}})

    record_id: str = Field(default=..., description="""The record (ledger stream) the value belongs to.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['PsetValue',
                       'LinkCount',
                       'WorkflowState',
                       'NumberingAllocatedPayload',
                       'FileUploadedPayload',
                       'FeedTag',
                       'Hashtag',
                       'File']} })
    scope: str = Field(default=..., description="""Scope of the record, repeated so scope-wide filters need no join.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'SchemaEffectiveChangedPayload',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'OutboxEvent']} })
    path: str = Field(default=..., description="""Layer-aware path, for example `psets.valve_data.x.fat_witness_by`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['PsetValue']} })
    pset: str = Field(default=..., description="""Pset name, for example `valve_data` or `prj.shutdown_tie_in`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue', 'PsetValuesSetPayload']} })
    property_name: str = Field(default=..., description="""Property relative to the pset; custom-section properties start with `x.`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue']} })
    layer: PsetLayer = Field(default=..., description="""Layer derived from the path.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue', 'PsetValuesSetPayload']} })
    value_type: PsetValueType = Field(default=..., description="""Which of the typed value columns is set.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue']} })
    value_text: Optional[str] = Field(default=None, description="""String values.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue']} })
    value_num: Optional[float] = Field(default=None, description="""Integer and decimal values.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue']} })
    value_bool: Optional[bool] = Field(default=None, description="""Boolean values.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue']} })
    value_json: Optional[Any] = Field(default=None, description="""Lists and other structured values.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:column': {'tag': 'tl:column', 'value': 'value_json'},
                         'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['PsetValue']} })
    unit: Optional[str] = Field(default=None, description="""UCUM unit recorded with the value, when the schema declared one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the event that last set the row.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'WebhookCursor']} })
    updated_at: datetime  = Field(default=..., description="""Timestamp of that event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription']} })


class Link(ConfiguredBaseModel):
    """
    One link between two records, in its current lifecycle state.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_links'}},
         'from_schema': 'https://example.org/throughline/core/links'})

    link_id: str = Field(default=..., description="""Immutable link identifier; equals the ledger `stream_id` of the link.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link']} })
    scope: str = Field(default=..., description="""Scope of the link, which is the scope of its `from` record.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'SchemaEffectiveChangedPayload',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'OutboxEvent']} })
    from_id: str = Field(default=..., description="""The record the link starts at (the subject of the relation).""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['Link']} })
    to_id: str = Field(default=..., description="""The record the link points to.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['Link']} })
    relation: str = Field(default=..., description="""Forward relation code, for example `raised_against`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link', 'LinkAddedPayload', 'LinkSuggestedPayload']} })
    status: LinkStatus = Field(default=LinkStatus("active"), description="""Lifecycle state.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt'],
         'ifabsent': 'string(active)'} })
    pin: Optional[str] = Field(default=None, description="""Revision the link is pinned to; null means floating to the current revision.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'LinkRepinnedPayload']} })
    note: Optional[str] = Field(default=None, description="""Optional free text.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'LinkAcceptedPayload']} })
    source: LinkSource = Field(default=..., description="""How the link was created.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'CloudEvent',
                       'OutboxEvent']} })
    confidence: Optional[float] = Field(default=None, description="""Confidence of a suggested link, between 0 and 1.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link', 'LinkAddedPayload', 'LinkSuggestedPayload']} })
    reason: Optional[str] = Field(default=None, description="""Reason given with the last flag, decline, or retraction.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'File']} })
    declined: bool = Field(default=False, description="""True when the link was a suggestion that a person declined. Declines are remembered.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link'], 'ifabsent': 'false'} })
    verified_by: Optional[str] = Field(default=None, description="""Actor of the last `Link.Verified` event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link']} })
    verified_at: Optional[datetime ] = Field(default=None, description="""Time of the last `Link.Verified` event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link']} })
    created_by: str = Field(default=..., description="""Actor of the creating event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link', 'WebhookSubscription']} })
    created_at: datetime  = Field(default=..., description="""Time of the creating event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookSecret']} })
    updated_at: datetime  = Field(default=..., description="""Time of the last applied event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription']} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'WebhookCursor']} })


class LinkCount(ConfiguredBaseModel):
    """
    Per-record link counts, maintained with `cur_links` (brief 7.4).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_link_counts'}},
         'from_schema': 'https://example.org/throughline/core/links'})

    record_id: str = Field(default=..., description="""The record the counts belong to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue',
                       'LinkCount',
                       'WorkflowState',
                       'NumberingAllocatedPayload',
                       'FileUploadedPayload',
                       'FeedTag',
                       'Hashtag',
                       'File']} })
    scope: str = Field(default=..., description="""Scope of the record.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'SchemaEffectiveChangedPayload',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'OutboxEvent']} })
    active_out: int = Field(default=0, description="""Active links that start at the record.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LinkCount'], 'ifabsent': 'int(0)'} })
    active_in: int = Field(default=0, description="""Active links that point to the record.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LinkCount'], 'ifabsent': 'int(0)'} })
    stale: int = Field(default=0, description="""Stale links in either direction.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LinkCount'], 'ifabsent': 'int(0)'} })
    broken: int = Field(default=0, description="""Broken links in either direction.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LinkCount'], 'ifabsent': 'int(0)'} })
    suggested: int = Field(default=0, description="""Suggested links in either direction.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LinkCount'], 'ifabsent': 'int(0)'} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last event that touched the counts.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'WebhookCursor']} })


class NumberingCounter(ConfiguredBaseModel):
    """
    The last sequence number allocated for one counter.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_numbering'}},
         'from_schema': 'https://example.org/throughline/core/numbering'})

    counter_id: str = Field(default=..., description="""Ledger stream id of the counter, `numbering:<scope>:<pattern>:<prefix>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    scope: str = Field(default=..., description="""Scope the counter belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'SchemaEffectiveChangedPayload',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'OutboxEvent']} })
    pattern: str = Field(default=..., description="""Identifier of the numbering pattern.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter', 'NumberingAllocatedPayload']} })
    prefix: str = Field(default=..., description="""The rendered key without its sequence number, for example `P123-REC-`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter', 'NumberingAllocatedPayload']} })
    last_sequence: int = Field(default=..., description="""The highest sequence number allocated so far.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    last_key: str = Field(default=..., description="""The key built from `last_sequence`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    last_record_id: Optional[str] = Field(default=None, description="""The record the last number was allocated for; null for a standalone allocation.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    allocations: int = Field(default=..., description="""Number of allocations made from this counter.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the counter after the last allocation.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last allocation.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'WebhookCursor']} })
    updated_at: datetime  = Field(default=..., description="""Time of the last allocation (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription']} })


class WorkflowState(ConfiguredBaseModel):
    """
    The state a record is in, since when, and by which transition it got there.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table',
                                      'value': 'cur_workflow_state'}},
         'from_schema': 'https://example.org/throughline/core/workflow'})

    record_id: str = Field(default=..., description="""The record (ledger stream) the state belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue',
                       'LinkCount',
                       'WorkflowState',
                       'NumberingAllocatedPayload',
                       'FileUploadedPayload',
                       'FeedTag',
                       'Hashtag',
                       'File']} })
    scope: str = Field(default=..., description="""Scope of the record.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'SchemaEffectiveChangedPayload',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'OutboxEvent']} })
    workflow: str = Field(default=..., description="""Identifier of the workflow definition, for example `core.review`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState', 'WorkflowTransitionedPayload']} })
    workflow_version: int = Field(default=..., description="""Version of the workflow definition that was in force.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState', 'WorkflowTransitionedPayload']} })
    state: str = Field(default=..., description="""Current state name.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['WorkflowState', 'WebhookSecret']} })
    entered_at: datetime  = Field(default=..., description="""When the record entered the state (`state_entered_at`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState']} })
    transition: str = Field(default=..., description="""Name of the transition that led here.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState', 'WorkflowTransitionedPayload']} })
    transitioned_by: str = Field(default=..., description="""Actor of the transition.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the transition event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'WebhookCursor']} })


class EventPayload(ConfiguredBaseModel):
    """
    Common parent of the event payload classes. Payloads are open: new optional fields are additive.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True, 'from_schema': 'https://example.org/throughline/core/events'})

    pass


class LinkPayload(EventPayload):
    """
    Payload of a `Link.*` event. The stream is the link, `link_id`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True, 'from_schema': 'https://example.org/throughline/core/events'})

    pass


class WebhookEventPayload(EventPayload):
    """
    Payload of a `WebhookSubscription.*` event. The stream is the subscription.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True, 'from_schema': 'https://example.org/throughline/core/events'})

    pass


class RecordCreatedPayload(EventPayload):
    """
    A record was created.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Record.Created'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'},
                         'tl:sample_changes': {'tag': 'tl:sample_changes',
                                               'value': '{"key": [null, '
                                                        '"P123-REC-0001"], "title": '
                                                        '[null, "Gate valve '
                                                        '47-1234"]}'}},
         'examples': [{'value': '{"description": null, "key": "P123-REC-0001", '
                                '"psets": {}, "record_type": "core.Record", "title": '
                                '"Gate valve 47-1234"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    record_type: str = Field(default=..., description="""Fully qualified record type.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordCreatedPayload', 'NumberingAllocatedPayload']} })
    key: Optional[str] = Field(default=None, description="""Human-readable key; null until numbering assigns one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'EventOrigin',
                       'EventLinkRef']} })
    title: str = Field(default=..., description="""Title.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'RecordCreatedPayload']} })
    description: Optional[str] = Field(default=None, description="""Description.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'RecordCreatedPayload']} })
    psets: Optional[Any] = Field(default=None, description="""Initial property-set values keyed by pset name.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordEnvelope', 'RecordCreatedPayload']} })


class RecordUpdatedPayload(EventPayload):
    """
    One or more fields of a record changed.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Record.Updated'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'},
                         'tl:sample_changes': {'tag': 'tl:sample_changes',
                                               'value': '{"title": ["Gate valve", '
                                                        '"Gate valve 47-1234"]}'}},
         'examples': [{'value': '{"changes": {"title": ["Gate valve", "Gate valve '
                                '47-1234"]}}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    changes: Any = Field(default=..., description="""Object of field name to [old, new].""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordUpdatedPayload',
                       'RecordCorrectedPayload',
                       'WebhookSubscriptionUpdatedPayload',
                       'CloudEventData']} })


class RecordVoidedPayload(EventPayload):
    """
    A record was voided. The record stays in the ledger.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Record.Voided'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"reason": "Entered in error"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    reason: str = Field(default=..., description="""Why it was voided.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'File']} })


class RecordCorrectedPayload(EventPayload):
    """
    A recorded value was corrected after the fact; history keeps the original.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Record.Corrected'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'},
                         'tl:sample_changes': {'tag': 'tl:sample_changes',
                                               'value': '{"title": ["Gate vlave", '
                                                        '"Gate valve"]}'}},
         'examples': [{'value': '{"changes": {"title": ["Gate vlave", "Gate valve"]}, '
                                '"reason": "Typo"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    changes: Any = Field(default=..., description="""Object of field name to [old, new].""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordUpdatedPayload',
                       'RecordCorrectedPayload',
                       'WebhookSubscriptionUpdatedPayload',
                       'CloudEventData']} })
    reason: str = Field(default=..., description="""Why it was corrected.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'File']} })


class PsetValuesSetPayload(EventPayload):
    """
    Values of a property set were written on a record.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Pset.ValuesSet'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'},
                         'tl:sample_changes': {'tag': 'tl:sample_changes',
                                               'value': '{"psets.valve_data.size_in": '
                                                        '[null, 4]}'}},
         'examples': [{'value': '{"conformance": "ok", "effective_schema_hash": '
                                '"9f2c", "layer": "standard", "pset": "valve_data", '
                                '"units": {"size_in": "in"}, "values": {"size_in": '
                                '4}}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    pset: str = Field(default=..., description="""Property-set name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue', 'PsetValuesSetPayload']} })
    layer: str = Field(default=..., description="""Pset layer: standard, custom or project.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue', 'PsetValuesSetPayload']} })
    values: Any = Field(default=..., description="""Object of property name to value.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['PsetValuesSetPayload']} })
    effective_schema_hash: Optional[str] = Field(default=None, description="""Hash of the effective schema in force.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValuesSetPayload',
                       'WorkflowTransitionedPayload',
                       'SchemaEffectiveChangedPayload']} })
    conformance: Optional[str] = Field(default=None, description="""Conformance after the write: ok, warning, nonconformant or waived.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValuesSetPayload',
                       'WorkflowTransitionedPayload']} })
    units: Optional[Any] = Field(default=None, description="""Units of the written properties, when the schema declares them.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['PsetValuesSetPayload']} })


class LinkAddedPayload(LinkPayload):
    """
    A link between two records became active.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Link.Added'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'},
                         'tl:sample_links': {'tag': 'tl:sample_links',
                                             'value': '[{"id": '
                                                      '"urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P6", '
                                                      '"rel": "raised_against"}]'}},
         'examples': [{'value': '{"confidence": null, "from_ref": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", "note": null, "pin": '
                                'null, "relation": "raised_against", "source": '
                                '"manual", "to_ref": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    from_ref: str = Field(default=..., description="""Record id at the start of the link.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LinkAddedPayload', 'LinkSuggestedPayload']} })
    to_ref: str = Field(default=..., description="""Record id at the end of the link.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LinkAddedPayload', 'LinkSuggestedPayload']} })
    relation: str = Field(default=..., description="""Relation code.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link', 'LinkAddedPayload', 'LinkSuggestedPayload']} })
    pin: Optional[str] = Field(default=None, description="""Revision the link is pinned to; null for a floating link.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'LinkRepinnedPayload']} })
    note: Optional[str] = Field(default=None, description="""Free-text note.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'LinkAcceptedPayload']} })
    source: Optional[str] = Field(default=None, description="""Who or what made the link: manual, rule, ai or import.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'CloudEvent',
                       'OutboxEvent']} })
    confidence: Optional[float] = Field(default=None, description="""Confidence of a suggested link, 0 to 1.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link', 'LinkAddedPayload', 'LinkSuggestedPayload']} })


class LinkSuggestedPayload(LinkPayload):
    """
    A link was suggested and waits for a person to accept or decline.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Link.Suggested'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'},
                         'tl:sample_links': {'tag': 'tl:sample_links',
                                             'value': '[{"id": '
                                                      '"urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P6", '
                                                      '"rel": "references"}]'}},
         'examples': [{'value': '{"confidence": 0.82, "from_ref": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", "note": null, "pin": '
                                'null, "relation": "references", "source": "ai", '
                                '"to_ref": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    from_ref: str = Field(default=..., description="""Record id at the start of the link.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LinkAddedPayload', 'LinkSuggestedPayload']} })
    to_ref: str = Field(default=..., description="""Record id at the end of the link.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LinkAddedPayload', 'LinkSuggestedPayload']} })
    relation: str = Field(default=..., description="""Relation code.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link', 'LinkAddedPayload', 'LinkSuggestedPayload']} })
    pin: Optional[str] = Field(default=None, description="""Revision the link is pinned to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'LinkRepinnedPayload']} })
    note: Optional[str] = Field(default=None, description="""Free-text note.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'LinkAcceptedPayload']} })
    source: Optional[str] = Field(default=None, description="""Origin of the suggestion: rule, ai or import.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'CloudEvent',
                       'OutboxEvent']} })
    confidence: Optional[float] = Field(default=None, description="""Confidence, 0 to 1.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link', 'LinkAddedPayload', 'LinkSuggestedPayload']} })


class LinkAcceptedPayload(LinkPayload):
    """
    A suggested link was accepted and is now active.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Link.Accepted'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"note": "Confirmed on site"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    note: Optional[str] = Field(default=None, description="""Free-text note.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'LinkAcceptedPayload']} })


class LinkDeclinedPayload(LinkPayload):
    """
    A suggested link was declined; it will not be suggested again.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Link.Declined'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"reason": "Different valve"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    reason: Optional[str] = Field(default=None, description="""Why it was declined.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'File']} })


class LinkRepinnedPayload(LinkPayload):
    """
    The pin of a link was set to another revision.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Link.Repinned'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"pin": "B"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    pin: Optional[str] = Field(default=None, description="""The new pin; null makes the link floating.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'LinkRepinnedPayload']} })


class LinkVerifiedPayload(LinkPayload):
    """
    A person verified an active link.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Link.Verified'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    pass


class LinkFlaggedPayload(LinkPayload):
    """
    A link was flagged stale or broken.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Link.Flagged'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"reason": "revision B issued", "status": "stale"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    status: str = Field(default=..., description="""stale or broken.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt']} })
    reason: Optional[str] = Field(default=None, description="""Why it was flagged.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'File']} })


class LinkRetractedPayload(LinkPayload):
    """
    A link was retracted. Its row and history stay.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Link.Retracted'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"reason": "Wrong record"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    reason: Optional[str] = Field(default=None, description="""Why it was retracted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'File']} })


class WorkflowTransitionedPayload(EventPayload):
    """
    A record moved from one workflow state to another.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Workflow.Transitioned'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'},
                         'tl:sample_changes': {'tag': 'tl:sample_changes',
                                               'value': '{"status": ["InReview", '
                                                        '"Issued"]}'}},
         'examples': [{'value': '{"conformance": "ok", "effective_schema_hash": '
                                '"9f2c", "from_state": "InReview", "guards_evaluated": '
                                '[{"kind": "required_pset", "message": "", "passed": '
                                'true}], "reason": null, "signature": null, '
                                '"to_state": "Issued", "transition": "issue", '
                                '"workflow": "document", "workflow_version": 1}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    workflow: str = Field(default=..., description="""Workflow id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState', 'WorkflowTransitionedPayload']} })
    workflow_version: Optional[int] = Field(default=None, description="""Workflow version.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState', 'WorkflowTransitionedPayload']} })
    from_state: str = Field(default=..., description="""State before.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowTransitionedPayload', 'OutboxEvent']} })
    to_state: str = Field(default=..., description="""State after.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowTransitionedPayload', 'OutboxEvent']} })
    transition: str = Field(default=..., description="""Transition name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState', 'WorkflowTransitionedPayload']} })
    guards_evaluated: Optional[Any] = Field(default=None, description="""List of {kind, passed, message} for each guard that ran.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['WorkflowTransitionedPayload']} })
    signature: Optional[Any] = Field(default=None, description="""Signature data when the transition was signed.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['WorkflowTransitionedPayload']} })
    reason: Optional[str] = Field(default=None, description="""Free-text reason.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'File']} })
    conformance: Optional[str] = Field(default=None, description="""Conformance after the transition.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValuesSetPayload',
                       'WorkflowTransitionedPayload']} })
    effective_schema_hash: Optional[str] = Field(default=None, description="""Hash of the effective schema in force.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValuesSetPayload',
                       'WorkflowTransitionedPayload',
                       'SchemaEffectiveChangedPayload']} })


class NumberingAllocatedPayload(EventPayload):
    """
    A number was allocated from a counter.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Numbering.Allocated'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"key": "P123-REC-0001", "pattern": "rec", "prefix": '
                                '"P123-REC-", "record_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", "record_type": '
                                '"core.Record", "sequence": 1}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    pattern: str = Field(default=..., description="""Numbering pattern id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter', 'NumberingAllocatedPayload']} })
    key: str = Field(default=..., description="""The key built.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'EventOrigin',
                       'EventLinkRef']} })
    sequence: int = Field(default=..., description="""The sequence number.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingAllocatedPayload']} })
    prefix: Optional[str] = Field(default=None, description="""The key without its sequence.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter', 'NumberingAllocatedPayload']} })
    record_id: Optional[str] = Field(default=None, description="""The record the number was allocated for.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue',
                       'LinkCount',
                       'WorkflowState',
                       'NumberingAllocatedPayload',
                       'FileUploadedPayload',
                       'FeedTag',
                       'Hashtag',
                       'File']} })
    record_type: Optional[str] = Field(default=None, description="""Record type.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordCreatedPayload', 'NumberingAllocatedPayload']} })


class FileUploadedPayload(EventPayload):
    """
    A file was uploaded and attached to a record; it is quarantined until its scan finishes.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'File.Uploaded'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"content_type": "application/pdf", "deduplicated": '
                                'false, "file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P8", '
                                '"filename": "mtr.pdf", "record_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", "revision": 1, '
                                '"sha256": '
                                '"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", '
                                '"size": 1024, "slot": "mtr", "status": '
                                '"quarantined"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    file_id: str = Field(default=..., description="""File id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'File']} })
    record_id: str = Field(default=..., description="""The record the file is attached to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue',
                       'LinkCount',
                       'WorkflowState',
                       'NumberingAllocatedPayload',
                       'FileUploadedPayload',
                       'FeedTag',
                       'Hashtag',
                       'File']} })
    slot: Optional[str] = Field(default=None, description="""File slot; null for a generic attachment.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload', 'File']} })
    revision: Optional[int] = Field(default=None, description="""Position in the slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload', 'File']} })
    sha256: str = Field(default=..., description="""SHA-256 of the bytes.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload', 'File']} })
    size: int = Field(default=..., description="""Size in bytes.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload', 'File']} })
    content_type: str = Field(default=..., description="""Media type.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload', 'File']} })
    filename: str = Field(default=..., description="""Original file name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload', 'File']} })
    status: Optional[str] = Field(default=None, description="""quarantined.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt']} })
    deduplicated: Optional[bool] = Field(default=None, description="""True when the bytes already existed.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload', 'File']} })


class FileProcessedPayload(EventPayload):
    """
    A file passed its scan and is available.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'File.Processed'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P8", "report": '
                                '{"scanner": "stub"}, "status": "available", '
                                '"supersedes": []}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    file_id: str = Field(default=..., description="""File id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'File']} })
    status: Optional[str] = Field(default=None, description="""available.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt']} })
    report: Optional[Any] = Field(default=None, description="""Scan report.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['FileProcessedPayload', 'FileRejectedPayload', 'File']} })
    supersedes: Optional[Any] = Field(default=None, description="""Ids of the files this one replaced in a single-file slot.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['FileProcessedPayload']} })


class FileRejectedPayload(EventPayload):
    """
    A file failed its scan and was rejected.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'File.Rejected'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P8", "reason": '
                                '"malware signature", "report": {"scanner": "stub"}, '
                                '"status": "rejected"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    file_id: str = Field(default=..., description="""File id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'File']} })
    status: Optional[str] = Field(default=None, description="""rejected.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt']} })
    reason: str = Field(default=..., description="""Why it was rejected.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'File']} })
    report: Optional[Any] = Field(default=None, description="""Scan report.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['FileProcessedPayload', 'FileRejectedPayload', 'File']} })


class SchemaEffectiveChangedPayload(EventPayload):
    """
    The effective schema of a scope changed.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Schema.EffectiveChanged'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"effective_schema_hash": "9f2c", "packages": '
                                '["co.acme.engineering@3.2.0"], "previous_hash": null, '
                                '"scope": "project:P123"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    scope: str = Field(default=..., description="""Scope id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'SchemaEffectiveChangedPayload',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'OutboxEvent']} })
    effective_schema_hash: str = Field(default=..., description="""New hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValuesSetPayload',
                       'WorkflowTransitionedPayload',
                       'SchemaEffectiveChangedPayload']} })
    previous_hash: Optional[str] = Field(default=None, description="""Previous hash; null the first time.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SchemaEffectiveChangedPayload']} })
    packages: Optional[list[str]] = Field(default=None, description="""Adopted packages as name@version.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SchemaEffectiveChangedPayload']} })


class SchemaPackagePublishedPayload(EventPayload):
    """
    A schema package version was published.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'SchemaPackage.Published'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"package": "co.acme.engineering", "version": '
                                '"3.2.0"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    package: str = Field(default=..., description="""Package name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SchemaPackagePublishedPayload']} })
    version: str = Field(default=..., description="""Package version.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin']} })


class WebhookSubscriptionCreatedPayload(WebhookEventPayload):
    """
    A webhook subscription was created. The signing secret is held outside the ledger.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'WebhookSubscription.Created'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"event_schema_version": "v1", "expires_at": null, '
                                '"filter": {"event_types": ["Workflow.Transitioned"], '
                                '"transitions": ["* -> Issued"]}, "integration_app": '
                                'null, "name": "NDE requests", "owner": "user:jsmith", '
                                '"payload_mode": "delta", "secret_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6PB", "subscription_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6PA", "target_url": '
                                '"https://nde.example.net/hooks/tl"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    subscription_id: str = Field(default=..., description="""Subscription id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'WebhookSecret',
                       'WebhookHealth']} })
    name: str = Field(default=..., description="""Label.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookCursor']} })
    owner: str = Field(default=..., description="""Owner actor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload', 'WebhookSubscription']} })
    integration_app: Optional[str] = Field(default=None, description="""Integration app.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload', 'WebhookSubscription']} })
    target_url: str = Field(default=..., description="""Receiver URL.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload', 'WebhookSubscription']} })
    filter: Any = Field(default=..., description="""SubscriptionFilter object.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['WebhookSubscriptionCreatedPayload', 'WebhookSubscription']} })
    payload_mode: str = Field(default=..., description="""thin, delta or full.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload', 'WebhookSubscription']} })
    event_schema_version: Optional[str] = Field(default=None, description="""Schema pin.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload', 'WebhookSubscription']} })
    expires_at: Optional[str] = Field(default=None, description="""ISO-8601 time after which the subscription stops.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookSecret']} })
    secret_id: str = Field(default=..., description="""Id of the first signing secret (not the secret).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscriptionSecretRotatedPayload',
                       'WebhookSecret']} })


class WebhookSubscriptionUpdatedPayload(WebhookEventPayload):
    """
    A subscription's name, target, filter or payload mode changed.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'WebhookSubscription.Updated'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"changes": {"payload_mode": ["thin", "delta"]}}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    changes: Any = Field(default=..., description="""Object of field name to [old, new].""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordUpdatedPayload',
                       'RecordCorrectedPayload',
                       'WebhookSubscriptionUpdatedPayload',
                       'CloudEventData']} })


class WebhookSubscriptionDisabledPayload(WebhookEventPayload):
    """
    A subscription stopped receiving events.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'WebhookSubscription.Disabled'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"detail": "5 deliveries dead-lettered since the last '
                                'success", "reason": "sustained_failure"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    reason: str = Field(default=..., description="""owner or sustained_failure.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'File']} })
    detail: Optional[str] = Field(default=None, description="""Free-text detail, for example the failure counts.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionDisabledPayload', 'CloudEventData']} })


class WebhookSubscriptionEnabledPayload(WebhookEventPayload):
    """
    A disabled subscription started receiving events again, from this event on.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'WebhookSubscription.Enabled'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    pass


class WebhookSubscriptionSecretRotatedPayload(WebhookEventPayload):
    """
    A new signing secret was issued; the previous one keeps signing until the overlap ends.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'WebhookSubscription.SecretRotated'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"previous_expires_at": '
                                '"2026-10-10T03:14:07.000000Z", "previous_secret_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6PC", "secret_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    secret_id: str = Field(default=..., description="""Id of the new secret (not the secret).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscriptionSecretRotatedPayload',
                       'WebhookSecret']} })
    previous_secret_id: Optional[str] = Field(default=None, description="""Id of the secret that is being replaced.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionSecretRotatedPayload']} })
    previous_expires_at: Optional[str] = Field(default=None, description="""ISO-8601 time when the previous secret stops signing.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionSecretRotatedPayload']} })


class FeedTag(ConfiguredBaseModel):
    """
    One `#tag` or `@mention` found in a post body, as carried in the event payloads.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/feed'})

    text: str = Field(default=..., description="""The tag as written, without its leading sigil (`47-1234-S03`, `area:A12`, `party:acme-nde`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag']} })
    kind: TagKind = Field(default=..., description="""Kind of the tag after resolution.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag', 'Hashtag']} })
    start: int = Field(default=..., description="""Character offset of the sigil in the body.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag']} })
    end: int = Field(default=..., description="""Character offset just past the last character of the tag.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag']} })
    namespace: Optional[str] = Field(default=None, description="""For code and mention tags written `ns:value`, the part before the colon.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag', 'Hashtag']} })
    record_id: Optional[str] = Field(default=None, description="""For a record tag that resolved to a record, that record's id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue',
                       'LinkCount',
                       'WorkflowState',
                       'NumberingAllocatedPayload',
                       'FileUploadedPayload',
                       'FeedTag',
                       'Hashtag',
                       'File']} })


class ActivityPost(ConfiguredBaseModel):
    """
    A broadcast post (brief 19.2, 21.1). Authored by a person, an agent or an external party; an agent's posts are labelled by its `agent:<id>` actor. A post has no replies.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'as:Note',
         'from_schema': 'https://example.org/throughline/core/feed'})

    post_id: str = Field(default=..., description="""Immutable post identifier; equals the ledger `stream_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPostedPayload',
                       'FeedEditedPayload',
                       'FeedRetractedPayload',
                       'FeedReactedPayload']} })
    scope: str = Field(default=..., description="""The project the post was made in. A post is visible wherever its project is.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'SchemaEffectiveChangedPayload',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'OutboxEvent']} })
    author: str = Field(default=..., description="""Actor that posted (`user:<id>`, `agent:<id>` or `svc:<name>`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'FeedPostedPayload']} })
    body: str = Field(default=..., description="""Text of the post, with its `#tags` and `@mentions`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPostedPayload',
                       'FeedEditedPayload',
                       'WebhookDelivery']} })
    importance: Importance = Field(default=Importance("normal"), description="""Importance the author gave; a signal tag raises the effective level to high.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'EventCard', 'FeedPostedPayload', 'FeedItemRow'],
         'ifabsent': 'string(normal)'} })
    tags: Optional[list[FeedTag]] = Field(default=None, description="""Tags found in the body.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'FeedPostedPayload', 'FeedEditedPayload']} })
    record_ids: Optional[list[str]] = Field(default=None, description="""Records the post references (the resolved record tags), without repeats.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPostedPayload',
                       'FeedEditedPayload',
                       'SubscriptionFilter']} })


class EventCard(ConfiguredBaseModel):
    """
    Feed rendering of one or more aggregated ledger events (brief 19.2, 21.1). Consecutive events with the same actor, event type and scope within a time window form one card.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'as:Activity',
         'from_schema': 'https://example.org/throughline/core/feed'})

    card_id: str = Field(default=..., description="""Deterministic card id, `card:<event id of the first aggregated event>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventCard']} })
    scope: str = Field(default=..., description="""Scope of the aggregated events.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'SchemaEffectiveChangedPayload',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'OutboxEvent']} })
    actor: str = Field(default=..., description="""Actor of the aggregated events.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'EventCard', 'FeedItemRow', 'OutboxEvent']} })
    summary: str = Field(default=..., description="""Rendered one-line summary, for example `jsmith created 14 records`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventCard',
                       'FeedItemRow',
                       'ProposalCreatedPayload',
                       'ProposalRow']} })
    importance: Importance = Field(default=Importance("low"), description="""System cards are low importance.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'EventCard', 'FeedPostedPayload', 'FeedItemRow'],
         'ifabsent': 'string(low)'} })
    event_type: str = Field(default=..., description="""The ledger event type every aggregated event has.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'EventCard', 'FeedItemRow', 'OutboxEvent']} })
    event_count: int = Field(default=..., description="""Number of aggregated ledger events.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventCard', 'FeedItemRow']} })
    subjects: Optional[list[str]] = Field(default=None, description="""Records the aggregated events are about.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventCard']} })


class FeedPostedPayload(EventPayload):
    """
    A post was made in a project feed. It is the first event of the post stream. The projection derives the effective importance from `importance` and the tags.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Feed.Posted'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"author": "user:mlee", "body": "Spool arrived '
                                '#P123-REC-0003 #hold", "importance": "normal", '
                                '"post_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", '
                                '"record_ids": ["01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"], "tags": '
                                '[{"end": 28, "kind": "record", "namespace": null, '
                                '"record_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6", "start": '
                                '14, "text": "P123-REC-0003"}, {"end": 34, "kind": '
                                '"signal", "namespace": null, "record_id": null, '
                                '"start": 29, "text": "hold"}]}'}],
         'from_schema': 'https://example.org/throughline/core/feed'})

    post_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPostedPayload',
                       'FeedEditedPayload',
                       'FeedRetractedPayload',
                       'FeedReactedPayload']} })
    body: str = Field(default=..., description="""Text of the post.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPostedPayload',
                       'FeedEditedPayload',
                       'WebhookDelivery']} })
    author: str = Field(default=..., description="""Actor that posted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'FeedPostedPayload']} })
    importance: Importance = Field(default=Importance("normal"), description="""Importance the author gave. The projection derives the effective level from it and the tags.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'EventCard', 'FeedPostedPayload', 'FeedItemRow'],
         'ifabsent': 'string(normal)'} })
    tags: Optional[list[FeedTag]] = Field(default=None, description="""Tags found in the body, after resolution.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'FeedPostedPayload', 'FeedEditedPayload']} })
    record_ids: Optional[list[str]] = Field(default=None, description="""Records the post references, without repeats.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPostedPayload',
                       'FeedEditedPayload',
                       'SubscriptionFilter']} })


class FeedEditedPayload(EventPayload):
    """
    A post was edited. The payload is a full replacement of the body and its tags; the earlier text stays in the ledger, so edits are visible history (brief 21.1).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Feed.Edited'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"body": "Spool arrived, bevels damaged", "post_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", "record_ids": [], '
                                '"tags": []}'}],
         'from_schema': 'https://example.org/throughline/core/feed'})

    post_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPostedPayload',
                       'FeedEditedPayload',
                       'FeedRetractedPayload',
                       'FeedReactedPayload']} })
    body: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPostedPayload',
                       'FeedEditedPayload',
                       'WebhookDelivery']} })
    tags: Optional[list[FeedTag]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'FeedPostedPayload', 'FeedEditedPayload']} })
    record_ids: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPostedPayload',
                       'FeedEditedPayload',
                       'SubscriptionFilter']} })


class FeedRetractedPayload(EventPayload):
    """
    A post was retracted. The projection keeps a tombstone row and drops the body.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Feed.Retracted'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"post_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", "reason": '
                                '"Wrong project"}'}],
         'from_schema': 'https://example.org/throughline/core/feed'})

    post_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPostedPayload',
                       'FeedEditedPayload',
                       'FeedRetractedPayload',
                       'FeedReactedPayload']} })
    reason: str = Field(default=..., description="""Why the post was retracted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'File']} })


class FeedReactedPayload(EventPayload):
    """
    A reaction was set or cleared on a post. The actor of the event sets (`on` true) or clears (`on` false) one acknowledgement. Reactions are limited to `ack`, `+1` and `resolved` (brief 21.1).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Feed.Reacted'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"on": true, "post_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", '
                                '"reaction": "ack"}'}],
         'from_schema': 'https://example.org/throughline/core/feed'})

    post_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPostedPayload',
                       'FeedEditedPayload',
                       'FeedRetractedPayload',
                       'FeedReactedPayload']} })
    reaction: str = Field(default=..., description="""One of `ack`, `+1`, `resolved`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedReactedPayload']} })
    on: bool = Field(default=..., description="""True to set the reaction, false to clear it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedReactedPayload']} })

    @field_validator('reaction')
    def pattern_reaction(cls, v):
        pattern=re.compile(r"^(ack|\+1|resolved)$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.search(element):
                    err_msg = f"Invalid reaction format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.search(v):
            err_msg = f"Invalid reaction format: {v}"
            raise ValueError(err_msg)
        return v


class FeedItemRow(ConfiguredBaseModel):
    """
    One row of the feed: a post (with a tombstone once retracted) or an event card. Newest first by `occurred_at`, then `seq`. A card is extended while it is the scope's open card (`open_scope`); the unique key on `open_scope` states that a scope has at most one open card.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_feed_items'}},
         'from_schema': 'https://example.org/throughline/core/feed',
         'unique_keys': {'open_scope': {'description': 'A scope has at most one open '
                                                       'card (NULL for closed cards '
                                                       'and posts).',
                                        'unique_key_name': 'open_scope',
                                        'unique_key_slots': ['open_scope']}}})

    item_id: str = Field(default=..., description="""The post id, or `card:<event id of the first aggregated event>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow', 'Hashtag']} })
    item_type: FeedItemType = Field(default=..., description="""Whether the row is a post or an event card.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow']} })
    scope: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'SchemaEffectiveChangedPayload',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'OutboxEvent']} })
    actor: str = Field(default=..., description="""Author of a post, or the actor of a card's events.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'EventCard', 'FeedItemRow', 'OutboxEvent']} })
    occurred_at: datetime  = Field(default=..., description="""`recorded_at` of the post, or of the latest event of a card.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow']} })
    seq: int = Field(default=..., description="""`seq` of the posted event, or of the latest event of a card.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['Event',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'OutboxEvent',
                       'WebhookDelivery']} })
    summary: str = Field(default=..., description="""Body of a post (empty once retracted) or the rendered summary of a card.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventCard',
                       'FeedItemRow',
                       'ProposalCreatedPayload',
                       'ProposalRow']} })
    importance: Importance = Field(default=Importance("normal"), description="""Effective importance. High when a post has a signal tag, else `base_importance`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'EventCard', 'FeedPostedPayload', 'FeedItemRow'],
         'ifabsent': 'string(normal)'} })
    base_importance: Importance = Field(default=Importance("normal"), description="""Importance the author gave the post (cards are low).""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow'], 'ifabsent': 'string(normal)'} })
    event_type: Optional[str] = Field(default=None, description="""Cards only; the event type of every aggregated event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'EventCard', 'FeedItemRow', 'OutboxEvent']} })
    event_count: int = Field(default=1, description="""1 for a post; the number of aggregated ledger events for a card.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventCard', 'FeedItemRow'], 'ifabsent': 'int(1)'} })
    first_us: Optional[int] = Field(default=None, description="""Cards only; `recorded_at` of the first aggregated event in microseconds since the Unix epoch. An integer so the window test does not depend on how a dialect returns timestamps.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow']} })
    first_seq: Optional[int] = Field(default=None, description="""Cards only; `seq` of the first aggregated event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow']} })
    open_scope: Optional[str] = Field(default=None, description="""Cards only; the scope while the card can still be extended, else null.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow']} })
    retracted: bool = Field(default=False, description="""True once the post was retracted. The row stays as a tombstone.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow'], 'ifabsent': 'false'} })
    retract_reason: Optional[str] = Field(default=None, description="""Reason given with `Feed.Retracted`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow']} })
    edit_count: int = Field(default=0, description="""Number of `Feed.Edited` events applied to the post.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow'], 'ifabsent': 'int(0)'} })
    reactions: Any = Field(default=..., description="""Reacting actors by reaction (a JSON object such as ack: [user:a]); empty lists are dropped.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['FeedItemRow']} })
    version: Optional[int] = Field(default=None, description="""Posts only; ledger `stream_version` of the post stream after the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin']} })


class Hashtag(ConfiguredBaseModel):
    """
    One tag of a post (hashtag, namespaced code, signal tag, topic or mention), or one subject record of a card (kind `record`). Cards have rows only for records, so the feed of a record includes its cards.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_feed_tags'}},
         'from_schema': 'https://example.org/throughline/core/feed'})

    tag_row_id: str = Field(default=..., description="""`<item id>|<kind>|<tag key>|<start>`, unique per occurrence.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Hashtag']} })
    item_id: str = Field(default=..., description="""The post or card the tag belongs to.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['FeedItemRow', 'Hashtag']} })
    scope: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'SchemaEffectiveChangedPayload',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'OutboxEvent']} })
    kind: TagKind = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag', 'Hashtag']} })
    tag_text: str = Field(default=..., description="""The tag as written, without its sigil. For a card's subject row, the record id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Hashtag']} })
    tag_key: str = Field(default=..., description="""Normalised text used to find the tag's feed (lower case). For a card's subject row, the record id.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['Hashtag']} })
    namespace: Optional[str] = Field(default=None, description="""For code and mention tags, the part before the colon.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag', 'Hashtag']} })
    record_id: Optional[str] = Field(default=None, description="""For a resolved record tag, or a card's subject, the record.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['PsetValue',
                       'LinkCount',
                       'WorkflowState',
                       'NumberingAllocatedPayload',
                       'FileUploadedPayload',
                       'FeedTag',
                       'Hashtag',
                       'File']} })
    start_pos: int = Field(default=..., description="""Offset of the sigil in the post body; 0 for a card's subject row.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Hashtag']} })
    end_pos: int = Field(default=..., description="""Offset just past the tag; 0 for a card's subject row.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Hashtag']} })
    seq: int = Field(default=..., description="""`seq` of the event that added the row; orders a card's subjects.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'OutboxEvent',
                       'WebhookDelivery']} })


class ProposalCreatedPayload(EventPayload):
    """
    An agent proposed a change. `command` is the command model as the agent built it, with `actor` set to the agent and `source` to `mcp:<agent>`; accepting re-runs it as the accepting person.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Proposal.Created'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"agent": "agent:triage", "command": {"actor": '
                                '"agent:triage", "scope": "project:P123", "source": '
                                '"mcp:triage", "record_type": "core.Record", "title": '
                                '"Weld NCR", "psets": {}, "numbering": {}}, '
                                '"command_type": "CreateRecord", "proposal_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", "summary": "Create '
                                'record: Weld NCR", "tool": "create_record"}'}],
         'from_schema': 'https://example.org/throughline/core/proposals'})

    proposal_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalCreatedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'ProposalRow']} })
    tool: str = Field(default=..., description="""The MCP tool that was called (`create_record`, `update_psets`, `link_records`, `transition_workflow`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalCreatedPayload', 'ProposalRow']} })
    agent: str = Field(default=..., description="""The proposing actor, `agent:<id>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalCreatedPayload', 'ProposalRow']} })
    command_type: str = Field(default=..., description="""Name of the command model (`CreateRecord`, `SetPsetValues`, `AddLink`, `TransitionWorkflow`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalCreatedPayload', 'ProposalRow']} })
    command: Any = Field(default=..., description="""The command, as JSON.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ProposalCreatedPayload', 'ProposalRow']} })
    summary: str = Field(default=..., description="""One line for the review queue.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventCard',
                       'FeedItemRow',
                       'ProposalCreatedPayload',
                       'ProposalRow']} })


class ProposalAcceptedPayload(EventPayload):
    """
    A person accepted a proposal and its command ran in the same transaction.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Proposal.Accepted'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"by": "user:mlee", "proposal_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", "result_stream_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P6", "result_version": 1}'}],
         'from_schema': 'https://example.org/throughline/core/proposals'})

    proposal_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalCreatedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'ProposalRow']} })
    by: str = Field(default=..., description="""The accepting person, `user:<id>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload']} })
    result_stream_id: str = Field(default=..., description="""Stream the command wrote to (the new record, the changed record, the link).""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalAcceptedPayload', 'ProposalRow']} })
    result_version: int = Field(default=..., description="""Stream version after the command.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalAcceptedPayload']} })


class ProposalRejectedPayload(EventPayload):
    """
    A person rejected a proposal. Nothing else was written.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Proposal.Rejected'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"by": "user:mlee", "proposal_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", "reason": "Duplicate of '
                                'NCR-0042"}'}],
         'from_schema': 'https://example.org/throughline/core/proposals'})

    proposal_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalCreatedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'ProposalRow']} })
    by: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload']} })
    reason: str = Field(default=..., description="""Why, for the agent and the audit trail.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'File']} })


class ProposalFailedPayload(EventPayload):
    """
    A person accepted a proposal, but the command was refused (the record changed since, a guard failed). The command's own writes were rolled back; this event is written in a fresh transaction.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Proposal.Failed'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"by": "user:mlee", "error": "ConcurrencyError: '
                                'expected version 3, stream is at 4", "proposal_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"}'}],
         'from_schema': 'https://example.org/throughline/core/proposals'})

    proposal_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalCreatedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'ProposalRow']} })
    by: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload']} })
    error: str = Field(default=..., description="""`<ErrorClass>: <message>` of the refusal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalFailedPayload', 'WebhookAttempt']} })


class ProposalRow(ConfiguredBaseModel):
    """
    One proposal: what was asked, by whom, and how it ended. Oldest first by `seq` is the review queue. `created_day` (UTC, from the `effective_at` of `Proposal.Created`) with `agent` is the budget key.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_proposals'}},
         'from_schema': 'https://example.org/throughline/core/proposals'})

    proposal_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalCreatedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'ProposalRow']} })
    scope: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'SchemaEffectiveChangedPayload',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'OutboxEvent']} })
    tool: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalCreatedPayload', 'ProposalRow']} })
    agent: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['ProposalCreatedPayload', 'ProposalRow']} })
    command_type: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalCreatedPayload', 'ProposalRow']} })
    command: Any = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ProposalCreatedPayload', 'ProposalRow']} })
    summary: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['EventCard',
                       'FeedItemRow',
                       'ProposalCreatedPayload',
                       'ProposalRow']} })
    status: ProposalStatus = Field(default=ProposalStatus("pending"), json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt'],
         'ifabsent': 'string(pending)'} })
    created_day: str = Field(default=..., description="""UTC day of creation, `YYYY-MM-DD`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['ProposalRow']} })
    created_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookSecret']} })
    created_event_id: str = Field(default=..., description="""Event id of `Proposal.Created`; the cause of the accepted command's events.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalRow']} })
    decided_by: Optional[str] = Field(default=None, description="""The person who accepted, rejected or failed it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalRow']} })
    decided_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalRow']} })
    reason: Optional[str] = Field(default=None, description="""The rejection reason, or the error of a failed proposal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'File']} })
    result_stream_id: Optional[str] = Field(default=None, description="""Accepted only; the stream the command wrote to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalAcceptedPayload', 'ProposalRow']} })
    seq: int = Field(default=..., description="""`seq` of `Proposal.Created`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['Event',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'OutboxEvent',
                       'WebhookDelivery']} })
    version: Optional[int] = Field(default=None, description="""Ledger `stream_version` of the proposal stream after the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin']} })


class File(ConfiguredBaseModel):
    """
    One file attached to a record, in its current lifecycle state.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_files'}},
         'from_schema': 'https://example.org/throughline/core/files'})

    file_id: str = Field(default=..., description="""Immutable file identifier; equals the ledger `stream_id` of the file.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'File']} })
    scope: str = Field(default=..., description="""Scope of the file, which is the scope of its record.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'SchemaEffectiveChangedPayload',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'OutboxEvent']} })
    record_id: str = Field(default=..., description="""The record the file is attached to.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['PsetValue',
                       'LinkCount',
                       'WorkflowState',
                       'NumberingAllocatedPayload',
                       'FileUploadedPayload',
                       'FeedTag',
                       'Hashtag',
                       'File']} })
    slot: Optional[str] = Field(default=None, description="""Name of the record type's file slot; null for a generic attachment.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload', 'File']} })
    revision: int = Field(default=1, description="""Position of the file among the attachments of its record and slot, starting at 1.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload', 'File'], 'ifabsent': 'int(1)'} })
    sha256: str = Field(default=..., description="""Lower-case SHA-256 hex digest of the bytes; the object key derives from it.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['FileUploadedPayload', 'File']} })
    size: int = Field(default=..., description="""Size in bytes, verified by the server.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload', 'File']} })
    content_type: str = Field(default=..., description="""Declared media type.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload', 'File']} })
    filename: str = Field(default=..., description="""Original file name, kept for display and download.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload', 'File']} })
    status: FileStatus = Field(default=FileStatus("quarantined"), description="""Quarantine lifecycle state.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt'],
         'ifabsent': 'string(quarantined)'} })
    deduplicated: bool = Field(default=False, description="""True when the object already existed in the store at upload time.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload', 'File'], 'ifabsent': 'false'} })
    superseded_by: Optional[str] = Field(default=None, description="""The file that replaced this one in a cardinality-one slot; null while it is current.""", json_schema_extra = { "linkml_meta": {'domain_of': ['File']} })
    report: Optional[Any] = Field(default=None, description="""Scan or processing report of the last `File.Processed` or `File.Rejected`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['FileProcessedPayload', 'FileRejectedPayload', 'File']} })
    reason: Optional[str] = Field(default=None, description="""Why the file was rejected.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'File']} })
    uploaded_by: str = Field(default=..., description="""Actor of the `File.Uploaded` event; the only reader while the file is quarantined.""", json_schema_extra = { "linkml_meta": {'domain_of': ['File']} })
    uploaded_at: datetime  = Field(default=..., description="""Time of the `File.Uploaded` event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['File']} })
    processed_at: Optional[datetime ] = Field(default=None, description="""Time of the `File.Processed` or `File.Rejected` event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['File']} })
    updated_at: datetime  = Field(default=..., description="""Time of the last applied event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription']} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'WebhookCursor']} })


class SubscriptionFilter(ConfiguredBaseModel):
    """
    Which events a subscription (or rule, or stream) wants (brief 18.2). Every part that is set must match; a part that is absent matches everything. Globs use `*` and `?` and are case-sensitive.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/integration'})

    scope_selector: Optional[str] = Field(default=None, description="""A scope id or glob (`project:P123`, `project:*`). A subscription that lives in a project is restricted to that project whatever this says.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SubscriptionFilter']} })
    event_types: Optional[list[str]] = Field(default=None, description="""Ledger event type names or globs (`Record.*`, `*.Created`, `Link.Added`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['SubscriptionFilter']} })
    record_selector: Optional[str] = Field(default=None, description="""A query-language expression (`status:open type:core.Record`) the event's subject record must match.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SubscriptionFilter']} })
    record_ids: Optional[list[str]] = Field(default=None, description="""Ids of the subject records. A link event also matches through the record at its other end.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPostedPayload',
                       'FeedEditedPayload',
                       'SubscriptionFilter']} })
    changed_fields: Optional[list[str]] = Field(default=None, description="""Field paths or globs that must appear among the event's changes (`status`, `psets.vt.*`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['SubscriptionFilter', 'OutboxEvent']} })
    transitions: Optional[list[str]] = Field(default=None, description="""Workflow transitions as `<from> -> <to>` with `*` as a wildcard (`InReview -> Issued`, `* -> Passed`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['SubscriptionFilter']} })
    link_relations: Optional[list[str]] = Field(default=None, description="""Link relation codes (or globs) of a link event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SubscriptionFilter', 'OutboxEvent']} })
    file_slots: Optional[list[str]] = Field(default=None, description="""File slot names (or globs) of a file event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SubscriptionFilter']} })
    hashtags: Optional[list[str]] = Field(default=None, description="""Hashtags (without `#`, case-insensitive) in a feed post.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SubscriptionFilter', 'OutboxEvent']} })


class WebhookSubscription(ConfiguredBaseModel):
    """
    An outbound webhook (brief 18.4): where to send, what to send, and how. One row per subscription in its current state.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table',
                                      'value': 'cur_webhook_subscription'}},
         'from_schema': 'https://example.org/throughline/core/integration'})

    subscription_id: str = Field(default=..., description="""Immutable id; equals the ledger `stream_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'WebhookSecret',
                       'WebhookHealth']} })
    scope: str = Field(default=..., description="""The scope the subscription lives in. `company` sees every project; a project sees itself.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'SchemaEffectiveChangedPayload',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'OutboxEvent']} })
    name: str = Field(default=..., description="""Short label for lists and logs.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookCursor']} })
    owner: str = Field(default=..., description="""Actor who owns the subscription and is notified of auto-disable.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload', 'WebhookSubscription']} })
    integration_app: Optional[str] = Field(default=None, description="""The integration app the subscription belongs to, when there is one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload', 'WebhookSubscription']} })
    target_url: str = Field(default=..., description="""`https://` URL of the receiver. Checked against the egress policy at every attempt.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload', 'WebhookSubscription']} })
    filter: Any = Field(default=..., description="""A `SubscriptionFilter` as a JSON object; `{}` selects every event.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['WebhookSubscriptionCreatedPayload', 'WebhookSubscription']} })
    payload_mode: PayloadMode = Field(default=PayloadMode("thin"), json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload', 'WebhookSubscription'],
         'ifabsent': 'string(thin)'} })
    event_schema_version: str = Field(default="v1", description="""Event schema version pin. Only `v1` exists.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload', 'WebhookSubscription'],
         'ifabsent': 'string(v1)'} })
    status: SubscriptionStatus = Field(default=SubscriptionStatus("active"), json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt'],
         'ifabsent': 'string(active)'} })
    disabled_reason: Optional[DisabledReason] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscription']} })
    active_windows: Any = Field(default=..., description="""JSON list of `{\"from\": seq, \"until\": seq or null}`. An event is delivered when `from < seq <= until` for some window (`until` null is open). Creation and every enable open a window; a disable closes the open one. Events committed while disabled are not delivered unless replayed.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['WebhookSubscription']} })
    expires_at: Optional[datetime ] = Field(default=None, description="""After this time the subscription no longer receives events.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookSecret']} })
    current_secret_id: Optional[str] = Field(default=None, description="""The newest signing secret (the value lives in `wh_secret`, never here).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscription']} })
    created_by: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Link', 'WebhookSubscription']} })
    created_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookSecret']} })
    updated_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription']} })
    version: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin']} })
    last_seq: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'WebhookCursor']} })


class EventOrigin(ConfiguredBaseModel):
    """
    Pointer to the originating record at the version of the event (brief 18.3, `RecordRef`).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/integration'})

    id: str = Field(default=..., description="""`urn:tl:<ulid>` of the record.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'EventOrigin', 'EventLinkRef', 'CloudEvent']} })
    key: Optional[str] = Field(default=None, description="""Human-readable key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'EventOrigin',
                       'EventLinkRef']} })
    type: Optional[str] = Field(default=None, description="""Record type.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'EventOrigin', 'EventLinkRef', 'CloudEvent']} })
    uri: str = Field(default=..., description="""Resolvable URI of the record at this version (`...@v7`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventOrigin', 'EventLinkRef']} })
    version: int = Field(default=..., description="""Version of the record after the event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin']} })
    api: Optional[str] = Field(default=None, description="""API URL of the record.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventOrigin']} })


class EventLinkRef(ConfiguredBaseModel):
    """
    One immediate link of the origin record (delta mode).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/integration'})

    rel: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['EventLinkRef']} })
    id: Optional[str] = Field(default=None, description="""`urn:tl:<ulid>` of the record at the other end.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'EventOrigin', 'EventLinkRef', 'CloudEvent']} })
    type: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'EventOrigin', 'EventLinkRef', 'CloudEvent']} })
    key: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'EventOrigin',
                       'EventLinkRef']} })
    uri: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['EventOrigin', 'EventLinkRef']} })


class CloudEventData(ConfiguredBaseModel):
    """
    The `data` member of a webhook CloudEvent.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/integration'})

    origin: EventOrigin = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['CloudEventData', 'WebhookDelivery']} })
    changes: Optional[Any] = Field(default=None, description="""Delta and full modes. Object of field path to `[old, new]`; `old` is null when the event does not carry it.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordUpdatedPayload',
                       'RecordCorrectedPayload',
                       'WebhookSubscriptionUpdatedPayload',
                       'CloudEventData']} })
    links: Optional[list[EventLinkRef]] = Field(default=None, description="""Delta and full modes. Immediate links.""", json_schema_extra = { "linkml_meta": {'domain_of': ['CloudEventData']} })
    detail: Optional[Any] = Field(default=None, description="""Delta and full modes. The ledger event payload, described per event type in the catalog.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['WebhookSubscriptionDisabledPayload', 'CloudEventData']} })
    record: Optional[Any] = Field(default=None, description="""Full mode only. The record projection as of delivery preparation, with its `version`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['CloudEventData']} })


class CloudEvent(ConfiguredBaseModel):
    """
    The CloudEvents 1.0 envelope (brief 18.3) used for webhooks, streams, the events API and exports. Extension attributes are lower-case as CloudEvents requires: `tlseq`, `tlstreamversion`, `tlcorrelationid`, `tlactor`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/integration'})

    specversion: Literal["1.0"] = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['CloudEvent'], 'equals_string': '1.0'} })
    id: str = Field(default=..., description="""The ledger event id. Receivers dedupe on it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'EventOrigin', 'EventLinkRef', 'CloudEvent']} })
    source: str = Field(default=..., description="""URI of the company and project the event came from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'CloudEvent',
                       'OutboxEvent']} })
    type: str = Field(default=..., description="""`tl.<module>.<Class>.<Verb>.v<schema version>`, for example `tl.core.Record.Created.v1`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'EventOrigin', 'EventLinkRef', 'CloudEvent']} })
    time: datetime  = Field(default=..., description="""When the ledger committed the event (UTC).""", json_schema_extra = { "linkml_meta": {'domain_of': ['CloudEvent']} })
    subject: str = Field(default=..., description="""`urn:tl:<ulid>` of the subject record, the ordering key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['CloudEvent']} })
    dataschema: str = Field(default=..., description="""URI of the catalog schema of this event type.""", json_schema_extra = { "linkml_meta": {'domain_of': ['CloudEvent']} })
    datacontenttype: Literal["application/json"] = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['CloudEvent'], 'equals_string': 'application/json'} })
    tlseq: int = Field(default=..., description="""Ledger `seq`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['CloudEvent']} })
    tlstreamversion: int = Field(default=..., description="""Version within the event's stream.""", json_schema_extra = { "linkml_meta": {'domain_of': ['CloudEvent']} })
    tlcorrelationid: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['CloudEvent']} })
    tlactor: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['CloudEvent']} })
    data: CloudEventData = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['CloudEvent', 'OutboxEvent']} })

    @field_validator('type')
    def pattern_type(cls, v):
        pattern=re.compile(r"^tl\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.v[0-9]+$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.search(element):
                    err_msg = f"Invalid type format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.search(v):
            err_msg = f"Invalid type format: {v}"
            raise ValueError(err_msg)
        return v


class OutboxEvent(ConfiguredBaseModel):
    """
    One ledger event as delivery needs it. Immutable once written.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'outbox_events'}},
         'from_schema': 'https://example.org/throughline/core/outbox'})

    seq: int = Field(default=..., description="""Ledger `seq` of the event; the delivery cursor and ordering backbone.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'OutboxEvent',
                       'WebhookDelivery']} })
    event_id: str = Field(default=..., description="""Ledger event id; the CloudEvents `id` and the Standard Webhooks `webhook-id`, so receivers dedupe on it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent', 'WebhookDelivery']} })
    scope: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'SchemaEffectiveChangedPayload',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'OutboxEvent']} })
    event_type: str = Field(default=..., description="""Ledger event type, for example `Record.Created`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'EventCard', 'FeedItemRow', 'OutboxEvent']} })
    schema_version: int = Field(default=1, json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent'], 'ifabsent': 'int(1)'} })
    stream_id: str = Field(default=..., description="""The stream the event was appended to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent']} })
    stream_type: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent']} })
    stream_version: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent']} })
    subject_id: str = Field(default=..., description="""The record the event is about, and the delivery ordering key: the stream for record events, the `from` record for link events, the record of a file, the record of a numbering allocation. Equal to `stream_id` when the event has no other subject.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['OutboxEvent', 'WebhookDelivery']} })
    subject_type: Optional[str] = Field(default=None, description="""Record type of the subject (`core.Record`), when it is a known record.""", json_schema_extra = { "linkml_meta": {'domain_of': ['OutboxEvent']} })
    subject_key: Optional[str] = Field(default=None, description="""Human-readable key of the subject, when it has one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['OutboxEvent']} })
    subject_version: Optional[int] = Field(default=None, description="""Version of the subject record after the event (the stream version when the stream is the subject).""", json_schema_extra = { "linkml_meta": {'domain_of': ['OutboxEvent']} })
    actor: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'EventCard', 'FeedItemRow', 'OutboxEvent']} })
    source: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'CloudEvent',
                       'OutboxEvent']} })
    recorded_at: str = Field(default=..., description="""ISO-8601 UTC time of the event (the CloudEvents `time`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent']} })
    correlation_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent']} })
    changed_fields: Any = Field(default=..., description="""JSON list of changed field paths (`status`, `psets.vt.result`), for filters.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['SubscriptionFilter', 'OutboxEvent']} })
    from_state: Optional[str] = Field(default=None, description="""Workflow state before a `Workflow.Transitioned`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowTransitionedPayload', 'OutboxEvent']} })
    to_state: Optional[str] = Field(default=None, description="""Workflow state after a `Workflow.Transitioned`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowTransitionedPayload', 'OutboxEvent']} })
    related_ids: Any = Field(default=..., description="""JSON list of the other records the event is about (the far end of a link), for the `record_ids` filter.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['OutboxEvent']} })
    link_relations: Any = Field(default=..., description="""JSON list of link relation codes the event is about.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['SubscriptionFilter', 'OutboxEvent']} })
    file_slot: Optional[str] = Field(default=None, description="""File slot of a `File.*` event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['OutboxEvent']} })
    hashtags: Any = Field(default=..., description="""JSON list of hashtags in the event payload (feed posts, later).""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['SubscriptionFilter', 'OutboxEvent']} })
    data: Any = Field(default=..., description="""URI-free envelope data: `origin` (id, key, type, version), `changes` (field to [old, new]), `links` (immediate link refs of link events) and `detail` (the ledger payload).""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['CloudEvent', 'OutboxEvent']} })


class WebhookDelivery(ConfiguredBaseModel):
    """
    One event to be delivered to one subscription, with its retry state.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'wh_delivery'}},
         'from_schema': 'https://example.org/throughline/core/outbox',
         'unique_keys': {'subscription_dedupe': {'description': 'A live event reaches '
                                                                'a subscription once; '
                                                                'replays carry their '
                                                                'own dedupe key.',
                                                 'unique_key_name': 'subscription_dedupe',
                                                 'unique_key_slots': ['subscription_id',
                                                                      'dedupe_key']}}})

    delivery_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery', 'WebhookAttempt']} })
    subscription_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'WebhookSecret',
                       'WebhookHealth']} })
    dedupe_key: str = Field(default=..., description="""`<seq>` for a live delivery, `<seq>:<origin>:<ulid>` for a replay or redrive.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery']} })
    seq: int = Field(default=..., description="""Ledger `seq` of the event; deliveries of one subject go out in this order.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'OutboxEvent',
                       'WebhookDelivery']} })
    event_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent', 'WebhookDelivery']} })
    subject_id: str = Field(default=..., description="""The delivery ordering key (see `OutboxEvent.subject_id`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['OutboxEvent', 'WebhookDelivery']} })
    origin: DeliveryOrigin = Field(default=DeliveryOrigin("live"), json_schema_extra = { "linkml_meta": {'domain_of': ['CloudEventData', 'WebhookDelivery'], 'ifabsent': 'string(live)'} })
    status: DeliveryStatus = Field(default=DeliveryStatus("pending"), json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt'],
         'ifabsent': 'string(pending)'} })
    body: str = Field(default=..., description="""The exact JSON text that is sent (and re-sent on every retry), built once when the delivery was created.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPostedPayload',
                       'FeedEditedPayload',
                       'WebhookDelivery']} })
    attempts: int = Field(default=0, json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery'], 'ifabsent': 'int(0)'} })
    created_at: str = Field(default=..., description="""ISO-8601 UTC. The retry deadline counts from here.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookSecret']} })
    next_attempt_at: str = Field(default=..., description="""ISO-8601 UTC. A pending delivery is not tried before this time.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery']} })
    lease_until: Optional[str] = Field(default=None, description="""ISO-8601 UTC while a worker holds the delivery; an expired lease can be taken over.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery']} })
    lease_owner: Optional[str] = Field(default=None, description="""Worker id that holds the lease.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery']} })
    last_status: Optional[int] = Field(default=None, description="""HTTP status of the last attempt; null for a network error or a blocked target.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery']} })
    last_error: Optional[str] = Field(default=None, description="""Short reason of the last failure (no secrets, no response bodies beyond an excerpt).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery']} })
    delivered_at: Optional[str] = Field(default=None, description="""ISO-8601 UTC of the successful attempt.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery']} })
    dead_at: Optional[str] = Field(default=None, description="""ISO-8601 UTC when the delivery was dead-lettered.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery']} })
    dead_reason: Optional[str] = Field(default=None, description="""`retries_exhausted`, `gone`, `egress_denied`, `unreachable_permanently` or `subscription_removed`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery']} })
    replay_of: Optional[str] = Field(default=None, description="""For a redrive, the dead delivery it re-enqueued.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery']} })


class WebhookAttempt(ConfiguredBaseModel):
    """
    The log of one delivery attempt (status, latency, response excerpt).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'wh_attempt'}},
         'from_schema': 'https://example.org/throughline/core/outbox'})

    attempt_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookAttempt']} })
    delivery_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['WebhookDelivery', 'WebhookAttempt']} })
    subscription_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'WebhookSecret',
                       'WebhookHealth']} })
    attempt: int = Field(default=..., description="""1 for the first attempt of the delivery.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookAttempt']} })
    started_at: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookAttempt']} })
    latency_ms: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookAttempt']} })
    status: Optional[int] = Field(default=None, description="""HTTP status; null when no response was received.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt']} })
    outcome: str = Field(default=..., description="""`delivered`, `retry`, `dead`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookAttempt']} })
    error: Optional[str] = Field(default=None, description="""Short failure reason.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalFailedPayload', 'WebhookAttempt']} })
    response_excerpt: Optional[str] = Field(default=None, description="""First 512 characters of the response body, control characters removed.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookAttempt']} })


class WebhookSecret(ConfiguredBaseModel):
    """
    A signing secret of a subscription. Secrets never enter the ledger or the logs.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'wh_secret'}},
         'from_schema': 'https://example.org/throughline/core/outbox'})

    secret_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscriptionSecretRotatedPayload',
                       'WebhookSecret']} })
    subscription_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'WebhookSecret',
                       'WebhookHealth']} })
    secret: str = Field(default=..., description="""`whsec_` plus the base64 of 32 random bytes (the Standard Webhooks format).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSecret']} })
    state: SecretState = Field(default=SecretState("active"), json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState', 'WebhookSecret'], 'ifabsent': 'string(active)'} })
    created_at: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookSecret']} })
    expires_at: Optional[str] = Field(default=None, description="""ISO-8601 UTC. A rotated-out secret keeps signing until this time (the overlap), then retires.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookSecret']} })


class WebhookHealth(ConfiguredBaseModel):
    """
    Failure bookkeeping per subscription, for auto-disable and the operator screens.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'wh_health'}},
         'from_schema': 'https://example.org/throughline/core/outbox'})

    subscription_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'WebhookSecret',
                       'WebhookHealth']} })
    consecutive_dead: int = Field(default=0, description="""Deliveries dead-lettered since the last success.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookHealth'], 'ifabsent': 'int(0)'} })
    failing_since: Optional[str] = Field(default=None, description="""ISO-8601 UTC of the first failed attempt since the last success; null while healthy.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookHealth']} })
    last_success_at: Optional[str] = Field(default=None, description="""ISO-8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookHealth']} })
    last_failure_at: Optional[str] = Field(default=None, description="""ISO-8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookHealth']} })
    delivered_total: int = Field(default=0, json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookHealth'], 'ifabsent': 'int(0)'} })
    failed_total: int = Field(default=0, json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookHealth'], 'ifabsent': 'int(0)'} })


class WebhookCursor(ConfiguredBaseModel):
    """
    How far the dispatcher has read the outbox.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'wh_cursor'}},
         'from_schema': 'https://example.org/throughline/core/outbox'})

    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookCursor']} })
    last_seq: int = Field(default=0, json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'WebhookCursor'],
         'ifabsent': 'int(0)'} })


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
RecordEnvelope.model_rebuild()
Record.model_rebuild()
Event.model_rebuild()
PsetValue.model_rebuild()
Link.model_rebuild()
LinkCount.model_rebuild()
NumberingCounter.model_rebuild()
WorkflowState.model_rebuild()
EventPayload.model_rebuild()
LinkPayload.model_rebuild()
WebhookEventPayload.model_rebuild()
RecordCreatedPayload.model_rebuild()
RecordUpdatedPayload.model_rebuild()
RecordVoidedPayload.model_rebuild()
RecordCorrectedPayload.model_rebuild()
PsetValuesSetPayload.model_rebuild()
LinkAddedPayload.model_rebuild()
LinkSuggestedPayload.model_rebuild()
LinkAcceptedPayload.model_rebuild()
LinkDeclinedPayload.model_rebuild()
LinkRepinnedPayload.model_rebuild()
LinkVerifiedPayload.model_rebuild()
LinkFlaggedPayload.model_rebuild()
LinkRetractedPayload.model_rebuild()
WorkflowTransitionedPayload.model_rebuild()
NumberingAllocatedPayload.model_rebuild()
FileUploadedPayload.model_rebuild()
FileProcessedPayload.model_rebuild()
FileRejectedPayload.model_rebuild()
SchemaEffectiveChangedPayload.model_rebuild()
SchemaPackagePublishedPayload.model_rebuild()
WebhookSubscriptionCreatedPayload.model_rebuild()
WebhookSubscriptionUpdatedPayload.model_rebuild()
WebhookSubscriptionDisabledPayload.model_rebuild()
WebhookSubscriptionEnabledPayload.model_rebuild()
WebhookSubscriptionSecretRotatedPayload.model_rebuild()
FeedTag.model_rebuild()
ActivityPost.model_rebuild()
EventCard.model_rebuild()
FeedPostedPayload.model_rebuild()
FeedEditedPayload.model_rebuild()
FeedRetractedPayload.model_rebuild()
FeedReactedPayload.model_rebuild()
FeedItemRow.model_rebuild()
Hashtag.model_rebuild()
ProposalCreatedPayload.model_rebuild()
ProposalAcceptedPayload.model_rebuild()
ProposalRejectedPayload.model_rebuild()
ProposalFailedPayload.model_rebuild()
ProposalRow.model_rebuild()
File.model_rebuild()
SubscriptionFilter.model_rebuild()
WebhookSubscription.model_rebuild()
EventOrigin.model_rebuild()
EventLinkRef.model_rebuild()
CloudEventData.model_rebuild()
CloudEvent.model_rebuild()
OutboxEvent.model_rebuild()
WebhookDelivery.model_rebuild()
WebhookAttempt.model_rebuild()
WebhookSecret.model_rebuild()
WebhookHealth.model_rebuild()
WebhookCursor.model_rebuild()
