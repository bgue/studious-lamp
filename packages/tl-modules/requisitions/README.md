# tl-mod-requisitions (`tl_mod_requisitions`)

Requisitions and work orders (brief §9, M9): the abstract `Requisition` and its four kinds (labour, material,
general, scaffold request) and the `WorkOrder` that approval opens. Schema: `schema/modules/requisitions/`;
contract: `docs/build-spec/phase2-contracts-draft.md` §3.

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_mod_requisitions.module:spec` | entry point `throughline.modules` (`requisitions`) | The `ModuleSpec`: record types and projectors. No command yet (P2-I4A S2). |
| `tl_mod_requisitions.names` | module | Record types, tables, event types, kinds. |
| `tl_mod_requisitions.projectors` | package | `RequisitionProjector` (four kinds) and `WorkOrderProjector`. |

## Depends on / used by
- Depends on: `tl-core`, `tl-schema`.
- Used by: nothing yet.
