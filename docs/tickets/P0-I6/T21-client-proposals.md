# P0-I6-T21 — ApiClient review-queue methods

Status: ready
Tier: haiku
Labels: api
Depends on: — (the proposal routes are on the base)
Branch: `p0/i6b-t21-client-proposals`

## Goal
`ApiClient` can read and decide the review queue over HTTP: `list_proposals`, `get_proposal`, `accept_proposal`, `reject_proposal`. The module
`tl_api/client/proposals.py` (a mixin of `ApiClient`, already wired in `client/__init__.py`) has the signatures and docstrings; the four
methods raise `NotImplementedError`. A provided test file (9 tests) must pass.

## Brief references (pasted)
> **11.3** Record-changing MCP tools are propose-only in Phase 0: a call records a proposal; a person accepts or rejects it in a review queue.
> Accepting runs the proposal's command as that person, tagged with the agent that proposed it.
> README-C (the client): every method sends the bearer token; an error response is turned back into the exception class an embedded call would
> raise (`tl_api.errors.exception_for`), so `ProposalNotFoundError`, `ProposalNotPendingError` and `ProposalDeciderError` arrive as such.

### Specification
Routes (final, already served; see `docs/reference/openapi.json`):
`GET /proposals?scope=&status=&agent=&all=&limit=` returns a list of `ProposalView`; `all=true` lists every status and ignores `status`.
`GET /proposals/{id}?scope=` returns one. `POST /proposals/{id}/accept` takes `{"roles": [..]}`; `POST /proposals/{id}/reject` takes `{"reason": ".."}`;
both return the proposal. A command that cannot be applied on accept is an HTTP 200 whose proposal has status `failed`; do not raise for it.
`ApiClientBase` offers `_get_json(path, params)` (drops None parameters), `_post_json(path, body)`, `_model(cls, data)`, `_models(cls, data)` and the
module function `quote(segment)` for path segments (it raises `ValueError` for `.` and `..`).

Learnings that apply:
- pyright is `strict` for `packages/tl-api/src`; ruff limits lines to 100 columns. Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I6/provided/*.py.txt`; copy them into the test tree byte for byte. Do not edit the copy.
- Commit your report at `docs/reports/P0-I6/P0-I6-T21.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. Remove the `STUB` paragraph from every docstring you fill in and the `STUB` line in the module docstring.
- The OpenAPI document is drift-checked by `just check`; this ticket changes no route, so it must stay clean.
- ruff's autofix removed an import the stub does not use; add back `quote` to the `from tl_api.client.base import ...` line.

## Interfaces (verbatim from the repo at the branch point)
```python
"""The review queue over HTTP: list, show, accept and reject proposals (P0-I6-T21).

STUB (P0-I6-T21): the four methods raise NotImplementedError.

A proposal is the ``ProposalView`` the service returns. Failures raise the embedded exception
classes (``ProposalNotFoundError``, ``ProposalNotPendingError``, ``ProposalDeciderError`` ...).
Accepting a proposal whose command can no longer be applied does not raise: the answer is the
proposal with ``status == "failed"`` and the refusal in ``reason``.
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_core.proposals.types import ProposalStatus, ProposalView

from tl_api.client.base import ApiClientBase


class ProposalsApi(ApiClientBase):
    def list_proposals(
        self,
        scope: str,
        *,
        status: ProposalStatus | None = "pending",
        agent: str | None = None,
        limit: int = 200,
    ) -> list[ProposalView]:
        """Proposals of ``scope``, oldest first (``GET /proposals``); ``status`` None: all.

        Query parameters: ``scope``, ``status`` (omitted when None), ``all=true`` only when
        ``status`` is None, ``agent`` and ``limit`` (``_get_json`` drops the None values). Decode
        the list with ``self._models(ProposalView, data)``.

        STUB (P0-I6-T21): remove this paragraph when you implement the method.
        """
        raise NotImplementedError("STUB (P0-I6-T21)")

    def get_proposal(self, proposal_id: str, *, scope: str | None = None) -> ProposalView:
        """One proposal with its command (``GET /proposals/{id}``, optional ``scope`` query).

        The id goes into the path through ``quote(proposal_id)``. Decode with
        ``self._model(ProposalView, data)``.

        STUB (P0-I6-T21): remove this paragraph when you implement the method.
        """
        raise NotImplementedError("STUB (P0-I6-T21)")

    def accept_proposal(self, proposal_id: str, *, roles: Sequence[str] = ()) -> ProposalView:
        """Run the proposal's command as the token's actor (``POST /proposals/{id}/accept``).

        The body is ``{"roles": list(roles)}``. The answer is a ``ProposalView`` with status
        ``accepted``, or ``failed`` when the command was refused.

        STUB (P0-I6-T21): remove this paragraph when you implement the method.
        """
        raise NotImplementedError("STUB (P0-I6-T21)")

    def reject_proposal(self, proposal_id: str, reason: str) -> ProposalView:
        """Reject a pending proposal with a reason (``POST /proposals/{id}/reject``).

        The body is ``{"reason": reason}``.

        STUB (P0-I6-T21): remove this paragraph when you implement the method.
        """
        raise NotImplementedError("STUB (P0-I6-T21)")
```
```python
# tl_core.proposals.types.ProposalView (pydantic): proposal_id, scope, tool, agent, command_type, command: dict[str, Any], summary,
#   status: "pending"|"accepted"|"rejected"|"failed", decided_by: str|None, reason: str|None, result_stream_id: str|None, seq: int
# tl_api.client.base: quote(segment) -> str;  ApiClientBase._get_json(path, params=None) -> Any;  ._post_json(path, body, params=None) -> Any
#                     ._model(model_cls, data) -> M;  ._models(model_cls, data) -> list[M]
# A sibling to copy the style from: tl_api/client/feed.py (FeedApi) and tl_api/client/records.py
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-api/src/tl_api/client/proposals.py`
- `packages/tl-api/src/tl_api/client/feed.py` (style)
- `packages/tl-api/src/tl_api/routes/proposals.py` (the routes you call)
- `docs/tickets/P0-I6/provided/b-test_client_proposals.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-api/src/tl_api/client/proposals.py` (edit)
- `packages/tl-api/tests/test_client_proposals.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I6/P0-I6-T21.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I6/provided/b-test_client_proposals.py.txt packages/tl-api/tests/test_client_proposals.py`
2. Implement the four methods; delete the STUB paragraphs; add the import you need.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-api/tests/test_client_proposals.py -q
just check
just test
```
Expected: 9 tests pass; `just check` clean; `just test` green.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report.

## Escalation triggers
- Stop and report *Blocked* if a pasted signature disagrees with the repo.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
