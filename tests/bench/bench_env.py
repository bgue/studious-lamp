"""Building the clients a bench talks to: an embedded TUI client on either dialect."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any

from bench_data import Dataset
from bench_gen import SCOPE
from tl_adapters import db as adapter_db
from tl_core.uow import UnitOfWork
from tl_tui.embedded import EmbeddedClient

RECORDS = int(os.environ.get("TL_BENCH_RECORDS", "100000"))
REBUILD_RECORDS = int(os.environ.get("TL_BENCH_REBUILD_RECORDS", "10000"))
DIALECTS = [d.strip() for d in os.environ.get("TL_BENCH_DIALECTS", "sqlite,postgres").split(",")]
ROUNDS = int(os.environ.get("TL_BENCH_ROUNDS", "3"))
SAMPLES = int(os.environ.get("TL_BENCH_SAMPLES", "20"))
LABEL = os.environ.get("TL_BENCH_LABEL", "bench")

UowFactory = Callable[[bool], AbstractContextManager[UnitOfWork]]


@contextmanager
def embedded_client(dataset: Dataset) -> Iterator[EmbeddedClient]:
    """The TUI's embedded client over ``dataset``: one pooled engine, one unit of work per call."""
    factory: Any = adapter_db.make_uow_factory(dataset.target)
    client = EmbeddedClient(factory)
    try:
        yield client
    finally:
        factory.dispose()


__all__ = [
    "DIALECTS",
    "LABEL",
    "RECORDS",
    "REBUILD_RECORDS",
    "ROUNDS",
    "SAMPLES",
    "SCOPE",
    "UowFactory",
    "embedded_client",
]
