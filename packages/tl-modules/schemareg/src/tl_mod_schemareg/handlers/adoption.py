"""``AdoptSchemaPackage``: a project pins a version of a company package (brief 27.4).

Adoption is per project. A version that only adds things (``additive``) is pinned on the word of
the administrator; anything else (constraining, renaming, a downgrade) needs the digest of the
project impact report the administrator read, which this handler computes again and compares
(the preview-token pattern: the pin is for the report that was shown, not for one made later).
The pin must compose: a project whose own packages depend on another version of the same company
package cannot pin this one until they are published against it.

``AdoptSchemaSet`` adopts one optional set of a company package for one project (owner decision,
2026-10-30: a superuser of the project adopts it in one action). A pin does not make an optional
set effective for a project; only an extension of the set does (``tl_schema.compose``). The command
therefore publishes a new version of the project's extension package that extends the set at the
company version it names and depends on that version, so the set is effective for that project
and for no other. It moves the project's company version only when the move is additive.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ConfigDict, Field
from tl_core.auth.errors import ForbiddenError
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork
from tl_schema.classify import classify_packages
from tl_schema.packages import PackageDoc, version_tuple
from tl_schema.registry import PackageError, PackageRegistry

from tl_mod_schemareg import analysis, registry
from tl_mod_schemareg.common import append, bump, correlated, scoped
from tl_mod_schemareg.errors import (
    AdoptionError,
    ImpactReviewRequiredError,
    InvalidSchemaPackageError,
)
from tl_mod_schemareg.handlers.packages import (
    AnalyseSchemaPackage,
    ApproveSchemaPackage,
    DraftSchemaPackage,
    PublishSchemaPackage,
    SubmitSchemaPackage,
    approve_reviewed,
    handle_analyse_schema_package,
    handle_draft_schema_package,
    handle_publish_schema_package,
    handle_submit_schema_package,
)
from tl_mod_schemareg.limits import MAX_PROJECT
from tl_mod_schemareg.names import ADOPTION, ADOPTION_PINNED, PUBLISHED

_PROJECT = re.compile(r"[A-Za-z0-9_.-]+")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


class AdoptSchemaPackage(Command):
    """Pin ``package@version`` for ``project``. The command's own scope is ignored."""

    model_config = ConfigDict(extra="forbid")

    project: str = Field(min_length=1, max_length=MAX_PROJECT)
    package: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=5, max_length=40)
    impact_sha256: str | None = Field(default=None, min_length=64, max_length=64)


def published_company(
    uow: UnitOfWork, reg: PackageRegistry, package: str, version: str
) -> PackageDoc:
    """``package@version`` when it is a company package in force whose ledger state allows adopting
    it. Raises ``AdoptionError``."""
    try:
        target = reg.get(package, version)
    except PackageError as exc:
        raise AdoptionError(f"{package}@{version} is not in force in this registry") from exc
    if target.kind != "company":
        raise AdoptionError(
            f"{target.key()} is a {target.kind} package: a project's own packages are in force "
            "from publication and are not pinned"
        )
    if reg.origin(package, version) == "ledger":
        row = registry.find_package(uow.conn(), package, version)
        if row is None or row.state != PUBLISHED:
            state = row.state if row is not None else "unknown"
            raise AdoptionError(f"{target.key()} is {state}; only a published version is adopted")
    return target


def handle_adopt_schema_package(uow: UnitOfWork, cmd: AdoptSchemaPackage) -> CommandResult:
    """Pin the version. Raises ``AdoptionError`` and ``ImpactReviewRequiredError``."""
    cmd = correlated(cmd)
    if _PROJECT.fullmatch(cmd.project) is None or _VERSION.fullmatch(cmd.version) is None:
        raise AdoptionError("the project or the version is not written in a form that can be used")
    scope = f"project:{cmd.project}"
    cmd = scoped(cmd, scope)
    held = analysis.provider()
    reg = held.registry()
    target = published_company(uow, reg, cmd.package, cmd.version)
    existing = registry.get_adoption(uow.conn(), cmd.project, cmd.package)
    if existing is not None and existing.version == cmd.version:
        raise AdoptionError(f"{cmd.project} already pins {target.key()}")
    in_force = {ref.name: ref.version for ref in held.effective(scope).packages}.get(cmd.package)
    worst = "downgrade"
    additive = False
    if in_force is None:
        worst, additive = "additive", True
    elif version_tuple(cmd.version) > version_tuple(in_force):
        report = classify_packages(reg.get(cmd.package, in_force), target)
        worst, additive = report.worst, report.auto_adoptable
    elif in_force == cmd.version:
        worst, additive = "additive", True  # an explicit pin of the version already in force
    try:
        impact, _before, _after = analysis.project_impact(
            uow.conn(), cmd.project, cmd.package, cmd.version
        )
    except InvalidSchemaPackageError as exc:
        raise AdoptionError(str(exc)) from exc
    if not additive and cmd.impact_sha256 != impact.digest:
        raise ImpactReviewRequiredError(
            f"adopting {target.key()} for {cmd.project} is a {worst} change; read the impact "
            f"report and pass its digest ({impact.digest}) to confirm"
        )
    payload = {
        "project": cmd.project,
        "package": cmd.package,
        "version": cmd.version,
        "previous_version": existing.version if existing is not None else in_force,
        "worst_class": worst,
        "impact_sha256": None if additive else impact.digest,
        "adopted_by": cmd.actor,
        "auto": False,
    }
    pinned = NewEvent(event_type=ADOPTION_PINNED, payload=payload)
    if existing is None:
        result = create_module_record(
            uow,
            cmd,
            record_type=ADOPTION,
            title=f"{cmd.project} pins {cmd.package}",
            key=f"{cmd.project}/{cmd.package}",
            composed_key=True,
            extra_events=[pinned],
        )
    else:
        done = append(uow, cmd, existing.id, ADOPTION, [pinned])
        result = CommandResult(
            stream_id=existing.id,
            key=existing.key,
            version=done.new_version,
            events=done.events,
        )
    bump()
    return result


