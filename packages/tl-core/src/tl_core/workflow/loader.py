"""Read workflow definitions from YAML and look them up by record type and scope (brief 8).

Definitions live in ``<schema dir>/workflows/*.yaml`` (``TL_SCHEMA_DIR`` or ``schema/fixtures``).
A project definition (``scope: project:P123``) overrides the company definition for the same record
type; among definitions of equal scope the highest ``version`` wins.
"""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from tl_schema.registry import default_schema_dir

from tl_core.workflow.definition import RequiredPsetsGuard, WorkflowDefinition

_SCOPE_PATTERN = re.compile(r"company|project:[A-Za-z0-9_.-]+")


class WorkflowError(ValueError):
    """A workflow file or definition set that cannot be used. The message names the source."""


def parse_workflow(text: str, *, source: str = "<string>") -> WorkflowDefinition:
    """Parse YAML text into a checked ``WorkflowDefinition``.

    Raises ``WorkflowError`` whose message starts with ``source`` for: invalid YAML, a document
    that is not a mapping, a pydantic validation error (one line per error, ``<loc>: <message>``),
    or any problem reported by ``semantic_problems`` (one line per problem).
    """
    try:
        data: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise WorkflowError(f"{source}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkflowError(
            f"{source}: a workflow file must be a YAML mapping, not {type(data).__name__}"
        )
    try:
        definition = WorkflowDefinition.model_validate(data)
    except ValidationError as exc:
        lines = [
            f"{source}: {'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        ]
        raise WorkflowError("\n".join(lines)) from exc
    problems = semantic_problems(definition)
    if problems:
        raise WorkflowError("\n".join(f"{source}: {problem}" for problem in problems))
    return definition


def load_workflow(path: Path) -> WorkflowDefinition:
    """Read and parse one file (``source`` is its name). Read errors become ``WorkflowError``."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise WorkflowError(f"{path.name}: cannot read file: {exc}") from exc
    return parse_workflow(text, source=path.name)


def semantic_problems(definition: WorkflowDefinition) -> list[str]:
    """Meaning errors in a structurally valid definition, in a fixed order; empty when sound.

    Reported (exact wording is tested): duplicate state name; ``initial_state`` not a state;
    duplicate transition name; a transition ``from`` list that is empty; a ``from`` or ``to`` that
    is not a state; a state that cannot be reached from the initial state through the transitions;
    an invalid ``scope`` (must be ``company`` or ``project:<id>`` with letters, digits, ``_.-``);
    a ``required_psets`` guard with neither ``psets`` nor ``values``.
    """
    problems: list[str] = []
    names = definition.state_names()
    state_set = set(names)

    seen_states: set[str] = set()
    for name in names:
        if name in seen_states:
            problems.append(f"duplicate state '{name}'")
        seen_states.add(name)

    if definition.initial_state not in state_set:
        problems.append(f"initial_state '{definition.initial_state}' is not a state")

    if not _SCOPE_PATTERN.fullmatch(definition.scope):
        problems.append(f"invalid scope {definition.scope!r}")

    seen_transitions: set[str] = set()
    for transition in definition.transitions:
        name = transition.name
        if name in seen_transitions:
            problems.append(f"duplicate transition '{name}'")
        seen_transitions.add(name)
        if not transition.from_states:
            problems.append(f"transition '{name}' has no from states")
        for source_state in transition.from_states:
            if source_state not in state_set:
                problems.append(f"transition '{name}' starts in unknown state '{source_state}'")
        if transition.to not in state_set:
            problems.append(f"transition '{name}' ends in unknown state '{transition.to}'")
        for guard in transition.guards:
            if isinstance(guard, RequiredPsetsGuard) and not guard.psets and not guard.values:
                problems.append(
                    f"transition '{name}': a required_psets guard needs psets or values"
                )

    if definition.initial_state in state_set:
        reached = {definition.initial_state}
        queue: deque[str] = deque([definition.initial_state])
        while queue:
            current = queue.popleft()
            for transition in definition.transitions_from(current):
                if transition.to in state_set and transition.to not in reached:
                    reached.add(transition.to)
                    queue.append(transition.to)
        for name in dict.fromkeys(names):
            if name not in reached:
                problems.append(f"state '{name}' is unreachable from the initial state")

    return problems


class WorkflowRegistry:
    """Definitions in registration order."""

    def __init__(self, definitions: Iterable[WorkflowDefinition] = ()) -> None:
        self._definitions: list[WorkflowDefinition] = []
        for definition in definitions:
            self.add(definition)

    def add(self, definition: WorkflowDefinition) -> None:
        """Register a definition; ``WorkflowError`` when ``(id, version, scope)`` is taken."""
        key = (definition.id, definition.version, definition.scope)
        for existing in self._definitions:
            if (existing.id, existing.version, existing.scope) == key:
                raise WorkflowError(
                    f"workflow {definition.id} version {definition.version} "
                    f"scope {definition.scope} is already registered"
                )
        self._definitions.append(definition)

    def all(self) -> list[WorkflowDefinition]:
        """Every definition, in registration order."""
        return list(self._definitions)

    def find(self, record_type: str, scope: str) -> WorkflowDefinition | None:
        """The definition for a record of ``record_type`` in ``scope``, or ``None``.

        Candidates have the record type and a scope equal to ``scope`` or ``company``. A candidate
        with the exact scope beats a company one; among equals the highest version wins.
        """
        candidates = [
            definition
            for definition in self._definitions
            if definition.record_type == record_type and definition.scope in (scope, "company")
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda d: (d.scope == scope, d.version))

    def get(self, workflow_id: str, version: int) -> WorkflowDefinition | None:
        """The definition with this id and version (company scope preferred), or ``None``."""
        matches = [
            definition
            for definition in self._definitions
            if definition.id == workflow_id and definition.version == version
        ]
        if not matches:
            return None
        return next((d for d in matches if d.scope == "company"), matches[0])


def load_workflows(directory: Path) -> WorkflowRegistry:
    """Every ``*.yaml`` file of ``directory`` (not recursive, sorted by name), parsed.

    A missing directory gives an empty registry. The first bad file raises ``WorkflowError``.
    """
    registry = WorkflowRegistry()
    if not directory.is_dir():
        return registry
    for path in sorted(directory.glob("*.yaml"), key=lambda p: p.name):
        registry.add(load_workflow(path))
    return registry


def default_workflows() -> WorkflowRegistry:
    """The definitions in ``<schema dir>/workflows`` (``tl_schema.registry.default_schema_dir``)."""
    return load_workflows(default_schema_dir() / "workflows")
