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
                 'feed'],
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



class RecordEnvelope(ConfiguredBaseModel):
    """
    Fields every record type shares (brief 6.2). Mixed into each concrete record class.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True, 'from_schema': 'https://example.org/throughline/core/record'})

    id: str = Field(default=..., description="""Immutable global identifier; equals the ledger `stream_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    key: Optional[str] = Field(default=None, description="""Human-readable number, unique within a scope. Null until numbering assigns one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    type: str = Field(default=..., description="""Fully qualified record type, for example `core.Record`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    scope: str = Field(default=..., description="""`company` or `project:<id>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag']} })
    title: str = Field(default=..., description="""Short human-readable title.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    description: Optional[str] = Field(default=None, description="""Longer free-text description.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    status: Optional[str] = Field(default=None, description="""Workflow state; null when the record type has no workflow.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link']} })
    psets: Any = Field(default=..., description="""Property-set values keyed by pset name, stored as a JSON object.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordEnvelope']} })
    voided: bool = Field(default=False, description="""Set by `Record.Voided`. Voided rows are never deleted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope'], 'ifabsent': 'false'} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link', 'NumberingCounter', 'FeedItemRow']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState']} })
    effective_schema_hash: Optional[str] = Field(default=None, description="""Hash of the effective schema in force at the last write; null before Increment 2.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    conformance: ConformanceStatus = Field(default=ConformanceStatus("ok"), description="""Conformance of the current values to the effective schema.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope'], 'ifabsent': 'string(ok)'} })
    created_at: datetime  = Field(default=..., description="""Timestamp of the creating event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link']} })
    updated_at: datetime  = Field(default=..., description="""Timestamp of the last applied event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'PsetValue', 'Link', 'NumberingCounter']} })


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

    id: str = Field(default=..., description="""Immutable global identifier; equals the ledger `stream_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    key: Optional[str] = Field(default=None, description="""Human-readable number, unique within a scope. Null until numbering assigns one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    type: str = Field(default=..., description="""Fully qualified record type, for example `core.Record`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    scope: str = Field(default=..., description="""`company` or `project:<id>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag']} })
    title: str = Field(default=..., description="""Short human-readable title.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    description: Optional[str] = Field(default=None, description="""Longer free-text description.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    status: Optional[str] = Field(default=None, description="""Workflow state; null when the record type has no workflow.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link']} })
    psets: Any = Field(default=..., description="""Property-set values keyed by pset name, stored as a JSON object.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordEnvelope']} })
    voided: bool = Field(default=False, description="""Set by `Record.Voided`. Voided rows are never deleted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope'], 'ifabsent': 'false'} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link', 'NumberingCounter', 'FeedItemRow']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState']} })
    effective_schema_hash: Optional[str] = Field(default=None, description="""Hash of the effective schema in force at the last write; null before Increment 2.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    conformance: ConformanceStatus = Field(default=ConformanceStatus("ok"), description="""Conformance of the current values to the effective schema.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope'], 'ifabsent': 'string(ok)'} })
    created_at: datetime  = Field(default=..., description="""Timestamp of the creating event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link']} })
    updated_at: datetime  = Field(default=..., description="""Timestamp of the last applied event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'PsetValue', 'Link', 'NumberingCounter']} })


class Event(ConfiguredBaseModel):
    """
    One immutable ledger event.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/ledger'})

    seq: int = Field(default=..., description="""Global monotonic sequence; the ordering backbone.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'FeedItemRow', 'Hashtag']} })
    event_id: str = Field(default=..., description="""Unique event identifier (ULID).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    stream_id: str = Field(default=..., description="""The record (aggregate) the event belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    stream_type: str = Field(default=..., description="""Record type of the stream, for example `core.Record`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    stream_version: int = Field(default=..., description="""Per-stream version, used for optimistic concurrency.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    event_type: str = Field(default=..., description="""`<Class>.<PastTenseVerb>`, for example `Record.Created`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'EventCard', 'FeedItemRow']} })
    schema_version: int = Field(default=1, description="""Version of the event payload schema, for upcasting.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event'], 'ifabsent': 'int(1)'} })
    scope: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag']} })
    payload: Any = Field(default=..., description="""Event payload, a JSON object validated against the event type's schema.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['Event']} })
    actor: str = Field(default=..., description="""`user:<id>`, `svc:<name>` or `agent:<id>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'EventCard', 'FeedItemRow']} })
    recorded_at: datetime  = Field(default=..., description="""System (transaction) time.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    effective_at: datetime  = Field(default=..., description="""Business (valid) time.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    correlation_id: str = Field(default=..., description="""Ties a command chain, import, or automated process together.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    causation_id: Optional[str] = Field(default=None, description="""Identifier of the event or command that caused this one; may be null.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    source: str = Field(default=..., description="""`tui`, `api`, `mcp:<agent>`, `cli`, `import:<job>` or `sim:<run>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'Link']} })
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
         'domain_of': ['PsetValue', 'LinkCount', 'WorkflowState', 'FeedTag', 'Hashtag']} })
    scope: str = Field(default=..., description="""Scope of the record, repeated so scope-wide filters need no join.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag']} })
    path: str = Field(default=..., description="""Layer-aware path, for example `psets.valve_data.x.fat_witness_by`.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['PsetValue']} })
    pset: str = Field(default=..., description="""Pset name, for example `valve_data` or `prj.shutdown_tie_in`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue']} })
    property_name: str = Field(default=..., description="""Property relative to the pset; custom-section properties start with `x.`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue']} })
    layer: PsetLayer = Field(default=..., description="""Layer derived from the path.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue']} })
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
                       'WorkflowState']} })
    updated_at: datetime  = Field(default=..., description="""Timestamp of that event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'PsetValue', 'Link', 'NumberingCounter']} })


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
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag']} })
    from_id: str = Field(default=..., description="""The record the link starts at (the subject of the relation).""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['Link']} })
    to_id: str = Field(default=..., description="""The record the link points to.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['Link']} })
    relation: str = Field(default=..., description="""Forward relation code, for example `raised_against`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link']} })
    status: LinkStatus = Field(default=LinkStatus("active"), description="""Lifecycle state.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link'], 'ifabsent': 'string(active)'} })
    pin: Optional[str] = Field(default=None, description="""Revision the link is pinned to; null means floating to the current revision.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link']} })
    note: Optional[str] = Field(default=None, description="""Optional free text.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link']} })
    source: LinkSource = Field(default=..., description="""How the link was created.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'Link']} })
    confidence: Optional[float] = Field(default=None, description="""Confidence of a suggested link, between 0 and 1.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link']} })
    reason: Optional[str] = Field(default=None, description="""Reason given with the last flag, decline, or retraction.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link', 'FeedRetracted']} })
    declined: bool = Field(default=False, description="""True when the link was a suggestion that a person declined. Declines are remembered.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link'], 'ifabsent': 'false'} })
    verified_by: Optional[str] = Field(default=None, description="""Actor of the last `Link.Verified` event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link']} })
    verified_at: Optional[datetime ] = Field(default=None, description="""Time of the last `Link.Verified` event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link']} })
    created_by: str = Field(default=..., description="""Actor of the creating event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link']} })
    created_at: datetime  = Field(default=..., description="""Time of the creating event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link']} })
    updated_at: datetime  = Field(default=..., description="""Time of the last applied event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'PsetValue', 'Link', 'NumberingCounter']} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link', 'NumberingCounter', 'FeedItemRow']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState']} })


class LinkCount(ConfiguredBaseModel):
    """
    Per-record link counts, maintained with `cur_links` (brief 7.4).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table', 'value': 'cur_link_counts'}},
         'from_schema': 'https://example.org/throughline/core/links'})

    record_id: str = Field(default=..., description="""The record the counts belong to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue', 'LinkCount', 'WorkflowState', 'FeedTag', 'Hashtag']} })
    scope: str = Field(default=..., description="""Scope of the record.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag']} })
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
                       'WorkflowState']} })


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
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag']} })
    pattern: str = Field(default=..., description="""Identifier of the numbering pattern.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    prefix: str = Field(default=..., description="""The rendered key without its sequence number, for example `P123-REC-`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    last_sequence: int = Field(default=..., description="""The highest sequence number allocated so far.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    last_key: str = Field(default=..., description="""The key built from `last_sequence`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    last_record_id: Optional[str] = Field(default=None, description="""The record the last number was allocated for; null for a standalone allocation.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    allocations: int = Field(default=..., description="""Number of allocations made from this counter.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the counter after the last allocation.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link', 'NumberingCounter', 'FeedItemRow']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last allocation.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState']} })
    updated_at: datetime  = Field(default=..., description="""Time of the last allocation (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'PsetValue', 'Link', 'NumberingCounter']} })


class WorkflowState(ConfiguredBaseModel):
    """
    The state a record is in, since when, and by which transition it got there.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'tl:current_state': {'tag': 'tl:current_state', 'value': True},
                         'tl:table': {'tag': 'tl:table',
                                      'value': 'cur_workflow_state'}},
         'from_schema': 'https://example.org/throughline/core/workflow'})

    record_id: str = Field(default=..., description="""The record (ledger stream) the state belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue', 'LinkCount', 'WorkflowState', 'FeedTag', 'Hashtag']} })
    scope: str = Field(default=..., description="""Scope of the record.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag']} })
    workflow: str = Field(default=..., description="""Identifier of the workflow definition, for example `core.review`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState']} })
    workflow_version: int = Field(default=..., description="""Version of the workflow definition that was in force.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState']} })
    state: str = Field(default=..., description="""Current state name.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['WorkflowState']} })
    entered_at: datetime  = Field(default=..., description="""When the record entered the state (`state_entered_at`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState']} })
    transition: str = Field(default=..., description="""Name of the transition that led here.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState']} })
    transitioned_by: str = Field(default=..., description="""Actor of the transition.""", json_schema_extra = { "linkml_meta": {'domain_of': ['WorkflowState']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the transition event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState']} })


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
    record_id: Optional[str] = Field(default=None, description="""For a record tag that resolved to a record, that record's id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue', 'LinkCount', 'WorkflowState', 'FeedTag', 'Hashtag']} })


class ActivityPost(ConfiguredBaseModel):
    """
    A broadcast post (brief 19.2, 21.1). Authored by a person, an agent or an external party; an agent's posts are labelled by its `agent:<id>` actor. A post has no replies.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'class_uri': 'as:Note',
         'from_schema': 'https://example.org/throughline/core/feed'})

    post_id: str = Field(default=..., description="""Immutable post identifier; equals the ledger `stream_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPosted',
                       'FeedEdited',
                       'FeedRetracted',
                       'FeedReacted']} })
    scope: str = Field(default=..., description="""The project the post was made in. A post is visible wherever its project is.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState',
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag']} })
    author: str = Field(default=..., description="""Actor that posted (`user:<id>`, `agent:<id>` or `svc:<name>`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'FeedPosted']} })
    body: str = Field(default=..., description="""Text of the post, with its `#tags` and `@mentions`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'FeedPosted', 'FeedEdited']} })
    importance: Importance = Field(default=Importance("normal"), description="""Importance the author gave; a signal tag raises the effective level to high.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'EventCard', 'FeedPosted', 'FeedItemRow'],
         'ifabsent': 'string(normal)'} })
    tags: Optional[list[FeedTag]] = Field(default=None, description="""Tags found in the body.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'FeedPosted', 'FeedEdited']} })
    record_ids: Optional[list[str]] = Field(default=None, description="""Records the post references (the resolved record tags), without repeats.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'FeedPosted', 'FeedEdited']} })


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
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag']} })
    actor: str = Field(default=..., description="""Actor of the aggregated events.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'EventCard', 'FeedItemRow']} })
    summary: str = Field(default=..., description="""Rendered one-line summary, for example `jsmith created 14 records`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventCard', 'FeedItemRow']} })
    importance: Importance = Field(default=Importance("low"), description="""System cards are low importance.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'EventCard', 'FeedPosted', 'FeedItemRow'],
         'ifabsent': 'string(low)'} })
    event_type: str = Field(default=..., description="""The ledger event type every aggregated event has.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'EventCard', 'FeedItemRow']} })
    event_count: int = Field(default=..., description="""Number of aggregated ledger events.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventCard', 'FeedItemRow']} })
    subjects: Optional[list[str]] = Field(default=None, description="""Records the aggregated events are about.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventCard']} })


class FeedPosted(ConfiguredBaseModel):
    """
    Payload of `Feed.Posted`, the first event of a post stream.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/feed'})

    post_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPosted',
                       'FeedEdited',
                       'FeedRetracted',
                       'FeedReacted']} })
    body: str = Field(default=..., description="""Text of the post.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'FeedPosted', 'FeedEdited']} })
    author: str = Field(default=..., description="""Actor that posted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'FeedPosted']} })
    importance: Importance = Field(default=Importance("normal"), description="""Importance the author gave. The projection derives the effective level from it and the tags.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'EventCard', 'FeedPosted', 'FeedItemRow'],
         'ifabsent': 'string(normal)'} })
    tags: Optional[list[FeedTag]] = Field(default=None, description="""Tags found in the body, after resolution.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'FeedPosted', 'FeedEdited']} })
    record_ids: Optional[list[str]] = Field(default=None, description="""Records the post references, without repeats.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'FeedPosted', 'FeedEdited']} })


