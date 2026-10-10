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
