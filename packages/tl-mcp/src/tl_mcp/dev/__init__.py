"""The dev MCP server (brief 25.3): tools and resources for coding agents, dev data only.

Run it with ``uv run python -m tl_mcp.dev`` (stdio). It is a separate entry point from the product
MCP server (:mod:`tl_mcp`): different tools, no actor, and a guard (:mod:`tl_mcp.dev.guard`) that
refuses any database that is not dev data. Runbook: ``docs/runbooks/dev-mcp.md``.
"""
