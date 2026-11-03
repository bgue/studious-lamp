"""The awp module's reads over HTTP: CWPs, CWAs, the WBS, the path of construction and the packages
(P2-I1 T03b).

The same models the embedded client returns (``tl_mod_awp.views``, and the route model
``CwpDetailView`` that adds the link count, file count and timeline). The module's missing-record
error (``RecordNotFoundError``) is rebuilt from the 404 body.
"""

from __future__ import annotations

from typing import Literal

from tl_mod_awp import views as awp_views

from tl_api.client.base import ApiClientBase, quote
from tl_api.routes.awp import CwpDetailView


class AwpApi(ApiClientBase):
    def list_cwps(
        self,
        project: str,
        *,
        state: str | None = None,
        discipline: str | None = None,
        cwa: str | None = None,
    ) -> list[awp_views.CwpRow]:
        """A project's CWPs by number (``GET /projects/{project}/awp/cwps``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/awp/cwps",
            {"state": state, "discipline": discipline, "cwa": cwa},
        )
        return self._models(awp_views.CwpRow, data)

    def get_cwp(self, project: str, number: str) -> CwpDetailView:
        """One CWP with its links, files and timeline (``GET .../awp/cwps/{number}``)."""
        data = self._get_json(f"/projects/{quote(project)}/awp/cwps/{quote(number)}")
        return self._model(CwpDetailView, data)

    def list_cwas(self, project: str) -> list[awp_views.CwaRow]:
        """A project's construction work areas (``GET .../awp/cwas``)."""
        data = self._get_json(f"/projects/{quote(project)}/awp/cwas")
        return self._models(awp_views.CwaRow, data)

    def wbs_tree(self, project: str, *, depth: int | None = None) -> list[awp_views.WbsRow]:
        """The WBS nodes depth-first, each with its rollup (``GET .../awp/wbs``)."""
        data = self._get_json(f"/projects/{quote(project)}/awp/wbs", {"depth": depth})
        return self._models(awp_views.WbsRow, data)

    def get_wbs_node(self, project: str, code: str) -> awp_views.WbsRow:
        """One WBS node by its code (``GET .../awp/wbs/{code}``)."""
        data = self._get_json(f"/projects/{quote(project)}/awp/wbs/{quote(code)}")
        return self._model(awp_views.WbsRow, data)

    def get_path(self, project: str, version: int | None = None) -> awp_views.PathView:
        """The path of construction at a version, the current one by default (``.../awp/path``)."""
        data = self._get_json(f"/projects/{quote(project)}/awp/path", {"version": version})
        return self._model(awp_views.PathView, data)

    def list_path_versions(self, project: str) -> list[awp_views.PathVersion]:
        """The versions of the path, newest first (``GET .../awp/path/versions``)."""
        data = self._get_json(f"/projects/{quote(project)}/awp/path/versions")
        return self._models(awp_views.PathVersion, data)

    def list_packages(
        self, project: str, *, kind: Literal["EWP", "PWP"] | None = None
    ) -> list[awp_views.PackageRow]:
        """The EWP and PWP references by package number (``GET .../awp/packages``)."""
        data = self._get_json(f"/projects/{quote(project)}/awp/packages", {"kind": kind})
        return self._models(awp_views.PackageRow, data)
