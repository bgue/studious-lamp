"""A small world for the settings tests: a database, some definitions, shortcuts to act and look."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core import settings as S
from tl_core.ledger import Event
from tl_core.settings.registry import load_definitions, platform_file, use_definitions
from tl_core.settings.types import EffectiveSetting, SettingDefinition
from tl_core.util import utcnow

P1 = "project:P1"
ALICE = "user:alice"
SRC = "test"


def custom(key: str, kind: str, default: Any, **extra: Any) -> SettingDefinition:
    return SettingDefinition.model_validate(
        {
            "key": key,
            "type": kind,
            "default": default,
            "description": "d",
            "scopes": ["platform", "company", "project"],
            "lockable": True,
            "since": "0.1.0",
            **extra,
        }
    )


#: definitions the tests use beside the platform file
EXTRA = [
    custom("t.limit", "int", 10, validation={"minimum": 0, "maximum": 100}),
    custom("t.advanced", "string", "a", risk="advanced"),
    custom("t.danger", "list", [], risk="dangerous"),
    custom("t.restart", "int", 1, effect="restart", scopes=["platform", "company"]),
    custom("t.secret", "string", "x", sensitivity="secret"),
    custom("t.fixed", "string", "x", lockable=False),
    custom("t.every", "duration", "5m", validation={"minimum": 10, "maximum": 86400}),
    custom(
        "ui.t.pref", "enum", "a", validation={"choices": ["a", "b"]}, scopes=["platform", "user"]
    ),
    custom("t.plain", "string", "x", scopes=["platform", "company", "project", "user"]),
]


@contextmanager
def definitions_in_force() -> Iterator[None]:
    """The platform file plus :data:`EXTRA`, for the length of a block."""
    with use_definitions([*load_definitions(platform_file()), *EXTRA]):
        yield


def future(hours: float = 1) -> datetime:
    return utcnow() + timedelta(hours=hours)


class World:
    def __init__(self, db: DbTarget) -> None:
        self.db = db
        create_schema(db)

    def factory(self, readonly: bool = False) -> Any:
        """``factory(readonly=...)`` as the proposals service expects it."""
        return open_uow(self.db, readonly=readonly)

    # --- acting -------------------------------------------------------------------------------

    def set(self, key: str, layer: str, value: Any, **kw: Any) -> EffectiveSetting:
        kw.setdefault("actor", ALICE)
        kw.setdefault("source", SRC)
        with open_uow(self.db) as uow:
            return S.set_setting(uow, key=key, layer=layer, value=value, **kw)

    def reset(self, key: str, layer: str, **kw: Any) -> EffectiveSetting:
        kw.setdefault("actor", ALICE)
        kw.setdefault("source", SRC)
        with open_uow(self.db) as uow:
            return S.reset_setting(uow, key=key, layer=layer, **kw)

    def lock(
        self, key: str, locked: bool = True, bounds: dict[str, Any] | None = None, **kw: Any
    ) -> EffectiveSetting:
        kw.setdefault("actor", ALICE)
        kw.setdefault("source", SRC)
        kw.setdefault("reason", "policy")
        with open_uow(self.db) as uow:
            return S.lock_setting(uow, key=key, locked=locked, bounds=bounds, **kw)

    def revert(self, key: str, layer: str, seq: int, **kw: Any) -> EffectiveSetting:
        kw.setdefault("actor", ALICE)
        kw.setdefault("source", SRC)
        with open_uow(self.db) as uow:
            return S.revert_setting(uow, key=key, layer=layer, seq=seq, **kw)

    # --- looking ------------------------------------------------------------------------------

    def get(self, key: str, **kw: Any) -> EffectiveSetting:
        with open_uow(self.db, readonly=True) as uow:
            return S.resolve(uow.conn(), key, **kw)

    def value(self, key: str, **kw: Any) -> Any:
        return self.get(key, **kw).value

    def history(self, key: str, **kw: Any) -> list[Any]:
        with open_uow(self.db, readonly=True) as uow:
            return S.history(uow.conn(), key, **kw)

    def events(self) -> list[Event]:
        with open_uow(self.db, readonly=True) as uow:
            return uow.ledger.read_after(0, limit=10_000)

    def head(self) -> int:
        with open_uow(self.db, readonly=True) as uow:
            return uow.ledger.head_seq()

    def rows(self, table: str) -> list[dict[str, Any]]:
        order = {"cur_setting": "seq", "cur_setting_lock": "key"}[table]
        with open_uow(self.db, readonly=True) as uow:
            found = uow.conn().execute(text(f"SELECT * FROM {table} ORDER BY {order}")).mappings()
            return [dict(row) for row in found]
