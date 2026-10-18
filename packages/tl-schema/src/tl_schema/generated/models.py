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
                 'settings',
                 'files',
                 'integration',
                 'outbox',
                 'extension',
                 'events',
                 'auth',
                 'jobs',
                 'integration_ops'],
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


class SettingType(str, Enum):
    """
    The value type of a setting (brief 30.1).
    """
    bool = "bool"
    int = "int"
    decimal = "decimal"
    string = "string"
    enum = "enum"
    list = "list"
    duration = "duration"
    """
    Whole number plus unit, `ms`, `s`, `m`, `h`, `d` or `w` (`5m`, `24h`).
    """
    size = "size"
    """
    Whole number plus unit, `B`, `KB`, `MB`, `GB` or `TB` (`50MB`).
    """
    date = "date"
    """
    ISO date, `YYYY-MM-DD`.
    """
    json = "json"


class SettingScope(str, Enum):
    """
    Which layers may set a key. `platform` is the shipped default only; nobody sets it at run time.
    """
    platform = "platform"
    company = "company"
    project = "project"
    user = "user"


class SettingEffect(str, Enum):
    """
    What a change needs before it is fully in force (brief 30.3).
    """
    live = "live"
    reindex = "reindex"
    rebuild = "rebuild"
    restart = "restart"


class SettingSensitivity(str, Enum):
    """
    A `secret` setting would live in the vault; Phase 0 has none and refuses to set one.
    """
    normal = "normal"
    secret = "secret"


class SettingRisk(str, Enum):
    """
    `advanced` needs a reason with every change; `dangerous` also needs the explicit "I accept the risk".
    """
    normal = "normal"
    advanced = "advanced"
    dangerous = "dangerous"


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


class AccessLevel(str, Enum):
    """
    Who may run a command or invoke an action (ADR-0011, ADR-0013).
    """
    user = "user"
    controller = "controller"
    admin = "admin"


class AutomationAccess(str, Enum):
    """
    What a service actor (rule, inbound endpoint, enricher) may be declared to hold. Automation never runs an `admin` command in Phase 1.
    """
    user = "user"
    controller = "controller"


class ExecutorKind(str, Enum):
    """
    How an action is carried out. Phase 1 builds `job` and `webhook`; a definition naming another is refused.
    """
    webhook = "webhook"
    mcp_tool = "mcp_tool"
    connector = "connector"
    job = "job"
    agent = "agent"


class SideEffectClass(str, Enum):
    """
    What running an action can change (brief 18.7); the confirmation a person sees depends on it.
    """
    read = "read"
    propose = "propose"
    write = "write"
    external = "external"


class InvocationStatus(str, Enum):
    """
    Where an action invocation is in its life.
    """
    requested = "requested"
    running = "running"
    completed = "completed"
    failed = "failed"


class RuleMode(str, Enum):
    """
    Whether a rule runs its steps or proposes them.
    """
    act = "act"
    propose = "propose"


class InboundAuth(str, Enum):
    """
    How an inbound request proves who sent it.
    """
    hmac_sha256 = "hmac_sha256"
    """
    Standard Webhooks signature over `id.timestamp.body`.
    """
    jwt_hs256 = "jwt_hs256"
    """
    A bearer JWT signed with HS256 that names the body by its SHA-256.
    """


class AcceptancePolicy(str, Enum):
    """
    What happens to a value an enricher proposes for a property.
    """
    auto = "auto"
    """
    Accepted at once when the confidence reaches the threshold.
    """
    propose = "propose"
    """
    Waits in the review queue for a person.
    """
    shadow = "shadow"
    """
    Stored for evaluation and shown to admins only.
    """


class AcceptanceState(str, Enum):
    """
    Where a proposed enrichment value is.
    """
    shadow = "shadow"
    proposed = "proposed"
    accepted = "accepted"
    auto_accepted = "auto_accepted"
    rejected = "rejected"


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


class TypeStatus(str, Enum):
    """
    Where a registered extension type version is in its life.
    """
    active = "active"
    """
    Validated and registered; new instances may be created.
    """
    quarantined = "quarantined"
    """
    Failed validation; it has a report and no instances can be created.
    """
    deprecated = "deprecated"
    """
    Retired by its owner; existing instances stay readable, no new ones.
    """


class StorageMode(str, Enum):
    """
    Where the body of an extension type instance lives (brief 31.2).
    """
    managed = "managed"
    """
    The body is in the ledger, as pset values.
    """
    object_backed = "object-backed"
    """
    The body is a content-addressed document in the object store; the ledger holds a pointer.
    """
    directory_backed = "directory-backed"
    """
    Files in a watched directory. Refused in v0 (TypeIssue `unsupported`).
    """


class AccountKind(str, Enum):
    """
    What kind of principal an account is.
    """
    person = "person"
    """
    A human who signs in with a username and password (later Entra ID).
    """
    agent = "agent"
    """
    An AI agent. It never has a password or the admin role; it authenticates with an admin-issued token and is always propose-only.
    """
    sim = "sim"
    """
    A simulator actor, a seeded account with the user role.
    """


class AccountStatus(str, Enum):
    """
    Whether an account may authenticate.
    """
    active = "active"
    disabled = "disabled"
    """
    Cannot sign in; its sessions and agent tokens are refused.
    """


class AccountRole(str, Enum):
    """
    The three roles of Phase 1 (ADR-0008 decision 3, amended by ADR-0013).
    """
    admin = "admin"
    """
    Everything, including the admin module.
    """
    user = "user"
    """
    Everything except `admin.*` and `control.*` actions.
    """
    document_controller = "document_controller"
    """
    A user who may also run the controlling acts of document control (`control.*`). Not an admin; never held by an agent.
    """


class SecretOwnerKind(str, Enum):
    """
    Whose signing secret a row is.
    """
    inbound = "inbound"
    """
    The HMAC or JWT secret of an inbound endpoint (`owner_id` is the endpoint id).
    """
    action = "action"
    """
    The signing secret of a webhook action (`owner_id` is the definition id).
    """


class DeliveryState(str, Enum):
    """
    Where an inbound delivery is.
    """
    queued = "queued"
    """
    Verified and stored; waiting for the `inbound.map` job.
    """
    applied = "applied"
    """
    Mapped and every command ran.
    """
    failed = "failed"
    """
    Mapping or a command was refused; in the error queue until retried.
    """
    dry_run = "dry_run"
    """
    Mapped and planned for a dry-run endpoint; nothing ran.
    """
    killed = "killed"
    """
    Passed over while the kill switch was on; never replayed.
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
                       'RuleCreatedPayload',
                       'SettingDefinition',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'EventOrigin',
                       'EventLinkRef',
                       'Rule']} })
    type: str = Field(default=..., description="""Fully qualified record type, for example `core.Record`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'SettingDefinition',
                       'EventOrigin',
                       'EventLinkRef',
                       'CloudEvent']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    title: str = Field(default=..., description="""Short human-readable title.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'RuleCreatedPayload',
                       'Rule']} })
    description: Optional[str] = Field(default=None, description="""Longer free-text description.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'SettingDefinition',
                       'IntegrationApp',
                       'ActionDefinition']} })
    status: Optional[str] = Field(default=None, description="""Workflow state; null when the record type has no workflow.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'ActionInvocation',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    psets: Any = Field(default=..., description="""Property-set values keyed by pset name, stored as a JSON object.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordEnvelope', 'RecordCreatedPayload']} })
    voided: bool = Field(default=False, description="""Set by `Record.Voided`. Voided rows are never deleted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope'], 'ifabsent': 'false'} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })
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
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookDelivery',
                       'WebhookSecret',
                       'Account',
                       'AuthSession',
                       'AuthTokenSecret',
                       'IntegrationSecret']} })
    updated_at: datetime  = Field(default=..., description="""Timestamp of the last applied event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AuthCredential']} })


class Record(RecordEnvelope):
    """
    The generic Phase 0 record type, `core.Record`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:ix_scope_voided_created': {'tag': 'tl:ix_scope_voided_created',
                                                        'value': 'scope, voided, '
                                                                 'created_at, id'},
                         'tl:ix_scope_voided_key_asc': {'tag': 'tl:ix_scope_voided_key_asc',
                                                        'value': 'scope, voided, '
                                                                 'empty_last(key), '
                                                                 'key, id'},
                         'tl:ix_scope_voided_key_desc': {'tag': 'tl:ix_scope_voided_key_desc',
                                                         'value': 'scope, voided, '
                                                                  'empty_last(key), '
                                                                  'key desc, id'},
                         'tl:ix_scope_voided_updated': {'tag': 'tl:ix_scope_voided_updated',
                                                        'value': 'scope, voided, '
                                                                 'updated_at, id'}},
         'from_schema': 'https://example.org/throughline/core/record',
         'unique_keys': {'scope_key': {'description': 'A key is unique within its '
                                                      'scope.',
                                       'unique_key_name': 'scope_key',
                                       'unique_key_slots': ['scope', 'key']}}})

    id: str = Field(default=..., description="""Immutable global identifier; equals the ledger `stream_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'EventOrigin', 'EventLinkRef', 'CloudEvent']} })
    key: Optional[str] = Field(default=None, description="""Human-readable number, unique within a scope. Null until numbering assigns one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'RuleCreatedPayload',
                       'SettingDefinition',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'EventOrigin',
                       'EventLinkRef',
                       'Rule']} })
    type: str = Field(default=..., description="""Fully qualified record type, for example `core.Record`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'SettingDefinition',
                       'EventOrigin',
                       'EventLinkRef',
                       'CloudEvent']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    title: str = Field(default=..., description="""Short human-readable title.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'RuleCreatedPayload',
                       'Rule']} })
    description: Optional[str] = Field(default=None, description="""Longer free-text description.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'SettingDefinition',
                       'IntegrationApp',
                       'ActionDefinition']} })
    status: Optional[str] = Field(default=None, description="""Workflow state; null when the record type has no workflow.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'ActionInvocation',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    psets: Any = Field(default=..., description="""Property-set values keyed by pset name, stored as a JSON object.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordEnvelope', 'RecordCreatedPayload']} })
    voided: bool = Field(default=False, description="""Set by `Record.Voided`. Voided rows are never deleted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope'], 'ifabsent': 'false'} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })
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
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookDelivery',
                       'WebhookSecret',
                       'Account',
                       'AuthSession',
                       'AuthTokenSecret',
                       'IntegrationSecret']} })
    updated_at: datetime  = Field(default=..., description="""Timestamp of the last applied event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AuthCredential']} })


class Event(ConfiguredBaseModel):
    """
    One immutable ledger event.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/ledger'})

    seq: int = Field(default=..., description="""Global monotonic sequence; the ordering backbone.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'ActionInvocation',
                       'InboundEndpointVersion',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'WebhookDelivery',
                       'RuleFiring']} })
    event_id: str = Field(default=..., description="""Unique event identifier (ULID).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent', 'WebhookDelivery', 'RuleFiring']} })
    stream_id: str = Field(default=..., description="""The record (aggregate) the event belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent', 'RecordBodyStoredPayload']} })
    stream_type: str = Field(default=..., description="""Record type of the stream, for example `core.Record`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent']} })
    stream_version: int = Field(default=..., description="""Per-stream version, used for optimistic concurrency.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'OutboxEvent']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    payload: Any = Field(default=..., description="""Event payload, a JSON object validated against the event type's schema.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['Event']} })
    actor: str = Field(default=..., description="""`user:<id>`, `svc:<name>` or `agent:<id>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'EventCard',
                       'FeedItemRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'OutboxEvent',
                       'AuthAudit']} })
    recorded_at: datetime  = Field(default=..., description="""System (transaction) time.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'SettingChangeRow', 'SettingLockRow', 'OutboxEvent']} })
    effective_at: datetime  = Field(default=..., description="""Business (valid) time.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    correlation_id: str = Field(default=..., description="""Ties a command chain, import, or automated process together.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent']} })
    causation_id: Optional[str] = Field(default=None, description="""Identifier of the event or command that caused this one; may be null.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    source: str = Field(default=..., description="""`tui`, `api`, `mcp:<agent>`, `cli`, `import:<job>` or `sim:<run>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'SettingChangeRow',
                       'CloudEvent',
                       'OutboxEvent']} })
    prev_hash: Optional[str] = Field(default=None, description="""Hash of the previous event in the same scope; null for the first.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    hash: str = Field(default=..., description="""Hash of this event chained to `prev_hash`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'RecordBody']} })


class PsetValue(ConfiguredBaseModel):
    """
    One current pset value of one record, addressed by its layer-aware path.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:ix_path_num': {'tag': 'tl:ix_path_num',
                                            'value': 'path, value_num, record_id'},
                         'tl:ix_path_text': {'tag': 'tl:ix_path_text',
                                             'value': 'path, value_text, record_id'},
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
                       'File',
                       'ActionInvocationTarget',
                       'RecordBody',
                       'BodyQuarantine']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    path: str = Field(default=..., description="""Layer-aware path, for example `psets.valve_data.x.fat_witness_by`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['PsetValue']} })
    pset: str = Field(default=..., description="""Pset name, for example `valve_data` or `prj.shutdown_tie_in`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue', 'PsetValuesSetPayload', 'TypeRegistrationRow']} })
    property_name: str = Field(default=..., description="""Property relative to the pset; custom-section properties start with `x.`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue']} })
    layer: PsetLayer = Field(default=..., description="""Layer derived from the path.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue',
                       'PsetValuesSetPayload',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow']} })
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
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })
    updated_at: datetime  = Field(default=..., description="""Timestamp of that event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AuthCredential']} })


class Link(ConfiguredBaseModel):
    """
    One link between two records, in its current lifecycle state.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:ix_relation_status_from': {'tag': 'tl:ix_relation_status_from',
                                                        'value': 'relation, status, '
                                                                 'from_id, to_id'},
                         'tl:ix_relation_status_to': {'tag': 'tl:ix_relation_status_to',
                                                      'value': 'relation, status, '
                                                               'to_id, from_id'},
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
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
                       'ActionInvocation',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account'],
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
                       'SettingChangeRow',
                       'CloudEvent',
                       'OutboxEvent']} })
    confidence: Optional[float] = Field(default=None, description="""Confidence of a suggested link, between 0 and 1.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'EnrichmentProposedPayload',
                       'EnrichmentValue']} })
    reason: Optional[str] = Field(default=None, description="""Reason given with the last flag, decline, or retraction.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })
    declined: bool = Field(default=False, description="""True when the link was a suggestion that a person declined. Declines are remembered.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link'], 'ifabsent': 'false'} })
    verified_by: Optional[str] = Field(default=None, description="""Actor of the last `Link.Verified` event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link']} })
    verified_at: Optional[datetime ] = Field(default=None, description="""Time of the last `Link.Verified` event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link']} })
    created_by: str = Field(default=..., description="""Actor of the creating event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'Account']} })
    created_at: datetime  = Field(default=..., description="""Time of the creating event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookDelivery',
                       'WebhookSecret',
                       'Account',
                       'AuthSession',
                       'AuthTokenSecret',
                       'IntegrationSecret']} })
    updated_at: datetime  = Field(default=..., description="""Time of the last applied event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AuthCredential']} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })


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
                       'File',
                       'ActionInvocationTarget',
                       'RecordBody',
                       'BodyQuarantine']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
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
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })


