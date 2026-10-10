# Fanout plan: P0-I6 (feed core and hashtags, MCP write tools, simulator v0)

Status: active (WS-A may start now; WS-B and WS-C start after P0-I4 and P0-I5 merge into the trunk)
Orchestrator session: 2026-10-09
Brief sections: §21.1–§21.4, §19.2–§19.3, §11.3, §18.12, §29.5, §30 (`feed.*` defaults); build spec 05 §Increment 6

## Objective
People and agents post to a project feed. Hashtags resolve to records, codes, signals, topics and mentions, and never
mutate records. Ledger activity shows as aggregated event cards. MCP agents can propose record changes that a human
accepts from a review queue. A deterministic simulator drives a small project through the public API and MCP, so the
demo shows simulated crew posts and records arriving live.

## Exit criteria
- [ ] Feed events `Feed.Posted|Edited|Retracted|Reacted` and the `cur_feed_items` and `cur_feed_tags` projections, with tombstones on retraction.
- [ ] Hashtag parser for record, code, signal, topic and mention tags, using the P0-I3 numbering patterns. A record tag creates a *suggested* `references` link through the existing link service.
- [ ] Event cards aggregate deterministically on rebuild, using `CARD_WINDOW_SECONDS` in `tl_core/feed/types.py`.
- [ ] Feed queries: project, record (with a one-hop linked-records toggle), and hashtag. A TUI feed pane follows sketch 6 (§21.4 keys `j/k`, `Enter`, `p`, `.`, `o`), and the composer autocompletes on `#` and `@`.
- [ ] `#hold` on a post that references a record yields a *proposal* stub ("create a constraint?"). It never makes a direct change.
- [ ] MCP tools `create_record`, `update_psets`, `link_records` and `transition_workflow` are propose-only, using `tl_core/proposals/types.py`. `post_feed` is a direct write labelled as an agent (§21.3). Calls are tagged `source=mcp:<agent>`. Each agent has a daily proposal budget. The review queue is reachable from the CLI (`tl proposal ls|accept|reject`) and the API.
- [ ] Simulator v0 lives in the new `tl-sim` package (03 §1). It has the orchestrator loop (`sim_create/advance/inject/status/assert`), a deterministic actor base, and three actors: document controller, planner and crew, all on generic records. It also has a scenario loader, a seed template, `just seed`, and a ground-truth log with `sim_assert` over the `cur_` tables. It acts only through the REST API and MCP.
- [ ] Demo `just demo P0-I6`: a seeded simulation advances one day. Crew posts and records appear in a remote TUI feed and the API. An agent proposal is accepted from the CLI.

## Workstreams

| WS | Name | Branch, worktree | Base | Provides | Consumes |
|---|---|---|---|---|---|
| A | Feed | `p0/i6a` · `/home/user/wt/p0-i6a` | `p0/i6` (now) | feed schema, events, projector, parser, cards, queries, TUI pane | numbering `detect_keys`, link services (P0-I3) |
| B | MCP write | `p0/i6b` | `p0/i6` after P0-I4 is on the trunk | proposals service, MCP write tools, `tl proposal`, API routes | `proposals/types.py`, tl_mcp server (P0-I4 WS-C), feed `post` service (A) |
| C | Simulator | `p0/i6c` | `p0/i6` after P0-I4 and P0-I5 are on the trunk | `tl-sim` package, effective-time override, scenarios, `just seed` | REST API and MCP (P0-I4), A's post command, B's proposals |

## Shared contracts (committed on `p0/i6`)
- `packages/tl-core/src/tl_core/feed/types.py`: event type names, `ParsedTag`, `FeedItem`, `DEFAULT_SIGNAL_TAGS`, `CARD_WINDOW_SECONDS`, and the precedence of tag kinds.
- `packages/tl-core/src/tl_core/proposals/types.py`: proposal events, `ProposalView`, `PROPOSABLE_TOOLS`, `ToolMode = "propose"`, budgets, and the service signatures.
- Simulator actor interface (WS-C creates `packages/tl-sim/src/tl_sim/types.py` verbatim):

