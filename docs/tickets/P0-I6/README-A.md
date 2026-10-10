# Increment plan: P0-I6 workstream A, activity feed and hashtags

Status: done
Supervisor session: 2026-10-09
Brief sections: §21.1 to §21.4, §19.2, §19.3, §30 (`feed.*`)
Branch: `p0/i6a` (worktree `/home/user/wt/p0-i6a`), fanout plan `docs/tickets/P0-I6/FANOUT.md`

## Objective
People and agents post to a project feed. Hashtags resolve to records, codes, signal tags, topics and mentions and never change a
record. Ledger activity shows as event cards that aggregate the same way on a rebuild as in the live run. The feed has queries by
project, record (with a one-hop toggle) and hashtag, a CLI (`tl feed`), and a TUI pane with a composer that completes `#` and `@`.

## Published for workstreams B and C: the post service
```python
# tl_core.services.feed
class PostToFeed(Command):          # Command: actor, source, scope, correlation_id, causation_id, idempotency_key
    body: str                       # 1..10_000 characters, not blank
    importance: Importance = "normal"   # "low" | "normal" | "high"; a signal tag raises the effective level to high
    post_id: str | None = None      # None: a new ULID

def handle_post(uow: UnitOfWork, cmd: PostToFeed) -> CommandResult: ...
#   scope must be "project:<id>" (InvalidScopeError otherwise). CommandResult.stream_id = the post id, version 1,
#   events = [Feed.Posted, Link.Suggested*]: one suggested `references` link (post -> record, source key_detected,
#   causation = the posted event) per resolved record tag, in the same unit of work. Agents post with actor "agent:<id>"
#   and source "mcp:<agent>" (WS-B) or "sim:<run>" (WS-C); the feed shows the agent label from the actor.

class EditPost(Command):  post_id: str; body: str; expected_version: int | None = None
def handle_edit_post(uow, cmd) -> CommandResult                       # Feed.Edited (+ Link.Suggested for newly tagged records)
# tl_core.services.feed_actions
class RetractPost(Command): post_id: str; reason: str; expected_version: int | None = None
class ReactToPost(Command): post_id: str; reaction: "ack" | "+1" | "resolved"; on: bool = True; expected_version: int | None = None
def handle_retract_post(uow, cmd) -> CommandResult                    # Feed.Retracted, leaves a tombstone
def handle_react_to_post(uow, cmd) -> CommandResult                   # Feed.Reacted; NoChangesError if nothing changes
# tl_core.services.feed_queries (read, in the caller's unit of work)
def list_feed(uow, scope, *, record_id=None, include_linked=False, tag=None, item_type=None, limit=50, before_seq=None) -> FeedPage
def get_post(uow, scope, post_id) -> FeedItem
# tl_core.services.feed_completion
def feed_suggestions(uow, items) -> dict[str, list[FeedSuggestion]]   # the `#hold` stub
def complete_tags(uow, scope, sigil, prefix, *, limit=8) -> list[Completion]
```
`Feed.Posted` payload: `post_id, body, author, importance (what the author declared), tags [ParsedTag as dict], record_ids`. The
projection derives the effective importance (high when a tag is a signal tag). Edited: `post_id, body, tags, record_ids`. Retracted:
`post_id, reason`. Reacted: `post_id, reaction, on`. Each has a catalog class in `schema/core/feed.yaml`
(`FeedPostedPayload` and three more). The API routes for the feed are not in this workstream: whoever writes them calls the functions above.

## Decisions
| # | Decision |
|---|---|
| A1 | A post is not a record, so the link service now accepts a post as the `from` end of a link (`services/links._record(..., allow_post=True)`), and `link_queries.links_of` lists such links with `other_type = core.ActivityPost`, no key, and the body start as title. `references` from a post to a record is the only use. Reviewed with D2. |
| A2 | Unresolved record-like tags stay topics (FANOUT D2). Only `#`-prefixed keys are record tags; a bare key in the body is a composer chip (§7.2). |
| A3 | Card rules (`tl_core/feed/cards.py`): per scope one open card; same actor and event type within `CARD_WINDOW_SECONDS` of the first event extends it; any other event closes it and starts one. `Feed.*` events close the open card and never become cards. `Numbering.Allocated`, `Link.Suggested` and `Webhook.*` are transparent (neither card nor closer), because numbering writes an event before every `Record.Created` and a tagged post writes a suggestion after `Feed.Posted`; both would split every burst. |
| A4 | The projector sets `handles_all` and is registered before the outbox. It reads only its own tables, so `rebuild --only feed` equals a full rebuild. Time is kept as integer microseconds (`first_us`) so the window test does not depend on how a dialect returns timestamps. |
| A5 | `#hold` suggestions are derived from the post's tags at read time (`feed_suggestions`), never stored. Accepting is a notice in Phase 0; the review queue is WS-B. |
| A6 | Reactions are one JSON object on the post row (`{reaction: [actors]}`), idempotent per actor. The pane toggles by sending `on=True` and, on `NoChangesError`, `on=False`. |
| A7 | Retraction drops the body and the non-record tags (the post leaves hashtag feeds) and keeps the record tags (the tombstone stays in the record's feed). A retracted post's suggested links stay: only a person retracts a link. |
| A8 | Authorisation is not enforced (ADR-0005): anyone may edit or retract a post. |
| A9 | Reviewer ruling: a sigil inside markdown code (inline span or fenced block) or after a `/` in its word (`http://x/#frag`) is not a tag. |
| A10 | Reviewer ruling: a post is the `from` end of a link only for the relation `references`; any other relation (or none) raises `UnknownRelationError`. |

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 | `schema/core/feed.yaml`, generated output | schema (delegated approval) | orchestrator | done |
| S2 | Hashtag parser `feed/tags.py`, resolution precedence | named supervisor-tier piece | pending | done |
| S3 | Card aggregation rules `feed/cards.py` | named supervisor-tier piece | pending | done |
| S4 | `FeedProjector` and the rebuild-equals-live property test | named supervisor-tier piece | pending | done |
| S5 | `handle_post`, `handle_edit_post`, link service change for post ends | composition of handlers | pending | done |
| S6 | `ClientInterface` feed methods, embedded client, `FakeClient` feed mixin | interface | | done |
| S7 | Stubs and provided tests for T01 to T04 | scaffolds | | done |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| P0-I6-T01 | Retract and react handlers | haiku | S5 | merged | pass, no findings |
| P0-I6-T02 | Feed list queries (`list_feed`, `get_post`) | haiku | S4 | merged | pass, no findings |
| P0-I6-T03 | `#hold` suggestions and composer completion | haiku | S4 | merged | pass, no findings |
| P0-I6-T04 | Feed pane widget | haiku | S6 | merged | pass |
| P0-I6-T05 | `tl feed post\|ls\|retract\|react` | haiku | T01, T02 | merged | pass, no findings |
| P0-I6-T06 | Composer with `#` and `@` completion | haiku | S6 | merged | pass |
| S8 | App `F`/`p` keys, main-area feed view, keymap, palette, embedded-client tests | TUI wiring | T04, T06 | done | |

## Order of work
1. Round 1 (done): S1 to S7, tickets T01 to T04, DISPATCH batch 1 (T01 to T04).
2. Round 2: merge batch 1; write T05 and T06 with stubs and provided tests; DISPATCH batch 2; start S8.
3. Round 3: merge batch 2; S8; demo `dev/demos/P0-I6-A.sh`; docs; gates; report.

## Risks and escalation triggers
- Card aggregation that depends on processing order breaks rebuild determinism: the property test compares rebuild with live and with an independent reading of the rules, and fails when the window edge is mutated.
- The projector runs for every event of the system (about three statements per event). Measure in the I8 performance pass.
- The catalog test lists `Proposal.*` event types named in `proposals/types.py` (the frozen WS-B contract). WS-B adds their catalog classes with `proposals.yaml`; until then `packages/tl-schema/tests/test_catalog.py::test_every_event_type_the_code_names_is_in_the_catalog` fails on every branch that has `proposals/types.py`.

## Accepted as is (reviewer)
- The property test is sensitive to the window edge only because the generated gaps are biased towards 600 s; a uniform generator did not find a mutated edge in 40 examples.
- `detect_keys` is quadratic in the length of a post at the 10 000 character cap (one regex pass per numbering pattern, overlap check against kept matches). A 100 000 character input of tags parses in under a second; posts are capped, so no change.

## Blocked / Decision
(none)
