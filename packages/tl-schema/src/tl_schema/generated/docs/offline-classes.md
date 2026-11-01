# Offline classes

Generated from `tl:offline` and `tl:stream_type` in `schema/`. Do not edit by hand.

Classes:

- `full`: Created and edited offline, merged on sync.
- `draft_only`: Drafts offline; issue, number and sign happen on the authority.
- `none`: Online only.

## Record types

| Record type | Label | Class | Meaning |
|---|---|---|---|
| `core.Record` | Record | `full` | Created and edited offline, merged on sync. |
| `correspondence.CommercialItem` | Commercial item | `none` | Online only. |
| `correspondence.ContractClause` | Contract clause | `none` | Online only. |
| `correspondence.Correspondence` | Correspondence | `draft_only` | Drafts offline; issue, number and sign happen on the authority. |
| `correspondence.CorrespondenceThread` | Correspondence thread | `none` | Online only. |
| `correspondence.Party` | Party | `none` | Online only. |
| `correspondence.ResponseClock` | Response clock | `none` | Online only. |
| `correspondence.TechnicalItem` | Technical item | `draft_only` | Drafts offline; issue, number and sign happen on the authority. |
| `cost.CostCode` | Cost code | `none` | Online only. |
| `cost.CostSnapshot` | Cost snapshot | `none` | Online only. |
| `documents.DerivedDocument` | Derived document | `none` | Online only. |
| `documents.Document` | Document | `draft_only` | Drafts offline; issue, number and sign happen on the authority. |
| `documents.DocumentSchema` | Document schema | `none` | Online only. |
| `documents.ProcessingJob` | Processing job | `none` | Online only. |
| `documents.Rendition` | Rendition | `draft_only` | Drafts offline; issue, number and sign happen on the authority. |
| `documents.ReviewCycle` | Review cycle | `none` | Online only. |
| `documents.Revision` | Revision | `draft_only` | Drafts offline; issue, number and sign happen on the authority. |
| `documents.Transmittal` | Transmittal | `draft_only` | Drafts offline; issue, number and sign happen on the authority. |
| `engineering.CodeList` | Code list | `none` | Online only. |
| `engineering.CodeValue` | Code value | `none` | Online only. |
| `engineering.Mnemonic` | Mnemonic | `none` | Online only. |
| `engineering.NumberingPattern` | Numbering pattern | `none` | Online only. |
| `engineering.Tag` | Tag | `full` | Created and edited offline, merged on sync. |
| `engineering.TagClass` | Tag class | `none` | Online only. |
| `legacy.LoadRun` | Load run | `none` | Online only. |
| `materials.InventoryLocation` | Inventory location | `none` | Online only. |
| `materials.ItemMaster` | Item master | `none` | Online only. |
| `materials.MTO` | Material take-off | `none` | Online only. |
| `materials.MTOLine` | Material take-off line | `none` | Online only. |
| `materials.POLineRef` | PO line | `none` | Online only. |
| `materials.ProjectItem` | Project item | `none` | Online only. |
| `materials.Receipt` | Receipt | `draft_only` | Drafts offline; issue, number and sign happen on the authority. |
| `materials.StockLot` | Stock lot | `draft_only` | Drafts offline; issue, number and sign happen on the authority. |
| `schedule.ActivityRef` | Activity reference | `none` | Online only. |
| `schedule.Schedule` | Schedule | `none` | Online only. |
| `schedule.ScheduleSnapshot` | Schedule snapshot | `none` | Online only. |
| `schemareg.Adoption` | Adoption | `none` | Online only. |
| `schemareg.SchemaPackage` | Schema package | `none` | Online only. |
| `schemareg.Waiver` | Waiver | `none` | Online only. |

## Core streams

| Stream | Class | Meaning |
|---|---|---|
| `core.Account` | `none` | Online only. |
| `core.ActionDefinition` | `none` | Online only. |
| `core.ActionInvocation` | `none` | Online only. |
| `core.ActivityPost` | `full` | Created and edited offline, merged on sync. |
| `core.Enricher` | `none` | Online only. |
| `core.EnrichmentValue` | `none` | Online only. |
| `core.InboundDelivery` | `none` | Online only. |
| `core.InboundEndpoint` | `none` | Online only. |
| `core.IntegrationApp` | `none` | Online only. |
| `core.Proposal` | `none` | Online only. |
| `core.Rule` | `none` | Online only. |
| `core.Setting` | `none` | Online only. |
| `core.Thread` | `full` | Created and edited offline, merged on sync. |
| `core.TypeRegistration` | `none` | Online only. |
| `core.WebhookSubscription` | `none` | Online only. |
