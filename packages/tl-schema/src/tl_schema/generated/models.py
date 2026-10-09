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
                 'workflow'],
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
                       'WorkflowState']} })
    title: str = Field(default=..., description="""Short human-readable title.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    description: Optional[str] = Field(default=None, description="""Longer free-text description.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    status: Optional[str] = Field(default=None, description="""Workflow state; null when the record type has no workflow.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link']} })
    psets: Any = Field(default=..., description="""Property-set values keyed by pset name, stored as a JSON object.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordEnvelope']} })
    voided: bool = Field(default=False, description="""Set by `Record.Voided`. Voided rows are never deleted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope'], 'ifabsent': 'false'} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link', 'NumberingCounter']} })
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
                       'WorkflowState']} })
    title: str = Field(default=..., description="""Short human-readable title.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    description: Optional[str] = Field(default=None, description="""Longer free-text description.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    status: Optional[str] = Field(default=None, description="""Workflow state; null when the record type has no workflow.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link']} })
    psets: Any = Field(default=..., description="""Property-set values keyed by pset name, stored as a JSON object.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordEnvelope']} })
    voided: bool = Field(default=False, description="""Set by `Record.Voided`. Voided rows are never deleted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope'], 'ifabsent': 'false'} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link', 'NumberingCounter']} })
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

    seq: int = Field(default=..., description="""Global monotonic sequence; the ordering backbone.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    event_id: str = Field(default=..., description="""Unique event identifier (ULID).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    stream_id: str = Field(default=..., description="""The record (aggregate) the event belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    stream_type: str = Field(default=..., description="""Record type of the stream, for example `core.Record`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    stream_version: int = Field(default=..., description="""Per-stream version, used for optimistic concurrency.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    event_type: str = Field(default=..., description="""`<Class>.<PastTenseVerb>`, for example `Record.Created`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    schema_version: int = Field(default=1, description="""Version of the event payload schema, for upcasting.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event'], 'ifabsent': 'int(1)'} })
    scope: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState']} })
    payload: Any = Field(default=..., description="""Event payload, a JSON object validated against the event type's schema.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['Event']} })
    actor: str = Field(default=..., description="""`user:<id>`, `svc:<name>` or `agent:<id>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
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
         'domain_of': ['PsetValue', 'LinkCount', 'WorkflowState']} })
    scope: str = Field(default=..., description="""Scope of the record, repeated so scope-wide filters need no join.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState']} })
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
                       'WorkflowState']} })
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
    reason: Optional[str] = Field(default=None, description="""Reason given with the last flag, decline, or retraction.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link']} })
    declined: bool = Field(default=False, description="""True when the link was a suggestion that a person declined. Declines are remembered.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link'], 'ifabsent': 'false'} })
    verified_by: Optional[str] = Field(default=None, description="""Actor of the last `Link.Verified` event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link']} })
    verified_at: Optional[datetime ] = Field(default=None, description="""Time of the last `Link.Verified` event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link']} })
    created_by: str = Field(default=..., description="""Actor of the creating event.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Link']} })
    created_at: datetime  = Field(default=..., description="""Time of the creating event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link']} })
    updated_at: datetime  = Field(default=..., description="""Time of the last applied event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'PsetValue', 'Link', 'NumberingCounter']} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link', 'NumberingCounter']} })
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

    record_id: str = Field(default=..., description="""The record the counts belong to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue', 'LinkCount', 'WorkflowState']} })
    scope: str = Field(default=..., description="""Scope of the record.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState']} })
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
                       'WorkflowState']} })
    pattern: str = Field(default=..., description="""Identifier of the numbering pattern.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    prefix: str = Field(default=..., description="""The rendered key without its sequence number, for example `P123-REC-`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    last_sequence: int = Field(default=..., description="""The highest sequence number allocated so far.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    last_key: str = Field(default=..., description="""The key built from `last_sequence`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    last_record_id: Optional[str] = Field(default=None, description="""The record the last number was allocated for; null for a standalone allocation.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    allocations: int = Field(default=..., description="""Number of allocations made from this counter.""", json_schema_extra = { "linkml_meta": {'domain_of': ['NumberingCounter']} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the counter after the last allocation.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Link', 'NumberingCounter']} })
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

    record_id: str = Field(default=..., description="""The record (ledger stream) the state belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['PsetValue', 'LinkCount', 'WorkflowState']} })
    scope: str = Field(default=..., description="""Scope of the record.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope',
                       'Event',
                       'PsetValue',
                       'Link',
                       'LinkCount',
                       'NumberingCounter',
                       'WorkflowState']} })
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