class NumberingCounter(ConfiguredBaseModel):
    """
    The last sequence number allocated for one counter.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_numbering'}},
         'from_schema': 'https://example.org/throughline/core/numbering'})

    counter_id: str = Field(default=..., description="""Ledger stream id of the counter, `numbering:<scope>:<pattern>:<prefix>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter', 'InboundCounter']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    pattern: str = Field(default=..., description="""Identifier of the numbering pattern.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter',
                       'NumberingAllocatedPayload',
                       'SettingValidation']} })
    prefix: str = Field(default=..., description="""The rendered key without its sequence number, for example `P123-REC-`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter', 'NumberingAllocatedPayload']} })
    last_sequence: int = Field(default=..., description="""The highest sequence number allocated so far.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    last_key: str = Field(default=..., description="""The key built from `last_sequence`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    last_record_id: Optional[str] = Field(default=None, description="""The record the last number was allocated for; null for a standalone allocation.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    allocations: int = Field(default=..., description="""Number of allocations made from this counter.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the counter after the last allocation.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last allocation.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })
    updated_at: datetime  = Field(default=..., description="""Time of the last allocation (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AuthCredential']} })


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
                       'File',
                       'ActionInvocationTarget',
                       'RecordBody',
                       'BodyQuarantine']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    workflow: str = Field(default=..., description="""Identifier of the workflow definition, for example `core.review`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState', 'WorkflowTransitionedPayload']} })
    workflow_version: int = Field(default=..., description="""Version of the workflow definition that was in force.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState', 'WorkflowTransitionedPayload']} })
    state: str = Field(default=..., description="""Current state name.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['WorkflowState',
                       'WebhookSecret',
                       'JobQueue',
                       'IntegrationSecret',
                       'InboundDelivery']} })
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
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })


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

    record_type: str = Field(default=..., description="""Fully qualified record type.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'ActionInvocationTarget']} })
    key: Optional[str] = Field(default=None, description="""Human-readable key; null until numbering assigns one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'RuleCreatedPayload',
                       'SettingDefinition',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'EventOrigin',
                       'EventLinkRef',
                       'Rule']} })
    title: str = Field(default=..., description="""Title.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'RuleCreatedPayload',
                       'Rule']} })
    description: Optional[str] = Field(default=None, description="""Description.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'SettingDefinition',
                       'IntegrationApp',
                       'ActionDefinition']} })
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
                       'IntegrationAppRevisedPayload',
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
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


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
                       'IntegrationAppRevisedPayload',
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
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


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

    pset: str = Field(default=..., description="""Property-set name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue', 'PsetValuesSetPayload', 'TypeRegistrationRow']} })
    layer: str = Field(default=..., description="""Pset layer: standard, custom or project.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue',
                       'PsetValuesSetPayload',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow']} })
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
                       'SettingChangeRow',
                       'CloudEvent',
                       'OutboxEvent']} })
    confidence: Optional[float] = Field(default=None, description="""Confidence of a suggested link, 0 to 1.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'EnrichmentProposedPayload',
                       'EnrichmentValue']} })


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
                       'SettingChangeRow',
                       'CloudEvent',
                       'OutboxEvent']} })
    confidence: Optional[float] = Field(default=None, description="""Confidence, 0 to 1.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'EnrichmentProposedPayload',
                       'EnrichmentValue']} })


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
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


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
                       'ActionInvocation',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    reason: Optional[str] = Field(default=None, description="""Why it was flagged.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


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
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


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
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })
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

    pattern: str = Field(default=..., description="""Numbering pattern id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter',
                       'NumberingAllocatedPayload',
                       'SettingValidation']} })
    key: str = Field(default=..., description="""The key built.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'RuleCreatedPayload',
                       'SettingDefinition',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'EventOrigin',
                       'EventLinkRef',
                       'Rule']} })
    sequence: int = Field(default=..., description="""The sequence number.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingAllocatedPayload']} })
    prefix: Optional[str] = Field(default=None, description="""The key without its sequence.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter', 'NumberingAllocatedPayload']} })
    record_id: Optional[str] = Field(default=None, description="""The record the number was allocated for.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue',
                       'LinkCount',
                       'WorkflowState',
                       'NumberingAllocatedPayload',
                       'FileUploadedPayload',
                       'FeedTag',
                       'Hashtag',
                       'File',
                       'ActionInvocationTarget',
                       'RecordBody',
                       'BodyQuarantine']} })
    record_type: Optional[str] = Field(default=None, description="""Record type.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'ActionInvocationTarget']} })


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
                       'File',
                       'ActionInvocationTarget',
                       'RecordBody',
                       'BodyQuarantine']} })
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
                       'ActionInvocation',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
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
                       'ActionInvocation',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    report: Optional[Any] = Field(default=None, description="""Scan report.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['FileProcessedPayload',
                       'FileRejectedPayload',
                       'File',
                       'TypeRegistrationQuarantinedPayload',
                       'TypeRegistrationRow']} })
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
                       'ActionInvocation',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    reason: str = Field(default=..., description="""Why it was rejected.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })
    report: Optional[Any] = Field(default=None, description="""Scan report.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['FileProcessedPayload',
                       'FileRejectedPayload',
                       'File',
                       'TypeRegistrationQuarantinedPayload',
                       'TypeRegistrationRow']} })


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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    effective_schema_hash: str = Field(default=..., description="""New hash.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValuesSetPayload',
                       'WorkflowTransitionedPayload',
                       'SchemaEffectiveChangedPayload']} })
    previous_hash: Optional[str] = Field(default=None, description="""Previous hash; null the first time.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SchemaEffectiveChangedPayload', 'RecordBodyStoredPayload']} })
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
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })


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
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookCursor',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RuleCursor',
                       'EnrichmentCursor']} })
    owner: str = Field(default=..., description="""Owner actor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'SettingDefinition',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    integration_app: Optional[str] = Field(default=None, description="""Integration app.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'ActionDefinition',
                       'Rule',
                       'Enricher']} })
    target_url: str = Field(default=..., description="""Receiver URL.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload', 'WebhookSubscription']} })
    filter: Any = Field(default=..., description="""SubscriptionFilter object.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['WebhookSubscriptionCreatedPayload', 'WebhookSubscription']} })
    payload_mode: str = Field(default=..., description="""thin, delta or full.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload', 'WebhookSubscription']} })
    event_schema_version: Optional[str] = Field(default=None, description="""Schema pin.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload', 'WebhookSubscription']} })
    expires_at: Optional[str] = Field(default=None, description="""ISO-8601 time after which the subscription stops.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookSecret',
                       'AgentToken',
                       'AuthSession',
                       'AgentTokenIssuedPayload',
                       'IntegrationSecret']} })
    secret_id: str = Field(default=..., description="""Id of the first signing secret (not the secret).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscriptionSecretRotatedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'ActionDefinition',
                       'WebhookSecret',
                       'IntegrationSecret']} })


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
                       'IntegrationAppRevisedPayload',
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
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })
    detail: Optional[str] = Field(default=None, description="""Free-text detail, for example the failure counts.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionDisabledPayload',
                       'CloudEventData',
                       'AuthAudit']} })


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
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'ActionDefinition',
                       'WebhookSecret',
                       'IntegrationSecret']} })
    previous_secret_id: Optional[str] = Field(default=None, description="""Id of the secret that is being replaced.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionSecretRotatedPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'InboundEndpointSecretRotatedPayload']} })
    previous_expires_at: Optional[str] = Field(default=None, description="""ISO-8601 time when the previous secret stops signing.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionSecretRotatedPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'InboundEndpointSecretRotatedPayload']} })


class IntegrationAppEventPayload(EventPayload):
    """
    Payload of an `IntegrationApp.*` event. The stream is the app (`core.IntegrationApp`); no payload holds a secret.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True, 'from_schema': 'https://example.org/throughline/core/events'})

    pass


class ActionDefinitionEventPayload(EventPayload):
    """
    Payload of an `ActionDefinition.*` event. The stream is the definition (`core.ActionDefinition`); a secret is held outside the ledger.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True, 'from_schema': 'https://example.org/throughline/core/events'})

    pass


class ActionInvocationEventPayload(EventPayload):
    """
    Payload of an `Action.*` event. The stream is the invocation (`core.ActionInvocation`).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True, 'from_schema': 'https://example.org/throughline/core/events'})

    pass


class RuleEventPayload(EventPayload):
    """
    Payload of a `Rule.*` event. The stream is the rule (`core.Rule`).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True, 'from_schema': 'https://example.org/throughline/core/events'})

    pass


class InboundEndpointEventPayload(EventPayload):
    """
    Payload of an `InboundEndpoint.*` event. The stream is the endpoint (`core.InboundEndpoint`); a secret is held outside the ledger.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True, 'from_schema': 'https://example.org/throughline/core/events'})

    pass


class InboundDeliveryEventPayload(EventPayload):
    """
    Payload of an `Inbound.*` event. The stream is the delivery (`core.InboundDelivery`); no payload holds the request body, a header or a secret.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True, 'from_schema': 'https://example.org/throughline/core/events'})

    pass


class EnricherEventPayload(EventPayload):
    """
    Payload of an `Enricher.*` event. The stream is the enricher (`core.Enricher`).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True, 'from_schema': 'https://example.org/throughline/core/events'})

    pass


class EnrichmentEventPayload(EventPayload):
    """
    Payload of an `Enrichment.*` event. The stream is the value (`core.EnrichmentValue`).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True, 'from_schema': 'https://example.org/throughline/core/events'})

    pass


class IntegrationAppRegisteredPayload(IntegrationAppEventPayload):
    """
    An integration app was registered. Its name is the first segment of its inbound paths.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'IntegrationApp.Registered'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"app_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P1", '
                                '"description": "Results from the NDE contractor", '
                                '"enabled": true, "label": "Acme NDE", "name": '
                                '"acme-nde", "owner": "user:jsmith"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    app_id: str = Field(default=..., description="""App id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload', 'IntegrationApp']} })
    name: str = Field(default=..., description="""Slug, unique across the ledger.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookCursor',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RuleCursor',
                       'EnrichmentCursor']} })
    label: str = Field(default=..., description="""Label.""", json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'IntegrationApp',
                       'ActionDefinition',
                       'AgentToken',
                       'AgentTokenIssuedPayload']} })
    description: Optional[str] = Field(default=None, description="""Description.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'SettingDefinition',
                       'IntegrationApp',
                       'ActionDefinition']} })
    owner: str = Field(default=..., description="""Owner actor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'SettingDefinition',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    enabled: Optional[bool] = Field(default=None, description="""Whether its endpoints, rules, actions and enrichers run.""", json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher']} })


class IntegrationAppRevisedPayload(IntegrationAppEventPayload):
    """
    An app's label, description or owner changed.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'IntegrationApp.Revised'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"changes": {"label": ["Acme NDE", "Acme NDE '
                                'results"]}, "reason": "renamed"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    changes: Any = Field(default=..., description="""Object of field name to [old, new].""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordUpdatedPayload',
                       'RecordCorrectedPayload',
                       'WebhookSubscriptionUpdatedPayload',
                       'IntegrationAppRevisedPayload',
                       'CloudEventData']} })
    reason: Optional[str] = Field(default=None, description="""Why.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class IntegrationAppEnabledPayload(IntegrationAppEventPayload):
    """
    An app was switched on: its endpoints, rules, actions and enrichers run again.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'IntegrationApp.Enabled'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"reason": "contract renewed"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    reason: Optional[str] = Field(default=None, description="""Why.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class IntegrationAppDisabledPayload(IntegrationAppEventPayload):
    """
    An app was switched off: its endpoints answer 404 and its rules, actions and enrichers do nothing.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'IntegrationApp.Disabled'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"reason": "contractor offboarded"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    reason: Optional[str] = Field(default=None, description="""Why.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class ActionDefinitionDefinedPayload(ActionDefinitionEventPayload):
    """
    An action was defined (version 1). A webhook action's signing secret is held outside the ledger.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'ActionDefinition.Defined'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"access": "user", "applies_to": {"condition": null, '
                                '"record_types": ["core.Record"]}, "definition_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P2", "description": "Send an '
                                'inspection request to the NDE contractor", "enabled": '
                                'true, "executor": "webhook", "executor_config": '
                                '{"kind": "webhook", "timeout_s": 10.0, "url": '
                                '"https://nde.example.net/hooks/request"}, '
                                '"integration_app": "acme-nde", "label": "Send to '
                                'NDE", "name": "send_to_nde", "owner": "user:jsmith", '
                                '"parameters": [{"choices": ["RT", "UT"], "kind": '
                                '"string", "label": "Method", "max_length": null, '
                                '"name": "method", "required": true}], '
                                '"requires_approval": false, "result_handling": '
                                '["store"], "secret_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P3", '
                                '"side_effect_class": "external", "version": 1}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    definition_id: str = Field(default=..., description="""Definition id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'ActionRequestedPayload',
                       'ActionDefinition',
                       'ActionInvocation']} })
    name: str = Field(default=..., description="""Action name (slug).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookCursor',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RuleCursor',
                       'EnrichmentCursor']} })
    label: str = Field(default=..., description="""Label.""", json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'IntegrationApp',
                       'ActionDefinition',
                       'AgentToken',
                       'AgentTokenIssuedPayload']} })
    description: Optional[str] = Field(default=None, description="""Description.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'SettingDefinition',
                       'IntegrationApp',
                       'ActionDefinition']} })
    version: int = Field(default=..., description="""Definition version.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    applies_to: Any = Field(default=..., description="""ActionTarget object: record type globs and an optional condition.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionDefinitionDefinedPayload', 'ActionDefinition']} })
    parameters: Any = Field(default=..., description="""List of ActionParameter objects.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionDefinitionDefinedPayload',
                       'ActionRequestedPayload',
                       'ActionDefinition',
                       'ActionInvocation']} })
    executor: str = Field(default=..., description="""job or webhook.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload', 'ActionDefinition']} })
    executor_config: Any = Field(default=..., description="""Executor configuration; never a secret.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionDefinitionDefinedPayload', 'ActionDefinition']} })
    side_effect_class: str = Field(default=..., description="""read, propose, write or external.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload', 'ActionDefinition']} })
    requires_approval: Optional[bool] = Field(default=None, description="""Whether an invocation waits for a second person.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload', 'ActionDefinition']} })
    access: str = Field(default=..., description="""user, controller or admin.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher']} })
    result_handling: Any = Field(default=..., description="""List of store and post_to_feed.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionDefinitionDefinedPayload', 'ActionDefinition']} })
    owner: str = Field(default=..., description="""Owner actor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'SettingDefinition',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    enabled: Optional[bool] = Field(default=None, description="""Whether it can be invoked.""", json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher']} })
    integration_app: Optional[str] = Field(default=None, description="""Integration app name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'ActionDefinition',
                       'Rule',
                       'Enricher']} })
    secret_id: Optional[str] = Field(default=None, description="""Id of the first signing secret of a webhook action (not the secret).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscriptionSecretRotatedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'ActionDefinition',
                       'WebhookSecret',
                       'IntegrationSecret']} })


class ActionDefinitionRevisedPayload(ActionDefinitionEventPayload):
    """
    An action was revised; the event carries the whole new definition and the row is replaced.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'ActionDefinition.Revised'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"definition": {"label": "Send to NDE contractor", '
                                '"name": "send_to_nde", "version": 2}, '
                                '"definition_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P2", '
                                '"reason": "label", "version": 2}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    definition_id: str = Field(default=..., description="""Definition id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'ActionRequestedPayload',
                       'ActionDefinition',
                       'ActionInvocation']} })
    version: int = Field(default=..., description="""The new definition version.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    definition: Any = Field(default=..., description="""The new definition (no secret).""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionDefinitionRevisedPayload', 'InboundEndpointVersion']} })
    reason: str = Field(default=..., description="""Why.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class ActionDefinitionRetiredPayload(ActionDefinitionEventPayload):
    """
    An action was retired: it can no longer be invoked; its invocations stay readable.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'ActionDefinition.Retired'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"definition_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P2", '
                                '"reason": "replaced by send_to_nde_v2"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    definition_id: str = Field(default=..., description="""Definition id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'ActionRequestedPayload',
                       'ActionDefinition',
                       'ActionInvocation']} })
    reason: str = Field(default=..., description="""Why.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class ActionDefinitionSecretRotatedPayload(ActionDefinitionEventPayload):
    """
    A new signing secret was issued for a webhook action; the previous one keeps verifying until the overlap ends.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'ActionDefinition.SecretRotated'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"definition_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P2", '
                                '"previous_expires_at": "2026-10-18T03:14:07.000000Z", '
                                '"previous_secret_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P3", '
                                '"secret_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P4"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    definition_id: str = Field(default=..., description="""Definition id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'ActionRequestedPayload',
                       'ActionDefinition',
                       'ActionInvocation']} })
    secret_id: str = Field(default=..., description="""Id of the new secret (not the secret).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscriptionSecretRotatedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'ActionDefinition',
                       'WebhookSecret',
                       'IntegrationSecret']} })
    previous_secret_id: Optional[str] = Field(default=None, description="""Id of the secret being replaced.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionSecretRotatedPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'InboundEndpointSecretRotatedPayload']} })
    previous_expires_at: Optional[str] = Field(default=None, description="""ISO-8601 time when the previous secret stops.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionSecretRotatedPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'InboundEndpointSecretRotatedPayload']} })


class ActionRequestedPayload(ActionInvocationEventPayload):
    """
    An action was requested on records. The execution is queued as a job.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Action.Requested'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"action": "send_to_nde", "action_version": 1, '
                                '"definition_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P2", '
                                '"invocation_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", '
                                '"invoked_by": "user:jsmith", "parameters": {"method": '
                                '"RT"}, "targets": [{"id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P6", "key": "47-1234-W012", '
                                '"record_type": "core.Record", "version": 3}]}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    invocation_id: str = Field(default=..., description="""Invocation id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload',
                       'ActionRunningPayload',
                       'ActionCompletedPayload',
                       'ActionFailedPayload',
                       'ActionInvocation',
                       'ActionInvocationTarget']} })
    action: str = Field(default=..., description="""Action name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload', 'ActionInvocation']} })
    action_version: int = Field(default=..., description="""Definition version run.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload', 'ActionInvocation']} })
    definition_id: str = Field(default=..., description="""Definition id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'ActionRequestedPayload',
                       'ActionDefinition',
                       'ActionInvocation']} })
    targets: Any = Field(default=..., description="""List of RecordRef objects.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionRequestedPayload', 'ActionInvocation']} })
    parameters: Any = Field(default=..., description="""Parameters as validated against the definition.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionDefinitionDefinedPayload',
                       'ActionRequestedPayload',
                       'ActionDefinition',
                       'ActionInvocation']} })
    invoked_by: str = Field(default=..., description="""Who asked.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload', 'ActionInvocation']} })
    proposal_id: Optional[str] = Field(default=None, description="""The accepted proposal this came from, when the action requires approval.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload',
                       'ProposalCreatedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'ProposalRow',
                       'ActionInvocation']} })


class ActionRunningPayload(ActionInvocationEventPayload):
    """
    A worker started an attempt.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Action.Running'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"attempt": 1, "invocation_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    invocation_id: str = Field(default=..., description="""Invocation id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload',
                       'ActionRunningPayload',
                       'ActionCompletedPayload',
                       'ActionFailedPayload',
                       'ActionInvocation',
                       'ActionInvocationTarget']} })
    attempt: int = Field(default=..., description="""Attempt number, from 1.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRunningPayload',
                       'ActionCompletedPayload',
                       'ActionFailedPayload',
                       'ActionInvocation',
                       'WebhookAttempt',
                       'JobQueue']} })


class ActionCompletedPayload(ActionInvocationEventPayload):
    """
    The executor finished the action.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Action.Completed'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"attempt": 1, "http_status": 200, "invocation_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", "result": {"accepted": '
                                'true}}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    invocation_id: str = Field(default=..., description="""Invocation id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload',
                       'ActionRunningPayload',
                       'ActionCompletedPayload',
                       'ActionFailedPayload',
                       'ActionInvocation',
                       'ActionInvocationTarget']} })
    attempt: int = Field(default=..., description="""Attempt number.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRunningPayload',
                       'ActionCompletedPayload',
                       'ActionFailedPayload',
                       'ActionInvocation',
                       'WebhookAttempt',
                       'JobQueue']} })
    result: Optional[Any] = Field(default=None, description="""The executor's bounded JSON result.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionCompletedPayload', 'ActionInvocation']} })
    http_status: Optional[int] = Field(default=None, description="""HTTP status of a webhook action.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionCompletedPayload',
                       'ActionFailedPayload',
                       'ActionInvocation']} })


class ActionFailedPayload(ActionInvocationEventPayload):
    """
    The action failed for good (not retried any more).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Action.Failed'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"attempt": 3, "http_status": 503, "invocation_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P5", "problems": [{"code": '
                                '"http_error", "message": "The receiver answered '
                                '503."}]}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    invocation_id: str = Field(default=..., description="""Invocation id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload',
                       'ActionRunningPayload',
                       'ActionCompletedPayload',
                       'ActionFailedPayload',
                       'ActionInvocation',
                       'ActionInvocationTarget']} })
    attempt: int = Field(default=..., description="""Attempt number.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRunningPayload',
                       'ActionCompletedPayload',
                       'ActionFailedPayload',
                       'ActionInvocation',
                       'WebhookAttempt',
                       'JobQueue']} })
    problems: Any = Field(default=..., description="""List of Problem objects (code and message).""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionFailedPayload', 'RuleBlockedPayload', 'ActionInvocation']} })
    http_status: Optional[int] = Field(default=None, description="""HTTP status of a webhook action.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionCompletedPayload',
                       'ActionFailedPayload',
                       'ActionInvocation']} })


class RuleCreatedPayload(RuleEventPayload):
    """
    A rule was created. It starts disabled and in propose mode.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Rule.Created'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"access": "user", "condition": null, "enabled": '
                                'false, "integration_app": null, "key": "hse-notify", '
                                '"mode": "propose", "owner": "user:jsmith", "rule_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P7", "service_actor": '
                                '"svc:rule-hse-notify", "then": [{"args": {"body": '
                                '"HSE notified of ${subject_key}"}, "command": '
                                '"PostToFeed"}], "title": "Notify HSE on #safety", '
                                '"version": 1, "when": {"event_types": '
                                '["Feed.PostCreated"], "hashtags": ["safety"]}}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    rule_id: str = Field(default=..., description="""Rule id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'RuleBlockedPayload',
                       'Rule',
                       'RuleFiring']} })
    key: str = Field(default=..., description="""Rule key (slug).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'RuleCreatedPayload',
                       'SettingDefinition',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'EventOrigin',
                       'EventLinkRef',
                       'Rule']} })
    title: str = Field(default=..., description="""Title.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'RuleCreatedPayload',
                       'Rule']} })
    version: int = Field(default=..., description="""Rule version.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    when: Any = Field(default=..., description="""SubscriptionFilter object.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RuleCreatedPayload',
                       'EnricherRegisteredPayload',
                       'Rule',
                       'Enricher']} })
    condition: Optional[str] = Field(default=None, description="""Query-language condition on the subject record.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleCreatedPayload', 'Rule']} })
    then: Any = Field(default=..., description="""List of RuleStep objects.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RuleCreatedPayload', 'Rule']} })
    mode: str = Field(default=..., description="""act or propose.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleCreatedPayload', 'Rule']} })
    service_actor: str = Field(default=..., description="""svc:rule-<slug>.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher']} })
    access: str = Field(default=..., description="""user or controller.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher']} })
    owner: str = Field(default=..., description="""Owner actor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'SettingDefinition',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    enabled: Optional[bool] = Field(default=None, description="""Whether it runs.""", json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher']} })
    integration_app: Optional[str] = Field(default=None, description="""Integration app name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'ActionDefinition',
                       'Rule',
                       'Enricher']} })


class RuleRevisedPayload(RuleEventPayload):
    """
    A rule was revised; the event carries the whole new rule. Switching to act mode is a revision with a reason.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Rule.Revised'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"reason": "ready to act", "rule": {"key": '
                                '"hse-notify", "mode": "act", "version": 2}, '
                                '"rule_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P7", "version": '
                                '2}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    rule_id: str = Field(default=..., description="""Rule id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'RuleBlockedPayload',
                       'Rule',
                       'RuleFiring']} })
    version: int = Field(default=..., description="""The new rule version.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    rule: Any = Field(default=..., description="""The new rule.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RuleRevisedPayload']} })
    reason: str = Field(default=..., description="""Why.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class RuleEnabledPayload(RuleEventPayload):
    """
    A rule was switched on, from this event on.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Rule.Enabled'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"reason": "after dry run", "rule_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P7"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    rule_id: str = Field(default=..., description="""Rule id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'RuleBlockedPayload',
                       'Rule',
                       'RuleFiring']} })
    reason: Optional[str] = Field(default=None, description="""Why.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class RuleDisabledPayload(RuleEventPayload):
    """
    A rule was switched off.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Rule.Disabled'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"reason": "noisy", "rule_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P7"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    rule_id: str = Field(default=..., description="""Rule id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'RuleBlockedPayload',
                       'Rule',
                       'RuleFiring']} })
    reason: Optional[str] = Field(default=None, description="""Why.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class RuleBlockedPayload(RuleEventPayload):
    """
    A matched event did not run the rule: the step was refused, the causation depth limit or a budget stopped it.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Rule.Blocked'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"depth": 3, "outcome": "depth_limit", "problems": '
                                '[{"code": "depth_limit", "message": "The causation '
                                'depth limit of 3 was reached."}], "rule_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P7", "rule_version": 2, '
                                '"trigger_event_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P8", '
                                '"trigger_seq": 412}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    rule_id: str = Field(default=..., description="""Rule id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'RuleBlockedPayload',
                       'Rule',
                       'RuleFiring']} })
    rule_version: int = Field(default=..., description="""Rule version.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleBlockedPayload', 'RuleFiring']} })
    trigger_event_id: str = Field(default=..., description="""The event that matched.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleBlockedPayload']} })
    trigger_seq: int = Field(default=..., description="""Its seq.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleBlockedPayload']} })
    depth: int = Field(default=..., description="""Causation depth of the trigger.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleBlockedPayload', 'RuleFiring']} })
    outcome: str = Field(default=..., description="""refused, depth_limit or budget.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleBlockedPayload', 'WebhookAttempt', 'RuleFiring']} })
    problems: Any = Field(default=..., description="""List of Problem objects.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionFailedPayload', 'RuleBlockedPayload', 'ActionInvocation']} })


class InboundEndpointCreatedPayload(InboundEndpointEventPayload):
    """
    An inbound endpoint was created. It starts disabled and in dry-run mode. Its secret is held outside the ledger.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'InboundEndpoint.Created'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"access": "user", "allowed_commands": '
                                '["SetPsetValues"], "app": "acme-nde", "auth": '
                                '"hmac_sha256", "dry_run": true, "enabled": false, '
                                '"endpoint_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9", '
                                '"external_schema": null, "mapping": '
                                '"results.{\\"command\\": \\"SetPsetValues\\", '
                                '\\"args\\": {\\"stream_id\\": {\\"$key\\": weld}, '
                                '\\"pset\\": \\"nde\\", \\"values\\": {\\"result\\": '
                                'result}}}", "mapping_language": '
                                '"jsonata-restricted@1", "max_body_bytes": 262144, '
                                '"name": "results", "owner": "user:jsmith", '
                                '"rate_per_minute": 60, "secret_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P10", "service_actor": '
                                '"svc:inbound-acme-nde-results", "version": 1}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    endpoint_id: str = Field(default=..., description="""Endpoint id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'InboundReceivedPayload',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'InboundReplay',
                       'InboundDelivery',
                       'InboundCounter']} })
    app: str = Field(default=..., description="""Integration app name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload', 'InboundEndpoint']} })
    name: str = Field(default=..., description="""Endpoint name (slug).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookCursor',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RuleCursor',
                       'EnrichmentCursor']} })
    version: int = Field(default=..., description="""Endpoint version.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    auth: str = Field(default=..., description="""hmac_sha256 or jwt_hs256.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload', 'InboundEndpoint']} })
    mapping: str = Field(default=..., description="""Restricted JSONata expression.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload', 'InboundEndpoint']} })
    mapping_language: str = Field(default=..., description="""jsonata-restricted@1.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload', 'InboundEndpoint']} })
    external_schema: Optional[str] = Field(default=None, description="""Which external schema the mapping reads.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload', 'InboundEndpoint']} })
    allowed_commands: Any = Field(default=..., description="""List of command names.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['InboundEndpointCreatedPayload', 'InboundEndpoint']} })
    service_actor: str = Field(default=..., description="""svc:inbound-<slug>.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher']} })
    access: str = Field(default=..., description="""user or controller.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher']} })
    max_body_bytes: int = Field(default=..., description="""Body cap.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload', 'InboundEndpoint']} })
    rate_per_minute: int = Field(default=..., description="""Rate bound.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload', 'InboundEndpoint']} })
    dry_run: Optional[bool] = Field(default=None, description="""Verify, map and plan only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload',
                       'InboundAppliedPayload',
                       'InboundEndpoint']} })
    enabled: Optional[bool] = Field(default=None, description="""Whether it accepts deliveries.""", json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher']} })
    owner: str = Field(default=..., description="""Owner actor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'SettingDefinition',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    secret_id: str = Field(default=..., description="""Id of the first secret (not the secret).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscriptionSecretRotatedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'ActionDefinition',
                       'WebhookSecret',
                       'IntegrationSecret']} })


class InboundEndpointRevisedPayload(InboundEndpointEventPayload):
    """
    An endpoint was revised; the event carries the whole new definition (no secret).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'InboundEndpoint.Revised'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"endpoint": {"dry_run": false, "name": "results", '
                                '"version": 2}, "endpoint_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P9", "reason": "go live", '
                                '"version": 2}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    endpoint_id: str = Field(default=..., description="""Endpoint id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'InboundReceivedPayload',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'InboundReplay',
                       'InboundDelivery',
                       'InboundCounter']} })
    version: int = Field(default=..., description="""The new endpoint version.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    endpoint: Any = Field(default=..., description="""The new definition.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['InboundEndpointRevisedPayload']} })
    reason: str = Field(default=..., description="""Why.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class InboundEndpointEnabledPayload(InboundEndpointEventPayload):
    """
    An endpoint started accepting deliveries.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'InboundEndpoint.Enabled'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"endpoint_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9", '
                                '"reason": "go live"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    endpoint_id: str = Field(default=..., description="""Endpoint id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'InboundReceivedPayload',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'InboundReplay',
                       'InboundDelivery',
                       'InboundCounter']} })
    reason: Optional[str] = Field(default=None, description="""Why.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class InboundEndpointDisabledPayload(InboundEndpointEventPayload):
    """
    An endpoint stopped accepting deliveries; it answers 404.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'InboundEndpoint.Disabled'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"endpoint_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9", '
                                '"reason": "key leaked"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    endpoint_id: str = Field(default=..., description="""Endpoint id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'InboundReceivedPayload',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'InboundReplay',
                       'InboundDelivery',
                       'InboundCounter']} })
    reason: Optional[str] = Field(default=None, description="""Why.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class InboundEndpointSecretRotatedPayload(InboundEndpointEventPayload):
    """
    A new secret was issued; the previous one keeps verifying until the overlap ends (at most 24 hours).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'InboundEndpoint.SecretRotated'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"endpoint_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9", '
                                '"previous_expires_at": "2026-10-18T03:14:07.000000Z", '
                                '"previous_secret_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P10", '
                                '"secret_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P11"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    endpoint_id: str = Field(default=..., description="""Endpoint id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'InboundReceivedPayload',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'InboundReplay',
                       'InboundDelivery',
                       'InboundCounter']} })
    secret_id: str = Field(default=..., description="""Id of the new secret (not the secret).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscriptionSecretRotatedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'ActionDefinition',
                       'WebhookSecret',
                       'IntegrationSecret']} })
    previous_secret_id: Optional[str] = Field(default=None, description="""Id of the secret being replaced.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionSecretRotatedPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'InboundEndpointSecretRotatedPayload']} })
    previous_expires_at: Optional[str] = Field(default=None, description="""ISO-8601 time when the previous secret stops.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionSecretRotatedPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'InboundEndpointSecretRotatedPayload']} })


class InboundReceivedPayload(InboundDeliveryEventPayload):
    """
    A signed POST was accepted and queued for mapping. The payload and the headers are not in the event.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Inbound.Received'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"delivery_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P12", '
                                '"endpoint_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9", '
                                '"endpoint_version": 2, "payload_sha256": '
                                '"0000000000000000000000000000000000000000000000000000000000000000", '
                                '"payload_size": 412}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    delivery_id: str = Field(default=..., description="""Delivery id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundReceivedPayload',
                       'InboundAppliedPayload',
                       'InboundFailedPayload',
                       'InboundRetriedPayload',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'InboundDelivery']} })
    endpoint_id: str = Field(default=..., description="""Endpoint id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'InboundReceivedPayload',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'InboundReplay',
                       'InboundDelivery',
                       'InboundCounter']} })
    endpoint_version: int = Field(default=..., description="""The endpoint version it will be mapped by.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundReceivedPayload', 'InboundDelivery']} })
    payload_sha256: str = Field(default=..., description="""SHA-256 of the raw body.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundReceivedPayload', 'InboundDelivery']} })
    payload_size: int = Field(default=..., description="""Body size in bytes.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundReceivedPayload', 'InboundDelivery']} })


class InboundAppliedPayload(InboundDeliveryEventPayload):
    """
    A delivery was mapped and its commands ran (or, for a dry-run endpoint, were planned).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Inbound.Applied'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"command_count": 2, "delivery_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P12", "dry_run": false}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    delivery_id: str = Field(default=..., description="""Delivery id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundReceivedPayload',
                       'InboundAppliedPayload',
                       'InboundFailedPayload',
                       'InboundRetriedPayload',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'InboundDelivery']} })
    command_count: int = Field(default=..., description="""Commands run or planned.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundAppliedPayload', 'InboundDelivery', 'RuleFiring']} })
    dry_run: bool = Field(default=..., description="""True when nothing ran.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload',
                       'InboundAppliedPayload',
                       'InboundEndpoint']} })


class InboundFailedPayload(InboundDeliveryEventPayload):
    """
    A delivery could not be applied; it is in the error queue until an admin retries it.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Inbound.Failed'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"code": "key_not_found", "delivery_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P12", "message": "No record '
                                'has the key 47-1234-W099."}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    delivery_id: str = Field(default=..., description="""Delivery id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundReceivedPayload',
                       'InboundAppliedPayload',
                       'InboundFailedPayload',
                       'InboundRetriedPayload',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'InboundDelivery']} })
    code: str = Field(default=..., description="""A fixed code.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundFailedPayload', 'InboundCounter']} })
    message: str = Field(default=..., description="""A bounded message; never a payload excerpt.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundFailedPayload']} })


class InboundRetriedPayload(InboundDeliveryEventPayload):
    """
    An admin re-ran a failed delivery, optionally with a corrected payload.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Inbound.Retried'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"by": "user:jsmith", "corrected_sha256": '
                                '"1111111111111111111111111111111111111111111111111111111111111111", '
                                '"delivery_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P12", '
                                '"original_sha256": '
                                '"0000000000000000000000000000000000000000000000000000000000000000"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    delivery_id: str = Field(default=..., description="""Delivery id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundReceivedPayload',
                       'InboundAppliedPayload',
                       'InboundFailedPayload',
                       'InboundRetriedPayload',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'InboundDelivery']} })
    by: str = Field(default=..., description="""The admin.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundRetriedPayload',
                       'EnrichmentAcceptedPayload',
                       'EnrichmentRejectedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'AccountPasswordChangedPayload']} })
    original_sha256: str = Field(default=..., description="""SHA-256 of the received body.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundRetriedPayload']} })
    corrected_sha256: Optional[str] = Field(default=None, description="""SHA-256 of the corrected body, when one was supplied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundRetriedPayload']} })


class EnricherRegisteredPayload(EnricherEventPayload):
    """
    An enricher was registered. It starts disabled.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Enricher.Registered'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"access": "user", "code_version": "1.0.0", '
                                '"enabled": false, "enricher_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P13", "integration_app": '
                                'null, "model_ref": null, "name": "doc_classifier", '
                                '"owner": "user:jsmith", "properties": [{"kind": '
                                '"string", "name": "doc_type", "policy": "propose", '
                                '"threshold": 0.9}], "service_actor": '
                                '"svc:enricher-doc-classifier", "version": 1, "when": '
                                '{"event_types": ["File.Processed"]}}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    enricher_id: str = Field(default=..., description="""Enricher id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'Enricher']} })
    name: str = Field(default=..., description="""Enricher name; one path segment of the enrich. layer.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookCursor',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RuleCursor',
                       'EnrichmentCursor']} })
    version: int = Field(default=..., description="""Registration version.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    code_version: str = Field(default=..., description="""The plugin's own version.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnricherRegisteredPayload', 'Enricher']} })
    model_ref: Optional[str] = Field(default=None, description="""Null for a deterministic enricher.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnricherRegisteredPayload',
                       'EnrichmentProposedPayload',
                       'Enricher',
                       'EnrichmentValue']} })
    when: Any = Field(default=..., description="""SubscriptionFilter object.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RuleCreatedPayload',
                       'EnricherRegisteredPayload',
                       'Rule',
                       'Enricher']} })
    properties: Any = Field(default=..., description="""List of {name, kind, policy, threshold}.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['EnricherRegisteredPayload', 'Enricher']} })
    service_actor: str = Field(default=..., description="""svc:enricher-<slug>.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher']} })
    access: str = Field(default=..., description="""user or controller.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher']} })
    owner: str = Field(default=..., description="""Owner actor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'SettingDefinition',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    enabled: Optional[bool] = Field(default=None, description="""Whether it runs.""", json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher']} })
    integration_app: Optional[str] = Field(default=None, description="""Integration app name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'ActionDefinition',
                       'Rule',
                       'Enricher']} })


class EnricherRevisedPayload(EnricherEventPayload):
    """
    An enricher's registration changed; the event carries the whole new registration.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Enricher.Revised'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"enricher": {"name": "doc_classifier", "version": '
                                '2}, "enricher_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P13", '
                                '"reason": "auto-accept above 0.95", "version": 2}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    enricher_id: str = Field(default=..., description="""Enricher id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'Enricher']} })
    version: int = Field(default=..., description="""The new registration version.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    enricher: Any = Field(default=..., description="""The new registration.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['EnricherRevisedPayload',
                       'EnrichmentProposedPayload',
                       'EnrichmentValue']} })
    reason: str = Field(default=..., description="""Why.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class EnricherEnabledPayload(EnricherEventPayload):
    """
    An enricher was switched on.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Enricher.Enabled'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"enricher_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P13", '
                                '"reason": "after evaluation"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    enricher_id: str = Field(default=..., description="""Enricher id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'Enricher']} })
    reason: Optional[str] = Field(default=None, description="""Why.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class EnricherDisabledPayload(EnricherEventPayload):
    """
    An enricher was switched off.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Enricher.Disabled'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"enricher_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P13", '
                                '"reason": "wrong labels"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    enricher_id: str = Field(default=..., description="""Enricher id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'Enricher']} })
    reason: Optional[str] = Field(default=None, description="""Why.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class EnrichmentProposedPayload(EnrichmentEventPayload):
    """
    An enricher proposed a value for a property of its own layer of a record. A shadow value is for evaluation and admins only.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Enrichment.Proposed'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"acceptance_state": "proposed", "confidence": 0.9, '
                                '"enricher": "doc_classifier", "enricher_version": '
                                '"1.0.0", "inputs": [{"file_sha256": '
                                '"2222222222222222222222222222222222222222222222222222222222222222", '
                                '"record": {"id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6", "key": '
                                '"ISD-001", "record_type": "documents.Document", '
                                '"version": 4}}], "model_ref": null, "produced_at": '
                                '"2026-10-17T03:14:07.000000Z", "property_path": '
                                '"enrich.doc_classifier.doc_type", "target": {"id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P6", "key": "ISD-001", '
                                '"record_type": "documents.Document", "version": 4}, '
                                '"value": "ISO", "value_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P14"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    value_id: str = Field(default=..., description="""Value id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnrichmentProposedPayload',
                       'EnrichmentAcceptedPayload',
                       'EnrichmentRejectedPayload',
                       'EnrichmentValue']} })
    target: Any = Field(default=..., description="""RecordRef of the record.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['EnrichmentProposedPayload', 'EnrichmentValue']} })
    property_path: str = Field(default=..., description="""enrich.<enricher>.<property>.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnrichmentProposedPayload', 'EnrichmentValue']} })
    value: Optional[Any] = Field(default=None, description="""A scalar or a list of scalars.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['EnrichmentProposedPayload',
                       'SettingChangeRow',
                       'EnrichmentValue']} })
    enricher: str = Field(default=..., description="""Enricher name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnricherRevisedPayload',
                       'EnrichmentProposedPayload',
                       'EnrichmentValue']} })
    enricher_version: str = Field(default=..., description="""The plugin's version.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnrichmentProposedPayload', 'EnrichmentValue']} })
    confidence: float = Field(default=..., description="""0 to 1.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'EnrichmentProposedPayload',
                       'EnrichmentValue']} })
    inputs: Any = Field(default=..., description="""List of {record, file_sha256}: what the value was made from.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['EnrichmentProposedPayload', 'EnrichmentValue']} })
    model_ref: Optional[str] = Field(default=None, description="""Null for a deterministic enricher.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnricherRegisteredPayload',
                       'EnrichmentProposedPayload',
                       'Enricher',
                       'EnrichmentValue']} })
    produced_at: str = Field(default=..., description="""ISO-8601 time.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnrichmentProposedPayload', 'EnrichmentValue']} })
    acceptance_state: str = Field(default=..., description="""shadow or proposed.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnrichmentProposedPayload', 'EnrichmentValue']} })


class EnrichmentAcceptedPayload(EnrichmentEventPayload):
    """
    A person (or the enricher's own auto policy) accepted a value: it is now written to the enricher's layer of the record.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Enrichment.Accepted'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"automatic": false, "by": "user:mlee", "value_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P14"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    value_id: str = Field(default=..., description="""Value id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnrichmentProposedPayload',
                       'EnrichmentAcceptedPayload',
                       'EnrichmentRejectedPayload',
                       'EnrichmentValue']} })
    by: str = Field(default=..., description="""The accepting person, or the enricher's service actor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundRetriedPayload',
                       'EnrichmentAcceptedPayload',
                       'EnrichmentRejectedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'AccountPasswordChangedPayload']} })
    automatic: bool = Field(default=..., description="""True for the auto policy.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnrichmentAcceptedPayload']} })


class EnrichmentRejectedPayload(EnrichmentEventPayload):
    """
    A value was rejected by a person, or replaced by a newer proposal.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Enrichment.Rejected'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"by": "user:mlee", "reason": "wrong type", '
                                '"value_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P14"}'}],
         'from_schema': 'https://example.org/throughline/core/events'})

    value_id: str = Field(default=..., description="""Value id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnrichmentProposedPayload',
                       'EnrichmentAcceptedPayload',
                       'EnrichmentRejectedPayload',
                       'EnrichmentValue']} })
    by: str = Field(default=..., description="""The person, or the enricher's service actor for a replacement.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundRetriedPayload',
                       'EnrichmentAcceptedPayload',
                       'EnrichmentRejectedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'AccountPasswordChangedPayload']} })
    reason: str = Field(default=..., description="""Why.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class FeedTag(ConfiguredBaseModel):
    """
    One `#tag` or `@mention` found in a post body, as carried in the event payloads.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/feed'})

    text: str = Field(default=..., description="""The tag as written, without its leading sigil (`47-1234-S03`, `area:A12`, `party:acme-nde`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag']} })
    kind: TagKind = Field(default=..., description="""Kind of the tag after resolution.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag',
                       'Hashtag',
                       'Account',
                       'AccountCreatedPayload',
                       'JobQueue']} })
    start: int = Field(default=..., description="""Character offset of the sigil in the body.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag']} })
    end: int = Field(default=..., description="""Character offset just past the last character of the tag.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag']} })
    namespace: Optional[str] = Field(default=None, description="""For code and mention tags written `ns:value`, the part before the colon.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag',
                       'Hashtag',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    record_id: Optional[str] = Field(default=None, description="""For a record tag that resolved to a record, that record's id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue',
                       'LinkCount',
                       'WorkflowState',
                       'NumberingAllocatedPayload',
                       'FileUploadedPayload',
                       'FeedTag',
                       'Hashtag',
                       'File',
                       'ActionInvocationTarget',
                       'RecordBody',
                       'BodyQuarantine']} })


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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    actor: str = Field(default=..., description="""Actor of the aggregated events.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'EventCard',
                       'FeedItemRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'OutboxEvent',
                       'AuthAudit']} })
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
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


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
    One row of the feed: a post (with a tombstone once retracted) or an event card. Newest first by `occurred_at`, then `seq`. A card is extended while it is the scope's open card (`open_scope` is set); a scope has at most one open card, and it is the scope's newest card (the projector closes a card before it opens the next). This is not a unique key: a unique index on `open_scope` made every lookup and insert slower with each closed card within one transaction on Postgres, so a rebuild grew quadratically (P0-I8 D13). The newest card is found through the index on `(scope, first_seq)`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:ix_scope_first_seq': {'tag': 'tl:ix_scope_first_seq',
                                                   'value': 'scope, first_seq'},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_feed_items'}},
         'from_schema': 'https://example.org/throughline/core/feed'})

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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    actor: str = Field(default=..., description="""Author of a post, or the actor of a card's events.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'EventCard',
                       'FeedItemRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'OutboxEvent',
                       'AuthAudit']} })
    occurred_at: datetime  = Field(default=..., description="""`recorded_at` of the post, or of the latest event of a card.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow']} })
    seq: int = Field(default=..., description="""`seq` of the posted event, or of the latest event of a card.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['Event',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'ActionInvocation',
                       'InboundEndpointVersion',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'WebhookDelivery',
                       'RuleFiring']} })
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
    first_seq: Optional[int] = Field(default=None, description="""Cards only; `seq` of the first aggregated event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow', 'TypeRegistrationRow']} })
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
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })


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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    kind: TagKind = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag',
                       'Hashtag',
                       'Account',
                       'AccountCreatedPayload',
                       'JobQueue']} })
    tag_text: str = Field(default=..., description="""The tag as written, without its sigil. For a card's subject row, the record id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Hashtag']} })
    tag_key: str = Field(default=..., description="""Normalised text used to find the tag's feed (lower case). For a card's subject row, the record id.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['Hashtag']} })
    namespace: Optional[str] = Field(default=None, description="""For code and mention tags, the part before the colon.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag',
                       'Hashtag',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    record_id: Optional[str] = Field(default=None, description="""For a resolved record tag, or a card's subject, the record.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['PsetValue',
                       'LinkCount',
                       'WorkflowState',
                       'NumberingAllocatedPayload',
                       'FileUploadedPayload',
                       'FeedTag',
                       'Hashtag',
                       'File',
                       'ActionInvocationTarget',
                       'RecordBody',
                       'BodyQuarantine']} })
    start_pos: int = Field(default=..., description="""Offset of the sigil in the post body; 0 for a card's subject row.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Hashtag']} })
    end_pos: int = Field(default=..., description="""Offset just past the tag; 0 for a card's subject row.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Hashtag']} })
    seq: int = Field(default=..., description="""`seq` of the event that added the row; orders a card's subjects.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'ActionInvocation',
                       'InboundEndpointVersion',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'WebhookDelivery',
                       'RuleFiring']} })


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

    proposal_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload',
                       'ProposalCreatedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'ProposalRow',
                       'ActionInvocation']} })
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

    proposal_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload',
                       'ProposalCreatedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'ProposalRow',
                       'ActionInvocation']} })
    by: str = Field(default=..., description="""The accepting person, `user:<id>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundRetriedPayload',
                       'EnrichmentAcceptedPayload',
                       'EnrichmentRejectedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'AccountPasswordChangedPayload']} })
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

    proposal_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload',
                       'ProposalCreatedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'ProposalRow',
                       'ActionInvocation']} })
    by: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['InboundRetriedPayload',
                       'EnrichmentAcceptedPayload',
                       'EnrichmentRejectedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'AccountPasswordChangedPayload']} })
    reason: str = Field(default=..., description="""Why, for the agent and the audit trail.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


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

    proposal_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload',
                       'ProposalCreatedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'ProposalRow',
                       'ActionInvocation']} })
    by: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['InboundRetriedPayload',
                       'EnrichmentAcceptedPayload',
                       'EnrichmentRejectedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'AccountPasswordChangedPayload']} })
    error: str = Field(default=..., description="""`<ErrorClass>: <message>` of the refusal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalFailedPayload', 'WebhookAttempt']} })


class ProposalRow(ConfiguredBaseModel):
    """
    One proposal: what was asked, by whom, and how it ended. Oldest first by `seq` is the review queue. `created_day` (UTC, from the `effective_at` of `Proposal.Created`) with `agent` is the budget key.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_proposals'}},
         'from_schema': 'https://example.org/throughline/core/proposals'})

    proposal_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload',
                       'ProposalCreatedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'ProposalRow',
                       'ActionInvocation']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
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
                       'ActionInvocation',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account'],
         'ifabsent': 'string(pending)'} })
    created_day: str = Field(default=..., description="""UTC day of creation, `YYYY-MM-DD`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['ProposalRow']} })
    created_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookDelivery',
                       'WebhookSecret',
                       'Account',
                       'AuthSession',
                       'AuthTokenSecret',
                       'IntegrationSecret']} })
    created_event_id: str = Field(default=..., description="""Event id of `Proposal.Created`; the cause of the accepted command's events.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalRow']} })
    decided_by: Optional[str] = Field(default=None, description="""The person who accepted, rejected or failed it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalRow', 'EnrichmentValue']} })
    decided_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalRow', 'EnrichmentValue']} })
    reason: Optional[str] = Field(default=None, description="""The rejection reason, or the error of a failed proposal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })
    result_stream_id: Optional[str] = Field(default=None, description="""Accepted only; the stream the command wrote to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalAcceptedPayload', 'ProposalRow']} })
    seq: int = Field(default=..., description="""`seq` of `Proposal.Created`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['Event',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'ActionInvocation',
                       'InboundEndpointVersion',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'WebhookDelivery',
                       'RuleFiring']} })
    version: Optional[int] = Field(default=None, description="""Ledger `stream_version` of the proposal stream after the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })


class SettingValidation(ConfiguredBaseModel):
    """
    Range, choices or pattern of a value. For `list` values `choices` and `pattern` apply to each item; for `duration` and `size` the range is in seconds and bytes.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/settings'})

    minimum: Optional[float] = Field(default=None, description="""Smallest allowed value.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingValidation']} })
    maximum: Optional[float] = Field(default=None, description="""Largest allowed value.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingValidation']} })
    choices: Optional[Any] = Field(default=None, description="""The allowed values (a JSON list), for an enum or the items of a list.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['SettingValidation']} })
    pattern: Optional[str] = Field(default=None, description="""Regular expression a string value (or each list item) must match in full.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter',
                       'NumberingAllocatedPayload',
                       'SettingValidation']} })


