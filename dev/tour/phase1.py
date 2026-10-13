"""The Phase 1 screenshot tour, interim: what P1-I0 to P1-I2 added to the platform core.

    uv run python dev/tour/phase1.py [--out docs/reports/tour/phase-1]

Same method as `phase0.py` (see its docstring and `tourkit.py`): a fresh SQLite ledger in a
temporary directory, the real TUI driven headless, the real `tl` commands, an MCP server and an API
client run in this process, SVG screenshots out. Every `tl` command here runs as a named person with
their own signed-in session (`demo`, an admin; `amy` and `ana`, plain users), the way the P1 demos
do. Passwords are the documented dev ones and are only ever typed through stdin.

It covers P1-I0 (identity and admin), P1-I1 (standards and engineering tags) and P1-I2 (document
control). The final Phase 1 tour extends it at the Phase 1 exit. The text is
`docs/reports/PHASE-1-TOUR.md`; its section numbers match the file names written here.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from pathlib import Path
from typing import Any

import tourkit as tk
from textual.pilot import Pilot
from textual.widgets import DataTable, Input, SelectionList
from tourkit import Shell, Transcript, Workspace, expect

REPO = Path(__file__).resolve().parents[2]
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
P = ("--project", PROJECT)
PASSWORDS = {  # made-up dev passwords for made-up people
    "demo": "demo",
    "amy": "a long passphrase for amy",
    "ana": "a long passphrase for ana",
    "ben": "a long passphrase for ben",
}
STANDARDS = "standards/co.acme.standards@1.0.0.yaml"
DOC_STANDARDS = "standards/co.acme.documents@1.0.0.yaml"
TAG_MAPPING = "templates/tag-list-instrument-index.yaml"
TAG_FILE = "legacy/instrument-index.csv"
DMS_MAPPING = "templates/document-register-dms-export.yaml"
DMS_FILE = "legacy/dms-document-register.csv"


# --- setup -----------------------------------------------------------------------------------


def stage_files(ws: Workspace) -> None:
    """Copy the sample standards, legacy files and mappings next to the ledger (short paths)."""
    for source, target in (
        ("schema/fixtures/standards", "standards"),
        ("dev/seed/legacy", "legacy"),
        ("dev/seed/templates", "templates"),
    ):
        shutil.copytree(REPO / source, ws.root / target)
    for name in "ABCD":
        (ws.root / f"sheet-{name}.pdf").write_text(f"%PDF-1.7 sheet {name}\n")


def password(who: str) -> str:
    return PASSWORDS[who] + "\n"


def add_person(ws: Workspace, name: str, display: str) -> None:
    ws.tl(
        "admin",
        "user",
        "add",
        name,
        "--display-name",
        display,
        "--password-stdin",
        stdin=password(name),
        who="demo",
    )


def sign_in(ws: Workspace, who: str) -> None:
    ws.tl("login", who, "--password-stdin", stdin=password(who), who=who)


def setup(ws: Workspace) -> None:
    """The ledger, the admin's session, and the two plain users. Not shown."""
    stage_files(ws)
    ws.tl("init", "--dev")
    sign_in(ws, "demo")
    add_person(ws, "amy", "Amy A")
    add_person(ws, "ana", "Ana B")
    sign_in(ws, "amy")
    sign_in(ws, "ana")
    tk.CLOCK.advance(minutes=30)


def build_app(ws: Workspace, *, admin: bool = False) -> Any:
    from tl_tui.main import build_app as make

    return make(ws.db, PROJECT, live=False, actor="user:demo", is_admin=admin)


# --- 01 sign-in ------------------------------------------------------------------------------


