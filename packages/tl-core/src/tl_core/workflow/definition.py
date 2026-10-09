"""Workflow definition models: states, transitions, and guards (brief 8).

A definition is declarative YAML (``schema/fixtures/workflows/*.yaml``) parsed into these models by
``tl_core.workflow.loader``. The models check structure only (field names and types); the loader
checks meaning (every transition names real states, and so on).

Guards, evaluated by ``tl_core.workflow.engine`` before a transition is allowed:

=================  ==============================================================================
``required_psets``  named psets hold values, and listed property paths have a value
``conformance``     the record conforms to the effective schema *in the target state*
``required_links``  explicit link requirements (same shape as an expected link)
``expected_links``  the record type's declared expected links with ``by_state`` = target state
``roles``           the actor holds one of the roles (a stub list on the command until auth exists)
=================  ==============================================================================
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from tl_core.links.expected import ExpectedLink


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class RequiredPsetsGuard(_Model):
    kind: Literal["required_psets"]
    psets: list[str] = []  # pset names such as "valve_data" or "prj.shutdown_tie_in": hold values
    values: list[str] = []  # property paths such as "valve_data.size_in": each has a value


class ConformanceGuard(_Model):
    kind: Literal["conformance"]
    # Worst conformance status that still passes. "warning" fails only on "nonconformant".
    max_status: Literal["ok", "warning"] = "warning"


class RequiredLinksGuard(_Model):
    kind: Literal["required_links"]
    links: list[ExpectedLink] = Field(min_length=1)


class ExpectedLinksGuard(_Model):
    kind: Literal["expected_links"]


class RolesGuard(_Model):
    kind: Literal["roles"]
    any_of: list[str] = Field(min_length=1)


Guard = Annotated[
    RequiredPsetsGuard | ConformanceGuard | RequiredLinksGuard | ExpectedLinksGuard | RolesGuard,
    Field(discriminator="kind"),
]


class StateDef(_Model):
    name: str = Field(min_length=1)
    label: str | None = None


class TransitionDef(_Model):
    name: str = Field(min_length=1)
    from_states: list[str] = Field(alias="from")
    to: str = Field(min_length=1)
    label: str | None = None
    guards: list[Guard] = []


class WorkflowDefinition(_Model):
    id: str = Field(min_length=1)  # e.g. "core.review"
    version: int = Field(ge=1)
    record_type: str = Field(min_length=1)  # e.g. "core.Record"
    scope: str = "company"  # "company" or "project:<id>": a project definition overrides
    initial_state: str = Field(min_length=1)
    states: list[StateDef] = Field(min_length=1)
    transitions: list[TransitionDef] = []

    def state_names(self) -> list[str]:
        """State names in declaration order."""
        return [state.name for state in self.states]

    def transition(self, name: str) -> TransitionDef | None:
        """The transition with this name, or ``None``."""
        return next((t for t in self.transitions if t.name == name), None)

    def transitions_from(self, state: str) -> list[TransitionDef]:
        """Transitions that can start in ``state``, in declaration order."""
        return [t for t in self.transitions if state in t.from_states]
