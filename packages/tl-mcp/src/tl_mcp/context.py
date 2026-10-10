"""What every tool and resource needs: a unit-of-work factory, the actor and the authorise hook."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass

from tl_core.uow import UnitOfWork

#: ``factory(readonly)`` yields an entered unit of work (``SqliteUowFactory`` has this shape).
UowFactory = Callable[[bool], AbstractContextManager[UnitOfWork]]
Authorizer = Callable[[str, str, str], None]


@dataclass(frozen=True)
class McpContext:
    factory: UowFactory
    actor: str  # ``agent:<id>`` or ``user:<id>``, fixed for the life of the server (ADR-0005)
    authorize: Authorizer
