"""Load the ``Labels`` a screen needs from the client, once per screen (P1-UX-S2).

Type titles come from the generated ``TYPE_LABELS``. Code labels come from the enum values of the
effective schema's fields (``form_metadata``), keyed by the field's last path part (``doc_type``)
and by its full path. Domains and subtypes come from the correspondence domains of the project,
services from the accounts the signed-in person may list. The company's standard code lists
(``list_code_lists``: ``Discipline``, ``DocumentType``, ``Area``) are keyed by their column name
(``discipline``, ``doc_type``, ``area``) and by their list name.
A read that fails leaves its part empty: a label that is missing falls back to the code,
never to an error.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from tl_core.settings.layers import project_of_scope
from tl_schema.forms import FieldMeta
from tl_schema.generated.type_labels import TYPE_LABELS

from tl_tui.client import ClientInterface
from tl_tui.display import Labels

# A label read that fails (a refusal, a missing service, an old server) leaves its part empty.
_SKIPPED = (Exception,)


def _code_labels(
    client: ClientInterface, scope: str, record_types: Iterable[str]
) -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    for record_type in record_types:
        try:
            meta = client.form_metadata(scope, record_type)
        except _SKIPPED:
            continue
        fields: list[FieldMeta] = [*meta.core_fields]
        for group in meta.psets:
            fields.extend(group.fields)
        for field in fields:
            if not field.enum_values:
                continue
            values = {v.code: v.label for v in field.enum_values}
            for name in (field.path, field.path.rsplit(".", 1)[-1]):
                found.setdefault(name, {}).update(values)
    return found


#: A code list whose plain column is not its snake-case name (``documents.doc_type``).
_COLUMN_OF_LIST = {"DocumentType": "doc_type"}


def _column(list_name: str) -> str:
    """``Discipline`` -> ``discipline``, ``UnitOfMeasure`` -> ``unit_of_measure``."""
    if list_name in _COLUMN_OF_LIST:
        return _COLUMN_OF_LIST[list_name]
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", list_name).lower()


def _standard_labels(client: ClientInterface, scope: str) -> dict[str, dict[str, str]]:
    """The company's code lists (``Discipline``, ``DocumentType``, ``Area``...) by column name."""
    try:
        lists = client.list_code_lists(scope)
    except _SKIPPED:
        return {}
    found: dict[str, dict[str, str]] = {}
    for name, values in lists.items():
        for key in (_column(name), name):
            found.setdefault(key, {}).update(values)
    return found


def load_labels(
    client: ClientInterface, scope: str, record_types: Iterable[str] = ("core.Record",)
) -> Labels:
    """The labels for ``scope``; ``record_types`` are the types whose code lists are wanted."""
    project = project_of_scope(scope)
    domains: dict[str, str] = {}
    subtypes: dict[tuple[str, str], str] = {}
    if project:
        try:
            for domain in client.list_correspondence_domains(project):
                domains[domain.code] = domain.name
                for subtype in domain.subtypes:
                    subtypes[(domain.code, subtype.code)] = subtype.label
        except _SKIPPED:
            domains, subtypes = {}, {}
    services: dict[str, str] = {}
    try:
        for account in client.list_accounts():
            if account.kind == "agent":
                services[f"agent:{account.username}"] = account.display_name
                services[f"svc:{account.username}"] = account.display_name
    except _SKIPPED:
        services = {}
    code_labels = _code_labels(client, scope, record_types)
    for name, values in _standard_labels(client, scope).items():
        known = code_labels.setdefault(name, {})
        for code, label in values.items():
            known.setdefault(code, label)
    return Labels(
        type_titles=dict(TYPE_LABELS),
        code_labels=code_labels,
        domains=domains,
        subtypes=subtypes,
        services=services,
    )


def schema_keys(client: ClientInterface, scope: str, labels: Labels) -> list[str]:
    """The record-type keys and dotted property keys that a plain screen must never show.

    Type keys are every key of ``labels.type_titles`` (``core.Record``, ``engineering.Tag``).
    Property keys are ``<set>.<property>`` (``valve_data.body_material``) and the full field path
    (``psets.valve_data.body_material``), read from the form metadata of every labelled type. Only
    keys the schema names are listed, so ``m/s`` or a sentence with a full stop cannot match.
    Longest first; ``display.key_hits`` finds them in text.
    """
    keys: set[str] = set(labels.type_titles)
    for record_type in labels.type_titles:
        try:
            meta = client.form_metadata(scope, record_type)
        except _SKIPPED:  # a type with no form has no property keys
            continue
        for group in meta.psets:
            for field in group.fields:
                keys.add(field.path)
                keys.add(field.path.removeprefix("psets."))
    return sorted(keys, key=lambda key: (-len(key), key))
