"""The read shapes of the schema registry: what the API, the CLI and the workbench show.

Rows are pydantic models, so the API returns them as they are and the clients parse them back.
Nothing here writes, and nothing checks a role: reads need ``document.read`` at the entry points.
``package_detail`` carries the stored reports and a text diff of the package against the version it
was compared with; ``sample_test`` is brief 27.4's "test on sample": it re-checks a bounded sample
of the records a draft touches and counts the ones that would newly be non-conformant.
"""

from __future__ import annotations

import difflib
import json
from datetime import date
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.modules import bound_psets
from tl_core.util import utcnow
from tl_schema.classify import ClassificationReport
from tl_schema.conformance import evaluate
from tl_schema.packages import version_tuple

from tl_mod_schemareg import analysis, registry
from tl_mod_schemareg.errors import SchemaPackageNotFoundError
from tl_mod_schemareg.impact_types import ImpactReport
from tl_mod_schemareg.names import WAIVER_APPROVED_STATE

MAX_DIFF_LINES = 400
MAX_SAMPLE = 5000
DEFAULT_SAMPLE = 1000
MAX_EXAMPLES = 10


class PackageSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    key: str
    scope: str
    package: str
    version: str
    kind: str
    project: str | None
    title: str | None
    state: str
    worst_class: str | None
    analysed: bool  # the reports are for the content as it is now
    drafted_by: str
    submitted_by: str | None
    approved_by: str | None
    published_at: str | None
    changelog: str | None


class LintIssueView(BaseModel):
    model_config = ConfigDict(frozen=True)

    severity: str
    rule: str
    path: str
    message: str


class PackageDetail(PackageSummary):
    content: str
    content_sha256: str
    base_ref: str | None
    classification: ClassificationReport | None
    impact: ImpactReport | None
    impact_sha256: str | None
    lint: list[LintIssueView]
    diff: str  # unified diff of the canonical YAML against the base ("" for a first version)
    diff_truncated: bool


class AdoptionView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    project: str
    package: str
    version: str
    previous_version: str | None
    worst_class: str | None
    impact_sha256: str | None
    adopted_by: str
    adopted_at: str


class WaiverView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    key: str
    project: str
    path: str
    number: int
    reason: str
    expires: str
    expired: bool
    state: str
    requested_by: str
    approver: str | None


class DriftView(BaseModel):
    """A project's version of a company package against the company's."""

    model_config = ConfigDict(frozen=True)

    package: str
    project_version: str
    company_version: str
    behind: bool
    pinned: bool