class AdoptSchemaSet(Command):
    """Adopt the optional set ``pset`` of ``package@version`` for ``project``. The scope of the
    command is the project's (``project:<id>``), or ``company`` for an administrator."""

    model_config = ConfigDict(extra="forbid")

    project: str = Field(min_length=1, max_length=MAX_PROJECT)
    package: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=5, max_length=40)
    pset: str = Field(min_length=1, max_length=100)


def _extension_content(
    project: str, current: PackageDoc | None, package: str, version: str, pset: str
) -> str:
    """The text of the project's next extension: what it has, re-pointed at ``package@version``,
    with an (empty) extension of ``pset`` added. JSON is YAML, so the package parser reads it."""
    if current is None:
        data: dict[str, Any] = {
            "package": f"x.{project}",
            "version": "1.0.0",
            "kind": "extension",
            "description": f"Project {project} extension: sets adopted from {package}.",
            "project": project,
            "depends": {},
            "extends": [],
        }
    else:
        data = current.model_dump(mode="json", exclude_defaults=True)
        major, minor, _patch = (int(part) for part in current.version.split("."))
        data["version"] = f"{major}.{minor + 1}.0"
        data.setdefault("extends", [])
        for entry in data["extends"]:
            if entry["ref"].partition("@")[0] == package:
                entry["ref"] = f"{package}@{version}#{entry['ref'].partition('#')[2]}"
    data["depends"] = {**data.get("depends", {}), package: version}
    data["extends"].append({"ref": f"{package}@{version}#{pset}"})
    return json.dumps(data, indent=2)


def handle_adopt_schema_set(uow: UnitOfWork, cmd: AdoptSchemaSet) -> CommandResult:
    """Publish the project's extension with ``pset`` extended. Raises ``AdoptionError``,
    ``ForbiddenError`` (a command scope that is not the project's) and the errors of the package
    commands it runs (a lint error, an extension that does not compose)."""
    cmd = correlated(cmd)
    if _PROJECT.fullmatch(cmd.project) is None or _VERSION.fullmatch(cmd.version) is None:
        raise AdoptionError("the project or the version is not written in a form that can be used")
    scope = f"project:{cmd.project}"
    if cmd.scope not in ("company", scope):
        raise ForbiddenError(f"AdoptSchemaSet for {cmd.project} must be sent in the scope {scope}")
    held = analysis.provider()
    reg = held.registry()
    target = published_company(uow, reg, cmd.package, cmd.version)
    base = target.psets.get(cmd.pset)
    if base is None:
        raise AdoptionError(f"{target.key()} has no set {cmd.pset}")
    if base.adoption != "optional":
        raise AdoptionError(f"{cmd.pset} is not optional: every project has it")
    effective = held.effective(scope)
    if effective.find_pset(cmd.pset) is not None:
        raise AdoptionError(f"{cmd.project} has already adopted {cmd.pset}")
    in_force = {ref.name: ref.version for ref in effective.packages}.get(cmd.package)
    if in_force is not None and in_force != cmd.version:
        if version_tuple(cmd.version) < version_tuple(in_force):
            raise AdoptionError(
                f"{cmd.project} is on {cmd.package}@{in_force}, above {cmd.version}; "
                "adopt the set from the version it is on"
            )
        report = classify_packages(reg.get(cmd.package, in_force), target)
        if not report.auto_adoptable:
            raise AdoptionError(
                f"moving {cmd.project} from {cmd.package}@{in_force} to {cmd.version} is a "
                f"{report.worst} change; an administrator adopts that version after reading "
                "the impact report"
            )
    try:
        extensions = [d for d in reg.adopted(scope, held.pins_of(scope)) if d.kind == "extension"]
    except PackageError as exc:
        raise AdoptionError(str(exc)) from exc
    if len(extensions) > 1:
        raise AdoptionError(
            f"{cmd.project} has several extension packages; an administrator publishes "
            f"the extension of {cmd.pset}"
        )
    content = _extension_content(
        cmd.project, extensions[0] if extensions else None, cmd.package, cmd.version, cmd.pset
    )
    common = {
        "actor": cmd.actor,
        "source": cmd.source,
        "correlation_id": cmd.correlation_id,
        "causation_id": cmd.causation_id,
    }
    drafted = handle_draft_schema_package(
        uow,
        DraftSchemaPackage(
            scope=scope,
            content=content,
            changelog=f"Adopt {cmd.pset} of {cmd.package}@{cmd.version}.",
            **common,
        ),
    )
    events = list(drafted.events)
    package_id = drafted.stream_id
    analysed = handle_analyse_schema_package(
        uow, AnalyseSchemaPackage(scope=scope, package_id=package_id, **common)
    )
    submitted = handle_submit_schema_package(
        uow, SubmitSchemaPackage(scope=scope, package_id=package_id, **common)
    )
    events.extend([*analysed.events, *submitted.events])
    row = registry.get_package(uow.conn(), package_id)
    assert row is not None  # just drafted
    approved = approve_reviewed(
        uow, ApproveSchemaPackage(scope=scope, package_id=package_id, **common), row
    )
    events.extend(approved.events)
    published = handle_publish_schema_package(
        uow, PublishSchemaPackage(scope=scope, package_id=package_id, **common)
    )
    events.extend(published.events)
    return CommandResult(
        stream_id=package_id, key=published.key, version=published.version, events=events
    )
