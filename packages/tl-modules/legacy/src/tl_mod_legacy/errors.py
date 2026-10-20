"""The expected failures of the legacy module. Each takes a readable message.

They subclass ``ServiceError``. A message is fixed text plus names and counts; it never holds a
cell of the file.
"""

from __future__ import annotations

from tl_core.services.errors import ServiceError


class LegacyError(ServiceError):
    """Base of the module's expected failures."""


class UnknownLoaderError(LegacyError):
    """No loader of that name is installed."""


class LoadRunNotFoundError(LegacyError):
    """No load run with that id or key."""


class LoadRunStateError(LegacyError):
    """The run is not in a state that allows the stage."""


class SourceFileError(LegacyError):
    """The file cannot be used: wrong kind, too large, or refused by the reader."""


class MappingProblemError(LegacyError):
    """The loader's mapping cannot be read, or does not fit the file."""


class LoadRefusedError(LegacyError):
    """The load cannot proceed; ``problems`` lists why."""

    def __init__(self, message: str, problems: list[str] | None = None) -> None:
        super().__init__(message)
        self.problems: list[str] = problems if problems is not None else []


class NotConfiguredError(LegacyError):
    """The process has no file service for load runs."""


class CompensationRefusedError(LegacyError):
    """The batch cannot be taken back as a whole; ``problems`` lists why."""

    def __init__(self, message: str, problems: list[str] | None = None) -> None:
        super().__init__(message)
        self.problems: list[str] = problems if problems is not None else []
