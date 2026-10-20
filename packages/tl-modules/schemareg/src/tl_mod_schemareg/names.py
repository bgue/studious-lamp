"""Names the schema registry module shares: record types, event types, tables, workflow states.

Plain constants, so a projector, a handler, a CLI command and a test all spell them the same way.
"""

from __future__ import annotations

from typing import Final

SCHEMA_PACKAGE: Final = "schemareg.SchemaPackage"
ADOPTION: Final = "schemareg.Adoption"
WAIVER: Final = "schemareg.Waiver"
RECORD_TYPES: Final = frozenset({SCHEMA_PACKAGE, ADOPTION, WAIVER})

PACKAGE_TABLE: Final = "cur_schemareg_schema_package"
ADOPTION_TABLE: Final = "cur_schemareg_adoption"
WAIVER_TABLE: Final = "cur_schemareg_waiver"
PACKAGE_VIEW: Final = "v_schemareg_schema_package"
ADOPTION_VIEW: Final = "v_schemareg_adoption"
WAIVER_VIEW: Final = "v_schemareg_waiver"

PACKAGE_DRAFTED: Final = "SchemaPackage.Drafted"
PACKAGE_REVISED: Final = "SchemaPackage.Revised"
PACKAGE_ANALYSED: Final = "SchemaPackage.Analysed"
PACKAGE_SUBMITTED: Final = "SchemaPackage.Submitted"
PACKAGE_CHANGES_REQUESTED: Final = "SchemaPackage.ChangesRequested"
PACKAGE_APPROVED: Final = "SchemaPackage.Approved"
PACKAGE_PUBLISHED: Final = (
    "SchemaPackage.Published"  # a core catalog event (schema/core/events.yaml)
)
PACKAGE_DEPRECATED: Final = "SchemaPackage.Deprecated"
PACKAGE_RETIRED: Final = "SchemaPackage.Retired"
ADOPTION_PINNED: Final = "Adoption.Pinned"
WAIVER_REQUESTED: Final = "Waiver.Requested"
WAIVER_APPROVED: Final = "Waiver.Approved"
WAIVER_REVOKED: Final = "Waiver.Revoked"

# SchemaPackage workflow states (schema/fixtures/workflows/schemareg-schema-package.yaml)
DRAFT: Final = "Draft"
IN_REVIEW: Final = "InReview"
APPROVED: Final = "Approved"
PUBLISHED: Final = "Published"
DEPRECATED: Final = "Deprecated"
RETIRED: Final = "Retired"
#: The states in which a version is part of the schema registry's effective schema.
IN_FORCE: Final = (PUBLISHED, DEPRECATED)

# Waiver workflow states
REQUESTED: Final = "Requested"
WAIVER_APPROVED_STATE: Final = "Approved"
REVOKED: Final = "Revoked"
