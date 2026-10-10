"""A busy write lock is one named error on both adapters, and nothing is left half-open (P0-I5)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import event
from tl_adapters._unit import BaseUnitOfWork
from tl_adapters.db import DbTarget, create_schema, make_engine, make_ledger, write_tx
from tl_adapters.postgres import engine as pg_engine
from tl_core.projection.defaults import default_registry
from tl_core.services.errors import LockTimeoutError, RetryableTransactionError


def test_a_busy_write_lock_raises_lock_timeout_and_the_unit_of_work_stays_usable(
    adapter_name: str, new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch
) -> None:
    target = new_db()
    create_schema(target)
    engine = make_engine(target)
    if adapter_name == "postgres":
        monkeypatch.setattr(pg_engine, "LOCK_TIMEOUT", "200ms")
    else:

        @event.listens_for(engine, "connect")
        def _short_busy_timeout(dbapi_connection: Any, _record: Any) -> None:
            dbapi_connection.execute("PRAGMA busy_timeout=200")

    uow = BaseUnitOfWork(
        make_ledger(engine), default_registry(), None, lambda: write_tx(engine), readonly=False
    )
    try:
        with write_tx(engine):  # another writer holds the lock
            with pytest.raises(LockTimeoutError):
                uow.__enter__()
            with pytest.raises(RetryableTransactionError) as raised, write_tx(engine):
                pass
            assert isinstance(raised.value, LockTimeoutError)  # a retryable kind of error
        with uow:  # the failed enter left the unit of work reusable
            assert uow.conn() is not None
    finally:
        engine.dispose()
