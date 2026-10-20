"""Errors of the integration layer (P1-I7). Each has a row in ``tl_api/errors.py``."""

from __future__ import annotations

from tl_core.services.errors import ServiceError


class InvalidIntegrationError(ServiceError):
    """A definition (rule, action, endpoint, enricher, app) cannot be stored as written."""


class IntegrationNotFoundError(ServiceError):
    """No such rule, action, endpoint, enricher, app or value."""


class DuplicateIntegrationError(ServiceError):
    """The name or key is taken."""


class IntegrationStateError(ServiceError):
    """The record is already in the state asked for, or its state does not allow the change."""


class ActionAccessError(ServiceError):
    """The caller does not hold the access an action needs."""


class CommandAccessError(ServiceError):
    """The command's own actor does not hold the access the command needs (the runner's check)."""
