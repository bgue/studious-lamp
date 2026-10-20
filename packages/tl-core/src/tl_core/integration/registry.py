"""Reading the integration records for screens and clients (P1-I7; FANOUT D11, D12).

One read for the API route, the embedded TUI client and the tests: rows of the projection tables
with their ``*_json`` columns parsed. No secret is ever in these tables; the columns that hold an
executor's configuration are left out, and the deliveries (the inbound error queue) come without
their payload or object key.
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import Connection, text

from tl_core import confidentiality
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
    include_shadow: bool = False,
) -> list[dict[str, Any]]:
    """The rows of one ``kind`` (``KINDS``). ``state`` filters enrichments (``acceptance_state``)
    and deliveries (``state``); ``target_id`` enrichments by record; ``endpoint_id`` deliveries.
    Shadow values (an enricher on trial, never shown to a person) come back only with
    ``include_shadow``, which the caller sets for an admin."""
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
            # a value of a record the viewer may not read is not listed (ADR-0016)
            visible, visible_params = confidentiality.not_hidden("target_id")
            clauses.append(visible)
            params.update(visible_params)
            if state is not None:
                clauses.append("acceptance_state = :state")
                params["state"] = state
            if target_id is not None:
                clauses.append("target_id = :target")
                params["target"] = target_id
            if not include_shadow:
                clauses.append("acceptance_state <> 'shadow'")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM {table}{where} ORDER BY {order} LIMIT :limit"  # noqa: S608
    found = [decode(dict(r)) for r in conn.execute(text(sql), params).mappings()]
    if kind == "invocations":
        found = _visible_invocations(conn, found)
    return found


def _target_ids(row: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for target in cast("list[object]", row.get("targets") or []):
        if isinstance(target, dict):
            record_id = cast("dict[str, object]", target).get("id")
            if record_id:
                found.append(str(record_id))
    return found


def _visible_invocations(conn: Connection, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The invocations none of whose targets the viewer must not read: the row names the records
    (key, id) it ran on, so one on a hidden record is not listed (ADR-0016)."""
    hidden = confidentiality.hidden_among(conn, [i for row in rows for i in _target_ids(row)])
    if not hidden:
        return rows
    return [row for row in rows if not hidden.intersection(_target_ids(row))]


__all__ = ["KINDS", "MAX_ROWS", "TABLES", "decode", "list_registry"]
