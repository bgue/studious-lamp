"""Acceptance for P2-QR-S3: the scan page. A signed-out visitor is bounced to sign-in, a signed-in
one gets the card or the one 404, a limited session gets the 429, the headers hold, and the access
log never shows a code. Exit 0, one ``PASS <check>`` line per check, then ``S3 ok``. SQLite only;
no network.

Run: ``uv run python dev/accept/P2-QR/S3.py``.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "tl-modules" / "qr" / "tests"))
os.environ.update(TL_ENV="test", TL_WEB_SECRET="accept-secret-0123456789abcdef-0123456789abc")

from fastapi.testclient import TestClient  # noqa: E402
from qr_world import PASSWORD, FakeProvider, World, providers_of  # noqa: E402
from tl_adapters.backend import open_backend  # noqa: E402
from tl_adapters.db import as_target, create_schema  # noqa: E402
from tl_api.app import create_app  # noqa: E402
from tl_api.main import install_access_log_filter  # noqa: E402
from tl_api.ratelimit import SourceLimiter  # noqa: E402
from tl_api.settings import ApiSettings  # noqa: E402
from tl_api.tokens import TokenStore  # noqa: E402
from tl_core.qr import registry  # noqa: E402
from tl_core.settings import resolver  # noqa: E402
from tl_mod_qr import service  # noqa: E402
from tl_web import scan_limit  # noqa: E402

OWN = "http://127.0.0.1"
BASE = "https://tl.example.com"


def passed(name: str) -> None:
    print(f"PASS {name}")


def need(ok: bool, what: str) -> None:
    if not ok:
        raise SystemExit(f"FAIL {what}")


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="qr-s3-"))
    target = as_target(str(work / "tl.db"))
    create_schema(target)
    world = World(target)
    world.people()
    registry.load_scan_cards = lambda *a, **k: providers_of(FakeProvider())  # type: ignore[assignment]
    real = resolver.value_of
    service.value_of = lambda conn, key, **kw: (  # type: ignore[attr-defined]
        BASE if key == service.BASE_URL else real(conn, key, **kw)
    )
    code = world.serve(service.issue, "uma", "IssueScanCode", target_id=world.record()).code
    backend = open_backend(target)
    settings = ApiSettings(db_path=work / "tl.db", tokens_path=work / "tokens.json")
    app: Any = create_app(
        backend,
        settings=settings,
        tokens=TokenStore(settings.tokens_path),
        source_limiter=SourceLimiter(10_000),
    )

    def client() -> TestClient:
        return TestClient(app, base_url=OWN, follow_redirects=False)

    out = client().get(f"/web/q/{code}")
    need(out.status_code == 303 and out.headers["location"].startswith("/web/sign-in"), "bounce")
    need(
        code in out.headers["location"] and "no-referrer" == out.headers["referrer-policy"], "next"
    )
    passed("signed-out bounce to sign-in with next")

    me = client()
    done = me.post(
        "/web/sign-in",
        data={"username": "uma", "password": PASSWORD, "next": f"/web/q/{code}"},
        headers={"Origin": OWN},
    )
    need(done.status_code == 303 and done.headers["location"] == f"/web/q/{code}", "return")
    me.headers["Cookie"] = "tl_session=" + done.headers["set-cookie"].split(";")[0].split("=")[1]
    passed("sign-in returns to the scan path")

    card = me.get(f"/web/q/{code}")
    need(
        card.status_code == 200 and "Fake card" in card.text and "<script" not in card.text, "card"
    )
    need(card.headers["referrer-policy"] == "no-referrer", "referrer")
    need(card.headers["cache-control"] == "no-store", "no-store")
    passed("signed-in card, no script, no-referrer, no-store")

    miss = me.get("/web/q/ZZZZZZZZZZZZZZZZ")
    odd = me.get("/web/q/short")
    need(miss.status_code == odd.status_code == 404 and miss.content == odd.content, "one miss")
    passed("every miss is the same 404")

    app.state.scan_misses = scan_limit.MissCounter(session_limit=3)
    for _ in range(3):
        me.get("/web/q/ZZZZZZZZZZZZZZZZ")
    limited = me.get(f"/web/q/{code}")
    need(limited.status_code == 429 and "retry-after" in limited.headers, "429")
    passed("a limited session gets 429 for a hit")

    seen: list[str] = []

    class Keep(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(self.format(record))

    access = logging.getLogger("uvicorn.access")
    access.addHandler(Keep())
    access.setLevel(logging.INFO)
    install_access_log_filter()
    access.info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", f"/web/q/{code}", "1.1", 200)
    need(len(seen) == 1 and code not in seen[0] and "/web/q/<redacted>" in seen[0], "log")
    passed("the access log never shows the code")
    print("S3 ok")


if __name__ == "__main__":
    main()
