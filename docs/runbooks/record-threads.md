# Runbook — record threads and dispatch

Purpose: switch record threads on, let people dispatch from them, and find out why a slash command was refused. Brief: §21.5; ADR-0018.

## When to use
- Trigger: a team asks for threads on a record type, a dispatch is refused, or a reminder did not arrive.

## Before you start
- Access needed: admin (settings); any person with an account can read and post.
- Safe to run during business hours: yes. Switching threads off keeps the messages.

## Steps
1. Switch threads on for a record type (company layer shown; project layer works the same).
   ```
   uv run tl config set threads.enabled true --company --reason "pilot"
   uv run tl config set threads.enabled_types core.Record --company --reason "pilot"
   ```
   Expected: `uv run tl thread show --project P123 <key>` says `threads on`. An empty type list means no record type has a thread.
2. Choose who may dispatch: `threads.dispatch.roles` (empty means any signed-in person) and `threads.dispatch.enabled`.
   Each command a dispatch runs still needs its own access; a dispatch never runs more than the person could by hand.
3. Decide what agents may do: `threads.agents.can_dispatch` is `propose` (an agent files a proposal that a person previews and accepts) or `none`. It is an `advanced` key, so changing it needs `--reason`.
4. Make sure each person who dispatches has an account (`uv run tl admin user add`). The command runner reads what a person holds from the account; no account, no access (a preview then shows the command as not permitted).
5. Try a command.
   ```
   uv run tl thread preview --project P123 <key> '/link #<other key> as requires'
   uv run tl thread dispatch --project P123 <key> '/link #<other key> as requires' --token <token>
   ```
   Expected: the preview lists each command with the access it needs and `can dispatch: yes`; the dispatch prints `dispatched <message id>`.

## Verify
- `uv run tl thread show` lists the message with its outcome line. `Thread.Dispatched` is in `uv run tl events`.
- A refusal code in the preview: `not_permitted` (the person lacks the access), `command_refused` (the dry run failed; the message says why), `dispatch_unavailable` (the verb has no target for this record yet: `/assign`, `/due`, `/hold`, `/release`, `/raise rfi`), `reserved_field` (a command names a field only the server sets).
- A confirm answering `dispatch_stale` means the record or the plan changed after the preview: preview again.
- Reminders: `/remind` queues a `thread.reminder` job; `uv run tl thread reminders` runs the due ones and posts them.

## Roll back
- Switch `threads.enabled` off. Nothing is deleted; posting and dispatching stop, reading stays.
- A wrong dispatch is undone by the ordinary commands of what it did; the thread keeps the message and its `dispatched_from` links as the record of why.

## Related
- `docs/adr/0018-record-threads-and-dispatch.md`, `docs/runbooks/settings.md` (`uv run tl config`), `docs/runbooks/accounts-and-access.md`, `docs/runbooks/proposal-review-queue.md`.
