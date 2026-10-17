"""The derivation pipeline over HTTP: reads and commands (P1-I3, ADR-0014).

The same models the embedded services return (``tl_mod_documents.derivation.views``, the diff,
report and plan models of that package). A refusal is the module's exception, rebuilt from the
error body. A derived document is named by its id or its key (``ISD-001@A/instrument-index``).
"""

from __future__ import annotations

from tl_core.services.commands import CommandResult
from tl_mod_documents.derivation import views
from tl_mod_documents.derivation.derived import (
    CancelJob,
    OpenDerivedDocument,
    StartExtraction,
    ValidateDerived,
    VoidDerivedDocument,
)
from tl_mod_documents.derivation.diff import DerivedDiff
from tl_mod_documents.derivation.publish import (
    CompensatePublication,
    CompensationPlan,
    PublishDerivedDocuments,
    PublishDerivedTags,
    PublishPlan,
)
from tl_mod_documents.derivation.schemas import RegisterDocumentSchema, RetireDocumentSchema
from tl_mod_documents.derivation.validation import ValidationReport

from tl_api.client.base import ApiClientBase, quote


class DerivationApi(ApiClientBase):
    # --- reads -----------------------------------------------------------------------------

    def list_document_schemas(
        self, project: str, *, code: str | None = None, include_retired: bool = False
    ) -> list[views.SchemaSummary]:
        """The schemas a project sees (``GET /projects/{p}/document-schemas``)."""
        params = {"code": code, "include_retired": "true" if include_retired else None}
        data = self._get_json(f"/projects/{quote(project)}/document-schemas", params)
        return self._models(views.SchemaSummary, data)

    def get_document_schema(self, project: str, ref: str) -> views.SchemaView:
        """One schema by ``code`` or ``code@semver``."""
        data = self._get_json(f"/projects/{quote(project)}/document-schemas/{quote(ref)}")
        return self._model(views.SchemaView, data)

    def list_derived_documents(
        self,
        project: str,
        *,
        state: str | None = None,
        document: str | None = None,
        schema: str | None = None,
        include_void: bool = False,
        limit: int = 200,
    ) -> list[views.DerivedSummary]:
        """A project's derived documents (``GET /projects/{p}/derived-documents``)."""
        params = {
            "state": state,
            "document": document,
            "schema": schema,
            "include_void": "true" if include_void else None,
            "limit": limit,
        }
        data = self._get_json(f"/projects/{quote(project)}/derived-documents", params)
        return self._models(views.DerivedSummary, data)

    def get_derived_document(self, project: str, ref: str) -> views.DerivedView:
        """One derived document with its content revisions and running job."""
        data = self._get_json(f"/projects/{quote(project)}/derived-documents/{quote(ref)}")
        return self._model(views.DerivedView, data)

    def list_processing_jobs(
        self,
        project: str,
        *,
        state: str | None = None,
        derived: str | None = None,
        limit: int = 200,
    ) -> list[views.JobView]:
        """A project's jobs, newest first (``GET /projects/{p}/processing-jobs``)."""
        params = {"state": state, "derived": derived, "limit": limit}
        data = self._get_json(f"/projects/{quote(project)}/processing-jobs", params)
        return self._models(views.JobView, data)

    def get_processing_job(self, project: str, job_id: str) -> views.JobView:
        data = self._get_json(f"/projects/{quote(project)}/processing-jobs/{quote(job_id)}")
        return self._model(views.JobView, data)

    def get_derived_rows(
        self,
        project: str,
        ref: str,
        *,
        content_rev: int | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> views.RowsPage:
        """A page of the extracted rows of a content revision."""
        params = {"content_rev": content_rev, "offset": offset, "limit": limit}
        data = self._get_json(f"/projects/{quote(project)}/derived-rows/{quote(ref)}", params)
        return self._model(views.RowsPage, data)

    def get_derived_report(
        self, project: str, ref: str, *, content_rev: int | None = None
    ) -> ValidationReport:
        """The stored validation report of a content revision."""
        data = self._get_json(
            f"/projects/{quote(project)}/derived-reports/{quote(ref)}",
            {"content_rev": content_rev},
        )
        return self._model(ValidationReport, data)

    def get_derived_diff(
        self,
        project: str,
        ref: str,
        *,
        against: str = "previous_pass",
        content_rev: int | None = None,
    ) -> DerivedDiff:
        """What changed against the previous pass or the previous revision."""
        data = self._get_json(
            f"/projects/{quote(project)}/derived-diffs/{quote(ref)}",
            {"against": against, "content_rev": content_rev},
        )
        return self._model(DerivedDiff, data)

    def check_derived_document(
        self,
        project: str,
        ref: str,
        *,
        schema: str | None = None,
        content_rev: int | None = None,
    ) -> ValidationReport:
        """Check stored rows against a schema now; nothing is stored."""
        data = self._get_json(
            f"/projects/{quote(project)}/derived-validations/{quote(ref)}",
            {"schema": schema, "content_rev": content_rev},
        )
        return self._model(ValidationReport, data)

    def get_publish_preview(
        self, project: str, ref: str, *, target: str | None = None
    ) -> PublishPlan:
        """What publishing would do with each row now."""
        data = self._get_json(
            f"/projects/{quote(project)}/derived-publish-previews/{quote(ref)}",
            {"target": target},
        )
        return self._model(PublishPlan, data)

    def get_compensation_preview(self, project: str, ref: str) -> CompensationPlan:
        """What compensating the publication in force would reverse."""
        data = self._get_json(
            f"/projects/{quote(project)}/derived-compensation-previews/{quote(ref)}"
        )
        return self._model(CompensationPlan, data)

    # --- commands (the token's actor is used) ------------------------------------------------

    def register_document_schema(self, cmd: RegisterDocumentSchema) -> CommandResult:
        """``POST /commands/RegisterDocumentSchema`` (admin)."""
        return self._command("RegisterDocumentSchema", cmd)

    def retire_document_schema(self, cmd: RetireDocumentSchema) -> CommandResult:
        """``POST /commands/RetireDocumentSchema`` (admin)."""
        return self._command("RetireDocumentSchema", cmd)

    def open_derived_document(self, cmd: OpenDerivedDocument) -> CommandResult:
        """``POST /commands/OpenDerivedDocument``."""
        return self._command("OpenDerivedDocument", cmd)

    def start_extraction(self, cmd: StartExtraction) -> CommandResult:
        """``POST /commands/StartExtraction``: queue an extraction job."""
        return self._command("StartExtraction", cmd)

    def validate_derived(self, cmd: ValidateDerived) -> CommandResult:
        """``POST /commands/ValidateDerived``: queue a validation job."""
        return self._command("ValidateDerived", cmd)

    def cancel_job(self, cmd: CancelJob) -> CommandResult:
        """``POST /commands/CancelJob``."""
        return self._command("CancelJob", cmd)

    def void_derived_document(self, cmd: VoidDerivedDocument) -> CommandResult:
        """``POST /commands/VoidDerivedDocument``."""
        return self._command("VoidDerivedDocument", cmd)

    def publish_derived_tags(self, cmd: PublishDerivedTags) -> CommandResult:
        """``POST /commands/PublishDerivedTags`` (admin): one correlated import."""
        return self._command("PublishDerivedTags", cmd)

    def publish_derived_documents(self, cmd: PublishDerivedDocuments) -> CommandResult:
        """``POST /commands/PublishDerivedDocuments`` (controller)."""
        return self._command("PublishDerivedDocuments", cmd)

    def compensate_publication(self, cmd: CompensatePublication) -> CommandResult:
        """``POST /commands/CompensatePublication`` (admin)."""
        return self._command("CompensatePublication", cmd)
