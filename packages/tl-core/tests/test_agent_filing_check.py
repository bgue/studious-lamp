"""P2-X2-S1: filing needs the module ``user`` word on the scope; hidden equals missing."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, make_uow_factory, open_uow
from tl_core import confidentiality as cf
from tl_core.auth import accounts
from tl_core.auth.module_grants import (
    GrantModuleRole,
    RevokeModuleRole,
    grant_module_role,
    revoke_module_role,
)
from tl_core.modules import ModuleSpec, ProposableCommand, use_modules
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.proposals import propose, submit

SCOPE = "project:P1"
OTHER = "project:P2"
NEVER = "project:NEVER"
AGENT = "agent:bot"
ADMIN = "user:ada"
TOOL = "create_record"
MODULE_TOOL = "vault_create"


class VaultCreate(CreateRecord):
    """The module's own command: a core name may not be gated by a module (it is refused whole)."""


#: The command class and tool ``cmd`` and the ``do_*`` helpers use; a fixture switches them.
_ACTIVE: dict[str, object] = {"cls": CreateRecord, "tool": TOOL}


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    target = new_db()
    create_schema(target)
    return target


@pytest.fixture
def factory(db: DbTarget) -> Iterator[object]:
    made = make_uow_factory(db)
    try:
        yield made
    finally:
        made.dispose()


@pytest.fixture
def module_command() -> Iterator[None]:
    """A module that declares ``CreateRecord`` with the ``controller`` word."""
    spec = ModuleSpec(
        name="vault",
        record_types=frozenset(),
        projectors=lambda: [],
        command_words={"VaultCreate": "controller"},
        proposable=(
            ProposableCommand(MODULE_TOOL, VaultCreate, lambda uow, c: None, "controller"),  # type: ignore[arg-type,return-value]
        ),
    )
    _ACTIVE.update(cls=VaultCreate, tool=MODULE_TOOL)
    try:
        with use_modules([spec]):
            yield
    finally:
        _ACTIVE.update(cls=CreateRecord, tool=TOOL)


@pytest.fixture
def core_command() -> Iterator[None]:
    with use_modules([ModuleSpec(name="vault", record_types=frozenset(), projectors=lambda: [])]):
        yield


class World:
    def __init__(self, db: DbTarget) -> None:
        self.db = db
        self.ids: dict[str, str] = {}
        self.make("ada", ["admin"], "person")

    def make(self, name: str, roles: list[str], kind: str) -> None:
        with open_uow(self.db) as uow:
            view = accounts.create_account(
                uow, username=name, display_name=name, kind=kind,  # type: ignore[arg-type]
                roles=roles, password=None, by="user:root",
            )  # fmt: skip
        self.ids[name] = view.account_id

    def make_bot(self) -> None:
        """The agent's account: role ``user`` (derives the user word, grants nothing)."""
        self.make("bot", ["user"], "agent")

    def _cmd(self, cls: type[GrantModuleRole], project: str, module: str, role: str):  # type: ignore[no-untyped-def]
        return cls(
            actor=ADMIN, source="test", scope="company", account_id=self.ids["bot"],
            project=project, module=module, role=role, reason="test",
        )  # fmt: skip

    def grant(self, role: str, *, project: str = SCOPE, module: str = "vault") -> None:
        with open_uow(self.db) as uow:
            grant_module_role(uow, self._cmd(GrantModuleRole, project, module, role))

    def revoke(self, role: str, *, project: str = SCOPE, module: str = "vault") -> None:
        with open_uow(self.db) as uow:
            revoke_module_role(uow, self._cmd(RevokeModuleRole, project, module, role))  # type: ignore[arg-type]

    def count(self, sql: str) -> int:
        with open_uow(self.db, readonly=True) as uow:
            return int(uow.conn().execute(text(sql)).scalar_one())


@pytest.fixture
def world(db: DbTarget) -> World:
    return World(db)


def cmd(scope: str = SCOPE, *, key: str | None = None, rk: str = "R-1") -> CreateRecord:
    return _ACTIVE["cls"](  # type: ignore[no-any-return,operator]
        actor=AGENT, source="mcp:x", scope=scope, record_type="core.Record",
        title="A record", key=rk, idempotency_key=key,
    )  # fmt: skip


def do_submit(factory: object, c: CreateRecord, *, budget: int = 5, agent: str = AGENT):  # type: ignore[no-untyped-def]
    return submit(
        factory,  # type: ignore[arg-type]
        tool=str(_ACTIVE["tool"]), agent=agent, command=c, summary="Create a record", budget=budget,
    )  # fmt: skip


def do_propose(db: DbTarget, c: CreateRecord, *, agent: str = AGENT):  # type: ignore[no-untyped-def]
    with open_uow(db) as uow:
        return propose(
            uow, tool=str(_ACTIVE["tool"]), agent=agent, command=c, summary="Create a record"
        )


def refusal(
    db: DbTarget, factory: object, c: CreateRecord, how: str, *, agent: str = AGENT
) -> RecordNotFoundError:
    with pytest.raises(RecordNotFoundError) as caught:
        if how == "submit":
            do_submit(factory, c, agent=agent)
        else:
            do_propose(db, c, agent=agent)
    return caught.value


