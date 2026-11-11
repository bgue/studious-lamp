# Runbook — install, try, deploy and connect the terminal release

Purpose: let a person install one release of the Throughline terminal app (`tl`, `tl-tui`), try it on the demo project,
run a real server, and connect a user, with no checkout. Design: `docs/tickets/P2-REL/README.md`. Accounts: `docs/runbooks/accounts-and-access.md`. Brief: §24.6.

Every step has an **Expected** line. Where the line was copied from a recorded run of the release smoke script
(`dev/release/smoke.sh`, ticket P2-REL-T05), the step says so. A line marked `(unverified)` was not run by anyone yet;
it is read from the code or the docs, and the first person who runs it must correct it.

## When to use
- Trigger: a person wants to try the terminal app; a team wants a server with real accounts; a new release is cut.

## Before you start
- Python **3.12** and `uv` on the machine. Other Python versions are not supported (see the table below).
- Linux, macOS 13 or later, or Windows 11 through WSL2 (the Linux install, run inside WSL2).
- Access needed: the release folder (wheels, `SHA256SUMS`, the starter bundle). For a real server, a Postgres 16 database and a host you control.
- Safe to run during business hours: yes. The try-it copy runs on your own machine only; never on a shared host.

## What is supported
Copied from `docs/tickets/P2-REL/README.md` (owner answer to R-1, 2026-11-08: the default table was accepted).

| Axis | Supported | Tested how, where |
|---|---|---|
| Release | One version for every package; the app and the server of the same `major.minor` talk; a different minor shows a warning at sign-in and is not supported; patch is free | T01, T02; unit tests |
| Install | `uv tool install tl-cli --find-links <release dir or URL>` from the release wheels; Python **3.12** only (3.13 and later are not claimed until a run says so) | T05 smoke, every run on Linux; macOS in CI (T07) |
| Platforms | Linux x86-64 and arm64, macOS 13 or later (Apple silicon and Intel), Windows 11 **through WSL2** (the Linux install, nothing native) | Linux: the whole suite and the smoke. macOS: smoke in CI only (T07; "best effort" until T07 has run green once). WSL2: manual, once, by the owner; not automated |
| Terminals | 256 colours, 80x24 or larger: GNOME Terminal, iTerm2, Windows Terminal (WSL2), kitty. Anything else: not refused, not supported | Textual snapshot tests at 80x24 and 120x40 (existing); a person on each named terminal once before the release is tagged |
| Server | Postgres 16 for shared use (several people, remote clients); SQLite only for one person on one machine (try-it and personal use), never behind `TL_ENV=prod` on a non-loopback bind | parity suite on touched dirs; T05 real-server path on Postgres 16 |
| Network | HTTPS to the server through a TLS proxy the deployer runs (ADR-0009: TLS in front is a deployment duty); the server itself speaks http; plain http only on loopback or with `TL_ALLOW_PLAIN_HTTP=1` | S2 tests |
| CLI | `tl` is an operator tool: it needs the ledger (SQLite file or Postgres URL), so it runs on the server host or with database credentials. Users who only have an account use the TUI | decision Q-REL2 |
| Accounts | Real accounts created with `tl admin bootstrap` and `tl admin user add`; the `demo` account and the dev token file never on a real server | Sec-1, Sec-4 |
| Data | New ledgers only; no migration from a dev ledger; a ledger made by a release opens with the same `major.minor` | Decision: no data migration |
| Fixes | The latest release only; no back-ports | policy |
| Not supported | native Windows, Python other than 3.12, Postgres other than 16, mixed minors, running the starter on a shared host, anything under `dev/` | |

## 1. Install

1. Get the release folder (the owner or the person who cut the release gives you the folder or its URL). It holds the
   `*.whl` files, `SHA256SUMS` and `starter-p200-<version>.tar.gz`. Replace `0.1.0` below with the release version.
   Expected: the folder lists the wheels, `SHA256SUMS` and the starter archive.

