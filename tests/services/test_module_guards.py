"""State guards, the life of a link and reserved names at the module seam (ADR-0010 addendum).

A fake module stands in for a real one: ``fake.Thing`` allows the link commands, and its guard
refuses links from a Thing whose key starts with ``LOCKED``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core.ledger import Event
from tl_core.modules import ModuleLoadError, ModuleSpec, require_generic, use_modules
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import Command, CreateRecord
from tl_core.services.errors import (
    ReservedKeyError,
    UnsupportedRecordTypeError,
)
from tl_core.services.links import (
    AddLink,
    FlagLink,
    RetractLink,
    SuggestLink,
    handle_add_link,
    handle_flag_link,
    handle_retract_link,
    handle_suggest_link,
)
from tl_core.services.records import create_module_record, handle_create_record

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures"
SCOPE = "project:P123"
THING = "fake.Thing"
BASE: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": SCOPE}


class FakeProjector:
    name = "fake_thing"
    handles = frozenset({"Thing.Defined"})

    def ddl(self, dialect: str) -> list[str]:
        return []

    def apply(self, conn: Connection, event: Event) -> None:
        return None

    def reset(self, conn: Connection) -> None:
        return None


def locked_things_take_no_links(conn: Connection, record_id: str, slot: str | None) -> None:
    key = conn.execute(
        text("SELECT key FROM cur_core_record WHERE id = :i"), {"i": record_id}
    ).scalar_one()
    if str(key).startswith("LOCKED"):
        raise UnsupportedRecordTypeError(f"{key} is locked")


LINK_COMMANDS = frozenset({"AddLink", "SuggestLink", "FlagLink", "RetractLink"})


def spec(commands: frozenset[str] = LINK_COMMANDS) -> ModuleSpec:
    return ModuleSpec(
        name="fake",
        record_types=frozenset({THING}),
        projectors=lambda: [FakeProjector()],
        generic_commands={THING: commands},
        generic_guards={(THING, "AddLink"): locked_things_take_no_links},
    )


@pytest.fixture(autouse=True)
def fixture_schemas() -> Iterator[None]:
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        yield


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    target = new_db()
    create_schema(target)
    return target


def thing(db: DbTarget, key: str) -> str:
    with open_uow(db) as uow:
        made = create_module_record(uow, Command(**BASE), record_type=THING, title=key, key=key)
    return made.stream_id


def plain(db: DbTarget, key: str) -> str:
    with open_uow(db) as uow:
        made = handle_create_record(
            uow, CreateRecord(**BASE, record_type="core.Record", title=key, key=key)
        )
    return made.stream_id


def test_a_guard_sees_the_record_and_the_slot_and_runs_after_the_allow_list(db: DbTarget) -> None:
    seen: list[tuple[str, str | None]] = []

    def watch(conn: Connection, record_id: str, slot: str | None) -> None:
        seen.append((record_id, slot))

    with use_modules(
        [
            ModuleSpec(
                name="fake",
                record_types=frozenset({THING}),
                projectors=lambda: [FakeProjector()],
                generic_commands={THING: frozenset({"AttachFile"})},
                generic_guards={(THING, "AttachFile"): watch},
            )
        ]
    ):
        record = thing(db, "T-1")
        with open_uow(db, readonly=True) as uow:
            require_generic(uow.conn(), THING, "AttachFile", record, slot="pdf")
            with pytest.raises(UnsupportedRecordTypeError, match="cannot change"):
                require_generic(uow.conn(), THING, "UpdateRecord", record)  # not allowed at all
            require_generic(uow.conn(), "core.Record", "AttachFile", "anything")  # not a module's
    assert seen == [(record, "pdf")]


def test_a_spec_cannot_guard_what_it_does_not_own() -> None:
    for key in ((THING, "NotACommand"), ("other.Thing", "AddLink")):
        with pytest.raises(ModuleLoadError, match="generic_guards"):
            ModuleSpec(
                name="fake",
                record_types=frozenset({THING}),
                projectors=lambda: [],
                generic_guards={key: locked_things_take_no_links},
            )


def test_a_link_from_a_record_is_refused_by_its_guard_in_one_state_and_not_in_another(
    db: DbTarget,
) -> None:
    with use_modules([spec()]):
        open_one, locked = thing(db, "OPEN-1"), thing(db, "LOCKED-1")
        target = plain(db, "P-1")
        with open_uow(db) as uow:
            handle_add_link(
                uow, AddLink(**BASE, from_id=open_one, to_id=target, relation="references")
            )
        with (
            open_uow(db) as uow,
            pytest.raises(UnsupportedRecordTypeError, match="LOCKED-1 is locked"),
        ):
            handle_add_link(
                uow, AddLink(**BASE, from_id=locked, to_id=target, relation="references")
            )
        # the guard is keyed by command: a suggestion is not guarded here
        with open_uow(db) as uow:
            handle_suggest_link(
                uow, SuggestLink(**BASE, from_id=locked, to_id=target, relation="references")
            )


def test_the_life_of_a_link_follows_the_allow_list_of_the_record_it_starts_at(db: DbTarget) -> None:
    with use_modules([spec()]):
        mine = thing(db, "OPEN-1")
        target = plain(db, "P-1")
        link = _link(db, mine, target)
        with open_uow(db) as uow:
            handle_flag_link(uow, FlagLink(**BASE, link_id=link, status="stale", reason="x"))
    with use_modules([spec(frozenset({"AddLink"}))]):
        link2 = _link(db, mine, plain(db, "P-2"), by_module=True)
        with (
            open_uow(db) as uow,
            pytest.raises(UnsupportedRecordTypeError, match="FlagLink cannot"),
        ):
            handle_flag_link(uow, FlagLink(**BASE, link_id=link2, status="stale", reason="x"))
        with open_uow(db) as uow, pytest.raises(UnsupportedRecordTypeError, match="RetractLink"):
            handle_retract_link(uow, RetractLink(**BASE, link_id=link2, reason="x"))
        with open_uow(db) as uow:  # the module itself may
            handle_retract_link(uow, RetractLink(**BASE, link_id=link2, reason="x"), by_module=True)


def _link(db: DbTarget, from_id: str, to_id: str, *, by_module: bool = False, **more: Any) -> str:
    with open_uow(db) as uow:
        made = handle_add_link(
            uow,
            AddLink(**BASE, from_id=from_id, to_id=to_id, relation="references", **more),
            by_module=by_module,
        )
    return made.stream_id


def test_a_link_a_module_wrote_by_rule_is_flagged_and_retracted_only_by_the_module(
    db: DbTarget,
) -> None:
    with use_modules([spec()]):
        mine = thing(db, "OPEN-1")
        by_rule = _link(db, mine, plain(db, "P-1"), link_source="rule")
        by_hand = _link(db, mine, plain(db, "P-2"))
        for command, handler, extra in (
            ("FlagLink", handle_flag_link, {"status": "stale", "reason": "x"}),
            ("RetractLink", handle_retract_link, {"reason": "x"}),
        ):
            cls: Any = FlagLink if command == "FlagLink" else RetractLink
            with (
                open_uow(db) as uow,
                pytest.raises(UnsupportedRecordTypeError, match="written by a rule"),
            ):
                handler(uow, cls(**BASE, link_id=by_rule, **extra))
        with open_uow(db) as uow:  # a link made by hand is the person's
            handle_flag_link(uow, FlagLink(**BASE, link_id=by_hand, status="stale", reason="x"))
        with open_uow(db) as uow:  # and the module may flag its own rule's link
            handle_flag_link(
                uow,
                FlagLink(**BASE, link_id=by_rule, status="stale", reason="x"),
                by_module=True,
            )


def test_a_rule_link_between_core_records_is_not_reserved(db: DbTarget) -> None:
    with use_modules([spec()]):
        link = _link(db, plain(db, "P-1"), plain(db, "P-2"), link_source="rule")
        with open_uow(db) as uow:
            handle_flag_link(uow, FlagLink(**BASE, link_id=link, status="stale", reason="x"))


def test_the_supersedes_relation_onto_a_module_record_is_the_modules(db: DbTarget) -> None:
    with use_modules([spec()]):
        old, other = thing(db, "OPEN-1"), plain(db, "P-1")
        newer = plain(db, "P-2")
        pairs: list[tuple[Any, Any]] = [
            (AddLink, handle_add_link),
            (SuggestLink, handle_suggest_link),
        ]
        for cls, handler in pairs:
            with open_uow(db) as uow, pytest.raises(UnsupportedRecordTypeError, match="supersedes"):
                handler(uow, cls(**BASE, from_id=newer, to_id=old, relation="supersedes"))
        # between core records, or made by the module, it is allowed
        with open_uow(db) as uow:
            handle_add_link(uow, AddLink(**BASE, from_id=newer, to_id=other, relation="supersedes"))
        with open_uow(db) as uow:
            handle_add_link(
                uow,
                AddLink(**BASE, from_id=newer, to_id=old, relation="supersedes"),
                by_module=True,
            )


@pytest.mark.parametrize("key", ["ISO-1234@A", "A/B", "@", "/x"])
def test_a_typed_key_of_a_generic_record_cannot_hold_the_characters_modules_use(
    db: DbTarget, key: str
) -> None:
    with open_uow(db) as uow, pytest.raises(ReservedKeyError, match="'@' or '/'"):
        handle_create_record(
            uow, CreateRecord(**BASE, record_type="core.Record", title="t", key=key)
        )
    plain(db, "ISO-1234-A")  # a hyphen is fine
