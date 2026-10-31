"""``allowed_actions`` with a holder: the hook sees the module roles at the record's own scope.

A stand-in module, ``vault``, owns ``vault.Item``; its hook offers ``CloseItem`` to a holder of the
word ``user``, ``SealItem`` to ``controller`` and ``RetireItem`` to ``admin``. Records live in two
projects. Accounts and grants are real (the ledger, the projection, the resolver); only the module
is a stand-in. An offer must never be one the command's endpoint would refuse for lack of the word.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import Connection, text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core import confidentiality as cf
from tl_core.actions import ActionOffer, Holds, Level, allowed_actions
from tl_core.auth import accounts
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.module_roles import Holder, holder_for_actor
from tl_core.ledger import Event
from tl_core.modules import ConfidentialSource, ModuleSpec, use_modules
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import Command
from tl_core.services.records import create_module_record

FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures"
P1, P2 = "project:P1", "project:P2"
ITEM = "vault.Item"
SOURCE = ConfidentialSource(
    record_types=frozenset({ITEM}), table="cur_vault_item", id_column="id", class_column="klass"
)
DDL = ["CREATE TABLE IF NOT EXISTS cur_vault_item (id TEXT PRIMARY KEY, klass TEXT)"]
VIEWER = cf.Viewer(actor="user:ann", level=0, account="user:ann")


class VaultProjector:
    name = "vault"
    handles = frozenset({"Vault.Never"})

    def ddl(self, dialect: str) -> list[str]:
        return DDL

    def apply(self, conn: Connection, event: Event) -> None:
        return None

    def reset(self, conn: Connection) -> None:
        return None


def hook(conn: Connection, record_id: str, holds: Holds) -> list[ActionOffer]:
    offers: list[ActionOffer] = []
    for level, command in (
        ("user", "CloseItem"),
        ("controller", "SealItem"),
        ("admin", "RetireItem"),
    ):
        if holds(level):  # type: ignore[arg-type]
            offers.append(ActionOffer(command=command, label=command))
    return offers


@pytest.fixture(autouse=True)
def fixture_schemas() -> Iterator[None]:
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        yield


@pytest.fixture(autouse=True)
def vault_module() -> Iterator[None]:
    spec = ModuleSpec(
        name="vault",
        record_types=frozenset({ITEM}),
        projectors=lambda: [VaultProjector()],
        confidential=(SOURCE,),
        actions={ITEM: hook},
    )
    other = ModuleSpec(name="other", record_types=frozenset(), projectors=lambda: [])
    with use_modules([spec, other]):
        yield


class World:
    def __init__(self, db: DbTarget) -> None:
        self.db = db
        self.ids: dict[str, str] = {}
        for name, roles, kind in (
            ("ada", ("admin",), "person"),
            ("ann", ("user",), "person"),
            ("dora", ("document_controller",), "person"),
            ("bot", ("user",), "agent"),
        ):
            with open_uow(db) as uow:
                view = accounts.create_account(
                    uow, username=name, display_name=name, kind=kind,  # type: ignore[arg-type]
                    roles=list(roles), password=None, by="user:root",
                )  # fmt: skip
            self.ids[name] = view.account_id
        self.items = {P1: self.add(P1), P2: self.add(P2)}

    def add(self, scope: str) -> str:
        with open_uow(self.db) as uow:
            made = create_module_record(
                uow,
                Command(actor="user:ann", source="test", scope=scope),
                record_type=ITEM,
                title=f"item {scope}",
                key=f"K-{scope}",
            )
            uow.conn().execute(
                text("INSERT INTO cur_vault_item (id, klass) VALUES (:i, 'internal')"),
                {"i": made.stream_id},
            )
        return made.stream_id

    def grant(self, who: str, project: str, module: str, role: str) -> None:
        with open_uow(self.db) as uow:
            grant_module_role(
                uow,
                GrantModuleRole(
                    actor="user:ada", source="test", scope="company", account_id=self.ids[who],
                    project=project, module=module, role=role, reason="test",
                ),
            )  # fmt: skip

    def ask(
        self, who: str, scope: str, *, base: Level | None = None, holder: bool = True
    ) -> list[str]:
        """The commands offered to ``who`` on the item of ``scope``; ``base`` is the level the
        entry point's own ``holds`` gives (``admin`` only for an admin)."""
        actor = f"agent:{who}" if who == "bot" else f"user:{who}"
        ranks = ("user", "controller", "admin")
        level = base or ("admin" if who == "ada" else "user")

        def holds(wanted: Level) -> bool:
            return ranks.index(wanted) <= ranks.index(level)

        with cf.use_viewer(VIEWER), open_uow(self.db, readonly=True) as uow:
            who_holds: Holder | None = holder_for_actor(uow.conn(), actor) if holder else None
            got = allowed_actions(
                uow, self.items[scope], actor=actor, holds=holds, holder=who_holds
            )
        return [a.command for a in got.actions]


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    target = new_db()
    create_schema(target)
    return target


@pytest.fixture
def world(db: DbTarget) -> World:
    return World(db)


def test_a_user_with_no_grant_is_offered_the_user_acts_and_not_the_controlling_ones(
    world: World,
) -> None:
    for scope in (P1, P2):
        assert world.ask("ann", scope) == ["CloseItem"]


def test_a_superuser_grant_offers_the_controlling_act_on_that_project_only(world: World) -> None:
    world.grant("ann", P1, "vault", "superuser")
    assert world.ask("ann", P1) == ["CloseItem", "SealItem"]
    assert world.ask("ann", P2) == ["CloseItem"]


def test_a_viewer_grant_lowers_the_offer_to_nothing_on_that_project(world: World) -> None:
    world.grant("ann", P2, "vault", "viewer")
    assert world.ask("ann", P2) == []
    assert world.ask("ann", P1) == ["CloseItem"]


def test_a_grant_for_another_module_does_not_change_the_offer(world: World) -> None:
    world.grant("ann", P1, "other", "superuser")
    world.grant("ann", P2, "other", "viewer")
    assert world.ask("ann", P1) == ["CloseItem"] == world.ask("ann", P2)


def test_an_all_modules_grant_applies_to_the_module(world: World) -> None:
    world.grant("ann", P1, "*", "superuser")
    assert world.ask("ann", P1) == ["CloseItem", "SealItem"]


def test_the_admin_word_comes_from_the_entry_point_and_never_from_the_table(
    world: World,
) -> None:
    world.grant("ann", P1, "vault", "superuser")
    assert "RetireItem" not in world.ask("ann", P1)  # superuser holds no admin word
    assert world.ask("ada", P1) == ["CloseItem", "SealItem", "RetireItem"]
    # the base says "not admin" for an admin account: the offer follows the base
    assert world.ask("ada", P1, base="controller") == ["CloseItem", "SealItem"]


def test_the_document_controller_is_offered_the_controlling_act_only_where_it_derives_it(
    world: World,
) -> None:
    # `vault` is none of the controller's three modules, so it derives `user` there
    assert world.ask("dora", P1) == ["CloseItem"]


def test_an_agent_is_offered_nothing_even_with_a_holder(world: World) -> None:
    world.grant("bot", P1, "vault", "user")
    assert world.ask("bot", P1) == []


def test_without_a_holder_the_hook_sees_the_entry_points_holds_unchanged(world: World) -> None:
    world.grant("ann", P2, "vault", "viewer")
    # no holder: the grant is not consulted, the base decides (the pre-ADR-0021 behaviour)
    assert world.ask("ann", P2, holder=False) == ["CloseItem"]
    assert world.ask("ann", P1, base="controller", holder=False) == ["CloseItem", "SealItem"]
