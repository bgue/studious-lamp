"""An agent is refused the approve, schedule and close commands, whatever grant it holds.

The AGENT_MAY_NOT pattern (``packages/tl-api/tests/test_auth_review.py``): a command is closed to
agents until it is listed as allowed. An agent may only propose (ADR-0027). Here the agent is the
approver's own account, so the grant is the same one a person holds; the refusal is the kind.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from req_world import SCOPE, World
from tl_adapters.db import open_uow
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import holder_for_actor, require_command_access
from tl_core.util import new_ulid
from tl_mod_requisitions.commands import ApproveRequisition, CloseWorkOrder, ScheduleWorkOrder


def test_an_agent_holding_the_approver_grant_may_not_approve_schedule_or_close(
    world: World,
) -> None:
    rid = world.raise_labor()
    wid = new_ulid()  # the access check reads the command word, not the record
    commands = [
        ApproveRequisition(
            actor="user:sue",
            source="test",
            scope=SCOPE,
            requisition=rid,
            expected_version=world.version(rid),
        ),
        ScheduleWorkOrder(
            actor="user:sue",
            source="test",
            scope=SCOPE,
            work_order=wid,
            expected_version=1,
            planned_start="2026-11-02",
            planned_finish="2026-11-13",
        ),
        CloseWorkOrder(
            actor="user:sue", source="test", scope=SCOPE, work_order=wid, expected_version=1
        ),
    ]
    with open_uow(world.db) as uow:
        conn = uow.conn()
        person = holder_for_actor(conn, "user:sue", dev_file=False)
        agent = replace(person, actor="agent:sue", kind="agent")
        for cmd in commands:
            require_command_access(conn, cmd, holder=person)  # the person may run it
            with pytest.raises(ForbiddenError):
                require_command_access(conn, cmd, holder=agent)
    assert world.state(rid) == "Requested"