class SettingDefinition(ConfiguredBaseModel):
    """
    One setting (brief 30.1). Definitions are data: `schema/settings/platform.yaml` and the `settings.yaml` of an extension type package list them under a top-level `settings:` key.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/settings'})

    key: str = Field(default=..., description="""Dotted and namespaced, lower-case words, for example `feed.reactions.enabled`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'RuleCreatedPayload',
                       'SettingDefinition',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'EventOrigin',
                       'EventLinkRef',
                       'Rule']} })
    type: SettingType = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'SettingDefinition',
                       'EventOrigin',
                       'EventLinkRef',
                       'CloudEvent']} })
    default: Any = Field(default=..., description="""The platform default (a JSON value that satisfies `type` and `validation`).""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['SettingDefinition']} })
    description: str = Field(default=..., description="""One sentence shown beside the key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'SettingDefinition',
                       'IntegrationApp',
                       'ActionDefinition']} })
    docs: Optional[str] = Field(default=None, description="""Longer explanation shown in the detail pane.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingDefinition']} })
    scopes: list[SettingScope] = Field(default=..., description="""Which layers may set the key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingDefinition']} })
    lockable: Optional[bool] = Field(default=False, description="""Whether the company can lock the key, or bound its values, for its projects.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingDefinition'], 'ifabsent': 'false'} })
    validation: Optional[SettingValidation] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SettingDefinition']} })
    effect: Optional[SettingEffect] = Field(default=SettingEffect("live"), json_schema_extra = { "linkml_meta": {'domain_of': ['SettingDefinition', 'SettingEffectApplied'],
         'ifabsent': 'string(live)'} })
    sensitivity: Optional[SettingSensitivity] = Field(default=SettingSensitivity("normal"), json_schema_extra = { "linkml_meta": {'domain_of': ['SettingDefinition'], 'ifabsent': 'string(normal)'} })
    risk: Optional[SettingRisk] = Field(default=SettingRisk("normal"), json_schema_extra = { "linkml_meta": {'domain_of': ['SettingDefinition'], 'ifabsent': 'string(normal)'} })
    since: str = Field(default=..., description="""The platform or package version that introduced the key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingDefinition']} })
    deprecated: Optional[str] = Field(default=None, description="""Set when the key is going away; says what replaces it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingDefinition']} })
    owner: Optional[str] = Field(default="platform", description="""`platform`, or `<namespace>.<TypeName>` for the extension type that defines the key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'SettingDefinition',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow'],
         'ifabsent': 'string(platform)'} })

    @field_validator('key')
    def pattern_key(cls, v):
        pattern=re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.search(element):
                    err_msg = f"Invalid key format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.search(v):
            err_msg = f"Invalid key format: {v}"
            raise ValueError(err_msg)
        return v


