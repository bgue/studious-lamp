"""In-memory schema workbench for `FakeClient` (P1-I8): the reads and the one command call.

It holds package details, adoptions, waivers, drift and impact reports a test gave it, and answers
the reads the way the embedded client does (filters, the module's not-found error). A command is
recorded in `schemareg_commands`; an admin's command by anyone else is a `ForbiddenError`.
`test_fakes_schemareg.py` checks the fake against the `ClientInterface` protocol.
"""

from __future__ import annotations

from tl_core.auth.errors import ForbiddenError
from tl_core.services.commands import Command, CommandResult
from tl_mod_schemareg import views
from tl_mod_schemareg.commands import API_COMMANDS
from tl_mod_schemareg.errors import SchemaPackageNotFoundError
from tl_mod_schemareg.impact_types import ImpactReport, empty_report


def make_package(
    package: str = "co.acme.engineering",
    version: str = "3.3.0",
    state: str = "Draft",
    **more: object,
) -> views.PackageDetail:
    """A package detail with plausible defaults; keyword arguments override a field."""
    fields: dict[str, object] = {
        "id": f"PKG-{package}-{version}",
        "key": f"{package}@{version}",
        "scope": "company",
        "package": package,
        "version": version,
        "kind": "company",
        "project": None,
        "title": None,
        "state": state,
        "worst_class": None,
        "analysed": False,
        "drafted_by": "user:dev",
        "submitted_by": None,
        "approved_by": None,
        "published_at": None,
        "changelog": None,
        "content": f"package: {package}\nversion: {version}\n",
        "content_sha256": "a" * 64,
        "base_ref": None,
        "classification": None,
        "impact": None,
        "impact_sha256": None,
        "lint": [],
        "diff": "",
        "diff_truncated": False,
    }
    fields.update(more)
    return views.PackageDetail.model_validate(fields)


class FakeSchemaRegistrySupport:
    """Mixin for `FakeClient`: call `_init_schemareg()` from its `__init__`."""

    def _init_schemareg(self) -> None:
        self._schema_packages: dict[str, views.PackageDetail] = {}
        self._schema_adoptions: list[views.AdoptionView] = []
        self._schema_waivers: list[views.WaiverView] = []
        self._schema_drift: dict[str, list[views.DriftView]] = {}
        self._schema_impact: dict[tuple[str, str, str], ImpactReport] = {}
        self._schema_samples: dict[str, views.SampleTestView] = {}
        self.schemareg_commands: list[Command] = []

    def seed_schema_package(self, detail: views.PackageDetail) -> None:
        self._schema_packages[detail.id] = detail

    def seed_schema_adoption(self, view: views.AdoptionView) -> None:
        self._schema_adoptions.append(view)

    def seed_schema_waiver(self, view: views.WaiverView) -> None:
        self._schema_waivers.append(view)

    def seed_schema_drift(self, project: str, rows: list[views.DriftView]) -> None:
        self._schema_drift[project] = rows

    def seed_schema_impact(
        self, project: str, package: str, version: str, report: ImpactReport
    ) -> None:
        self._schema_impact[(project, package, version)] = report

    def seed_schema_sample(self, ref: str, result: views.SampleTestView) -> None:
        self._schema_samples[ref] = result

    def _schema_package(self, ref: str) -> views.PackageDetail:
        for detail in self._schema_packages.values():
            if ref in (detail.id, detail.key):
                return detail
        raise SchemaPackageNotFoundError(f"no schema package {ref!r}")

    def list_schema_packages(
        self,
        *,
        scope: str | None = None,
        state: str | None = None,
        package: str | None = None,
        limit: int = 200,
    ) -> list[views.PackageSummary]:
        found = [
            views.PackageSummary(**d.model_dump(include=set(views.PackageSummary.model_fields)))
            for d in self._schema_packages.values()
            if (scope is None or d.scope == scope)
            and (state is None or d.state == state)
            and (package is None or d.package == package)
        ]
        found.sort(
            key=lambda p: (p.package, tuple(int(x) for x in p.version.split("."))), reverse=True
        )
        return found[:limit]

    def get_schema_package(self, ref: str) -> views.PackageDetail:
        return self._schema_package(ref)

    def sample_test_schema_package(self, ref: str, sample: int = 1000) -> views.SampleTestView:
        detail = self._schema_package(ref)
        return self._schema_samples.get(
            ref,
            views.SampleTestView(
                package=detail.key, scope=detail.scope, sample=sample, checked=0,
                newly_nonconformant=0, newly_warning=0, fixed=0, examples=[],
            ),
        )  # fmt: skip

    def list_schema_adoptions(self, project: str | None = None) -> list[views.AdoptionView]:
        return [a for a in self._schema_adoptions if project is None or a.project == project]

    def list_schema_waivers(
        self, project: str | None = None, state: str | None = None
    ) -> list[views.WaiverView]:
        return [
            w
            for w in self._schema_waivers
            if (project is None or w.project == project) and (state is None or w.state == state)
        ]

    def get_schema_drift(self, project: str) -> list[views.DriftView]:
        return list(self._schema_drift.get(project, []))

    def get_project_schema_impact(self, project: str, package: str, version: str) -> ImpactReport:
        return self._schema_impact.get(
            (project, package, version),
            empty_report(f"project:{project}", "0" * 64, "1" * 64),
        )

    def schemareg_command(self, name: str, cmd: Command) -> CommandResult:
        spec = next((c for c in API_COMMANDS if c.model.__name__ == name), None)
        if spec is None or type(cmd) is not spec.model:
            raise ForbiddenError(f"{name} is not a schema registry command")
        if spec.access == "admin" and not self.is_admin:  # type: ignore[attr-defined]
            raise ForbiddenError("this action needs the admin role")
        self.schemareg_commands.append(cmd)
        return CommandResult(stream_id="PKG-1", key=None, version=1, events=[])
