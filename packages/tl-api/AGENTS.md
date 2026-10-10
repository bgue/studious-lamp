# AGENTS.md — tl-api

Read the root `AGENTS.md` first. These rules add to it.

- No business logic here. Routes call `tl_core` services or handlers through `ctx.backend(readonly)`; no SQL, no ledger access, no adapter imports outside `backend.py`.
- Every route depends on `guard("<action>")` (it authenticates and calls `authorize`). A route without it fails `test_every_route_calls_the_hook`. Never design roles or permissions here: that is a human gate (ADR-0005).
- Open the unit of work inside the handler, never in a `yield` dependency (the response must not be built before the commit).
- Every expected failure comes from `tl_api/errors.py`. A new `ServiceError` subclass needs a row there; do not add an `Exception` catch-all handler (it breaks keep-alive connections).
- A command body never carries `actor`. Do not add a way to set it from a request.
- `docs/reference/openapi.json` is generated and drift-checked by `just check`: change a route, run `uv run python -m tl_api.openapi`, commit both. A ticket that only implements a route body must not change any signature, decorator or description.
- Any response that returns file bytes keeps `attachment`, `nosniff` and `application/octet-stream`.
- The client (`tl_api/client/`) keeps the `ClientInterface` method names and parameters; `tests/api/test_client_roundtrip.py` compares it with the embedded client. Put every id in a path through `quote()`.
- Modules that build endpoints in a loop (`commands.py`) must not use `from __future__ import annotations`.
- SSE tests need a real server (`Harness.live()`); the in-process test client buffers whole responses.