class SettingChangedPayload(EventPayload):
    """
    One key was set, or reset to what the layer above gives, at one layer. The stream is `setting:<layer>:<key>`. A change with `applies_at` in the future takes effect then (and not before): resolution is time-based, so no job applies it.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Setting.Changed'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"accept_risk": false, "applies_at": null, "key": '
                                '"feed.reactions.enabled", "layer": "project:P123", '
                                '"new_value": false, "old_set": false, "old_value": '
                                'null, "reason": null, "reset": false}'}],
         'from_schema': 'https://example.org/throughline/core/settings'})

    key: str = Field(default=..., description="""The setting key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'RuleCreatedPayload',
                       'SettingDefinition',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'EventOrigin',
                       'EventLinkRef',
                       'Rule']} })
    layer: str = Field(default=..., description="""`company`, `project:<id>` or `user:<id>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue',
                       'PsetValuesSetPayload',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow']} })
    old_value: Optional[Any] = Field(default=None, description="""The value the layer held when the change was recorded (null when it held none).""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['SettingChangedPayload', 'SettingChangeRow']} })
    old_set: Optional[bool] = Field(default=None, description="""Whether the layer held a value of its own before (false: it was inheriting).""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingChangedPayload', 'SettingChangeRow']} })
    new_value: Optional[Any] = Field(default=None, description="""The new value; null with `reset` true.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['SettingChangedPayload']} })
    reset: Optional[bool] = Field(default=None, description="""True when the layer goes back to inheriting.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingChangedPayload', 'SettingChangeRow']} })
    reason: Optional[str] = Field(default=None, description="""Why. Required for `advanced` and `dangerous` keys.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })
    applies_at: Optional[datetime ] = Field(default=None, description="""When the change takes effect, if later than the time it was recorded.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingChangedPayload', 'SettingChangeRow']} })
    accept_risk: Optional[bool] = Field(default=None, description="""The person confirmed \"I accept the risk\" (a `dangerous` key).""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingChangedPayload', 'SettingChangeRow']} })


class SettingLockedPayload(EventPayload):
    """
    The company locked a key for its projects, unlocked it, or changed the bounds projects must keep to. The stream is `setting:company:<key>`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Setting.Locked'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"bounds": null, "key": "ai.agents.default_mode", '
                                '"layer": "company", "locked": true, "reason": '
                                '"Company policy: agents propose, people decide"}'}],
         'from_schema': 'https://example.org/throughline/core/settings'})

    key: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'RuleCreatedPayload',
                       'SettingDefinition',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'EventOrigin',
                       'EventLinkRef',
                       'Rule']} })
    layer: str = Field(default=..., description="""Always `company`; only the company layer locks or bounds a key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue',
                       'PsetValuesSetPayload',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow']} })
    locked: bool = Field(default=..., description="""True when projects may not override the key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingLockedPayload', 'SettingLockRow']} })
    bounds: Optional[Any] = Field(default=None, description="""Limits for project values: `minimum`, `maximum` and/or `choices`; null for none.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['SettingLockedPayload', 'SettingLockRow']} })
    reason: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class SettingChangeRow(ConfiguredBaseModel):
    """
    One `Setting.Changed` event: the history of a key at a layer, and the entries the resolver reads. The row in force at time t is the one with the greatest `effective_us` (then `seq`) not after t.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_setting'}},
         'from_schema': 'https://example.org/throughline/core/settings'})

    change_id: str = Field(default=..., description="""Event id of the `Setting.Changed` event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingChangeRow']} })
    key: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'RuleCreatedPayload',
                       'SettingDefinition',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'EventOrigin',
                       'EventLinkRef',
                       'Rule']} })
    layer: str = Field(default=..., description="""`company`, `project:<id>` or `user:<id>`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['PsetValue',
                       'PsetValuesSetPayload',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    value: Any = Field(default=..., description="""The new value as JSON; `null` for a reset.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['EnrichmentProposedPayload',
                       'SettingChangeRow',
                       'EnrichmentValue']} })
    reset: bool = Field(default=False, json_schema_extra = { "linkml_meta": {'domain_of': ['SettingChangedPayload', 'SettingChangeRow'],
         'ifabsent': 'false'} })
    old_value: Any = Field(default=..., description="""The value the layer held before, as JSON.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['SettingChangedPayload', 'SettingChangeRow']} })
    old_set: bool = Field(default=False, json_schema_extra = { "linkml_meta": {'domain_of': ['SettingChangedPayload', 'SettingChangeRow'],
         'ifabsent': 'false'} })
    reason: Optional[str] = Field(default=None, description="""Why the change was made.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })
    actor: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'EventCard',
                       'FeedItemRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'OutboxEvent',
                       'AuthAudit']} })
    source: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'SettingChangeRow',
                       'CloudEvent',
                       'OutboxEvent']} })
    accept_risk: bool = Field(default=False, json_schema_extra = { "linkml_meta": {'domain_of': ['SettingChangedPayload', 'SettingChangeRow'],
         'ifabsent': 'false'} })
    applies_at: Optional[datetime ] = Field(default=None, description="""Set only for a change that was scheduled for later.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingChangedPayload', 'SettingChangeRow']} })
    effective_us: int = Field(default=..., description="""Microseconds since the epoch at which the change takes effect (`applies_at`, else the time it was recorded).""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingChangeRow']} })
    recorded_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'SettingChangeRow', 'SettingLockRow', 'OutboxEvent']} })
    seq: int = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['Event',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'ActionInvocation',
                       'InboundEndpointVersion',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'WebhookDelivery',
                       'RuleFiring']} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the setting stream after this event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })


class SettingLockRow(ConfiguredBaseModel):
    """
    The lock and bounds of one key, as the latest `Setting.Locked` event left them.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_setting_lock'}},
         'from_schema': 'https://example.org/throughline/core/settings'})

    key: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'RuleCreatedPayload',
                       'SettingDefinition',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'EventOrigin',
                       'EventLinkRef',
                       'Rule']} })
    locked: bool = Field(default=False, json_schema_extra = { "linkml_meta": {'domain_of': ['SettingLockedPayload', 'SettingLockRow'], 'ifabsent': 'false'} })
    bounds: Optional[Any] = Field(default=None, description="""The bounds as JSON, or null for none.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['SettingLockedPayload', 'SettingLockRow']} })
    reason: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })
    actor: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'EventCard',
                       'FeedItemRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'OutboxEvent',
                       'AuthAudit']} })
    seq: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'ActionInvocation',
                       'InboundEndpointVersion',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'WebhookDelivery',
                       'RuleFiring']} })
    version: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    recorded_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'SettingChangeRow', 'SettingLockRow', 'OutboxEvent']} })


class SettingEffectApplied(ConfiguredBaseModel):
    """
    Operational, not a projection (no event produces it and a rebuild never clears it): the last point at which each follow-up effect (`reindex`, `rebuild`, `restart`) was carried out. A key whose effect is not `live` owes that effect while it has a change newer than this point. `tl projections rebuild` and the server start write it.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table',
                                      'value': 'setting_effect_applied'}},
         'from_schema': 'https://example.org/throughline/core/settings'})

    effect: str = Field(default=..., description="""`reindex`, `rebuild` or `restart`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingDefinition', 'SettingEffectApplied']} })
    applied_seq: int = Field(default=..., description="""The ledger head when the effect was carried out.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingEffectApplied']} })
    applied_us: int = Field(default=..., description="""Microseconds since the epoch when it was carried out.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingEffectApplied']} })
    applied_by: str = Field(default=..., description="""What did it (`rebuild`, `reindex`, `server`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['SettingEffectApplied']} })


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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    record_id: str = Field(default=..., description="""The record the file is attached to.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['PsetValue',
                       'LinkCount',
                       'WorkflowState',
                       'NumberingAllocatedPayload',
                       'FileUploadedPayload',
                       'FeedTag',
                       'Hashtag',
                       'File',
                       'ActionInvocationTarget',
                       'RecordBody',
                       'BodyQuarantine']} })
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
                       'ActionInvocation',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account'],
         'ifabsent': 'string(quarantined)'} })
    deduplicated: bool = Field(default=False, description="""True when the object already existed in the store at upload time.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FileUploadedPayload', 'File'], 'ifabsent': 'false'} })
    superseded_by: Optional[str] = Field(default=None, description="""The file that replaced this one in a cardinality-one slot; null while it is current.""", json_schema_extra = { "linkml_meta": {'domain_of': ['File']} })
    report: Optional[Any] = Field(default=None, description="""Scan or processing report of the last `File.Processed` or `File.Rejected`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['FileProcessedPayload',
                       'FileRejectedPayload',
                       'File',
                       'TypeRegistrationQuarantinedPayload',
                       'TypeRegistrationRow']} })
    reason: Optional[str] = Field(default=None, description="""Why the file was rejected.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })
    uploaded_by: str = Field(default=..., description="""Actor of the `File.Uploaded` event; the only reader while the file is quarantined.""", json_schema_extra = { "linkml_meta": {'domain_of': ['File']} })
    uploaded_at: datetime  = Field(default=..., description="""Time of the `File.Uploaded` event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['File']} })
    processed_at: Optional[datetime ] = Field(default=None, description="""Time of the `File.Processed` or `File.Rejected` event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['File']} })
    updated_at: datetime  = Field(default=..., description="""Time of the last applied event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AuthCredential']} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })


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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    name: str = Field(default=..., description="""Short label for lists and logs.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookCursor',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RuleCursor',
                       'EnrichmentCursor']} })
    owner: str = Field(default=..., description="""Actor who owns the subscription and is notified of auto-disable.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'SettingDefinition',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    integration_app: Optional[str] = Field(default=None, description="""The integration app the subscription belongs to, when there is one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'ActionDefinition',
                       'Rule',
                       'Enricher']} })
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
                       'ActionInvocation',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account'],
         'ifabsent': 'string(active)'} })
    disabled_reason: Optional[DisabledReason] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscription']} })
    active_windows: Any = Field(default=..., description="""JSON list of `{\"from\": seq, \"until\": seq or null}`. An event is delivered when `from < seq <= until` for some window (`until` null is open). Creation and every enable open a window; a disable closes the open one. Events committed while disabled are not delivered unless replayed.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['WebhookSubscription']} })
    expires_at: Optional[datetime ] = Field(default=None, description="""After this time the subscription no longer receives events.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookSecret',
                       'AgentToken',
                       'AuthSession',
                       'AgentTokenIssuedPayload',
                       'IntegrationSecret']} })
    current_secret_id: Optional[str] = Field(default=None, description="""The newest signing secret (the value lives in `wh_secret`, never here).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscription', 'InboundEndpoint']} })
    created_by: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'Account']} })
    created_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookDelivery',
                       'WebhookSecret',
                       'Account',
                       'AuthSession',
                       'AuthTokenSecret',
                       'IntegrationSecret']} })
    updated_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AuthCredential']} })
    version: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    last_seq: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })


