"""The constraint hook: where an RFI will block work until it is answered (a stub; Phase 2).

Brief 9, M10: "The RFI record is a Technical-domain correspondence item. It feeds AWP constraints
(IWP blocked until answered)." There are no work packages yet, so the hook is a seam and nothing
more. ``ConstraintSink`` is called when an RFI is issued (a constraint opens) and when it is
answered (a constraint can close), with the item and its domain data; ``NullSink`` is the default
and records nothing. Phase 2 puts the AWP constraint behind it: it reads the records the RFI is
linked to (a work package it holds up) and writes a ``Constraint`` through its own command.

The hook runs inside the command's unit of work, after the item's events were appended, so a sink
that raises undoes the command. A sink must not read or write anything the caller may not.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Protocol

from tl_core.uow import UnitOfWork

from tl_mod_correspondence import registry, registry_domain


class ConstraintSink(Protocol):
    def rfi_issued(
        self, uow: UnitOfWork, item: registry.ItemRow, data: registry_domain.TechnicalData
    ) -> None:
        """An RFI, technical query or deviation request was issued: a constraint may open."""
        ...

    def rfi_answered(
        self, uow: UnitOfWork, item: registry.ItemRow, data: registry_domain.TechnicalData
    ) -> None:
        """It was answered: the constraint it held up can close."""
        ...


class NullSink:
    """The default: nothing is recorded."""

    def rfi_issued(
        self, uow: UnitOfWork, item: registry.ItemRow, data: registry_domain.TechnicalData
    ) -> None:
        del uow, item, data

    def rfi_answered(
        self, uow: UnitOfWork, item: registry.ItemRow, data: registry_domain.TechnicalData
    ) -> None:
        del uow, item, data


_sink: ConstraintSink = NullSink()


def current() -> ConstraintSink:
    """The sink in force (the null sink unless a process installed another)."""
    return _sink


@contextmanager
def use_sink(sink: ConstraintSink) -> Generator[None]:
    """Install ``sink`` for the length of a block (Phase 2's wiring, and tests)."""
    global _sink
    previous, _sink = _sink, sink
    try:
        yield
    finally:
        _sink = previous
