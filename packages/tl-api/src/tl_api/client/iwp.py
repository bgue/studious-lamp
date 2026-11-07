"""The IWP, constraint and readiness reads over HTTP (P2-I2 T04c2).

The same models the embedded client returns: ``tl_mod_awp.iwp_views`` for the IWP rows, detail and
scope, the route models ``ReadinessBody`` (no facts hash), ``ConstraintList``, ``ConstraintGroups``
and ``ConstraintRow`` for the rest. A missing, hidden or never-evaluated record raises the module's
``RecordNotFoundError``, rebuilt from the 404 body.
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter
from tl_core.constraints.review import BY_WORDS
from tl_mod_awp import iwp_views

from tl_api.client.base import ApiClientBase, quote
from tl_api.routes.awp import ReadinessBody
from tl_api.routes.constraints import ConstraintGroups, ConstraintList, ConstraintRow


class IwpApi(ApiClientBase):
    def list_iwps(
        self,
        project: str,
        *,
        state: str | None = None,
        discipline: str | None = None,
        foreman: str | None = None,
        limit: int = 200,
    ) -> list[iwp_views.IwpRow]:
        """A project's IWPs by number (``GET .../awp/iwps``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/awp/iwps",
            {"state": state, "discipline": discipline, "foreman": foreman, "limit": limit},
        )
        return self._models(iwp_views.IwpRow, data)

    def get_iwp(self, project: str, number: str) -> iwp_views.IwpDetail:
        """One IWP with its pins, open constraints and scope count (``.../awp/iwps/{number}``)."""
        data = self._get_json(f"/projects/{quote(project)}/awp/iwps/{quote(number)}")
        return self._model(iwp_views.IwpDetail, data)

    def list_iwp_scope(
        self, project: str, number: str, *, limit: int = 200
    ) -> list[iwp_views.ScopeRow]:
        """The scope items and tags of one IWP (``.../awp/iwps/{number}/scope``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/awp/iwps/{quote(number)}/scope", {"limit": limit}
        )
        return self._models(iwp_views.ScopeRow, data)

    def get_iwp_readiness(self, project: str, number: str) -> ReadinessBody:
        """The last readiness evaluation of one IWP (``.../awp/iwps/{number}/readiness``)."""
        data = self._get_json(f"/projects/{quote(project)}/awp/iwps/{quote(number)}/readiness")
        return self._model(ReadinessBody, data)

    def list_constraints(
        self,
        project: str,
        *,
        subject: str | None = None,
        state: str | None = None,
        category: str | None = None,
        phase: str | None = None,
        blocking: bool | None = None,
        owner: str | None = None,
        limit: int = 200,
    ) -> ConstraintList:
        """The constraints a viewer may read, and the total the same filters find
        (``GET .../constraints``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/constraints",
            {
                "subject": subject,
                "state": state,
                "category": category,
                "phase": phase,
                "blocking": blocking,
                "owner": owner,
                "limit": limit,
            },
        )
        return self._model(ConstraintList, data)

    def constraint_groups(self, project: str, by: str) -> ConstraintGroups:
        """The review groups by ``owner``, ``category`` or ``age`` (``.../constraints/groups``).
        A ``by`` outside ``BY_WORDS`` raises ``ValueError`` before any request."""
        if by not in BY_WORDS:
            raise ValueError(f"by must be one of {', '.join(BY_WORDS)}")
        data: Any = self._get_json(f"/projects/{quote(project)}/constraints/groups", {"by": by})
        return self._model(ConstraintGroups, data)

    def get_constraint(self, project: str, key: str) -> ConstraintRow:
        """One constraint by key (``GET .../constraints/{key}``)."""
        data = self._get_json(f"/projects/{quote(project)}/constraints/{quote(key)}")
        # ConstraintRow is a dataclass (not a model), so it is validated by a TypeAdapter.
        return TypeAdapter(ConstraintRow).validate_python(data)
