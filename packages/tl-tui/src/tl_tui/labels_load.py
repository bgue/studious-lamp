"""Load the ``Labels`` a screen needs from the client, once per screen (P1-UX-S2).

Type titles come from the generated ``TYPE_LABELS``. Code labels come from the enum values of the
effective schema's fields (``form_metadata``), keyed by the field's last path part (``doc_type``)
and by its full path. Domains and subtypes come from the correspondence domains of the project,
services from the accounts the signed-in person may list. A read that fails leaves its part empty:
a label that is missing falls back to the code, never to an error.
"""

from __future__ import annotations

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
    return Labels(
        type_titles=dict(TYPE_LABELS),
        code_labels=_code_labels(client, scope, record_types),
        domains=domains,
        subtypes=subtypes,
        services=services,
    )
