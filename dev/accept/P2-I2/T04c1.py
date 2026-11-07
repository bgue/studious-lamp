"""Acceptance for P2-I2-T04c1: the IWP and constraint read routes, as two readers (clearance low
and high). SQLite temp ledger, in-process TestClient, no network.

The seed is the T04a world (IWPs i1, i2 visible; i3 and its CWP hidden from the low reader by a
test-only class source; constraints on i1 (Open), i2 (Assigned), i3 (Cleared)). The low reader is
``uma`` (plain user), the high reader is ``ada`` (admin, reads restricted).

Prints one ``PASS <check>`` line per check, then ``T04c1 ok``. Exits 1 on the first failure.
The readiness route is NOT covered here: it is blocked (see the report).

Run: ``uv run python dev/accept/P2-I2/T04c1.py``.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parents[3] / "packages/tl-modules/awp/tests"))
sys.path.insert(0, str(Path(__file__).parent))

import t04a_checks as t  # noqa: E402
from awp_world import PASSWORD  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from tl_adapters.backend import open_backend  # noqa: E402
from tl_adapters.db import as_target, open_uow  # noqa: E402
from tl_api import routes as api_routes  # noqa: E402
from tl_api.app import create_app  # noqa: E402
from tl_api.auth import Forbidden  # noqa: E402
from tl_api.settings import ApiSettings  # noqa: E402
from tl_api.tokens import TokenStore  # noqa: E402
from tl_core.auth import sessions  # noqa: E402
from tl_core.constraints.commands import VIEW_WORD  # noqa: E402

PROJECT = "P123"
BASE = f"/projects/{PROJECT}/awp"
CBASE = f"/projects/{PROJECT}/constraints"
PIP1, PIP2, CIV1 = "P123-IWP-PIP-0001", "P123-IWP-PIP-0002", "P123-IWP-CIV-0001"
MADE_UP_IWP = "P123-IWP-CIV-9999"
MADE_UP_KEY = "P123-CON-9999"
LOW, HIGH = "uma", "ada"


def ok(name: str, cond: bool = True) -> None:
    if not cond:
        print(f"FAIL {name}", flush=True)
        sys.exit(1)
    print(f"PASS {name}", flush=True)


def keys_of(db: Path, sql: str, **params: Any) -> list[str]:
    with open_uow(as_target(str(db)), readonly=True) as uow:
        return [str(r[0]) for r in uow.conn().execute(text(sql), params).all()]


def numbers(body: list[dict[str, Any]]) -> list[str]:
    return [row["number"] for row in body]


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="t04c1-"))
    db = work / "t04c1.db"
    w, ctx = t.build(db)
    ids = t.seed(w, ctx)
    t.classed(w, {ids["i3"], ids["cwp"]})
    i1_key = w.column("cur_core_record", "key", ids["i1"])
    i3_key = w.column("cur_core_record", "key", ids["i3"])
    con_of_i1 = keys_of(
        db,
        "SELECT r.key FROM cur_core_constraint c JOIN cur_core_record r ON r.id = c.id "
        "WHERE c.subject_id = :s",
        s=ids["i1"],
    )
    con_of_i3 = keys_of(
        db,
        "SELECT r.key FROM cur_core_constraint c JOIN cur_core_record r ON r.id = c.id "
        "WHERE c.subject_id = :s",
        s=ids["i3"],
    )
    ok(
        "seed: one constraint on the visible IWP and one on the hidden IWP",
        len(con_of_i1) == 1 and len(con_of_i3) == 1,
    )

    tokens = work / "tokens.json"
    backend = open_backend(db)

    def app_with(hook: Any = None) -> Any:
        kwargs: dict[str, Any] = {}
        if hook is not None:
            kwargs["authorize_hook"] = hook
        return create_app(
            backend,
            settings=ApiSettings(db_path=db, tokens_path=tokens),
            tokens=TokenStore(tokens),
            **kwargs,
        )

    def client_for(app: Any, who: str | None) -> TestClient:
        client = TestClient(app, raise_server_exceptions=False)
        if who is not None:
            _, token = sessions.sign_in(backend, username=who, password=PASSWORD)
            client.headers.update({"Authorization": f"Bearer {token}"})
        return client

    app = app_with()
    low, high = client_for(app, LOW), client_for(app, HIGH)
    anonymous = client_for(app, None)

    # --- IWP list: class filter, totals -----------------------------------------------------
    low_iwps = low.get(f"{BASE}/iwps")
    high_iwps = high.get(f"{BASE}/iwps")
    ok("IWP list, low reader: the hidden IWP is absent", numbers(low_iwps.json()) == [PIP1, PIP2])
    ok("IWP list, high reader: all three", numbers(high_iwps.json()) == [CIV1, PIP1, PIP2])
    ok(
        "IWP list filter: discipline",
        numbers(low.get(f"{BASE}/iwps", params={"discipline": "CIV"}).json()) == [],
    )

    # --- IWP detail and scope: hidden looks like missing ------------------------------------
    hidden = low.get(f"{BASE}/iwps/{CIV1}")
    missing = low.get(f"{BASE}/iwps/{MADE_UP_IWP}")
    ok(
        "IWP detail, low reader: hidden and missing are the same 404 record_not_found",
        hidden.status_code == 404
        and missing.status_code == 404
        and hidden.json()["error"] == missing.json()["error"] == "record_not_found"
        and hidden.text.replace(CIV1, "KEY") == missing.text.replace(MADE_UP_IWP, "KEY"),
    )
    hidden_scope = low.get(f"{BASE}/iwps/{CIV1}/scope")
    missing_scope = low.get(f"{BASE}/iwps/{MADE_UP_IWP}/scope")
    ok(
        "IWP scope, low reader: hidden and missing answer alike",
        hidden_scope.status_code == 404
        and hidden_scope.text.replace(CIV1, "KEY")
        == missing_scope.text.replace(MADE_UP_IWP, "KEY"),
    )
    visible = high.get(f"{BASE}/iwps/{CIV1}")
    ok("IWP detail, high reader: the restricted IWP answers 200", visible.status_code == 200)
    detail = low.get(f"{BASE}/iwps/{PIP1}")
    ok(
        "IWP detail, low reader: 40 scope items and 2 pins",
        detail.status_code == 200
        and detail.json()["scope_count"] == 40
        and detail.json()["pin_count"] == 2,
    )
    scope = low.get(f"{BASE}/iwps/{PIP1}/scope")
    ok(
        "IWP scope, low reader: lists the 40 items",
        scope.status_code == 200 and len(scope.json()) == 40,
    )

    # --- constraints: list, total equals visible rows ---------------------------------------
    low_list = low.get(CBASE).json()
    high_list = high.get(CBASE).json()
    ok(
        "constraint list, low reader: rows and total are the visible two",
        len(low_list["rows"]) == low_list["total"] == 2,
    )
    ok(
        "constraint list, high reader: rows and total are all three",
        len(high_list["rows"]) == high_list["total"] == 3,
    )
    ok(
        "constraint list: the hidden constraint key is not in the low body",
        con_of_i3[0] not in low.get(CBASE).text,
    )
    by_subject = low.get(CBASE, params={"subject": i1_key}).json()
    ok(
        "constraint list filter: subject key finds its constraint",
        [r["key"] for r in by_subject["rows"]] == con_of_i1,
    )
    hidden_subject = low.get(CBASE, params={"subject": i3_key})
    missing_subject = low.get(CBASE, params={"subject": "P123-IWP-NOPE-0000"})
    ok(
        "constraint list: hidden subject and missing subject give the same empty body",
        hidden_subject.json() == missing_subject.json() == {"rows": [], "total": 0},
    )

    # --- constraint detail: hidden looks like missing ---------------------------------------
    hidden_con = low.get(f"{CBASE}/{con_of_i3[0]}")
    missing_con = low.get(f"{CBASE}/{MADE_UP_KEY}")
    ok(
        "constraint detail, low reader: hidden and missing are the same 404",
        hidden_con.status_code == 404
        and missing_con.status_code == 404
        and hidden_con.text.replace(con_of_i3[0], "KEY")
        == missing_con.text.replace(MADE_UP_KEY, "KEY"),
    )
    shown = low.get(f"{CBASE}/{con_of_i1[0]}")
    ok(
        "constraint detail, low reader: the visible constraint answers 200",
        shown.status_code == 200,
    )

    # --- groups: the grouping word is validated, groups count visible rows ------------------
    groups = low.get(f"{CBASE}/groups", params={"by": "owner"})
    ok(
        "constraint groups by owner: 200 and the visible count",
        groups.status_code == 200 and sum(g["count"] for g in groups.json()) == 2,
    )
    bad = low.get(f"{CBASE}/groups", params={"by": "colour"})
    ok("constraint groups: a word outside BY_WORDS is 422", bad.status_code == 422)

    # --- anonymous and refusal before any read ----------------------------------------------
    ok("constraint list without a token is 401", anonymous.get(CBASE).status_code == 401)

    seen: list[str] = []

    def refuse_view(actor: str, action: str, resource: str) -> None:
        seen.append(action)
        if action == VIEW_WORD:
            raise Forbidden(f"{action} refused for this check")

    refusing = TestClient(app_with(refuse_view), raise_server_exceptions=False)
    _, token = sessions.sign_in(backend, username=LOW, password=PASSWORD)
    refusing.headers.update({"Authorization": f"Bearer {token}"})
    calls: list[str] = []
    real_list = api_routes.constraints.list_constraints

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append("list")
        return real_list(*args, **kwargs)

    api_routes.constraints.list_constraints = counting  # type: ignore[attr-defined]
    try:
        refused = refusing.get(CBASE)
        still = refusing.get(f"{BASE}/iwps")
    finally:
        api_routes.constraints.list_constraints = real_list  # type: ignore[attr-defined]
    ok("refusal: the word check answers 403 for a constraint route", refused.status_code == 403)
    ok("refusal: no constraint read ran before the refusal", calls == [])
    ok(
        "refusal: the IWP route still reads (document.read, not the constraint word)",
        still.status_code == 200,
    )
    ok("refusal: the word was the action checked", VIEW_WORD in seen)
    print("T04c1 ok", flush=True)


if __name__ == "__main__":
    main()
