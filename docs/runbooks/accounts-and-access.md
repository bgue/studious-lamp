# Runbook — accounts, sign-in and access

Purpose: create and manage accounts, roles and agent tokens, get back in after a lockout or a restore, and know what must be true before a deployment is real. Design: `docs/adr/0009-authentication.md`. Brief: §8, §11.1, §18.12.

## When to use
- Trigger: a new person, agent or leaver; a locked-out admin; a restore from the archive; a first real deployment; a question about who signed in.

## Before you start
- Roles are `admin` (everything, including the admin module), `document_controller` (a `user` who may also run the controlling acts of document control: issue, supersede and void, signed copies, transmittals, review corrections, `tl doc import --apply`; no `admin.*`; ADR-0013) and `user` (everything except `admin.*` and the controlling acts). An agent (`agent:<name>`) is never admin, never a document controller and always propose-only. Module roles, which decide what an account may do in one module of one project, are separate from these account roles: see "Module roles" under Steps and the [access words reference](../reference/access-words.md).
- Access needed: for `tl admin ...` and recovery, read and write access to the database (SQLite path or `postgresql://` URL) on the host. `tl login` keeps one session per ledger, keyed `db:<absolute path>` for a file and `pg:user@host:port/database[?options=sha256:...]` for Postgres (never a password; the schema scope is hashed; ADR-0009 addendum of P1-I0 workstream B); a Postgres ledger always needs a session, and `--actor` is honoured on it only when it is your own. `tl logout` ends the server session first; if the server cannot be reached it forgets the local entry and warns that the server session was not revoked. `tl sim` makes its agent on a Postgres ledger only for a signed-in admin. For the API, an admin session.
- Safe to run during business hours: yes. A password hash takes about a quarter of a second of CPU.
- **Trust boundary of the embedded modes (decision D3).** The embedded TUI and the CLI open the database directly. Whoever can read the file can read the password hashes and write rows; file permissions are the real boundary there, and sign-in only identifies the actor and applies the roles. Remote use goes through the API.

## Steps

### Sign in and out
1. Terminal: `uv run tl login <username>` (asks for the password without echo, or reads one line with `--password-stdin`; the session is kept in a file with mode 0600 under your user config directory, `TL_SESSION_FILE` overrides it, and lasts 12 hours), `uv run tl whoami`, `uv run tl logout`.
   The TUI (`uv run tl tui`) shows its own sign-in screen unless you are already signed in with `tl login`; with `--remote URL` it signs in to the server. `F10` opens the accounts screen for an admin. Every `tl` command then acts as you; `--actor` may name someone else only in a dev setup (`TL_ENV` dev, test or ci) on a ledger file; anywhere else, and for any `--db` that is a database URL, a command with no session stops with `error: not signed in`, and `--actor` must be your own.
2. API: `POST /auth/sign-in` with `{"username", "password"}` answers a token for `Authorization: Bearer`. It lives 12 hours. `POST /auth/sign-out` ends it; `POST /auth/password` changes your own password and ends every session.
3. After 5 failed sign-ins of a name within 15 minutes the name is locked for 15 minutes, for every name alike. From one address, 20 failures in 10 minutes give 429 `rate_limited`.

### Accounts (admin)
4. List, add, change, disable:
   ```
   uv run tl admin user ls
   uv run tl admin user add alice --display-name "Alice Smith" --role user
   uv run tl admin user roles alice --role admin --role user --reason "covers the admin desk"
   uv run tl admin user roles alice --add document_controller --reason "takes over document control"
   uv run tl admin user roles alice --remove document_controller --reason "moved to site"
   uv run tl admin user disable alice --reason "left the project"
   uv run tl admin user enable alice
   uv run tl admin user reset-password alice
   ```
   The same through `GET/POST /admin/accounts`, `PUT /admin/accounts/{id}/roles`, `POST /admin/accounts/{id}/disable|enable|password`, and in the TUI admin screen.
   `--role` replaces the roles; `--add` and `--remove` change one role and keep the others (not together with `--role`). The `document_controller` role goes to a person or a sim account, never an agent (`invalid_account`); only an admin grants or takes it, a document controller cannot change any role, her own included. The accounts screen (`F10`) gives or takes it with `c`. The grant is an `Account.RolesSet` event (who, why).
   The last active admin cannot be disabled or demoted (`last_admin`); the controller role has no part in that rule. A password has 12 to 128 characters and is refused when it is common or too simple; it is never echoed.
5. Agent tokens: an agent account has no password. Issue it a token (shown once; 90 days unless you say otherwise), list and revoke:
   ```
   uv run tl admin user add triage --kind agent
   uv run tl admin token issue triage --label "triage assistant"
   uv run tl admin token ls
   uv run tl admin token revoke <token id> --reason rotated
   ```
   The agent's host sets `TL_AGENT_TOKEN` for the MCP server.

### Locked out, or the admin password is lost (local access only)
6. See who is hammering which name, then clear the lock, or reset the admin's password (this works even though other admins have passwords, and ends the admin's sessions):
   ```
   uv run tl admin audit --limit 50
   uv run tl admin unlock boss
   uv run tl admin bootstrap --username boss
   ```
   There is no API route for these: an attacker who keeps every admin locked over HTTP cannot be helped over HTTP either.
7. A new database has no admin: `uv run tl admin bootstrap --username boss` creates one. It creates a new admin only while no active admin has a password.

