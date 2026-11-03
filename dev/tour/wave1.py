# ruff: noqa: E501 (the one-sentence captions of the gallery are long single strings)
"""The wave-1 preview tour: the web client and the new areas (awp, materials), ahead of the full tour.

    uv run python dev/tour/wave1.py [--out docs/reports/tour/wave1] [--only web,tui,cli]
    just tour wave1

Same method as `highlights.py` (see `tourkit.py`): a fresh SQLite ledger in a temporary directory,
the frozen clock, the real application. Three kinds of picture, written to one folder with an
`index.json` (file, title, caption; in order) a gallery page can be built from:

    web-NN-<slug>.png   the web client in Chromium (Playwright, through `wave1_web.mjs`): 1440x900,
                        and one at 390x844; `tl serve` runs on a free loopback port and the browser
                        signs in as a plain user
    tui-NN-<slug>.svg   the terminal client, headless, frozen clock: the awp registers and, once
                        built, the materials screens
    cli-NN-<slug>.svg   `tl` transcripts: awp reads and reports, the load targets, materials

A screen or command that does not exist on the branch being previewed is skipped with a printed
"not built yet: <name>", so the script keeps working while the branches advance. Playwright is a
Node package here; `node` and a Chromium (PLAYWRIGHT_BROWSERS_PATH) are needed for the web half.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import pkgutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import highlights as hl
import phase1 as p1
import tourkit as tk
from textual.pilot import Pilot
from textual.widgets import DataTable
from tourkit import Shell, TourFailed, Workspace

REPO = p1.REPO
P = p1.P
PROJECT = p1.PROJECT
AWP_STANDARDS = "standards/co.acme.awp@1.0.0.yaml"
COST_CSV = (
    "code,description,parent,uom,quantity_budget,quantity_actual,quantity_eac,hours_budget\n"
    "4210,Piping,,,1000,400,1100,5000\n"
    "4210-PIP,Pipe installation,4210,in-dia,600,450,600,3000\n"
    "4210-WLD,Welding,4210,,400,150,500,2000\n"
    "4220,Civil works,,,,,,\n"
    "4220-ERC,Erection,4220,,300,100,320,1800\n"
)
WEB_PASSWORD = p1.PASSWORDS["amy"]

# --- the shots index ---------------------------------------------------------------------------


@dataclass
class Entry:
    file: str
    title: str
    caption: str


INDEX: list[Entry] = []
SKIPPED: list[str] = []


def listed(file: str, title: str, caption: str) -> None:
    INDEX.append(Entry(file, title, caption))


def not_built(name: str) -> None:
    """A screen or command the previewed tree does not have yet."""
    print(f"not built yet: {name}", flush=True)
    SKIPPED.append(name)


# --- the world ---------------------------------------------------------------------------------


def text_pdf(path: Path, pages: int) -> None:
    """A PDF with a line of text on each page (stdlib only), so the page-1 image and the viewer
    show something to read."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(pages))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i in range(pages):
        objs.append(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {5 + 2 * i} 0 R /Resources << /Font << /F1 3 0 R >> >> >>"
        )
        body = (
            "BT /F1 26 Tf 72 700 Td (Isometric, line 47-P-103) Tj ET "
            f"BT /F1 14 Tf 72 664 Td (Sheet {i + 1} of {pages}. For review.) Tj ET "
            "0.4 w 72 640 468 1 re S"
        )
        objs.append(f"<< /Length {len(body)} >>\nstream\n{body}\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for n, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{obj}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def demo(ws: Workspace, *args: str) -> str:
    return ws.tl(*args, who="demo")


def awp_world(ws: Workspace) -> None:
    """Areas, a WBS with cost codes, five CWPs in different states, a path, two packages."""
    (ws.root / "cost.csv").write_text(COST_CSV, encoding="utf-8")
    demo(
        ws,
        "cost",
        "import",
        "cost.csv",
        *P,
        "--period",
        "2026-09",
        "--as-of",
        "2026-09-30",
        "--apply",
    )
    for code, title, where in (
        ("A", "Process area", "North yard"),
        ("B", "Pipe rack", "East side"),
        ("C", "Utilities", "South corridor"),
        ("D", "Tank farm", "West bund"),
    ):
        demo(ws, "awp", "cwa", "define", code, *P, "--title", title, "--location", where)
    for code, title, parent in (
        ("1", "Process unit", None),
        ("1.1", "Civil", "1"),
        ("1.1.1", "Foundations", "1.1"),
        ("1.1.2", "Pipe supports", "1.1"),
        ("1.2", "Piping", "1"),
        ("1.2.1", "Shop spools", "1.2"),
        ("1.2.2", "Field erection", "1.2"),
        ("2", "Electrical", None),
        ("2.1", "Cable trays", "2"),
    ):
        extra = ("--parent", parent) if parent else ()
        demo(ws, "awp", "wbs", "define", code, *P, "--title", title, *extra)
    demo(
        ws,
        "awp",
        "wbs",
        "map",
        "1.2.1",
        *P,
        "--cost-code",
        "4210-PIP:60",
        "--cost-code",
        "4210-WLD:40",
    )
    demo(ws, "awp", "wbs", "map", "1.2.2", *P, "--cost-code", "4210-WLD:100")
    demo(ws, "awp", "wbs", "map", "1.1.1", *P, "--cost-code", "4220-ERC:100")
    cwps = (
        # discipline, title, cwa, start, finish, hours, wbs, moves
        ("PIP", "Piping spool set A", "A", "2026-11-02", "2026-12-18", "1250", "1.2.1",
         ("start-development", "release")),
        ("PIP", "Underground piping, rack side", "B", "2026-11-16", "2027-01-29", "640", "1.2.2",
         ("start-development",)),
        ("CIV", "Foundations, process area", "A", "2026-10-19", "2026-12-04", "2100", "1.1.1",
         ("start-development", "release", "start-execution")),
        ("ELE", "Cable tray, rack R-2", "B", "2027-01-11", "2027-03-12", "480", "2.1", ()),
        ("CIV", "Pipe supports, utilities", "C", "2027-02-01", "2027-03-26", "900", None, ()),
    )  # fmt: skip
    numbers: list[str] = []
    for discipline, title, cwa, start, finish, hours, wbs, moves in cwps:
        out = demo(
            ws, "awp", "cwp", "create", *P, "--discipline", discipline, "--title", title,
            "--cwa", cwa, "--planned-start", start, "--planned-finish", finish,
            "--budget-hours", hours, "--contractor", "Acme Fab",
        )  # fmt: skip
        number = out.split()[-1]
        numbers.append(number)
        if wbs:
            demo(ws, "awp", "cwp", "allocate", number, *P, "--wbs", f"{wbs}:100")
        for move in moves:
            demo(ws, "awp", "cwp", "move", number, move, *P)
    demo(
        ws, "awp", "path", "define", *P, "--step", "A", "--step", "B", "--step", "C", "--step", "D"
    )
    demo(ws, "awp", "path", "move", "C", *P, "--to", "2", "--reason", "Access")
    demo(
        ws, "awp", "package", "record", *P, "--type", "ewp", "--number", "EWP-101",
        "--title", "Piping design, process area", "--no-constraint-source",
        "--status", "IFC", "--forecast", "2026-10-30",
    )  # fmt: skip
    demo(
        ws, "awp", "package", "record", *P, "--type", "pwp", "--number", "PWP-201",
        "--title", "Pipe and fittings purchase", "--no-constraint-source",
        "--status", "Ordered", "--forecast", "2026-11-27",
    )  # fmt: skip


def web_world(ws: Workspace, n: dict[str, str]) -> dict[str, str]:
    """What only the web pictures need: a draft RFI, a restricted one, a link, a thread."""
    draft = hl.raise_rfi(
        ws, "Door hardware schedule for the control room",
        "Which hardware set applies to doors D-12 to D-16?", "CIV", 20,
    )  # fmt: skip
    secret = hl.raise_rfi(
        ws, "Freight terms for the pump P-201 delivery",
        "Confirm the freight and demurrage terms for the pump delivery.", "MEC", 12,
    )  # fmt: skip
    ws.tl("rfi", "submit", secret, *P, who="amy")
    ws.tl("corr", "class", "set", secret, *P, "--to", "restricted", "--reason", "commercial terms",
          who="dora")  # fmt: skip
    ws.tl("link", "add", n["rfi"], hl.DOCUMENT, *P, "--relation", "references", who="amy")
    for key, value in (
        ("threads.enabled", "true"),
        ("threads.enabled_types", "correspondence.TechnicalItem"),
    ):
        demo(
            ws,
            "config",
            "set",
            key,
            value,
            "--company",
            "--reason",
            "the web preview reads threads",
        )
    ws.tl(
        "thread", "post", n["rfi"], "The beam moved in revision C; sketch attached.", *P, who="amy"
    )
    ws.tl("thread", "post", n["rfi"], "Noted. Reissued with the revised routing.", *P, who="dora")
    return {"draft": draft, "restricted": secret}


def build_world(ws: Workspace) -> dict[str, str]:
    p1.make_pdf = text_pdf  # type: ignore[assignment]  # the PDFs of the tour carry readable text
    print("building the world: people, standards, RFIs, letters, documents", flush=True)
    numbers = hl.world(ws)
    demo(ws, "standards", "load", AWP_STANDARDS)
    print("the web extras: a draft RFI, a restricted one, a link, a thread", flush=True)
    numbers.update(web_world(ws, numbers))
    print("the awp world: areas, WBS, CWPs, path, packages", flush=True)
    awp_world(ws)
    p1.renew_sessions(ws)
    return numbers


# --- the web -----------------------------------------------------------------------------------

WEB_SHOTS: tuple[Entry, ...] = (
    Entry("web-01-sign-in", "Sign in", "The sign-in page asks for a name and a password and nothing else."),
    Entry("web-02-rfi-log", "RFI log with the record panel", "The RFI log lists every RFI the person may see, and the panel beside it shows the selected one with the actions it offers."),
    Entry("web-03-rfi-details", "An RFI: Details", "The Details tab gives the question, the answer, the key facts and the timeline of one RFI."),
    Entry("web-04-rfi-properties", "An RFI: Properties", "The Properties tab lists the extra fields of the record and whether they meet the standard."),
    Entry("web-05-rfi-history", "An RFI: History", "The History tab lists every change to the RFI, newest first, with who made it."),
    Entry("web-06-rfi-links", "An RFI: Links", "The Links tab shows what the RFI points to and what points to it."),
    Entry("web-07-rfi-trace", "An RFI: Trace", "The Trace tab follows the links outward to show where the RFI leads."),
    Entry("web-08-rfi-thread", "An RFI: Thread", "The Thread tab reads the conversation on the RFI, oldest message first."),
    Entry("web-09-rfi-files", "An RFI: Files", "The Files tab lists the attachments with their kind, size and page count."),
    Entry("web-10-correspondence-log", "Correspondence log", "The correspondence log lists letters and emails in and out, with the selected letter in the panel."),
    Entry("web-11-document-log", "Document log with a page-1 image", "The document log shows the first page of a PDF revision beside its number, title and state."),
    Entry("web-12-pdf-viewer", "PDF viewer", "The viewer opens a PDF in the page, with page controls, without leaving the web client."),
    Entry("web-13-refusal", "A refused action", "An action that is not offered on a record is refused in plain words, and nothing changes."),
    Entry("web-14-hidden-404", "A hidden record", "A record the person may not see answers exactly as one that does not exist."),
    Entry("web-15-rfi-log-phone", "RFI log on a phone", "At phone width the RFI log stacks the list and the panel in one column."),
)  # fmt: skip


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def stop(proc: subprocess.Popen[bytes]) -> None:
    """Stop the server and its process group (it runs in its own, so nothing else is touched)."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=10)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()


def web_shots(ws: Workspace, n: dict[str, str], out: Path) -> None:
    node = subprocess.run(["which", "node"], capture_output=True, text=True).stdout.strip()
    if not node:
        for entry in WEB_SHOTS:
            not_built(f"{entry.file} (node is not installed)")
        return
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    log = ws.root / "server.log"
    env = {**os.environ, "TL_WEB": "on", "TL_PROJECT": PROJECT, "TL_ENV": "dev"}
    tl_bin = Path(sys.executable).parent / "tl"
    print(f"the server on {base}", flush=True)
    with log.open("wb") as handle:
        proc = subprocess.Popen(
            [str(tl_bin), "serve", "--port", str(port)],
            cwd=ws.root, env=env, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True,
        )  # fmt: skip
    try:
        for _ in range(300):
            try:
                with urllib.request.urlopen(f"{base}/health", timeout=1) as reply:
                    if b'"ok"' in reply.read():
                        break
            except OSError:
                time.sleep(0.1)
        else:
            raise TourFailed(f"the server did not start:\n{log.read_text()[-2000:]}")
        config = {
            "base": base, "user": "amy", "password": WEB_PASSWORD.strip(), "project": PROJECT,
            "out": str(out), "rfi": n["rfi"], "draft": n["draft"], "restricted": n["restricted"],
            "letter": n["reply"], "document": hl.DOCUMENT_B,
        }  # fmt: skip
        config_path = ws.root / "web-config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        node_env = {k: v for k, v in os.environ.items() if k != "NO_COLOR"}
        run = subprocess.run(
            [node, str(Path(__file__).with_name("wave1_web.mjs")), str(config_path)],
            capture_output=True, text=True, timeout=420, env=node_env,
        )  # fmt: skip
        print(run.stdout, end="", flush=True)
        if run.returncode != 0:
            raise TourFailed(f"the web script failed:\n{run.stderr[-2000:]}")
    finally:
        stop(proc)
    for entry in WEB_SHOTS:
        if (out / f"{entry.file}.png").exists():
            INDEX.append(Entry(f"{entry.file}.png", entry.title, entry.caption))
        else:
            not_built(entry.file)


# --- the terminal client -----------------------------------------------------------------------


def widget_class(name: str) -> Any | None:
    """A screen class of ``tl_tui.widgets`` by name, wherever it lives; ``None`` when not built."""
    import tl_tui.widgets as widgets

    for info in pkgutil.iter_modules(widgets.__path__):
        module = importlib.import_module(f"tl_tui.widgets.{info.name}")
        found = module.__dict__.get(name)
        if isinstance(found, type) and found.__module__ == module.__name__:
            return found
    return None


async def screen_shot(
    pilot: Pilot[Any], ws: Workspace, app: Any, screen: Any, name: str, title: str,
    cursor: str, *needles: str,
) -> None:  # fmt: skip
    await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
    app.push_screen(screen)
    await tk.until(pilot, lambda: cursor in tk.screen_text(app), f"the rows of {name}")
    table = app.screen.query_one("#log-table", DataTable)
    table.move_cursor(row=p1.row_with(table, cursor))
    await tk.settle(pilot, 4)
    tk.shot_tui(ws, app, name, title, cursor, *needles)


def tui_register(
    ws: Workspace, class_name: str, name: str, title: str, caption: str, cursor: str,
    size: tuple[int, int], *needles: str, record: tuple[str, str, str, str] | None = None,
) -> None:  # fmt: skip
    """One register at ``size``; with ``record = (name, title, caption, needle)`` also its record
    screen (Enter)."""
    cls = widget_class(class_name)
    if cls is None:
        not_built(f"{name} ({class_name})")
        return
    app = p1.build_app(ws, admin=True)

    async def scenario(pilot: Pilot[Any]) -> None:
        await screen_shot(pilot, ws, app, cls(app.client, PROJECT), name, title, cursor, *needles)
        if record is not None:
            from tl_tui.widgets.record_screen import RecordScreen

            await pilot.press("enter")
            await tk.until(pilot, lambda: isinstance(app.screen, RecordScreen), "the record screen")
            await tk.until(pilot, lambda: record[3] in tk.screen_text(app), record[0])
            tk.shot_tui(ws, app, record[0], record[1], record[3])

    tk.run_tui(ws, app, scenario, size=size)
    listed(f"{name}.svg", title, caption)
    if record is not None:
        listed(f"{record[0]}.svg", record[1], record[2])


def tui_shots(ws: Workspace, n: dict[str, str]) -> None:
    first = "P123-CWP-PIP-0001"
    tui_register(
        ws, "CwpRegisterScreen", "tui-01-cwp-register-wide",
        "CWP register, 170 columns",
        "The CWP register lists the construction work packages with state, area and hours; the highlighted one is described beside the list.",
        first, (170, 44), "Piping spool set A", "Released",
        record=(
            "tui-05-cwp-record", "A CWP record",
            "Enter on a CWP opens its record: allocation to the WBS, packages, activity links and timeline.",
            "Piping spool set A",
        ),
    )  # fmt: skip
    tui_register(
        ws, "CwpRegisterScreen", "tui-02-cwp-register-narrow",
        "CWP register, 100 columns",
        "At 100 columns the same register moves the panel below the list.",
        first, (100, 44), "Piping spool set A",
    )  # fmt: skip
    tui_register(
        ws, "WbsScreen", "tui-03-wbs-tree",
        "WBS tree",
        "The work breakdown structure is a tree of nodes with the cost codes mapped to each leaf.",
        "1.2.1", (170, 44), "Shop spools", "Field erection",
    )  # fmt: skip
    tui_register(
        ws, "CwaRegisterScreen", "tui-04-cwa-register",
        "CWA register",
        "The construction work areas appear in the order of the path of construction, with their CWPs.",
        "A", (170, 44), "Process area", "Tank farm",
    )  # fmt: skip
    # materials: whichever screens the tree has (stock, movements, receipts, items, take-off lines)
    for index, (cls, slug, title, caption) in enumerate(
        (
            ("StockScreen", "stock-log", "Stock log", "The stock log shows the balance by lot and location."),
            ("MovementLogScreen", "movement-log", "Movement log", "The movement log lists receipts, issues and transfers in ledger order."),
            ("ReceiptLogScreen", "receipt-log", "Goods receipts", "The receipt log lists goods receipts, newest first, and shows which lack a material test report."),
            ("ReceiptEntryScreen", "receipt-entry", "Receipt entry", "The receipt entry screen records what arrived against a purchase-order line."),
            ("ItemLogScreen", "item-log", "Item library", "The item library lists the company's items with the projects that adopted them."),
            ("MtoLogScreen", "mto-log", "Take-off lines", "The take-off log lists the quantities each work package needs and how much is covered."),
        ),
        start=6,
    ):  # fmt: skip
        name = f"tui-{index:02d}-{slug}"
        if widget_class(cls) is None:
            not_built(f"{name} ({cls})")
        else:  # the screen exists: seed its data and add the shot here (title and caption above)
            not_built(
                f"{name} ({cls} is built, the tour has no data for it yet: {title}, {caption})"
            )


# --- the command line --------------------------------------------------------------------------


def cli_shot(
    ws: Workspace, name: str, title: str, caption: str,
    commands: list[tuple[str, ...]], *, width: int = 120, head: int | None = 30,
) -> None:  # fmt: skip
    sh = Shell(ws, title, width)
    for argv in commands:
        sh.run(*argv, who="demo", head=head)
    sh.save(name)
    listed(f"{name}.svg", title, caption)


def cli_shots(ws: Workspace) -> None:
    cli_shot(
        ws, "cli-01-awp-cwp-ls", "tl awp cwp ls",
        "The CWPs of the project, one line each: number, state, discipline, area, hours and title.",
        [("awp", "cwp", "ls", *P), ("awp", "cwp", "show", "P123-CWP-PIP-0001", *P)],
    )  # fmt: skip
    cli_shot(
        ws, "cli-02-awp-wbs-tree", "tl awp wbs tree",
        "The WBS printed depth first, each level indented, with the cost codes of the leaves.",
        [("awp", "wbs", "tree", *P), ("awp", "wbs", "show", "1.2.1", *P)],
    )  # fmt: skip
    cli_shot(
        ws, "cli-03-awp-reports", "tl awp report",
        "The three awp reports: CWP status by state, WBS against cost code, and the area sequence.",
        [
            ("awp", "report", "cwp_status", *P),
            ("awp", "report", "wbs_vs_cost_code", *P),
            ("awp", "report", "cwa_sequence", *P),
        ],
    )  # fmt: skip
    cli_shot(
        ws, "cli-04-awp-path-and-packages", "tl awp path, cwa and package",
        "The path of construction with its versions, the work areas, and the engineering and procurement packages.",
        [
            ("awp", "path", "show", *P),
            ("awp", "path", "versions", *P),
            ("awp", "cwa", "ls", *P),
            ("awp", "package", "ls", *P),
        ],
    )  # fmt: skip
    cli_shot(
        ws, "cli-05-load-targets", "tl load targets",
        "The load targets the legacy loader knows, now including the awp and materials ones.",
        [("load", "targets")],
    )  # fmt: skip
    from tl_cli.main import app as cli_app

    groups = {g.name for g in cli_app.registered_groups}
    found = next((g for g in ("materials", "mat") if g in groups), None)
    if found is None:
        not_built("cli-06-materials-stock (tl materials)")
        not_built("cli-07-materials-receipts (tl materials)")
        return
    for name, title, caption, verbs in (
        ("cli-06-materials-stock", f"tl {found} stock", "The stock balances by lot and location.", [("stock", *P)]),
        ("cli-07-materials-receipts", f"tl {found} receipts", "The goods receipts, newest first.", [("receipt", "ls", *P)]),
    ):  # fmt: skip
        try:
            cli_shot(ws, name, title, caption, [(found, *v) for v in verbs])
        except TourFailed as exc:
            not_built(f"{name} (the command failed: {str(exc).splitlines()[0]})")


# --- main --------------------------------------------------------------------------------------


def write_index(out: Path) -> None:
    order = {"web": 0, "tui": 1, "cli": 2}
    ordered = sorted(INDEX, key=lambda e: (order[e.file[:3]], e.file))
    rows = [{"file": e.file, "title": e.title, "caption": e.caption} for e in ordered]
    (out / "index.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=REPO / "docs/reports/tour/wave1")
    parser.add_argument("--only", default="web,tui,cli", help="comma list of web, tui, cli")
    args = parser.parse_args(argv)
    out = args.out if args.out.is_absolute() else Path.cwd() / args.out
    only = {part.strip() for part in args.only.split(",") if part.strip()}
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    if only == {"web", "tui", "cli"}:
        for old in (*out.glob("*.svg"), *out.glob("*.png"), *out.glob("index.json")):
            old.unlink()
    tk.freeze()
    tk.fixed_archive_key()
    ws = Workspace(out)
    steps: dict[str, Callable[[dict[str, str]], None]] = {
        "web": lambda n: web_shots(ws, n, out),
        "tui": lambda n: tui_shots(ws, n),
        "cli": lambda n: cli_shots(ws),
    }
    try:
        numbers = build_world(ws)
        for name, step in steps.items():
            if name in only:
                print(f"== {name}", flush=True)
                step(numbers)
    finally:
        ws.close()
    write_index(out)
    counts = {kind: sum(e.file.startswith(kind) for e in INDEX) for kind in ("web", "tui", "cli")}
    print(f"wrote {counts['web']} web, {counts['tui']} tui, {counts['cli']} cli to {out}")
    for name in SKIPPED:
        print(f"skipped: {name}")
    print(f"took {time.monotonic() - started:.0f} s")
    return tk.report_leaks()


if __name__ == "__main__":
    sys.exit(main())