class EventOrigin(ConfiguredBaseModel):
    """
    Pointer to the originating record at the version of the event (brief 18.3, `RecordRef`).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/integration'})

    id: str = Field(default=..., description="""`urn:tl:<ulid>` of the record.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'EventOrigin', 'EventLinkRef', 'CloudEvent']} })
    key: Optional[str] = Field(default=None, description="""Human-readable key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'RuleCreatedPayload',
                       'SettingDefinition',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'EventOrigin',
                       'EventLinkRef',
                       'Rule']} })
    type: Optional[str] = Field(default=None, description="""Record type.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'SettingDefinition',
                       'EventOrigin',
                       'EventLinkRef',
                       'CloudEvent']} })
    uri: str = Field(default=..., description="""Resolvable URI of the record at this version (`...@v7`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventOrigin', 'EventLinkRef', 'RecordBody', 'BodyQuarantine']} })
    version: int = Field(default=..., description="""Version of the record after the event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    api: Optional[str] = Field(default=None, description="""API URL of the record.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventOrigin']} })


class EventLinkRef(ConfiguredBaseModel):
    """
    One immediate link of the origin record (delta mode).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/integration'})

    rel: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['EventLinkRef']} })
    id: Optional[str] = Field(default=None, description="""`urn:tl:<ulid>` of the record at the other end.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'EventOrigin', 'EventLinkRef', 'CloudEvent']} })
    type: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'SettingDefinition',
                       'EventOrigin',
                       'EventLinkRef',
                       'CloudEvent']} })
    key: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'RuleCreatedPayload',
                       'SettingDefinition',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'EventOrigin',
                       'EventLinkRef',
                       'Rule']} })
    uri: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['EventOrigin', 'EventLinkRef', 'RecordBody', 'BodyQuarantine']} })


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
                       'IntegrationAppRevisedPayload',
                       'CloudEventData']} })
    links: Optional[list[EventLinkRef]] = Field(default=None, description="""Delta and full modes. Immediate links.""", json_schema_extra = { "linkml_meta": {'domain_of': ['CloudEventData']} })
    detail: Optional[Any] = Field(default=None, description="""Delta and full modes. The ledger event payload, described per event type in the catalog.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['WebhookSubscriptionDisabledPayload',
                       'CloudEventData',
                       'AuthAudit']} })
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
                       'SettingChangeRow',
                       'CloudEvent',
                       'OutboxEvent']} })
    type: str = Field(default=..., description="""`tl.<module>.<Class>.<Verb>.v<schema version>`, for example `tl.core.Record.Created.v1`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'SettingDefinition',
                       'EventOrigin',
                       'EventLinkRef',
                       'CloudEvent']} })
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


class IntegrationApp(ConfiguredBaseModel):
    """
    A named external system or internal integration (brief 19.2). Its `enabled` switch turns its inbound endpoints, rules, actions and enrichers off together. The name is unique in the ledger: it is the first segment of an inbound path (`/in/{app}/{endpoint}`).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table',
                                      'value': 'cur_integration_app'}},
         'from_schema': 'https://example.org/throughline/core/integration',
         'unique_keys': {'integration_app_name': {'unique_key_name': 'integration_app_name',
                                                  'unique_key_slots': ['name']}}})

    app_id: str = Field(default=..., description="""Immutable id; equals the ledger `stream_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload', 'IntegrationApp']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    name: str = Field(default=..., description="""A slug, unique across the ledger.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookCursor',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RuleCursor',
                       'EnrichmentCursor']} })
    label: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'IntegrationApp',
                       'ActionDefinition',
                       'AgentToken',
                       'AgentTokenIssuedPayload']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'SettingDefinition',
                       'IntegrationApp',
                       'ActionDefinition']} })
    owner: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'SettingDefinition',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    enabled: bool = Field(default=True, json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher'],
         'ifabsent': 'true'} })
    created_by: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'Account']} })
    created_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookDelivery',
                       'WebhookSecret',
                       'Account',
                       'AuthSession',
                       'AuthTokenSecret',
                       'IntegrationSecret']} })
    updated_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AuthCredential']} })
    version: int = Field(default=..., description="""Ledger stream version after the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    last_seq: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })


class ActionDefinition(ConfiguredBaseModel):
    """
    An operation people, rules and agents may ask for (brief 18.7, 19.2). One row per definition in its current version; `ReviseAction` bumps `version`, and an invocation names the version it ran. The webhook signing secret lives in `int_secret`; `secret_id` names it.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table',
                                      'value': 'cur_action_definition'}},
         'from_schema': 'https://example.org/throughline/core/integration',
         'unique_keys': {'action_definition_name': {'unique_key_name': 'action_definition_name',
                                                    'unique_key_slots': ['name']}}})

    definition_id: str = Field(default=..., description="""Immutable id; equals the ledger `stream_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'ActionRequestedPayload',
                       'ActionDefinition',
                       'ActionInvocation']} })
    name: str = Field(default=..., description="""A slug, unique across the ledger.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookCursor',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RuleCursor',
                       'EnrichmentCursor']} })
    label: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'IntegrationApp',
                       'ActionDefinition',
                       'AgentToken',
                       'AgentTokenIssuedPayload']} })
    description: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'SettingDefinition',
                       'IntegrationApp',
                       'ActionDefinition']} })
    scope: str = Field(default=..., description="""`company` actions may be invoked on any project's records; a project action only on its own.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    version: int = Field(default=..., description="""Definition version (1, 2, ...). The ledger stream version is `stream_version`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    applies_to: Any = Field(default=..., description="""`ActionTarget` as JSON: record type globs and an optional query-language condition.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionDefinitionDefinedPayload', 'ActionDefinition']} })
    parameters: Any = Field(default=..., description="""A JSON list of `ActionParameter`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionDefinitionDefinedPayload',
                       'ActionRequestedPayload',
                       'ActionDefinition',
                       'ActionInvocation']} })
    executor: ExecutorKind = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload', 'ActionDefinition']} })
    executor_config: Any = Field(default=..., description="""`JobExecutorConfig` or `WebhookExecutorConfig` as JSON. Never holds a secret.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionDefinitionDefinedPayload', 'ActionDefinition']} })
    side_effect_class: SideEffectClass = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload', 'ActionDefinition']} })
    requires_approval: bool = Field(default=False, json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload', 'ActionDefinition'],
         'ifabsent': 'false'} })
    access: AccessLevel = Field(default=AccessLevel("user"), json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher'],
         'ifabsent': 'string(user)'} })
    result_handling: Any = Field(default=..., description="""A JSON list of `store` and `post_to_feed`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionDefinitionDefinedPayload', 'ActionDefinition']} })
    owner: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'SettingDefinition',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    enabled: bool = Field(default=True, json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher'],
         'ifabsent': 'true'} })
    retired: bool = Field(default=False, description="""A retired definition cannot be invoked; its invocations stay readable.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinition'], 'ifabsent': 'false'} })
    integration_app: Optional[str] = Field(default=None, description="""The integration app this action belongs to, when there is one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'ActionDefinition',
                       'Rule',
                       'Enricher']} })
    secret_id: Optional[str] = Field(default=None, description="""The newest signing secret of a webhook action (the value lives in `int_secret`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscriptionSecretRotatedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'ActionDefinition',
                       'WebhookSecret',
                       'IntegrationSecret']} })
    created_by: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'Account']} })
    created_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookDelivery',
                       'WebhookSecret',
                       'Account',
                       'AuthSession',
                       'AuthTokenSecret',
                       'IntegrationSecret']} })
    updated_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AuthCredential']} })
    stream_version: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'OutboxEvent']} })
    last_seq: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })


class ActionInvocation(ConfiguredBaseModel):
    """
    One request to run an action (brief 18.7): Requested, then Running, then Completed or Failed. The targets are `RecordRef`s. `result` is bounded JSON; a larger one fails the invocation, it is never cut.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:ix_action_seq': {'tag': 'tl:ix_action_seq',
                                              'value': 'action, seq desc'},
                         'tl:table': {'tag': 'tl:table',
                                      'value': 'cur_action_invocation'}},
         'from_schema': 'https://example.org/throughline/core/integration'})

    invocation_id: str = Field(default=..., description="""Immutable id; equals the ledger `stream_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload',
                       'ActionRunningPayload',
                       'ActionCompletedPayload',
                       'ActionFailedPayload',
                       'ActionInvocation',
                       'ActionInvocationTarget']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    action: str = Field(default=..., description="""The definition's name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload', 'ActionInvocation']} })
    action_version: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload', 'ActionInvocation']} })
    definition_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'ActionRequestedPayload',
                       'ActionDefinition',
                       'ActionInvocation']} })
    status: InvocationStatus = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'ActionInvocation',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    targets: Any = Field(default=..., description="""A JSON list of `RecordRef`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionRequestedPayload', 'ActionInvocation']} })
    parameters: Any = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionDefinitionDefinedPayload',
                       'ActionRequestedPayload',
                       'ActionDefinition',
                       'ActionInvocation']} })
    invoked_by: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload', 'ActionInvocation']} })
    attempt: int = Field(default=0, json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRunningPayload',
                       'ActionCompletedPayload',
                       'ActionFailedPayload',
                       'ActionInvocation',
                       'WebhookAttempt',
                       'JobQueue'],
         'ifabsent': 'int(0)'} })
    requested_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActionInvocation']} })
    started_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ActionInvocation', 'WebhookAttempt', 'JobQueue']} })
    finished_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ActionInvocation', 'JobQueue', 'InboundDelivery']} })
    result: Optional[Any] = Field(default=None, description="""The executor's bounded JSON result of a completed invocation.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionCompletedPayload', 'ActionInvocation']} })
    http_status: Optional[int] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ActionCompletedPayload',
                       'ActionFailedPayload',
                       'ActionInvocation']} })
    problems: Optional[Any] = Field(default=None, description="""A JSON list of `Problem` of a failed invocation.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionFailedPayload', 'RuleBlockedPayload', 'ActionInvocation']} })
    proposal_id: Optional[str] = Field(default=None, description="""Set when the action requires approval and this invocation came from an accepted proposal.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRequestedPayload',
                       'ProposalCreatedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'ProposalRow',
                       'ActionInvocation']} })
    seq: int = Field(default=..., description="""`seq` of `Action.Requested`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'ActionInvocation',
                       'InboundEndpointVersion',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'WebhookDelivery',
                       'RuleFiring']} })
    version: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    last_seq: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })


class ActionInvocationTarget(ConfiguredBaseModel):
    """
    One record an invocation acts on, for \"what was run on this record\" (the record page).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:ix_record': {'tag': 'tl:ix_record',
                                          'value': 'record_id, invocation_id'},
                         'tl:table': {'tag': 'tl:table',
                                      'value': 'cur_action_invocation_target'}},
         'from_schema': 'https://example.org/throughline/core/integration',
         'unique_keys': {'action_target_pair': {'unique_key_name': 'action_target_pair',
                                                'unique_key_slots': ['invocation_id',
                                                                     'record_id']}}})

    target_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActionInvocationTarget', 'EnrichmentValue']} })
    invocation_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['ActionRequestedPayload',
                       'ActionRunningPayload',
                       'ActionCompletedPayload',
                       'ActionFailedPayload',
                       'ActionInvocation',
                       'ActionInvocationTarget']} })
    record_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue',
                       'LinkCount',
                       'WorkflowState',
                       'NumberingAllocatedPayload',
                       'FileUploadedPayload',
                       'FeedTag',
                       'Hashtag',
                       'File',
                       'ActionInvocationTarget',
                       'RecordBody',
                       'BodyQuarantine']} })
    record_key: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ActionInvocationTarget']} })
    record_type: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'ActionInvocationTarget']} })
    record_version: Optional[int] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ActionInvocationTarget']} })


class Rule(ConfiguredBaseModel):
    """
    A when/if/then rule (brief 18.8): `when` is a `SubscriptionFilter`, `condition` a query-language expression on the subject record, `then` a list of `RuleStep`. It acts or proposes as the service actor `svc:rule-<slug>`, declared `access`. Every revision is a new `version`; a rule starts disabled and in `propose` mode.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_rule'}},
         'from_schema': 'https://example.org/throughline/core/integration',
         'unique_keys': {'rule_key': {'unique_key_name': 'rule_key',
                                      'unique_key_slots': ['key']}}})

    rule_id: str = Field(default=..., description="""Immutable id; equals the ledger `stream_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'RuleBlockedPayload',
                       'Rule',
                       'RuleFiring']} })
    key: str = Field(default=..., description="""A slug, unique across the ledger; it appears in the `source` of what the rule does.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'RuleCreatedPayload',
                       'SettingDefinition',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'EventOrigin',
                       'EventLinkRef',
                       'Rule']} })
    title: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'RuleCreatedPayload',
                       'Rule']} })
    scope: str = Field(default=..., description="""A rule sees the events of its scope; `company` sees every project.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    version: int = Field(default=..., description="""Rule version (1, 2, ...). The ledger stream version is `stream_version`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    when: Any = Field(default=..., description="""A `SubscriptionFilter` as JSON.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RuleCreatedPayload',
                       'EnricherRegisteredPayload',
                       'Rule',
                       'Enricher']} })
    condition: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['RuleCreatedPayload', 'Rule']} })
    then: Any = Field(default=..., description="""A JSON list of `RuleStep`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RuleCreatedPayload', 'Rule']} })
    mode: RuleMode = Field(default=RuleMode("propose"), json_schema_extra = { "linkml_meta": {'domain_of': ['RuleCreatedPayload', 'Rule'], 'ifabsent': 'string(propose)'} })
    service_actor: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher']} })
    access: AutomationAccess = Field(default=AutomationAccess("user"), json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher'],
         'ifabsent': 'string(user)'} })
    owner: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'SettingDefinition',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    enabled: bool = Field(default=False, json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher'],
         'ifabsent': 'false'} })
    enabled_from_seq: int = Field(default=0, description="""The `seq` of the event that last switched it on. A worker that is behind does not apply it to events from before that moment.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Rule', 'Enricher'], 'ifabsent': 'int(0)'} })
    integration_app: Optional[str] = Field(default=None, description="""The integration app this rule belongs to, when there is one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'ActionDefinition',
                       'Rule',
                       'Enricher']} })
    created_by: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'Account']} })
    created_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookDelivery',
                       'WebhookSecret',
                       'Account',
                       'AuthSession',
                       'AuthTokenSecret',
                       'IntegrationSecret']} })
    updated_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AuthCredential']} })
    stream_version: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'OutboxEvent']} })
    last_seq: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })


class InboundEndpoint(ConfiguredBaseModel):
    """
    `POST /in/{app}/{name}` (brief 18.5, 19.3). `mapping` is restricted JSONata; `allowed_commands` is the subset of the automation commands the endpoint may produce; it runs as `service_actor` with `access`. The signing secrets are in `int_secret`; `current_secret_id` names the newest. Every earlier version stays in `cur_inbound_endpoint_version`, because a delivery is mapped by the version it was received under.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table',
                                      'value': 'cur_inbound_endpoint'}},
         'from_schema': 'https://example.org/throughline/core/integration',
         'unique_keys': {'inbound_endpoint_path': {'unique_key_name': 'inbound_endpoint_path',
                                                   'unique_key_slots': ['app',
                                                                        'name']}}})

    endpoint_id: str = Field(default=..., description="""Immutable id; equals the ledger `stream_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'InboundReceivedPayload',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'InboundReplay',
                       'InboundDelivery',
                       'InboundCounter']} })
    app: str = Field(default=..., description="""The integration app's name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload', 'InboundEndpoint']} })
    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookCursor',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RuleCursor',
                       'EnrichmentCursor']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    version: int = Field(default=..., description="""Endpoint version (1, 2, ...). The ledger stream version is `stream_version`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    auth: InboundAuth = Field(default=InboundAuth("hmac_sha256"), json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload', 'InboundEndpoint'],
         'ifabsent': 'string(hmac_sha256)'} })
    mapping: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload', 'InboundEndpoint']} })
    mapping_language: str = Field(default="jsonata-restricted@1", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload', 'InboundEndpoint'],
         'ifabsent': 'string(jsonata-restricted@1)'} })
    external_schema: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload', 'InboundEndpoint']} })
    allowed_commands: Any = Field(default=..., description="""A JSON list of command names.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['InboundEndpointCreatedPayload', 'InboundEndpoint']} })
    service_actor: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher']} })
    access: AutomationAccess = Field(default=AutomationAccess("user"), json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher'],
         'ifabsent': 'string(user)'} })
    max_body_bytes: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload', 'InboundEndpoint']} })
    rate_per_minute: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload', 'InboundEndpoint']} })
    dry_run: bool = Field(default=True, json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload',
                       'InboundAppliedPayload',
                       'InboundEndpoint'],
         'ifabsent': 'true'} })
    enabled: bool = Field(default=False, json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher'],
         'ifabsent': 'false'} })
    current_secret_id: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscription', 'InboundEndpoint']} })
    owner: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'SettingDefinition',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    created_by: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'Account']} })
    created_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookDelivery',
                       'WebhookSecret',
                       'Account',
                       'AuthSession',
                       'AuthTokenSecret',
                       'IntegrationSecret']} })
    updated_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AuthCredential']} })
    stream_version: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'OutboxEvent']} })
    last_seq: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })


class InboundEndpointVersion(ConfiguredBaseModel):
    """
    The definition of one endpoint version, as a JSON snapshot. A delivery records the version it was received under and is mapped by that version, whatever the endpoint says now.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table',
                                      'value': 'cur_inbound_endpoint_version'}},
         'from_schema': 'https://example.org/throughline/core/integration',
         'unique_keys': {'inbound_endpoint_version_pair': {'unique_key_name': 'inbound_endpoint_version_pair',
                                                           'unique_key_slots': ['endpoint_id',
                                                                                'version']}}})

    version_id: str = Field(default=..., description="""The id of the event that made this version.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointVersion']} })
    endpoint_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'InboundReceivedPayload',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'InboundReplay',
                       'InboundDelivery',
                       'InboundCounter']} })
    version: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    definition: Any = Field(default=..., description="""The `InboundEndpoint` model as JSON (no secret).""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['ActionDefinitionRevisedPayload', 'InboundEndpointVersion']} })
    seq: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'ActionInvocation',
                       'InboundEndpointVersion',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'WebhookDelivery',
                       'RuleFiring']} })


