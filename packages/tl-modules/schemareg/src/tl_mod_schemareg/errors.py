"""The expected failures of the schema registry module. Each takes a readable message.

They subclass ``ServiceError``; ``tl_api.errors`` maps each to a status and a stable code.
"""

from __future__ import annotations

from tl_core.services.errors import ServiceError


class SchemaRegistryError(ServiceError):
    """Base of the module's expected failures."""


class InvalidSchemaPackageError(SchemaRegistryError):
    """The package YAML, its name, its version or its place in the registry is not usable."""


class DuplicateSchemaPackageError(SchemaRegistryError):
    """That ``name@version`` exists already, in the registry or as a package file."""


class SchemaPackageNotFoundError(SchemaRegistryError):
    """No schema package with that id or ``name@version``."""


class SchemaPackageStateError(SchemaRegistryError):
    """The package is not in a state that allows the act (drafts change, published ones do not)."""


class StaleAnalysisError(SchemaRegistryError):
    """The classification and impact reports were made for other content (or none were made)."""


class SelfReviewError(SchemaRegistryError):
    """The author of a package or the requester of a waiver cannot approve it."""


class NotTheAuthorError(SchemaRegistryError):
    """Only the actor that drafted a package revises, analyses or submits it."""


class AdoptionError(SchemaRegistryError):
    """The pin cannot be made: the version is not adoptable, or does not compose for the project."""


class ImpactReviewRequiredError(SchemaRegistryError):
    """A pin that is not purely additive needs the digest of the impact report the adopter read."""


class InvalidWaiverError(SchemaRegistryError):
    """The waiver's path, date or reason is not usable, or the project cannot honour waivers."""


class WaiverNotFoundError(SchemaRegistryError):
    """No waiver with that id."""


class WaiverStateError(SchemaRegistryError):
    """The waiver is not in a state that allows the act."""


class SchemaScopeError(SchemaRegistryError):
    """The act needs a project (or the company) scope it was not given."""


class EffectiveTimeError(SchemaRegistryError):
    """A command carries a simulated time but writes to a scope that is not a simulation."""
