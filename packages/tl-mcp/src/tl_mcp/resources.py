"""The bodies of the resources (T43): a record with its links, a form schema, the relations.

Each returns JSON text. ``server.py`` registers them under ``tl://record/{scope}/{key}``,
``tl://schema/{scope}/{record_type}`` and ``tl://relations``.
"""

from __future__ import annotations

import json
from typing import Any

from tl_core.links.provider import get_vocabulary
from tl_core.services import link_queries, psets, queries
from tl_core.services.errors import RecordNotFoundError

from tl_mcp.context import McpContext


def dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def record_resource(ctx: McpContext, *, scope: str, key: str) -> str:
    """``{"record": <envelope>, "links": [<LinkView>...]}`` for the record with this key.

    Links are the active, stale, broken and suggested ones (``links_of`` without retracted).
    Raises ``RecordNotFoundError``.
    """
    with ctx.factory(True) as uow:
        found = queries.get_record(uow, scope, key)
        if found is None:
            raise RecordNotFoundError(f"no record with key {key!r} in scope {scope!r}")
        links = link_queries.links_of(uow, found["id"])
        return dump({"record": found, "links": [link.model_dump(mode="json") for link in links]})


def schema_resource(ctx: McpContext, *, scope: str, record_type: str) -> str:
    """The form metadata (``FormMetadata``) of a record type under the scope's effective schema."""
    with ctx.factory(True) as uow:
        meta = psets.form_metadata(uow, scope, record_type)
        return dump(meta.model_dump(mode="json"))


def relations_resource(ctx: McpContext) -> str:
    """The relation vocabulary: a list of ``{code, label, inverse_code, inverse_label}``."""
    vocabulary = get_vocabulary()
    rows = []
    for code in vocabulary.codes():
        relation = vocabulary.get(code)
        rows.append(
            {
                "code": relation.code,
                "label": relation.label,
                "inverse_code": relation.inverse_code,
                "inverse_label": relation.inverse_label,
            }
        )
    return dump(rows)
