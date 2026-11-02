"""In-memory materials reads for `FakeClient` (P2-I3-T04b): the nine reads and the one write door.

It holds the rows a test gave it, per project, and answers each read with the filters of the
matching route (``tl_api.routes.materials``): stock by lot, location (with ``subtree`` by the parent
codes of ``locations``), item, heat; movements by lot, kind and day; receipts ``open_only`` and
``missing_mtr``; PO lines by a substring; take-off lines by work package and shortage. Each list is
cut to ``limit``. A missing lot or receipt raises the module's not-found error. `materials_command`
records the command in `materials_commands` after the same name check as the embedded client.
`test_client_materials.py` runs the same reads on this fake and on the real clients.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from tl_core.auth.errors import ForbiddenError
from tl_core.services.commands import Command, CommandResult
from tl_mod_materials import views
from tl_mod_materials.commands import MATERIALS_COMMANDS
from tl_mod_materials.errors import LotNotFoundError, ReceiptNotFoundError

#: The receipt states ``open_only`` keeps: not yet accepted, rejected or void.
OPEN_STATES = ("Received", "Inspected")


@dataclass
class _ProjectRows:
    """One project's materials rows as the test put them."""

    stock: list[views.StockRowView] = field(default_factory=list[views.StockRowView])
    movements: list[views.MovementView] = field(default_factory=list[views.MovementView])
    receipts: list[views.ReceiptView] = field(default_factory=list[views.ReceiptView])
    locations: list[views.LocationView] = field(default_factory=list[views.LocationView])
    po_lines: list[views.PoLineView] = field(default_factory=list[views.PoLineView])
    mto_lines: list[views.MtoLineView] = field(default_factory=list[views.MtoLineView])
    lots: dict[str, views.LotDetailView] = field(default_factory=dict[str, views.LotDetailView])
    receipt_details: dict[str, views.ReceiptDetailView] = field(
        default_factory=dict[str, views.ReceiptDetailView]
    )


def _codes_under(locations: Sequence[views.LocationView], root: str, subtree: bool) -> set[str]:
    """``root`` and, with ``subtree``, every location whose parent chain reaches it."""
    if not subtree:
        return {root}
    below: dict[str, list[str]] = {}
    for loc in locations:
        if loc.parent_code is not None:
            below.setdefault(loc.parent_code, []).append(loc.code)
    found, todo = {root}, [root]
    while todo:
        for child in below.get(todo.pop(), []):
            if child not in found:
                found.add(child)
                todo.append(child)
    return found