EVENTS = "SELECT COUNT(*) FROM events"
PROPOSALS = "SELECT COUNT(*) FROM cur_proposals"
KEYS = "SELECT COUNT(*) FROM idempotency_key"


def test_no_word_refused_user_files_read_only_refused(
    db: DbTarget, factory: object, world: World, module_command: None
) -> None:
    refusal(db, factory, cmd(), "submit")  # no account: holds nothing
    world.make_bot()
    world.grant("viewer")  # read only: the grant replaces the derived user role
    refusal(db, factory, cmd(), "submit")
    world.grant("user")
    world.revoke("viewer")
    assert do_submit(factory, cmd()).proposal_id


def test_refusal_equals_missing_scope_refusal(
    db: DbTarget, factory: object, world: World, module_command: None
) -> None:
    from tl_api.errors import body_for

    world.make_bot()
    world.grant("viewer")  # a real scope where the agent lacks the word
    real = refusal(db, factory, cmd(SCOPE), "propose")
    world.revoke("viewer")
    world.grant("user", project=OTHER)
    ghost = cmd(NEVER).model_copy(update={"actor": "agent:ghost"})  # no account, never-made scope
    never = refusal(db, factory, ghost, "propose", agent="agent:ghost")
    assert type(real) is type(never)
    assert str(real).replace(SCOPE, "X") == str(never).replace(NEVER, "X")
    for word in ("vault", "user", "controller", "needs", "access"):
        assert word not in str(real)
    got_real, got_never = body_for(real), body_for(never)
    assert got_real is not None and got_never is not None
    assert got_real[0] == got_never[0] == 404


@pytest.mark.parametrize("how", ["submit", "propose"])
def test_the_commands_own_word_is_not_needed_at_filing(
    db: DbTarget, factory: object, world: World, module_command: None, how: str
) -> None:
    world.make_bot()
    world.grant("viewer")  # replace the derived role, then hold exactly the user word
    world.grant("user")
    world.revoke("viewer")  # user word only; the command's word is controller
    got = do_submit(factory, cmd()) if how == "submit" else do_propose(db, cmd())
    assert got.proposal_id


@pytest.mark.parametrize("how", ["submit", "propose"])
def test_refusal_writes_nothing(
    db: DbTarget, factory: object, world: World, module_command: None, how: str
) -> None:
    events, keys = world.count(EVENTS), world.count(KEYS)
    refusal(db, factory, cmd(key="k-refused-1"), how)
    assert world.count(EVENTS) == events
    assert world.count(KEYS) == keys
    assert world.count(PROPOSALS) == 0  # no budget use


def test_replay_answers_after_the_word_is_revoked_a_new_key_is_refused(
    db: DbTarget, factory: object, world: World, module_command: None
) -> None:
    world.make_bot()
    world.grant("user")
    first = do_submit(factory, cmd(key="k-order-1"))
    world.revoke("user")
    world.grant("viewer")  # replaces the derived user role: the word is gone
    again = do_submit(factory, cmd(key="k-order-1"))
    assert again.proposal_id == first.proposal_id
    refusal(db, factory, cmd(key="k-order-2", rk="R-2"), "submit")
    assert world.count(PROPOSALS) == 1


@pytest.mark.parametrize("how", ["submit", "propose"])
def test_core_command_needs_any_module_role_on_the_scope(
    db: DbTarget, factory: object, world: World, core_command: None, how: str
) -> None:
    refused = refusal(db, factory, cmd(), how)
    assert str(refused) == str(refusal(db, factory, cmd(NEVER), how)).replace(NEVER, SCOPE)
    world.make_bot()
    world.grant("viewer")  # any module, any word
    got = do_submit(factory, cmd()) if how == "submit" else do_propose(db, cmd())
    assert got.proposal_id
    ghost = cmd(OTHER, rk="R-3").model_copy(update={"actor": "agent:ghost"})
    refusal(db, factory, ghost, how, agent="agent:ghost")  # no account, no role anywhere


def test_refusal_is_identical_for_readers_with_and_without_clearance(
    db: DbTarget, factory: object, world: World, module_command: None
) -> None:
    texts = []
    for level in (0, 1, 2, 3, 4):
        viewer = cf.Viewer(actor="user:v", level=level, account="user:v")
        with cf.use_viewer(viewer):
            texts.append(str(refusal(db, factory, cmd(), "submit")))
    assert len(set(texts)) == 1


@pytest.mark.parametrize("how", ["submit", "propose"])
def test_derived_user_role_alone_is_refused_module_command(
    db: DbTarget, factory: object, world: World, module_command: None, how: str
) -> None:
    world.make_bot()  # account role user derives the user word, but no explicit grant
    refusal(db, factory, cmd(), how)
    world.grant("user")  # an explicit grant files
    got = do_submit(factory, cmd()) if how == "submit" else do_propose(db, cmd())
    assert got.proposal_id


@pytest.mark.parametrize("how", ["submit", "propose"])
def test_derived_user_role_alone_is_refused_core_command(
    db: DbTarget, factory: object, world: World, core_command: None, how: str
) -> None:
    world.make_bot()
    refusal(db, factory, cmd(), how)
    world.grant("user", module="*")  # granted_all_modules counts
    got = do_submit(factory, cmd()) if how == "submit" else do_propose(db, cmd())
    assert got.proposal_id
