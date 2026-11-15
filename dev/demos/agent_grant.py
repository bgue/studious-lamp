"""Demo setup: give an agent an account and an explicit module ``user`` grant, as an admin would.

Since P2-X2-S1 an agent files a proposal only under an explicit ``GrantModuleRole`` ``user`` on the
scope's project; a derived account role does not count. Run ``uv run python dev/demos/agent_grant.py
DB AGENT PROJECT...`` (the agent as ``triage`` or ``agent:triage``; projects as ``P123`` or
``project:P123``), or call ``grant_agent``.
Idempotent. DB is a SQLite path or a postgresql:// URL. Dev ledgers only: it makes an
admin account ``demo-grants`` to act through, as the dev setup has no signed-in admin here.
"""

from __future__ import annotations

import sys

from tl_adapters.db import as_target, make_uow_factory
from tl_core.auth import accounts, queries
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.modules import load_modules

ADMIN = "demo-grants"


def _module(project: str) -> str:
    """``*`` on a project; on ``company`` a module has to name company-level roles (the first)."""
    if project != "company":
        return "*"
    return next(spec.name for spec in load_modules() if spec.company_roles)


def grant_agent(db: str, agent: str, projects: list[str]) -> None:
    name = agent.removeprefix("agent:")
    scopes = [p if p.startswith("project:") or p == "company" else f"project:{p}" for p in projects]
    factory = make_uow_factory(as_target(db))
    with factory() as uow:
        for username, kind, roles in ((ADMIN, "person", ["admin"]), (name, "agent", ["user"])):
            if queries.find_account(uow.conn(), username=username) is None:
                accounts.create_account(
                    uow, username=username, display_name=username, kind=kind, roles=roles,
                    password=None, by="svc:demo",
                )  # fmt: skip
        account = queries.find_account(uow.conn(), username=name)
        assert account is not None
        for project in scopes:
            grant_module_role(
                uow,
                GrantModuleRole(
                    actor=f"user:{ADMIN}", source="demo", scope="company",
                    account_id=account.account_id, project=project, module=_module(project),
                    role="user", reason="demo agent may file proposals",
                ),
            )  # fmt: skip
    factory.close()


if __name__ == "__main__":
    grant_agent(sys.argv[1], sys.argv[2], sys.argv[3:])