class FakeMaterialsSupport:
    """Mixin for `FakeClient`: call `_init_materials()` from its `__init__`."""

    def _init_materials(self) -> None:
        self._materials: dict[str, _ProjectRows] = {}
        self._material_items: list[views.MaterialItemView] = []
        self.materials_commands: list[Command] = []  # every materials command, in call order

    # --- seeding -----------------------------------------------------------------------------

    def put_materials(
        self,
        project: str,
        *,
        stock: Sequence[views.StockRowView] = (),
        movements: Sequence[views.MovementView] = (),
        receipts: Sequence[views.ReceiptView] = (),
        locations: Sequence[views.LocationView] = (),
        po_lines: Sequence[views.PoLineView] = (),
        mto_lines: Sequence[views.MtoLineView] = (),
        lots: Sequence[views.LotDetailView] = (),
        receipt_details: Sequence[views.ReceiptDetailView] = (),
    ) -> None:
        """Replace one project's rows. Lots are keyed by ``key``, receipts by ``number``."""
        self._materials[project] = _ProjectRows(
            stock=list(stock),
            movements=list(movements),
            receipts=list(receipts),
            locations=list(locations),
            po_lines=list(po_lines),
            mto_lines=list(mto_lines),
            lots={lot.key: lot for lot in lots},
            receipt_details={r.number: r for r in receipt_details},
        )

    def put_material_items(self, items: Sequence[views.MaterialItemView]) -> None:
        """Replace the company library of items."""
        self._material_items = list(items)

    def _materials_of(self, project: str) -> _ProjectRows:
        return self._materials.get(project, _ProjectRows())

    # --- reads -------------------------------------------------------------------------------

    def list_materials_stock(
        self,
        project: str,
        *,
        lot: str | None = None,
        location: str | None = None,
        item: str | None = None,
        heat: str | None = None,
        subtree: bool = False,
        limit: int = 1000,
    ) -> list[views.StockRowView]:
        rows = self._materials_of(project)
        out = rows.stock
        if location is not None:
            known = {loc.code for loc in rows.locations}
            if location not in known:
                return []
            codes = _codes_under(rows.locations, location, subtree)
            out = [r for r in out if r.location in codes]
        if lot is not None:
            out = [r for r in out if r.lot == lot]
        if item is not None:
            out = [r for r in out if r.item_code == item]
        if heat is not None:
            out = [r for r in out if r.heat_no == heat]
        return out[:limit]

    def get_materials_lot(self, project: str, key: str) -> views.LotDetailView:
        found = self._materials_of(project).lots.get(key)
        if found is None:
            raise LotNotFoundError(key)
        return found

    def list_materials_movements(
        self,
        project: str,
        *,
        lot: str | None = None,
        since: str | None = None,
        until: str | None = None,
        kind: str | None = None,
        limit: int = 1000,
    ) -> list[views.MovementView]:
        out = self._materials_of(project).movements
        if lot is not None:
            out = [m for m in out if m.lot == lot]
        if kind is not None:
            out = [m for m in out if m.kind == kind]
        if since is not None:
            out = [m for m in out if m.recorded_at[:10] >= since[:10]]
        if until is not None:
            out = [m for m in out if m.recorded_at[:10] <= until[:10]]
        return out[:limit]

    def list_materials_receipts(
        self,
        project: str,
        *,
        open_only: bool = False,
        missing_mtr: bool = False,
        limit: int = 1000,
    ) -> list[views.ReceiptView]:
        out = self._materials_of(project).receipts
        if open_only:
            out = [r for r in out if r.state in OPEN_STATES]
        if missing_mtr:
            out = [r for r in out if r.mtr == "missing"]
        return out[:limit]

    def get_materials_receipt(self, project: str, number: str) -> views.ReceiptDetailView:
        found = self._materials_of(project).receipt_details.get(number)
        if found is None:
            raise ReceiptNotFoundError(number)
        return found

    def list_materials_locations(
        self, project: str, *, limit: int = 1000
    ) -> list[views.LocationView]:
        return self._materials_of(project).locations[:limit]

    def list_materials_po_lines(
        self, project: str, *, q: str | None = None, limit: int = 1000
    ) -> list[views.PoLineView]:
        out = self._materials_of(project).po_lines
        if q is not None:
            needle = q.lower()
            out = [
                p
                for p in out
                if any(needle in text.lower() for text in (p.key, p.item_code, p.supplier_text))
            ]
        return out[:limit]

    def list_materials_mto_lines(
        self,
        project: str,
        *,
        work_package: str | None = None,
        short_only: bool = False,
        limit: int = 1000,
    ) -> list[views.MtoLineView]:
        out = self._materials_of(project).mto_lines
        if work_package is not None:
            out = [m for m in out if m.work_package == work_package]
        if short_only:
            out = [m for m in out if m.short > 0]
        return out[:limit]

    def list_materials_items(
        self, *, project: str | None = None, limit: int = 1000
    ) -> list[views.MaterialItemView]:
        """The library; ``project`` is not used here (the fake holds one library)."""
        return self._material_items[:limit]

    # --- the write door ----------------------------------------------------------------------

    def materials_command(self, name: str, cmd: Command) -> CommandResult:
        spec = next((c for c in MATERIALS_COMMANDS if c.model.__name__ == name), None)
        if spec is None or type(cmd) is not spec.model:
            raise ForbiddenError(f"{name} is not a materials command")
        self.materials_commands.append(cmd)
        return CommandResult(stream_id="MAT-1", key=None, version=1, events=[])
