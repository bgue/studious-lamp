"""Compile package documents into effective psets and enforce what projects cannot do (brief 6.3).

``compile_psets`` takes the package documents a scope adopts (company packages at pinned versions,
that project's extension and project packages) and returns the resolved psets. Every row of the
"projects cannot" table is a ``SchemaCompileError`` with a stable ``rule`` code:

====================  ==========================================================================
rule                  what it rejects (brief 6.3 table row)
====================  ==========================================================================
``locked``            touching a locked pset or a locked property beyond filling values
``closed_list``       adding values to a ``closed`` value list
``crosswalk``         adding a value to an ``extensible`` list without a valid crosswalk
``loosen``            lowering enforcement, dropping required states, widening a range or
                      changing a pattern a company property already has
``shadow``            a custom property or project list that reuses a company name
``custom_not_allowed``  custom-section properties on a pset that forbids them
``custom_limit``      more custom-section properties than ``max_properties``
``materialize``       promoting a custom or project property to a typed column
``unknown_target``    extending a pset or package that is not adopted at that version
``unknown_property``  tightening, defaulting or labelling a property the pset does not have
``unknown_list``      adding values to a code list the pset does not use
``unknown_range``     a ``range`` that is neither a property kind nor a known code list
``duplicate``         the same pset, list or value defined twice
``pin``               a dependency pin that disagrees with an ``extends`` reference
``invalid``           any other inconsistency in a document
====================  ==========================================================================

Renaming or removing a company property, and changing a property's type, unit or meaning, are not
expressible: the document models forbid those keys, so ``tl_schema.registry`` rejects them at load.
Enrichment and source layers are never part of a package; writes to them are refused by the pset
command handler.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from tl_schema.effective import (
    ALWAYS,
    ENFORCEMENT_RANK,
    EffectiveProperty,
    EffectivePset,
    PropertyLayer,
    states_cover,
)
from tl_schema.forms import EnumValue, FieldKind
from tl_schema.packages import (
    NAME_PATTERN,
    PROPERTY_KINDS,
    CodeList,
    CodeValue,
    ExtendsDef,
    PackageDoc,
    PropertyDef,
    PsetDef,
    TightenDef,
)

PROJECT_PSET_PREFIX = "prj."
_NUMERIC_KINDS = ("int", "decimal", "quantity")


class SchemaCompileError(ValueError):
    """A package set that breaks a rule. ``rule`` is one of the codes in the module docstring."""

    def __init__(self, rule: str, message: str, *, package: str | None = None) -> None:
        super().__init__(f"{rule}: {message}")
        self.rule = rule
        self.package = package


def humanise(name: str) -> str:
    """``size_in`` becomes ``Size in``."""
    return name.replace("_", " ").capitalize()


def _enum_meanings(values: Sequence[CodeValue]) -> dict[str, str]:
    return {v.code: v.meaning for v in values if v.meaning is not None}


def _enum_values(code_list: CodeList) -> list[EnumValue]:
    return [EnumValue(code=v.code, label=v.label, crosswalk=v.crosswalk) for v in code_list.values]


def _resolve_property(
    name: str,
    pdef: PropertyDef,
    *,
    pset_enforcement: str,
    layer: PropertyLayer,
    origin: str,
    order: int,
    lists: dict[str, CodeList],
) -> EffectiveProperty:
    """Resolve one ``PropertyDef`` against the code lists visible to it."""
    kind: str
    code_list: str | None = None
    enum_values: list[EnumValue] | None = None
    enum_meanings: dict[str, str] = {}
    policy = pdef.value_list_policy
    if pdef.range in PROPERTY_KINDS:
        kind = pdef.range
        if policy is not None:
            raise SchemaCompileError(
                "invalid", f"{origin} {name}: value_list_policy needs a code-list range"
            )
    elif pdef.range in lists:
        kind = "enum"
        code_list = pdef.range
        listing = lists[pdef.range]
        if not listing.values:
            raise SchemaCompileError(
                "invalid", f"{origin} {name}: code list {pdef.range} has no values"
            )
        enum_values = _enum_values(listing)
        enum_meanings = _enum_meanings(listing.values)
        policy = policy or listing.value_list_policy
    else:
        raise SchemaCompileError(
            "unknown_range",
            f"{origin} {name}: range {pdef.range!r} is not a property kind or a known code list",
        )
    if kind == "quantity" and pdef.unit is None:
        raise SchemaCompileError("invalid", f"{origin} {name}: a quantity needs a unit")
    if (pdef.minimum is not None or pdef.maximum is not None) and kind not in _NUMERIC_KINDS:
        raise SchemaCompileError("invalid", f"{origin} {name}: minimum/maximum need a numeric kind")
    if pdef.pattern is not None and kind not in ("string", "text", "ref"):
        raise SchemaCompileError("invalid", f"{origin} {name}: pattern needs a string kind")
    if pdef.minimum is not None and pdef.maximum is not None and pdef.minimum > pdef.maximum:
        raise SchemaCompileError("invalid", f"{origin} {name}: minimum is above maximum")
    if kind == "json" and pdef.materialize:
        raise SchemaCompileError("invalid", f"{origin} {name}: a json property cannot be promoted")
    states = list(pdef.required_in_states)
    if pdef.required and ALWAYS not in states:
        states.insert(0, ALWAYS)
    prop = EffectiveProperty(
        name=name,
        layer=layer,
        label=pdef.label or humanise(name),
        description=pdef.description,
        kind=cast(FieldKind, kind),
        unit=pdef.unit.ucum if pdef.unit else None,
        code_list=code_list,
        enum_values=enum_values,
        enum_meanings=enum_meanings,
        value_list_policy=policy,
        required_in_states=states,
        enforcement=pdef.enforcement or cast(Any, pset_enforcement),
        materialize=pdef.materialize,
        minimum=pdef.minimum,
        maximum=pdef.maximum,
        pattern=pdef.pattern,
        default=pdef.default,
        exact_mappings=list(pdef.exact_mappings),
        origin=origin,
        order=order,
    )
    if prop.default is not None:
        _check_default(prop)
    return prop


def _check_default(prop: EffectiveProperty) -> None:
    value = prop.default
    kind = prop.kind
    ok: bool
    if kind == "bool":
        ok = isinstance(value, bool)
    elif kind == "int":
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif kind in ("decimal", "quantity"):
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif kind == "json":
        ok = True
    else:
        ok = isinstance(value, str)
    if ok and kind == "enum":
        codes = {v.code for v in prop.enum_values or []}
        ok = value in codes
    if not ok:
        raise SchemaCompileError(
            "invalid", f"{prop.origin} {prop.name}: default {value!r} does not fit kind {kind}"
        )


def _company_lists(
    doc: PackageDoc, index: dict[tuple[str, str], PackageDoc]
) -> dict[str, CodeList]:
    """Code lists a company document can use: its own plus those of the packages it depends on."""
    lists: dict[str, CodeList] = {}
    for dep_name, dep_version in sorted(doc.depends.items()):
        dep = index.get((dep_name, dep_version))
        if dep is None or dep.kind != "company":
            raise SchemaCompileError(
                "unknown_target",
                f"{doc.key()} depends on {dep_name}@{dep_version}, which is not adopted",
                package=doc.key(),
            )
        lists.update(dep.code_lists)
    lists.update(doc.code_lists)
    return lists


def _build_pset(
    name: str,
    pdef: PsetDef,
    *,
    layer: str,
    doc: PackageDoc,
    lists: dict[str, CodeList],
) -> EffectivePset:
    if layer == "standard" and pdef.enforcement == "locked" and pdef.custom_section.allowed:
        # A locked pset has no custom section; the default (allowed) is switched off, but an
        # explicit allow with a locked pset is a contradiction.
        explicit = "custom_section" in pdef.model_fields_set
        if explicit:
            raise SchemaCompileError(
                "invalid",
                f"{doc.key()} {name}: a locked pset cannot allow a custom section",
                package=doc.key(),
            )
    properties: dict[str, EffectiveProperty] = {}
    for order, (prop_name, prop_def) in enumerate(pdef.properties.items()):
        if layer == "project" and prop_def.materialize:
            raise SchemaCompileError(
                "materialize",
                f"{doc.key()} {name}.{prop_name}: only company standard properties can be promoted",
                package=doc.key(),
            )
        properties[prop_name] = _resolve_property(
            prop_name,
            prop_def,
            pset_enforcement=pdef.enforcement,
            layer="standard" if layer == "standard" else "project",
            origin=doc.key(),
            order=order,
            lists=lists,
        )
    custom_allowed = pdef.custom_section.allowed and pdef.enforcement != "locked"
    if layer == "project":
        custom_allowed = False
    return EffectivePset(
        name=name if layer == "standard" else f"{PROJECT_PSET_PREFIX}{name}",
        layer="standard" if layer == "standard" else "project",
        label=pdef.label or humanise(name),
        description=pdef.description,
        package=doc.package,
        version=doc.version,
        applies_to=list(pdef.applies_to),
        class_filter=pdef.class_filter,
        enforcement=pdef.enforcement,
        adoption=pdef.adoption,
        custom_allowed=custom_allowed,
        custom_max=pdef.custom_section.max_properties if custom_allowed else None,
        properties=properties,
    )


def _tighten(prop: EffectiveProperty, change: TightenDef, ext: PackageDoc) -> EffectiveProperty:
    where = f"{ext.key()} {prop.name}"
    update: dict[str, Any] = {}
    if change.required_in_states is not None:
        if not states_cover(change.required_in_states, prop.required_in_states):
            dropped = [s for s in prop.required_in_states if s not in change.required_in_states]
            raise SchemaCompileError(
                "loosen",
                f"{where}: required_in_states drops {', '.join(dropped)}",
                package=ext.key(),
            )
        update["required_in_states"] = list(change.required_in_states)
    if change.enforcement is not None:
        if change.enforcement == "locked":
            raise SchemaCompileError(
                "loosen", f"{where}: a project cannot lock a property", package=ext.key()
            )
        if ENFORCEMENT_RANK[change.enforcement] < ENFORCEMENT_RANK[prop.enforcement]:
            raise SchemaCompileError(
                "loosen",
                f"{where}: enforcement {change.enforcement} is below {prop.enforcement}",
                package=ext.key(),
            )
        update["enforcement"] = change.enforcement
    if change.minimum is not None or change.maximum is not None:
        if prop.kind not in _NUMERIC_KINDS:
            raise SchemaCompileError(
                "invalid", f"{where}: minimum/maximum need a numeric kind", package=ext.key()
            )
    if change.minimum is not None:
        if prop.minimum is not None and change.minimum < prop.minimum:
            raise SchemaCompileError(
                "loosen",
                f"{where}: minimum {change.minimum} is below the company minimum {prop.minimum}",
                package=ext.key(),
            )
        update["minimum"] = change.minimum
    if change.maximum is not None:
        if prop.maximum is not None and change.maximum > prop.maximum:
            raise SchemaCompileError(
                "loosen",
                f"{where}: maximum {change.maximum} is above the company maximum {prop.maximum}",
                package=ext.key(),
            )
        update["maximum"] = change.maximum
    if change.pattern is not None:
        if prop.kind not in ("string", "text", "ref"):
            raise SchemaCompileError(
                "invalid", f"{where}: pattern needs a string kind", package=ext.key()
            )
        if prop.pattern is not None and change.pattern != prop.pattern:
            raise SchemaCompileError(
                "loosen",
                f"{where}: the company pattern {prop.pattern!r} cannot be replaced",
                package=ext.key(),
            )
        update["pattern"] = change.pattern
    tightened = prop.model_copy(update=update)
    low, high = tightened.minimum, tightened.maximum
    if low is not None and high is not None and low > high:
        raise SchemaCompileError("invalid", f"{where}: minimum is above maximum", package=ext.key())
    return tightened


def _add_values(
    pset: EffectivePset, list_name: str, values: Sequence[CodeValue], ext: PackageDoc
) -> EffectivePset:
    users = [p for p in pset.properties.values() if p.code_list == list_name]
    if not users:
        raise SchemaCompileError(
            "unknown_list",
            f"{ext.key()}: pset {pset.name} has no property using code list {list_name}",
            package=ext.key(),
        )
    properties = dict(pset.properties)
    for prop in users:
        policy = prop.value_list_policy
        if policy == "closed":
            raise SchemaCompileError(
                "closed_list",
                f"{ext.key()}: {pset.name}.{prop.name} uses the closed list {list_name}",
                package=ext.key(),
            )
        existing = list(prop.enum_values or [])
        meanings = dict(prop.enum_meanings)
        codes = {v.code for v in existing}
        company_codes = set(codes)
        for value in values:
            if value.code in codes:
                raise SchemaCompileError(
                    "duplicate",
                    f"{ext.key()}: code {value.code} already exists in {list_name}",
                    package=ext.key(),
                )
            if policy == "extensible" and value.crosswalk not in company_codes:
                raise SchemaCompileError(
                    "crosswalk",
                    f"{ext.key()}: {value.code} needs a crosswalk to a company code of "
                    f"{list_name} (or 'other'), got {value.crosswalk!r}",
                    package=ext.key(),
                )
            if (
                policy == "project_defined"
                and value.crosswalk is not None
                and value.crosswalk not in company_codes
            ):
                raise SchemaCompileError(
                    "crosswalk",
                    f"{ext.key()}: crosswalk {value.crosswalk!r} of {value.code} is not a code "
                    f"of {list_name}",
                    package=ext.key(),
                )
            codes.add(value.code)
            existing.append(
                EnumValue(code=value.code, label=value.label, crosswalk=value.crosswalk)
            )
            meanings.update(_enum_meanings([value]))
        properties[prop.name] = prop.model_copy(
            update={"enum_values": existing, "enum_meanings": meanings}
        )
    return pset.model_copy(update={"properties": properties})


def _apply_extension(
    pset: EffectivePset,
    entry: ExtendsDef,
    ext: PackageDoc,
    base_doc: PackageDoc,
    company_lists: dict[str, CodeList],
) -> EffectivePset:
    key = ext.key()
    if pset.extension is not None:
        raise SchemaCompileError(
            "duplicate", f"{key}: pset {pset.name} is already extended by {pset.extension}"
        )
    if pset.enforcement == "locked":
        raise SchemaCompileError(
            "locked", f"{key}: pset {pset.name} is locked and cannot be extended", package=key
        )

    properties = dict(pset.properties)
    for name in [*entry.tighten, *entry.defaults, *entry.labels]:
        if name not in properties:
            raise SchemaCompileError(
                "unknown_property", f"{key}: pset {pset.name} has no property {name}", package=key
            )
    for name in [*entry.tighten, *entry.defaults, *entry.labels]:
        if properties[name].enforcement == "locked":
            raise SchemaCompileError(
                "locked", f"{key}: property {pset.name}.{name} is locked", package=key
            )
    for name, change in entry.tighten.items():
        properties[name] = _tighten(properties[name], change, ext)
    for name, value in entry.defaults.items():
        candidate = properties[name].model_copy(update={"default": value})
        _check_default(candidate)
        properties[name] = candidate
    for name, label in entry.labels.items():
        properties[name] = properties[name].model_copy(update={"label": label})
    result = pset.model_copy(update={"properties": properties, "extension": key})

    for list_name, values in entry.add_values.items():
        if list_name not in company_lists:
            raise SchemaCompileError(
                "unknown_list", f"{key}: {base_doc.key()} has no code list {list_name}", package=key
            )
        result = _add_values(result, list_name, values, ext)

    if entry.custom:
        if not pset.custom_allowed:
            raise SchemaCompileError(
                "custom_not_allowed",
                f"{key}: pset {pset.name} does not allow a custom section",
                package=key,
            )
        if pset.custom_max is not None and len(entry.custom) > pset.custom_max:
            raise SchemaCompileError(
                "custom_limit",
                f"{key}: {len(entry.custom)} custom properties exceed the limit "
                f"of {pset.custom_max}",
                package=key,
            )
        lists = {**company_lists, **ext.code_lists}
        for list_name in ext.code_lists:
            if list_name in company_lists:
                raise SchemaCompileError(
                    "shadow", f"{key}: code list {list_name} reuses a company name", package=key
                )
        custom: dict[str, EffectiveProperty] = {}
        start = len(pset.properties)
        for offset, (name, pdef) in enumerate(entry.custom.items()):
            if NAME_PATTERN.fullmatch(name) is None or "__" in name:
                raise SchemaCompileError(
                    "invalid", f"{key}: custom property name {name!r} is not lower snake case"
                )
            if name in pset.properties:
                raise SchemaCompileError(
                    "shadow",
                    f"{key}: custom property {name} reuses a company property of {pset.name}",
                    package=key,
                )
            if pdef.materialize:
                raise SchemaCompileError(
                    "materialize",
                    f"{key}: custom property {name} cannot be promoted to a column",
                    package=key,
                )
            if pdef.enforcement == "locked":
                raise SchemaCompileError(
                    "locked", f"{key}: a project cannot lock custom property {name}", package=key
                )
            custom[name] = _resolve_property(
                name,
                pdef,
                pset_enforcement="advisory",
                layer="custom",
                origin=key,
                order=start + offset,
                lists=lists,
            )
        result = result.model_copy(update={"custom": custom})
    return result


def compile_psets(docs: Sequence[PackageDoc]) -> dict[str, EffectivePset]:
    """Resolve company, extension and project documents into effective psets keyed by name.

    ``docs`` must already be the adopted set: exactly one version per package. The result is sorted
    by pset name. Raises ``SchemaCompileError`` for the first rule broken.
    """
    seen: set[str] = set()
    for doc in docs:
        if doc.package in seen:
            raise SchemaCompileError(
                "duplicate", f"package {doc.package} appears twice", package=doc.key()
            )
        seen.add(doc.package)
    index: dict[tuple[str, str], PackageDoc] = {(d.package, d.version): d for d in docs}
    psets: dict[str, EffectivePset] = {}
    base_docs: dict[str, PackageDoc] = {}

    for doc in sorted((d for d in docs if d.kind == "company"), key=lambda d: d.package):
        lists = _company_lists(doc, index)
        for name, pdef in doc.psets.items():
            if name in psets:
                raise SchemaCompileError(
                    "duplicate",
                    f"pset {name} is defined by {psets[name].package} and {doc.package}",
                    package=doc.key(),
                )
            psets[name] = _build_pset(name, pdef, layer="standard", doc=doc, lists=lists)
            base_docs[name] = doc

    extensions = sorted((d for d in docs if d.kind == "extension"), key=lambda d: d.package)
    for ext in extensions:
        for entry in ext.extends:
            package, version, pset_name = entry.target()
            base = index.get((package, version))
            if base is None or base.kind != "company":
                raise SchemaCompileError(
                    "unknown_target",
                    f"{ext.key()} extends {entry.ref}, but {package}@{version} is not adopted",
                    package=ext.key(),
                )
            if ext.depends.get(package) != version:
                raise SchemaCompileError(
                    "pin",
                    f"{ext.key()} extends {entry.ref} but does not pin {package} to {version}",
                    package=ext.key(),
                )
            if pset_name not in base.psets:
                raise SchemaCompileError(
                    "unknown_target",
                    f"{ext.key()}: {package}@{version} has no pset {pset_name}",
                    package=ext.key(),
                )
            psets[pset_name] = _apply_extension(
                psets[pset_name], entry, ext, base, _company_lists(base, index)
            )

    company_list_names: set[str] = set()
    for doc in docs:
        if doc.kind == "company":
            company_list_names.update(doc.code_lists)
    for proj in sorted((d for d in docs if d.kind == "project"), key=lambda d: d.package):
        for list_name in proj.code_lists:
            if list_name in company_list_names:
                raise SchemaCompileError(
                    "shadow",
                    f"{proj.key()}: code list {list_name} reuses a company name",
                    package=proj.key(),
                )
        for name, pdef in proj.psets.items():
            full = f"{PROJECT_PSET_PREFIX}{name}"
            if full in psets:
                raise SchemaCompileError(
                    "duplicate",
                    f"project pset {full} is defined twice",
                    package=proj.key(),
                )
            psets[full] = _build_pset(name, pdef, layer="project", doc=proj, lists=proj.code_lists)

    return {name: psets[name] for name in sorted(psets)}
