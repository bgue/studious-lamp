"""The LinkML classes of the integration layer carry the slot names of the contract models.

``tl_core.integration.contract`` is the frozen shape; ``schema/core/integration.yaml`` makes it
storable (FANOUT D13). A model field with no slot would be a value the ledger cannot keep, so each
field of a contract model must be a slot of its class, and every enum a model writes as a
``Literal`` must list the same values as the LinkML enum.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, get_args

import pytest
from pydantic import BaseModel
from tl_core.integration import contract
from tl_schema.generated import models as gen

#: contract model, the LinkML class that stores it, and the fields that are not slots on purpose.
MODELS: list[tuple[type[BaseModel], type[BaseModel], set[str]]] = [
    (contract.ActionDefinition, gen.ActionDefinition, set()),
    (contract.Rule, gen.Rule, set()),
    (contract.InboundEndpoint, gen.InboundEndpoint, set()),
    (contract.EnrichmentValue, gen.EnrichmentValue, set()),
    # an invocation is stored with its request; ``config`` is read from the definition at run time
    (contract.ActionRequest, gen.ActionInvocation, {"config"}),
]

#: Literal types of the contract -> the LinkML enum with the same values.
ENUMS: list[tuple[Any, type[Enum]]] = [
    (contract.Access, gen.AccessLevel),
    (contract.AutomationAccess, gen.AutomationAccess),
    (contract.ExecutorKind, gen.ExecutorKind),
    (contract.SideEffectClass, gen.SideEffectClass),
    (contract.InvocationStatus, gen.InvocationStatus),
    (contract.RuleMode, gen.RuleMode),
    (contract.InboundAuth, gen.InboundAuth),
    (contract.AcceptancePolicy, gen.AcceptancePolicy),
    (contract.AcceptanceState, gen.AcceptanceState),
]


@pytest.mark.parametrize(
    ("model", "stored", "exempt"), MODELS, ids=lambda x: getattr(x, "__name__", "")
)
def test_every_field_of_a_contract_model_is_a_slot_of_its_class(
    model: type[BaseModel], stored: type[BaseModel], exempt: set[str]
) -> None:
    missing = set(model.model_fields) - set(stored.model_fields) - exempt
    assert not missing, (
        f"{model.__name__} has fields {sorted(missing)} that {stored.__name__} cannot store"
    )


def test_the_enricher_registration_stores_what_the_plugin_declares() -> None:
    declared = {"name", "version", "model_ref"}  # the attributes of the ``Enricher`` protocol
    stored = set(gen.Enricher.model_fields)
    # ``version`` of the record is the registration version; the plugin's own is ``code_version``
    assert {"name", "model_ref", "code_version", "version"} <= stored
    assert declared - {"version"} <= stored


@pytest.mark.parametrize(("literal", "enum"), ENUMS, ids=lambda x: getattr(x, "__name__", ""))
def test_a_literal_of_the_contract_and_its_linkml_enum_list_the_same_values(
    literal: Any, enum: type[Enum]
) -> None:
    assert set(get_args(literal)) == {member.value for member in enum}


def test_the_pinned_models_are_all_there() -> None:
    """Guard the guard: the table above names the classes FANOUT D13 lists."""
    assert {stored.__name__ for _, stored, _ in MODELS} == {
        "ActionDefinition",
        "Rule",
        "InboundEndpoint",
        "EnrichmentValue",
        "ActionInvocation",
    }
    for name in ("IntegrationApp", "Enricher", "ActionInvocation"):
        assert hasattr(gen, name)
