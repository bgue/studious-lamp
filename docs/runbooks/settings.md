# Runbook — settings (about:config): read, change, lock, schedule, undo, move between projects

Purpose: look at the platform's settings, change one at the company, project or user layer with the right reason and risk, lock or bound it for projects, undo a change, and carry a configuration from one project to another. Brief: §30. Plan and decisions: `docs/tickets/P0-I8/README-A.md`.

A setting has a platform default and may be set at the company, then the project, then the user (UI keys only). The most specific layer wins unless the company locked the key. `●` marks a value set at the layer you are looking at. Every change is a `Setting.Changed` event with the old value, the new value, who, why and when, so the history is complete and a change can be undone. Changes apply live, except where the key's `effect` says it needs a `restart`, `rebuild` or `reindex` (see step 8).

## When to use
- Trigger: someone asks for a different value (how often the lake syncs, whether the feed allows reactions, the signal tags, how long a webhook is retried, the agents' daily proposal budget).
- Trigger: a project must not override a key, or may only use a range of values.
- Trigger: "who changed this, and from what?" or "undo that".
- Trigger: a second project should get the same configuration as the first.
- Trigger: an AI agent proposed a setting change and a person must decide (step 7).

## Before you start
- Access needed: the repository, `uv`, the dev ledger (`TL_DB`). To use the API: a token for a person (`uv run tl dev token add user:alice`). Agents never set a value: an `agent:` token gets 403 `agent_must_propose` and `tl config` refuses `--actor agent:...`; an agent proposes through MCP (`propose_setting_change`) and a person accepts.
- Which person may change or lock which key is the permission model, a human gate (ADR-0005): today any person may.
- Safe to run during business hours: yes for live keys. A key with `effect` other than `live` is not fully in force until the effect is carried out (step 8).
- Keys are in `schema/settings/platform.yaml`; extension packages add their own, named after their package. Secrets are not settings: a `secret` key is refused until there is a vault.

## Steps
1. **List and read.** The list is what a project sees; add `--user` for UI keys:
   ```
   uv run tl config ls --project P123
   uv run tl config ls --project P123 --prefix feed. --modified
   uv run tl config get feed.signal_tags --project P123 --long
   ```
   Expected: one line per key (`key  value  type  origin  locked`), `origin` is `default`, `company`, `project` or `user`, with ` ●` when the value is set at the layer shown. `--long` adds the description, default, risk, effect, bounds, scheduled changes and `pending <effect>`.
2. **Change a value.** Give exactly one layer. An `advanced` key needs `--reason`; a `dangerous` key needs `--reason` and `--accept-risk`; both are refused without them, and nothing is written:
   ```
   uv run tl config set feed.reactions.enabled false --project P123
   uv run tl config set lake.sync.interval 10m --company --reason "less load on the ledger"
   uv run tl config set webhooks.egress.allowlist hub.example.com --company --reason "partner hub" --accept-risk
   ```
   Expected: `set <key> <layer> <value>`, or `unchanged ...` when the value is already that. Lists are `a,b,c` or JSON. A value out of range, of the wrong type, or past a company bound is refused with the reason. An allow-list entry that covers too much (a range wider than /8 or /16, a link-local or metadata address, a 6to4, Teredo or NAT64 range) is refused even with the risk accepted.
3. **Schedule a change.** `--at` takes an ISO time with `Z` or an offset, in the future:
   ```
   uv run tl config set ai.agents.daily_proposals 200 --company --reason "pilot ends" --at 2026-11-01T08:00:00Z
   ```
   Expected: `scheduled <key> <layer> <value> at <time>`. `tl config get --long` lists it under `scheduled`; the value in force does not change until then. Cancel it before its time with `tl config revert` (step 5): it is the latest change at that layer.
4. **Lock a key, or bound it.** Company only, always with a reason; only keys marked lockable:
   ```
   uv run tl config lock feed.reactions.enabled --reason "policy"
   uv run tl config lock project.mode --choices live --reason "no sandboxes"   # bounds for the project values
   uv run tl config lock feed.reactions.enabled --unlock --reason "policy changed"
   ```
   Expected: `locked <key>` (with `bounds {...}`). A project value set earlier stays in the history but no longer applies; setting a locked key at a project is refused (409 `setting_locked`), a value outside the bounds is refused (`setting_out_of_bounds`).
5. **History and undo.**
   ```
   uv run tl config history feed.signal_tags --layer project:P123
   uv run tl config revert feed.signal_tags --layer project:P123 --seq 4
   ```
   Expected: one line per change (number, layer, time, actor, old and new value, reason). `revert` undoes only the **latest** change at that layer (409 `setting_revert_not_latest` otherwise, so an old change is never replayed over newer ones). To go further back, `revert` again, or set the value you want. Undoing an advanced or dangerous change needs the reason and the risk like any change.
6. **Compare, export, import.** A file is a template or a review copy; an import is all or nothing:
   ```
   uv run tl config diff default company
   uv run tl config export --project P123 --out p123.yaml
   uv run tl config import p123.yaml --project P124 --reason "same as P123"
   ```
   Expected: `diff` lists the keys whose effective value differs; `import` prints `imported N keys into <layer>`. The file may not contain anchors, aliases, dates or other non-JSON values, or more than 1000 keys or 256 KiB; a bad entry changes nothing. A dangerous key in the file needs `--accept-risk`.
7. **Decide what an agent proposed.** The proposal shows the key, the layer, the old and new value and the key's risk and effect:
   ```
   uv run tl proposal show <id>
   uv run tl proposal accept <id> --actor user:alice
   uv run tl proposal accept <id> --actor user:alice --accept-risk    # a dangerous key
   ```
   Expected: accepting a dangerous key without `--accept-risk` is refused (`risk_not_accepted`) and the proposal stays pending. The agent's proposal never carries the acceptance; you give it.
8. **Carry out a pending effect.** `tl config get --long` shows `pending restart`, `pending rebuild` or `pending reindex` while a change is not fully in force:
   - `restart`: restart the server (`tl serve`); the start marks it done.
   - `rebuild` or `reindex`: `uv run tl projections rebuild` (all projectors; a rebuild of some projectors carries out nothing).
   The setting's own events are unaffected by a rebuild.
9. **In the TUI and over HTTP.** `F9` (or `about:config` in the command palette) opens the list: `e` edit, `r` reset, `h` history with `u` to undo, `k` lock, `L` send changes to the company instead of the project, `m` modified only, `/` filter. Over HTTP: `GET /settings`, `PUT /settings/{key}`, `POST /settings/{key}/reset|lock|revert`, `GET /settings/{key}/history`, `GET /settings/diff`, `GET /settings/export`, `POST /settings/import`.

## Verify
- `uv run tl config get <key> --project P123 --long` shows the new value, its origin, and no `pending` line once the effect is carried out.
- `uv run tl config history <key>` shows your change with your actor and reason; the change is a `Setting.Changed` event (`uv run tl events tail --project P123` shows a project change).
- A running worker or watcher picks the change up on its own: `tl lake sync --watch` reads `lake.sync.interval` again before every wait, the webhook worker reads the egress allow-list and the retry window every few seconds, the feed reads its two keys in each call.

## Roll back
- Undo the latest change with `revert` (step 5), or set the previous value; a scheduled change is cancelled by reverting it.
- Remove a project's own value with `uv run tl config reset <key> --project P123` (it inherits again); lift a lock with `lock --unlock`.
- A bad import is rolled back by importing the file that `export` wrote before it, or by `revert` key by key.

## Related
- `docs/runbooks/proposal-review-queue.md` (accepting a proposal), `docs/runbooks/lake-sync.md` (`--watch`), `docs/runbooks/webhook-operations.md` (the egress allow-list and retry window), `docs/runbooks/rebuild-projections.md` (effects), `docs/runbooks/tui-dev.md`.
- `docs/tickets/P0-I8/README-A.md`: the decisions A1 to A20 (layers, schedules, locks, the propose-only rule, import hygiene).
- Deviations from the brief: no `schema.conformance.mode` setting yet; `ai.agents.default_mode` is stored, shown and lockable but nothing reads it.
