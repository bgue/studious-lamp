# P2-TWIN: twin-world confidentiality walk

Design: `docs/reports/OUTSIDE-REVIEW-2026-11-09.md` section 1. No product code changed.
## Deviations
- `confseed.seed_hidden_world` gained an optional `twin` hook (`Twin.mark(kind)` before each step; off by default,
  A unchanged); the RFI/commercial steps were split into small functions to host the marks.
- One extra step in the walker's own script (not the seed): a constraint on the open item with a hidden target.
## What it does
`tests/confidentiality/test_twin_walk.py`, `twin_world.py` (worlds), `twin_channels.py` (channels, compare).
- A is the seed as is. B skips every step that writes a kind the reader may not read, and what points at it (links,
  posts, proposals, clocks, files, the constraint target). Before each step B pads to A's `seq` with filler events
  (`Account.TwinFiller` on a `core.Account` stream, which readers skip) and burns ids to A's counter.
- Clock fixed, ids a counter. The A->B table is the identity but for ids B took after one file A deduplicated (call-site
  trace) and numbers, which follow their place in the counter (A's secret keys are asked of B as an unused key of the
  same shape; the answer is mapped back).
- Four world pairs (secret sets: bob+bot, ctl, boss, amy), SQLite always, Postgres under `--adapters`. Per reader:
  ~1070 API GETs (every OpenAPI GET route, the old walk's combinations, `MIN_ROUTES` guard), ~530 MCP read-tool calls,
  1 SSE catch-up, 4 `lake_query`, ~85 CLI reads (no bot: no CLI session), webhooks per mode. About 8.3k call pairs.
- Byte for byte: status, headers minus date/request id/content-length, body with JSON keys in order. A failure names
  channel, route and reader and shows the first differing bytes. A more than 2x B (and >0.1 s) is a warning only.
## Masks (explicit, `MASKS`)
- hash chain: `prev_hash`/`hash` cover every event of a scope, hidden ones too; no content.
- numbering counter: stream version and `sequence` of a numbering stream. A number follows its place in the counter,
  so a gap in numbers shows that something was numbered. **Not on the owner's list: needs a ruling.**
- filler events: dropped from the event list an admin reads (admins read account streams).
Known limit kept as a test: key oracle on create, 409 vs 200 (`test_the_key_oracle_on_create_is_the_known_limit`).
## Leaks found (`test_known_leak[...]`, strict xfail, one probe each; the walk explains them in `LEAKS`)
1. dedup-flag: `File.Attached.deduplicated=true` on a visible document when a hidden file has the same bytes
   (events, history, webhooks delta/full, lake). bob, bot, amy.
2. transmittal-line: a transmittal listing a hidden revision shows `position 2` with no 1, and its `Transmittal.Defined`
   event is withheld (history, activity, /events, CLI tail, webhook thin). bob, bot, amy.
3. feed-card-group: the feed folds events into one card and drops the whole card when one event is hidden, so a
   visible link's card is missing. amy, bob, bot.
4. link-total: `link_total` of `/links/search` counts links to hidden records. **Aggregate: the owner to say whether it
   is an accepted figure; not allow-listed.** bob, bot, amy.
Another difference in the same response as a known leak stays masked until that leak is fixed.
## Sentinel
`PAYLOAD_REFS` emptied in `tl_core/intent.py`: the amy walk fails with 4 differences (`/events?record_id=<constraint>`,
`/records/<id>/activity`, `/history`: `target_id` shows the hidden record where B has null). Restored.
## Not covered
- `Constraint.Cleared.resolved_by` (its link lands between visible events, where a filler cannot stand); no requisition
  or IWP in the seed; GET routes only, plus the key-oracle POST. Timing flags are noisy (A first, CLI warm-up).
## Gates
- `NODE_OPTIONS=--max-old-space-size=6144 just check`: pass.
- `just gate tests/confidentiality/test_twin_walk.py`: exit 0, 5 passed, 4 xfailed (547 s).
- `just gate-pg tests/confidentiality/test_twin_walk.py`: exit 0, 10 passed, 8 xfailed (3684 s).
- `just gate tests/confidentiality packages/tl-modules/correspondence/tests`: exit 0, 975 passed, 4 xfailed (787 s).
