"""ItemMasterProjector and ProjectItemProjector: the item library and the project's copies.

``ItemMaster.Defined`` inserts the library row; ``Revised`` changes the fields it carries (only
those that changed are present) and makes the project's copies follow (``category``, ``uom`` and
``consumable`` of every ``cur_materials_project_item`` row of the item); ``Retired`` sets the flag.
``ProjectItem.Defined`` inserts a copy. Deterministic: the rows depend only on the stream's events.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_materials.names import (
    ITEM_DEFINED,
    ITEM_MASTER_TABLE,
    ITEM_MASTER_VIEW,
    ITEM_RETIRED,
    ITEM_REVISED,
    PROJECT_ITEM_DEFINED,
    PROJECT_ITEM_TABLE,
    PROJECT_ITEM_VIEW,
)
from tl_mod_materials.projectors._common import ddl_for, require_row, touch_record

_INSERT_MASTER = text(
    f"INSERT INTO {ITEM_MASTER_TABLE} (id, scope, code, category, base_uom, size_text, "
    "rating_text, material_code, consumable, retired, last_seq) VALUES (:id, :scope, :code, "
    ":category, :base_uom, :size_text, :rating_text, :material_code, :consumable, :retired, "
    ":last_seq)"
)
#: Revised fields of the master and the column each one moves.
_MASTER_FIELDS = (
    "category",
    "base_uom",
    "size_text",
    "rating_text",
    "material_code",
    "consumable",
)
_RETIRE = text(
    f"UPDATE {ITEM_MASTER_TABLE} SET retired = :retired, last_seq = :last_seq WHERE id = :id"
)
_FOLLOW = text(
    f"UPDATE {PROJECT_ITEM_TABLE} SET category = :category, uom = :uom, consumable = :consumable, "
    "last_seq = :last_seq WHERE item_master_id = :id"
)
_MASTER_COPY = text(
    f"SELECT category, base_uom, consumable FROM {ITEM_MASTER_TABLE} WHERE id = :id"
)
_INSERT_COPY = text(
    f"INSERT INTO {PROJECT_ITEM_TABLE} (id, scope, item_master_id, category, uom, consumable, "
    "last_seq) VALUES (:id, :scope, :item_master_id, :category, :uom, :consumable, :last_seq)"
)


class ItemMasterProjector:
    name = "materials_item_master"
    handles = frozenset({ITEM_DEFINED, ITEM_REVISED, ITEM_RETIRED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(ITEM_MASTER_TABLE, dialect) + ddl_for(ITEM_MASTER_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == ITEM_DEFINED:
            conn.execute(
                _INSERT_MASTER,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "code": payload["code"],
                    "category": payload["category"],
                    "base_uom": payload["base_uom"],
                    "size_text": payload.get("size_text"),
                    "rating_text": payload.get("rating_text"),
                    "material_code": payload.get("material_code"),
                    "consumable": bool(payload["consumable"]),
                    "retired": False,
                    "last_seq": event.seq,
                },
            )
        elif kind == ITEM_REVISED:
            changed = [f for f in _MASTER_FIELDS if f in payload]
            if changed:
                sets = ", ".join(f"{f} = :{f}" for f in changed)
                params: dict[str, Any] = {f: payload[f] for f in changed}
                if "consumable" in params:
                    params["consumable"] = bool(params["consumable"])
                params.update({"id": event.stream_id, "last_seq": event.seq})
                done = conn.execute(
                    text(
                        f"UPDATE {ITEM_MASTER_TABLE} SET {sets}, last_seq = :last_seq "
                        "WHERE id = :id"
                    ),
                    params,
                )
                require_row(done.rowcount, ITEM_MASTER_TABLE, event)
                self._follow(conn, event)
        elif kind == ITEM_RETIRED:
            done = conn.execute(
                _RETIRE, {"id": event.stream_id, "retired": True, "last_seq": event.seq}
            )
            require_row(done.rowcount, ITEM_MASTER_TABLE, event)
        else:
            raise ValueError(f"ItemMasterProjector cannot apply event type: {kind}")
        touch_record(conn, event)

    @staticmethod
    def _follow(conn: Connection, event: Event) -> None:
        """The project copies take the master's category, unit and consumable flag."""
        master = conn.execute(_MASTER_COPY, {"id": event.stream_id}).one()
        conn.execute(
            _FOLLOW,
            {
                "id": event.stream_id,
                "category": master.category,
                "uom": master.base_uom,
                "consumable": bool(master.consumable),
                "last_seq": event.seq,
            },
        )

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {ITEM_MASTER_TABLE}"))


class ProjectItemProjector:
    name = "materials_project_item"
    handles = frozenset({PROJECT_ITEM_DEFINED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(PROJECT_ITEM_TABLE, dialect) + ddl_for(PROJECT_ITEM_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type != PROJECT_ITEM_DEFINED:
            raise ValueError(f"ProjectItemProjector cannot apply event type: {event.event_type}")
        payload: dict[str, Any] = event.payload
        conn.execute(
            _INSERT_COPY,
            {
                "id": event.stream_id,
                "scope": event.scope,
                "item_master_id": payload["item_master_id"],
                "category": payload["category"],
                "uom": payload["uom"],
                "consumable": bool(payload["consumable"]),
                "last_seq": event.seq,
            },
        )
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {PROJECT_ITEM_TABLE}"))
