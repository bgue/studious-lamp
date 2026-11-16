"""The gas test command (P2-PTW S3).

A gas test is one record of ``permits.GasTest``, a fact nothing changes. Its ``result`` is computed
by ``rules.gas_result`` from the five limits of the settings ``permits.gas.*`` read at project
scope; it is never typed. A failing test of an Active or Lapsed permit whose type needs a gas test
suspends the permit in the same unit of work (``Permit.Suspended`` through ``common.move``),
without the suspend word: the safety rule outranks the actor's words.
"""

from __future__ import annotations

from datetime import UTC
from decimal import Decimal
from typing import TYPE_CHECKING

from tl_core.ledger import NewEvent, iso_utc
from tl_core.services.commands import CommandResult
from tl_core.services.records import create_module_record
from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of
from tl_core.uow import UnitOfWork

from tl_mod_permits import rules
from tl_mod_permits.errors import GasTestRuleError, PermitStateError
from tl_mod_permits.handlers import common
from tl_mod_permits.handlers.common import append, correlated, move, require_project, silent
from tl_mod_permits.handlers.permit import load_permit
from tl_mod_permits.names import (
    ACTIVE,
    APPROVED,
    GAS_TEST,
    GAS_TEST_RECORDED,
    LAPSED,
    PERMIT,
    PERMIT_SUSPENDED,
    SUSPENDED,
    T_SUSPEND,
)
from tl_mod_permits.types_table import load_types

if TYPE_CHECKING:
    from tl_mod_permits.iso_commands import RecordGasTest

#: The states a gas test can be recorded against (not a permit that is over or not yet approved).
TESTABLE = (APPROVED, ACTIVE, LAPSED, SUSPENDED)
#: The states in which a failing test stops the work.
STOPPABLE = (ACTIVE, LAPSED)
MSG_FUTURE = "a gas test cannot be dated in the future"
MSG_SUSPENDED_BY_GAS = "gas test failed"
LIMIT_KEYS = {
    "o2_min_pct": "permits.gas.o2_min_pct",
    "o2_max_pct": "permits.gas.o2_max_pct",
    "lel_max_pct": "permits.gas.lel_max_pct",
    "h2s_max_ppm": "permits.gas.h2s_max_ppm",
    "co_max_ppm": "permits.gas.co_max_ppm",
}


def gas_limits(uow: UnitOfWork, scope: str) -> rules.GasLimits:
    """The five limits in force in the project of ``scope`` (``permits.gas.*``)."""
    conn = uow.conn()
    project = project_of_scope(scope)
    found = {
        name: Decimal(str(value_of(conn, key, project=project))) for name, key in LIMIT_KEYS.items()
    }
    return rules.GasLimits(**found)


def _reading(value: str | None) -> Decimal | None:
    """A reading of the command (validated decimal text) as a number."""
    return None if value is None else Decimal(value)


def handle_record_gas_test(uow: UnitOfWork, cmd: RecordGasTest) -> CommandResult:
    """Record a test of a permit; suspend the permit when it fails and the permit is live."""
    require_project(cmd)
    cmd = correlated(cmd)
    at = common.now()
    permit = load_permit(uow, cmd.scope, cmd.permit, at)
    if permit.state not in TESTABLE:
        raise PermitStateError(
            f"a permit that is {permit.state} does not take RecordGasTest; "
            f"it needs {' or '.join(TESTABLE)}"
        )
    taken = at if cmd.taken_at is None else cmd.taken_at.astimezone(UTC)
    if taken > at:
        raise GasTestRuleError(MSG_FUTURE)
    result = rules.gas_result(
        gas_limits(uow, cmd.scope),
        o2=_reading(cmd.o2_pct),
        lel=_reading(cmd.lel_pct),
        h2s=_reading(cmd.h2s_ppm),
        co=_reading(cmd.co_ppm),
    )
    made = create_module_record(
        uow, cmd, record_type=GAS_TEST, title=f"Gas test of {permit.key}", key=None
    )
    done = append(
        uow,
        cmd,
        made.stream_id,
        GAS_TEST,
        [
            NewEvent(
                event_type=GAS_TEST_RECORDED,
                payload=silent(
                    made.stream_id,
                    {
                        "permit_id": permit.id,
                        "taken_at": iso_utc(taken),
                        "tester": cmd.actor,
                        "instrument_text": cmd.instrument_text,
                        "o2_pct": cmd.o2_pct,
                        "lel_pct": cmd.lel_pct,
                        "h2s_ppm": cmd.h2s_ppm,
                        "co_ppm": cmd.co_ppm,
                        "result": result,
                        "note": cmd.note,
                    },
                ),
            )
        ],
    )
    events = [*made.events, *done.events]
    needs = load_types()[str(permit.row["permit_type"])].needs_gas_test
    if result == "fail" and needs and permit.state in STOPPABLE:
        stopped = append(
            uow,
            cmd,
            permit.id,
            PERMIT,
            [
                NewEvent(
                    event_type=PERMIT_SUSPENDED,
                    payload=silent(
                        permit.id,
                        {"reason": MSG_SUSPENDED_BY_GAS, "gas_test_id": made.stream_id},
                    ),
                )
            ],
        )
        moved = move(uow, cmd, permit.id, T_SUSPEND)
        events += [*stopped.events, *moved.events]
    return CommandResult(
        stream_id=made.stream_id, key=made.key, version=done.new_version, events=events
    )


__all__ = ["handle_record_gas_test"]
