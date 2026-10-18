"""Reading the integration records for screens and clients (P1-I7; FANOUT D11, D12).

One read for the API route, the embedded TUI client and the tests: rows of the projection tables
with their ``*_json`` columns parsed. No secret is ever in these tables; the columns that hold an
executor's configuration are left out, and the deliveries (the inbound error queue) come without
their payload or object key.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text

from tl_core.integration.errors import IntegrationNotFoundError
from tl_core.webhooks.rows import load_json

MAX_ROWS = 500
#: kind -> (table, order). The kinds a registry screen lists.
TABLES: dict[str, tuple[str, str]] = {
    "apps": ("cur_integration_app", "name"),
    "actions": ("cur_action_definition", "name"),
    "rules": ("cur_rule", "key"),
    "endpoints": ("cur_inbound_endpoint", "app, name"),
    "enrichers": ("cur_enricher", "name"),
    "invocations": ("cur_action_invocation", "seq DESC"),
    "enrichments": ("cur_enrichment_value", "seq DESC"),
}
KINDS = (*TABLES, "deliveries")
_HIDDEN = frozenset({"executor_config_json"})
_DELIVERY_COLUMNS = (
    "delivery_id, endpoint_id, endpoint_version, scope, state, payload_sha256, payload_size, "
    "received_at, finished_at, attempts, error_code, error_message, command_count"
)


def decode(row: dict[str, Any]) -> dict[str, Any]:
    """A row with its ``*_json`` columns parsed (and named without the suffix)."""
    out: dict[str, Any] = {}
    for name, value in row.items():
        if name in _HIDDEN:
            continue
        if name.endswith("_json") and isinstance(value, (str, bytes)):
            out[name.removesuffix("_json")] = load_json(value)
        else:
            out[name] = value
    return out


def list_registry(
    conn: Connection,
    kind: str,
    *,
    state: str | None = None,
    target_id: str | None = None,
    endpoint_id: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """The rows of one ``kind`` (``KINDS``). ``state`` filters enrichments (``acceptance_state``)
    and deliveries (``state``); ``target_id`` enrichments by record; ``endpoint_id`` deliveries."""
    if kind not in KINDS:
        raise IntegrationNotFoundError(f"no integration kind {kind}")
    limit = max(1, min(limit, MAX_ROWS))
    clauses: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    if kind == "deliveries":
        if state is not None:
            clauses.append("state = :state")
            params["state"] = state
        if endpoint_id is not None:
            clauses.append("endpoint_id = :endpoint")
            params["endpoint"] = endpoint_id
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT {_DELIVERY_COLUMNS} FROM int_delivery{where} "  # noqa: S608
            "ORDER BY received_at DESC, delivery_id DESC LIMIT :limit"
        )
    else:
        table, order = TABLES[kind]
        if kind == "enrichments":
            if state is not None:
                clauses.append("acceptance_state = :state")
                params["state"] = state
            if target_id is not None:
                clauses.append("target_id = :target")
                params["target"] = target_id
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM {table}{where} ORDER BY {order} LIMIT :limit"  # noqa: S608
    return [decode(dict(r)) for r in conn.execute(text(sql), params).mappings()]


__all__ = ["KINDS", "MAX_ROWS", "TABLES", "decode", "list_registry"]