class FeedEdited(ConfiguredBaseModel):
    """
    Payload of `Feed.Edited`: a full replacement of the body and its tags. The earlier text stays in the ledger, so edits are visible history (brief 21.1).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/feed'})

    post_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPosted',
                       'FeedEdited',
                       'FeedRetracted',
                       'FeedReacted']} })
    body: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'FeedPosted', 'FeedEdited']} })
    tags: Optional[list[FeedTag]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'FeedPosted', 'FeedEdited']} })
    record_ids: Optional[list[str]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'FeedPosted', 'FeedEdited']} })


class FeedRetracted(ConfiguredBaseModel):
    """
    Payload of `Feed.Retracted`. The projection keeps a tombstone row and drops the body.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/feed'})

    post_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPosted',
                       'FeedEdited',
                       'FeedRetracted',
                       'FeedReacted']} })
    reason: str = Field(default=..., description="""Why the post was retracted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link', 'FeedRetracted']} })


class FeedReacted(ConfiguredBaseModel):
    """
    Payload of `Feed.Reacted`: the actor of the event sets (`on` true) or clears (`on` false) one acknowledgement on a post. Reactions are limited to `ack`, `+1` and `resolved` (brief 21.1).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://example.org/throughline/core/feed'})

    post_id: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost',
                       'FeedPosted',
                       'FeedEdited',
                       'FeedRetracted',
                       'FeedReacted']} })
    reaction: str = Field(default=..., description="""One of `ack`, `+1`, `resolved`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedReacted']} })
    on: bool = Field(default=..., description="""True to set the reaction, false to clear it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedReacted']} })

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
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag']} })
    actor: str = Field(default=..., description="""Author of a post, or the actor of a card's events.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'EventCard', 'FeedItemRow']} })
    occurred_at: datetime  = Field(default=..., description="""`recorded_at` of the post, or of the latest event of a card.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow']} })
    seq: int = Field(default=..., description="""`seq` of the posted event, or of the latest event of a card.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['Event', 'FeedItemRow', 'Hashtag']} })
    summary: str = Field(default=..., description="""Body of a post (empty once retracted) or the rendered summary of a card.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventCard', 'FeedItemRow']} })
    importance: Importance = Field(default=Importance("normal"), description="""Effective importance. High when a post has a signal tag, else `base_importance`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityPost', 'EventCard', 'FeedPosted', 'FeedItemRow'],
         'ifabsent': 'string(normal)'} })
    base_importance: Importance = Field(default=Importance("normal"), description="""Importance the author gave the post (cards are low).""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow'], 'ifabsent': 'string(normal)'} })
    event_type: Optional[str] = Field(default=None, description="""Cards only; the event type of every aggregated event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'EventCard', 'FeedItemRow']} })
    event_count: int = Field(default=1, description="""1 for a post; the number of aggregated ledger events for a card.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EventCard', 'FeedItemRow'], 'ifabsent': 'int(1)'} })
    first_us: Optional[int] = Field(default=None, description="""Cards only; `recorded_at` of the first aggregated event in microseconds since the Unix epoch. An integer so the window test does not depend on how a dialect returns timestamps.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow']} })
    first_seq: Optional[int] = Field(default=None, description="""Cards only; `seq` of the first aggregated event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow']} })
    open_scope: Optional[str] = Field(default=None, description="""Cards only; the scope while the card can still be extended, else null.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow']} })
    retracted: bool = Field(default=False, description="""True once the post was retracted. The row stays as a tombstone.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow'], 'ifabsent': 'false'} })
    retract_reason: Optional[str] = Field(default=None, description="""Reason given with `Feed.Retracted`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow']} })
    edit_count: int = Field(default=0, description="""Number of `Feed.Edited` events applied to the post.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedItemRow'], 'ifabsent': 'int(0)'} })
    reactions: Any = Field(default=..., description="""Reacting actors by reaction (a JSON object such as ack: [user:a]); empty lists are dropped.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['FeedItemRow']} })
    version: Optional[int] = Field(default=None, description="""Posts only; ledger `stream_version` of the post stream after the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link', 'NumberingCounter', 'FeedItemRow']} })


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
                       'ActivityPost',
                       'EventCard',
                       'FeedItemRow',
                       'Hashtag']} })
    kind: TagKind = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag', 'Hashtag']} })
    tag_text: str = Field(default=..., description="""The tag as written, without its sigil. For a card's subject row, the record id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Hashtag']} })
    tag_key: str = Field(default=..., description="""Normalised text used to find the tag's feed (lower case). For a card's subject row, the record id.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['Hashtag']} })
    namespace: Optional[str] = Field(default=None, description="""For code and mention tags, the part before the colon.""", json_schema_extra = { "linkml_meta": {'domain_of': ['FeedTag', 'Hashtag']} })
    record_id: Optional[str] = Field(default=None, description="""For a resolved record tag, or a card's subject, the record.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:indexed': {'tag': 'tl:indexed', 'value': True}},
         'domain_of': ['PsetValue', 'LinkCount', 'WorkflowState', 'FeedTag', 'Hashtag']} })
    start_pos: int = Field(default=..., description="""Offset of the sigil in the post body; 0 for a card's subject row.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Hashtag']} })
    end_pos: int = Field(default=..., description="""Offset just past the tag; 0 for a card's subject row.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Hashtag']} })
    seq: int = Field(default=..., description="""`seq` of the event that added the row; orders a card's subjects.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event', 'FeedItemRow', 'Hashtag']} })


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
FeedTag.model_rebuild()
ActivityPost.model_rebuild()
EventCard.model_rebuild()
FeedPosted.model_rebuild()
FeedEdited.model_rebuild()
FeedRetracted.model_rebuild()
FeedReacted.model_rebuild()
FeedItemRow.model_rebuild()
Hashtag.model_rebuild()
