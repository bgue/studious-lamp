"""The requisition and work order reads over HTTP (P2-I4A T04c2).

The same models the embedded client returns: the route models ``RequisitionList``,
``RequisitionDetailBody``, ``WorkOrderList`` and ``WorkOrderDetailBody``
(``tl_api.routes.requisitions``).
A missing or hidden requisition or work order raises the service's ``RecordNotFoundError``, rebuilt
from the 404 body.
"""

from __future__ import annotations

from typing import Literal

from tl_api.client.base import ApiClientBase, quote
from tl_api.routes.requisitions import (
    RequisitionDetailBody,
    RequisitionList,
    WorkOrderDetailBody,
    WorkOrderList,
)


class RequisitionsApi(ApiClientBase):
    def list_requisitions(
        self,
        project: str,
        *,
        kind: Literal["labor", "material", "general", "scaffold"] | None = None,
        state: str | None = None,
        requester: str | None = None,
        for_key: str | None = None,
        limit: int = 200,
    ) -> RequisitionList:
        """The requisitions a viewer may read, by key (``GET .../requisitions``); ``for_key`` is
        the IWP or CWP key they serve (sent as the ``for`` query)."""
        data = self._get_json(
            f"/projects/{quote(project)}/requisitions",
            {
                "kind": kind,
                "state": state,
                "requester": requester,
                "for": for_key,
                "limit": limit,
            },
        )
        return self._model(RequisitionList, data)

    def get_requisition(self, project: str, key: str) -> RequisitionDetailBody:
        """One requisition with its kind fields and work order (``.../requisitions/{key}``)."""
        data = self._get_json(f"/projects/{quote(project)}/requisitions/{quote(key)}")
        return self._model(RequisitionDetailBody, data)

    def list_work_orders(
        self,
        project: str,
        *,
        state: str | None = None,
        assigned_to: str | None = None,
        limit: int = 200,
    ) -> WorkOrderList:
        """The work orders a viewer may read, by key (``GET .../work-orders``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/work-orders",
            {"state": state, "assigned_to": assigned_to, "limit": limit},
        )
        return self._model(WorkOrderList, data)

    def get_work_order(self, project: str, key: str) -> WorkOrderDetailBody:
        """One work order with the key of its requisition (``.../work-orders/{key}``)."""
        data = self._get_json(f"/projects/{quote(project)}/work-orders/{quote(key)}")
        return self._model(WorkOrderDetailBody, data)