class Enricher(ConfiguredBaseModel):
    """
    The registration of an enricher plugin (brief 18.9): which events it follows (`when`), which properties of its own `enrich.<name>` pset layer it fills and the acceptance policy of each, and the service actor and access it runs as. `code_version` is the plugin's own version. Phase 1 enrichers are deterministic (`model_ref` is null; ADR-0008 decision 8).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_enricher'}},
         'from_schema': 'https://example.org/throughline/core/integration',
         'unique_keys': {'enricher_name': {'unique_key_name': 'enricher_name',
                                           'unique_key_slots': ['name']}}})

    enricher_id: str = Field(default=..., description="""Immutable id; equals the ledger `stream_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'Enricher']} })
    name: str = Field(default=..., description="""One path segment of the `enrich.` layer; unique across the ledger.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookCursor',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RuleCursor',
                       'EnrichmentCursor']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    version: int = Field(default=..., description="""Registration version (1, 2, ...). The ledger stream version is `stream_version`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    code_version: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['EnricherRegisteredPayload', 'Enricher']} })
    model_ref: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['EnricherRegisteredPayload',
                       'EnrichmentProposedPayload',
                       'Enricher',
                       'EnrichmentValue']} })
    when: Any = Field(default=..., description="""A `SubscriptionFilter` as JSON.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RuleCreatedPayload',
                       'EnricherRegisteredPayload',
                       'Rule',
                       'Enricher']} })
    properties: Any = Field(default=..., description="""A JSON list of `{name, kind, policy, threshold}`: the properties of the layer and their acceptance policy.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['EnricherRegisteredPayload', 'Enricher']} })
    service_actor: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher']} })
    access: AutomationAccess = Field(default=AutomationAccess("user"), json_schema_extra = { "linkml_meta": {'domain_of': ['ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher'],
         'ifabsent': 'string(user)'} })
    owner: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'SettingDefinition',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    enabled: bool = Field(default=False, json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher'],
         'ifabsent': 'false'} })
    enabled_from_seq: int = Field(default=0, description="""The `seq` of the event that last switched it on. A worker that is behind does not apply it to events from before that moment.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Rule', 'Enricher'], 'ifabsent': 'int(0)'} })
    integration_app: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'ActionDefinition',
                       'Rule',
                       'Enricher']} })
    created_by: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'Account']} })
    created_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookDelivery',
                       'WebhookSecret',
                       'Account',
                       'AuthSession',
                       'AuthTokenSecret',
                       'IntegrationSecret']} })
    updated_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AuthCredential']} })
    stream_version: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'OutboxEvent']} })
    last_seq: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })


class EnrichmentValue(ConfiguredBaseModel):
    """
    A value an enricher proposed for one property of one record, with provenance (brief 18.9, 19.2). Accepting it writes only the enricher's own layer `enrich.<enricher>.<property>`; promoting it to an authoritative field is a person's own `SetPsetValues`. A `shadow` value is shown to admins and the evaluation report only.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:ix_queue': {'tag': 'tl:ix_queue',
                                         'value': 'acceptance_state, seq'},
                         'tl:ix_target': {'tag': 'tl:ix_target',
                                          'value': 'target_id, property_path'},
                         'tl:table': {'tag': 'tl:table',
                                      'value': 'cur_enrichment_value'}},
         'from_schema': 'https://example.org/throughline/core/integration'})

    value_id: str = Field(default=..., description="""Immutable id; equals the ledger `stream_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnrichmentProposedPayload',
                       'EnrichmentAcceptedPayload',
                       'EnrichmentRejectedPayload',
                       'EnrichmentValue']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    target: Any = Field(default=..., description="""The `RecordRef` of the record, as JSON.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['EnrichmentProposedPayload', 'EnrichmentValue']} })
    target_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActionInvocationTarget', 'EnrichmentValue']} })
    property_path: str = Field(default=..., description="""`enrich.<enricher>.<property>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EnrichmentProposedPayload', 'EnrichmentValue']} })
    value: Optional[Any] = Field(default=None, description="""A scalar or a list of scalars, as JSON.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['EnrichmentProposedPayload',
                       'SettingChangeRow',
                       'EnrichmentValue']} })
    enricher: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['EnricherRevisedPayload',
                       'EnrichmentProposedPayload',
                       'EnrichmentValue']} })
    enricher_version: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['EnrichmentProposedPayload', 'EnrichmentValue']} })
    confidence: float = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'EnrichmentProposedPayload',
                       'EnrichmentValue']} })
    inputs: Any = Field(default=..., description="""A JSON list of `EnrichmentInput`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['EnrichmentProposedPayload', 'EnrichmentValue']} })
    model_ref: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['EnricherRegisteredPayload',
                       'EnrichmentProposedPayload',
                       'Enricher',
                       'EnrichmentValue']} })
    produced_at: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['EnrichmentProposedPayload', 'EnrichmentValue']} })
    acceptance_state: AcceptanceState = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['EnrichmentProposedPayload', 'EnrichmentValue']} })
    decided_by: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalRow', 'EnrichmentValue']} })
    decided_at: Optional[datetime ] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ProposalRow', 'EnrichmentValue']} })
    reason: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })
    seq: int = Field(default=..., description="""`seq` of `Enrichment.Proposed`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'ActionInvocation',
                       'InboundEndpointVersion',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'WebhookDelivery',
                       'RuleFiring']} })
    version: int = Field(default=..., description="""Ledger stream version after the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    last_seq: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })


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
                       'SettingChangeRow',
                       'SettingLockRow',
                       'ActionInvocation',
                       'InboundEndpointVersion',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'WebhookDelivery',
                       'RuleFiring']} })
    event_id: str = Field(default=..., description="""Ledger event id; the CloudEvents `id` and the Standard Webhooks `webhook-id`, so receivers dedupe on it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent', 'WebhookDelivery', 'RuleFiring']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    event_type: str = Field(default=..., description="""Ledger event type, for example `Record.Created`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'EventCard', 'FeedItemRow', 'OutboxEvent']} })
    schema_version: int = Field(default=1, json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent'], 'ifabsent': 'int(1)'} })
    stream_id: str = Field(default=..., description="""The stream the event was appended to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent', 'RecordBodyStoredPayload']} })
    stream_type: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent']} })
    stream_version: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'OutboxEvent']} })
    subject_id: str = Field(default=..., description="""The record the event is about, and the delivery ordering key: the stream for record events, the `from` record for link events, the record of a file, the record of a numbering allocation. Equal to `stream_id` when the event has no other subject.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['OutboxEvent', 'WebhookDelivery']} })
    subject_type: Optional[str] = Field(default=None, description="""Record type of the subject (`core.Record`), when it is a known record.""", json_schema_extra = { "linkml_meta": {'domain_of': ['OutboxEvent']} })
    subject_key: Optional[str] = Field(default=None, description="""Human-readable key of the subject, when it has one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['OutboxEvent']} })
    subject_version: Optional[int] = Field(default=None, description="""Version of the subject record after the event (the stream version when the stream is the subject).""", json_schema_extra = { "linkml_meta": {'domain_of': ['OutboxEvent']} })
    actor: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'EventCard',
                       'FeedItemRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'OutboxEvent',
                       'AuthAudit']} })
    source: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'Link',
                       'LinkAddedPayload',
                       'LinkSuggestedPayload',
                       'SettingChangeRow',
                       'CloudEvent',
                       'OutboxEvent']} })
    recorded_at: str = Field(default=..., description="""ISO-8601 UTC time of the event (the CloudEvents `time`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'SettingChangeRow', 'SettingLockRow', 'OutboxEvent']} })
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

    delivery_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['InboundReceivedPayload',
                       'InboundAppliedPayload',
                       'InboundFailedPayload',
                       'InboundRetriedPayload',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'InboundDelivery']} })
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
                       'SettingChangeRow',
                       'SettingLockRow',
                       'ActionInvocation',
                       'InboundEndpointVersion',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'WebhookDelivery',
                       'RuleFiring']} })
    event_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent', 'WebhookDelivery', 'RuleFiring']} })
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
                       'ActionInvocation',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account'],
         'ifabsent': 'string(pending)'} })
    body: str = Field(default=..., description="""The exact JSON text that is sent (and re-sent on every retry), built once when the delivery was created.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPostedPayload',
                       'FeedEditedPayload',
                       'WebhookDelivery']} })
    attempts: int = Field(default=0, json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery', 'InboundDelivery'], 'ifabsent': 'int(0)'} })
    created_at: str = Field(default=..., description="""ISO-8601 UTC. The retry deadline counts from here.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookDelivery',
                       'WebhookSecret',
                       'Account',
                       'AuthSession',
                       'AuthTokenSecret',
                       'IntegrationSecret']} })
    next_attempt_at: str = Field(default=..., description="""ISO-8601 UTC. A pending delivery is not tried before this time.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery']} })
    lease_until: Optional[str] = Field(default=None, description="""ISO-8601 UTC while a worker holds the delivery; an expired lease can be taken over.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery', 'JobQueue']} })
    lease_owner: Optional[str] = Field(default=None, description="""Worker id that holds the lease.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery', 'JobQueue']} })
    last_status: Optional[int] = Field(default=None, description="""HTTP status of the last attempt; null for a network error or a blocked target.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery']} })
    last_error: Optional[str] = Field(default=None, description="""Short reason of the last failure (no secrets, no response bodies beyond an excerpt).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery', 'JobQueue']} })
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
         'domain_of': ['InboundReceivedPayload',
                       'InboundAppliedPayload',
                       'InboundFailedPayload',
                       'InboundRetriedPayload',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'InboundDelivery']} })
    subscription_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'WebhookSecret',
                       'WebhookHealth']} })
    attempt: int = Field(default=..., description="""1 for the first attempt of the delivery.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRunningPayload',
                       'ActionCompletedPayload',
                       'ActionFailedPayload',
                       'ActionInvocation',
                       'WebhookAttempt',
                       'JobQueue']} })
    started_at: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActionInvocation', 'WebhookAttempt', 'JobQueue']} })
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
                       'ActionInvocation',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    outcome: str = Field(default=..., description="""`delivered`, `retry`, `dead`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleBlockedPayload', 'WebhookAttempt', 'RuleFiring']} })
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
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'ActionDefinition',
                       'WebhookSecret',
                       'IntegrationSecret']} })
    subscription_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'WebhookSecret',
                       'WebhookHealth']} })
    secret: str = Field(default=..., description="""`whsec_` plus the base64 of 32 random bytes (the Standard Webhooks format).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSecret', 'IntegrationSecret']} })
    state: SecretState = Field(default=SecretState("active"), json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState',
                       'WebhookSecret',
                       'JobQueue',
                       'IntegrationSecret',
                       'InboundDelivery'],
         'ifabsent': 'string(active)'} })
    created_at: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookDelivery',
                       'WebhookSecret',
                       'Account',
                       'AuthSession',
                       'AuthTokenSecret',
                       'IntegrationSecret']} })
    expires_at: Optional[str] = Field(default=None, description="""ISO-8601 UTC. A rotated-out secret keeps signing until this time (the overlap), then retires.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookSecret',
                       'AgentToken',
                       'AuthSession',
                       'AgentTokenIssuedPayload',
                       'IntegrationSecret']} })


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
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookCursor',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RuleCursor',
                       'EnrichmentCursor']} })
    last_seq: int = Field(default=0, json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor'],
         'ifabsent': 'int(0)'} })


class ExtensionRecord(RecordEnvelope):
    """
    Base class of every extension record type. A package's `type.yaml` declares a class that is_a `ExtensionRecord`; its own slots are the body of an instance. A slot annotated `tl:index: true` is an index field (brief 31.4): it is copied into the pset named for the type, so the query language filters on it. The class annotation `tl:storage_mode` (`managed` or `object-backed`) says where the body lives.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True,
         'from_schema': 'https://example.org/throughline/core/extension'})

    id: str = Field(default=..., description="""Immutable global identifier; equals the ledger `stream_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'EventOrigin', 'EventLinkRef', 'CloudEvent']} })
    key: Optional[str] = Field(default=None, description="""Human-readable number, unique within a scope. Null until numbering assigns one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'NumberingAllocatedPayload',
                       'RuleCreatedPayload',
                       'SettingDefinition',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'EventOrigin',
                       'EventLinkRef',
                       'Rule']} })
    type: str = Field(default=..., description="""Fully qualified record type, for example `core.Record`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'SettingDefinition',
                       'EventOrigin',
                       'EventLinkRef',
                       'CloudEvent']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    title: str = Field(default=..., description="""Short human-readable title.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'RuleCreatedPayload',
                       'Rule']} })
    description: Optional[str] = Field(default=None, description="""Longer free-text description.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'RecordCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'SettingDefinition',
                       'IntegrationApp',
                       'ActionDefinition']} })
    status: Optional[str] = Field(default=None, description="""Workflow state; null when the record type has no workflow.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'ActionInvocation',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    psets: Any = Field(default=..., description="""Property-set values keyed by pset name, stored as a JSON object.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordEnvelope', 'RecordCreatedPayload']} })
    voided: bool = Field(default=False, description="""Set by `Record.Voided`. Voided rows are never deleted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope'], 'ifabsent': 'false'} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })
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
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookDelivery',
                       'WebhookSecret',
                       'Account',
                       'AuthSession',
                       'AuthTokenSecret',
                       'IntegrationSecret']} })
    updated_at: datetime  = Field(default=..., description="""Timestamp of the last applied event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AuthCredential']} })


class TypeRegistrationRegisteredPayload(EventPayload):
    """
    A type package validated and was registered. The package files stay where they are; this event holds metadata only. `content_hash` is the sha256 of the canonical bytes of the package's `type.lock`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'TypeRegistration.Registered'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"content_hash": '
                                '"4d1c0a0f9f43b3a0a0f3a6a6b9d3f0a5c8e5d9b2f1a7c3e6d4b8a2f9c1e7d0b3", '
                                '"index_fields": ["crane", "lift_date", "risk_class"], '
                                '"location_uri": '
                                '"file:///srv/types/co.acme/LiftPlan/1.0.0", "name": '
                                '"LiftPlan", "namespace": "co.acme", "owner": '
                                '"user:alice", "schema_hash": '
                                '"7a3b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b", '
                                '"status": "active", "storage_mode": "object-backed", '
                                '"type_ref": "co.acme.LiftPlan@1.0.0", "version": '
                                '"1.0.0"}'}],
         'from_schema': 'https://example.org/throughline/core/extension'})

    namespace: str = Field(default=..., description="""Namespace, dotted lower-case segments, for example `co.acme`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag',
                       'Hashtag',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    name: str = Field(default=..., description="""Type name, UpperCamelCase, for example `LiftPlan`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookCursor',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RuleCursor',
                       'EnrichmentCursor']} })
    version: str = Field(default=..., description="""Semantic version `MAJOR.MINOR.PATCH`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    type_ref: str = Field(default=..., description="""`<namespace>.<name>@<version>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRegisteredPayload',
                       'TypeRegistrationQuarantinedPayload',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow']} })
    location_uri: str = Field(default=..., description="""Where the package files are, for example `file:///srv/types/co.acme/LiftPlan/1.0.0`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRegisteredPayload',
                       'TypeRegistrationQuarantinedPayload',
                       'TypeRegistrationRow']} })
    content_hash: str = Field(default=..., description="""sha256 over the canonical bytes of `type.lock`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRegisteredPayload',
                       'TypeRegistrationQuarantinedPayload',
                       'TypeRegistrationRow']} })
    owner: str = Field(default=..., description="""Actor that registered the package.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'SettingDefinition',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    status: TypeStatus = Field(default=..., description="""`active` for this event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'ActionInvocation',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    storage_mode: StorageMode = Field(default=..., description="""`managed` or `object-backed` in v0.""", json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRegisteredPayload', 'TypeRegistrationRow']} })
    index_fields: Optional[list[str]] = Field(default=None, description="""Slots annotated `tl:index`: the query contract.""", json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRegisteredPayload', 'TypeRegistrationRow']} })
    schema_hash: str = Field(default=..., description="""Hash of the compiled class: the schema a stored body validated against.""", json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RecordBody']} })


class TypeRegistrationQuarantinedPayload(EventPayload):
    """
    A type package failed validation, or its files changed under a version that is already registered. The report lists every problem (`kind`, `path`, `detail`). A conflict never removes a registration that is already active.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'TypeRegistration.Quarantined'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"content_hash": '
                                '"4d1c0a0f9f43b3a0a0f3a6a6b9d3f0a5c8e5d9b2f1a7c3e6d4b8a2f9c1e7d0b3", '
                                '"location_uri": '
                                '"file:///srv/types/co.acme/LiftPlan/1.0.1", "report": '
                                '[{"detail": "examples/bad.json: \'risk_class\' is not '
                                'one of [\'low\', \'medium\', \'high\']", "kind": '
                                '"example", "path": "examples/bad.json"}], "type_ref": '
                                '"co.acme.LiftPlan@1.0.1"}'}],
         'from_schema': 'https://example.org/throughline/core/extension'})

    type_ref: str = Field(default=..., description="""`<namespace>.<name>@<version>`, or `invalid:<relative path>` when the path is not a package path.""", json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRegisteredPayload',
                       'TypeRegistrationQuarantinedPayload',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow']} })
    location_uri: str = Field(default=..., description="""Where the package files are.""", json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRegisteredPayload',
                       'TypeRegistrationQuarantinedPayload',
                       'TypeRegistrationRow']} })
    content_hash: str = Field(default=..., description="""sha256 over the canonical `type.lock` form of the files as found.""", json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRegisteredPayload',
                       'TypeRegistrationQuarantinedPayload',
                       'TypeRegistrationRow']} })
    report: Any = Field(default=..., description="""List of `{kind, path, detail}`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['FileProcessedPayload',
                       'FileRejectedPayload',
                       'File',
                       'TypeRegistrationQuarantinedPayload',
                       'TypeRegistrationRow']} })


class TypeRegistrationDeprecatedPayload(EventPayload):
    """
    The owner retired a version. Existing instances stay readable and editable; no new instance can be created.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'TypeRegistration.Deprecated'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"reason": "superseded by 2.0.0", "type_ref": '
                                '"co.acme.LiftPlan@1.0.0"}'}],
         'from_schema': 'https://example.org/throughline/core/extension'})

    type_ref: str = Field(default=..., description="""The deprecated version.""", json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRegisteredPayload',
                       'TypeRegistrationQuarantinedPayload',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow']} })
    reason: str = Field(default=..., description="""Why.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class RecordBodyStoredPayload(EventPayload):
    """
    The body of an object-backed record was stored as a content-addressed object. The body itself is never in the ledger. A new body is a new object (a new hash); the old one stays, and `previous_hash` chains the versions.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Record.BodyStored'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"pointer": {"hash": '
                                '"9c1f0e3a5b7d2c4f6a8b0d1e3f5a7c9b2d4f6a8c0e1b3d5f7a9c2e4b6d8f0a1c", '
                                '"schema_hash": '
                                '"7a3b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b", '
                                '"size": 412, "uri": '
                                '"records/co.acme.LiftPlan/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5/9c1f0e3a5b7d2c4f6a8b0d1e3f5a7c9b2d4f6a8c0e1b3d5f7a9c2e4b6d8f0a1c.json"}, '
                                '"previous_hash": null, "stream_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"}'}],
         'from_schema': 'https://example.org/throughline/core/extension'})

    stream_id: str = Field(default=..., description="""The record (this stream).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent', 'RecordBodyStoredPayload']} })
    pointer: Any = Field(default=..., description="""`{uri, hash, size, schema_hash}`: object key, sha256 of the stored bytes, size, schema the body validated against.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordBodyStoredPayload']} })
    previous_hash: Optional[str] = Field(default=None, description="""Hash of the body this one replaces; null for the first body.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SchemaEffectiveChangedPayload', 'RecordBodyStoredPayload']} })


class TypeRegistrationRow(ConfiguredBaseModel):
    """
    One registered type version: the current state of the stream `type:<namespace>.<Name>@<version>`. `type_name` (`co.acme.LiftPlan`) is what a record's `type` holds. An `active` or `deprecated` row whose files later changed keeps its status and shows the changed hash in `conflict_hash`, with the conflict in `report_json`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table',
                                      'value': 'cur_core_type_registration'}},
         'from_schema': 'https://example.org/throughline/core/extension'})

    type_ref: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRegisteredPayload',
                       'TypeRegistrationQuarantinedPayload',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow']} })
    type_name: str = Field(default=..., description="""`<namespace>.<name>`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['TypeRegistrationRow', 'RecordBody', 'BodyQuarantine']} })
    namespace: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag',
                       'Hashtag',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookCursor',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RuleCursor',
                       'EnrichmentCursor']} })
    version: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    pset: Optional[str] = Field(default=None, description="""Name of the pset that holds the index fields of instances.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue', 'PsetValuesSetPayload', 'TypeRegistrationRow']} })
    location_uri: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRegisteredPayload',
                       'TypeRegistrationQuarantinedPayload',
                       'TypeRegistrationRow']} })
    content_hash: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRegisteredPayload',
                       'TypeRegistrationQuarantinedPayload',
                       'TypeRegistrationRow']} })
    owner: Optional[str] = Field(default=None, description="""Actor that registered it; null for a quarantined row.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'RuleCreatedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'SettingDefinition',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow']} })
    status: TypeStatus = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'ActionInvocation',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    storage_mode: Optional[StorageMode] = Field(default=None, description="""Null for a quarantined row.""", json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRegisteredPayload', 'TypeRegistrationRow']} })
    index_fields: Optional[Any] = Field(default=None, description="""JSON list of index field names.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['TypeRegistrationRegisteredPayload', 'TypeRegistrationRow']} })
    schema_hash: Optional[str] = Field(default=None, description="""Null for a quarantined row.""", json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RecordBody']} })
    report: Optional[Any] = Field(default=None, description="""JSON list of `{kind, path, detail}`: why it was quarantined, or the conflict that was refused.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['FileProcessedPayload',
                       'FileRejectedPayload',
                       'File',
                       'TypeRegistrationQuarantinedPayload',
                       'TypeRegistrationRow']} })
    conflict_hash: Optional[str] = Field(default=None, description="""Content hash of changed files refused under this registered version.""", json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRow']} })
    reason: Optional[str] = Field(default=None, description="""Deprecation reason.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })
    first_seq: int = Field(default=..., description="""`seq` of the first event of the stream.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow', 'TypeRegistrationRow']} })
    last_seq: int = Field(default=..., description="""`seq` of the last event of the stream.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })
    version_n: int = Field(default=..., description="""Stream version after the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRow']} })
    updated_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AuthCredential']} })


class RecordBody(ConfiguredBaseModel):
    """
    The pointer to the current body of an object-backed record: one row per record, from `Record.BodyStored`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table',
                                      'value': 'cur_core_record_body'}},
         'from_schema': 'https://example.org/throughline/core/extension'})

    record_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue',
                       'LinkCount',
                       'WorkflowState',
                       'NumberingAllocatedPayload',
                       'FileUploadedPayload',
                       'FeedTag',
                       'Hashtag',
                       'File',
                       'ActionInvocationTarget',
                       'RecordBody',
                       'BodyQuarantine']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    type_name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['TypeRegistrationRow', 'RecordBody', 'BodyQuarantine']} })
    uri: str = Field(default=..., description="""Object key `records/<type>/<id>/<sha256>.json`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventOrigin', 'EventLinkRef', 'RecordBody', 'BodyQuarantine']} })
    hash: str = Field(default=..., description="""sha256 of the stored bytes.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'RecordBody']} })
    body_size: int = Field(default=..., description="""Size of the stored bytes.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordBody']} })
    schema_hash: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RecordBody']} })
    body_versions: int = Field(default=..., description="""How many bodies the record has had.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordBody']} })
    last_seq: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })
    updated_at: datetime  = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AuthCredential']} })


