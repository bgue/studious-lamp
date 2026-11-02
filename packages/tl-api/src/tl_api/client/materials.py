"""The materials module's reads over HTTP, and its one write door (P2-I3-T04b).

The same models the embedded views return (``tl_mod_materials.views``). A missing lot or receipt is
the module's ``LotNotFoundError`` or ``ReceiptNotFoundError``, rebuilt from the 404 body. The writes
are ``materials_command(name, cmd)``: ``name`` is a model of ``tl_mod_materials.commands``
``MATERIALS_COMMANDS``, posted to ``/commands/<name>``.
"""

from __future__ import annotations

from tl_core.auth.errors import ForbiddenError
from tl_core.services.commands import Command, CommandResult
from tl_mod_materials import views
from tl_mod_materials.commands import MATERIALS_COMMANDS

from tl_api.client.base import ApiClientBase, quote


class MaterialsApi(ApiClientBase):
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
        """The balances by lot and location (``GET .../materials/stock``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/materials/stock",
            {
                "lot": lot,
                "location": location,
                "item": item,
                "heat": heat,
                "subtree": subtree,
                "limit": limit,
            },
        )
        return self._models(views.StockRowView, data)

    def get_materials_lot(self, project: str, key: str) -> views.LotDetailView:
        """One lot with its balances, reservations and last ten movements (``.../lots/{key}``)."""
        data = self._get_json(f"/projects/{quote(project)}/materials/lots/{quote(key)}")
        return self._model(views.LotDetailView, data)

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
        """The movement log in ledger order (``GET .../materials/movements``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/materials/movements",
            {"lot": lot, "since": since, "until": until, "kind": kind, "limit": limit},
        )
        return self._models(views.MovementView, data)

    def list_materials_receipts(
        self,
        project: str,
        *,
        open_only: bool = False,
        missing_mtr: bool = False,
        limit: int = 1000,
    ) -> list[views.ReceiptView]:
        """A project's goods receipts, newest first (``GET .../materials/receipts``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/materials/receipts",
            {"open_only": open_only, "missing_mtr": missing_mtr, "limit": limit},
        )
        return self._models(views.ReceiptView, data)

    def get_materials_receipt(self, project: str, number: str) -> views.ReceiptDetailView:
        """One goods receipt with its lines and files (``.../materials/receipts/{number}``)."""
        data = self._get_json(f"/projects/{quote(project)}/materials/receipts/{quote(number)}")
        return self._model(views.ReceiptDetailView, data)

    def list_materials_locations(
        self, project: str, *, limit: int = 1000
    ) -> list[views.LocationView]:
        """A project's storage locations in tree order (``GET .../materials/locations``)."""
        data = self._get_json(f"/projects/{quote(project)}/materials/locations", {"limit": limit})
        return self._models(views.LocationView, data)

    def list_materials_po_lines(
        self, project: str, *, q: str | None = None, limit: int = 1000
    ) -> list[views.PoLineView]:
        """A project's purchase-order lines by key (``GET .../materials/po-lines``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/materials/po-lines", {"q": q, "limit": limit}
        )
        return self._models(views.PoLineView, data)

    def list_materials_mto_lines(
        self,
        project: str,
        *,
        work_package: str | None = None,
        short_only: bool = False,
        limit: int = 1000,
    ) -> list[views.MtoLineView]:
        """A project's take-off lines (``GET .../materials/mto-lines``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/materials/mto-lines",
            {"work_package": work_package, "short_only": short_only, "limit": limit},
        )
        return self._models(views.MtoLineView, data)

    def list_materials_items(
        self, *, project: str | None = None, limit: int = 1000
    ) -> list[views.MaterialItemView]:
        """The company library of items; with ``project``, the items it adopted (``.../items``)."""
        data = self._get_json("/companies/materials/items", {"project": project, "limit": limit})
        return self._models(views.MaterialItemView, data)

    def materials_command(self, name: str, cmd: Command) -> CommandResult:
        """Run a materials command by name (``POST /commands/<name>``, the token's actor).

        A name that is not in ``MATERIALS_COMMANDS``, or a command of another class, raises
        ``ForbiddenError`` before anything is sent.
        """
        spec = next((c for c in MATERIALS_COMMANDS if c.model.__name__ == name), None)
        if spec is None or type(cmd) is not spec.model:
            raise ForbiddenError(f"{name} is not a materials command")
        return self._command(name, cmd)