2. Check the files against the sums. In the release folder:
   ```
   sha256sum -c --quiet SHA256SUMS        # Linux and WSL2
   shasum -a 256 -c --quiet SHA256SUMS    # macOS
   ```
   Expected: no output and exit 0 (the smoke script runs this check first). Any line with `FAILED` means: do not install; ask for the folder again.

3. Install the release. Pin the version: PyPI has an unrelated project called `tl-cli` (version 0.2), and without the pin `uv` may pick it.
   ```
   uv tool install "tl-cli==0.1.0" --find-links /path/to/release
   ```
   Expected: `uv` installs `tl-cli` 0.1.0 and puts the `tl` and `tl-tui` commands on the path (unverified: the smoke script
   installs the same wheels with `uv venv` and `uv pip install`, not with `uv tool`).
   To force the interpreter, add `--python 3.12` to the same command (unverified).

4. Verify the version of both commands:
   ```
   tl --version
   tl-tui --version
   ```
   Expected: each prints `throughline 0.1.0` (recorded run of the release, and the smoke install step asserts the same version).

5. Upgrade to a newer release: put the new folder in place and install its pinned version again (unverified):
   ```
   uv tool install --force "tl-cli==0.2.0" --find-links /path/to/new-release
   ```
   Expected: `tl --version` prints the new version. The ledger is not changed by an install; a ledger keeps its `major.minor`.

6. Uninstall (unverified):
   ```
   uv tool uninstall tl-cli
   ```
   Expected: `tl` and `tl-tui` are no longer on the path. Your ledger files and the session file stay where they are.

**Python 3.12 note.** The release is tested on Python 3.12 only. A machine with 3.13 or later can fail in ways nobody has
checked. Use `uv` to get 3.12 (`uv python install 3.12`, unverified).

**WSL2 note.** On Windows, install WSL2 with a Linux distribution and do every step above inside that Linux shell. Native
Windows is not supported.

## 2. Try it on the demo project (your own machine only)

The starter bundle is the demo project P200 (North Refinery, Hydrotreater Unit 2) as one SQLite ledger, with its overlay
schema and `START.txt`. It listens on loopback only. It is a try-out, not a deployment.

1. Unpack the starter into a new folder. Reset means: delete the folder and unpack again.
   ```
   mkdir -p ~/throughline-try && tar -xzf /path/to/release/starter-p200-0.1.0.tar.gz -C ~/throughline-try
   cd ~/throughline-try
   ```
   Expected: the folder holds `START.txt`, `ledger/p200.db`, `ledger/files/` and `schema/`.

2. Read `START.txt`. It names the demo sign-in and the variables to set. Do not share it, and never use its values anywhere else.
   Expected: `START.txt` has at most 25 lines and a warning that the server listens on 127.0.0.1 only.

3. In the first terminal, in `~/throughline-try`, set the variables from `START.txt` and start the API. The line with the
   `export` is the one to copy; it sets the try-it object secret (public, for this bundle only).
   ```
   export TL_ENV=demo TL_PROJECT=P200 TL_DB=./ledger/p200.db TL_SCHEMA_DIR=./schema TL_OBJECT_ROOT=./ledger/files TL_OBJECT_SECRET=<the value from START.txt>
   tl serve
   ```
   Expected: the server runs and keeps running in this terminal. Stop it with Ctrl+C.

4. In a second terminal, check the server:
   ```
   curl -s http://127.0.0.1:8765/health
   ```
   Expected: `{"status":"ok","version":"0.1.0"}` (smoke try-it step: `/health` carries the release version).

5. In the second terminal, in `~/throughline-try`, with the same variables from step 3, open the app:
   ```
   tl-tui --remote http://127.0.0.1:8765
   ```
   Expected: the sign-in screen asks for a username and a password (unverified: the smoke script does not drive the screen).

6. Sign in as the project administrator named in `START.txt`, with the demo password from `START.txt`.
   Expected: the P200 logs fill in (unverified on the screen; the smoke script signs in as the same account and reads
   the P200 records route, `GET /records?scope=project:P200`, and gets 500 rows).

