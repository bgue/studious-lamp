# P1-I1-T07 — Tag class commands: define, revise, close

Status: ready
Tier: haiku
Labels: core
Depends on: P1-I1-S3 (registry reads, errors, projectors and the module seam, on `p1/i1`); no other ticket
Branch: `p1/i1-t07-tag-class-commands`

## Goal
A steward can create a tag class, change it and retire it. `handlers/tag_class.py` has the three command models, the helpers
and the three handler signatures with docstrings final; the three handler bodies raise `NotImplementedError`. You implement
them. One provided test file (`18` test functions, 31 cases) must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Brief 9 M2.** `TagClass`: class definition, required psets, applicable ITR templates (references only). Tag class determines mandatory psets (e.g. control valve: size, rating, body material, actuator type, fail action).
>
> **Brief 27.5 Change classification.** Add required property, tighten range/pattern, close a value list: *constraining* — grace period; existing records flagged non-conformant (not rewritten); conformance report; waivers possible.
>
> **Brief 5.2 Rules.** No updates, no deletes on the event table. Corrections are explicit events with a mandatory reason.

### Specification
A tag class is a company record. Creating one appends **one** `ledger.append` with two events on a new stream: `Record.Created`
(the envelope) and `TagClass.Defined` (the typed fields). `create_module_record` does that for you; you pass it the second event.
- **Key** of a class: `TC:<code>`. **Title**: the label. **Description**: the definition (may be `None`).
- **`TagClass.Defined` payload**: exactly `code, label, family, required_psets, itr_templates, mnemonics, edition`.
- **Revise** appends `TagClass.Revised` with `{"changes": {field: [old, new]}, "reason": ...}`; only fields whose value differs are in `changes`; a field in the command that equals the current value is left out.
- **Close** appends `TagClass.Closed` with `{"lifecycle", "superseded_by", "reason"}`.
- A class is revised or closed only while `active`. `expected_version=None` means "whatever version it has now"; a number is checked by the ledger (`ConcurrencyError`).
- Nothing is written when a check fails: every check comes before `uow.append`/`create_module_record`.
- Errors are in `tl_mod_engineering.errors`; the existing ones (`UnknownPsetError`, `NoChangesError`, `UnsupportedFieldError`) are in `tl_core.services.errors`.
- The projectors already write `cur_engineering_tag_class` from these events (tested); you write the handlers only.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/engineering/src/tl_mod_engineering/handlers/tag_class.py` (the stub you complete):
```python
"""Tag class commands: define, revise and close (brief 9 M2; P1-I1-T07).

A tag class is a company record (``engineering.TagClass``) whose ``required_psets`` name the
property sets a tag of that class must carry. Each handler runs inside an entered unit of work,
appends through it and never commits. A failed check raises a ``ServiceError`` before anything is
appended, so nothing is written.

STUB (P1-I1-T07): the three ``handle_*`` bodies raise NotImplementedError; the command models, the
signatures, the docstrings and the helpers (``_require_company``, ``_require_psets``,
``_load_active``, ``_check_value``) are final. Each body has a STEPS comment. Implement them, then
delete this paragraph, the STEPS comments and the ``ruff: noqa`` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from typing import Any, Literal, get_args

from pydantic import Field, field_validator
from tl_core.ledger import NewEvent
from tl_core.schema_provider import get_provider
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError, UnknownPsetError, UnsupportedFieldError
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

from tl_mod_engineering import registry
from tl_mod_engineering.document import ENTRY_CODE, PSET_NAME, TagFamily
from tl_mod_engineering.errors import (
    AlreadyClosedError,
    DuplicateTagClassError,
    InvalidTagClassError,
    RegistryScopeError,
    TagClassNotFoundError,
)
from tl_mod_engineering.names import (
    COMPANY,
    TAG_CLASS,
    TAG_CLASS_CLOSED,
    TAG_CLASS_DEFINED,
    TAG_CLASS_REVISED,
)

#: The fields ``ReviseTagClass.changes`` may carry.
REVISABLE = ("label", "family", "required_psets", "itr_templates", "mnemonics")
_LIST_FIELDS = ("required_psets", "itr_templates", "mnemonics")


class DefineTagClass(Command):
    """Create a tag class. ``scope`` must be ``company``."""

    code: str
    label: str = Field(min_length=1)
    definition: str | None = None
    family: TagFamily
    required_psets: list[str] = []
    itr_templates: list[str] = []
    mnemonics: list[str] = []
    edition: str = Field(min_length=1)

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if ENTRY_CODE.fullmatch(value) is None:
            raise ValueError(f"class code {value!r} may hold letters, digits and _ only")
        return value


class ReviseTagClass(Command):
    """Change fields of a tag class. ``changes`` maps a field in ``REVISABLE`` to its new value."""

    stream_id: str
    expected_version: int | None = None  # None: whatever version the class has now
    changes: dict[str, Any]
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


class CloseTagClass(Command):
    """End a tag class's life. Tags already of that class keep it."""

    stream_id: str
    expected_version: int | None = None
    lifecycle: Literal["superseded", "retired"] = "retired"
    superseded_by: str | None = None  # the replacing class; required for ``superseded``
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


