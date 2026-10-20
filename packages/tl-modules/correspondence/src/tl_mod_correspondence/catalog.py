"""What a handler needs from the schema directory: the domains and the calendars in force.

Domains and calendars are files (``schema/fixtures/correspondence/domains``, ``.../calendars``).
``domain_set`` reads the domain folder and checks it against the workflows, the numbering patterns
and the register sources; the answer is kept until a file changes (content hash, as the schema
provider does), so a domain edit takes effect on the next command. A file with a problem makes the
whole set unusable: every command that needs a domain then fails with ``UnknownDomainError`` naming
the problem, never with a guess. ``use_domains`` installs a set for the length of a block (tests).
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date

from tl_core.numbering.config import get_numbering
from tl_core.workflow.loader import default_workflows
from tl_schema.registry import default_schema_dir

from tl_mod_correspondence import sources
from tl_mod_correspondence.calendars import (
    Calendar,
    CalendarError,
    list_calendars,
    load_calendar,
    split_ref,
)
from tl_mod_correspondence.domains import DomainDefinition, DomainError, DomainSet, load_domains
from tl_mod_correspondence.errors import CalendarUnavailableError, UnknownDomainError

_lock = threading.Lock()
_cache: tuple[str, DomainSet] | None = None
_override: DomainSet | None = None


def _signature() -> str:
    """A hash of every file a domain check reads: the schema directory, its name and contents."""
    root = default_schema_dir()
    digest = hashlib.sha256(str(root).encode())
    for subfolder in ("correspondence/domains", "workflows", "numbering"):
        place = root / subfolder
        if place.is_dir():
            for path in sorted(place.glob("*.yaml")):
                digest.update(path.name.encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()


def domain_set() -> DomainSet:
    """The checked domain definitions in force. Raises ``UnknownDomainError`` on a bad file."""
    global _cache
    if _override is not None:
        return _override
    signature = _signature()
    with _lock:
        if _cache is not None and _cache[0] == signature:
            return _cache[1]
        try:
            found = load_domains(
                default_schema_dir(),
                workflows=default_workflows(),
                numbering=get_numbering(),
                sources=sources.SOURCE_NAMES,
            )
        except DomainError as exc:
            raise UnknownDomainError(f"the domain definitions cannot be used: {exc}") from exc
        _cache = (signature, found)
        return found


@contextmanager
def use_domains(domains: DomainSet) -> Generator[None]:
    """Install ``domains`` for the duration of the block (tests and embedders)."""
    global _override
    previous, _override = _override, domains
    try:
        yield
    finally:
        _override = previous


def find_domain(scope: str, code: str) -> DomainDefinition:
    """The definition that governs ``code`` in ``scope``. Raises ``UnknownDomainError``."""
    found = domain_set().find(code, scope)
    if found is None:
        known = ", ".join(domain_set().codes()) or "none defined"
        raise UnknownDomainError(f"no domain {code!r} applies in {scope} (known: {known})")
    return found


def check_subtype(scope: str, domain: str, subtype: str) -> DomainDefinition:
    """The definition, once ``subtype`` is known to belong to ``domain``."""
    definition = find_domain(scope, domain)
    if definition.subtype(subtype) is None:
        codes = ", ".join(s.code for s in definition.subtypes)
        raise UnknownDomainError(f"domain {domain!r} has no subtype {subtype!r} (known: {codes})")
    return definition


def default_calendar_ref(scope: str) -> str:
    """``<project>-default@<highest version>`` for a project scope, else the company's.

    Raises ``CalendarUnavailableError`` when no such calendar file exists: a clock never counts
    on a calendar nobody wrote (fail closed).
    """
    project = scope.removeprefix("project:") if scope.startswith("project:") else "company"
    wanted = f"{project}-default"
    versions: list[int] = []
    for ref in list_calendars():
        code, version = split_ref(ref)
        if code == wanted:
            versions.append(version)
    if not versions:
        raise CalendarUnavailableError(f"there is no calendar {wanted!r} for {scope}")
    return f"{wanted}@{max(versions)}"


def calendar_for(ref: str, scope: str | None = None) -> Calendar:
    """The calendar ``ref``. Raises ``CalendarUnavailableError`` (unknown, unreadable, or one of
    another project than ``scope``)."""
    try:
        calendar = load_calendar(ref)
    except CalendarError as exc:
        raise CalendarUnavailableError(str(exc)) from exc
    if scope is not None and calendar.scope not in ("company", scope):
        raise CalendarUnavailableError(f"calendar {ref} belongs to {calendar.scope}, not {scope}")
    return calendar


def due_for(calendar: Calendar, start_on: date, days: int, day_type: str) -> date:
    """The due date; a count that leaves the calendar's range is ``CalendarUnavailableError``."""
    try:
        return calendar.add_days(start_on, days, day_type)
    except CalendarError as exc:
        raise CalendarUnavailableError(str(exc)) from exc
