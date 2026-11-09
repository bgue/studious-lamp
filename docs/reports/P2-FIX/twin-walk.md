# P2-TWIN: twin-world confidentiality walk
Design: `docs/reports/OUTSIDE-REVIEW-2026-11-09.md` section 1. No product code changed.
## Deviations
- `confseed.seed_hidden_world` gained an optional `twin` hook (`Twin.mark(kind)` before each step; off by default,
  A unchanged); the RFI/commercial steps were split into small functions to host the marks.
- One extra step in the walker's own script: a constraint on the open item with a hidden target.
## What it does
`tests/confidentiality/test_twin_walk.py`, `twin_world.py` (worlds), `twin_channels.py` (channels, compare).
- A is the seed as is. B skips every step that writes a kind the reader may not read, and what points at it (links,
  posts, proposals, clocks, files, the constraint target). Before each step B pads to A's `seq` with filler events
  (`Account.TwinFiller` on a `core.Account` stream, which readers skip) and burns ids to A's counter.
- Clock fixed, ids a counter; the A->B table maps ids B took after a deduplicated file, and numbers (asked of B as an unused key).
- Four world pairs (secret sets: bob+bot, ctl, boss, amy), SQLite always, Postgres under `--adapters`. Per reader:
  ~1070 API GETs (every OpenAPI GET route, the old walk's combinations, `MIN_ROUTES` guard), ~530 MCP read-tool calls,
  1 SSE catch-up, 4 `lake_query`, ~85 CLI reads (no bot), webhooks per mode.
- Byte for byte: status, headers minus date/request id/content-length, body with JSON keys in order. A failure names
  channel, route and reader and shows the first differing bytes. A more than 2x B (and >0.1 s) is a warning only.
## Masks (explicit, `MASKS`; each says what it masks)
- hash chain: `prev_hash`/`hash` (by key; in the lake by column, so a file's content hash is compared).
- numbering counter: `stream_version` of a `numbering:` stream (and `numbering:.. vN` text) and `payload.sequence`
  of `Numbering.Allocated` only (flat object with pattern/key/prefix/record_type). Owner ruling 2026-11-09: numbering
  gaps are a known limit.
- redacted row scope: the `scope` column of an `Internal.Redacted` lake row only. On Postgres one account event sits a
  seq later in A than in B (A's hidden event precedes it in the step), so the placeholder there differs in scope. Harness
  order, not content; the old broad lake mask hid it. Follow-up: pad inside the step.
- filler events: dropped from the event list an admin reads (admins read account streams).
Known limit kept as a test: key oracle on create, 409 vs 200 (`test_the_key_oracle_on_create_is_the_known_limit`).
## Leaks (`test_known_leak[...]`, strict xfail, one probe each)
Each leak applies only on the (channel, route) pairs it names (`mask_where` / `where`, never empty). A mask changes
one field. An extra unit (event, card, row) is cut out of B alone, the rest of the call must be A byte for byte.
1. dedup-flag: `File.Attached.deduplicated` (api /events, lake events, webhooks delta/full).
2. transmittal-line: `position` (transmittal GET, `get_transmittal`) and the withheld `Transmittal.Defined` unit
   (/events, activity, history, CLI tail, lake events as a redacted row, webhooks). Lake: A shows the placeholder row.
3. feed-card-group: the missing card (API /feed, CLI feed). Knock-on on a 50-card page: A shows up to as many older
   cards at the end, `next_before` and a label only one side names may differ; nothing else.
4. link-total: `link_total` of `/links/search` counts hidden links. Owner ruling: it must count only visible links
   (strict xfail until the product fix lands).
5. NEW webhook-target: delta/full webhook of a constraint with an unreadable target carries `target_id` and
   `target_kind` (A: id and "record"; B: null); API and events show null. Found once the old broad mask went (it was
   hidden by the Transmittal.Defined allowance). bob, bot, amy. Needs a product fix.
Unit tests (no worlds) pin the narrowness: other route, other channel, another difference on the same call, a
`sequence` outside Numbering.Allocated, a content hash.
## Sentinel
`PAYLOAD_REFS` lookup emptied in `tl_core/intent.py`: the amy walk fails with 6 differences. Restored.
## Timing
The SQLite 2x-and-0.1 s bound is a warning, not enforced (CLI warm-up and A-first order make it noisy).
## Not covered
`Constraint.Cleared.resolved_by`; requisition and IWP; POST routes but the key oracle.
## Gates
- `NODE_OPTIONS=--max-old-space-size=6144 just check`: pass.
- `just gate tests/confidentiality/test_twin_walk.py`: exit 0, 9 passed, 5 xfailed (548 s).
- `just gate-pg tests/confidentiality/test_twin_walk.py`: exit 0, 14 passed, 10 xfailed (4552 s; includes the SQLite cases).
