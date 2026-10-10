"""Validate a type package: layout, lock, lint, compile, examples, settings (brief 31.1).

``validate_package`` returns the ``TypeRegistration`` a valid package would get (with an empty
``owner``, which ``sync`` fills in) or every ``TypeIssue`` found. It reads files and writes
nothing. ``describe_package`` gives the identity (type ref, content hash, location) of any package
directory, valid or not, which a quarantine event needs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError
from tl_schema.compile import SchemaCompileError, compile_psets

from tl_core.extypes.compile import (
    MAX_PATTERN,
    TYPE_FILE,
    body_issues,
    compile_type,
    to_package_doc,
)
from tl_core.extypes.lock import (
    LOCK_NAME,
    compute_lock,
    content_hash,
    lock_issues,
    package_files,
)
from tl_core.extypes.model import CompiledType
from tl_core.extypes.names import (
    Coordinates,
    LayoutError,
    coordinates,
    invalid_ref,
    package_coordinates,
)
from tl_core.extypes.types import TypeIssue, TypeRegistration
from tl_core.schema_provider import SchemaProvider
from tl_core.settings.types import SettingDefinition
from tl_core.workflow.loader import WorkflowError, parse_workflow, semantic_problems

SETTINGS_FILE = "settings.yaml"
WORKFLOW_FILE = "workflow.yaml"
EXAMPLES_DIR = "examples"
_EXAMPLE_SUFFIXES = (".json", ".yaml", ".yml")


@dataclass(frozen=True)
class Described:
    """Identity of a package directory: where it is and what its files hash to."""

    type_ref: str
    location_uri: str
    content_hash: str
    coords: Coordinates | None
    layout: list[TypeIssue]


def describe_package(path: Path, root: Path | None = None) -> Described:
    """Identity of the package at ``path``. The hash is of the files as found, not of ``type.lock``.

    With a ``root`` the path must be ``<root>/<namespace>/<Name>/<version>``; without one the last
    three path segments are used. A path that is not a package path gets the stand-in ref
    ``invalid:<relative path>`` and a ``layout`` issue.
    """
    base = path.resolve()
    actual, listing = compute_lock(base)
    layout = list(listing)
    coords: Coordinates | None = None
    try:
        if root is not None:
            coords = package_coordinates(root, path)
        else:
            coords = coordinates(base.parent.parent.name, base.parent.name, base.name)
        type_ref = coords.type_ref
    except LayoutError as exc:
        layout.append(TypeIssue(kind="layout", path=None, detail=str(exc)))
        type_ref = invalid_ref(root, path) if root is not None else f"invalid:{base.name}"
    return Described(type_ref, base.as_uri(), content_hash(actual), coords, layout)


def read_settings(
    package: Path, coords: Coordinates
) -> tuple[list[SettingDefinition], list[TypeIssue]]:
    """``settings.yaml`` as setting definitions (none when absent), with the namespace rule.

    Every key starts with ``<namespace>.``; ``owner`` defaults to the type name and must equal it;
    a secret setting is refused (FANOUT D4). Registering the definitions with the settings
    registry is a separate step (``tl_core.settings.register_definitions``).
    """
    file = package / SETTINGS_FILE
    if not file.is_file():
        return [], []
    issue = _settings_issue
    try:
        data: Any = yaml.safe_load(file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        return [], [issue(f"not readable YAML: {exc}")]
    raw: Any = cast("dict[str, Any]", data).get("settings") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return [], [issue("must be a mapping with a 'settings' list")]
    rows = cast("list[Any]", raw)
    definitions: list[SettingDefinition] = []
    issues: list[TypeIssue] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        where = f"settings[{index}]"
        if not isinstance(row, dict):
            issues.append(issue(f"{where}: must be a mapping"))
            continue
        merged: dict[str, Any] = {"owner": coords.type_name, **cast("dict[str, Any]", row)}
        try:
            definition = SettingDefinition.model_validate(merged)
        except ValidationError as exc:
            detail = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
            )
            issues.append(issue(f"{where}: {detail}"))
            continue
        if not definition.key.startswith(f"{coords.namespace}."):
            issues.append(
                issue(f"{where}: key {definition.key!r} must start with {coords.namespace}.")
            )
        elif definition.owner != coords.type_name:
            issues.append(issue(f"{where}: owner must be {coords.type_name}"))
        elif (
            definition.validation is not None
            and definition.validation.pattern is not None
            and len(definition.validation.pattern) > MAX_PATTERN
        ):
            issues.append(issue(f"{where}: validation.pattern is longer than {MAX_PATTERN}"))
        elif definition.sensitivity == "secret":
            issues.append(
                issue(f"{where}: secret settings are not available (a vault is a human gate)")
            )
        elif definition.key in seen:
            issues.append(issue(f"{where}: key {definition.key!r} is declared twice"))
        else:
            seen.add(definition.key)
            definitions.append(definition)
    return definitions, issues


def _settings_issue(detail: str) -> TypeIssue:
    return TypeIssue(kind="settings", path=SETTINGS_FILE, detail=detail)


def _check_workflow(package: Path, coords: Coordinates) -> list[TypeIssue]:
    file = package / WORKFLOW_FILE
    if not file.is_file():
        return []
    try:
        definition = parse_workflow(file.read_text(encoding="utf-8"), source=WORKFLOW_FILE)
    except (OSError, UnicodeDecodeError, WorkflowError) as exc:
        return [TypeIssue(kind="compile", path=WORKFLOW_FILE, detail=str(exc))]
    problems = semantic_problems(definition)
    if definition.record_type != coords.type_name:
        problems.append(f"record_type must be {coords.type_name}, not {definition.record_type}")
    return [TypeIssue(kind="compile", path=WORKFLOW_FILE, detail=p) for p in problems]


def _check_examples(package: Path, compiled: CompiledType) -> list[TypeIssue]:
    directory = package / EXAMPLES_DIR
    if not directory.is_dir():
        return []
    issues: list[TypeIssue] = []
    for file in sorted(directory.rglob("*")):
        if not file.is_file() or file.suffix not in _EXAMPLE_SUFFIXES:
            continue
        relative = file.relative_to(package).as_posix()
        try:
            text = file.read_text(encoding="utf-8")
            body: Any = json.loads(text) if file.suffix == ".json" else yaml.safe_load(text)
        except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
            issues.append(TypeIssue(kind="example", path=relative, detail=f"not readable: {exc}"))
            continue
        for problem in body_issues(compiled, body):
            issues.append(TypeIssue(kind="example", path=relative, detail=problem))
    return issues


def _collision(compiled: CompiledType, provider: SchemaProvider) -> list[TypeIssue]:
    """The pset name must not belong to a platform or company package of the provider."""
    schema = provider.effective("company")
    pset = schema.psets.get(compiled.pset)
    if pset is not None and pset.package != compiled.type_name:
        detail = f"pset {compiled.pset} already belongs to {pset.package}@{pset.version}"
        return [TypeIssue(kind="conflict", path=TYPE_FILE, detail=detail)]
    return []


def validate_package(
    path: Path,
    *,
    provider: SchemaProvider,
    root: Path | None = None,
    described: Described | None = None,
) -> tuple[TypeRegistration | None, list[TypeIssue]]:
    """Validate the package at ``path``; see the module docstring.

    Never raises: an unexpected failure while reading the package (a vanished file, a LinkML
    error) is a ``compile`` issue, so one bad package cannot stop a sync of the others.
    ``described`` is the identity ``describe_package`` already gave, so the files are read once.

    Checks, in order, collecting every issue: layout (path segments, ``type.yaml`` present, no
    links, sizes), ``type.lock`` against the files, LinkML lint, compile into the effective schema
    (a one-pset package must compile and its pset name must not belong to another package of
    ``provider``), ``form.yaml``, ``workflow.yaml``, ``settings.yaml`` and every file in
    ``examples/``. ``unsupported`` marks directory-backed storage.
    """
    try:
        return _validate(path, provider, root, described)
    except Exception as exc:
        detail = f"validation failed unexpectedly: {type(exc).__name__}: {str(exc)[:300]}"
        return None, [TypeIssue(kind="compile", path=None, detail=detail)]


def _validate(
    path: Path, provider: SchemaProvider, root: Path | None, known: Described | None
) -> tuple[TypeRegistration | None, list[TypeIssue]]:
    described = known if known is not None else describe_package(path, root)
    issues = list(described.layout)
    if not (path / TYPE_FILE).is_file():
        issues.append(TypeIssue(kind="layout", path=TYPE_FILE, detail="type.yaml is missing"))
    issues.extend(lock_issues(path))
    compiled: CompiledType | None = None
    if described.coords is not None and (path / TYPE_FILE).is_file():
        compiled, compile_issues = compile_type(path, described.coords)
        issues.extend(compile_issues)
    if compiled is not None and described.coords is not None:
        try:
            compile_psets([to_package_doc(compiled)])
        except (SchemaCompileError, ValidationError, ValueError) as exc:
            issues.append(TypeIssue(kind="compile", path=TYPE_FILE, detail=str(exc)[:500]))
        issues.extend(_collision(compiled, provider))
        issues.extend(_check_workflow(path, described.coords))
        _, settings_issues = read_settings(path, described.coords)
        issues.extend(settings_issues)
        issues.extend(_check_examples(path, compiled))
    if issues or compiled is None or described.coords is None:
        return None, _unique(issues)
    return (
        TypeRegistration(
            namespace=compiled.namespace,
            name=compiled.name,
            version=compiled.version,
            type_ref=compiled.type_ref,
            location_uri=described.location_uri,
            content_hash=described.content_hash,
            owner="",
            status="active",
            storage_mode=compiled.storage_mode,
            index_fields=compiled.index_fields,
            schema_hash=compiled.schema_hash(),
        ),
        [],
    )


def _unique(issues: list[TypeIssue]) -> list[TypeIssue]:
    seen: set[tuple[str, str | None, str]] = set()
    out: list[TypeIssue] = []
    for issue in issues:
        key = (issue.kind, issue.path, issue.detail)
        if key not in seen:
            seen.add(key)
            out.append(issue)
    return out


__all__ = [
    "LOCK_NAME",
    "Described",
    "describe_package",
    "package_files",
    "read_settings",
    "validate_package",
]
