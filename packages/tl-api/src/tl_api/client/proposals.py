"""The review queue over HTTP: list, show, accept and reject proposals (P0-I6-T21).

A proposal is the ``ProposalView`` the service returns. Failures raise the embedded exception
classes (``ProposalNotFoundError``, ``ProposalNotPendingError``, ``ProposalDeciderError`` ...).
Accepting a proposal whose command can no longer be applied does not raise: the answer is the
proposal with ``status == "failed"`` and the refusal in ``reason``.
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_core.proposals.types import ProposalStatus, ProposalView

from tl_api.client.base import ApiClientBase, quote


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
        """
        data = self._get_json(
            "/proposals",
            {
                "scope": scope,
                "status": status,
                "all": True if status is None else None,
                "agent": agent,
                "limit": limit,
            },
        )
        return self._models(ProposalView, data)

    def get_proposal(self, proposal_id: str, scope: str) -> ProposalView:
        """One proposal with its command (``GET /proposals/{id}?scope=``); the scope is required
        and a proposal of another scope is ``ProposalNotFoundError``.

        The id goes into the path through ``quote(proposal_id)``. Decode with
        ``self._model(ProposalView, data)``.
        """
        data = self._get_json(f"/proposals/{quote(proposal_id)}", {"scope": scope})
        return self._model(ProposalView, data)

    def accept_proposal(self, proposal_id: str, *, roles: Sequence[str] = ()) -> ProposalView:
        """Run the proposal's command as the token's actor (``POST /proposals/{id}/accept``).

        The body is ``{"roles": list(roles)}``. The answer is a ``ProposalView`` with status
        ``accepted``, or ``failed`` when the command was refused.
        """
        data = self._post_json(f"/proposals/{quote(proposal_id)}/accept", {"roles": list(roles)})
        return self._model(ProposalView, data)

    def reject_proposal(self, proposal_id: str, reason: str) -> ProposalView:
        """Reject a pending proposal with a reason (``POST /proposals/{id}/reject``).

        The body is ``{"reason": reason}``.
        """
        data = self._post_json(f"/proposals/{quote(proposal_id)}/reject", {"reason": reason})
        return self._model(ProposalView, data)
