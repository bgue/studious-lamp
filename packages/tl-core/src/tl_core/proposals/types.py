"""Proposal (review queue) contracts for P0-I6 MCP write tools (brief §11.3, §18.12).

Frozen for the increment: change only by orchestrator decision.

Phase 0 MCP record-changing tools are **propose-only**: a tool call validates its command and
records a proposal; a human accepts it, and only then does the command run, as the accepting human
with the agent named in the payload. A direct "write" mode is not built: deciding who may write
directly is part of the permission model, a human gate (04-gates.md §2, ADR-0005).

Proposals are ledger events on their own stream (stream_type ``core.Proposal``, stream id =
proposal id, scope = the command's scope).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

# Proposal.Created: {proposal_id, tool, agent, command_type, command: dict, summary}
PROPOSAL_CREATED = "Proposal.Created"
# Proposal.Accepted: {proposal_id, by, result_stream_id, result_version}
PROPOSAL_ACCEPTED = "Proposal.Accepted"
# Proposal.Rejected: {proposal_id, by, reason}
PROPOSAL_REJECTED = "Proposal.Rejected"
# Proposal.Failed: {proposal_id, by, error}; accepted, but the command refused (stale, guard)
PROPOSAL_FAILED = "Proposal.Failed"

ProposalStatus = Literal["pending", "accepted", "rejected", "failed"]
# The only mode in Phase 0; "write" is refused with a human-gate message.
ToolMode = Literal["propose"]

# The command types a proposal may carry, mapped by tool. The command model is the shared one
# from tl_core.services (CreateRecord, SetPsetValues, AddLink, TransitionWorkflow).
PROPOSABLE_TOOLS: dict[str, str] = {
    "create_record": "CreateRecord",
    "update_psets": "SetPsetValues",
    "link_records": "AddLink",
    "transition_workflow": "TransitionWorkflow",
}


class ProposalView(BaseModel):
    proposal_id: str
    scope: str
    tool: str
    agent: str  # "agent:<id>"
    command_type: str
    command: dict[str, Any]
    summary: str
    status: ProposalStatus
    decided_by: str | None = None
    reason: str | None = None
    result_stream_id: str | None = None
    seq: int


# Service signatures (implemented in tl_core.services.proposals):
#   propose(uow, *, tool: str, agent: str, command: Command, summary: str) -> ProposalView
#       Validates the command (pydantic plus the handler's non-writing pre-checks) and raises the
#       same ServiceError the handler would. Records Proposal.Created with source "mcp:<agent>".
#   accept_proposal(uow, *, proposal_id: str, by: str) -> ProposalView
#       In one unit of work: re-runs the command with actor=by, source="mcp:<agent>", causation
#       = the Proposal.Created event id, then appends Proposal.Accepted. If the command raises a
#       ServiceError, roll back and append Proposal.Failed in a fresh unit of work.
#   reject_proposal(uow, *, proposal_id: str, by: str, reason: str) -> ProposalView
#   list_proposals(conn, scope: str, *, status: ProposalStatus | None = "pending")
#       -> list[ProposalView]
# Budgets: at most AGENT_DAILY_PROPOSALS proposals created per agent per UTC day, else
# BudgetExceededError(ServiceError).
AGENT_DAILY_PROPOSALS = 500
