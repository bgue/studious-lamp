"""The values the document-register import passes between its steps (brief 9 M1, bulk import).

``mapping.read_rows`` turns a DMS export into ``ImportRow`` values; ``diff.plan_import`` compares
them with the documents the project already has and returns an ``ImportPlan``: what would be
registered, what is there already and which rows cannot be imported. Nothing here touches the
ledger; applying a plan is ``tl_mod_documents.imports.apply``.

The import registers **documents**. The revision, status and date columns of the legacy register
are kept as a note on the document (its description); the revisions themselves, with their files
and issue dates, arrive with the legacy loaders of P1-I8, because issuing a revision here needs a
rendition and an admin's decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ImportRow:
    """One data row of the file, after the mapping."""

    line: int  # row number of the file; the header is row 1, so the first data row is 2
    number: str  # the document number as written (stripped); empty when the cell was blank
    title: str | None
    doc_type: str | None  # the mapped document type code
    discipline: str | None  # the mapped discipline code
    originator: str | None
    legacy_revision: str | None  # the revision the old register shows, kept as a note
    legacy_status: str | None  # the status the old register shows, kept as a note
    legacy_date: str | None  # the date the old register shows, kept as a note
    problems: list[str] = field(default_factory=lambda: [])  # why the row cannot be used
    raw: dict[str, str] = field(default_factory=lambda: {})  # the row by column header

    @property
    def note(self) -> str | None:
        """The legacy columns as one sentence, for the document's description."""
        parts = [
            f"revision {self.legacy_revision}" if self.legacy_revision else None,
            f"status {self.legacy_status}" if self.legacy_status else None,
            f"dated {self.legacy_date}" if self.legacy_date else None,
        ]
        found = [p for p in parts if p]
        return "Legacy register: " + ", ".join(found) if found else None


@dataclass
class ImportPlan:
    new: list[ImportRow] = field(default_factory=lambda: [])  # would be registered
    exists: list[str] = field(default_factory=lambda: [])  # numbers the project already has
    invalid: list[ImportRow] = field(default_factory=lambda: [])  # rows that cannot be imported

    def counts(self) -> dict[str, int]:
        """``{"new": 3, "exists": 1, "invalid": 2}``."""
        return {"new": len(self.new), "exists": len(self.exists), "invalid": len(self.invalid)}
