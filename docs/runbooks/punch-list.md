# Runbook — punch list: raise, clear, verify, reopen, void, and what the refusals mean

Purpose: run the punch list day to day: raise an item, clear it, verify it at the terminal or in the TUI, reopen or void it, and
read what each refusal means. Module: [quality](../modules/quality/README.md). Brief: §9 M5.

## When to use
- A defect or open work is found on a project and must be tracked to closure.
- An item is cleared on site and must be checked by someone else.
- A cleared item is wrong and must go back to Open, or an item is no longer needed and must be voided.
- You need the punch list by state, area, system, person or due date.

## Before you start
- Sign in (`tl login <name>`). Commands take the ledger from `--db` or `TL_DB` and the project from `--project` (the reads take
  `--project` too).
- Words (`schema/settings/access-words.yaml`): reads need `quality.view`. Raise, edit and clear need the `user` table word. Verify,
  reopen and void need the `controller` table word, which the module superuser role grants. Who holds which word is an account
  decision; the demo gives `uma` a plain user and `rob` and `sue` the superuser role.
- Items are named by key, for example `P123-PUN-0001`. A void item keeps its key.

## Steps

### Raise an item
1. `uv run tl punch raise --project P123 --subject "Weld crack at spool W-12" --area A1 --system 47-01 --due 2026-12-01 --category A --assignee user:rob --from <IWP-NUMBER>`
   prints `raised P123-PUN-0001  version <v>`.
2. The options: `--subject` is required (up to 200 characters). `--description`, `--area`, `--system`, `--due` (`YYYY-MM-DD`),
   `--category` (`A`, `B` or `C`; default `B`), `--assignee` (`user:X`) and `--from` (the key of the record it was raised from) are optional.
   `--from` an IWP, a tag, a document or a letter links the item to it (`raised against` in `tl link list`). A `--from` that does not exist,
   or that you may not read, prints `error: no record <key>` and writes nothing.
3. A bad `--category` is a usage error (exit 2).

### Edit an item
1. `uv run tl punch edit P123-PUN-0001 --project P123 --due 2026-12-08` prints `edited P123-PUN-0001  version <v>`.
2. At least one field is needed (`name at least one field to change`, exit 2). Only the raiser, the assignee or a verifier may edit
   (see the refusal table). Edit works on an Open item only.
3. `--expected-version N` makes the edit fail if the item changed since you read it.

### Clear an item (the work is done)
1. `uv run tl punch clear P123-PUN-0001 --project P123 --note "Re-welded, NDT clean"` prints `cleared P123-PUN-0001  version <v>`.
2. `--note` is required. Clear works on an Open item only.

### Verify an item (someone else checks)
1. `uv run tl punch verify P123-PUN-0001 --project P123` prints `verified P123-PUN-0001  version <v>`. Verify works on a Cleared item only.
2. The person who cleared it cannot verify it, even with the controller word. Use another controller.
3. In the TUI: open the item from the punch list, press `v` (Verify) and answer the "Are you sure" question.

### Reopen an item
1. `uv run tl punch reopen P123-PUN-0002 --project P123 --reason "Wrong size"` returns a Cleared or Verified item to Open, prints
   `reopened P123-PUN-0002  version <v>`, and `tl punch show` then shows `reopened  1`.
2. `--reason` is required (exit 2 without it). The clear and verify columns are reset.

### Void an item
1. `uv run tl punch void P123-PUN-0003 --project P123 --reason "Duplicate of P123-PUN-0001"` prints `voided P123-PUN-0003  version <v>`.
2. Void works on an Open or Cleared item. `--reason` is required. Void is final: a later `clear`, `verify`, `reopen`, `edit` or `void`
   is refused with `a void punch item accepts no further change`.
3. The TUI does not offer void yet; use the terminal or the API.

### Read the list
1. `uv run tl punch ls --project P123` lists items by key, with a count line. Filters: `--state Open|Cleared|Verified|Void`, `--area`,
   `--system`, `--assignee user:X`, `--category A|B|C`, `--from <KEY>` (items raised from that record), `--overdue` (Open items past
   their due date), `--limit N` (default 200).
