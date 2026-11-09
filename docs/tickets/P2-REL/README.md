# P2-REL — Terminal app release (TUI and CLI)

Roadmap item 2 (`docs/build-spec/roadmap-2026-11-07.md`). Owner constraints, 2026-11-07: packaging and install;
connecting to a real server with real accounts; a runbook; the demo project as the starter; security work only
where the release needs it (sign-in, token, server connection); say what "supported" means; cheapest tier; schema and
core-interface changes are the orchestrator's gate; no data migration; no PRs; no model names in committed files.
Everything else goes to `docs/build-spec/DEFERRED.md` (rows added with this plan).

## What is wrong today (found by reading the code, not guessed)
1. **A wheel install cannot work.** `tl_schema`, `tl_core.auth` and `tl_core.settings` find `schema/core`, `schema/fixtures`
   and `schema/settings/access-words.yaml` with `Path(__file__).parents[4|5]`. That only resolves inside a checkout.
   No `pyproject.toml` ships any data. So there is no installable release until the data travels with the wheels (S1).
2. **A real server cannot be started.** `check_bind` refuses any non-loopback host without `--insecure-dev` and says
   "the Phase 0 API has no real authentication", which is no longer true (ADR-0009). The only supported shape is
   loopback behind your own TLS proxy, and nothing says so; the TUI only warns about plain http (S2).
3. **The CLI has no remote mode.** Every `tl` command except `tl tui --remote` opens the ledger itself (`--db`, `TL_DB`);
   `tl login` signs in to a ledger, not to a server. For a real deployment the CLI is therefore an operator tool run
   on the server host, or with Postgres credentials. The TUI is the user client over HTTP. See Q-REL2.
4. **No version, no wheel build, no starter outside a checkout.** `0.0.1` everywhere, no `--version`, no build recipe,
   and the demo generator lives in `dev/` (not in any wheel).

## Objective
A person with Python 3.12 and `uv` and no checkout can: install one release; try it on the demo project (P200) on their own
machine; and, on a real deployment, sign in from the TUI to a server with their own account over TLS. The runbook says how.

## Demo clauses (the closing check, run by the orchestrator at DONE)
1. Fresh directory, fresh venv: `uv tool install tl-cli --find-links <release dir>` then `tl --version` and `tl-tui --version`
   print the release version; no checkout on `PYTHONPATH`.
2. **Try it:** unpack the starter bundle, `tl serve` on loopback with the bundle's ledger, `tl-tui --remote http://127.0.0.1:8765`
   shows the sign-in screen; the demo account signs in; the P200 logs (documents, correspondence, materials, IWPs) fill.
3. **Real server:** a new ledger on a Postgres URL, `tl admin bootstrap`, `tl serve` with `TL_ENV=prod` bound to a non-loopback
   address behind a proxy header setting; the dev token file and the demo account are refused; a TUI of another minor
   version shows the mismatch warning; plain http to a non-loopback host is refused unless explicitly allowed.
4. `just release-build` then `dev/release/check_wheels.py` ends `OK`: the wheel list holds no token file, database, `.gate`
   or demo password; every package carries its data.
5. The runbook `docs/runbooks/terminal-release.md` is followed top to bottom by someone who has not read the code (the
   owner or the orchestrator), and each step's "Expected" line is what they see.

## Order of work
Batch 1 (two heavy slots, disjoint paths): **S1** and **S2**. Batch 2 (after S1 merged for T01 and T03, after S2 for T02):
**T01, T03, T02**. Batch 3: **T04, T05** (wave 2 merge first, see below), then **T06**, and **T07** if the owner keeps it.
Nothing is dispatched this round: the orchestrator dispatches after the wave 2 close.

**Needs the wave 2 merge** (IWP and constraint CLI on the trunk): **T04** (the starter's awp and constraint sections are
the P2-SEED T01/T06 sections), **T05** (the smoke runs `tl awp` reads on the starter) and **T06** (the runbook names the IWP
log and `tl awp`). S1, S2, T01, T02, T03, T07 do not touch the IWP or constraint CLI and may start before the merge, but
branch from the trunk **after** the merge when it is already there, to avoid a second rebase of the pyproject files.

## Pieces and tickets
Sizes: S = builder piece (about 1 weekly point), H = Haiku ticket (about 0.25). Owner's estimate was 1 piece + 4 tickets;
this plan is 2 pieces + 7 tickets (about 3.75 points) because the two defects above are core and security work that
must not be a Haiku ticket. Cheapest cuts, in order: T07 (CI job), then T02 (version handshake). Cutting both gives
2 S + 5 H, about 3.25.