```python
# packages/tl-sim/src/tl_sim/types.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from random import Random
from typing import Any, Protocol

class SimClient(Protocol):
    """The only way actors touch the suite: wraps the P0-I4 HTTP client (README-C) and the MCP client.
    Every call carries the simulated time (header X-TL-Effective-At) and the actor's token."""
    def create_record(self, *, record_type: str, title: str, psets: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def set_psets(self, record_id: str, values: dict[str, Any]) -> dict[str, Any]: ...
    def link(self, from_id: str, to_id: str, relation: str | None = None) -> dict[str, Any]: ...
    def transition(self, record_id: str, transition: str) -> dict[str, Any]: ...
    def post(self, body: str) -> dict[str, Any]: ...
    def propose(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]: ...   # MCP propose-only tools
    def query(self, q: str, *, limit: int = 100) -> list[dict[str, Any]]: ...

@dataclass(frozen=True)
class SimContext:
    run_id: str
    scope: str                 # always "project:sim-<run_id>"
    now: datetime              # simulated time (UTC)
    rng: Random                # seeded per (run seed, actor name, day)
    client: SimClient

@dataclass(frozen=True)
class GroundTruth:
    """What the scenario intended. sim_assert compares these with cur_ tables."""
    at: datetime
    actor: str
    intent: str                # e.g. "record.created", "post.created", "link.added", "proposal.accepted"
    ref: str                   # key or id the intent is about
    expect: dict[str, Any]     # field -> expected value

class Actor(Protocol):
    name: str                  # "document_controller", "planner", "crew"
    identity: str              # "agent:sim-<name>"
    def step(self, ctx: SimContext) -> list[GroundTruth]: ...   # one simulated working day
```

## Orchestrator decisions
| # | Decision |
|---|---|
| D1 | Posts and proposals are ledger streams (`core.ActivityPost`, `core.Proposal`). Event cards are projection-only and are rebuilt deterministically from `recorded_at` and `seq`, never from wall-clock time. |
| D2 | Hashtags never mutate records. A resolved record tag calls the existing `SuggestLink` handler (relation `references`) in the same unit of work as `Feed.Posted`. A declined suggestion is not re-suggested (P0-I3 rule). Unresolved record-like tags stay `topic`. Namespaced codes are stored with their namespace but are not resolved, because the Standards registry arrives in Phase 1. Topics are text only; there is no `Topic` record in Phase 0. Mentions are stored unresolved, except `@agent:<id>`. |
| D3 | Visibility: a post's scope is its project. Record-level confidentiality waits for the auth model, which is a human gate. |
| D4 | MCP record-changing tools are propose-only. There is no direct-write mode, because deciding who may write directly is part of the permission model, a human gate (ADR-0005). Accepting runs the command as the human, with `source=mcp:<agent>` and causation set to the proposal. `post_feed` writes directly, labelled with the agent's actor. |
| D5 | Simulated time: `Command` (03 §7) is not changed. A new `tl_core.util.effective_time(dt)` context manager sets a contextvar that the ledger adapters read when `NewEvent.effective_at` is None. The API honours `X-TL-Effective-At` only for scopes matching `project:sim-*`; other scopes get HTTP 400. `simulated = true` (§29.5) is expressed by the `project:sim-` scope prefix plus `source=sim:<run_id>`. There is no new Event field. |
| D6 | Simulator v0 is fully deterministic and makes no LLM calls (cost budget zero). The LLM role agents of §29.5 come later. |
| D7 | `feed.signal_tags` and `feed.reactions.enabled` are constants in Phase 0. about:config arrives in P0-I8. |

## Merge order and conflict owner
A → (trunk sync after P0-I4 and P0-I5) → B → C. Merge commits only. The later-merging workstream's supervisor
resolves conflicts. C writes `dev/demos/P0-I6.sh` and `docs/reports/P0-I6.md`.

## Human gates
| Gate | Approver | Where recorded |
|---|---|---|
| `schema/core/feed.yaml` (ActivityPost, EventCard, Hashtag, Feed payloads) and `schema/core/proposals.yaml` | Orchestrator under KICKOFF delegation (§19.2, §21, §11.3) | APPROVALS.md |
| Direct-write MCP mode, per-role tool permissions | Human (auth and permission model) | Not built; noted in the report |

## Risks and escalation triggers
- Card aggregation that depends on processing order breaks rebuild determinism. Add a property test: rebuild equals live.
- Simulator flakiness from wall-clock time or thread timing. Every wait goes through the change feed with a timeout, never sleep-polling.
- If WS-C needs a change to 03 §7 (Command or Event), stop and escalate. Do not edit it. That is a KICKOFF stop condition.

## Decisions log
| Date | Raised by | Question | Decision | ADR |
|---|---|---|---|---|
| 2026-10-09 | orchestrator | How do agents write without an auth model? | Propose-only, with a human accept (D4) | ADR-0005 |
