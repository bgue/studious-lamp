"""Read workflow definitions from YAML and look them up by record type and scope (brief 8).

Definitions live in ``<schema dir>/workflows/*.yaml`` (``TL_SCHEMA_DIR`` or ``schema/fixtures``).
A project definition (``scope: project:P123``) overrides the company definition for the same record
type; among definitions of equal scope the highest ``version`` wins.

STUB (P0-I3-T08): the signatures are final; the bodies marked ``raise NotImplementedError`` are
the ticket. Remove this paragraph when done.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from tl_core.workflow.definition import WorkflowDefinition


class WorkflowError(ValueError):
    """A workflow file or definition set that cannot be used. The message names the source."""


def parse_workflow(text: str, *, source: str = "<string>") -> WorkflowDefinition:
    """Parse YAML text into a checked ``WorkflowDefinition``.

    Raises ``WorkflowError`` whose message starts with ``source`` for: invalid YAML, a document
    that is not a mapping, a pydantic validation error (one line per error, ``<loc>: <message>``),
    or any problem reported by ``semantic_problems`` (one line per problem).
    """
    raise NotImplementedError


def load_workflow(path: Path) -> WorkflowDefinition:
    """Read and parse one file (``source`` is its name). Read errors become ``WorkflowError``."""
    raise NotImplementedError


def semantic_problems(definition: WorkflowDefinition) -> list[str]:
    """Meaning errors in a structurally valid definition, in a fixed order; empty when sound.

    Reported (exact wording is tested): duplicate state name; ``initial_state`` not a state;
    duplicate transition name; a transition ``from`` list that is empty; a ``from`` or ``to`` that
    is not a state; a state that cannot be reached from the initial state through the transitions;
    an invalid ``scope`` (must be ``company`` or ``project:<id>`` with letters, digits, ``_.-``);
    a ``required_psets`` guard with neither ``psets`` nor ``values``.
    """
    raise NotImplementedError


class WorkflowRegistry:
    """Definitions in registration order."""

    def __init__(self, definitions: Iterable[WorkflowDefinition] = ()) -> None:
        self._definitions: list[WorkflowDefinition] = []
        for definition in definitions:
            self.add(definition)

    def add(self, definition: WorkflowDefinition) -> None:
        """Register a definition; ``WorkflowError`` when ``(id, version, scope)`` is taken."""
        raise NotImplementedError

    def all(self) -> list[WorkflowDefinition]:
        """Every definition, in registration order."""
        raise NotImplementedError

    def find(self, record_type: str, scope: str) -> WorkflowDefinition | None:
        """The definition for a record of ``record_type`` in ``scope``, or ``None``.

        Candidates have the record type and a scope equal to ``scope`` or ``company``. A candidate
        with the exact scope beats a company one; among equals the highest version wins.
        """
        raise NotImplementedError

    def get(self, workflow_id: str, version: int) -> WorkflowDefinition | None:
        """The definition with this id and version (company scope preferred), or ``None``."""
        raise NotImplementedError


def load_workflows(directory: Path) -> WorkflowRegistry:
    """Every ``*.yaml`` file of ``directory`` (not recursive, sorted by name), parsed.

    A missing directory gives an empty registry. The first bad file raises ``WorkflowError``.
    """
    raise NotImplementedError


def default_workflows() -> WorkflowRegistry:
    """The definitions in ``<schema dir>/workflows`` (``tl_schema.registry.default_schema_dir``)."""
    raise NotImplementedError