7. Read the ledger from the command line. This is a read; it needs no server:
   ```
   tl --db ./ledger/p200.db awp package ls --project P200
   ```
   Expected: the first line begins `packages:` with a count of 10 (recorded run; the command exits 0).

8. Stop the server with Ctrl+C in its terminal. Sign-out happens when you quit the app (Ctrl+Q); it ends the server session.
   Expected: the server process exits and the port stops answering (`curl -s http://127.0.0.1:8765/health` fails to connect)
   (unverified: the smoke script stops its server itself and does not press Ctrl+C).

**Never on a shared host.** The demo accounts have a known password. Run the try-it copy only on your own machine, on
loopback. Do not expose its port, and do not import its ledger into a real one.

## 3. A real server (for the person who deploys it)

The server runs behind a TLS proxy that you run. The server speaks plain http on a private address; the proxy speaks https
to users. TLS in front of the API is a deployment duty (ADR-0009, section 14 "Threat model" and section 15 "Release gates").
The plain-http refusal is enforced by the terminal app only: `tl-tui --remote` will not send a password or token over
plain http to a non-loopback host. Other clients of the API (the MCP server and any script using `ApiClient`) are not
guarded, so a real server must only be reachable through the TLS proxy.
ADR-0009 has no heading named "deployment duties"; sections 14 and 15 are the match, and the owner should confirm that
citation (open question in the T06 report).

1. **Prepare a Postgres 16 database** that is empty and new. Keep its URL out of shell history and out of command lines:
   store it in your secret store or in a file readable only by you, and load it into `TL_DB` (below).
   Expected: the database exists and has no tables yet.

2. **Set the environment.** Load `TL_DB` from your secret store (never type the URL as an argument to a command). Generate
   the object-store secret once and keep it in your vault; the public try-it value must never be used here. The server
   does not yet refuse that exact public value (S2 F1, a logged follow-up), so nothing enforces this rule: check the value
   yourself before you start the server.
   ```
   export TL_ENV=prod
   export TL_OBJECT_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
   ```
   Expected: `TL_ENV` is `prod`. The server refuses a non-loopback bind unless `TL_ENV` names a deployment; `dev`, `test`, `ci` and `demo` do not count. The server refuses to start without `TL_OBJECT_SECRET` when `TL_ENV` is `prod`.
   Never use the public try-it value from the starter bundle's START.txt here: the server does not yet refuse that exact
   value, so nothing stops a copy-paste (a follow-up will add the check).

3. **Create the schema.** Run it from a directory of your own, not from a checkout:
   ```
   tl init
   ```
   Expected: `tl init` finishes without an error (recorded run: "tl init on the new database" succeeded).

4. **Create the first admin.** Put the password in a file readable only by you and pass it on standard input, never as an argument:
   ```
   tl admin bootstrap --username boss --password-stdin < ~/boss.pw
   ```
   Expected: the account `boss` exists and is an admin (recorded run: boss signs in on the prod server).

5. **Bind and proxy.** Start the server on a non-loopback address, telling it which header your proxy writes:
   ```
   TL_TRUSTED_PROXY_HEADER=X-Forwarded-For tl serve --host 0.0.0.0 --port 8765
   ```
   Expected: the start-up log has one line `serving on 0.0.0.0:8765 behind TLS proxy: yes` (unverified: read from `tl_api.main`, not run). Your proxy must **overwrite** the header or **append** its peer address to it (accounts runbook, release gates).

6. **Refuse the unsafe form.** Without `TL_ENV`, a non-loopback bind must exit with status 2:
   ```
   tl serve --host 0.0.0.0
   ```
   Expected: exit status 2 and the text `refusing to bind` (recorded run).

7. **Check the dev token file is ignored.** A token from a dev token file must not authenticate on a prod server:
   ```
   curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer <a dev token>" "https://<your host>/records?scope=project%3AP200"
   ```
   Expected: `401` (recorded run).