def section_sign_in(ws: Workspace) -> None:
    from tl_tui.embedded import EmbeddedAuthenticator
    from tl_tui.sign_in import SignInApp

    authenticator = EmbeddedAuthenticator.for_target(str(ws.db))
    app = SignInApp(authenticator, target="ledger ./tl.db", hint=authenticator.demo_hint())

    async def scenario(pilot: Pilot[Any]) -> None:
        await tk.settle(pilot, 4)
        tk.shot_tui(
            ws, app, "01a-sign-in", "Sign in to Throughline (TUI)", "Sign in to Throughline", "demo"
        )
        screen = app.screen
        screen.query_one("#sign-in-username", Input).value = "amy"
        screen.query_one("#sign-in-password", Input).value = "not her passphrase"
        await pilot.press("enter", "enter")  # username to password, then submit
        await tk.until(pilot, lambda: "invalid" in tk.screen_text(app).lower(), "the refusal")
        tk.shot_tui(
            ws,
            app,
            "01b-sign-in-refused",
            "A wrong password is refused, with no hint which half",
            "invalid username or password",
        )

    tk.run_tui(ws, app, scenario, size=(100, 30))

    sh = Shell(ws, "Sessions: who you are, and what that allows", 118)
    sh.note("each person has their own session file, as on their own machine")
    sh.run("whoami", who="amy")
    sh.run("admin", "user", "ls", who="amy", ok=False)
    sh.run("whoami", who="demo")
    sh.run("admin", "user", "ls", who="demo")
    ws.save("01c-sessions-cli", sh.transcript.svg())


# --- 02 accounts, roles and agent tokens -----------------------------------------------------


