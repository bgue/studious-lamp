"""Reads of the schema registry: packages, adoptions, waivers, drift, impact, sample test (P1-I8).

Thin: one call into ``tl_mod_schemareg.views`` or ``analysis`` per route. The writes are the
module's commands (``POST /commands/DraftSchemaPackage`` and the rest; ``tl_mod_schemareg.commands``
holds their access levels). Every read needs the action ``document.read``, which agents hold because
they only read. Packages carry no confidential class; the record counts in a report are taken as the
lowest reader (ADR-0016), so no route here can tell a reader that a record they may not read exists.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from tl_core.auth.types import Principal
from tl_mod_schemareg import analysis, views
from tl_mod_schemareg.impact_types import ImpactReport, redact_names

from tl_api.auth import current_principal, guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["schema registry"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard("document.read"))]
Me = Annotated[Principal, Depends(current_principal)]


@router.get("/schema/packages", operation_id="list_schema_packages")
def list_schema_packages(
    ctx: Ctx,
    actor: Reader,
    scope: Annotated[
        str | None, Query(max_length=80, description="company or project:<id>.")
    ] = None,
    state: Annotated[str | None, Query(max_length=20, description="For example Published.")] = None,
    package: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> list[views.PackageSummary]:
    """Package versions by name and version, highest first."""
    with ctx.backend(True) as uow:
        return views.package_summaries(
            uow.conn(), scope=scope, state=state, package=package, limit=limit, offset=offset
        )


@router.get("/schema/packages/{ref:path}", operation_id="get_schema_package")
def get_schema_package(ctx: Ctx, actor: Reader, principal: Me, ref: str) -> views.PackageDetail:
    """One package by record id or ``name@version``, with its reports, lint and diff.
    The impact report names mappings, rules and reports only to an administrator.
    404 `schema_package_not_found`."""
    with ctx.backend(True) as uow:
        return views.package_detail(uow.conn(), ref, names=principal.is_admin)


@router.get("/schema/sample-tests/{ref:path}", operation_id="sample_test_schema_package")
def sample_test_schema_package(
    ctx: Ctx,
    actor: Reader,
    ref: str,
    sample: Annotated[int, Query(ge=1, le=views.MAX_SAMPLE)] = views.DEFAULT_SAMPLE,
) -> views.SampleTestView:
    """Re-check a sample of the readable records against the schema the draft makes."""
    with ctx.backend(True) as uow:
        return views.sample_test(uow.conn(), ref, sample)


@router.get("/schema/adoptions", operation_id="list_schema_adoptions")
def list_schema_adoptions(
    ctx: Ctx, actor: Reader, project: Annotated[str | None, Query(max_length=64)] = None
) -> list[views.AdoptionView]:
    """The pins of every project, or of one."""
    with ctx.backend(True) as uow:
        return views.adoption_views(uow.conn(), project)


@router.get("/schema/waivers", operation_id="list_schema_waivers")
def list_schema_waivers(
    ctx: Ctx,
    actor: Reader,
    project: Annotated[str | None, Query(max_length=64)] = None,
    state: Annotated[str | None, Query(max_length=20)] = None,
) -> list[views.WaiverView]:
    """Waivers by project and path, with whether each has expired."""
    with ctx.backend(True) as uow:
        return views.waiver_views(uow.conn(), project, state)


@router.get("/projects/{project}/schema/drift", operation_id="get_schema_drift")
def get_schema_drift(ctx: Ctx, actor: Reader, project: str) -> list[views.DriftView]:
    """The project's version of each company package against the company's."""
    return views.drift_views(project)


@router.get("/projects/{project}/schema/impact", operation_id="get_project_schema_impact")
def get_project_schema_impact(
    ctx: Ctx,
    actor: Reader,
    principal: Me,
    project: str,
    package: Annotated[str, Query(max_length=200)],
    version: Annotated[str, Query(max_length=40)],
) -> ImpactReport:
    """What pinning ``package@version`` does to the project; its ``digest`` confirms an adoption.
    Other readers than an administrator get counts where the report would name mappings, rules
    and reports (and a digest of their own: only an administrator adopts)."""
    with ctx.backend(True) as uow:
        report, _before, _after = analysis.project_impact(uow.conn(), project, package, version)
        return report if principal.is_admin else redact_names(report)
