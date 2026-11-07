"""Acceptance for P2-I2-T04c2: the IWP, constraint and readiness reads on the embedded client, the
API client and the fake (P2-I2 T04c2).

The ledger is the T04a world (as T04c1): IWPs i1, i2 visible to the low reader ``uma``; i3 (and its
CWP) hidden from her by a test-only class source; constraints on i1 (Open), i2 (Assigned), i3
(Cleared). The embedded client reads it as ``user:uma``; the API client calls the T04c1 routes on a
copy of it, signed in as ``uma``; the fake is ``seed_iwp(FakeClient())``. The readiness rows of i1
and i3 are written directly (the engine is S4's), as T04c1 does.

Prints ``PASS <method> <n> <client>`` for the seven methods on each of the three clients, then the
checks ``same``, ``missing``, ``hidden``, ``no-hash`` and ``word``, and ``T04c2 ok``. Exits 1 on the
first failure. No network.

Run: ``uv run python dev/accept/P2-I2/T04c2.py``.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages/tl-modules/awp/tests"))
sys.path.insert(0, str(ROOT / "packages/tl-tui/tests"))
sys.path.insert(0, str(Path(__file__).parent))

import t04a_checks as t  # noqa: E402
from awp_world import PASSWORD  # noqa: E402
from fakes import FakeClient  # noqa: E402
from fakes_iwp import seed_iwp  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from tl_adapters.backend import open_backend  # noqa: E402
from tl_adapters.db import as_target, open_uow  # noqa: E402
from tl_api.app import create_app  # noqa: E402
from tl_api.client import ApiClient  # noqa: E402
from tl_api.settings import ApiSettings  # noqa: E402
from tl_api.tokens import TokenStore  # noqa: E402
from tl_core.auth import sessions  # noqa: E402
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from tl_core.services.errors import RecordNotFoundError  # noqa: E402
from tl_mod_awp.names import READINESS_CHECK_TABLE, READINESS_TABLE  # noqa: E402
from tl_mod_awp.projectors._common import ddl_for  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
PIP1, PIP2, CIV1 = "P123-IWP-PIP-0001", "P123-IWP-PIP-0002", "P123-IWP-CIV-0001"
MISSING = "NO-SUCH"
LOW = "uma"
ACTOR = f"user:{LOW}"
NO_WORD_ACTOR = "user:ghost"  # an account-less actor: holds no core.constraint.view
BY = "owner"


def ok(name: str, cond: bool = True) -> None:
    if not cond:
        print(f"FAIL {name}", flush=True)
        sys.exit(1)
    print(f"PASS {name}", flush=True)


def plain(value: Any) -> Any:
    """A model (or a list of them) as plain JSON data, so two clients' answers can be compared."""
    if isinstance(value, list):
        return [plain(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")  # pyright: ignore[reportUnknownMemberType]
    if hasattr(value, "__dataclass_fields__"):
        return {k: plain(getattr(value, k)) for k in value.__dataclass_fields__}  # pyright: ignore
    return value


def keys_of(db: Path, sql: str, **params: Any) -> list[str]:
    with open_uow(as_target(str(db)), readonly=True) as uow:
        return [str(r[0]) for r in uow.conn().execute(text(sql), params).all()]


def raised(call: Any, error: type[Exception]) -> str | None:
    """The message of the ``error`` ``call`` raises, or ``None`` when it raises nothing of it."""
    try:
        call()
    except error as exc:
        return str(exc)
    return None


def missing_raises(client: Any, read: Any) -> bool:
    """Whether ``read(client)`` raises RecordNotFoundError (the missing-record error)."""
    return raised(lambda: read(client), RecordNotFoundError) is not None


def run_reads(label: str, client: Any, first_key: str, first_con: str) -> dict[str, Any]:
    """The seven reads of ``client`` on the project; prints one PASS line per method."""
    answers: dict[str, Any] = {}
    answers["list_iwps"] = client.list_iwps(PROJECT)
    answers["get_iwp"] = client.get_iwp(PROJECT, first_key)
    answers["list_iwp_scope"] = client.list_iwp_scope(PROJECT, first_key)
    answers["get_iwp_readiness"] = client.get_iwp_readiness(PROJECT, first_key)
    answers["list_constraints"] = client.list_constraints(PROJECT)
    answers["constraint_groups"] = client.constraint_groups(PROJECT, BY)
    answers["get_constraint"] = client.get_constraint(PROJECT, first_con)
    sizes = {
        "list_iwps": len(answers["list_iwps"]),
        "get_iwp": 1,
        "list_iwp_scope": len(answers["list_iwp_scope"]),
        "get_iwp_readiness": len(answers["get_iwp_readiness"].checks),
        "list_constraints": len(answers["list_constraints"].rows),
        "constraint_groups": len(answers["constraint_groups"].groups),
        "get_constraint": 1,
    }
    for method, n in sizes.items():
        print(f"PASS {method} {n} {label}", flush=True)
    return answers


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="t04c2-"))
    db = work / "t04c2.db"
    w, ctx = t.build(db)
    ids = t.seed(w, ctx)
    t.classed(w, {ids["i3"], ids["cwp"]})
    i1_key = w.column("cur_core_record", "key", ids["i1"])
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
    ok("seed: i1 and i3 each have one constraint", len(con_of_i1) == 1 == len(con_of_i3))
    ok("seed: i1 is the visible IWP", i1_key == PIP1)

    # readiness rows for i1 and i3 (the engine is S4's; the rows are written as T04c1 writes them)
    with open_uow(w.db) as uow:
        conn = uow.conn()
        for table in (READINESS_TABLE, READINESS_CHECK_TABLE):
            for statement in ddl_for(table, "sqlite"):
                conn.execute(text(statement))
        for n, iwp in enumerate((ids["i1"], ids["i3"])):
            conn.execute(
                text(
                    f"INSERT INTO {READINESS_TABLE} (iwp_id, scope, evaluated_at, today, ready, "
                    "facts_hash, as_of_seq) VALUES (:i, :s, 't', 'd', 0, 'FACTSHASH', 1)"
                ),
                {"i": iwp, "s": SCOPE},
            )
            conn.execute(
                text(
                    f"INSERT INTO {READINESS_CHECK_TABLE} (row_id, scope, iwp_id, name, version, "
                    "state, detail, count_ok, count_total, resolve_via_json, as_of_seq) VALUES "
                    "(:r, :s, :i, 'constraints_cleared', '1', 'blocked', 'x', 1, 3, '[]', 1)"
                ),
                {"r": f"row{n}", "s": SCOPE, "i": iwp},
            )

    # the embedded client, as the low reader
    embedded = EmbeddedClient.for_sqlite(db, actor=ACTOR)

    # the API client, on the routes over a copy of the ledger, signed in as the same reader
    api_db = work / "t04c2-api.db"
    api_db.write_bytes(db.read_bytes())
    tokens = work / "tokens.json"
    backend = open_backend(api_db)
    app = create_app(
        backend,
        settings=ApiSettings(db_path=api_db, tokens_path=tokens),
        tokens=TokenStore(tokens),
    )
    _, token = sessions.sign_in(backend, username=LOW, password=PASSWORD)
    http = TestClient(app, raise_server_exceptions=False)
    api = ApiClient("http://testserver", token, http=http)

    # the fake, seeded with the shape of seed_iwp
    fake = FakeClient()
    seed_iwp(fake)

    emb = run_reads("embedded", embedded, PIP1, con_of_i1[0])
    api_answers = run_reads("api", api, PIP1, con_of_i1[0])
    fak = run_reads("fake", fake, "P123-IWP-PIP-0001", "P123-CON-0001")

    # --- same: embedded and API equal on the four reads they both serve as models --------------
    same = all(
        plain(emb[m]) == plain(api_answers[m])
        for m in ("get_iwp", "get_iwp_readiness", "list_constraints", "get_constraint")
    )
    ok("same: embedded and API equal for get_iwp, readiness, constraints", same)

    # --- missing: all three raise RecordNotFoundError for NO-SUCH -----------------------------
    missing_reads = (
        ("get_iwp", lambda c: c.get_iwp(PROJECT, MISSING)),
        ("list_iwp_scope", lambda c: c.list_iwp_scope(PROJECT, MISSING)),
        ("get_iwp_readiness", lambda c: c.get_iwp_readiness(PROJECT, MISSING)),
        ("get_constraint", lambda c: c.get_constraint(PROJECT, MISSING)),
    )
    all_missing = all(
        missing_raises(client, read)
        for client in (embedded, api, fake)
        for _n, read in missing_reads
    )
    ok("missing: all three raise RecordNotFoundError for NO-SUCH", all_missing)

    # --- hidden: a low reader gets the missing text for a hidden IWP, no hidden constraint -----
    hidden_text = raised(lambda: embedded.get_iwp(PROJECT, CIV1), RecordNotFoundError)
    missing_text = raised(lambda: embedded.get_iwp(PROJECT, MISSING), RecordNotFoundError)
    api_hidden = raised(lambda: api.get_iwp(PROJECT, CIV1), RecordNotFoundError)
    api_missing = raised(lambda: api.get_iwp(PROJECT, MISSING), RecordNotFoundError)
    same_text = (
        hidden_text is not None
        and api_hidden is not None
        and hidden_text.replace(CIV1, "KEY") == (missing_text or "").replace(MISSING, "KEY")
        and api_hidden.replace(CIV1, "KEY") == (api_missing or "").replace(MISSING, "KEY")
    )
    listed = emb["list_constraints"]
    hidden_absent = (
        con_of_i3[0] not in [r.key for r in listed.rows]
        and listed.total == len(listed.rows) == 2
        and con_of_i3[0] not in [r.key for r in api_answers["list_constraints"].rows]
        and api_answers["list_constraints"].total == 2
    )
    ok(
        "hidden: same error text as missing; hidden constraint absent from rows and total",
        same_text and hidden_absent,
    )

    # --- no-hash: the readiness model has no facts hash ---------------------------------------
    no_hash = all(
        "facts_hash" not in type(a["get_iwp_readiness"]).model_fields
        and "facts_hash" not in plain(a["get_iwp_readiness"])
        for a in (emb, api_answers, fak)
    )
    ok("no-hash: no facts_hash field on the readiness model", no_hash)

    # --- word: an actor without core.constraint.view is refused before any read ----------------
    refused = raised(
        lambda: EmbeddedClient.for_sqlite(db, actor=NO_WORD_ACTOR).list_constraints(PROJECT),
        ForbiddenError,
    )
    ok(
        "word: an actor without core.constraint.view is refused by list_constraints",
        refused is not None,
    )

    api.close()
    http.close()
    backend.close()
    print("T04c2 ok", flush=True)


if __name__ == "__main__":
    main()
