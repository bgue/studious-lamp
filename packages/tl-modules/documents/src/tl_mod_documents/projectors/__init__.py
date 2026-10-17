"""Projectors of this module, one file per projector (`tl new projector`)."""

from __future__ import annotations

from tl_mod_documents.projectors.derived_document import DerivedDocumentProjector
from tl_mod_documents.projectors.document import DocumentProjector
from tl_mod_documents.projectors.document_schema import DocumentSchemaProjector
from tl_mod_documents.projectors.processing_job import ProcessingJobProjector
from tl_mod_documents.projectors.rendition import RenditionProjector
from tl_mod_documents.projectors.review_cycle import ReviewCycleProjector
from tl_mod_documents.projectors.revision import RevisionProjector
from tl_mod_documents.projectors.transmittal import TransmittalProjector

__all__ = [
    "DerivedDocumentProjector",
    "DocumentProjector",
    "DocumentSchemaProjector",
    "ProcessingJobProjector",
    "RenditionProjector",
    "ReviewCycleProjector",
    "RevisionProjector",
    "TransmittalProjector",
]
