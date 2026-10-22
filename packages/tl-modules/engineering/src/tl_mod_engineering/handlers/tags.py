"""Tag commands: create, reclassify, rename, split, merge (brief 9 M2; P1-I1-T06).

A tag is a project record (``engineering.Tag``) whose number is its key. Its number is checked
against the registry numbering pattern, its class (a company ``TagClass``) binds the property sets
it must carry, and a rename, split or merge creates new tags that supersede the old ones. Each
handler runs inside an entered unit of work, appends through it and never commits. A failed check
raises a ``ServiceError`` before anything is appended, so nothing is written. All the events of one
command share one correlation id.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator
from tl_core.ledger import NewEvent
from tl_core.schema_provider import get_provider
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import DuplicateKeyError, NoChangesError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.psets import SetPsetValues, handle_set_pset_values
from tl_core.services.records import create_module_record
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow
from tl_schema.conformance import evaluate

from tl_mod_engineering import patterns, registry
from tl_mod_engineering.actions import ENDED
from tl_mod_engineering.errors import (
    InvalidTagNumberError,
    RegistryScopeError,
    TagClassNotFoundError,
    TagNotFoundError,
    TagSupersededError,
)
from tl_mod_engineering.limits import (
    MAX_DESCRIPTION,
    MAX_ITEMS,
    MAX_NUMBER,
    MAX_PROPERTIES,
    MAX_PSETS,
    MAX_REASON,
    MAX_TEXT,
)
from tl_mod_engineering.names import (
    COMPANY,
    TAG,
    TAG_DEFINED,
    TAG_RECLASSIFIED,
    TAG_SUPERSEDED,
)

#: Pset roots that people do not write (enrichment and source layers).
_NOT_COPIED = ("enrich", "src")
#: One write of values: ``(pset, layer, values)`` as ``SetPsetValues`` takes them.
Write = tuple[str, Literal["standard", "custom", "project"], dict[str, Any]]


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("reason must not be blank")
    return value


class CreateTag(Command):
    """Create a tag in a project scope. ``number`` becomes the record key.

    The number must fit the registry numbering pattern. A command has no ``origin`` and no pattern
    policy: a tag made here is ``created`` and its number is checked. A number that breaks the
    pattern is stored only through :class:`RecordTag` (admin) or the import service.
    """

    model_config = ConfigDict(extra="forbid")  # a stale `pattern_policy=` or `origin=` is an error

    number: str = Field(min_length=1, max_length=MAX_NUMBER)
    class_code: str | None = Field(default=None, max_length=MAX_NUMBER)
    service: str | None = Field(default=None, max_length=MAX_TEXT)  # the title; default: the number
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    psets: dict[str, dict[str, Any]] = Field(default={}, max_length=MAX_PSETS)

    @field_validator("psets")
    @classmethod
    def _psets_fit(cls, value: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        for name, values in value.items():
            if len(values) > MAX_PROPERTIES:
                raise ValueError(f"pset {name!r} has more than {MAX_PROPERTIES} properties")
        return value


class RecordTag(CreateTag):
    """Create a tag and keep a number that breaks the pattern, as a violation (admin).

    For legacy numbers that are kept as they are. The violations are stored with the tag and show
    in the reports. The API offers it as an admin command; ``tl tag create --allow-violation``
    needs the admin role.
    """


class ReclassifyTag(Command):
    stream_id: str
    expected_version: int | None = None
    class_code: str = Field(max_length=MAX_NUMBER)
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


class RenameTag(Command):
    """Replace a tag by a new tag with another number (same class, service and values)."""

    stream_id: str
    expected_version: int | None = None
    new_number: str = Field(min_length=1, max_length=MAX_NUMBER)
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


class SplitTag(Command):
    """Replace one tag by several (each with the old tag's class, service and values)."""

    stream_id: str
    expected_version: int | None = None
    new_numbers: list[str] = Field(min_length=2, max_length=MAX_ITEMS)
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


class MergeTags(Command):
    """Replace several tags by one. The new tag takes class, service and values of the first."""

    stream_ids: list[str] = Field(min_length=2, max_length=MAX_ITEMS)
    new_number: str = Field(min_length=1, max_length=MAX_NUMBER)
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


def _require_project(cmd: Command) -> None:
    if not cmd.scope.startswith("project:"):
        raise RegistryScopeError(f"tags belong to a project; the scope is {cmd.scope!r}")


def _correlated[C: Command](cmd: C) -> C:
    """``cmd`` with a correlation id, so every event of the command carries the same one."""
    if cmd.correlation_id is not None:
        return cmd
    return cmd.model_copy(update={"correlation_id": new_ulid()})


def _class_of(uow: UnitOfWork, code: str) -> registry.TagClassRow:
    found = registry.active_tag_class(uow.conn(), COMPANY, code)
    if found is None:
        raise TagClassNotFoundError(f"no active tag class {code!r}")
    return found


def _conformance(
    scope: str, psets: dict[str, Any], state: str | None, bound: tuple[str, ...]
) -> tuple[str, str]:
    """``(status, effective_schema_hash)`` of a tag with these values under the scope's schema."""
    schema = get_provider().effective(scope)
    report = evaluate(schema, TAG, psets, state=state, on=utcnow().date(), bound=bound)
    return report.status, schema.hash


def _check_number(
    uow: UnitOfWork,
    scope: str,
    number: str,
    class_row: registry.TagClassRow | None,
    policy: str,
) -> tuple[patterns.ParsedNumber | None, list[dict[str, Any]], str]:
    """``(parsed, issues, number_status)`` for a new tag number; raises when it is refused."""
    pattern = patterns.pattern_for(uow.conn(), TAG)
    if pattern is None:
        return None, [], "ok"
    parsed = patterns.parse_number(uow.conn(), scope, pattern, number)
    issues = list(parsed.issues)
    if class_row is not None and class_row.mnemonics and parsed.mnemonic is not None:
        if parsed.mnemonic not in class_row.mnemonics:
            issues.append(
                patterns.NumberIssue(
                    "mnemonic",
                    "class_mnemonic",
                    f"{parsed.mnemonic!r} does not usually identify a {class_row.code} "
                    f"({', '.join(class_row.mnemonics)})",
                    level="warning",
                )
            )
    errors = [i for i in issues if i.level == "error"]
    if errors and policy == "enforce":
        raise InvalidTagNumberError(
            f"tag number {number!r}: " + "; ".join(i.message for i in errors),
            [i.as_dict() for i in issues],
        )
    return parsed, [i.as_dict() for i in issues], ("violation" if errors else "ok")


def _create(
    uow: UnitOfWork,
    cmd: Command,
    *,
    number: str,
    class_code: str | None,
    title: str,
    description: str | None,
    writes: list[Write],
    policy: str,
    origin: str,
    supersedes: list[str],
) -> CommandResult:
    """Check the number and class, append the tag, then write its initial values."""
    class_row = _class_of(uow, class_code) if class_code is not None else None
    parsed, issues, number_status = _check_number(uow, cmd.scope, number, class_row, policy)
    bound = tuple(class_row.required_psets) if class_row is not None else ()
    status, schema_hash = _conformance(cmd.scope, {}, None, bound)
    payload: dict[str, Any] = {
        "number": number,
        "class_code": class_row.code if class_row is not None else None,
        "area": parsed.area if parsed else None,
        "mnemonic": parsed.mnemonic if parsed else None,
        "sequence": parsed.sequence if parsed else None,
        "segments": parsed.segments if parsed else {},
        "pattern_code": parsed.pattern_code if parsed else None,
        "number_status": number_status,
        "violations": issues,
        "origin": origin,
        "supersedes": supersedes,
        "bound_psets": list(bound),
        "conformance": status,
        "effective_schema_hash": schema_hash,
    }
    made = create_module_record(
        uow,
        cmd,
        record_type=TAG,
        title=title,
        description=description,
        key=number,
        extra_events=[NewEvent(event_type=TAG_DEFINED, payload=payload)],
    )
    events = list(made.events)
    version = made.version
    for pset, layer, values in writes:
        written = handle_set_pset_values(
            uow,
            SetPsetValues(
                actor=cmd.actor,
                source=cmd.source,
                scope=cmd.scope,
                correlation_id=cmd.correlation_id,
                stream_id=made.stream_id,
                expected_version=version,
                pset=pset,
                layer=layer,
                values=values,
            ),
        )
        events.extend(written.events)
        version = written.version
    return CommandResult(stream_id=made.stream_id, key=made.key, version=version, events=events)


def handle_create_tag(uow: UnitOfWork, cmd: CreateTag) -> CommandResult:
    """Append ``Record.Created`` and ``Tag.Defined``, then ``Pset.ValuesSet`` for each given pset.

    Raises ``RegistryScopeError`` (not a project scope), ``TagClassNotFoundError`` (no active
    class of that code), ``InvalidTagNumberError`` (policy ``enforce`` and the number breaks the
    registry pattern: ``issues`` lists every problem), ``DuplicateKeyError`` and the pset errors.
    With no registry pattern for tags the number is accepted as written.
    """
    return _create_from(uow, cmd, policy="enforce", origin="created")


def handle_record_tag(
    uow: UnitOfWork, cmd: RecordTag, *, origin: Literal["created", "import"] = "created"
) -> CommandResult:
    """Like :func:`handle_create_tag`, but a number that breaks the pattern is kept as a violation.

    ``origin`` is not part of the command: only a caller inside the platform (the import service)
    can say ``import``. Who may call this is the caller's rule (``RecordTag`` is admin-only in the
    API and the CLI).
    """
    return _create_from(uow, cmd, policy="record", origin=origin)


def _create_from(
    uow: UnitOfWork, cmd: CreateTag, *, policy: str, origin: Literal["created", "import"]
) -> CommandResult:
    _require_project(cmd)
    cmd = _correlated(cmd)
    writes: list[Write] = [(name, "standard", values) for name, values in sorted(cmd.psets.items())]
    return _create(
        uow,
        cmd,
        number=cmd.number,
        class_code=cmd.class_code,
        title=cmd.service or cmd.number,
        description=cmd.description,
        writes=writes,
        policy=policy,
        origin=origin,
        supersedes=[],
    )


def _load_live(uow: UnitOfWork, cmd: Command, stream_id: str) -> registry.TagRow:
    tag = registry.get_tag(uow.conn(), stream_id)
    if tag is None or tag.scope != cmd.scope:
        raise TagNotFoundError(f"no tag {stream_id!r} in scope {cmd.scope!r}")
    if tag.status in ENDED:
        raise TagSupersededError(f"tag {tag.number} is {tag.status} and takes no more changes")
    return tag


def handle_reclassify_tag(uow: UnitOfWork, cmd: ReclassifyTag) -> CommandResult:
    """Append ``Tag.Reclassified``: the new class binds its own psets; conformance is recomputed.

    Raises ``TagNotFoundError``, ``TagSupersededError``, ``TagClassNotFoundError`` and
    ``NoChangesError`` (already of that class).
    """
    tag = _load_live(uow, cmd, cmd.stream_id)
    class_row = _class_of(uow, cmd.class_code)
    if tag.class_code == class_row.code:
        raise NoChangesError(f"tag {tag.number} is already of class {class_row.code}")
    bound = tuple(class_row.required_psets)
    status, schema_hash = _conformance(cmd.scope, tag.psets, tag.status, bound)
    result = uow.append(
        stream_id=tag.id,
        stream_type=TAG,
        scope=cmd.scope,
        expected_version=cmd.expected_version if cmd.expected_version is not None else tag.version,
        events=[
            NewEvent(
                event_type=TAG_RECLASSIFIED,
                payload={
                    "from_class": tag.class_code,
                    "to_class": class_row.code,
                    "reason": cmd.reason,
                    "bound_psets": list(bound),
                    "conformance": status,
                    "effective_schema_hash": schema_hash,
                },
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=tag.id, key=tag.number, version=result.new_version, events=result.events
    )


def _writes_of(psets: dict[str, Any]) -> list[Write]:
    """The writes that recreate a record's standard, custom and project values on a new record."""
    writes: list[Write] = []
    for name, section in sorted(psets.items()):
        if name in _NOT_COPIED or not isinstance(section, dict):
            continue
        if name == "prj":
            for project_pset, values in sorted(section.items()):
                if isinstance(values, dict) and values:
                    writes.append((f"prj.{project_pset}", "project", dict(values)))
            continue
        plain = {k: v for k, v in section.items() if k != "x"}
        if plain:
            writes.append((name, "standard", plain))
        custom = section.get("x")
        if isinstance(custom, dict) and custom:
            writes.append((name, "custom", {f"x.{k}": v for k, v in custom.items()}))
    return writes


def _supersede(
    uow: UnitOfWork,
    cmd: Command,
    olds: list[registry.TagRow],
    new_numbers: list[str],
    *,
    operation: str,
    reason: str,
    expected: dict[str, int | None],
) -> list[CommandResult]:
    """Create the new tags, link them to the old ones, take the old ones out of service."""
    _require_project(cmd)
    for number in new_numbers:
        if registry.find_tag(uow.conn(), cmd.scope, number) is not None:
            raise DuplicateKeyError(f"tag number {number!r} is already used in scope {cmd.scope!r}")
    source = olds[0]
    writes = _writes_of(source.psets)
    created = [
        _create(
            uow,
            cmd,
            number=number,
            class_code=source.class_code,
            title=source.title,
            description=None,
            writes=writes,
            policy="enforce",
            origin=operation,
            supersedes=[old.id for old in olds],
        )
        for number in new_numbers
    ]
    new_ids = [made.stream_id for made in created]
    for old in olds:
        for made in created:
            handle_add_link(
                uow,
                AddLink(
                    actor=cmd.actor,
                    source=cmd.source,
                    scope=cmd.scope,
                    correlation_id=cmd.correlation_id,
                    from_id=made.stream_id,
                    to_id=old.id,
                    relation="supersedes",
                    link_source="rule",
                    note=reason,
                ),
                by_module=True,
            )
        current = registry.get_tag(uow.conn(), old.id)
        assert current is not None
        wanted = expected.get(old.id)
        appended = uow.append(
            stream_id=old.id,
            stream_type=TAG,
            scope=cmd.scope,
            expected_version=wanted if wanted is not None else current.version,
            events=[
                NewEvent(
                    event_type=TAG_SUPERSEDED,
                    payload={"operation": operation, "superseded_by": new_ids, "reason": reason},
                )
            ],
            actor=cmd.actor,
            source=cmd.source,
            correlation_id=cmd.correlation_id or new_ulid(),
            causation_id=cmd.causation_id,
        )
        handle_transition_workflow(
            uow,
            TransitionWorkflow(
                actor=cmd.actor,
                source=cmd.source,
                scope=cmd.scope,
                correlation_id=cmd.correlation_id,
                stream_id=old.id,
                expected_version=appended.new_version,
                transition="supersede",
                reason=reason,
            ),
        )
    return created


def handle_rename_tag(uow: UnitOfWork, cmd: RenameTag) -> CommandResult:
    """Create a tag with ``new_number`` that supersedes this one.

    The new tag has the old one's class, service and values (origin ``rename``); a ``supersedes``
    link runs from the new tag to the old; the old tag gets ``Tag.Superseded`` and the workflow
    transition ``supersede``. Raises ``TagNotFoundError``, ``TagSupersededError``,
    ``NoChangesError`` (same number), ``DuplicateKeyError`` and everything ``CreateTag`` raises.
    """
    old = _load_live(uow, cmd, cmd.stream_id)
    if cmd.new_number == old.number:
        raise NoChangesError(f"tag {old.number} already has that number")
    cmd = _correlated(cmd)
    (made,) = _supersede(
        uow,
        cmd,
        [old],
        [cmd.new_number],
        operation="rename",
        reason=cmd.reason,
        expected={old.id: cmd.expected_version},
    )
    return made


def handle_split_tag(uow: UnitOfWork, cmd: SplitTag) -> list[CommandResult]:
    """Create one tag per number in ``new_numbers``, all superseding this one (origin ``split``).

    Raises as ``handle_rename_tag`` does, and ``NoChangesError`` for a repeated new number.
    """
    old = _load_live(uow, cmd, cmd.stream_id)
    if len(set(cmd.new_numbers)) != len(cmd.new_numbers):
        raise NoChangesError("the new tag numbers must differ from one another")
    if old.number in cmd.new_numbers:
        raise NoChangesError(f"tag {old.number} is the one being split; give it new numbers")
    cmd = _correlated(cmd)
    return _supersede(
        uow,
        cmd,
        [old],
        cmd.new_numbers,
        operation="split",
        reason=cmd.reason,
        expected={old.id: cmd.expected_version},
    )


def handle_merge_tags(uow: UnitOfWork, cmd: MergeTags) -> CommandResult:
    """Create one tag that supersedes all of ``stream_ids`` (origin ``merge``).

    The new tag takes the class, service and values of the first tag listed. Raises as
    ``handle_rename_tag`` does for each tag, and ``NoChangesError`` for a repeated id.
    """
    if len(set(cmd.stream_ids)) != len(cmd.stream_ids):
        raise NoChangesError("a tag can be merged only once")
    olds = [_load_live(uow, cmd, stream_id) for stream_id in cmd.stream_ids]
    if cmd.new_number in [old.number for old in olds]:
        raise NoChangesError(f"{cmd.new_number!r} is the number of a tag being merged")
    cmd = _correlated(cmd)
    (made,) = _supersede(
        uow, cmd, olds, [cmd.new_number], operation="merge", reason=cmd.reason, expected={}
    )
    return made
