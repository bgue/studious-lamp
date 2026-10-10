# Report — P0-I6 workstream A (activity feed and hashtags)

Plan and published contract: `docs/tickets/P0-I6/README-A.md`. Branch `p0/i6a`, worktree `/home/user/wt/p0-i6a`.

## Outcome
Objective met: yes. People and agents post to a project feed. `#` and `@` tokens become record, code, signal, topic and mention tags
and never change a record; a resolved record tag adds a suggested `references` link (post to record) in the same unit of work. Event
cards aggregate deterministically: a rebuild gives the same `cur_feed_items` as the live run. Feed queries exist by project, record
(with the one-hop toggle) and hashtag. `tl feed post|ls|retract|react` works. The TUI has a feed pane (`F`, sketch 6 keys) and a
composer (`p`) that completes `#` and `@`. `#hold` on a post that references a record shows a constraint suggestion stub; nothing is
created. Demo: `just demo P0-I6-A` runs clean. Demo path on a fresh clone: not tried (it uses a temporary ledger and the installed workspace).

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| P0-I6-T01 retract and react handlers | merged | 1 | pass, no findings |
| P0-I6-T02 feed list queries | merged | 1 | first run BLOCKED on T01 (see Deviations); pass after the integration merge |
| P0-I6-T03 suggestions and completion | merged | 1 | first run BLOCKED on T01 and T02; pass after the integration merge |
| P0-I6-T04 feed pane | merged | 1 | pass |
| P0-I6-T05 `tl feed` | merged | 1 | pass, no findings |
| P0-I6-T06 composer | merged | 1 | pass; `rich` declared in tl-tui (MIT) |
No ticket was taken over or abandoned. Supervisor pieces S1 to S8 are listed in README-A.

## Gates (on p0/i6a after the T05 merge)
| Gate | Result |
|---|---|
| `just check` (ruff, format, pyright, codegen drift, licence check) | clean |
| `just test` | 2763 passed |
| `just test-tui` | 374 passed, 24 snapshots |
| `just demo P0-I6-A` | "P0-I6-A demo ok" |
| Feed tests on sqlite and postgres (`--adapters sqlite,postgres`) | pass: post, projection, actions, queries, completion, property, webhook contract |
| Full `just test-parity` | not run by me; the feed service tests carry the `parity` marker through `new_db` |
| Fresh-context review of S2 to S4 (tags, cards, projector) | pass at 7213187; two rulings applied afterwards (see below) |

## Deviations from plan
- T02 and T03 went out in one batch with T01 although their provided tests call T01's (and T03's call T02's) code. Three tickets came back BLOCKED. They passed after the base was merged into the ticket branches. Learning L-P0-I6A-5.
- The link service now accepts a post as the `from` end of a link (A1), restricted to the relation `references` after review (A10); `links_of` lists such links. Two trunk tests were edited: `tests/webhooks/scenario.py` (the four `Feed.*` samples) and `tests/webhooks/test_outbox_projector.py` (`["feed", "outbox"]`). The command-palette snapshot and `test_keymap.py` changed for the two new commands and contexts.
- Reviewer rulings applied: no tags inside URLs or markdown code (A9), posts link only with `references` (A10).
- `Feed.Posted` carries the importance the author declared; the projection derives the effective level (high with a signal tag).

## Escalations and decisions
None open. Rulings received: A1 accepted, trunk test edits accepted, declared versus effective importance accepted, `UnknownRelationError` accepted for non-references post links.

## Accepted as is (reviewer)
The property test finds a mutated window edge only because its generated gaps are biased towards 600 s. `detect_keys` is quadratic in post length at the 10 000 character cap; a 100 000 character input of tags parses in under a second.

## Learnings
Appended: L-P0-I6A-1 (fresh worktree needs `uv sync --all-packages`), L-P0-I6A-2 (property test needs a pure oracle, a controlled clock, edge-biased gaps; check by mutation), L-P0-I6A-3 (plumbing events split "consecutive" aggregations; unique index on a nullable column states "one open X per scope"), L-P0-I6A-4 (split a stub module so tickets do not share a path; hand-written stubs), L-P0-I6A-5 (batch only independent tickets). Implementer proposals declined: none.

## Docs
`packages/tl-core/README.md` and `AGENTS.md`, `packages/tl-cli/README.md` and `AGENTS.md`, `packages/tl-tui/README.md` and `AGENTS.md`, `packages/tl-schema/README.md`, `docs/tickets/P0-I6/README-A.md`, ticket reports under `docs/reports/P0-I6/`. No runbook: the feed adds no operational command or alert. Generated docs untouched by hand.

## Schema and dependency approvals
`schema/core/feed.yaml` (P0-I6-S1, with the `Feed*Payload` catalog classes added at the P0-I5 merge). One dependency declared: `rich` in tl-tui (MIT, already installed as textual's dependency).

## Follow-ups
- Feed API routes (list, post, react, retract, complete) and the remote client's feed methods: the `ClientInterface` gained six methods that the remote client must implement. Scheduled with the P0-I4 integration.
- `#hold` suggestion acceptance (the review queue, WS-B).
- Feed performance at 100k records: the projector runs for every event (about three statements); measure in the I8 pass.
- Follow, thread and saved-query feeds, mutes and digests (brief 21.3) are not built.

## Cost notes
Six implementer tickets, one retry-free pass each; three needed an integration merge. Supervisor pieces S1 to S8 are about 2 800 lines of source and tests.
