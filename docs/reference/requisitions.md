# Reference — requisitions: API routes, MCP tools and CLI verbs

Purpose: the exact routes, tools and verbs of the requisitions module as built in P2-I4A. Module: `docs/modules/requisitions/README.md`.
Runbook: `docs/runbooks/requisitions.md`. Access words: `docs/reference/access-words.md`.

## API routes (`packages/tl-api/src/tl_api/routes/requisitions.py`)
Every read checks `requisitions.view` (table word `read`) before any lookup. A hidden record answers as a missing one.
Paths are the router's; the client builds them the same way.

| Method and path | Operation | Query | Returns |
|---|---|---|---|
| `GET /projects/{project}/requisitions` | `list_requisitions` | `kind` (`labor`, `material`, `general`, `scaffold`), `state`, `requester`, `for` (IWP or CWP key), `limit` (1 to 200, default 200) | requisition rows, by key |
| `GET /projects/{project}/requisitions/{key}` | `get_requisition` | none | one requisition with its kind's fields and its work order |
| `GET /projects/{project}/work-orders` | `list_work_orders` | `state`, `assigned_to`, `limit` (1 to 200, default 200) | work order rows, by key |
| `GET /projects/{project}/work-orders/{key}` | `get_work_order` | none | one work order with the key of its requisition |

Writes are not on these routes. The API builds one `POST /commands/<Name>` route per command of `REQUISITIONS_COMMANDS`:
`RaiseRequisition`, `EditRequisition`, `ApproveRequisition`, `RejectRequisition`, `CancelRequisition`,
`ScheduleWorkOrder`, `AssignWorkOrder`, `StartWorkOrder`, `CompleteWorkOrder`, `CloseWorkOrder`. Each checks its access word
(table in the module README).

## MCP tools (`packages/tl-mcp/src/tl_mcp/requisition_tools.py`)
| Tool | Kind | Arguments | Does |
|---|---|---|---|
| `list_requisitions` | read only | `project`, `kind`, `state`, `requester`, `for_key` | As the route, without `limit`. |
| `get_requisition` | read only | `project`, `key` | As the route. |
| `list_work_orders` | read only | `project`, `state`, `assigned_to` | As the route, without `limit`. Work orders of hidden requisitions are left out. |
| `get_work_order` | read only | `project`, `key` | As the route. |
| `propose_requisition` | proposes | `project`, `kind` (`labor`, `material`, `general`, `scaffold`), `subject`, `need_by`, `priority`, `for_key`, `craft`, `headcount`, `start_date`, `end_date`, `lines`, `general_type`, `purpose`, `duration_days`, plus the `intent` and `summary` arguments every proposal takes | Creates a proposal. Nothing is written to the requisition until a person with `requisitions.raise` accepts it. |

The four reads and the proposal are the only requisition tools; an agent cannot call a command. An agent is always
propose-only (`schema/settings/module-roles.yaml`). Known gap: the MCP reads do not check `requisitions.view` yet; the API and the CLI do
(`docs/build-spec/DEFERRED.md`).

## CLI verbs (`packages/tl-cli/src/tl_cli/req.py`, `req_write.py`, `req_read.py`)
Every verb takes `--db` or `TL_DB` (the ledger) and prints one line on success. Refusals are `error:` lines.

### `tl req`
| Verb | Options (required marked `*`) | Prints |
|---|---|---|
| `raise-labor` | `*--project`, `*--subject`, `*--craft`, `*--headcount`, `*--start`, `*--end`, `--classification`, `--shift`, `--requirements`, `--need-by`, `--priority`, `--for`, `--actor` | `raised <key>  version <v>` |
| `raise-material` | `*--project`, `*--subject`, `--line ITEMKEY:QTY:UOM` (repeat, 1 to 200), `--from-location`, `--need-by`, `--priority`, `--for`, `--actor` | `raised <key>  version <v>` |
| `raise-general` | `*--project`, `*--subject`, `*--type`, `--need-by`, `--priority`, `--for`, `--actor` | `raised <key>  version <v>` |
| `raise-scaffold` | `*--project`, `*--subject`, `*--purpose`, `*--days`, `--need-by`, `--priority`, `--for`, `--actor` | `raised <key>  version <v>` |
| `edit NUMBER` | `--project`, `--subject`, `--need-by`, `--priority`, `--craft`, `--headcount`, `--start`, `--end`, `--expected-version`, `--actor` | `edit <key>  version <v>` |
| `approve NUMBER` | `--project`, `--expected-version`, `--actor` | `approve <key>  version <v>` (opens the work order) |
| `reject NUMBER` | `--project`, `*--reason`, `--expected-version`, `--actor` | `reject <key>  version <v>` |
| `cancel NUMBER` | `--project`, `*--reason`, `--expected-version`, `--actor` | `cancel <key>  version <v>` |
| `ls` | `--project`, `--kind`, `--state`, `--requester`, `--for`, `--limit`, `--actor` | `requisitions: <n>`, then one line per row: key, kind, state, priority, need by, requester, subject |
| `show NUMBER` | `--project`, `--actor` | the state, the kind's fields, `serves <IWP>`, `work order <key>` or `-`, `approved by` |

### `tl wo`
| Verb | Options (required marked `*`) | Prints |
|---|---|---|
| `schedule NUMBER` | `*--project`, `*--start`, `*--finish`, `--hours`, `--expected-version`, `--actor` | `schedule <key>  version <v>` |
| `assign NUMBER` | `*--project`, `*--to` (`user:X` or text), `--expected-version`, `--actor` | `assign <key>  version <v>` |
| `start NUMBER` | `*--project`, `--at` (ISO), `--expected-version`, `--actor` | `start <key>  version <v>` |
| `complete NUMBER` | `*--project`, `--hours` (one decimal place), `--at` (ISO), `--expected-version`, `--actor` | `complete <key>  version <v>` |
| `close NUMBER` | `*--project`, `--expected-version`, `--actor` | `close <key>  version <v>` |
| `ls` | `*--project`, `--state`, `--assigned`, `--limit`, `--actor` | count line, then one line per work order |
| `show NUMBER` | `*--project`, `--actor` | the work order with the requisition it belongs to |

`--actor` defaults to the signed-in user. `--expected-version` is the version you read; a stale one is refused.
The fulfilment verb (`tl req fulfil`) does not exist yet (`docs/build-spec/DEFERRED.md`).

## Events and access
Events and their payloads: `docs/modules/requisitions/README.md`. Words and holders: `docs/reference/access-words.md`
and `schema/settings/module-roles.yaml`.