class BodyQuarantine(ConfiguredBaseModel):
    """
    Operational state, not a projection: a record whose stored body failed verification on read (brief 31.4). Reads of the record's body are refused until the body is stored again or `tl types quarantine recheck` verifies it. A rebuild of projections never clears it.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table',
                                      'value': 'tl_body_quarantine'}},
         'from_schema': 'https://example.org/throughline/core/extension'})

    record_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue',
                       'LinkCount',
                       'WorkflowState',
                       'NumberingAllocatedPayload',
                       'FileUploadedPayload',
                       'FeedTag',
                       'Hashtag',
                       'File',
                       'ActionInvocationTarget',
                       'RecordBody',
                       'BodyQuarantine']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    type_name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['TypeRegistrationRow', 'RecordBody', 'BodyQuarantine']} })
    uri: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['EventOrigin', 'EventLinkRef', 'RecordBody', 'BodyQuarantine']} })
    expected_hash: str = Field(default=..., description="""The hash the ledger recorded for the body.""", json_schema_extra = { "linkml_meta": {'domain_of': ['BodyQuarantine']} })
    actual_hash: Optional[str] = Field(default=None, description="""Hash of the bytes found; null when the object is missing.""", json_schema_extra = { "linkml_meta": {'domain_of': ['BodyQuarantine']} })
    reason: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })
    detected_at: datetime  = Field(default=..., description="""When the mismatch was found.""", json_schema_extra = { "linkml_meta": {'domain_of': ['BodyQuarantine']} })


class Account(ConfiguredBaseModel):
    """
    One account in its current state. A projection of the `Account.*` events.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_account'}},
         'from_schema': 'https://example.org/throughline/core/auth',
         'unique_keys': {'username': {'description': 'Usernames are unique across all '
                                                     'account kinds.',
                                      'unique_key_name': 'username',
                                      'unique_key_slots': ['username']}}})

    account_id: str = Field(default=..., description="""Immutable id; the ledger stream is `account:<account_id>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Account',
                       'AgentToken',
                       'AuthCredential',
                       'AuthSession',
                       'AuthAudit',
                       'AccountCreatedPayload',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AccountPasswordChangedPayload',
                       'AgentTokenIssuedPayload',
                       'AgentTokenRevokedPayload']} })
    username: str = Field(default=..., description="""Normalised (NFKC, lower case) and matching `[a-z0-9][a-z0-9_.@-]{0,63}`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Account', 'AccountCreatedPayload']} })
    display_name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Account', 'AccountCreatedPayload']} })
    kind: AccountKind = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag',
                       'Hashtag',
                       'Account',
                       'AccountCreatedPayload',
                       'JobQueue']} })
    roles: Any = Field(default=..., description="""JSON list of roles from `admin`, `user` and `document_controller`, for example `[\"user\", \"document_controller\"]`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['Account', 'AccountCreatedPayload', 'AccountRolesSetPayload']} })
    is_admin: int = Field(default=0, description="""1 when `roles` holds `admin`. Lets the last-admin check count in plain SQL.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['Account'],
         'ifabsent': 'int(0)'} })
    status: AccountStatus = Field(default=AccountStatus("active"), json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'LinkFlaggedPayload',
                       'FileUploadedPayload',
                       'FileProcessedPayload',
                       'FileRejectedPayload',
                       'ProposalRow',
                       'File',
                       'WebhookSubscription',
                       'ActionInvocation',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account'],
         'ifabsent': 'string(active)'} })
    created_by: str = Field(default=..., description="""Actor that created the account.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'Account']} })
    created_at: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookDelivery',
                       'WebhookSecret',
                       'Account',
                       'AuthSession',
                       'AuthTokenSecret',
                       'IntegrationSecret']} })
    updated_at: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AuthCredential']} })
    version: int = Field(default=..., description="""Version of the account stream after the last event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'NumberingCounter',
                       'SchemaPackagePublishedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionRevisedPayload',
                       'RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'EnricherRegisteredPayload',
                       'EnricherRevisedPayload',
                       'FeedItemRow',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'WebhookSubscription',
                       'EventOrigin',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'Enricher',
                       'EnrichmentValue',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'Account']} })
    last_seq: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })


class AgentToken(ConfiguredBaseModel):
    """
    The metadata of one agent token. The token itself is only in `auth_token_secret`, as a hash.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_agent_token'}},
         'from_schema': 'https://example.org/throughline/core/auth'})

    token_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['AgentToken',
                       'AuthTokenSecret',
                       'AgentTokenIssuedPayload',
                       'AgentTokenRevokedPayload']} })
    account_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['Account',
                       'AgentToken',
                       'AuthCredential',
                       'AuthSession',
                       'AuthAudit',
                       'AccountCreatedPayload',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AccountPasswordChangedPayload',
                       'AgentTokenIssuedPayload',
                       'AgentTokenRevokedPayload']} })
    label: str = Field(default=..., description="""What the token is for; shown in lists.""", json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'IntegrationApp',
                       'ActionDefinition',
                       'AgentToken',
                       'AgentTokenIssuedPayload']} })
    expires_at: Optional[str] = Field(default=None, description="""ISO-8601 UTC; null for a token that does not expire.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookSecret',
                       'AgentToken',
                       'AuthSession',
                       'AgentTokenIssuedPayload',
                       'IntegrationSecret']} })
    revoked: int = Field(default=0, json_schema_extra = { "linkml_meta": {'domain_of': ['AgentToken'], 'ifabsent': 'int(0)'} })
    revoked_at: Optional[str] = Field(default=None, description="""ISO-8601 UTC.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AgentToken']} })
    revoke_reason: Optional[str] = Field(default=None, description="""Free text, no secrets.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AgentToken']} })
    issued_by: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['AgentToken']} })
    issued_at: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['AgentToken']} })
    last_seq: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor']} })


class AuthCredential(ConfiguredBaseModel):
    """
    A password hash. Operational; never in the ledger, the archive, the lake or webhooks.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'auth_credential'}},
         'from_schema': 'https://example.org/throughline/core/auth'})

    account_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Account',
                       'AgentToken',
                       'AuthCredential',
                       'AuthSession',
                       'AuthAudit',
                       'AccountCreatedPayload',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AccountPasswordChangedPayload',
                       'AgentTokenIssuedPayload',
                       'AgentTokenRevokedPayload']} })
    password_hash: str = Field(default=..., description="""`scrypt$<log2 N>$<r>$<p>$<salt>$<hash>` (ADR-0009 section 2).""", json_schema_extra = { "linkml_meta": {'domain_of': ['AuthCredential']} })
    updated_at: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'NumberingCounter',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AuthCredential']} })


class AuthSession(ConfiguredBaseModel):
    """
    A signed-in session. Only the SHA-256 of the token is stored; ending a session deletes the row.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'auth_session'}},
         'from_schema': 'https://example.org/throughline/core/auth'})

    token_hash: str = Field(default=..., description="""Hex SHA-256 of the `tls_` token.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AuthSession', 'AuthTokenSecret']} })
    account_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['Account',
                       'AgentToken',
                       'AuthCredential',
                       'AuthSession',
                       'AuthAudit',
                       'AccountCreatedPayload',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AccountPasswordChangedPayload',
                       'AgentTokenIssuedPayload',
                       'AgentTokenRevokedPayload']} })
    created_at: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookDelivery',
                       'WebhookSecret',
                       'Account',
                       'AuthSession',
                       'AuthTokenSecret',
                       'IntegrationSecret']} })
    expires_at: str = Field(default=..., description="""ISO-8601 UTC. Sign-out, disable and a password change delete the row.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookSecret',
                       'AgentToken',
                       'AuthSession',
                       'AgentTokenIssuedPayload',
                       'IntegrationSecret']} })


class AuthTokenSecret(ConfiguredBaseModel):
    """
    The hash of one agent token. Only a `token_id` links it to the ledger metadata.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'auth_token_secret'}},
         'from_schema': 'https://example.org/throughline/core/auth'})

    token_hash: str = Field(default=..., description="""Hex SHA-256 of the `tla_` token.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AuthSession', 'AuthTokenSecret']} })
    token_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['AgentToken',
                       'AuthTokenSecret',
                       'AgentTokenIssuedPayload',
                       'AgentTokenRevokedPayload']} })
    created_at: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookDelivery',
                       'WebhookSecret',
                       'Account',
                       'AuthSession',
                       'AuthTokenSecret',
                       'IntegrationSecret']} })


class AuthAttempt(ConfiguredBaseModel):
    """
    Failed-sign-in counters, keyed by normalised username whether or not an account exists. A lock lasts 15 minutes, for every name (a longer lock for some names would tell which exist).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'auth_attempt'}},
         'from_schema': 'https://example.org/throughline/core/auth'})

    username_key: str = Field(default=..., description="""The normalised username, cut to 64 characters.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AuthAttempt', 'AuthAudit']} })
    failed_count: int = Field(default=0, json_schema_extra = { "linkml_meta": {'domain_of': ['AuthAttempt'], 'ifabsent': 'int(0)'} })
    window_started_at: str = Field(default=..., description="""ISO-8601 UTC of the first failure in the current window.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AuthAttempt']} })
    last_failed_at: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['AuthAttempt']} })
    locked_until: Optional[str] = Field(default=None, description="""ISO-8601 UTC while locked.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AuthAttempt']} })


class AuthAudit(ConfiguredBaseModel):
    """
    The operational audit of authentication: sign-in success and failure, locks, unlocks, sign-out, agent token issue and revoke, password resets. It holds no secret (never a password, hash or token) and is kept 90 days. It is not a projection and not in the ledger, the archive or the lake; `tl admin audit` lists it.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'auth_audit'}},
         'from_schema': 'https://example.org/throughline/core/auth'})

    audit_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['AuthAudit']} })
    at: str = Field(default=..., description="""ISO-8601 UTC.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['AuthAudit']} })
    event: str = Field(default=..., description="""`sign_in_ok`, `sign_in_failed`, `locked`, `unlocked`, `sign_out`, `token_issued`, `token_revoked`, `password_reset` or `bootstrap`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['AuthAudit']} })
    username_key: Optional[str] = Field(default=None, description="""The normalised username the attempt named, whether or not an account exists, or `<invalid>` when what was typed cannot be a username (it may have been a password, so it is never kept).""", json_schema_extra = { "linkml_meta": {'domain_of': ['AuthAttempt', 'AuthAudit']} })
    account_id: Optional[str] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Account',
                       'AgentToken',
                       'AuthCredential',
                       'AuthSession',
                       'AuthAudit',
                       'AccountCreatedPayload',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AccountPasswordChangedPayload',
                       'AgentTokenIssuedPayload',
                       'AgentTokenRevokedPayload']} })
    actor: Optional[str] = Field(default=None, description="""The actor that did it, when there is one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'EventCard',
                       'FeedItemRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'OutboxEvent',
                       'AuthAudit']} })
    detail: Optional[str] = Field(default=None, description="""A short reason code or id (`bad_credentials`, `disabled`, a token id, the end of a lock). Never a secret.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionDisabledPayload',
                       'CloudEventData',
                       'AuthAudit']} })
    count: int = Field(default=1, description="""How many times this happened in a row; repeated failures of one name in a lock window share one row, and `at` is the last of them.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AuthAudit', 'InboundCounter'], 'ifabsent': 'int(1)'} })


class AccountEventPayload(EventPayload):
    """
    Payload of an `Account.*` or `AgentToken.*` event. The stream is `account:<account_id>`; no payload holds a secret. These events are internal: the webhook dispatcher never delivers them and the events API shows them to admins only.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True, 'from_schema': 'https://example.org/throughline/core/auth'})

    pass


class AccountCreatedPayload(AccountEventPayload):
    """
    An account was created. A password, if any, is held outside the ledger. Internal: never delivered to webhooks.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Account.Created'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA", '
                                '"display_name": "Demo User", "kind": "person", '
                                '"roles": ["admin"], "username": "demo"}'}],
         'from_schema': 'https://example.org/throughline/core/auth'})

    account_id: str = Field(default=..., description="""Account id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Account',
                       'AgentToken',
                       'AuthCredential',
                       'AuthSession',
                       'AuthAudit',
                       'AccountCreatedPayload',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AccountPasswordChangedPayload',
                       'AgentTokenIssuedPayload',
                       'AgentTokenRevokedPayload']} })
    username: str = Field(default=..., description="""Normalised username.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Account', 'AccountCreatedPayload']} })
    display_name: str = Field(default=..., description="""Name shown in lists.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Account', 'AccountCreatedPayload']} })
    kind: AccountKind = Field(default=..., description="""person, agent or sim.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag',
                       'Hashtag',
                       'Account',
                       'AccountCreatedPayload',
                       'JobQueue']} })
    roles: Any = Field(default=..., description="""List of roles.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['Account', 'AccountCreatedPayload', 'AccountRolesSetPayload']} })


class AccountRolesSetPayload(AccountEventPayload):
    """
    The roles of an account were replaced. Internal: never delivered to webhooks.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Account.RolesSet'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA", '
                                '"reason": "promoted to run the admin module", '
                                '"roles": ["admin", "user"]}'}],
         'from_schema': 'https://example.org/throughline/core/auth'})

    account_id: str = Field(default=..., description="""Account id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Account',
                       'AgentToken',
                       'AuthCredential',
                       'AuthSession',
                       'AuthAudit',
                       'AccountCreatedPayload',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AccountPasswordChangedPayload',
                       'AgentTokenIssuedPayload',
                       'AgentTokenRevokedPayload']} })
    roles: Any = Field(default=..., description="""The new list of roles.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['Account', 'AccountCreatedPayload', 'AccountRolesSetPayload']} })
    reason: Optional[str] = Field(default=None, description="""Why the roles changed.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class AccountDisabledPayload(AccountEventPayload):
    """
    An account was disabled: it cannot sign in and its sessions and agent tokens stop working. Internal: never delivered to webhooks.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Account.Disabled'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA", '
                                '"reason": "left the project"}'}],
         'from_schema': 'https://example.org/throughline/core/auth'})

    account_id: str = Field(default=..., description="""Account id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Account',
                       'AgentToken',
                       'AuthCredential',
                       'AuthSession',
                       'AuthAudit',
                       'AccountCreatedPayload',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AccountPasswordChangedPayload',
                       'AgentTokenIssuedPayload',
                       'AgentTokenRevokedPayload']} })
    reason: Optional[str] = Field(default=None, description="""Why it was disabled.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class AccountEnabledPayload(AccountEventPayload):
    """
    A disabled account was enabled again. Internal: never delivered to webhooks.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Account.Enabled'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA", '
                                '"reason": "returned"}'}],
         'from_schema': 'https://example.org/throughline/core/auth'})

    account_id: str = Field(default=..., description="""Account id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Account',
                       'AgentToken',
                       'AuthCredential',
                       'AuthSession',
                       'AuthAudit',
                       'AccountCreatedPayload',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AccountPasswordChangedPayload',
                       'AgentTokenIssuedPayload',
                       'AgentTokenRevokedPayload']} })
    reason: Optional[str] = Field(default=None, description="""Why it was enabled.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class AccountPasswordChangedPayload(AccountEventPayload):
    """
    The password of an account was set or changed. The event records that it happened, never the password or its hash. Internal: never delivered to webhooks.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'Account.PasswordChanged'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA", "by": '
                                '"user:demo", "forced": true}'}],
         'from_schema': 'https://example.org/throughline/core/auth'})

    account_id: str = Field(default=..., description="""Account id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Account',
                       'AgentToken',
                       'AuthCredential',
                       'AuthSession',
                       'AuthAudit',
                       'AccountCreatedPayload',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AccountPasswordChangedPayload',
                       'AgentTokenIssuedPayload',
                       'AgentTokenRevokedPayload']} })
    by: str = Field(default=..., description="""Actor that changed it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundRetriedPayload',
                       'EnrichmentAcceptedPayload',
                       'EnrichmentRejectedPayload',
                       'ProposalAcceptedPayload',
                       'ProposalRejectedPayload',
                       'ProposalFailedPayload',
                       'AccountPasswordChangedPayload']} })
    forced: bool = Field(default=..., description="""True for an admin reset or a bootstrap, false for the person changing their own.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AccountPasswordChangedPayload']} })


class AgentTokenIssuedPayload(AccountEventPayload):
    """
    An agent token was issued. The event holds its metadata; the token is shown once and stored only as a hash. Internal: never delivered to webhooks.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'AgentToken.Issued'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB", '
                                '"expires_at": "2027-01-09T03:14:07.000000Z", "label": '
                                '"triage assistant", "token_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6PC"}'}],
         'from_schema': 'https://example.org/throughline/core/auth'})

    token_id: str = Field(default=..., description="""Token id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AgentToken',
                       'AuthTokenSecret',
                       'AgentTokenIssuedPayload',
                       'AgentTokenRevokedPayload']} })
    account_id: str = Field(default=..., description="""The agent account.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Account',
                       'AgentToken',
                       'AuthCredential',
                       'AuthSession',
                       'AuthAudit',
                       'AccountCreatedPayload',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AccountPasswordChangedPayload',
                       'AgentTokenIssuedPayload',
                       'AgentTokenRevokedPayload']} })
    label: str = Field(default=..., description="""What the token is for.""", json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'IntegrationApp',
                       'ActionDefinition',
                       'AgentToken',
                       'AgentTokenIssuedPayload']} })
    expires_at: Optional[str] = Field(default=None, description="""ISO-8601 time after which the token stops working; null for none.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookSecret',
                       'AgentToken',
                       'AuthSession',
                       'AgentTokenIssuedPayload',
                       'IntegrationSecret']} })


class AgentTokenRevokedPayload(AccountEventPayload):
    """
    An agent token was revoked and no longer authenticates. Internal: never delivered to webhooks.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:event_type': {'tag': 'tl:event_type',
                                           'value': 'AgentToken.Revoked'},
                         'tl:event_version': {'tag': 'tl:event_version', 'value': '1'}},
         'examples': [{'value': '{"account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB", '
                                '"reason": "rotated", "token_id": '
                                '"01J9Z6Q4W3X2Y1V0T9S8R7Q6PC"}'}],
         'from_schema': 'https://example.org/throughline/core/auth'})

    token_id: str = Field(default=..., description="""Token id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AgentToken',
                       'AuthTokenSecret',
                       'AgentTokenIssuedPayload',
                       'AgentTokenRevokedPayload']} })
    account_id: str = Field(default=..., description="""The agent account.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Account',
                       'AgentToken',
                       'AuthCredential',
                       'AuthSession',
                       'AuthAudit',
                       'AccountCreatedPayload',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AccountPasswordChangedPayload',
                       'AgentTokenIssuedPayload',
                       'AgentTokenRevokedPayload']} })
    reason: Optional[str] = Field(default=None, description="""Why it was revoked.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link',
                       'RecordVoidedPayload',
                       'RecordCorrectedPayload',
                       'LinkDeclinedPayload',
                       'LinkFlaggedPayload',
                       'LinkRetractedPayload',
                       'WorkflowTransitionedPayload',
                       'FileRejectedPayload',
                       'WebhookSubscriptionDisabledPayload',
                       'IntegrationAppRevisedPayload',
                       'IntegrationAppEnabledPayload',
                       'IntegrationAppDisabledPayload',
                       'ActionDefinitionRevisedPayload',
                       'ActionDefinitionRetiredPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'EnricherRevisedPayload',
                       'EnricherEnabledPayload',
                       'EnricherDisabledPayload',
                       'EnrichmentRejectedPayload',
                       'FeedRetractedPayload',
                       'ProposalRejectedPayload',
                       'ProposalRow',
                       'SettingChangedPayload',
                       'SettingLockedPayload',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'File',
                       'EnrichmentValue',
                       'TypeRegistrationDeprecatedPayload',
                       'TypeRegistrationRow',
                       'BodyQuarantine',
                       'AccountRolesSetPayload',
                       'AccountDisabledPayload',
                       'AccountEnabledPayload',
                       'AgentTokenRevokedPayload']} })


class JobQueue(ConfiguredBaseModel):
    """
    One queued, running or finished job. `job_id` is the id of the job record. A worker claims a row by moving it to `running` with a lease; a lease that expired makes the row claimable again (the work is retried, or failed when `attempt` has reached `max_attempts`). Completion is accepted for the claimed `attempt` only, so a late worker whose lease was taken over cannot finish a job twice.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:ix_claim': {'tag': 'tl:ix_claim',
                                         'value': 'state, run_after'},
                         'tl:ix_scope_state': {'tag': 'tl:ix_scope_state',
                                               'value': 'scope, state'},
                         'tl:table': {'tag': 'tl:table', 'value': 'job_queue'}},
         'from_schema': 'https://example.org/throughline/core/jobs'})

    job_id: str = Field(default=..., description="""The id of the job record (a ledger stream id).""", json_schema_extra = { "linkml_meta": {'domain_of': ['JobQueue']} })
    kind: str = Field(default=..., description="""The job kind a handler is registered for, for example `extract`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag',
                       'Hashtag',
                       'Account',
                       'AccountCreatedPayload',
                       'JobQueue']} })
    scope: str = Field(default=..., description="""The scope of the job record.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    state: str = Field(default=..., description="""queued, running, done, failed or cancelled.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState',
                       'WebhookSecret',
                       'JobQueue',
                       'IntegrationSecret',
                       'InboundDelivery']} })
    priority: int = Field(default=0, description="""Higher runs first among claimable jobs.""", json_schema_extra = { "linkml_meta": {'domain_of': ['JobQueue'], 'ifabsent': 'int(0)'} })
    attempt: int = Field(default=0, description="""Number of times the job has been claimed; the claim that is running now is this attempt.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionRunningPayload',
                       'ActionCompletedPayload',
                       'ActionFailedPayload',
                       'ActionInvocation',
                       'WebhookAttempt',
                       'JobQueue'],
         'ifabsent': 'int(0)'} })
    max_attempts: int = Field(default=3, description="""A job is failed for good when a claim would be attempt `max_attempts` + 1.""", json_schema_extra = { "linkml_meta": {'domain_of': ['JobQueue'], 'ifabsent': 'int(3)'} })
    run_after: str = Field(default=..., description="""ISO-8601 UTC; the job is not claimable before this moment (a retry waits here).""", json_schema_extra = { "linkml_meta": {'domain_of': ['JobQueue']} })
    lease_owner: Optional[str] = Field(default=None, description="""The worker that holds the claim; null when not running.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery', 'JobQueue']} })
    lease_until: Optional[str] = Field(default=None, description="""ISO-8601 UTC; the claim of a running job expires here.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery', 'JobQueue']} })
    enqueued_at: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['JobQueue']} })
    started_at: Optional[str] = Field(default=None, description="""ISO-8601 UTC of the latest claim.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionInvocation', 'WebhookAttempt', 'JobQueue']} })
    finished_at: Optional[str] = Field(default=None, description="""ISO-8601 UTC when the job reached done, failed or cancelled.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionInvocation', 'JobQueue', 'InboundDelivery']} })
    last_error: Optional[str] = Field(default=None, description="""The latest failure, cut to 500 characters; never a stack trace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery', 'JobQueue']} })


class IntegrationSecret(ConfiguredBaseModel):
    """
    A signing secret of an inbound endpoint or a webhook action. Secrets never enter the ledger or the logs.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:ix_owner': {'tag': 'tl:ix_owner',
                                         'value': 'owner_kind, owner_id, state'},
                         'tl:table': {'tag': 'tl:table', 'value': 'int_secret'}},
         'from_schema': 'https://example.org/throughline/core/integration_ops'})

    secret_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscriptionSecretRotatedPayload',
                       'ActionDefinitionDefinedPayload',
                       'ActionDefinitionSecretRotatedPayload',
                       'InboundEndpointCreatedPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'ActionDefinition',
                       'WebhookSecret',
                       'IntegrationSecret']} })
    owner_kind: SecretOwnerKind = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationSecret']} })
    owner_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['IntegrationSecret']} })
    secret: str = Field(default=..., description="""`whsec_` plus the base64 of 32 random bytes (the Standard Webhooks format).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSecret', 'IntegrationSecret']} })
    state: SecretState = Field(default=SecretState("active"), json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState',
                       'WebhookSecret',
                       'JobQueue',
                       'IntegrationSecret',
                       'InboundDelivery'],
         'ifabsent': 'string(active)'} })
    created_at: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Link',
                       'ProposalRow',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookDelivery',
                       'WebhookSecret',
                       'Account',
                       'AuthSession',
                       'AuthTokenSecret',
                       'IntegrationSecret']} })
    expires_at: Optional[str] = Field(default=None, description="""ISO-8601 UTC. A rotated-out secret keeps verifying until this time (at most 24 hours), then retires.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'WebhookSubscription',
                       'WebhookSecret',
                       'AgentToken',
                       'AuthSession',
                       'AgentTokenIssuedPayload',
                       'IntegrationSecret']} })


