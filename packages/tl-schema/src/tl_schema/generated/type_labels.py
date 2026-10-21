"""Display names of record types, from class titles. Do not edit by hand."""

from __future__ import annotations

from typing import Final

TYPE_LABELS: Final[dict[str, str]] = {
    "core.Record": "Record",
    "correspondence.CommercialItem": "Commercial item",
    "correspondence.ContractClause": "Contract clause",
    "correspondence.Correspondence": "Correspondence",
    "correspondence.CorrespondenceThread": "Correspondence thread",
    "correspondence.Party": "Party",
    "correspondence.ResponseClock": "Response clock",
    "correspondence.TechnicalItem": "Technical item",
    "cost.CostCode": "Cost code",
    "cost.CostSnapshot": "Cost snapshot",
    "documents.DerivedDocument": "Derived document",
    "documents.Document": "Document",
    "documents.DocumentSchema": "Document schema",
    "documents.ProcessingJob": "Processing job",
    "documents.Rendition": "Rendition",
    "documents.ReviewCycle": "Review cycle",
    "documents.Revision": "Revision",
    "documents.Transmittal": "Transmittal",
    "engineering.CodeList": "Code list",
    "engineering.CodeValue": "Code value",
    "engineering.Mnemonic": "Mnemonic",
    "engineering.NumberingPattern": "Numbering pattern",
    "engineering.Tag": "Tag",
    "engineering.TagClass": "Tag class",
    "legacy.LoadRun": "Load run",
    "schedule.ActivityRef": "Activity reference",
    "schedule.Schedule": "Schedule",
    "schedule.ScheduleSnapshot": "Schedule snapshot",
    "schemareg.Adoption": "Adoption",
    "schemareg.SchemaPackage": "Schema package",
    "schemareg.Waiver": "Waiver",
}
