"""Acceptance for P2-I1-T03a: the awp read routes, called as a person with a read role.

Copies the seed ledger ``.accept/p2-i1.db`` (written by ``S4.py --keep``) to a scratch file, builds
the API on the copy and signs in ``vera`` (the awp viewer). Each of the eight GET routes is called
once and prints ``PASS GET <path> 200 <n> rows`` (the detail prints its counts and timeline length).
A missing CWP and a made-up id answer 404 ``record_not_found`` with the same text template, an
unknown WBS code answers 404, a bad ``kind`` answers 422 and an anonymous call answers 401. Prints
``T03a ok`` at the end; exits 1 on the first failure. No network.

Run: ``uv run python dev/accept/P2-I1/T03a.py``.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from tl_adapters.backend import open_backend
from tl_api.app import create_app
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore
from tl_core.auth import sessions

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / ".accept" / "p2-i1.db"
PASSWORD = "correct horse battery"  # the S4 seed's password for every person
READER = "vera"  # the awp viewer grant in the S4 seed
PROJECT = "P123"
BASE = f"/projects/{PROJECT}/awp"
MADE_UP_ID = "01J0000000000000000000000Z"
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def passed(line: str) -> None:
    print(f"PASS {line}", flush=True)


def need(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL {message}", flush=True)
        sys.exit(1)


def error_of(response: Any) -> tuple[str, str]:
    body = response.json()
    return str(body["error"]), str(body["message"])


def get_ok(client: TestClient, path: str) -> Any:
    response = client.get(path)
    status = response.status_code
    need(status == 200, f"GET {path} answered {status}: {response.text}")
    return response.json()


def main() -> None:
    need(SOURCE.exists(), f"{SOURCE} is missing; run dev/accept/P2-I1/S4.py --keep {SOURCE}")
    work = Path(tempfile.mkdtemp(prefix="t03a-"))
    try:
        db = work / "p2-i1.db"
        shutil.copy(SOURCE, db)
        tokens = work / "tokens.json"
        backend = open_backend(db)
        app = create_app(
            backend,
            settings=ApiSettings(db_path=db, tokens_path=tokens),
            tokens=TokenStore(tokens),
        )
        _, token = sessions.sign_in(backend, username=READER, password=PASSWORD)
        client = TestClient(app, raise_server_exceptions=False)
        client.headers.update({"Authorization": f"Bearer {token}"})
        anonymous = TestClient(app, raise_server_exceptions=False)

        cwps = get_ok(client, f"{BASE}/cwps")
        passed(f"GET {BASE}/cwps 200 {len(cwps)} rows")
        need(len(cwps) == 6, f"the seed has 6 CWPs, saw {len(cwps)}")

        number = cwps[0]["number"]
        detail = get_ok(client, f"{BASE}/cwps/{number}")
        timeline = detail["timeline"]
        need(len(timeline) >= 1, "a released CWP has at least one event")
        need(all(set(row) == {"date", "who", "event", "note"} for row in timeline), "timeline rows")
        need(all(DATE.fullmatch(row["date"]) for row in timeline), "timeline dates")
        passed(
            f"GET {BASE}/cwps/{number} 200 links={detail['link_count']} "
            f"files={detail['file_count']} timeline={len(timeline)} rows"
        )

        cwas = get_ok(client, f"{BASE}/cwas")
        passed(f"GET {BASE}/cwas 200 {len(cwas)} rows")

        wbs = get_ok(client, f"{BASE}/wbs")
        passed(f"GET {BASE}/wbs 200 {len(wbs)} rows")

        node = get_ok(client, f"{BASE}/wbs/1.1.1")
        passed(f"GET {BASE}/wbs/1.1.1 200 1 rows (total_hours={node['total_hours']})")

        path = get_ok(client, f"{BASE}/path")
        passed(f"GET {BASE}/path 200 {len(path['steps'])} rows (version {path['version']})")

        versions = get_ok(client, f"{BASE}/path/versions")
        passed(f"GET {BASE}/path/versions 200 {len(versions)} rows")

        packages = get_ok(client, f"{BASE}/packages")
        passed(f"GET {BASE}/packages 200 {len(packages)} rows")

        bad_kind = client.get(f"{BASE}/packages", params={"kind": "XWP"})
        need(bad_kind.status_code == 422, f"bad kind answered {bad_kind.status_code}")
        passed(f"GET {BASE}/packages?kind=XWP 422 (validated before the view)")

        missing = client.get(f"{BASE}/cwps/P123-CWP-9999")
        made_up = client.get(f"{BASE}/cwps/{MADE_UP_ID}")
        for name, response, key in (
            ("missing CWP", missing, "P123-CWP-9999"),
            ("made-up id", made_up, MADE_UP_ID),
        ):
            code, message = error_of(response)
            need(response.status_code == 404, f"{name} answered {response.status_code}")
            need(code == "record_not_found", f"{name} error was {code}")
            need(message == f"no CWP {key!r}", f"{name} text was {message!r}")
        passed(f"GET {BASE}/cwps/<missing> 404 record_not_found, same text for a made-up id")

        no_node = client.get(f"{BASE}/wbs/9.9.9")
        code, _ = error_of(no_node)
        need(no_node.status_code == 404 and code == "record_not_found", f"wbs 9.9.9: {code}")
        passed(f"GET {BASE}/wbs/9.9.9 404 record_not_found")

        plain = anonymous.get(f"{BASE}/cwps")
        need(plain.status_code == 401, f"anonymous answered {plain.status_code}")
        passed(f"GET {BASE}/cwps without a token 401")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("T03a ok", flush=True)


if __name__ == "__main__":
    main()
