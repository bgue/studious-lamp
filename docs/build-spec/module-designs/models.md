# M12 — Models (3D): IFC ingest, mapping, slices, workspace, model context

Brief §23, §10.6 sketches 9 and 10, §16 Phase 3 ("progress colour-overlaid in the model"). Plan `09-phase3-plan.md`
I6 (ingest, objects, mapping, slices) and I7 (workspace, viewpoints, overlays, spatial context, TUI panel).
Status: design v0.1. Licence gates (Q9, P3-Q9) precede any viewer code.

## Users and stories
Model or BIM coordinator, engineers and planners (locate, slices per IWP), QC and field (raise from a view), client
(viewpoints on RFIs), everyone (model context on a record).
- As a **model coordinator** I upload a new IFC revision, see it validated and converted, and review the objects the
  mapping rules could not tie to a tag.
- As a **workface planner** every IWP gets a slice under the size limit when a revision is published, and the pack
  carries its snapshot.
- As a **QC inspector** I raise a punch or an NCR from the view I am looking at and the viewpoint travels with it.
- As an **engineer** I open any weld, NCR or RFI and see where it is, even when nobody set a location on it.

## Records and states
| Record | States |
|---|---|
| `ModelDocument` | An M1 `Document` of type `model` (built); the IFC is its revision file |
| `ModelRevision` (`derived from` the document revision) | Uploaded → Validated / Invalid (IDS) → Converted → Mapped → Published → Superseded |
| `ModelObject` | Operational rows per revision (not records): GlobalId, class, name, storey, `ifc.*` properties, bounding box |
| `ObjectMappingRule` | Active → Retired; proposals when ambiguous |
| `FederatedView`, `Viewpoint`, `Overlay` | Saved; a viewpoint attaches to any record |
| `ModelSlice`, `SliceRule` | Requested → Generated → Published (`mobile` or `desktop_only`) → Superseded; floating slices regenerate on publish |

## Logs and record screens (TUI, log standard)
**Model revisions log.** Columns: Document, Rev, State, IFC schema, Objects, Mapped %, Slices, Published. Panel:
identity `MOD-PIP-001 rev C · Piping model, areas A12 to A14`; state `Mapped · 2 134 objects, 91% mapped`; summary
`IFC4 · piping · 184 MB · 12 slices`. Sections: Validation (schema, IDS result), Conversion (XKT, thumbnails),
Mapping (by rule: matched, ambiguous, unmatched), Diff vs previous (added, removed, changed; tag coverage), Slices
(table For, Rule, IFC MB, Eligibility, State), Files, Timeline. Actions: Uploaded: Validate. Validated: Convert,
Run mapping. Mapped: Publish (controller), Generate slices. Published: Supersede (by a new revision), Regenerate
slices. Any: Open thread.
**Object table** per revision: GlobalId, Class, Name, Storey, Mapped to; `/` searches names and properties; Enter
opens the mapped record or a chooser. **Mapping review queue**: Object, Candidates, Rule, actions Accept, Choose,
Skip (the P1-I7 review-queue pattern). **Slice list**: Slice, For (IWP, test package, subsystem, CWA), Rule, IFC MB,
Eligibility, State; action Regenerate. **Revision diff**: a compare screen (the XER compare pattern).
**Model context panel** on any record (`M`): location breadcrumb (area, level, grid), nearby tagged objects, linked
objects by status, `ctx_source` (direct, mapped, located, inherited, area); `B` deep link or QR; `P` pair with an
open web viewer; a server-rendered snapshot only if P3-Q13 says build. Action Locate in model sets the xref fields.
**Web model workspace** (the first browser page of the product, §23.3): split view with the viewer on one side and
the standard record panel and result list on the other, one search bar over the query language (records, objects,
locations), two-way selection, overlays from saved queries (weld state, ITR status, IWP readiness, test package
state, punch, scaffolds) updated from the change feed, viewpoints saved and attached, federation of revisions, bulk
link objects to a record, raise RFI, punch or NCR from the view. The guest-link page embeds the same component.
**Tiles:** unmapped objects by class, slices over the size limit, revisions awaiting publish.

## Workflows and approvals
Pipeline (§23.2): upload as a document revision → `models.ingest` (IfcOpenShell in the envelope; schema check;
optional IDS) → `models.convert` (XKT via Node when present, else `desktop_only`) → object extraction → mapping →
diff → publish (controller) → slices per IWP, test package and subsystem with the size gate and automatic split →
`models.context` recompute. Model-derived properties publish into Engineering Data through a `PublishMapping` kind
`model_props` with provenance to the revision; nothing else writes tags from a model. Bounds refuse oversize files
and object counts rather than truncating (R-P3-6).

## Links to other modules
Documents (revision, transmittal, pin); tags, lines, spools, equipment (mapping links `references`); IWP, test
package, subsystem, CWA (slices and bounding boxes); RFI, NCR, punch, correspondence, posts (viewpoints); welds (via
spool, iso, line), scaffolds (location) through `tl:spatial_context_via`; schedule (an overlay by activity dates,
**proposed** later).

## Integrations
Webhooks `ModelRevision.Published`, `ModelSlice.Updated` (feed card "IWP-PIP-0042 model slice updated: 14 objects
changed"). BCF 3.0 import and export of viewpoints. IDS validation report stored like a derived-document report.
MCP read tools (object lookup, context of a record, mapping coverage). Enrichment hook on publish.

## Reports
Mapping coverage by class and discipline; unmapped and ambiguous objects; slices by size and eligibility; revision
diff summary; records with and without model context (`has:model_context`).

## Confidentiality and roles
A model revision follows its document's class; objects and context of a hidden record are hidden; the viewer shows
only models the viewer may see; the guest page shows the one record's context. Upload: `user`; publish and mapping
rules: `controller`; accept a mapping proposal: `user`; agents read only. The xeokit SDK is AGPL (Q9): viewer code
lives only in `web/` behind the `ModelViewer` interface with a `NullViewer`, never in a distributed build without a
licence decision (R-P3-5).

## First increment vs later
First (Phase 3): I6 ingest, validation, conversion with stub fallback, objects, mapping engine and review queue,
diff, slices, `model_props` publication, TUI screens, reports; I7 the `ModelViewer` interface and workspace, tools,
viewpoints and BCF, overlays, bulk link, raise from view, spatial context resolver, `cur_models_context`, TUI panel,
pairing, guest page (with I8).
Later: headless snapshots in the TUI (P3-Q13); mobile slices in the PWA (Phase 5); 4D overlay by schedule
**(proposed)**; alternative viewer (web-ifc) if the licence decision requires; clash and design review stay out of
scope.

## Open questions for the owner
P3-Q3 models as a document type (recommended) or a subclass; P3-Q9 Node, Playwright, xeokit and IfcOpenShell
licences and toolchain; P3-Q13 TUI snapshots. New: which discipline's model arrives first and in which IFC schema
(drives the fixture)? Is the web workspace acceptable as the first browser surface, and does that pull the full web
client earlier (README §4)? Is BCF exchange with the engineer's design tools required in v1?