2. `uv run tl punch show P123-PUN-0001 --project P123` prints the item: state, who cleared and who verified, reopen history, source.
3. The API reads the same data: `GET /projects/{project}/punch`, `GET /projects/{project}/punch/{key}`, `GET /projects/{project}/punch-counts`.

### Clear, verify and reopen in the TUI
1. Start the TUI with `just tui` (project from `TL_PROJECT`, default `P123`), then open the command palette and choose `punch`.
2. The log lists items. Keys in the log: `s` cycles the state filter, `c` the category, `o` overdue only, `m` mine. Enter opens an item.
3. On an item: `c` clears (asks for a note), `v` verifies (asks "Are you sure"), `o` reopens (asks for a reason). Only the keys the
   state offers do anything. A refusal from the client shows `! <text>` on the status line.
4. The TUI does not raise, edit or void. Use `tl punch` or the API for those.

## Refusals and what they mean
Texts are copied from the code and from the T02 and T06 reports. The CLI prints `error: <text>`. The `<key>` is the key you typed.

| Text | Meaning | What to do |
|---|---|---|
| `forbidden` (`error: forbidden`) | Your account lacks the word for this command (for example a plain user verifying) | Ask a controller |
| `the person who cleared a punch item may not verify it` | You cleared this item | Another controller verifies it |
| `only the raiser, the assignee or a verifier may edit a punch item` | You are not a party to the item | Ask the raiser or the assignee |
| `no punch item <key>` | The key is unknown, in another project, or the item is hidden from you (the same text for all three) | Check the key with `tl punch ls`; if the item should be visible, check the access to its source record |
| `no record <key>` | The `--from` key is unknown or hidden from you; nothing was written | Check the key |
| `a punch item that is <State> does not take <Command>; it needs <states>` | The item is in the wrong state (for example `VerifyPunchItem` on an Open item; it needs Cleared) | Move it first (clear, reopen) |
| `a void punch item accepts no further change` | The item is Void (terminal) | Raise a new item |
| `the record changed since it was read` | `--expected-version` is older than the item; someone changed it | Run `tl punch show`, then retry with the new version |
| `name at least one field to change`, `--reason` or `--note` missing, bad `--category` or `--state` | A usage error in the command line (exit 2) | Fix the options |

## Numbering
- Keys are `<project>-PUN-nnnn`, one count per project, gap-free (`schema/fixtures/numbering/patterns.yaml`, the `quality.PunchItem`
  pattern). The next key follows the last one; no key is skipped or reused.
- Two raises at the same time get two different keys.

## What an agent may propose
- An agent (MCP) may call `propose_punch_item` with `subject` (required) and optionally `description`, `area`, `system`, `assignee`
  and `from_key`. Nothing is raised at once: the proposal is pending.
- A person who may raise punch items accepts it: `uv run tl proposal ls`, then `uv run tl proposal accept <id>`. The item is raised as
  that person (`raised by user:<name>`) and gets the next key. Reject a proposal with `tl proposal reject <id>`
  ([proposal review queue](proposal-review-queue.md)).
- No agent may clear, verify, edit, reopen or void. The MCP tools for those are not in the agent word list.

## The generator (demo data)
- `just demo-project dev/data/demo-project.db --sections core,engineering,awp,constraints,quality` prints
  `quality: <n> records, <m> events`. The section makes 29 items for project P200: Open, Cleared, Verified and Void, one reopened,
  overdue ones, items raised from IWPs and tags.
- Restricted sources come from the correspondence section (two existing letters are restricted through the correspondence command). Without that section the items
  are free-standing and the run prints one note line. `--sections core,quality` works, with free-standing items only.
- The generator runs the real punch commands, so the generated items follow the same rules as the terminal.

## Verify the demo
- `just demo P2-PUNCH` runs clauses 1 to 6 on SQLite and then on Postgres, and clause 7 on SQLite (`dev/demos/P2-PUNCH.sh`).
  Each clause prints `PASS clause N: ...` only after its check succeeds.
