"""The cost module's reads over HTTP: cost codes, their figures, the snapshots (P1-I4).

The same models the embedded services return (``tl_mod_cost.views``). A missing code is the
module's ``CostCodeNotFoundError``, rebuilt from the error body.
"""

from __future__ import annotations

from tl_core.services.commands import CommandResult
from tl_mod_cost import views
from tl_mod_cost.handlers.snapshots import ImportCostSnapshot

from tl_api.client.base import ApiClientBase, quote


class CostApi(ApiClientBase):
    def list_cost_snapshots(self, project: str) -> list[views.CostSnapshotView]:
        """A project's cost snapshots (``GET /projects/{project}/cost-snapshots``)."""
        data = self._get_json(f"/projects/{quote(project)}/cost-snapshots")
        return self._models(views.CostSnapshotView, data)

    def list_cost_codes(
        self,
        project: str,
        *,
        parent: str | None = None,
        q: str | None = None,
        limit: int = 1000,
    ) -> list[views.CostCodeView]:
        """A project's cost codes with the latest figures (``GET .../cost-codes``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/cost-codes", {"parent": parent, "q": q, "limit": limit}
        )
        return self._models(views.CostCodeView, data)

    def get_cost_code(self, project: str, code: str) -> views.CostCodeDetailView:
        """One cost code with its children and history (``GET .../cost-codes/{code}``)."""
        data = self._get_json(f"/projects/{quote(project)}/cost-codes/{quote(code)}")
        return self._model(views.CostCodeDetailView, data)

    def import_cost_snapshot(self, cmd: ImportCostSnapshot) -> CommandResult:
        """Import one period of figures (``POST /commands/ImportCostSnapshot``): the admin's."""
        return self._command("ImportCostSnapshot", cmd)