| Id | What | Tier | Size | Review | Depends on | Wave 2 | Gate |
|---|---|---|---|---|---|---|---|
| S1 | Installable wheels: one resource locator, data inside the wheels, five path constants moved onto it | builder | S | full | trunk | no | interface line (module `tl_schema.resources` is new) |
| S2 | Real server mode: bind policy, `TL_ENV=prod`, plain-http refusal, startup checks, tests | builder | S | full | trunk | no | security (auth path): human gate |
| T01 | One release version; `tl --version`, `tl-tui --version`; `dev/release/set_version.sh` | Haiku | H | lite | S1 | no | none |
| T02 | `/health` carries the server version; the TUI sign-in warns on a different minor | Haiku | H | full | S2 | no | interface line (`/health` adds a field; OpenAPI regenerated) |
| T03 | `just release-build` and `dev/release/check_wheels.py` | Haiku | H | full | S1, T01 | no | none |
| T04 | `just release-starter`: the P200 starter bundle (ledger, overlay schema, START.txt) | Haiku | H | lite | T03 | **yes** | none |
| T05 | `dev/release/smoke.sh`: clean venv, install, try-it path, real-server path | Haiku | H | full | S2, T03, T04 | **yes** | none |
| T06 | Runbook `terminal-release.md`, README and index lines, `tui-dev.md` pointer | Haiku | H | lite | T05 | **yes** | none |
| T07 | CI job `release-smoke` on Linux and macOS (YAML parsed only; cannot run here) | Haiku | H | lite | T05 | no | none |

Ticket count is 7 (under the 10 that would need `4 PLANCHK`).

## Security rows (release-only; the wider review stays in DEFERRED)
| Row | What must hold | Where | Proof |
|---|---|---|---|
| Sec-1 | A non-loopback bind is allowed only when `TL_ENV` is set to a value outside dev, test, ci and demo; then the dev token file is never read and the `demo` account must be absent or disabled, else the server does not start | S2 | tests: each `TL_ENV` value x bind x demo present |
| Sec-2 | The sign-in screen and `tl tui` refuse `http://` to a non-loopback host unless `TL_ALLOW_PLAIN_HTTP=1`; the refusal text never prints a token or password | S2 | test on `make_app`/`sign_in_first` |
| Sec-3 | A session token never reaches stdout, stderr, the process list, a log or an exception text on the connect, sign-in and sign-out paths of the TUI and `tl login` | S2 (tests), existing ADR-0009 tests | grep-style test over captured output |
| Sec-4 | `TL_TOKEN` and `--token` (dev and agent tokens) do not authenticate on a prod server unless the token is a real agent token | S2 | test against `create_app` with `TL_ENV=prod` |
| Sec-5 | The session file is mode 0600 and the directory is not world-readable; a file open to others is refused | existing `tl_cli.session` tests; a one-line check in T05 | smoke output |
| Sec-6 | No wheel or starter holds a token file, a `*.db` outside the starter, a signing key, or a password other than the documented demo one inside the starter | T03 (`check_wheels.py`), T04 | `OK` line |
| Sec-7 | Starter accounts exist only in the starter (`TL_ENV=demo`); the runbook says never to run it on a shared host | T04, T06 | runbook text, S2 Sec-1 refusal |
Deferred, not done: wider terminal security review, remote CLI sign-in, signed wheels, TLS inside the server.

## Proposed definition of "supported" (answer to R-1)
Default if the owner does not answer: the roadmap's recommendation, made testable and with each claim tied to a check.

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

## Owner questions (defaults apply unless answered)
| # | Question | Default |
|---|---|---|
| R-1 | What "supported" means | The table above |
| Q-REL1 | Where does a release live (a file share, a GitHub release page, a package index)? | A directory or release page of wheels plus `SHA256SUMS`, used with `--find-links`; no PyPI upload, no signing |
| Q-REL2 | May the CLI stay an operator tool (no remote mode) for this release? | Yes; a remote CLI is deferred (it needs a client over every command group) |
| Q-REL3 | Version number of the first release | `0.1.0` |

## Process notes
- Builders run what their spec names. S1 builds one wheel and lists it; it does not run the whole suite. Gates: `just check`,
  then `just gate <paths named in the spec>`. The orchestrator runs the per-folder run at DONE.
- `check_wheels.py`, `smoke.sh` and `set_version.sh` are shell and small Python; each has a test under `dev/tests/`.
- The supervisor wrote no code this round; no registry lines are needed (no new commands except flags).

## Plan check
Not requested: 2 pieces and 7 tickets, under the threshold in rule 8.
