# tl-mod-materials (`tl_mod_materials`)

Materials module: the item library, storage locations, purchase-order lines, goods receipts with their material test reports, ledgered stock by lot, take-off (MTO) lines and reservations (brief §2.1, M4; spec `docs/build-spec/specs/m4-materials.md`).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_mod_materials.module:spec` | entry point `throughline.modules` (`materials`) | The `ModuleSpec`: record types, projectors, command words, offline drafts, company roles. |
| `tl_mod_materials.commands.MATERIALS_COMMANDS` | tuple of `CommandSpec` | Every command with its handler and access word (the API builds one route per row). |
| `tl_mod_materials.views` | module | Read models (`StockRowView`, `LotDetailView`, `ReceiptDetailView`, `MtoLineView`, ...) used by the API, CLI, TUI and MCP. |
| `tl_mod_materials.api.post_movements` | function | The public surface for posting stock movements from another module (for fulfilment); `by_module=True` skips the lot type's allow-list, never the access word. |
| `tl_mod_materials.mto.mto_target` | entry point `throughline.publish_targets` (`mto`) | Publish target for a derived take-off document (`PublishDerivedMto`). |
| `tl_mod_materials.readiness.materials_reserved` | entry point `throughline.readiness_checks` | Readiness check for an IWP: are its take-off lines covered by reservations and issues. |
| `tl_mod_materials.targets.*`, `loaders.materials` | entry points | Load targets and legacy loaders (table below). |

## Depends on / used by
- Depends on: `tl-core`, `tl-schema`, `tl-adapters`, `tl-mod-documents` (publish pipeline), `tl-mod-legacy` (loaders).
- Used by: `tl-api` (commands and reads), `tl-cli` (`tl mat`, `tl load`), `tl-mcp` (materials tools), `tl-tui` (six screens).

## Commands
Read a command's usage with `--help`; the CLI lives in `packages/tl-cli/src/tl_cli/mat*.py`.
```
uv run tl mat --help
uv run tl mat receipt --help
uv run tl mat mto --help
```

Access words are rows of `schema/settings/access-words.yaml`. A command needs its word; the default role is the role-table word that holds it.

| Access word | Commands | Default role |
|---|---|---|
| `materials.view` | every read (`tl mat stock`, `lot`, `movements`, `report`, `item`, `loc`, `po`, `mto list`, `mto show`, `receipt list`, `receipt show`) | read (viewer) |
| `materials.library.edit` | DefineItem, ReviseItem, RetireItem | controller (company superuser, else admin) |
| `materials.item.adopt` | AdoptItem | user |
| `materials.location.configure` | DefineLocation, ReviseLocation, RetireLocation | controller |
| `materials.po.edit` | RecordPoLine, UpdatePoLine | user |
| `materials.receive` | CreateReceipt (`tl mat receipt receive`), ReviseReceipt, InspectReceipt (`tl mat receipt inspect`) | user |
| `materials.receipt.decide` | AcceptReceipt (`tl mat receipt accept`), RejectReceipt (`tl mat receipt reject`) | user |
| `materials.void` | VoidReceipt (`tl mat receipt void`) | controller |
| `materials.move` | IssueStock, TransferStock, ReturnStock (`tl mat move issue\|transfer\|return`) | user |
| `materials.reserve` | ReserveStock, UnreserveStock (`tl mat move reserve\|unreserve`) | user |
| `materials.adjust` | AdjustStock, ScrapStock (`tl mat move adjust\|scrap`) | controller |
| `materials.mto.publish` | PublishDerivedMto | controller |
| `materials.mto.assign` | AssignMtoLines (`tl mat mto assign`) | user |

The ten commands that need the controller role are DefineItem, ReviseItem, RetireItem, DefineLocation, ReviseLocation, RetireLocation, VoidReceipt, AdjustStock, ScrapStock and PublishDerivedMto.

Agents: no materials command is in `AGENT_ACTIONS` (`tl_core.auth.provider`), so an agent is denied every one of them. An agent acts through the ten MCP tools below only.

## Load targets and loaders
| Loader (`tl load open --loader`) | System/table | Target | Scope |
|---|---|---|---|
| `mat-items` | `mat/items` | `materials_item_master` | company (`--company`) |
| `mat-locations` | `mat/locations` | `materials_location` | project (`--project P123`) |
| `mat-po-lines` | `mat/po_lines` | `materials_po_line` | project (`--project P123`) |

```
uv run tl load loaders
uv run tl load targets
```

## MCP tools (`packages/tl-mcp/src/tl_mcp/materials_tools.py`)
`MATERIALS_MCP_ACTIONS` names these ten `mcp.<tool>` actions.

| Tool | Kind | Answers |
|---|---|---|
| `list_material_stock` | read | Balances by lot and location (`on_hand`, `reserved`, `available`). |
| `get_material_lot` | read | One lot with balances, reservations and its last ten movements. |
| `list_material_movements` | read | Movements, oldest first, by lot, date and kind. |
| `list_material_receipts` | read | Receipts by number, with MTR status. |
| `get_material_receipt` | read | One receipt with its lines, dates, people and files. |
| `list_material_locations` | read | Storage locations in tree order. |
| `list_po_lines` | read | Purchase-order lines by key. |
| `list_mto_lines` | read | Take-off lines with required, reserved, issued and short. |
| `list_material_items` | read | The item library, or the items one project adopted. |
| `propose_reservation` | proposes | Files a pending reservation; nothing changes until a person with `materials.reserve` accepts it. |

## Screens (TUI)
Open a screen from the key or the palette (`Ctrl+P`); the palette id is the name in `packages/tl-tui/src/tl_tui/commands.py`.

| Key | Palette id | Screen | Class (`packages/tl-tui/src/tl_tui/widgets/`) |
|---|---|---|---|
| `S` | `stock` | Stock: lots on hand by location | `stock_screen.StockScreen` |
| `M` | `movements` | Movements: receipts, issues, transfers, holds | `movement_screen.MovementLogScreen` |
| `D` | `mto-lines` | Take-off lines: required, reserved, issued, short | `mto_screen.MtoLinesScreen` |
| `E` | `receipts` | Receipts: deliveries, inspection, MTR | `receipt_log.ReceiptLogScreen` |
| `I` | `items` | Items: the company item library (no project needed) | `item_library.ItemLibraryScreen` |
| `W` | `locations` | Locations: storage places and what they hold | `location_screen.LocationScreen` |

The keys are in `packages/tl-tui/src/tl_tui/keymap.py` and bound in `packages/tl-tui/src/tl_tui/app.py`. The screens are read-only: they call the same reads as the API.

## Offline classes
| Record type | Offline class (`schema/modules/materials/`) | Works without the API |
|---|---|---|
| `materials.StockLot` | `draft_only` | `IssueStock`, `TransferStock`, `ReturnStock` are captured as drafts and posted on sync (`STOCK_LOT_DRAFTS` in `module.py`). |
| `materials.Receipt` | `draft_only` | The schema says so, but the module registers no drafting command for it: nothing is captured offline. |
| Items, locations, PO lines, MTO and MTO lines | `none` | Nothing. |

## Configuration
| Setting | Default | Notes |
|---|---|---|
| `materials.receipt.mtr_required_categories` | `[]` | Item categories whose receipts need an available `mtr` file before Accept. Platform, company or project scope; lockable. |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P2-I3 (schema S1, package S2, receipts and movements S3, MTO S4, readiness T03).
Last interface change: P2-I3.
