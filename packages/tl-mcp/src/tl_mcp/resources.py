"""The bodies of the resources (T43): a record with its links, a form schema, the relations.

STUB (P0-I4-T43): function bodies below raise ``NotImplementedError``. Names, signatures and
docstrings are final; implement the bodies, then delete this paragraph.

Each returns JSON text. ``server.py`` registers them under ``tl://record/{scope}/{key}``,
``tl://schema/{scope}/{record_type}`` and ``tl://relations``.
"""

from __future__ import annotations

from typing import Any

from tl_mcp.context import McpContext


def dump(data: Any) -> str:
    raise NotImplementedError("STUB (P0-I4-T43)")


def record_resource(ctx: McpContext, *, scope: str, key: str) -> str:
    """``{"record": <envelope>, "links": [<LinkView>...]}`` for the record with this key.

    Links are the active, stale, broken and suggested ones (``links_of`` without retracted).
    Raises ``RecordNotFoundError``.
    """
    raise NotImplementedError("STUB (P0-I4-T43)")


def schema_resource(ctx: McpContext, *, scope: str, record_type: str) -> str:
    """The form metadata (``FormMetadata``) of a record type under the scope's effective schema."""
    raise NotImplementedError("STUB (P0-I4-T43)")


def relations_resource(ctx: McpContext) -> str:
    """The relation vocabulary: a list of ``{code, label, inverse_code, inverse_label}``."""
    raise NotImplementedError("STUB (P0-I4-T43)")