### After a restore from the archive
8. Accounts come back from the ledger **without passwords and without agent token secrets** (they are never in the ledger). Nobody can sign in. The restore prints the commands: set the first admin's password with `tl admin bootstrap --username <admin>`, reset the others with `tl admin user reset-password`, and issue agents new tokens with `tl admin token issue`.

### The demo account
9. `just seed` and `tl init --dev` create `demo` / `demo` (role `admin`) in dev, demo and test setups only. In any other `TL_ENV` it does not authenticate, and the server refuses to start while it is enabled. Before real use: create your own admin, then `uv run tl admin user disable demo`.

### Upgrading an existing dev database
10. Run `uv run tl init` once (it is safe to repeat): it creates the account tables. A lake that already held account events is rebuilt once: see `docs/runbooks/lake-sync.md`, "After the accounts upgrade".

### Module roles
11. Module roles decide what an account may do in one module of one project. Only an admin grants or revokes them. The roles are:

    | Role | Words it holds | An agent may get it |
    |---|---|---|
    | `viewer` | `read` | yes |
    | `user` | `read`, `user` | yes |
    | `superuser` | `read`, `user`, `controller` | no |

    An explicit grant for that project and module replaces the role the account role would give. Without one, the account role gives a module role: `user` gives `user` in every module; `document_controller` gives `user` in every module and `superuser` in `documents`, `correspondence` and `schedule`. `admin` and `company` are platform words and cannot be granted.

    Grant a role. `--reason` is kept in the history. `--module *` means every module. `--project company` is the company scope: it reads company grants only for a module that declares company roles (materials, in Phase 2). Granting a role the account already holds changes nothing.
    ```
    uv run tl admin roles grant alice --project P1 --module documents --role superuser --reason "document controller on P1"
    ```
    Expected: the grant appears in step 12's list.

12. List the explicit grants, filtered if you like:
    ```
    uv run tl admin roles ls --project P1 --module documents
    uv run tl admin roles ls --user alice --json
    ```
    Expected: one row per explicit grant, with who, where, which role, who granted it and when.

13. Show what an account holds on a project, and where each role comes from:
    ```
    uv run tl admin roles effective alice --project P1
    ```
    Expected: one row per module, with the role held and whether an explicit grant or the account role gave it.

14. Revoke a grant. It takes the same `--project`, `--module`, `--role` and `--reason` as the grant:
    ```
    uv run tl admin roles revoke alice --project P1 --module documents --role superuser --reason "moved off P1"
    ```
    Expected: the grant is gone from step 12's list. Revoking a role the account does not hold is an error (`no_such_grant`, 404 over the API).

In the TUI, open the accounts screen with `F10` and press `m` to open the module roles log. The API routes are:

| Action | Route | Who |
|---|---|---|
| Grant | `POST /admin/accounts/{id}/module-roles` | admin |
| Revoke | `POST /admin/accounts/{id}/module-roles/revoke` | admin |
| List grants | `GET /admin/module-roles` | admin |
| Effective roles | `GET /admin/accounts/{id}/effective-roles?project` | admin |
| My roles | `GET /auth/me/roles?project` | any signed-in account |

Errors: `unknown_role` 422, `unknown_module` 422, `no_such_grant` 404, `no_company_roles` 422.

### What a grant does not change
- A `superuser` grant gives no restricted read (ADR-0016 is unchanged), and module roles do not filter reads.
- A grant does not change the account role. A proposal is accepted only when the accepter holds the account role and the module word.
- Grant events are hidden from `GET /events` for non-admins.
- Agents still only propose.

## Release gates (before anything that is not a developer's machine)
- [ ] **A front-door rate limiter** (reverse proxy, gateway or WAF) on `POST /auth/sign-in` and `/auth/password`, by client address, with an alert on a high failure rate. The server's own per-address limit is in memory and per process; it is a second layer.
- [ ] TLS in front of the API.
- [ ] `TL_ENV` is not `dev`, `demo` or `test`; the dev token file is absent; no enabled `demo` account.
- [ ] `TL_TRUSTED_PROXY_HEADER` names the header the proxy writes (for example `X-Forwarded-For`), if there is a proxy. The proxy must **overwrite** the header or **append** the peer address to it. The server uses the last entry of the last header line, so a proxy that only adds its own line is safe, and one that passes a client's line through after its own is not.
- [ ] Shared addresses are understood. The per-address limit counts IPv6 clients by their /64 and treats `::ffff:a.b.c.d` as that IPv4 address. Many people behind one NAT, or a proxy without `TL_TRUSTED_PROXY_HEADER` (every client then looks like the proxy), share one budget of 20 failures in 10 minutes: one person who fails 20 times blocks sign-in for all of them for the rest of the window (HTTP 429, `Retry-After`). Set the header, and size the front-door limiter for the real client addresses.
- [ ] A real admin exists and its password is in the operator's vault.

## Verify
- `uv run tl whoami` and `GET /auth/me` name the account and its roles.
- `uv run tl admin audit` shows your sign-in, and failed attempts per name with a count. It never shows a password or a token.
- `GET /admin/accounts` shows no hash; the ledger events `Account.*` and `AgentToken.*` hold metadata only.

## Roll back
- A wrong role or a disabled account: `tl admin user roles ...`, `tl admin user enable ...`. A leaked agent token: `tl admin token revoke`. A leaked password: `tl admin user reset-password` (ends the sessions).

## Related
- `docs/adr/0009-authentication.md`, `docs/adr/0008-phase1-owner-decisions.md`
- `docs/runbooks/restore-from-archive.md`, `docs/runbooks/lake-sync.md`, `docs/runbooks/api-and-mcp-dev.md`
