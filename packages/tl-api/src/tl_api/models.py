"""Response and request models that have no tl_core class of their own.

Everything else in the API is a tl_core model used as is (``Event``, ``CommandResult``,
``LinkView``, ``TraceNode``, ``FileInfo`` ...), so the OpenAPI document and the HTTP client read
the same classes the services return.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class RecordOut(BaseModel):
    """A record envelope (brief 6.2): the dict ``tl_core.services.queries`` returns."""

    id: str
    key: str | None
    type: str
    scope: str
    title: str
    description: str | None
    status: str | None
    psets: dict[str, Any]
    voided: bool
    version: int  # also sent as the ETag
    last_seq: int
    effective_schema_hash: str | None
    conformance: str
    created_at: str
    updated_at: str


class CountOut(BaseModel):
    count: int


class RelationOut(BaseModel):
    """A relation of the link vocabulary (brief 7.1)."""

    code: str  # forward code, e.g. "raised_against"
    label: str  # "raised against"
    inverse_code: str
    inverse_label: str  # "has raised"


class DefaultRelationOut(BaseModel):
    relation: str


class DetectKeysBody(BaseModel):
    """Body of ``POST /keys/detect`` (a read: it only looks keys up)."""

    scope: str
    text: str
    linked_to: str | None = (
        None  # a record id: link status is reported against it, and it is left out
    )