class SampleExample(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    path: str
    rule: str
    message: str


class SampleTestView(BaseModel):
    model_config = ConfigDict(frozen=True)

    package: str
    scope: str
    sample: int  # the size asked for
    checked: int
    newly_nonconformant: int
    newly_warning: int
    fixed: int  # records that were not ok before and are ok now
    examples: list[SampleExample]


def _today() -> date:
    return utcnow().date()


def _summary(row: registry.PackageRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "key": row.key,
        "scope": row.scope,
        "package": row.package,
        "version": row.version,
        "kind": row.kind,
        "project": row.project,
        "title": row.package_title,
        "state": row.state,
        "worst_class": row.worst_class,
        "analysed": row.analysed_sha256 is not None and row.analysed_sha256 == row.content_sha256,
        "drafted_by": row.drafted_by,
        "submitted_by": row.submitted_by,
        "approved_by": row.approved_by,
        "published_at": row.published_at,
        "changelog": row.changelog,
    }


def package_summaries(
    conn: Connection,
    *,
    scope: str | None = None,
    state: str | None = None,
    package: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[PackageSummary]:
    rows = registry.list_packages(
        conn, scope=scope, state=state, package=package, limit=limit, offset=offset
    )
    return [PackageSummary(**_summary(r)) for r in rows]


def _find(conn: Connection, ref: str) -> registry.PackageRow:
    row = registry.get_package(conn, ref)
    if row is None and "@" in ref:
        name, _, version = ref.partition("@")
        row = registry.find_package(conn, name, version)
    if row is None:
        raise SchemaPackageNotFoundError(f"no schema package {ref!r}")
    return row


def _canonical(content: str) -> list[str]:
    data = yaml.safe_load(content)
    return yaml.safe_dump(data, sort_keys=True, default_flow_style=False).splitlines()


def _diff(row: registry.PackageRow) -> tuple[str, bool]:
    if row.base_ref is None:
        return "", False
    name, _, version = row.base_ref.partition("@")
    try:
        base = analysis.provider().registry().get(name, version)
    except Exception:  # noqa: BLE001 - a base that is gone leaves the diff empty
        return "", False
    before = yaml.safe_dump(
        base.model_dump(mode="json", exclude_none=True), sort_keys=True, default_flow_style=False
    ).splitlines()
    try:
        after = _canonical(row.content)
    except yaml.YAMLError:
        return "", False
    lines = list(difflib.unified_diff(before, after, row.base_ref, row.key, lineterm="", n=2))
    return "\n".join(lines[:MAX_DIFF_LINES]), len(lines) > MAX_DIFF_LINES


def lint_issues(row: registry.PackageRow) -> list[LintIssueView]:
    """The lint issues of the package on its own (all severities); empty for unparsable text."""
    try:
        doc = analysis.parse_content(row.content)
    except Exception:  # noqa: BLE001 - nothing to lint in text that is not a package
        return []
    from tl_schema.lint import lint_documents

    return [
        LintIssueView(severity=i.severity, rule=i.rule, path=i.path, message=i.message)
        for i in lint_documents([doc])
    ]


def package_detail(conn: Connection, ref: str) -> PackageDetail:
    """One package by id or ``name@version``: content, stored reports, lint and the text diff."""
    row = _find(conn, ref)
    diff, truncated = _diff(row)
    return PackageDetail(
        **_summary(row),
        content=row.content,
        content_sha256=row.content_sha256,
        base_ref=row.base_ref,
        classification=(
            ClassificationReport.model_validate(row.classification)
            if row.classification is not None
            else None
        ),
        impact=ImpactReport.model_validate(row.impact) if row.impact is not None else None,
        impact_sha256=row.impact_sha256,
        lint=lint_issues(row),
        diff=diff,
        diff_truncated=truncated,
    )


def adoption_views(conn: Connection, project: str | None = None) -> list[AdoptionView]:
    return [
        AdoptionView(
            id=a.id,
            project=a.project,
            package=a.package,
            version=a.version,
            previous_version=a.previous_version,
            worst_class=a.worst_class,
            impact_sha256=a.impact_sha256,
            adopted_by=a.adopted_by,
            adopted_at=a.adopted_at,
        )
        for a in registry.list_adoptions(conn, project=project)
    ]


def waiver_views(
    conn: Connection, project: str | None = None, state: str | None = None
) -> list[WaiverView]:
    now = _today().isoformat()
    return [
        WaiverView(
            id=w.id,
            key=w.key,
            project=w.project,
            path=w.path,
            number=w.number,
            reason=w.reason,
            expires=w.expires,
            expired=w.state == WAIVER_APPROVED_STATE and w.expires < now,
            state=w.state,
            requested_by=w.requested_by,
            approver=w.approver,
        )
        for w in registry.list_waivers(conn, project=project, state=state)
    ]


def drift_views(project: str) -> list[DriftView]:
    """Company packages the project uses, at its version and at the company's (brief 27.4)."""
    held = analysis.provider()
    scope = f"project:{project}"
    company = {p.name: p.version for p in held.effective("company").packages}
    pins = held.pins_of(scope)
    found: list[DriftView] = []
    for ref in held.effective(scope).packages:
        latest = company.get(ref.name)
        if latest is None:
            continue
        found.append(
            DriftView(
                package=ref.name,
                project_version=ref.version,
                company_version=latest,
                behind=version_tuple(ref.version) < version_tuple(latest),
                pinned=ref.name in pins,
            )
        )
    return sorted(found, key=lambda d: d.package)


def sample_test(conn: Connection, ref: str, sample: int = DEFAULT_SAMPLE) -> SampleTestView:
    """Re-check up to ``sample`` readable records of the draft's scope against the schema it makes.

    A record counts as newly non-conformant when it is now non-conformant and was not before.
    The records are the ones the viewer may read (ADR-0016), in id order.
    """
    row = _find(conn, ref)
    size = max(1, min(sample, MAX_SAMPLE))
    doc = analysis.parse_content(row.content)
    before, after, scope = analysis.trial_schemas(doc)
    if before is None:
        before = after
    clause, params = confidentiality.not_hidden("id")
    scoped = "" if scope == "company" else " AND scope = :scope"
    if scope != "company":
        params = {**params, "scope": scope}
    rows = conn.execute(
        text(
            "SELECT id, key, type, status, psets_json FROM cur_core_record "
            f"WHERE NOT voided AND {clause}{scoped} ORDER BY id LIMIT :n"
        ),
        {**params, "n": size},
    ).all()
    today = _today()
    newly_bad = newly_warn = fixed = 0
    examples: list[SampleExample] = []
    for rec in rows:
        psets: dict[str, Any] = json.loads(rec.psets_json)
        bound = bound_psets(conn, rec.type, rec.id)
        old = evaluate(before, rec.type, psets, state=rec.status, on=today, bound=bound)
        new = evaluate(after, rec.type, psets, state=rec.status, on=today, bound=bound)
        if new.status == "nonconformant" and old.status != "nonconformant":
            newly_bad += 1
            issue = next((i for i in new.issues if i.level == "nonconformant"), None)
            if issue is not None and len(examples) < MAX_EXAMPLES:
                examples.append(
                    SampleExample(
                        key=str(rec.key or rec.id),
                        path=issue.path,
                        rule=issue.rule,
                        message=issue.message,
                    )
                )
        elif new.status == "warning" and old.status == "ok":
            newly_warn += 1
        elif new.status == "ok" and old.status != "ok":
            fixed += 1
    return SampleTestView(
        package=row.key,
        scope=scope,
        sample=size,
        checked=len(rows),
        newly_nonconformant=newly_bad,
        newly_warning=newly_warn,
        fixed=fixed,
        examples=examples,
    )


__all__ = [
    "AdoptionView",
    "DriftView",
    "LintIssueView",
    "PackageDetail",
    "PackageSummary",
    "SampleTestView",
    "WaiverView",
    "adoption_views",
    "drift_views",
    "lint_issues",
    "package_detail",
    "package_summaries",
    "sample_test",
    "waiver_views",
]
