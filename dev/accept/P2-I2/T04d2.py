"""Acceptance for P2-I2-T04d2: `tl awp readiness ls|show` through CliRunner. SQLite temp ledger.

Prints one ``PASS <check>`` per line and ends with ``T04d2 ok`` (or exits with ``FAIL <check>``).
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import s4_world as sw  # noqa: E402
import typer  # noqa: E402
from awp_world import hidden_record  # noqa: E402
from tl_cli.awp_readiness_read import register  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core.readiness.types import RecordRef  # noqa: E402
from tl_mod_awp import readiness as rd  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

ULID = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}")


def ok(name: str, cond: object = True) -> None:
    sys.exit(f"FAIL {name}") if not cond else print(f"PASS {name}")


def main() -> None:
    c2 = sw.c2_ready()
    w = sw.build(Path(tempfile.mkdtemp()) / "t04d2.db")
    if not c2:
        sw.fake_c2(w)
    hidden = hidden_record(w)  # a restricted correspondence item: the pinned document
    hidden_key = w.column("cur_core_record", "key", hidden) or "RFI-0001"
    a, b, c, h = (w.iwp(title=t) for t in ("Rack 12", "Rack 13", "Rack 14", "Rack hidden"))
    key = {i: w.column("cur_core_record", "key", i) for i in (a, b, c, h)}
    good, odd = sw.Stand("zz_doc", "ok"), sw.Stand("zz_odd", "n_a")
    pinned = sw.Stand("zz_pin", "blocked")
    pinned.refs = [RecordRef(record_id=hidden, record_type="x.Rfi", key=hidden_key)]
    sw.run(w, rd.evaluate_now, a, sw.TODAY, sw.checks(good, odd))
    sw.run(w, rd.evaluate_now, b, sw.TODAY, sw.checks(good, pinned))
    sw.run(w, rd.evaluate_now, h, sw.TODAY, sw.checks(good, odd))  # c is never evaluated

    app = typer.Typer()
    register(app)
    runner = CliRunner()

    def run(*args: str) -> tuple[int, str]:
        res = runner.invoke(app, ["readiness", *args, "--project", "P123"], obj=w.db)
        return res.exit_code, res.output

    _, out = run("ls")
    lines = out.splitlines()
    rows = lines[1:]
    ok("ls: count line and rows in number order", lines[0] == "readiness: 4" and len(rows) == 4
       and [r.split("  ")[0] for r in rows] == sorted(key.values()))  # fmt: skip
    ok(
        "ls: evaluated form",
        re.fullmatch(rf"{key[a]}  ready  \d+/\d+  \d{{4}}-\d\d-\d\d  -", rows[0]),
    )
    ok("ls: not evaluated form", rows[2] == f"{key[c]}  not evaluated  -/-  -  -")
    ok(
        "ls: blocked check names listed",
        rows[1].endswith("  constraints_cleared, zz_pin") and "  not ready  " in rows[1],
    )
    _, show_a = run("show", key[a])
    _, show_b = run("show", key[b])
    ok("show: n_a counts as passing", "zz_odd  n_a" in show_a and "checks  3/3" in show_a)
    ok("show: blocked check and its count", "zz_pin  blocked" in show_b and "checks  1/3" in show_b)
    ok("no facts_hash or record id in output", "facts_hash" not in out + show_a + show_b
       and not ULID.search(out + show_a + show_b))  # fmt: skip
    ok("hidden pinned document: no id or key in show",
       hidden not in show_b and hidden_key not in show_b)  # fmt: skip
    unknown = "P123-IWP-PIP-9999"
    errors = [run("show", unknown), run("show", key[c])]
    real_hidden = cf.is_hidden
    cf.is_hidden = lambda conn, rid, viewer=None: rid == h or real_hidden(conn, rid, viewer)
    try:
        errors.append(run("show", key[h]))
    finally:
        cf.is_hidden = real_hidden
    # The text names the IWP asked for, so compare the three with that number put in place.
    asked = (unknown, key[c], key[h])
    texts = [o.replace(n, "<n>") for n, (_, o) in zip(asked, errors, strict=True)]
    ok(
        "unknown, hidden and never-evaluated answer alike (exit 1)",
        len(set(texts)) == 1
        and all(code == 1 for code, _ in errors)
        and texts[0] == "error: no readiness for <n>\n",
    )
    ok("no Traceback", "Traceback" not in out + show_a + show_b)
    print("T04d2 ok")


if __name__ == "__main__":
    main()
