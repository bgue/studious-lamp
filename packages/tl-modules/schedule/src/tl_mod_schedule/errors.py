"""The expected failures of the schedule module. Each takes a readable message.

They subclass ``ServiceError``; ``tl_api.errors`` maps each to a status and a stable code.
"""

from __future__ import annotations

from tl_core.services.errors import ServiceError


class ScheduleError(ServiceError):
    """Base of the module's expected failures."""


class ScheduleScopeError(ScheduleError):
    """Schedules belong to a project scope."""


class InvalidScheduleError(ScheduleError):
    """The schedule's code, type or P6 project is not usable; the message says which."""


class ScheduleNotFoundError(ScheduleError):
    """No schedule with that id or code in the scope."""


class SnapshotNotFoundError(ScheduleError):
    """No snapshot with that id, key or number in the schedule."""


class SnapshotStateError(ScheduleError):
    """The snapshot is not in a state that allows the change."""


class SourceFileError(ScheduleError):
    """The snapshot has no usable XER file (none attached, still scanning, rejected, too large)."""


class DuplicateSnapshotError(ScheduleError):
    """Another snapshot of the schedule was built from the same file."""


class StaleSnapshotError(ScheduleError):
    """The snapshot's data date is not later than the current snapshot's."""


class ActivityNotFoundError(ScheduleError):
    """The snapshot (or the current snapshot) has no activity with that id."""


class NoCurrentSnapshotError(ScheduleError):
    """The schedule has no published snapshot yet."""


class ScheduleNotConfiguredError(ScheduleError):
    """This process has no file service for schedule files; its command must give it one."""


class TablesMismatchError(ScheduleError):
    """The typed rows read again from the source file are not the ones the ledger recorded."""


class TooManyLinksError(ScheduleError):
    """The activity already has the most links one activity may have."""


class TooManyReferencesError(ScheduleError):
    """The schedule already has the most activity references it may have."""


class TypedRowsMissingError(ScheduleError):
    """The current snapshot's activities are not in the database (after a restore): run
    ``tl xer reconcile`` first. Judging links against missing rows would call every activity gone.
    """


class FutureDataDateError(ScheduleError):
    """The snapshot's data date is too far after today to be the current schedule."""
