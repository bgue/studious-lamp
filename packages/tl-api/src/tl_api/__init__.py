"""The Throughline REST API, SSE stream and HTTP client (brief 11.1, 18.1-18.3).

Nothing is imported here on purpose: ``import tl_api`` stays cheap for callers (the CLI, the
remote TUI client) that need only one submodule. Start with ``tl_api.app.create_app``.
"""
