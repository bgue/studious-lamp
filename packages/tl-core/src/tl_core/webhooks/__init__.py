"""Outbound webhooks (brief 18.3, 18.4): outbox, subscriptions, signing, ordered delivery.

Dialect-neutral. Everything here talks to the database through a ``UnitOfWork`` connection
(SQLAlchemy Core with bound parameters) and to the network through a ``Transport`` Protocol, so the
SQLite and Postgres adapters share it. See ``docs/runbooks/webhook-operations.md`` and
``packages/tl-core/README.md``.
"""