def _require_company(cmd: Command) -> None:
    if cmd.scope != COMPANY:
        raise RegistryScopeError(f"tag classes are company records; the scope is {cmd.scope!r}")


def _require_psets(names: list[str]) -> None:
    """Every name must be a pset of the company effective schema."""
    schema = get_provider().effective(COMPANY)
    for name in names:
        if PSET_NAME.fullmatch(name) is None or schema.find_pset(name) is None:
            raise UnknownPsetError(f"pset {name!r} is not in the company effective schema")


def _load_active(uow: UnitOfWork, cmd: Command, stream_id: str) -> registry.TagClassRow:
    row = registry.get_tag_class(uow.conn(), stream_id)
    if row is None or row.scope != cmd.scope:
        raise TagClassNotFoundError(f"no tag class {stream_id!r} in scope {cmd.scope!r}")
    if not row.active:
        raise AlreadyClosedError(f"tag class {row.code} is {row.lifecycle}")
    return row


def handle_define_tag_class(uow: UnitOfWork, cmd: DefineTagClass) -> CommandResult:
    """Append ``Record.Created`` and ``TagClass.Defined`` for a new class (key ``TC:<code>``).

    Raises ``RegistryScopeError`` (not company scope), ``UnknownPsetError`` (a required pset the
    company schema does not define) and ``DuplicateTagClassError`` (the code is taken, closed or
    not).
    """
    # STEPS
    # 1. _require_company(cmd); _require_psets(cmd.required_psets).
    # 2. taken = registry.find_tag_classes(uow.conn(), COMPANY, code=cmd.code); if there is one,
    #    raise DuplicateTagClassError(
    #        f"tag class {cmd.code!r} is already defined (lifecycle {taken[0].lifecycle})").
    # 3. payload = a dict with exactly these keys: code, label, family, required_psets,
    #    itr_templates, mnemonics, edition (all from cmd; the definition is not in the payload, it
    #    is the record's description).
    # 4. return create_module_record(uow, cmd, record_type=TAG_CLASS, title=cmd.label,
    #        description=cmd.definition, key=f"TC:{cmd.code}",
    #        extra_events=[NewEvent(event_type=TAG_CLASS_DEFINED, payload=payload)]).
    raise NotImplementedError


def handle_revise_tag_class(uow: UnitOfWork, cmd: ReviseTagClass) -> CommandResult:
    """Append ``TagClass.Revised`` with the fields that differ, as ``{field: [old, new]}``.

    Raises ``TagClassNotFoundError``, ``AlreadyClosedError``, ``UnsupportedFieldError`` (a field
    outside ``REVISABLE``), ``InvalidTagClassError`` (a blank label, an unknown family, a list field
    that is not a list of strings), ``UnknownPsetError`` and ``NoChangesError`` (nothing differs).
    """
    # STEPS
    # 1. row = _load_active(uow, cmd, cmd.stream_id).
    # 2. unsupported = sorted(set(cmd.changes) - set(REVISABLE)); if any, raise
    #    UnsupportedFieldError(f"fields {', '.join(unsupported)} cannot be revised; "
    #                         f"only {', '.join(REVISABLE)} can").
    # 3. current = {"label": row.label, "family": row.family, "required_psets": row.required_psets,
    #    "itr_templates": row.itr_templates, "mnemonics": row.mnemonics}.
    # 4. changes: dict[str, list[Any]] = {}. For each (field, new) of cmd.changes in order:
    #    _check_value(field, new); if new != current[field]: changes[field] = [current[field], new].
    # 5. If "required_psets" in changes: _require_psets(changes["required_psets"][1]).
    # 6. If changes is empty: raise NoChangesError(
    #        f"no field of tag class {row.code} differs from the request").
    # 7. result = uow.append(stream_id=row.id, stream_type=TAG_CLASS, scope=cmd.scope,
    #        expected_version=cmd.expected_version if cmd.expected_version is not None
    #            else row.version,
    #        events=[NewEvent(event_type=TAG_CLASS_REVISED,
    #                         payload={"changes": changes, "reason": cmd.reason})],
    #        actor=cmd.actor, source=cmd.source,
    #        correlation_id=cmd.correlation_id or new_ulid(), causation_id=cmd.causation_id).
    # 8. return CommandResult(stream_id=row.id, key=row.key, version=result.new_version,
    #        events=result.events).
    raise NotImplementedError


def _check_value(field: str, value: Any) -> None:
    if field == "label":
        if not isinstance(value, str) or not value.strip():
            raise InvalidTagClassError("label must not be blank")
    elif field == "family":
        if value not in get_args(TagFamily):
            raise InvalidTagClassError(f"family must be one of {', '.join(get_args(TagFamily))}")
    elif field in _LIST_FIELDS:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise InvalidTagClassError(f"{field} must be a list of strings")


