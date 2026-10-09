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
     'imports': ['linkml:types', 'annotations', 'record', 'ledger'],
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



class RecordEnvelope(ConfiguredBaseModel):
    """
    Fields every record type shares (brief 6.2). Mixed into each concrete record class.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True, 'from_schema': 'https://example.org/throughline/core/record'})

    id: str = Field(default=..., description="""Immutable global identifier; equals the ledger `stream_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    key: Optional[str] = Field(default=None, description="""Human-readable number, unique within a scope. Null until numbering assigns one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    type: str = Field(default=..., description="""Fully qualified record type, for example `core.Record`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    scope: str = Field(default=..., description="""`company` or `project:<id>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Event']} })
    title: str = Field(default=..., description="""Short human-readable title.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    description: Optional[str] = Field(default=None, description="""Longer free-text description.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    status: Optional[str] = Field(default=None, description="""Workflow state; null when the record type has no workflow.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    psets: Any = Field(default=..., description="""Property-set values keyed by pset name, stored as a JSON object.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordEnvelope']} })
    voided: bool = Field(default=False, description="""Set by `Record.Voided`. Voided rows are never deleted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope'], 'ifabsent': 'false'} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    effective_schema_hash: Optional[str] = Field(default=None, description="""Hash of the effective schema in force at the last write; null before Increment 2.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    conformance: ConformanceStatus = Field(default=ConformanceStatus("ok"), description="""Conformance of the current values to the effective schema.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope'], 'ifabsent': 'string(ok)'} })
    created_at: datetime  = Field(default=..., description="""Timestamp of the creating event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    updated_at: datetime  = Field(default=..., description="""Timestamp of the last applied event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })


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
    scope: str = Field(default=..., description="""`company` or `project:<id>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Event']} })
    title: str = Field(default=..., description="""Short human-readable title.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    description: Optional[str] = Field(default=None, description="""Longer free-text description.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    status: Optional[str] = Field(default=None, description="""Workflow state; null when the record type has no workflow.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    psets: Any = Field(default=..., description="""Property-set values keyed by pset name, stored as a JSON object.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['RecordEnvelope']} })
    voided: bool = Field(default=False, description="""Set by `Record.Voided`. Voided rows are never deleted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope'], 'ifabsent': 'false'} })
    version: int = Field(default=..., description="""Ledger `stream_version` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    last_seq: int = Field(default=..., description="""Ledger `seq` of the last event applied.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    effective_schema_hash: Optional[str] = Field(default=None, description="""Hash of the effective schema in force at the last write; null before Increment 2.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    conformance: ConformanceStatus = Field(default=ConformanceStatus("ok"), description="""Conformance of the current values to the effective schema.""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope'], 'ifabsent': 'string(ok)'} })
    created_at: datetime  = Field(default=..., description="""Timestamp of the creating event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })
    updated_at: datetime  = Field(default=..., description="""Timestamp of the last applied event (system time).""", json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope']} })


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
    scope: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['RecordEnvelope', 'Event']} })
    payload: Any = Field(default=..., description="""Event payload, a JSON object validated against the event type's schema.""", json_schema_extra = { "linkml_meta": {'annotations': {'tl:json': {'tag': 'tl:json', 'value': True}},
         'domain_of': ['Event']} })
    actor: str = Field(default=..., description="""`user:<id>`, `svc:<name>` or `agent:<id>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    recorded_at: datetime  = Field(default=..., description="""System (transaction) time.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    effective_at: datetime  = Field(default=..., description="""Business (valid) time.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    correlation_id: str = Field(default=..., description="""Ties a command chain, import, or automated process together.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    causation_id: Optional[str] = Field(default=None, description="""Identifier of the event or command that caused this one; may be null.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    source: str = Field(default=..., description="""`tui`, `api`, `mcp:<agent>`, `cli`, `import:<job>` or `sim:<run>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    prev_hash: Optional[str] = Field(default=None, description="""Hash of the previous event in the same scope; null for the first.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })
    hash: str = Field(default=..., description="""Hash of this event chained to `prev_hash`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Event']} })


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
RecordEnvelope.model_rebuild()
Record.model_rebuild()
Event.model_rebuild()