class InboundReplay(ConfiguredBaseModel):
    """
    A webhook id or JWT id already seen by an endpoint inside the replay window.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:ix_seen': {'tag': 'tl:ix_seen', 'value': 'seen_at'},
                         'tl:table': {'tag': 'tl:table', 'value': 'int_replay'}},
         'from_schema': 'https://example.org/throughline/core/integration_ops'})

    replay_id: str = Field(default=..., description="""`<endpoint id>:<webhook-id or jti>`; the primary key makes a second use fail.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundReplay']} })
    endpoint_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'InboundReceivedPayload',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'InboundReplay',
                       'InboundDelivery',
                       'InboundCounter']} })
    seen_at: str = Field(default=..., description="""ISO-8601 UTC; rows older than the retention are pruned.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundReplay']} })


class InboundDelivery(ConfiguredBaseModel):
    """
    One accepted inbound POST and what became of it. The raw body is an object, never a column.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:ix_endpoint_state': {'tag': 'tl:ix_endpoint_state',
                                                  'value': 'endpoint_id, state'},
                         'tl:ix_received': {'tag': 'tl:ix_received',
                                            'value': 'received_at'},
                         'tl:table': {'tag': 'tl:table', 'value': 'int_delivery'}},
         'from_schema': 'https://example.org/throughline/core/integration_ops'})

    delivery_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['InboundReceivedPayload',
                       'InboundAppliedPayload',
                       'InboundFailedPayload',
                       'InboundRetriedPayload',
                       'WebhookDelivery',
                       'WebhookAttempt',
                       'InboundDelivery']} })
    endpoint_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'InboundReceivedPayload',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'InboundReplay',
                       'InboundDelivery',
                       'InboundCounter']} })
    endpoint_version: int = Field(default=..., description="""The endpoint version the delivery is mapped by.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundReceivedPayload', 'InboundDelivery']} })
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
                       'SettingChangeRow',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'RecordBody',
                       'BodyQuarantine',
                       'JobQueue',
                       'InboundDelivery']} })
    state: DeliveryState = Field(default=DeliveryState("queued"), json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState',
                       'WebhookSecret',
                       'JobQueue',
                       'IntegrationSecret',
                       'InboundDelivery'],
         'ifabsent': 'string(queued)'} })
    object_key: str = Field(default=..., description="""`inbound/<endpoint id>/<delivery id>`; the raw body.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundDelivery']} })
    payload_sha256: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['InboundReceivedPayload', 'InboundDelivery']} })
    payload_size: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['InboundReceivedPayload', 'InboundDelivery']} })
    corrected_object_key: Optional[str] = Field(default=None, description="""The corrected payload an admin supplied on a retry, as a new object.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundDelivery']} })
    received_at: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['InboundDelivery']} })
    finished_at: Optional[str] = Field(default=None, description="""ISO-8601 UTC of the last attempt.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActionInvocation', 'JobQueue', 'InboundDelivery']} })
    attempts: int = Field(default=0, json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookDelivery', 'InboundDelivery'], 'ifabsent': 'int(0)'} })
    error_code: Optional[str] = Field(default=None, description="""A fixed code (`mapping_error`, `key_not_found`, `command_refused`, ...).""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundDelivery']} })
    error_message: Optional[str] = Field(default=None, description="""A bounded message for a person; never a payload excerpt.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundDelivery']} })
    command_count: Optional[int] = Field(default=None, description="""How many commands ran (or were planned, for a dry run).""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundAppliedPayload', 'InboundDelivery', 'RuleFiring']} })


class InboundCounter(ConfiguredBaseModel):
    """
    Per-endpoint counters of accepted deliveries and of refusals by fixed code (never a header, a claim or a body).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'int_counter'}},
         'from_schema': 'https://example.org/throughline/core/integration_ops'})

    counter_id: str = Field(default=..., description="""`<endpoint id>:<code>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter', 'InboundCounter']} })
    endpoint_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['InboundEndpointCreatedPayload',
                       'InboundEndpointRevisedPayload',
                       'InboundEndpointEnabledPayload',
                       'InboundEndpointDisabledPayload',
                       'InboundEndpointSecretRotatedPayload',
                       'InboundReceivedPayload',
                       'InboundEndpoint',
                       'InboundEndpointVersion',
                       'InboundReplay',
                       'InboundDelivery',
                       'InboundCounter']} })
    code: str = Field(default=..., description="""`accepted`, `bad_signature`, `replay`, `too_large`, `rate_limited`, `invalid_payload`, ...""", json_schema_extra = { "linkml_meta": {'domain_of': ['InboundFailedPayload', 'InboundCounter']} })
    count: int = Field(default=0, json_schema_extra = { "linkml_meta": {'domain_of': ['AuthAudit', 'InboundCounter'], 'ifabsent': 'int(0)'} })
    last_at: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['InboundCounter']} })


class RuleCursor(ConfiguredBaseModel):
    """
    How far the rules worker has read the ledger.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'rule_cursor'}},
         'from_schema': 'https://example.org/throughline/core/integration_ops'})

    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookCursor',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RuleCursor',
                       'EnrichmentCursor']} })
    last_seq: int = Field(default=0, json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor'],
         'ifabsent': 'int(0)'} })


class RuleFiring(ConfiguredBaseModel):
    """
    One rule's outcome for one event, written in the unit of work that runs its commands: the exactly-once effect of a rule. `killed` rows record events passed over while the kill switch was on.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:ix_event': {'tag': 'tl:ix_event', 'value': 'event_id'},
                         'tl:ix_rule_seq': {'tag': 'tl:ix_rule_seq',
                                            'value': 'rule_id, seq desc'},
                         'tl:table': {'tag': 'tl:table', 'value': 'rule_firing'}},
         'from_schema': 'https://example.org/throughline/core/integration_ops'})

    firing_id: str = Field(default=..., description="""`<rule id>:<rule version>:<event id>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleFiring']} })
    rule_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RuleCreatedPayload',
                       'RuleRevisedPayload',
                       'RuleEnabledPayload',
                       'RuleDisabledPayload',
                       'RuleBlockedPayload',
                       'Rule',
                       'RuleFiring']} })
    rule_version: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RuleBlockedPayload', 'RuleFiring']} })
    event_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'OutboxEvent', 'WebhookDelivery', 'RuleFiring']} })
    seq: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Event',
                       'FeedItemRow',
                       'Hashtag',
                       'ProposalRow',
                       'SettingChangeRow',
                       'SettingLockRow',
                       'ActionInvocation',
                       'InboundEndpointVersion',
                       'EnrichmentValue',
                       'OutboxEvent',
                       'WebhookDelivery',
                       'RuleFiring']} })
    depth: int = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RuleBlockedPayload', 'RuleFiring']} })
    outcome: str = Field(default=..., description="""`fired`, `proposed`, `skipped_condition`, `refused`, `depth_limit`, `budget` or `killed`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RuleBlockedPayload', 'WebhookAttempt', 'RuleFiring']} })
    command_count: int = Field(default=0, json_schema_extra = { "linkml_meta": {'domain_of': ['InboundAppliedPayload', 'InboundDelivery', 'RuleFiring'],
         'ifabsent': 'int(0)'} })
    fired_at: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RuleFiring']} })


class EnrichmentCursor(ConfiguredBaseModel):
    """
    How far an enrichment dispatcher has read the ledger.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'enrich_cursor'}},
         'from_schema': 'https://example.org/throughline/core/integration_ops'})

    name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['WebhookSubscriptionCreatedPayload',
                       'IntegrationAppRegisteredPayload',
                       'ActionDefinitionDefinedPayload',
                       'InboundEndpointCreatedPayload',
                       'EnricherRegisteredPayload',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'InboundEndpoint',
                       'Enricher',
                       'WebhookCursor',
                       'TypeRegistrationRegisteredPayload',
                       'TypeRegistrationRow',
                       'RuleCursor',
                       'EnrichmentCursor']} })
    last_seq: int = Field(default=0, json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'File',
                       'WebhookSubscription',
                       'IntegrationApp',
                       'ActionDefinition',
                       'ActionInvocation',
                       'Rule',
                       'InboundEndpoint',
                       'Enricher',
                       'EnrichmentValue',
                       'WebhookCursor',
                       'TypeRegistrationRow',
                       'RecordBody',
                       'Account',
                       'AgentToken',
                       'RuleCursor',
                       'EnrichmentCursor'],
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
IntegrationAppEventPayload.model_rebuild()
ActionDefinitionEventPayload.model_rebuild()
ActionInvocationEventPayload.model_rebuild()
RuleEventPayload.model_rebuild()
InboundEndpointEventPayload.model_rebuild()
InboundDeliveryEventPayload.model_rebuild()
EnricherEventPayload.model_rebuild()
EnrichmentEventPayload.model_rebuild()
IntegrationAppRegisteredPayload.model_rebuild()
IntegrationAppRevisedPayload.model_rebuild()
IntegrationAppEnabledPayload.model_rebuild()
IntegrationAppDisabledPayload.model_rebuild()
ActionDefinitionDefinedPayload.model_rebuild()
ActionDefinitionRevisedPayload.model_rebuild()
ActionDefinitionRetiredPayload.model_rebuild()
ActionDefinitionSecretRotatedPayload.model_rebuild()
ActionRequestedPayload.model_rebuild()
ActionRunningPayload.model_rebuild()
ActionCompletedPayload.model_rebuild()
ActionFailedPayload.model_rebuild()
RuleCreatedPayload.model_rebuild()
RuleRevisedPayload.model_rebuild()
RuleEnabledPayload.model_rebuild()
RuleDisabledPayload.model_rebuild()
RuleBlockedPayload.model_rebuild()
InboundEndpointCreatedPayload.model_rebuild()
InboundEndpointRevisedPayload.model_rebuild()
InboundEndpointEnabledPayload.model_rebuild()
InboundEndpointDisabledPayload.model_rebuild()
InboundEndpointSecretRotatedPayload.model_rebuild()
InboundReceivedPayload.model_rebuild()
InboundAppliedPayload.model_rebuild()
InboundFailedPayload.model_rebuild()
InboundRetriedPayload.model_rebuild()
EnricherRegisteredPayload.model_rebuild()
EnricherRevisedPayload.model_rebuild()
EnricherEnabledPayload.model_rebuild()
EnricherDisabledPayload.model_rebuild()
EnrichmentProposedPayload.model_rebuild()
EnrichmentAcceptedPayload.model_rebuild()
EnrichmentRejectedPayload.model_rebuild()
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
SettingValidation.model_rebuild()
SettingDefinition.model_rebuild()
SettingChangedPayload.model_rebuild()
SettingLockedPayload.model_rebuild()
SettingChangeRow.model_rebuild()
SettingLockRow.model_rebuild()
SettingEffectApplied.model_rebuild()
File.model_rebuild()
SubscriptionFilter.model_rebuild()
WebhookSubscription.model_rebuild()
EventOrigin.model_rebuild()
EventLinkRef.model_rebuild()
CloudEventData.model_rebuild()
CloudEvent.model_rebuild()
IntegrationApp.model_rebuild()
ActionDefinition.model_rebuild()
ActionInvocation.model_rebuild()
ActionInvocationTarget.model_rebuild()
Rule.model_rebuild()
InboundEndpoint.model_rebuild()
InboundEndpointVersion.model_rebuild()
Enricher.model_rebuild()
EnrichmentValue.model_rebuild()
OutboxEvent.model_rebuild()
WebhookDelivery.model_rebuild()
WebhookAttempt.model_rebuild()
WebhookSecret.model_rebuild()
WebhookHealth.model_rebuild()
WebhookCursor.model_rebuild()
ExtensionRecord.model_rebuild()
TypeRegistrationRegisteredPayload.model_rebuild()
TypeRegistrationQuarantinedPayload.model_rebuild()
TypeRegistrationDeprecatedPayload.model_rebuild()
RecordBodyStoredPayload.model_rebuild()
TypeRegistrationRow.model_rebuild()
RecordBody.model_rebuild()
BodyQuarantine.model_rebuild()
Account.model_rebuild()
AgentToken.model_rebuild()
AuthCredential.model_rebuild()
AuthSession.model_rebuild()
AuthTokenSecret.model_rebuild()
AuthAttempt.model_rebuild()
AuthAudit.model_rebuild()
AccountEventPayload.model_rebuild()
AccountCreatedPayload.model_rebuild()
AccountRolesSetPayload.model_rebuild()
AccountDisabledPayload.model_rebuild()
AccountEnabledPayload.model_rebuild()
AccountPasswordChangedPayload.model_rebuild()
AgentTokenIssuedPayload.model_rebuild()
AgentTokenRevokedPayload.model_rebuild()
JobQueue.model_rebuild()
IntegrationSecret.model_rebuild()
InboundReplay.model_rebuild()
InboundDelivery.model_rebuild()
InboundCounter.model_rebuild()
RuleCursor.model_rebuild()
RuleFiring.model_rebuild()
EnrichmentCursor.model_rebuild()
