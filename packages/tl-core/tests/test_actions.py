"""``tl_core.actions.allowed_actions``: visibility first, agents get nothing, then the hook (S1).

A fake module, ``vault``, stands in for a real one: its ``Item`` carries a class and has a hook; its
``Bare`` has no hook. The hook is a spy, so a test can prove it is never called for a record the
viewer may not read.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import Connection, text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core import confidentiality as cf
from tl_core.actions import ActionOffer, Holds, Level, RecordActions, allowed_actions
from tl_core.ledger import Event
from tl_core.modules import ConfidentialSource, ModuleLoadError, ModuleSpec, use_modules
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import Command
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.records import create_module_record

FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures"
SCOPE = "project:P123"
ITEM, BARE = "vault.Item", "vault.Bare"
FAKE_ID = "01J000000000000000000000"

SOURCE = ConfidentialSource(
    record_types=frozenset({ITEM}),
    table="cur_vault_item",
    id_column="id",
    class_column="klass",
)
DDL = ["CREATE TABLE IF NOT EXISTS cur_vault_item (id TEXT PRIMARY KEY, klass TEXT)"]

USER = cf.Viewer(actor="user:ann", level=0, account="user:ann")
CONTROLLER = cf.Viewer(actor="user:ctl", level=1, account="user:ctl")


class VaultProjector:
    name = "vault"
    handles = frozenset({"Vault.Never"})

    def ddl(self, dialect: str) -> list[str]:
        return DDL

    def apply(self, conn: Connection, event: Event) -> None:
        return None

    def reset(self, conn: Connection) -> None:
        return None


class Spy:
    """The module's hook: records its calls, offers 'Close' to all and 'Seal' to a controller."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, conn: Connection, record_id: str, holds: Holds) -> list[ActionOffer]:
        self.calls.append(record_id)
        offers = [ActionOffer(command="CloseItem", label="Close")]
        if holds("controller"):
            offers.append(ActionOffer(command="SealItem", label="Seal"))
        return offers


@pytest.fixture
def spy() -> Spy:
    return Spy()


@pytest.fixture(autouse=True)
def fixture_schemas() -> Iterator[None]:
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        yield


@pytest.fixture(autouse=True)
def vault_module(spy: Spy) -> Iterator[None]:
    spec = ModuleSpec(
        name="vault",
        record_types=frozenset({ITEM, BARE}),
        projectors=lambda: [VaultProjector()],
        confidential=(SOURCE,),
        actions={ITEM: spy},
    )
    with use_modules([spec]):
        yield


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    target = new_db()
    create_schema(target)
    return target


def add(db: DbTarget, name: str, record_type: str, klass: str | None = None) -> str:
    with open_uow(db) as uow:
        made = create_module_record(
            uow,
            Command(actor="user:u", source="test", scope=SCOPE),
            record_type=record_type,
            title=f"SECRET-{name}",
            key=f"K-{name}",
        )
        if record_type == ITEM:
            uow.conn().execute(
                text("INSERT INTO cur_vault_item (id, klass) VALUES (:i, :k)"),
                {"i": made.stream_id, "k": klass},
            )
    return made.stream_id


def ask(
    db: DbTarget,
    record_id: str,
    *,
    viewer: cf.Viewer = USER,
    actor: str = "user:ann",
    level: Level = "user",
) -> RecordActions:
    ranks = ("user", "controller", "admin")

    def holds(wanted: Level) -> bool:
        return ranks.index(wanted) <= ranks.index(level)

    with cf.use_viewer(viewer), open_uow(db, readonly=True) as uow:
        return allowed_actions(uow, record_id, actor=actor, holds=holds)


def refusal(db: DbTarget, record_id: str, viewer: cf.Viewer = USER) -> str:
    with pytest.raises(RecordNotFoundError) as caught:
        ask(db, record_id, viewer=viewer)
    return str(caught.value)


def test_a_readable_record_gets_the_hooks_offers_for_what_the_caller_holds(
    db: DbTarget, spy: Spy
) -> None:
    item = add(db, "open", ITEM, "internal")
    plain = ask(db, item)
    assert plain.record_id == item
    assert [(a.command, a.label) for a in plain.actions] == [("CloseItem", "Close")]
    ctl = ask(db, item, viewer=CONTROLLER, actor="user:ctl", level="controller")
    assert [a.command for a in ctl.actions] == ["CloseItem", "SealItem"]
    assert spy.calls == [item, item]


def test_a_hidden_id_and_a_missing_id_give_the_identical_error(db: DbTarget) -> None:
    hidden = add(db, "restricted", ITEM, "restricted")
    unknown = add(db, "unknown-class", ITEM, "Confidential")
    messages = {
        refusal(db, hidden).replace(hidden, "X"),
        refusal(db, unknown).replace(unknown, "X"),
        refusal(db, FAKE_ID).replace(FAKE_ID, "X"),
    }
    assert messages == {"no record 'X'"}
    assert ask(db, hidden, viewer=CONTROLLER, level="controller").record_id == hidden


def test_the_hook_is_not_called_for_a_hidden_or_missing_record(db: DbTarget, spy: Spy) -> None:
    hidden = add(db, "restricted", ITEM, "restricted")
    refusal(db, hidden)
    refusal(db, FAKE_ID)
    assert spy.calls == []


def test_visibility_is_judged_before_the_agent_rule(db: DbTarget) -> None:
    hidden = add(db, "restricted", ITEM, "restricted")
    with pytest.raises(RecordNotFoundError):
        ask(db, hidden, actor="agent:bot")


def test_an_agent_gets_no_actions_whatever_it_holds(db: DbTarget, spy: Spy) -> None:
    item = add(db, "open", ITEM, "internal")
    got = ask(db, item, actor="agent:bot", level="admin")
    assert got.record_id == item and got.actions == []
    assert spy.calls == []


def test_a_type_with_no_hook_gets_no_actions(db: DbTarget, spy: Spy) -> None:
    bare = add(db, "bare", BARE)
    got = ask(db, bare, level="admin")
    assert got == RecordActions(record_id=bare, state=None, actions=[])
    assert spy.calls == []


def test_the_state_is_void_after_a_void_and_none_before_the_first_move(db: DbTarget) -> None:
    item = add(db, "open", ITEM, "internal")
    assert ask(db, item).state is None
    with open_uow(db) as uow:
        uow.conn().execute(text("UPDATE cur_core_record SET voided = :v"), {"v": True})
    assert ask(db, item).state == "Void"


def test_actions_may_only_name_a_record_type_the_module_owns() -> None:
    with pytest.raises(ModuleLoadError, match="actions names 'other.Thing'"):
        ModuleSpec(
            name="vault",
            record_types=frozenset({ITEM}),
            projectors=lambda: [],
            actions={"other.Thing": Spy()},
        )
