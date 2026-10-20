"""``AdoptSchemaPackage``: a project pins a version of a company package (brief 27.4).

Adoption is per project. A version that only adds things (``additive``) is pinned on the word of
the administrator; anything else (constraining, renaming, a downgrade) needs the digest of the
project impact report the administrator read, which this handler computes again and compares
(the preview-token pattern: the pin is for the report that was shown, not for one made later).
The pin must compose: a project whose own packages depend on another version of the same company
package cannot pin this one until they are published against it.
"""

from __future__ import annotations

import re

from pydantic import ConfigDict, Field
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork
from tl_schema.classify import classify_packages
from tl_schema.packages import version_tuple
from tl_schema.registry import PackageError

from tl_mod_schemareg import analysis, registry
from tl_mod_schemareg.common import append, bump, correlated
from tl_mod_schemareg.errors import (
    AdoptionError,
    ImpactReviewRequiredError,
    InvalidSchemaPackageError,
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


def handle_adopt_schema_package(uow: UnitOfWork, cmd: AdoptSchemaPackage) -> CommandResult:
    """Pin the version. Raises ``AdoptionError`` and ``ImpactReviewRequiredError``."""
    cmd = correlated(cmd)
    if _PROJECT.fullmatch(cmd.project) is None or _VERSION.fullmatch(cmd.version) is None:
        raise AdoptionError("the project or the version is not written in a form that can be used")
    scope = f"project:{cmd.project}"
    cmd = cmd.model_copy(update={"scope": scope})
    held = analysis.provider()
    reg = held.registry()
    try:
        target = reg.get(cmd.package, cmd.version)
    except PackageError as exc:
        raise AdoptionError(
            f"{cmd.package}@{cmd.version} is not in force in this registry"
        ) from exc
    if target.kind != "company":
        raise AdoptionError(
            f"{target.key()} is a {target.kind} package: a project's own packages are in force "
            "from publication and are not pinned"
        )
    if reg.origin(cmd.package, cmd.version) == "ledger":
        row = registry.find_package(uow.conn(), cmd.package, cmd.version)
        if row is None or row.state != PUBLISHED:
            state = row.state if row is not None else "unknown"
            raise AdoptionError(f"{target.key()} is {state}; only a published version is adopted")
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
