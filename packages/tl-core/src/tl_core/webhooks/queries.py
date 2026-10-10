"""Read-only views over subscriptions and deliveries, for the CLI and later screens.

Plain dicts, fixed SQL, bound parameters. Nothing here returns a secret.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from tl_core.uow import UnitOfWork
from tl_core.webhooks.base import iso_z, utc_now
from tl_core.webhooks.rows import load_json

_SUBSCRIPTION_SQL = (
    "SELECT s.subscription_id, s.scope, s.name, s.owner, s.target_url, s.filter_json, "
    "s.payload_mode, s.status, s.disabled_reason, s.expires_at, s.current_secret_id, s.created_at, "
    "COALESCE(h.delivered_total, 0) AS delivered_total, "
    "COALESCE(h.failed_total, 0) AS failed_total, "
    "COALESCE(h.consecutive_dead, 0) AS consecutive_dead, h.failing_since, h.last_success_at, "
    "(SELECT COUNT(*) FROM wh_delivery d WHERE d.subscription_id = s.subscription_id "
    "AND d.status = 'pending') AS pending, "
    "(SELECT COUNT(*) FROM wh_delivery d WHERE d.subscription_id = s.subscription_id "
    "AND d.status = 'dead') AS dead, "
    "(CASE WHEN EXISTS (SELECT 1 FROM wh_secret w WHERE w.subscription_id = s.subscription_id "
    "AND w.state = 'active' AND (w.expires_at IS NULL OR w.expires_at > :now)) "
    "THEN 0 ELSE 1 END) AS no_secret "
    "FROM cur_webhook_subscription s LEFT JOIN wh_health h ON h.subscription_id = s.subscription_id"
)


def _subscription(row: Any) -> dict[str, Any]:
    out = dict(row)
    out["filter"] = load_json(out.pop("filter_json"))
    out["needs_secret"] = bool(out.pop("no_secret")) and out["status"] == "active"
    # `status_label` is what listings print: an active subscription without a signing secret (a
    # restored database) is shown as `needs_secret`; `status` itself is the projection's value.
    out["status_label"] = "needs_secret" if out["needs_secret"] else out["status"]
    return out


def _now() -> str:
    return iso_z(utc_now())


def list_subscriptions(uow: UnitOfWork, scope: str | None = None) -> list[dict[str, Any]]:
    """Subscriptions (optionally of one scope) with delivery counts, oldest first."""
    sql = _SUBSCRIPTION_SQL + (" WHERE s.scope = :scope" if scope else "")
    sql += " ORDER BY s.created_at, s.subscription_id"
    params: dict[str, Any] = {"now": _now()}
    if scope:
        params["scope"] = scope
    rows = uow.conn().execute(text(sql), params).mappings()
    return [_subscription(row) for row in rows]


def get_subscription(uow: UnitOfWork, subscription_id: str) -> dict[str, Any] | None:
    sql = _SUBSCRIPTION_SQL + " WHERE s.subscription_id = :s"
    row = uow.conn().execute(text(sql), {"s": subscription_id, "now": _now()}).mappings().first()
    return None if row is None else _subscription(row)


def list_deliveries(
    uow: UnitOfWork, subscription_id: str, *, status: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """Newest deliveries of a subscription first (the delivery log), without bodies."""
    sql = (
        "SELECT delivery_id, seq, event_id, subject_id, origin, status, attempts, created_at, "
        "next_attempt_at, last_status, last_error, delivered_at, dead_at, dead_reason "
        "FROM wh_delivery WHERE subscription_id = :s"
    )
    params: dict[str, Any] = {"s": subscription_id, "limit": limit}
    if status is not None:
        sql += " AND status = :status"
        params["status"] = status
    sql += " ORDER BY seq DESC, delivery_id DESC LIMIT :limit"
    return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]


def list_dlq(
    uow: UnitOfWork, subscription_id: str | None = None, *, limit: int = 100
) -> list[dict[str, Any]]:
    """Dead-lettered deliveries (not yet redriven), oldest first."""
    sql = (
        "SELECT delivery_id, subscription_id, seq, event_id, subject_id, attempts, last_status, "
        "last_error, dead_at, dead_reason FROM wh_delivery WHERE status = 'dead'"
    )
    params: dict[str, Any] = {"limit": limit}
    if subscription_id is not None:
        sql += " AND subscription_id = :s"
        params["s"] = subscription_id
    sql += " ORDER BY seq, delivery_id LIMIT :limit"
    return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]


def list_attempts(uow: UnitOfWork, delivery_id: str) -> list[dict[str, Any]]:
    """The attempt log of one delivery, first attempt first."""
    sql = (
        "SELECT attempt, started_at, latency_ms, status, outcome, error, response_excerpt "
        "FROM wh_attempt WHERE delivery_id = :d ORDER BY attempt"
    )
    return [dict(r) for r in uow.conn().execute(text(sql), {"d": delivery_id}).mappings()]
