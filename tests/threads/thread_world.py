"""Helpers of the thread tests: a ledger with threads switched on and some records."""

from __future__ import annotations

from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core import settings
from tl_core.services.commands import CreateRecord
from tl_core.services.records import handle_create_record

P1 = "project:P123"


def thread_db(target: DbTarget) -> DbTarget:
    """An empty ledger with threads switched on for ``core.Record`` (company layer)."""
    create_schema(target)
    put_setting(target, "threads.enabled", True)
    put_setting(target, "threads.enabled_types", ["core.Record"])
    return target


def put_setting(db: DbTarget, key: str, value: object, layer: str = "company") -> None:
    with open_uow(db) as uow:
        settings.set_setting(uow, key=key, layer=layer, value=value, actor="user:a", source="t")


def make_record(
    db: DbTarget, key: str, *, scope: str = P1, actor: str = "user:creator", title: str = ""
) -> str:
    """A ``core.Record`` with this key; returns its id."""
    cmd = CreateRecord(
        actor=actor,
        source="test",
        scope=scope,
        record_type="core.Record",
        title=title or key,
        key=key,
    )
    with open_uow(db) as uow:
        return handle_create_record(uow, cmd).stream_id


# --- the typed command table as a CommandRunner (the real table of tl_api) --------------------

from collections.abc import Callable, Iterator  # noqa: E402
from contextlib import contextmanager  # noqa: E402
from typing import Any  # noqa: E402

from tl_api.thread_runner import TableRunner as ApiTableRunner  # noqa: E402
from tl_core.auth.types import AccountKind  # noqa: E402
from tl_core.integration.contract import Access  # noqa: E402
from tl_core.numbering.config import (  # noqa: E402
    NumberingPattern,
    NumberingRegistry,
    use_numbering,
)
from tl_core.workflow.definition import WorkflowDefinition  # noqa: E402
from tl_core.workflow.loader import WorkflowRegistry  # noqa: E402
from tl_core.workflow.provider import use_workflows  # noqa: E402

TableRunner = ApiTableRunner


def everyone(level: Access) -> bool:
    return True


def only_users(level: Access) -> bool:
    return level == "user"


FLOW: dict[str, Any] = {
    "id": "t.thread",
    "version": 1,
    "record_type": "core.Record",
    "initial_state": "Draft",
    "states": [
        {"name": "Draft"},
        {"name": "Issued", "label": "Issued for use"},
        {"name": "Closed"},
    ],
    "transitions": [
        {"name": "issue", "from": ["Draft"], "to": "Issued"},
        {
            "name": "close",
            "from": ["Issued"],
            "to": "Closed",
            "guards": [{"kind": "roles", "any_of": ["boss"]}],
        },
        {"name": "reopen", "from": ["Closed", "Issued"], "to": "Draft"},
    ],
}


@contextmanager
def planning_world() -> Iterator[None]:
    """A numbering pattern for ``core.Record`` and one small workflow, for the block."""
    pattern = NumberingPattern.model_validate(
        {
            "id": "core.Record",
            "record_type": "core.Record",
            "scope": "project:*",
            "template": "{project}-{type}-{seq:4}",
            "type_code": "REC",
        }
    )
    with (
        use_numbering(NumberingRegistry([pattern])),
        use_workflows(WorkflowRegistry([WorkflowDefinition.model_validate(FLOW)])),
    ):
        yield


def make_person(db: DbTarget, username: str, kind: AccountKind = "person") -> None:
    """An active account, so ``@username`` resolves."""
    from tl_core.auth import accounts

    with open_uow(db) as uow:
        accounts.create_account(
            uow,
            username=username,
            display_name=username.title(),
            kind=kind,
            roles=["user"],
            password=None,
            by="user:a",
        )


Holds = Callable[[Access], bool]


def run_target(
    db: DbTarget, target: Any, record_id: str, line: str, *, actor: str = "user:a"
) -> Any:
    """What ``target.plan`` returns for ``line`` on a record: the way the planner calls it."""
    from tl_core.threads.contract import DispatchContext, ParsedDispatch
    from tl_core.threads.parser import CommandLineParser
    from tl_core.threads.visibility import readable_record

    parsed = CommandLineParser().parse(line)
    assert isinstance(parsed, ParsedDispatch), parsed
    with open_uow(db, readonly=True) as uow:
        record = readable_record(uow, record_id, actor=actor)
        context = DispatchContext(
            record=record.ref(),
            record_status=record.status,
            scope=record.scope,
            actor=actor,
            today="2026-10-17",
            now="2026-10-17T09:00:00+00:00",
        )
        return target.plan(uow, context, parsed)