def section_accounts(ws: Workspace) -> str:
    """An admin adds a person and an agent and issues the agent a token; returns the token."""
    sh = Shell(ws, "Accounts and agent tokens, as an admin", 118)
    sh.run(
        "admin",
        "user",
        "add",
        "ben",
        "--display-name",
        "Ben C",
        "--password-stdin",
        stdin=password("ben"),
        who="demo",
        show="tl admin user add ben --display-name 'Ben C' --password-stdin",
    )
    sh.run("admin", "user", "add", "triage", "--kind", "agent", who="demo")
    issued = ws.tl("admin", "token", "issue", "triage", "--label", "triage assistant", who="demo")
    token = issued.splitlines()[0].strip()
    expect(token.startswith("tla_"), "no agent token was issued")
    sh.transcript.command("tl admin token issue triage --label 'triage assistant'", "demo")
    sh.transcript.output(tk.redact(issued, "tla_"))
    sh.run("admin", "token", "ls", who="demo")
    sh.run("admin", "user", "ls", who="demo")
    ws.save("02a-accounts-cli", sh.transcript.svg())

    app = build_app(ws, admin=True)

    async def scenario(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await pilot.press("f10")
        await tk.until(pilot, lambda: "triage" in tk.screen_text(app), "the accounts screen")
        tk.shot_tui(
            ws,
            app,
            "02b-admin-accounts",
            "F10: accounts and their roles (admins only)",
            "demo",
            "amy",
            "triage",
        )
        await pilot.press("t")
        await tk.until(pilot, lambda: "triage assistant" in tk.screen_text(app), "the tokens view")
        tk.shot_tui(
            ws,
            app,
            "02c-admin-tokens",
            "F10, t: agent tokens: label, expiry, state; never the token",
            "triage assistant",
        )

    tk.run_tui(ws, app, scenario)
    return token


# --- 03 lockout ------------------------------------------------------------------------------


def section_lockout(ws: Workspace) -> None:
    sh = Shell(ws, "Five wrong passwords lock the name", 118)
    for _ in range(5):
        sh.run("login", "ben", "--password-stdin", stdin="a wrong guess\n", who="ben", ok=False)
    sh.note("the sixth try uses the right passphrase and is still refused: the name is locked")
    sh.run("login", "ben", "--password-stdin", stdin=password("ben"), who="ben", ok=False)
    sh.run("admin", "user", "ls", who="demo")
    sh.run("admin", "audit", "--username", "ben", "--limit", "8", who="demo")
    sh.note("an admin on the machine clears it (there is deliberately no API for this)")
    sh.run("admin", "unlock", "ben", who="demo")
    sh.run("login", "ben", "--password-stdin", stdin=password("ben"), who="ben")
    ws.save("03-lockout", sh.transcript.svg())


# --- 04 an agent over MCP with a service token -----------------------------------------------


def section_agent(ws: Workspace, token: str) -> None:
    server, backend = tk.mcp_for_token(ws, token)
    t = Transcript("An agent with a service token: it proposes, a person decides", 118)
    try:
        t.comment("the host of the agent has the token in TL_AGENT_TOKEN; it is shown nowhere here")
        ws.tl("record", "create", *P, "--key", "FV-1002", "--title", "Reflux valve", who="amy")
        names = sorted(tool.name for tool in asyncio.run(server.list_tools()))
        for forbidden in ("accept_proposal", "reject_proposal"):
            expect(forbidden not in names, f"an agent has the tool {forbidden}")
        t.command("mcp tools/list   (as agent:triage)")
        t.output(" ".join(names))
        t.output("no accept_proposal, no reject_proposal: an agent cannot decide")
        t.blank()
        proposed = asyncio.run(
            tk.call_tool(
                server,
                "update_psets",
                record="FV-1002",
                scope=SCOPE,
                pset="valve_data",
                layer="standard",
                values={"size_in": 6, "manufacturer": "Acme Flow"},
            )
        )
        proposal = proposed["proposal"]
        t.command(
            'mcp tools/call update_psets {record: "FV-1002", pset: "valve_data", '
            'values: {size_in: 6, manufacturer: "Acme Flow"}}'
        )
        t.output(f"status: {proposal['status']}   by: {proposal['agent']}")
        t.output(proposed["message"])
        t.blank()
        pid = proposal["proposal_id"]
        for argv, who in (
            (("proposal", "ls", *P), "ana"),
            (("proposal", "accept", pid), "ana"),
        ):
            t.command("tl " + " ".join(argv), who)
            t.output(ws.tl(*argv, who=who))
        t.blank()
        t.comment("an admin revokes the token while the agent's MCP server is still running")
        tokens = ws.tl("admin", "token", "ls", who="demo")
        token_id = tokens.split()[0]
        t.command("tl admin token ls", "demo")
        t.output(tokens)
        t.command(f"tl admin token revoke {token_id}", "demo")
        t.output(ws.tl("admin", "token", "revoke", token_id, who="demo"))
        try:
            asyncio.run(tk.call_tool(server, "search_records", scope=SCOPE, q=""))
        except Exception as exc:  # noqa: BLE001 - the refusal is what the tour shows
            refusal = str(exc)
        else:
            raise tk.TourFailed("a revoked token still worked")
        expect("invalid or expired token" in refusal, f"unexpected refusal: {refusal}")
        t.blank()
        t.command('mcp tools/call search_records {scope: "project:P123"}   (the next call)')
        t.output(f"refused: {refusal}")
    finally:
        backend.close()
    ws.save("04-agent-service-token", t.svg())


# --- 05 the same services on Postgres (stored evidence) ---------------------------------------


def section_postgres(ws: Workspace) -> None:
    t = Transcript("Evidence kept from the P1-I0 gates (stored, not re-run by this tour)", 118)
    t.comment("figures copied from docs/reports/P1-I0.md; the tour itself uses SQLite only")
    t.command("just demo P1-I0")
    t.output("P1-I0 demo OK on: sqlite postgres")
    t.output("PASS 1 to 5 on each backend (the Postgres run uses a throw-away database)")
    t.command("just test-parity")
    t.output("3161 passed on SQLite and Postgres, 0 failed (1 h 0 min)")
    t.command("just test-tui")
    t.output("708 passed, 34 snapshots")
    ws.save("05-postgres-evidence", t.svg())


# --- 06 the standards registry ---------------------------------------------------------------


def section_standards(ws: Workspace) -> None:
    sh = Shell(ws, "The company standards registry", 118)
    sh.run("standards", "load", STANDARDS, "--dry-run", who="demo")
    sh.run("standards", "load", STANDARDS, who="demo")
    sh.run("standards", "load", STANDARDS, who="demo")
    sh.run("standards", "ls", "--kind", "code-list", who="amy")
    sh.run("standards", "values", "Area", who="amy")
    sh.run("standards", "class", "ls", who="amy")
    ws.save("06-standards-registry", sh.transcript.svg())
    ws.tl("standards", "load", DOC_STANDARDS, who="demo")


# --- 07 engineering tags ---------------------------------------------------------------------


def section_tags(ws: Workspace) -> None:
    sh = Shell(
        ws, "An engineering tag: parsed, checked against its class, renamed by supersession", 118
    )
    sh.run(
        "tag",
        "create",
        "47-FV-2001",
        "--class",
        "ControlValve",
        "--service",
        "Feed gas flow control",
        *P,
        who="demo",
    )
    sh.run("tag", "create", "47-XX-1", *P, who="demo", ok=False)
    sh.note("filling in the property set the class requires makes the tag conform")
    sh.run(
        "pset", "set", *P, "47-FV-2001", "valve_data", "manufacturer=Acme", "size_in=4", who="demo"
    )
    sh.run("tag", "show", "47-FV-2001", *P, who="demo")
    sh.run(
        "tag",
        "rename",
        "47-FV-2001",
        "47-FV-2002",
        "--reason",
        "renumbered by the design office",
        *P,
        who="demo",
    )
    sh.run("tag", "ls", *P, "--all", who="demo")
    ws.save("07-engineering-tags", sh.transcript.svg())


# --- 08 tag register and the legacy tag import -----------------------------------------------


def section_tag_import(ws: Workspace) -> None:
    sh = Shell(ws, "A legacy instrument index: preview, refuse, apply", 118)
    sh.run("tag", "import", TAG_FILE, "--mapping", TAG_MAPPING, *P, who="amy")
    sh.run(
        "tag",
        "import",
        TAG_FILE,
        "--mapping",
        TAG_MAPPING,
        *P,
        "--apply",
        "--skip-invalid",
        who="amy",
        ok=False,
    )
    sh.run(
        "tag",
        "import",
        TAG_FILE,
        "--mapping",
        TAG_MAPPING,
        *P,
        "--apply",
        "--skip-invalid",
        who="demo",
        tail=3,
    )
    sh.run("tag", "report", "summary", *P, who="amy")
    sh.run("tag", "report", "violations", *P, who="amy")
    ws.save("08a-tag-import", sh.transcript.svg())

    app = build_app(ws)

    async def scenario(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await pilot.press("f8")
        await tk.until(pilot, lambda: "47-FV-1001" in tk.screen_text(app), "the tag register")
        tk.shot_tui(
            ws,
            app,
            "08b-tag-register",
            "F8: the tag register: class, status, what each tag lacks",
            "47-FV-1001",
            "FV1009",
        )
        await pilot.press("v")
        await tk.until(pilot, lambda: "47-FV-1001" not in tk.screen_text(app), "violations only")
        tk.shot_tui(
            ws,
            app,
            "08c-tag-register-violations",
            "F8, v: only the tags that do not conform",
            "FV1009",
        )

    tk.run_tui(ws, app, scenario)


# --- 09 to 11 documents ----------------------------------------------------------------------


def section_documents(ws: Workspace) -> None:
    sh = Shell(ws, "Documents: a number pattern, revisions, a status class per revision", 118)
    sh.run(
        "doc",
        "register",
        "ISO-12",
        *P,
        "--title",
        "Too short",
        "--type",
        "ISO",
        "--discipline",
        "PIP",
        who="amy",
        ok=False,
    )
    sh.run(
        "doc",
        "register",
        "ISO-1234",
        *P,
        "--title",
        "Isometric, line 47-P-101",
        "--type",
        "ISO",
        "--discipline",
        "PIP",
        "--originator",
        "Acme Piping",
        who="amy",
    )
    ws.tl(
        "doc",
        "register",
        "ISO-2000",
        *P,
        "--title",
        "Isometric, line 47-P-102",
        "--type",
        "ISO",
        "--discipline",
        "PIP",
        who="amy",
    )
    # the tags 47-FV-1001 and 47-FV-1002 came with the legacy instrument index (section 8)
    sh.run("doc", "rev", "create", "ISO-1234", *P, "--purpose", "For review", who="amy")
    sh.run(
        "doc",
        "rendition",
        "add",
        "ISO-1234",
        "A",
        "sheet-A.pdf",
        *P,
        "--kind",
        "pdf",
        "--pages",
        "3",
        who="amy",
    )
    sh.run("doc", "rev", "issue", "ISO-1234", "A", *P, "--status", "IFR", who="amy", ok=False)
    sh.run("doc", "rev", "issue", "ISO-1234", "A", *P, "--status", "IFR", who="demo")
    ws.save("09a-documents-cli", sh.transcript.svg())


def section_stale(ws: Workspace) -> None:
    sh = Shell(ws, "A pinned link goes stale; the re-pin shows what changed first", 118)
    sh.run("doc", "link", "47-FV-1001", "ISO-1234", *P, "--pin", "A", who="amy")
    sh.run(
        "doc", "rev", "create", "ISO-1234", *P, "--purpose", "Issued for construction", who="amy"
    )
    ws.tl(
        "doc",
        "rendition",
        "add",
        "ISO-1234",
        "B",
        "sheet-B.pdf",
        *P,
        "--kind",
        "pdf",
        "--pages",
        "5",
        who="amy",
    )
    sh.run("doc", "rev", "issue", "ISO-1234", "B", *P, "--status", "IFC", who="demo")
    stale = sh.run("doc", "stale", *P, who="amy")
    link = stale.splitlines()[0].split()[-1]
    sh.run("doc", "repin", link, *P, who="amy")
    sh.run("doc", "repin", link, *P, "--apply", who="amy", tail=1)
    ws.save("10a-stale-and-repin", sh.transcript.svg())

    sh = Shell(ws, "The stale rule knows revision classes (ADR-0012)", 118)
    sh.run("doc", "link", "47-FV-1002", "ISO-1234", *P, "--pin", "B", who="amy")
    sh.run(
        "doc",
        "rev",
        "create",
        "ISO-1234",
        *P,
        "--purpose",
        "Review comments incorporated",
        who="amy",
    )
    ws.tl("doc", "rendition", "add", "ISO-1234", "C", "sheet-C.pdf", *P, "--kind", "pdf", who="amy")
    sh.note("C is issued for review (IFR) after B was issued for construction (IFC)")
    sh.run("doc", "rev", "issue", "ISO-1234", "C", *P, "--status", "IFR", who="demo")
    stale = sh.run("doc", "stale", *P, who="amy")
    expect(not stale.strip(), "an IFR issued after an IFC flagged the IFC pin")
    sh.note("nothing is stale: nobody builds from a review draft. Now D is issued for construction")
    sh.run("doc", "rev", "create", "ISO-1234", *P, "--purpose", "Final for construction", who="amy")
    ws.tl("doc", "rendition", "add", "ISO-1234", "D", "sheet-D.pdf", *P, "--kind", "pdf", who="amy")
    sh.run("doc", "rev", "issue", "ISO-1234", "D", *P, "--status", "IFC", who="demo")
    sh.run("doc", "stale", *P, who="amy")
    sh.run("doc", "show", "ISO-1234", *P, who="amy")
    ws.save("10b-class-aware-stale", sh.transcript.svg())


def section_transmittal_review(ws: Workspace) -> None:
    sh = Shell(ws, "A transmittal of exact revisions; a review with a deadline", 118)
    created = sh.run(
        "transmittal",
        "create",
        *P,
        "--subject",
        "Isometrics for construction",
        "--purpose",
        "for_construction",
        "--to",
        "Site Office:Acme Construction:site@example.com",
        "--revision",
        "ISO-1234@D",
        who="amy",
    )
    number = next(
        line.split()[-1] for line in created.splitlines() if line.startswith("created transmittal")
    )
    sh.run("transmittal", "issue", number, *P, who="amy", ok=False)
    sh.run("transmittal", "issue", number, *P, who="demo")
    sh.run("transmittal", "show", number, *P, who="amy")
    ws.save("11a-transmittal", sh.transcript.svg())

    sh = Shell(ws, "A review round: who has not answered, and how late", 118)
    ws.tl("doc", "rev", "create", "ISO-2000", *P, "--purpose", "First draft", who="amy")
    sh.run(
        "review",
        "open",
        "ISO-2000",
        "A",
        *P,
        "--reviewer",
        "user:ana",
        "--reviewer",
        "user:amy",
        "--due",
        "2026-10-01",
        who="demo",
    )
    sh.run("doc", "report", "overdue", *P, "--on", "2026-10-13", who="demo")
    sh.run(
        "review",
        "answer",
        "ISO-2000@A/RC1",
        *P,
        "--outcome",
        "approved_with_comments",
        "--comment",
        "check the weld map",
        who="ana",
    )
    sh.run("doc", "report", "overdue", *P, "--on", "2026-10-13", who="demo")
    ws.save("11b-review-overdue", sh.transcript.svg())


def section_register_tui(ws: Workspace) -> None:
    """The F7 register (a status class per revision), the re-pin dialog and the composer."""
    app = build_app(ws)

    async def scenario(pilot: Pilot[Any]) -> None:
        from tl_tui.widgets.document_register import DocumentRegisterScreen

        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await pilot.press("f7")
        await tk.until(pilot, lambda: "ISO-1234" in tk.screen_text(app), "the document register")
        screen = app.screen
        expect(isinstance(screen, DocumentRegisterScreen), "F7 did not open the register")
        table = screen.query_one("#docs-table", DataTable)
        table.move_cursor(row=[v.number for v in screen.shown].index("ISO-1234"))
        await tk.until(pilot, lambda: "IFC" in tk.screen_text(app), "the detail panel")
        tk.shot_tui(
            ws,
            app,
            "09b-document-register",
            "F7: the register; one current revision per status class",
            "ISO-1234",
            "IFR",
            "IFC",
            "construction",
        )
        await pilot.press("r")
        await tk.until(pilot, lambda: "Re-pin a stale link" in tk.screen_text(app), "the dialog")
        tk.shot_tui(
            ws,
            app,
            "10c-repin-dialog",
            "F7, r: the re-pin dialog shows the diff before it asks",
            "Re-pin a stale link",
            "ISO-1234",
        )
        await pilot.press("escape")
        await tk.settle(pilot, 4)
        await pilot.press("t")
        await tk.until(pilot, lambda: "New transmittal" in tk.screen_text(app), "the composer")
        composer = app.screen
        composer.query_one("#tc-subject", Input).value = "Isometrics for construction, rev D"
        composer.query_one("#tc-to", Input).value = "Site Office:Acme Construction:site@example.com"
        await tk.settle(pilot, 4)
        expect(len(composer.query_one("#tc-revisions", SelectionList).selected) == 1, "no tick")
        tk.shot_tui(
            ws,
            app,
            "11c-transmittal-composer",
            "F7, t: a transmittal draft with the current revision ticked",
            "New transmittal",
            "ISO-1234",
        )
        await pilot.press("escape")
        await tk.settle(pilot, 3)

    tk.run_tui(ws, app, scenario, size=(160, 48))


# --- 12 legacy DMS import --------------------------------------------------------------------


def section_dms_import(ws: Workspace) -> None:
    sh = Shell(ws, "A legacy DMS register: judged before anything is written", 118)
    sh.run("doc", "import", DMS_FILE, "--mapping", DMS_MAPPING, *P, who="amy")
    sh.run(
        "doc",
        "import",
        DMS_FILE,
        "--mapping",
        DMS_MAPPING,
        *P,
        "--apply",
        "--skip-invalid",
        who="amy",
        ok=False,
    )
    sh.run(
        "doc",
        "import",
        DMS_FILE,
        "--mapping",
        DMS_MAPPING,
        *P,
        "--apply",
        "--skip-invalid",
        "--job",
        "dms-2024",
        who="demo",
        tail=2,
    )
    sh.run("doc", "show", "ISO-0101", *P, who="amy", tail=14)
    ws.save("12-dms-import", sh.transcript.svg())


# --- 13 what a plain user cannot do ----------------------------------------------------------


def section_refused(ws: Workspace) -> None:
    sh = Shell(ws, "What a plain user (amy) is refused", 118)
    sh.note("amy has the role `user`: she registers, edits, links and drafts;")
    sh.note("controlling acts (issue, load standards, apply imports) are admin work")
    refused = (
        ("standards", "load", STANDARDS),
        ("doc", "rev", "issue", "ISO-1234", "D", *P, "--status", "IFC"),
        ("transmittal", "issue", "P123-TRN-0001", *P),
        ("tag", "import", TAG_FILE, "--mapping", TAG_MAPPING, *P, "--apply"),
        ("admin", "token", "ls"),
    )
    for argv in refused:
        sh.run(*argv, who="amy", ok=False)
    sh.note("the API refuses the same acts with 403, and no one, admin or not, can void a document")
    sh.note("through a generic command (tests/auth and the P1-I2 demo, clause 8)")
    ws.save("13-refused-acts", sh.transcript.svg())


# --- the tour --------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=REPO / "docs/reports/tour/phase-1")
    args = parser.parse_args(argv)
    out = args.out if args.out.is_absolute() else Path.cwd() / args.out
    for old in out.glob("*.svg"):
        old.unlink()
    tk.freeze()
    tk.fixed_archive_key()
    ws = Workspace(out)
    try:
        print("setting up the ledger and its people", flush=True)
        setup(ws)
        print("P1-I0: identity and admin", flush=True)
        section_sign_in(ws)
        token = section_accounts(ws)
        section_lockout(ws)
        section_agent(ws, token)
        section_postgres(ws)
        print("P1-I1: standards and tags", flush=True)
        section_standards(ws)
        section_tags(ws)
        section_tag_import(ws)
        print("P1-I2: document control", flush=True)
        section_documents(ws)
        section_stale(ws)
        section_transmittal_review(ws)
        section_register_tui(ws)
        section_dms_import(ws)
        section_refused(ws)
    finally:
        ws.close()
    print(f"wrote {len(ws.written)} screenshots to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
