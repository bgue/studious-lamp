"""The permits module's reads and its one write door over HTTP (P2-PTW-T10).

The same models the embedded client returns (``tl_mod_permits.views`` and
``tl_mod_permits.iso_views``: dataclasses, so they are decoded with a ``TypeAdapter``).
``project`` is a query parameter, as the routes take it (``tl_mod_permits.routes``). A missing,
hidden or other-project permit, isolation or gas-test permit is the service's
``RecordNotFoundError``, rebuilt from the 404 body. ``permit_command(name, cmd)`` runs a model of
``tl_mod_permits.module.COMMANDS`` by name, posted to ``/commands/<name>``; that table already
holds the six isolation and gas-test commands.
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter
from tl_core.auth.errors import ForbiddenError
from tl_core.services.commands import Command, CommandResult
from tl_mod_permits import iso_views
from tl_mod_permits import views as permit_views
from tl_mod_permits.module import COMMANDS as PERMIT_COMMANDS

from tl_api.client.base import ApiClientBase, quote

_PAGE: TypeAdapter[permit_views.PermitPage] = TypeAdapter(permit_views.PermitPage)
_DETAIL: TypeAdapter[permit_views.PermitDetail] = TypeAdapter(permit_views.PermitDetail)
_BOARD: TypeAdapter[permit_views.PermitBoard] = TypeAdapter(permit_views.PermitBoard)
_ISO_PAGE: TypeAdapter[iso_views.IsolationPage] = TypeAdapter(iso_views.IsolationPage)
_ISO_DETAIL: TypeAdapter[iso_views.IsolationDetail] = TypeAdapter(iso_views.IsolationDetail)
_GAS_ROWS: TypeAdapter[list[iso_views.GasRow]] = TypeAdapter(list[iso_views.GasRow])


class PermitsApi(ApiClientBase):
    def list_permits(
        self,
        project: str,
        *,
        state: str | None = None,
        permit_type: str | None = None,
        area: str | None = None,
        holder: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> permit_views.PermitPage:
        """A project's permits by key (``GET /permits?project=``; ``type`` is the permit type);
        ``total`` counts the visible matches."""
        data: Any = self._get_json(
            "/permits",
            {
                "project": project,
                "state": state,
                "type": permit_type,
                "area": area,
                "holder": holder,
                "limit": limit,
                "offset": offset,
            },
        )
        return _PAGE.validate_python(data)

    def get_permit(self, project: str, key: str) -> permit_views.PermitDetail:
        """One permit (``GET /permits/{key}?project=``); 404 for a missing or hidden one."""
        data: Any = self._get_json(f"/permits/{quote(key)}", {"project": project})
        return _DETAIL.validate_python(data)

    def get_permit_board(
        self, project: str, *, area: str | None = None
    ) -> permit_views.PermitBoard:
        """The live permits by area and the counts by shown state (``GET /permits/board``)."""
        data: Any = self._get_json("/permits/board", {"project": project, "area": area})
        return _BOARD.validate_python(data)

    def list_isolations(
        self,
        project: str,
        *,
        state: str | None = None,
        energy: str | None = None,
        limit: int = 100,
    ) -> iso_views.IsolationPage:
        """A project's isolations by key (``GET /permits/isolations?project=``)."""
        data: Any = self._get_json(
            "/permits/isolations",
            {"project": project, "state": state, "energy": energy, "limit": limit},
        )
        return _ISO_PAGE.validate_python(data)

    def get_isolation(self, project: str, key: str) -> iso_views.IsolationDetail:
        """One isolation (``GET /permits/isolations/{key}?project=``); 404 when missing or
        hidden."""
        data: Any = self._get_json(f"/permits/isolations/{quote(key)}", {"project": project})
        return _ISO_DETAIL.validate_python(data)

    def list_gas_tests(self, project: str, permit_key: str) -> list[iso_views.GasRow]:
        """The gas tests of one permit, newest first (``GET /permits/{key}/gas-tests?project=``);
        404 for a missing or hidden permit."""
        data: Any = self._get_json(f"/permits/{quote(permit_key)}/gas-tests", {"project": project})
        return _GAS_ROWS.validate_python(data)

    def permit_command(self, name: str, cmd: Command) -> CommandResult:
        """Run a permit command by name (``POST /commands/<name>``, the token's actor).

        A name that is not in ``tl_mod_permits.module.COMMANDS``, or a command of another class,
        raises ``ForbiddenError`` before anything is sent.
        """
        spec = next((c for c in PERMIT_COMMANDS if c.model.__name__ == name), None)
        if spec is None or type(cmd) is not spec.model:
            raise ForbiddenError(f"{name} is not a permit command")
        return self._command(name, cmd)
