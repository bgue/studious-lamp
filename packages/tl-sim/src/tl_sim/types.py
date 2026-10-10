# packages/tl-sim/src/tl_sim/types.py
# The actor interface below is the frozen contract of docs/tickets/P0-I6/FANOUT.md, kept verbatim:
# the formatter and the line-length and import-order rules are switched off for this file only.
# ruff: noqa: E501, I001
# fmt: off
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
# fmt: on