def handle_close_tag_class(uow: UnitOfWork, cmd: CloseTagClass) -> CommandResult:
    """Append ``TagClass.Closed``.

    Raises ``TagClassNotFoundError``, ``AlreadyClosedError`` and ``InvalidTagClassError`` (a
    ``superseded`` close without a replacing class that exists, or a ``retired`` close with one).
    """
    # STEPS
    # 1. row = _load_active(uow, cmd, cmd.stream_id).
    # 2. If cmd.lifecycle == "superseded": successor = None if cmd.superseded_by is None else
    #    registry.get_tag_class(uow.conn(), cmd.superseded_by); if successor is None, or
    #    successor.scope != cmd.scope, or successor.id == row.id, raise InvalidTagClassError(
    #    "a superseded class needs superseded_by: another tag class").
    #    Else if cmd.superseded_by is not None: raise InvalidTagClassError(
    #    "a retired class has no superseded_by").
    # 3. result = uow.append(stream_id=row.id, stream_type=TAG_CLASS, scope=cmd.scope,
    #        expected_version=as in revise,
    #        events=[NewEvent(event_type=TAG_CLASS_CLOSED, payload={"lifecycle": cmd.lifecycle,
    #                "superseded_by": cmd.superseded_by, "reason": cmd.reason})],
    #        actor=cmd.actor, source=cmd.source,
    #        correlation_id=cmd.correlation_id or new_ulid(), causation_id=cmd.causation_id).
    # 4. return CommandResult(stream_id=row.id, key=row.key, version=result.new_version,
    #        events=result.events).
    raise NotImplementedError
```

`packages/tl-modules/engineering/src/tl_mod_engineering/registry.py` (what the handlers read):
```python
@dataclass(frozen=True)
class TagClassRow:
    id: str
    scope: str
    code: str
    label: str
    description: str | None
    family: str
    required_psets: list[str]
    itr_templates: list[str]
    mnemonics: list[str]
    lifecycle: str
    superseded_by: str | None
    edition: str
    key: str | None
    version: int

    @property
    def active(self) -> bool:
        return self.lifecycle == "active"

def get_tag_class(conn: Connection, stream_id: str) -> TagClassRow | None: ...
def find_tag_classes(
    conn: Connection, scope: str, *, code: str | None = None, active_only: bool = False
) -> list[TagClassRow]: ...   # every class of the scope with that code, any lifecycle, ordered by code
```

`tl_core.services.records.create_module_record` (already in the repo):
```python
def create_module_record(
    uow: UnitOfWork,
    cmd: Command,
    *,
    record_type: str,
    title: str,
    key: str | None,
    description: str | None = None,
    extra_events: Sequence[NewEvent] = (),
    numbering: dict[str, str] | None = None,
) -> CommandResult: ...  # Record.Created then extra_events in one append; DuplicateKeyError on a taken key
```

## Context (read these, nothing else)
- `packages/tl-modules/engineering/src/tl_mod_engineering/handlers/tag_class.py` (the file you edit)
- `packages/tl-modules/engineering/src/tl_mod_engineering/registry.py`
- `packages/tl-modules/engineering/src/tl_mod_engineering/errors.py`
- `docs/tickets/P1-I1/provided/t07-test_tag_class_commands.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- pyright is `standard` for `packages/tl-modules`; ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing.
- Provided files live under `docs/tickets/P1-I1/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I1/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*` table or change `schema/**` or anything under `generated/` unless this ticket says so.
- The test runs against a real ledger: `open_uow(db)` is a unit of work that commits when the `with` block ends normally and rolls back when an exception leaves it. Raise before appending and nothing is written.
- Parity (L-P0-I5-A8): the test uses the `new_db` fixture and runs on both databases. Postgres is native: `sudo pg_ctlcluster 16 main start` if it is not running; then `TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-modules/engineering/tests/test_tag_class_commands.py -q --adapters sqlite,postgres`.
- A handler never commits and never catches a `ServiceError` to hide it.

## Allowed paths
- `packages/tl-modules/engineering/src/tl_mod_engineering/handlers/tag_class.py` (edit)
- `packages/tl-modules/engineering/tests/test_tag_class_commands.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I1/P1-I1-T07.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I1/provided/t07-test_tag_class_commands.py.txt` to `packages/tl-modules/engineering/tests/test_tag_class_commands.py`.
3. Implement the three handlers by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-modules/engineering/tests/test_tag_class_commands.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-modules/engineering/tests/test_tag_class_commands.py -q --adapters sqlite,postgres
uv run pytest packages/tl-modules -q
```
Expected: `just check` clean; 31 passed on SQLite; 56 passed with both adapters; the whole module package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the output of the parity run (decisive lines).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change in `registry.py`, `errors.py`, a projector or `schema/**`: those are not yours.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
