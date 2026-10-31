"""Helpers for the module-role tests: a world of accounts over a real ledger and the grant verbs.

The ``World`` of ``tests/auth/authworld.py`` is reused. ``conftest.py`` next to this file puts both
directories on ``sys.path`` (pytest runs in importlib mode). Do not add ``__init__.py`` here.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_core.auth.module_grants import (
    GrantModuleRole,
    ModuleRoleResult,
    RevokeModuleRole,
    grant_module_role,
    revoke_module_role,
)
from tl_core.auth.module_roles import EffectiveRoles, Holder, effective_roles, holder_for_actor
from tl_core.auth.projector import account_stream_id
from tl_core.auth.types import AccountKind
from tl_core.ledger import NewEvent
from tl_core.modules import ModuleSpec

_AUTH = str(Path(__file__).resolve().parents[4] / "tests" / "auth")
if _AUTH not in sys.path:
    sys.path.insert(0, _AUTH)

from authworld import MovingClock, World  # noqa: E402

__all__ = ["MovingClock", "P1", "P2", "Roles", "World", "spec"]

P1 = "project:P1"
P2 = "project:P2"


class Roles:
    """A world plus the verbs the module-role tests keep repeating."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.ids: dict[str, str] = {}
        self.ada = self.person("ada", ("admin",))

    def person(
        self, name: str, roles: tuple[str, ...] = ("user",), kind: AccountKind = "person"
    ) -> str:
        view = self.world.create(name, roles=roles, kind=kind)
        self.ids[name] = view.account_id
        return view.account_id

    def command(
        self, cls: type[Any], who: str, project: str, module: str, role: str, by: str
    ) -> Any:
        return cls(
            actor=by,
            source="test",
            scope="company",
            account_id=self.ids.get(who, who),
            project=project,
            module=module,
            role=role,
            reason="test",
        )

    def grant(
        self, who: str, project: str, module: str, role: str, by: str = "user:ada"
    ) -> ModuleRoleResult:
        cmd = self.command(GrantModuleRole, who, project, module, role, by)
        with self.world.factory() as uow:
            return grant_module_role(uow, cmd)

    def revoke(
        self, who: str, project: str, module: str, role: str, by: str = "user:ada"
    ) -> ModuleRoleResult:
        cmd = self.command(RevokeModuleRole, who, project, module, role, by)
        with self.world.factory() as uow:
            return revoke_module_role(uow, cmd)

    def resolve(
        self, actor: str, scope: str, module: str, holder: Holder | None = None
    ) -> EffectiveRoles:
        with self.world.factory(readonly=True) as uow:
            conn = uow.conn()
            who = holder if holder is not None else holder_for_actor(conn, actor)
            return effective_roles(conn, who, scope=scope, module=module)

    def raw_grant(self, who: str, project: str, module: str, role: str) -> None:
        """A grant event appended past the command (the resolver must cap whatever the ledger holds)."""
        with self.world.factory() as uow:
            version = int(
                uow.conn()
                .execute(
                    text("SELECT version FROM cur_account WHERE account_id = :a"),
                    {"a": self.ids[who]},
                )
                .scalar_one()
            )
            uow.append(
                stream_id=account_stream_id(self.ids[who]),
                stream_type="core.Account",
                scope="company",
                expected_version=version,
                actor="user:ada",
                source="test",
                correlation_id="c" * 26,
                events=[
                    NewEvent(
                        event_type="Account.ModuleRoleGranted",
                        payload={
                            "account_id": self.ids[who],
                            "project": project,
                            "module": module,
                            "role": role,
                            "reason": "raw",
                        },
                    )
                ],
            )

    def count(self, sql: str, **params: Any) -> int:
        with self.world.factory(readonly=True) as uow:
            return int(uow.conn().execute(text(sql), params).scalar_one())


def spec(
    name: str, *, company_roles: bool = False, words: dict[str, str] | None = None
) -> ModuleSpec:
    """A stand-in module for ``use_modules``: no records, no projectors, the given command words."""
    return ModuleSpec(
        name=name,
        record_types=frozenset(),
        projectors=lambda: [],
        command_words=words or {},
        company_roles=company_roles,
    )