8. **First account per person.** Create one account for each person on the server host with
   `tl admin user add <username>` (add `--display-name` and `--role` as needed); see `docs/runbooks/accounts-and-access.md`
   step 4 for the password rules. Agents get tokens, not passwords (step 5 of the same runbook).
   Expected: `tl admin user ls` lists each person and no `demo` account.

9. **Disable `demo`.** A server created with `tl init` has no demo account (recorded run: the account list has no `demo`).
   If one exists, disable it: `tl admin user disable demo --reason "real server"`.
   Expected: `demo` is absent from the list, or shown as disabled.

10. **Duties the server does not do for you** (ADR-0009, section 15, and `docs/runbooks/accounts-and-access.md` release gates):
    - a **front-door rate limiter** (your proxy, gateway or WAF) on `POST /auth/sign-in` and `POST /auth/password`, by client
      address, with an alert on a high failure rate;
    - **TLS** from users to your proxy;
    - the `TL_TRUSTED_PROXY_HEADER` setting above, so per-address limits see real clients;
    - an admin other than `demo` whose password is in your vault.

11. **Back up.** Choose the procedure that matches your database and follow it:
    - SQLite (one person only): `docs/runbooks/sqlite-backup-and-litestream.md`.
    - Postgres: `docs/runbooks/pgbackrest-restore.md`; a restore is drilled, not assumed.
    - Either: the ledger archive, `docs/runbooks/restore-from-archive.md`.
    Expected: a restore into a scratch database lists the same accounts and records as the source.

## 4. Connect as a user

1. Start the app with the server's HTTPS address:
   ```
   tl-tui --remote https://<your host>
   ```
   Or set the variables once: `TL_REMOTE=https://<your host>` and `TL_PROJECT=<project id>`.
   Expected: the sign-in screen asks for a username and a password (unverified on the screen; the server address is the one
   your admin gives you).

2. Sign in with your own account. The password is never echoed.
   Expected: the header shows the remote marker and your project's logs (unverified on screen).

3. **The version warning.** The sign-in screen compares the server's version with yours. Only a different `major.minor` gives a
   warning line, and then the pair is not supported:
   ```
   server is 0.2.x, this app is 0.1.x: not a supported pair
   ```
   Expected: that line, and only when the minors differ (unverified: unit-tested in `tl_tui.version_note`). A patch difference shows nothing.

4. **Sessions last 12 hours.** After that the server ends the session and the app asks you to sign in again.
   Expected: the sign-in screen returns after 12 hours (`docs/runbooks/accounts-and-access.md`, step 2).

5. **Sign out.** Quit the app with Ctrl+Q. Quitting ends the server session on every way out.
   Expected: the app exits and the session is closed on the server.

6. **Forgotten password.** You cannot reset it yourself. An admin resets it on the server host:
   ```
   tl admin user reset-password <your username>
   ```
   Expected: the reset is done and your sessions end (accounts runbook, step 4; the command never echoes a password). How the
   new password reaches you is the admin's business under your deployment's rules (unverified).

## 5. The CLI is an operator tool

The `tl` command reads and writes the ledger itself. It needs the ledger, a SQLite file or a Postgres URL, so run it on the
server host or from a machine with database credentials. Users who only have an account use `tl-tui`, not `tl`.

1. Sign in to a ledger (this is not a sign-in to a server):
   ```
   tl login <your username>
   ```
   Expected: the session is kept in a file with mode 600 under your user config directory (`TL_SESSION_FILE` sets another
   path), and `tl whoami` names your account (recorded run: the session file has mode 600 after `tl login`).

2. Sign out of the ledger: `tl logout`. Expected: the local entry is forgotten; if the server cannot be reached it says that the server session was not revoked.

## 6. Troubleshooting

