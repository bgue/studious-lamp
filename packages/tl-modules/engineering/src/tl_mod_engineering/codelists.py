"""The code-list service: resolve a value, apply a list's policy to a new value (brief 6.3, 6.4).

A code list is a company record (``engineering.CodeList``) with a ``value_list_policy``; its
values are ``engineering.CodeValue`` records, company values in ``company`` scope and a project's
own values in that project's scope. A project's local values always map to company values
for reporting:

* ``closed``: only company values; a project cannot add one.
* ``extensible``: a project may add a value if it names an active company value of the list as its
  ``crosswalk``.
* ``project_defined``: the project owns its values; a crosswalk is optional and, when given, must
  name an active company value.

``resolve`` answers "what does this code mean here, and which company code is it?".
``plan_new_value`` applies the policy before a value is added; the registry command calls it and
writes nothing itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Connection

from tl_mod_engineering import registry
from tl_mod_engineering.errors import (
    CrosswalkRequiredError,
    DuplicateCodeValueError,
    InvalidCrosswalkError,
    ListClosedError,
    UnknownCodeError,
    UnknownCodeListError,
)
from tl_mod_engineering.names import COMPANY


@dataclass(frozen=True)
class Resolution:
    code_list: str
    scope: str  # where the value is defined: company or the project
    code: str
    label: str
    company_code: (
        str | None
    )  # the company code it stands for; None for a project value with no crosswalk
    origin: str  # company | project
    lifecycle: str
    usable: bool  # active and inside its effective dates on the day asked

    @property
    def via_crosswalk(self) -> bool:
        return self.company_code is not None and self.company_code != self.code


@dataclass(frozen=True)
class ValuePlan:
    """What a new value will be: the origin and the crosswalk the policy settled on."""

    origin: str
    crosswalk: str | None


def code_list(conn: Connection, name: str) -> registry.StandardRow:
    """The active company code list ``name``. Raises ``UnknownCodeListError``."""
    found = registry.active_standard(conn, COMPANY, "code_list", name)
    if found is None:
        raise UnknownCodeListError(f"no active code list {name!r}")
    return found


def _in_dates(row_from: str | None, row_to: str | None, on: date) -> bool:
    day = on.isoformat()
    return (row_from is None or row_from <= day) and (row_to is None or day <= row_to)


def _resolution(value: registry.CodeValueRow, on: date) -> Resolution:
    company_code = value.code if value.origin == "company" else value.crosswalk
    return Resolution(
        code_list=value.code_list,
        scope=value.scope,
        code=value.code,
        label=value.label,
        company_code=company_code,
        origin=value.origin,
        lifecycle=value.lifecycle,
        usable=value.active and _in_dates(value.effective_from, value.effective_to, on),
    )


def resolve(
    conn: Connection, scope: str, name: str, code: str, *, on: date | None = None
) -> Resolution:
    """What ``code`` means in code list ``name`` for ``scope``.

    The scope's own value wins over the company's (a project cannot reuse a company code, so this
    only matters for history). A retired or superseded value still resolves, with ``usable`` false.
    Raises ``UnknownCodeListError`` and ``UnknownCodeError``.
    """
    code_list(conn, name)
    day = on or date.today()
    for where in dict.fromkeys([scope, COMPANY]):
        value = registry.find_code_value(conn, where, name, code)
        if value is not None:
            return _resolution(value, day)
    raise UnknownCodeError(f"{code!r} is not a value of {name}")


def values(
    conn: Connection, scope: str, name: str, *, on: date | None = None, usable_only: bool = True
) -> list[Resolution]:
    """The values of list ``name`` visible to ``scope``: the company's, then the project's own."""
    code_list(conn, name)
    day = on or date.today()
    found: list[Resolution] = []
    for where in dict.fromkeys([COMPANY, scope]):
        found += [_resolution(v, day) for v in registry.code_values(conn, where, name)]
    return [r for r in found if r.usable] if usable_only else found


def plan_new_value(
    conn: Connection, *, scope: str, name: str, code: str, crosswalk: str | None
) -> ValuePlan:
    """Apply the list's policy to a value about to be added in ``scope``.

    Raises ``UnknownCodeListError``, ``DuplicateCodeValueError`` (the scope or the company already
    has the code), ``ListClosedError``, ``CrosswalkRequiredError`` and ``InvalidCrosswalkError``.
    """
    listed = code_list(conn, name)
    if registry.find_code_value(conn, scope, name, code) is not None:
        raise DuplicateCodeValueError(f"{name} already has a value {code!r} in scope {scope!r}")
    if scope == COMPANY:
        if crosswalk is not None:
            raise InvalidCrosswalkError("a company value has no crosswalk")
        return ValuePlan(origin="company", crosswalk=None)
    if registry.find_code_value(conn, COMPANY, name, code) is not None:
        raise DuplicateCodeValueError(f"{name} already has the company value {code!r}")
    policy = listed.value_list_policy or "closed"
    if policy == "closed":
        raise ListClosedError(f"{name} is closed: a project cannot add {code!r}")
    if crosswalk is None:
        if policy == "extensible":
            raise CrosswalkRequiredError(
                f"{name} is extensible: {code!r} must name the company value it maps to"
            )
        return ValuePlan(origin="project", crosswalk=None)
    target = registry.find_code_value(conn, COMPANY, name, crosswalk)
    if target is None or not target.active:
        raise InvalidCrosswalkError(f"{crosswalk!r} is not an active company value of {name}")
    return ValuePlan(origin="project", crosswalk=crosswalk)
