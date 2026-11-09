# P2-TWIN: twin-world confidentiality walk

Rule under test: a record a viewer may not read is indistinguishable from one that never existed, through every channel.
Design: `docs/reports/OUTSIDE-REVIEW-2026-11-09.md` section 1. No product code changed.

## Deviations
- `confseed.seed_hidden_world` gained an optional `twin` hook (a `Twin.mark(kind)` call before each step, default
  off, A unchanged) and the RFI/commercial steps were split into small functions to host the marks.
- Plus one new constraint step in the walker's own script (not the seed): see "Not covered".

## What it does
`tests/confidentiality/test_twin_walk.py` + `twin_world.py` (worlds) + `twin_channels.py` (channels, compare).
- World A is the seed as is. World B skips every step that writes a kind the reader may not read (and what points at
  it: links, posts, proposals, clocks, files, the constraint target). Before each step B pads to A's `seq` with filler
  events (`Account.TwinFiller` on a `core.Account` stream, which readers skip) and burns ids to A's counter.
- Clock fixed, ids a counter, so a record in both worlds is the same record. The A->B table is the identity but for
  (a) ids B took after one file A deduplicated (found by call-site trace), (b) numbers, which follow their place in
  the counter (A secret keys are asked of B as an unused key of the same shape, the answer is mapped back).
- Four world pairs (secret sets: bob+bot, ctl, boss, amy), every reader of the API walk, SQLite always, Postgres under
  `--adapters`. Per pair of worlds and reader: ~1070 API GETs (every OpenAPI GET route, the existing walk's
  combinations, `MIN_ROUTES` guard), ~530 MCP read-tool calls, 1 SSE catch-up, 4 `lake_query` after a sync, ~85 CLI
  reads (events tail, record/corr show, link list, thread show, evidence, file ls, ls verbs; no bot: agents have no
  CLI session), webhooks per mode (thin, delta, full) from a fake sink. About 8.3k call pairs on SQLite.
- Compared byte for byte (status, headers minus date/request id/content-length, body). A failure names channel,
  route, reader and shows the first differing bytes. Wall time per call: A more than 2x B (and >0.1 s) is a warning.

## Masks (explicit, in `MASKS`)
- hash chain: `prev_hash`/`hash` cover every event of a scope, hidden ones too; no content.
- numbering counter: stream version and `sequence` of a numbering stream. A number follows its place in the counter,
  so a gap in numbers shows that something was numbered. **New: not on the owner's list; needs a ruling.**
- filler events: dropped from the event list an admin reads (admins read account streams).
Known and kept as a test: key oracle on create (409 vs 200), `test_the_key_oracle_on_create_is_the_known_limit`.

## Leaks found (strict xfail, `test_known_leak[...]`, one probe each; the walk explains them in `LEAKS`)
1. dedup-flag: `File.Attached.deduplicated=true` on a visible document when a hidden file has the same bytes
   (events, history, webhooks delta/full, lake). Readers: bob, bot, amy.
2. transmittal-line: a transmittal listing a hidden revision shows `position 2` with no 1, and its
   `Transmittal.Defined` event is withheld (history, activity, /events, CLI tail, webhook thin). bob, bot, amy.
3. feed-card-group: the feed folds events into one card and drops the whole card with a hidden member, so a visible
   link's card is missing. amy, bob, bot.
4. link-total: `link_total` of `/links/search` counts links to hidden records. **Aggregate: owner to say whether it is
   an accepted figure; not allow-listed.** bob, bot, amy.
While a known leak is in a response, any other difference in that same response is masked until it is fixed.

## Gates
- `NODE_OPTIONS=--max-old-space-size=6144 just check`: pass.
- `just gate tests/confidentiality/test_twin_walk.py`: part 1 exit 0, 5 passed, 4 xfailed in 547 s.
- `just gate-pg ...` and `just gate tests/confidentiality packages/tl-modules/correspondence/tests`: see summary below.

## Sentinel
`PAYLOAD_REFS` emptied in `tl_core/intent.py`: the amy walk fails, 4 differences (`/events?record_id=<constraint>`,
`/records/<id>/activity` and `/history`: `target_id` shows the hidden record where B has null). Restored.

## Not covered
- `Constraint.Cleared.resolved_by`: the clear's link to the hidden record lands between visible events, where a
  filler cannot stand; only `Constraint.Raised` target is walked. No requisition, intent or IWP in the seed.
- Only GET routes; POST probes: the key oracle only.
- Timing flags are warnings and noisy (A is walked first, CLI warm-up); none was confirmed as a channel.