| What you see | What it means | What to do |
|---|---|---|
| A red line "Server unreachable" under the header | The app cannot reach the server; it retries and resumes when the server answers | Check the address, check `curl -s https://<host>/health`, check the proxy. Expected: `{"status":"ok", ...}` |
| `error: refusing plain http to <host>: ...` and exit 2 | You gave an `http://` address for a host that is not loopback. The app will not send a password unencrypted. This refusal is enforced by the TUI only; other `ApiClient` users (for example the MCP server) are not guarded, so the operator must put the server behind TLS or a trusted proxy | Use `https://`. Only for a dev setup on your own network, `TL_ALLOW_PLAIN_HTTP=1` lets it through with a warning: `warning: <host> is plain http: ...`. Never use it for a real server |
| Locked out: "too many failed sign-ins" or the name is locked | After 5 failed sign-ins of a name within 15 minutes, the name is locked for 15 minutes | Wait 15 minutes, or an admin runs `tl admin unlock <name>` on the server host. An admin who is locked out uses `tl admin bootstrap` on the server host (accounts runbook, step 6) |
| Too small or no colour: the side panels are gone, or the screen is hard to read | Below 80 columns the panels become overlays (`F2` and `F3`). Colours need a 256-colour terminal | Make the window 80x24 or larger, use one of the named terminals. Anything else is not supported |
| `not a supported pair` at sign-in | The server and the app have different `major.minor` versions | Install the app of the server's version (section 1). Patch differences are fine |
| `error: not signed in` | A `tl` command needs a session and there is none | Run `tl login <your username>` first. A Postgres ledger always needs a session; `--actor` may name only you |

## 7. Release checklist (for whoever cuts a release)

Run these in a checkout of the release commit, from the repository root. Replace `0.1.0` with the release version.

1. Set the version everywhere: `dev/release/set_version.sh 0.1.0`.
   Expected: one line per package file, exit 0.
2. Build the wheels: `just release-build`.
   Expected: `build: 21 wheels in dist/release-0.1.0 (version 0.1.0)` (recorded run, release 0.1.0).
3. Check the wheels: `uv run python dev/release/check_wheels.py dist/release-0.1.0`.
   Expected: `OK 21 wheels` and exit 0. Any other line names a wheel and a problem; do not publish.
4. Build the starter: `just release-starter`.
   Expected: a line ending `starter-p200-0.1.0.tar.gz` (about 3.6 MB in the recorded run) and an entry in `SHA256SUMS`.
5. Run the smoke test: `dev/release/smoke.sh dist/release-0.1.0`.
   Expected: the lines `install: ok`, `try-it: ok`, `real-server: ok` (or `skip real-server: no Postgres` where no Postgres is
   set), `session-file: ok`, and `smoke: PASS` as the last line (recorded run).
6. One person runs the try-it steps on a named terminal (GNOME Terminal, iTerm2, Windows Terminal or kitty) and one person
   runs them on WSL2. Expected: the sign-in screen reads at 80x24 on each (manual; not automated).
7. Publish the release folder (the wheels, `SHA256SUMS` and the starter archive) to the place agreed with the owner. The
   default is a folder or release page used with `--find-links`; there is no PyPI upload and no signing (Q-REL1).
   Expected: the published `SHA256SUMS` matches the files you published (section 1, step 2).

## Verify
- `tl --version` and `tl-tui --version` print the release version.
- `curl -s https://<host>/health` answers `{"status":"ok","version":"<version>"}`.
- `tl admin user ls` shows your accounts and no `demo` account on a real server.

## Roll back
- A bad install: `uv tool install --force "tl-cli==<previous version>" --find-links <folder>`.
- A leaked password or token: accounts runbook, "Roll back" (`tl admin user reset-password`, `tl admin token revoke`).
- A wrong ledger: restore from the archive (`docs/runbooks/restore-from-archive.md`); do not edit events in place.

## Related
- `docs/tickets/P2-REL/README.md` (the plan and the definition of "supported"); `docs/adr/0009-authentication.md`
- `docs/runbooks/accounts-and-access.md`; `docs/runbooks/tui-dev.md` (keys and the remote mode);
  `docs/runbooks/demo-project.md` (the demo ledger for developers); `docs/runbooks/run-on-postgres.md`
- `docs/runbooks/sqlite-backup-and-litestream.md`, `docs/runbooks/pgbackrest-restore.md`, `docs/runbooks/restore-from-archive.md`
