# Reference: punch list (routes, tools, verbs, commands)

Purpose: the exact names of the punch list's routes, MCP tools, CLI verbs and module commands, as built in P2-PUNCH.
How to do the work: [punch-list runbook](../runbooks/punch-list.md). Module: [quality](../modules/quality/README.md).

## API routes
Relative to the API root. Each needs `quality.view` for the signed-in person; a hidden item is absent from lists and gives the
same 404 text as a missing one.

| Method and path | operation_id | Returns |
|---|---|---|
| `GET /projects/{project}/punch` | `list_punch_items` | the items by key, with the total number of matches |
| `GET /projects/{project}/punch/{key}` | `get_punch_item` | one item with its fields and its history |
| `GET /projects/{project}/punch-counts` | `get_punch_counts` | the count of items in each state |

The routes are read-only. Writes go through the commands below (CLI, or the module command API).

## MCP tools
| Tool | Annotation | What it does |
|---|---|---|
| `list_punch_items` | read-only | Lists a project's items by key, with filters (`state`, `area`, `system`, `assignee`, `category`, `overdue`) and the page total |
| `get_punch_item` | read-only | One item, with its fields and history (`project`, `key`) |
| `propose_punch_item` | proposes | Files a pending proposal to raise an item (`subject` required; `description`, `area`, `system`, `assignee`, `from_key` optional). Nothing is raised until a person accepts |

No MCP tool clears, verifies, edits, reopens or voids. Their action names (`mcp.clear_punch_item`, `mcp.verify_punch_item`) are not in `MCP_ACTIONS`.

## CLI verbs (`tl punch`)
All verbs take `--project` (the project ID; scope `project:<ID>`) and `--actor` (the signed-in person; default is the dev actor).

| Verb | Arguments and options | Prints on success |
|---|---|---|
| `raise` | `--subject` (required), `--description`, `--area`, `--system`, `--due YYYY-MM-DD`, `--category A\|B\|C`, `--assignee user:X`, `--from <KEY>` | `raised <key>  version <v>` |
| `edit` | `<key>`; at least one of `--subject`, `--description`, `--area`, `--system`, `--due`, `--category`, `--assignee`; `--expected-version N` | `edited <key>  version <v>` |
| `clear` | `<key>`; `--note` (required); `--expected-version N` | `cleared <key>  version <v>` |
| `verify` | `<key>`; `--expected-version N` | `verified <key>  version <v>` |
| `reopen` | `<key>`; `--reason` (required); `--expected-version N` | `reopened <key>  version <v>` |
| `void` | `<key>`; `--reason` (required); `--expected-version N` | `voided <key>  version <v>` |
| `ls` | `--state Open\|Cleared\|Verified\|Void`, `--area`, `--system`, `--assignee`, `--category`, `--from <KEY>`, `--overdue`, `--limit N` (default 200) | one line per item, then a count line |
| `show` | `<key>` | the item: fields, state, who cleared and verified, reopen history |

`--expected-version` defaults to the version read at the start of the command. An unknown key prints `error: no punch item <key>`.

## Module commands
Six commands in `tl_mod_quality.module.PUNCH_COMMANDS`. Each is run through the module command path with its access word.

| Command | Access word | Table word | Moves |
|---|---|---|---|
| `RaisePunchItem` | `quality.punch.raise` | user | new to Open |
| `EditPunchItem` | `quality.punch.edit` | user | Open to Open |
| `ClearPunchItem` | `quality.punch.clear` | user | Open to Cleared |
| `VerifyPunchItem` | `quality.punch.verify` | controller | Cleared to Verified |
| `ReopenPunchItem` | `quality.punch.reopen` | controller | Cleared or Verified to Open |
| `VoidPunchItem` | `quality.punch.void` | controller | Open or Cleared to Void (terminal) |

The read word is `quality.view` (table word `read`). Access words are in `schema/settings/access-words.yaml`; the table words are in
[access-words.md](access-words.md).

## Event types
`PunchItem.Raised`, `PunchItem.Edited`, `PunchItem.Cleared`, `PunchItem.Verified`, `PunchItem.Reopened`, `PunchItem.Voided`.
Each carries the record ID; the projector writes `cur_quality_punch_item`. Events are immutable; a correction is a new event.

## Keys and states
- Key: `<project>-PUN-nnnn` (numbering pattern `quality.PunchItem`, gap-free per project).
- States: `Open`, `Cleared`, `Verified`, `Void`. `Void` is terminal.
- Category: `A`, `B` or `C` (default `B`).
