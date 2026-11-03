"""Acceptance for P2-I1-T03b: the awp reads on the embedded client, the API client and the fake.

Copies the seed ledger (written by ``S4.py --keep``) to a scratch file. The embedded client reads it
as ``vera`` (the awp viewer); the API client calls the T03a routes on a copy of it, signed in as
``vera`` too. The fake holds the shape ``seed_awp`` gives it. Each of the eight reads prints
``PASS <client> <method> <n> rows`` for the embedded client and the fake, and for the API client
where the read is a route. ``PASS same CWP`` when the embedded and the API client return equal CWP
details; ``PASS missing`` when all three raise ``RecordNotFoundError`` for ``NO-SUCH``. Prints
``T03b ok`` at the end; exits 1 on the first failure. No network.

Run: ``uv run python dev/accept/P2-I1/T03b.py --db .accept/p2-i1.db``.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "tl-tui" / "tests"))  # the fake client and its helpers

from fakes import FakeClient  # noqa: E402
from fakes_awp import seed_awp  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tl_adapters.backend import open_backend  # noqa: E402
from tl_api.app import create_app  # noqa: E402
from tl_api.client import ApiClient  # noqa: E402
from tl_api.settings import ApiSettings  # noqa: E402
from tl_api.tokens import TokenStore  # noqa: E402
from tl_core.auth import sessions  # noqa: E402
from tl_core.services.errors import RecordNotFoundError  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402

PASSWORD = "correct horse battery"  # the S4 seed's password for every person
READER = "vera"  # the awp viewer grant in the S4 seed
ACTOR = f"user:{READER}"
PROJECT = "P123"
MISSING = "NO-SUCH"


def passed(line: str) -> None:
    print(f"PASS {line}", flush=True)


def need(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL {message}", flush=True)
        sys.exit(1)


def plain(value: Any) -> Any:
    """A model or a list of models as plain data, so two answers can be compared."""
    if isinstance(value, list):
        return [plain(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")  # pyright: ignore[reportUnknownMemberType]
    return value


def reads(client: Any) -> dict[str, Any]:
    """The eight reads, called the same way on every client."""
    return {
        "list_cwps": lambda: client.list_cwps(PROJECT),
        "get_cwp": lambda: client.get_cwp(PROJECT, client.list_cwps(PROJECT)[0].number),
        "list_cwas": lambda: client.list_cwas(PROJECT),
        "wbs_tree": lambda: client.wbs_tree(PROJECT),
        "get_wbs_node": lambda: client.get_wbs_node(PROJECT, client.wbs_tree(PROJECT)[0].code),
        "get_path": lambda: client.get_path(PROJECT),
        "list_path_versions": lambda: client.list_path_versions(PROJECT),
        "list_packages": lambda: client.list_packages(PROJECT),
    }


def count(value: Any) -> int:
    """Rows of a list answer, the steps of a path answer, 1 for one record."""
    if isinstance(value, list):
        return len(value)  # pyright: ignore[reportUnknownArgumentType]
    return len(value.steps) if hasattr(value, "steps") else 1


def check_reads(label: str, client: Any, *, need_rows: bool) -> dict[str, Any]:
    """Prints the row count of each read and returns the answers as plain data."""
    answers: dict[str, Any] = {}
    for method, call in reads(client).items():
        answer = call()
        rows = count(answer)
        if need_rows:
            need(rows >= 1, f"{label} {method} answered no rows")
        passed(f"{label} {method} {rows} rows")
        answers[method] = plain(answer)
    return answers


def raises_missing(call: Any) -> bool:
    try:
        call()
    except RecordNotFoundError:
        return True
    return False


def all_missing(client: Any) -> bool:
    return raises_missing(lambda: client.get_cwp(PROJECT, MISSING)) and raises_missing(
        lambda: client.get_wbs_node(PROJECT, MISSING)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", required=True, type=Path, help="the seed ledger (S4.py --keep)")
    args = parser.parse_args()
    source: Path = args.db
    need(source.exists(), f"{source} is missing; run dev/accept/P2-I1/S4.py --keep {source}")
    work = Path(tempfile.mkdtemp(prefix="t03b-"))
    try:
        db = work / "p2-i1.db"
        shutil.copy(source, db)

        # the embedded client, as the viewer
        embedded = EmbeddedClient.for_sqlite(db, actor=ACTOR)
        embedded_answers = check_reads("embedded", embedded, need_rows=False)

        # the fake, seeded with the shape of the seed
        fake = FakeClient()
        seed_awp(fake)
        check_reads("fake", fake, need_rows=True)

        # the API client, on the T03a routes over the same copy, signed in as the viewer
        tokens = work / "tokens.json"
        backend = open_backend(db)
        app = create_app(
            backend,
            settings=ApiSettings(db_path=db, tokens_path=tokens),
            tokens=TokenStore(tokens),
        )
        _, token = sessions.sign_in(backend, username=READER, password=PASSWORD)
        http = TestClient(app, raise_server_exceptions=False)
        api = ApiClient("http://testserver", token, http=http)
        api_answers = check_reads("api", api, need_rows=False)
        need(api_answers == embedded_answers, "the API answers differ from the embedded ones")
        passed("api answers equal embedded answers on the eight reads")

        first = embedded.list_cwps(PROJECT)[0].number
        same = plain(embedded.get_cwp(PROJECT, first)) == plain(api.get_cwp(PROJECT, first))
        need(same, f"embedded and API CWP {first} differ")
        passed(f"same CWP {first}")

        need(
            all_missing(embedded) and all_missing(fake) and all_missing(api),
            "a client did not raise RecordNotFoundError for NO-SUCH",
        )
        passed("missing")
        api.close()
        http.close()
        backend.close()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("T03b ok", flush=True)


if __name__ == "__main__":
    main()
