"""What a draft changes: the trial schema, the classification and the impact (brief 27.4, 27.5).

Everything here answers "what if" and writes nothing. ``analyse`` is what ``AnalyseSchemaPackage``
stores; ``project_impact`` is what an adopter reads before pinning a version. Both need the
process schema provider (``DirectorySchemaProvider``): the registry of packages in force is its.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.schema_provider import DirectorySchemaProvider, get_provider
from tl_schema.classify import ClassificationReport, classify_packages
from tl_schema.compile import SchemaCompileError
from tl_schema.effective import EffectiveSchema
from tl_schema.lint import LintIssue, lint_documents
from tl_schema.packages import PackageDoc, version_tuple
from tl_schema.registry import PackageError, PackageRegistry, parse_package

from tl_mod_schemareg.errors import InvalidSchemaPackageError
from tl_mod_schemareg.impact import impact_report
from tl_mod_schemareg.impact_types import ImpactFacts, ImpactReport, Reference
from tl_mod_schemareg.limits import MAX_CONTENT_BYTES, MAX_PROJECT, WAIVER_MAX_DAYS

_PROJECT = re.compile(r"[A-Za-z0-9_.-]+")
_PATH = re.compile(r"psets\.[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+")


@dataclass(frozen=True)
class Analysis:
    """The two reports of one draft, and what they were made against."""

    base_ref: str | None
    classification: ClassificationReport
    impact: ImpactReport


def provider() -> DirectorySchemaProvider:
    """The process schema provider, which must keep a package registry."""
    found = get_provider()
    if not isinstance(found, DirectorySchemaProvider):
        raise InvalidSchemaPackageError("this process has no package registry to compare with")
    return found


def parse_content(content: str) -> PackageDoc:
    """The package a text holds. Raises ``InvalidSchemaPackageError`` (size, YAML, shape)."""
    if len(content.encode("utf-8")) > MAX_CONTENT_BYTES:
        raise InvalidSchemaPackageError(
            f"the package is larger than {MAX_CONTENT_BYTES} bytes; split it or trim it"
        )
    try:
        doc = parse_package(content, source="package")
    except PackageError as exc:
        raise InvalidSchemaPackageError(str(exc)) from exc
    if doc.project is not None and (
        _PROJECT.fullmatch(doc.project) is None or len(doc.project) > MAX_PROJECT
    ):
        raise InvalidSchemaPackageError(f"project {doc.project!r} is not a usable project id")
    return doc


def package_waiver_problems(doc: PackageDoc, today: date) -> list[str]:
    """Why the waivers a package declares break the rules of a waiver (FANOUT D5).

    A waiver asked for through ``RequestWaiver`` ends on a date at most 366 days ahead. A waiver
    that a package carries must too: without an expiry it would relax a property for ever, and
    without a limit it would do so for years, with none of the approval a request goes through.
    """
    if doc.conformance is None:
        return []
    last = today + timedelta(days=WAIVER_MAX_DAYS)
    found: list[str] = []
    for waiver in doc.conformance.waivers:
        if waiver.expires is None:
            found.append(f"the waiver for {waiver.path} has no expiry")
        elif waiver.expires > last:
            found.append(f"the waiver for {waiver.path} ends after {last.isoformat()}")
    return found


def scope_of(doc: PackageDoc) -> str:
    """``company`` for a company package, ``project:<id>`` for the others."""
    return "company" if doc.kind == "company" else f"project:{doc.project}"


def base_of(registry: PackageRegistry, doc: PackageDoc) -> PackageDoc | None:
    """The highest version of the package below ``doc`` that is in force (file or published)."""
    below = [
        v for v in registry.versions(doc.package) if version_tuple(v) < version_tuple(doc.version)
    ]
    return registry.get(doc.package, below[-1]) if below else None


def lint_errors(doc: PackageDoc) -> list[LintIssue]:
    """The error-level lint issues of the package on its own."""
    return [issue for issue in lint_documents([doc]) if issue.severity == "error"]


def trial_schemas(doc: PackageDoc) -> tuple[EffectiveSchema | None, EffectiveSchema, str]:
    """``(schema before, schema with the package published, scope)``.

    Raises ``InvalidSchemaPackageError`` when the package does not fit (a name taken, a dependency
    missing, a rule of the schema compiler broken).
    """
    held = provider()
    scope = scope_of(doc)
    registry = held.registry()
    if registry.origin(doc.package, doc.version) is not None:
        raise InvalidSchemaPackageError(f"{doc.key()} is already in force in this registry")
    try:
        before: EffectiveSchema | None = held.effective(scope)
    except (PackageError, SchemaCompileError):
        before = None
    try:
        after = held.trial(scope, [doc])
    except (PackageError, SchemaCompileError) as exc:
        raise InvalidSchemaPackageError(f"{doc.key()} does not compose: {exc}") from exc
    return before, after, scope


def _property_paths(schema: EffectiveSchema | None) -> set[str]:
    if schema is None:
        return set()
    return {
        f"psets.{name}.{prop.relative_key()}"
        for name, pset in schema.psets.items()
        for prop in pset.all_properties()
    }


def gather_facts(conn: Connection, scope: str, *schemas: EffectiveSchema | None) -> ImpactFacts:
    """Value counts and references for the property paths of the given schemas.

    Counts are of the records the lowest reader may read (ADR-0016): the report is stored in the
    ledger for every reader, so it must not count what they cannot see.
    """
    wanted: set[str] = set()
    for schema in schemas:
        wanted |= _property_paths(schema)
    clause, params = confidentiality.not_hidden("record_id", confidentiality.LOWEST)
    scoped = "" if scope == "company" else " AND scope = :scope"
    if scope != "company":
        params = {**params, "scope": scope}
    rows = conn.execute(
        text(
            f"SELECT path, COUNT(DISTINCT record_id) AS n FROM cur_pset_values "
            f"WHERE {clause}{scoped} GROUP BY path"
        ),
        params,
    )
    counts = {str(r.path): int(r.n) for r in rows if str(r.path) in wanted}
    return ImpactFacts(value_counts=counts, references=find_references(conn, wanted))


#: ``(kind, name column, text columns, table)`` of the stored things that can name a path.
_SCANNED: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("rule", "key", ("when_json", "condition", "then_json"), "cur_rule"),
    ("enricher", "name", ("when_json", "properties_json"), "cur_enricher"),
    (
        "action",
        "name",
        ("applies_to_json", "parameters_json", "executor_config_json"),
        "cur_action_definition",
    ),
    ("mapping", "code", ("mapping_json",), "cur_documents_document_schema"),
    ("endpoint", "endpoint_id", ("definition_json",), "cur_inbound_endpoint_version"),
)
#: Reports of the platform and the property sets they read (a static list: reports are code).
REPORTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tag conformance report (tl tag report)", ("psets.",)),
)


def find_references(conn: Connection, wanted: set[str]) -> list[Reference]:
    """Things that name one of the ``wanted`` paths, found by reading what is stored."""
    found: list[Reference] = []
    for kind, name_column, columns, table in _SCANNED:
        select = ", ".join(f"CAST({c} AS TEXT) AS c{i}" for i, c in enumerate(columns))
        try:
            rows = conn.execute(
                text(f"SELECT {name_column} AS name, {select} FROM {table} LIMIT 5000")
            )
        except Exception:  # noqa: BLE001 - a ledger made before the table existed has no references
            continue
        for row in rows:
            body = " ".join(str(v) for v in row[1:] if v is not None)
            for path in sorted(set(_PATH.findall(body)) & wanted):
                found.append(Reference(kind=kind, name=str(row[0]), path=path))  # type: ignore[arg-type]
    for name, prefixes in REPORTS:
        for path in sorted(p for p in wanted if p.startswith(prefixes)):
            found.append(Reference(kind="report", name=name, path=path))
    return found


def analyse(conn: Connection, doc: PackageDoc) -> Analysis:
    """Classification against the version below, and the impact on the scope's records."""
    before, after, scope = trial_schemas(doc)
    registry = provider().registry()
    in_force = registry.versions(doc.package)
    if in_force and version_tuple(doc.version) <= version_tuple(in_force[-1]):
        raise ValueError(
            f"{doc.key()} must be a higher version than {in_force[-1]}, the highest in force"
        )
    base = base_of(registry, doc)
    classification = classify_packages(base, doc)
    facts = gather_facts(conn, scope, before, after)
    return Analysis(
        base_ref=base.key() if base is not None else None,
        classification=classification,
        impact=impact_report(before, after, facts),
    )


def project_impact(
    conn: Connection, project: str, package: str, version: str
) -> tuple[ImpactReport, EffectiveSchema, EffectiveSchema]:
    """What pinning ``package@version`` does to ``project``'s schema and records.

    Returns the report and the two schemas (before, after). Raises ``InvalidSchemaPackageError``
    when the pin does not compose.
    """
    held = provider()
    scope = f"project:{project}"
    before = held.effective(scope)
    current = dict(_pins(held, scope))
    current[package] = version
    try:
        after = held.trial(scope, pins=current)
    except (PackageError, SchemaCompileError) as exc:
        raise InvalidSchemaPackageError(f"{package}@{version} does not compose: {exc}") from exc
    facts = gather_facts(conn, scope, before, after)
    return impact_report(before, after, facts), before, after


def _pins(held: DirectorySchemaProvider, scope: str) -> Mapping[str, str]:
    """The pins the registry holds for ``scope``."""
    return held.pins_of(scope)
