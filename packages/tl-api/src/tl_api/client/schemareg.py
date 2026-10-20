"""The schema registry's reads and commands over HTTP (P1-I8).

The same models the embedded services return (``tl_mod_schemareg.views``). A missing package is
the module's ``SchemaPackageNotFoundError``, rebuilt from the error body. Every command is
``schemareg_command(name, cmd)``; the names and their access are in ``tl_mod_schemareg.commands``.
"""

from __future__ import annotations

from tl_core.services.commands import Command, CommandResult
from tl_mod_schemareg import views
from tl_mod_schemareg.impact_types import ImpactReport

from tl_api.client.base import ApiClientBase, quote


class SchemaRegistryApi(ApiClientBase):
    def list_schema_packages(
        self,
        *,
        scope: str | None = None,
        state: str | None = None,
        package: str | None = None,
        limit: int = 200,
    ) -> list[views.PackageSummary]:
        """Package versions, highest first (``GET /schema/packages``)."""
        data = self._get_json(
            "/schema/packages",
            {"scope": scope, "state": state, "package": package, "limit": limit},
        )
        return self._models(views.PackageSummary, data)

    def get_schema_package(self, ref: str) -> views.PackageDetail:
        """One package by id or ``name@version`` (``GET /schema/packages/{ref}``)."""
        return self._model(views.PackageDetail, self._get_json(f"/schema/packages/{quote(ref)}"))

    def sample_test_schema_package(self, ref: str, sample: int = 1000) -> views.SampleTestView:
        """Test on sample (``GET /schema/sample-tests/{ref}``)."""
        data = self._get_json(f"/schema/sample-tests/{quote(ref)}", {"sample": sample})
        return self._model(views.SampleTestView, data)

    def list_schema_adoptions(self, project: str | None = None) -> list[views.AdoptionView]:
        """The pins of every project or one (``GET /schema/adoptions``)."""
        return self._models(
            views.AdoptionView, self._get_json("/schema/adoptions", {"project": project})
        )

    def list_schema_waivers(
        self, project: str | None = None, state: str | None = None
    ) -> list[views.WaiverView]:
        """Waivers (``GET /schema/waivers``)."""
        data = self._get_json("/schema/waivers", {"project": project, "state": state})
        return self._models(views.WaiverView, data)

    def get_schema_drift(self, project: str) -> list[views.DriftView]:
        """The project's package versions against the company's."""
        data = self._get_json(f"/projects/{quote(project)}/schema/drift")
        return self._models(views.DriftView, data)

    def get_project_schema_impact(self, project: str, package: str, version: str) -> ImpactReport:
        """What pinning ``package@version`` does to the project."""
        data = self._get_json(
            f"/projects/{quote(project)}/schema/impact", {"package": package, "version": version}
        )
        return self._model(ImpactReport, data)

    def schemareg_command(self, name: str, cmd: Command) -> CommandResult:
        """Run any registry command by name (``POST /commands/{name}``); the token's actor is
        used. See ``tl_mod_schemareg.commands`` for the names and their access."""
        return self._command(name, cmd)
