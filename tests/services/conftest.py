"""Shared fixture for the service tests: an agent that files needs an account and an explicit grant.

P2-X2 S1 (ADR-0027 F1): an agent files only where an admin granted it a module role; a role derived
from the account role does not count. One helper here, not a copy per test file.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from tl_core.auth import accounts
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.queries import find_account
from tl_core.modules import load_modules
from tl_core.uow import UnitOfWork

# helper modules beside the tests (ip_rules, test_module_conformance) import by bare name
# under importlib mode, whatever file pytest collects first
sys.path.insert(0, str(Path(__file__).resolve().parent))

PROJECTS = ("project:P123", "project:P1", "project:P2", "project:P999")


def _grant_filing(uow: UnitOfWork, name: str, projects: tuple[str, ...] = PROJECTS) -> None:
    """The agent's account (role user) and an explicit ``user`` grant (P2-X2 S1).

    An agent files only where an admin granted it a module role; a role derived from the account
    role does not count."""
    conn = uow.conn()
    view = find_account(conn, username=name)
    if view is None:
        view = accounts.create_account(
            uow, username=name, display_name=name, kind="agent",
            roles=["user"], password=None, by="svc:test",
        )  # fmt: skip
    if find_account(conn, username="gadmin") is None:
        accounts.create_account(
            uow, username="gadmin", display_name="gadmin", kind="person",
            roles=["admin"], password=None, by="svc:test",
        )  # fmt: skip
    targets = [(p, "*") for p in projects]
    targets += [("company", s.name) for s in load_modules() if s.company_roles][:1]
    for project, module in targets:
        grant_module_role(
            uow,
            GrantModuleRole(
                actor="user:gadmin", source="test", scope="company", account_id=view.account_id,
                project=project, module=module, role="user", reason="test",
            ),
        )  # fmt: skip


@pytest.fixture
def grant_filing() -> Callable[..., None]:
    """``grant_filing(uow, name, projects=PROJECTS)``: the agent account and its grant."""
    return _grant_filing
