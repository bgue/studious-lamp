"""The fixed identities of the simulator (a leaf module: actors and the orchestrator share them)."""

ORCHESTRATOR = "user:sim-orchestrator"
ASSISTANT = "agent:sim-assistant"
"""The one simulated agent. The API refuses record-changing commands from any ``agent:*`` token
(WS-B B15, FANOUT D4: agents propose, people accept), so the role actors, which stand in for people,
are ``user:sim-<role>``; the assistant only proposes (over MCP) and posts."""
