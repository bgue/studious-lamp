# ADR-0009 — Authentication, sessions, agent tokens and the admin roles

Status: accepted (approved by the orchestrator under ADR-0008 decision 6 after two fresh-context security reviews; the approval is logged in `docs/reports/APPROVALS.md`)
Date: 2026-10-11
Deciders: P1-I0A supervisor; approval by the orchestrator, logged in `docs/reports/APPROVALS.md`
Brief sections: §8 (identity and auth), §11.1 (auth), §18.12, §18.13; supersedes ADR-0005 for anything that is not dev or test

## Context
ADR-0005 gave Phase 0 a dev-only identity stub: static bearer tokens in a local file and an `authorize` hook that allows
everything. ADR-0008 decisions 2 to 5 replace it with username and password sign-in behind an identity seam, two roles
(`admin`, `user`), a seeded `demo` account in dev and demo setups only, and admin-issued service tokens for MCP agents.
The contract is `packages/tl-core/src/tl_core/auth/types.py` (frozen for P1-I0). This ADR fixes everything the contract
leaves open: the password KDF, the token formats, expiry and storage, the lockout and password policies, the timing and
enumeration rules, the Entra seam, how a restore treats accounts, and the threat model.

## Decision

### 1. Accounts, events and tables
- An account has a `username` (unique, case-insensitive), a `display_name`, a `kind` (`person`, `agent`, `sim`) and one
  or more roles from `admin`, `user`. Its actor string is `user:<username>` for `person` and `sim`, and `agent:<username>`
  for `agent`. Usernames match `[a-z0-9][a-z0-9_.@-]{0,63}` after NFKC normalisation and lower-casing; sign-in applies the
  same normalisation. Usernames are unique across kinds, so `user:x` and `agent:x` can never both exist.
- An `agent` account never has a password and can never hold the `admin` role. A `person` or `sim` account may have a password.
- Ledger events (metadata only, stream type `core.Account`, stream id `account:<account_id>`, scope `company`) are the
  ones the contract lists. They are projected into `cur_account` and `cur_agent_token`, which a rebuild may clear and refill.
- Operational tables hold every secret and every counter. They are created with the schema, are never rebuilt from the
  ledger, and are never read by the archive, the lake, the outbox or a webhook:

  | Table | Holds |
  |---|---|
  | `auth_credential` | the password hash, one row per account that has a password |
  | `auth_session` | the SHA-256 of each session token, its account, creation and expiry |
  | `auth_token_secret` | the SHA-256 of each agent token and its `token_id` |
  | `auth_attempt` | failed-sign-in counters and `locked_until`, keyed by normalised username |
  | `auth_audit` | the operational audit (section 12): who signed in, failed, locked, unlocked, signed out, and agent token issue and revoke; no secret; kept 90 days |
- Account events are internal. They contain no secret, but they list usernames and roles, so:
  - the webhook dispatcher never delivers a `core.Account` stream event;
  - the feed shows no card for them;
  - `GET /events`, `GET /stream` and the change feed filter them out for everyone but a human admin (`SubscriptionFilter.hide_stream_types`);
  - the product MCP server has no tool or resource that reads events, so no principal sees them there (a test pins the exact tool and resource lists);
  - **the default filter fails closed**: `SubscriptionFilter` hides the account streams unless its caller passes `hide_stream_types=()`, which only the events routes do, for a human admin. The embedded TUI's live feed, `tl events` and the change-feed registry therefore never show them;
  - the lake keeps a row for each, so `seq` stays gap-free, but it is redacted to `Internal.Redacted`: constant stream `internal` and version 1 (so it does not show how many accounts exist or how many events each has), a placeholder event id and hash, the day instead of the moment (day granularity is accepted: the lake shows that something happened on a day, never what or by whom), no actor and no payload. The lake's tip check walks back to the newest row that is not redacted. An existing dev lake keeps its older, richer rows (and time travel shows them) until it is rebuilt: `tl lake rebuild --yes` (the runbooks say so); there is no migration;
  - admins read accounts through `/admin/*`.

### 2. Password hashing
- The KDF is **scrypt from the standard library** (`hashlib.scrypt`). No dependency is added (ADR-0008 D5, ADR-0006).
  Parameters: N = 2^16, r = 8, p = 2 (64 MiB, the second OWASP-listed scrypt profile), 16-byte random salt from `secrets`,
  32-byte output, `maxmem` set explicitly to 2 x the need.
- The stored string is self-describing: `scrypt$<log2 N>$<r>$<p>$<salt b64>$<hash b64>` (URL-safe base64, no padding). Verification reads
  the parameters from the string and refuses any above **twice** what this process makes (one more bit of N, double r and p, of the larger of the configured and the production cost), so a tampered row cannot make the server allocate gigabytes.
  Parameters inside that bound that scrypt itself refuses (N too large for r) also count as a wrong password.
- A successful sign-in re-hashes the password when the stored parameters are weaker than the current ones (`needs_rehash`).
- At most 4 password hashes run at once in one process (4 x 64 MiB at most), of which sign-ins and self-service changes may hold 3; the fourth slot is kept for admin and local operations (create, reset, bootstrap, seed),
  so a sign-in flood cannot stop an admin. A hash waits at most 2 seconds for a slot, then `AuthBusyError` becomes HTTP 503 `auth_busy` with `Retry-After: 2`.
- **A hash never runs inside a write transaction**, because the writer lock is global and a held lock stalls every writer (review item 3). Sign-in verifies between two short transactions
  and computes a rehash before the write one. Services that store a password take a `PreparedPassword` (`prepare_password`: policy, then hash), which callers make before they open the unit of work.
- A stored hash made with weaker parameters than the current ones is verified at its own (cheaper) cost, so the time of a sign-in for such an account differs a little from one for an unknown name
  until the account's next successful sign-in rehashes it. This is accepted (review item 8f): it only exists during a cost upgrade.
- The password is NFKC-normalised, then UTF-8 encoded, before hashing. Tests pass cheap parameters (N = 2^4) through
  `ScryptParams`; the production default is the only value read at start-up.
- There is no pepper: a pepper that is lost or changed silently locks every account, and the database file is already
  the whole trust boundary (section 7). An Entra deployment removes passwords altogether.

### 3. Password policy
Applied by `prepare_password`, which every service that stores a password goes through; the seeded demo password is the one documented exception.
- 12 to 128 characters (after normalisation); no NUL, lone surrogate or other control character.
- Not equal to the username; not only spaces or invisible characters (Zs, Zl, Zp, Cf); at least 5 different characters.
- Not on the list of common passwords: `tl_core/auth/common_passwords.txt`, the 30,000 most common passwords of the zxcvbn-python package 4.5.0 (**MIT licence**, copyright 2016 Daniel Wolf, data only,
  the licence text is in the file header), plus product names. A value fails if it is on the list, or if it is a listed word of four or more letters with only digits and symbols around it (`Password1234!`).
  A larger breach list (10 million entries, for example an offline copy of a Have I Been Pwned range file) would catch more; that is a follow-up, as it needs a dependency or a large data file the owner has to approve.
- No composition rules and no forced rotation (NIST SP 800-63B). A violation is `WeakPasswordError` (422 `weak_password`)
  and says what is wrong without echoing the password.
- A person changes their own password through `sessions.change_own_password`, which checks the current password first and counts a wrong one towards lockout; an admin reset
  (`accounts.change_password`) does not need it and is recorded as `forced: true`. A password change or reset revokes every session of that account and clears its lock.

### 4. Sessions
- A session token is `tls_` followed by 32 random bytes from `secrets.token_urlsafe` (256 bits of entropy, 43 characters).
  The prefix lets a secret scanner and `principal_for_bearer` tell tokens apart; it carries no meaning for security.
- Only the SHA-256 of the token is stored (`auth_session.token_hash`). The token is high entropy, so a fast hash is correct,
  and a lookup by hash is an equality search on the index. The token is shown once, to the caller of `sign_in`.
- Lifetime: 12 hours absolute, no sliding renewal, so a request never writes. `sign_out` revokes the one session. Disabling an account,
  changing or resetting its password, and `sign_out_all` revoke all of its sessions. A role change takes effect at once because
  the principal is built from `cur_account` on every request, not copied into the session.
- Sign-out, disable and a password change delete the session rows at once; expired rows are deleted when the same account signs in again.

### 5. Agent tokens
- `tla_` followed by 32 random bytes (`token_urlsafe`). Stored as SHA-256 in `auth_token_secret`; returned once by
  `issue_agent_token`. Metadata (`AgentToken.Issued`: token id, account, label, expiry) is a ledger event; the token is not.
- An admin issues tokens for `agent` accounts only. A token may have an expiry; the CLI and the admin screen default to 90 days
  and need an explicit choice for none. Revocation is immediate. A token whose account is disabled does not authenticate.
- The principal of an agent token is `agent:<username>`, `via="agent_token"`. The propose-only rule (B15) is applied by the callers
  (`agent_must_propose` in the API, propose-only tools in MCP) whatever the agent's role; the `Authorizer` also refuses every `admin.*` action to an agent.

### 6. Lockout
- Counters are keyed by the **normalised username string, whether or not an account exists**, so an unknown name locks exactly like a real one
  and the response never tells them apart. A name that could not be a username (it does not match the username pattern, or has a NUL, a lone surrogate or too many characters) shares the single key `<invalid>`:
  whatever was typed there may be a password and is never stored, in the counters or in the audit.
- 5 consecutive failures within a 15-minute window lock the name for 15 minutes. **Every lock is 15 minutes, for every name, with no doubling** (review item 1): the requested cap for admins
  alone would have made the lock duration an oracle for which names are admins, and doubling for others for which names exist. At 5 guesses per name per 15 minutes a 12-character minimum is out of reach.
  A successful sign-in clears the counters.
- A locked name gets `AccountLockedError` (423 `account_locked`, with `locked_until`) before any password is checked, even with the right password.
- The check order is: locked? -> verify the password (always a full KDF run, see section 7) -> only then is a **disabled** account reported
  (`AccountDisabledError`, 403), so the status of an account is revealed only to someone who has its password.
- Counter rows with no failure for an hour and no lock in force are deleted whenever a failure is recorded, which bounds the table by the attack rate. It is indexed on `last_failed_at`.
- **Recovery from a held lock** (review item 1). An attacker can keep every named admin locked, so three local-only commands work on a database the operator can open and have no API route:
  `tl admin unlock <username>` clears a lock; `tl admin bootstrap --username <admin>` resets the password and the lock of an existing active admin even though admins with passwords exist;
  `tl admin audit` shows who is hammering which name. An admin password reset through the API also clears the lock.
- **A per-source limit sits in front of the per-name lockout** (`tl_api.ratelimit`, re-review condition): 20 failed sign-ins (401, 403 or 423) within 10 minutes from one client address, and the next `POST /auth/sign-in` is
  429 `rate_limited` with `Retry-After`, before any password is hashed or any row read. It defeats password spraying, which the per-name lockout cannot see, and the flat 15-minute lock. The address is the socket peer; behind a
  reverse proxy the deployment sets `TL_TRUSTED_PROXY_HEADER` (for example `X-Forwarded-For`) and the **last** entry of that header is used; without the setting the header is ignored, so a client cannot choose its address. The proxy must overwrite the header or append to it: the last line of the header, and its last entry, is used. IPv6 sources count by their /64, an IPv4-mapped IPv6 address counts as its IPv4 address, and a blocked source's recency is refreshed on every 429 so the 10,000-source bound drops quiet sources first. Sources sharing an address (NAT, or a proxy without the header) share one budget, which is a sign-in denial of service for that address by design; the runbook says so.
  It is in memory and per process (at most 10,000 sources), so it is a second layer: see section 15.

### 7. Constant time and enumeration
- Every sign-in attempt for an unknown name, an agent account, an account without a password, a disabled-looking wrong password or a wrong password runs one full scrypt against the stored hash or a
  random-salt stand-in of the current cost, so the time does not show whether the account exists.
- Input that cannot be hashed or stored (a NUL, a lone surrogate, more than 256 characters of username or 512 of password) is invalid credentials after the same one scrypt, with the same error, and writes nothing
  (Postgres rejects NUL in a parameter and would break the pooled connection). Usernames are never stripped: `" bob"` is not `bob`.
- Every service that takes text from a caller applies the same checks before a query: ids (account, token) of at most 64 clean characters, else not found; usernames for lookup and unlock; `reason` fields of at most 500
  clean characters without control characters, else `InvalidAccountError` (422). The path parameter `%00` or a reason with a surrogate therefore never reaches the database.
- The error for an unknown name and a wrong password is the same exception with the same text: `InvalidCredentialsError("invalid username or password")`.
- Comparisons of secrets use `hmac.compare_digest` on bytes (L-P0-I4-B6). Token lookup is by SHA-256 index equality; the token itself is never compared with a stored value.
- `principal_for_bearer` raises one `InvalidCredentialsError` for every bad token (unknown, expired, revoked, disabled account); the API answers 401 `unauthorized`. Sessions resolve only for
  non-agent accounts and agent tokens only for agent accounts, in the SQL.
- An open `GET /stream` re-resolves its token every 15 seconds and ends with a `closed` event when the token is signed out, revoked, expired or its account disabled, and no stream outlives 12 hours (review item 4).
- Request bodies on `/auth/*` are limited to 16 KiB and on `/admin/*` to 64 KiB (413 `payload_too_large`, counted while reading, before authentication). The authenticated principal is kept under a private ASGI scope key.
- No secret is logged, put in an error message, a `repr`, an event or a trace. `Principal`, `AccountView` and `AgentTokenView` carry none; a token appears only in the return value of
  `sign_in` and `issue_agent_token`, which callers hand to the user once and never store or log.
- Trust boundary of the embedded modes (decision D3): the embedded TUI and CLI open the database file directly and sign in against the local account store.
  Anyone who can read the file can read hashes and write rows, so file permissions are the real boundary; sign-in there identifies the actor for the ledger and
  applies the roles, it does not defend against the file's owner. Remote use goes through the API.
- **The CLI and TUI sessions (P1-I0 amendment, supervisor).** `tl login` signs in on the ledger file and keeps the session token in a file only its owner can read (`TL_SESSION_FILE`, default `~/.config/throughline/session.json`, mode 0600, one entry per ledger file; a file open to other users, damaged or unwritable is refused with the fix, never trusted). The token is never printed, logged or put in an exception. The default `--actor` of every embedded command is the session's account, checked against the ledger each time (an ended, expired or disabled-account session counts as none); without a session it is `user:dev` where `TL_ENV` is dev, test or ci and an error everywhere else. **An explicit `--actor` is honoured only when it is the session's own actor, or when `TL_ENV` is dev, test or ci and `--db` names a ledger file** (the file's owner can write the file anyway); the same check runs on the default and on a named value. Any `--db` with a `scheme://` (a database server, shared by many people) needs a valid session in every environment, so nobody can write as someone else there. Outside a dev setup `--actor user:root` without a session is `error: not signed in`. The session file is changed under an exclusive lock so concurrent logins keep each other's entries. The recovery commands write the OS user to the audit row (`tl admin unlock` as the actor `svc:cli:<os user>`, `bootstrap` in the detail). `tl admin user ...` and `tl admin token ...` need a signed-in admin so the history names who acted; `tl admin bootstrap`, `unlock` and `audit` and `tl init --dev` need none: they are the local recovery path. The embedded TUI signs in on its own screen (the process is the session; nothing is stored) unless `tl tui` passes the CLI session; the remote TUI signs in over `POST /auth/sign-in` and holds the 12-hour token in memory. The embedded client's admin calls refuse any actor that is not an active admin account whose own actor string equals the client's exactly (`svc:root` and `USER:ROOT` are not `user:root`; `ForbiddenError`), like the API's 403. The remote TUI ends its server session (`POST /auth/sign-out`) on every way out and the sign-in screen warns when the URL is plain http to a host that is not loopback.

### 8. Roster changes and the last admin
- `LastAdminError` (409) stops anyone disabling or demoting the last active `admin` person account (D4). Roster changes (create, roles, disable) count the active admins
  in `cur_account` (`is_admin`, `status`) inside their unit of work. Both adapters take the ledger's single writer lock when a write transaction begins, so two roster changes
  never interleave and two admins cannot disable each other at the same time. A test pins that, so a future finer-grained lock has to add its own guard.
- Bootstrap: `tl admin bootstrap --username <name>` works on the local database only (never over HTTP). For an existing active admin it sets the password, ends its sessions and clears its lock,
  whatever other admins have. For a new name it creates an admin, but only while no active admin has a password (a new database, or a restore). Anything else is refused.

### 9. Environments
- Dev tokens (`dev/data/tokens.json`, ADR-0005) are honoured only when `TL_ENV` is `dev`, `test` or `ci`. Unset or any other value refuses them, so a missing variable fails closed.
- `seed_demo` runs only for `dev`, `demo` or `test`. It creates `demo` with the role `admin` and the password `demo`, bypassing the password policy. It never changes an
  existing account. The username `demo` is reserved: `create_account` refuses it unless `TL_ENV` allows it.
- **The `demo` account does not authenticate, and its sessions stop working, unless `TL_ENV` is `dev`, `demo` or `test`** (review item 2): `authenticate` treats it as a wrong password after the usual hash,
  and `principal_for_bearer` rejects it. A server also refuses to start while an enabled `demo` account exists and `TL_ENV` is anything else, even on loopback behind a proxy, and refuses a
  non-loopback bind while it exists in any environment. Every start with it present in dev logs a warning.

### 10. Restore (D1)
A restore from the ledger archive rebuilds `cur_account` and `cur_agent_token` from events and finds no `auth_*` rows. Every restored account therefore has no password and every restored
agent token has no secret, so none can sign in. This is the same rule as webhook secrets. `restore_from_archive` returns a warning that names `tl admin bootstrap --username <name>`
for the first admin, then `tl admin user reset-password` for the rest and `tl admin token issue` for agents. Sessions are gone, which is also correct.

### 11. Authorization is closed for agents
`RoleAuthorizer` allows an `agent:*` principal only the actions in an explicit list (`tl_core.auth.provider.AGENT_ACTIONS`: reads, `auth.me`, `auth.sign_out`, the four feed commands, `proposal.accept` and `proposal.reject` so the service answers with its documented `proposal_decider`). The MCP server passes its own explicit list of tool and resource actions (`tl_mcp.identity.MCP_ACTIONS`); there is no `mcp.` prefix rule.
Everything else, including a route added later, is denied until someone adds it. The propose-only check (`agent_must_propose`) still runs first on the routes that change records, so an agent gets the specific code.
A test lists the action of every route and fails when one is undecided; another registers the real MCP server and fails on a tool or resource that is missing from, or stale in, its list.

### 12. The operational audit
`auth_audit` records `sign_in_ok`, `sign_in_failed`, `locked`, `unlocked`, `sign_out`, `token_issued`, `token_revoked`, `password_reset` and `bootstrap`, with the time, the name used (whether or not an account
exists), the account and actor when there are any, and a short code or id. It never holds a password, a hash or a token. Rows older than 90 days are deleted whenever a row is written. It is an operational table: not
in the ledger, the archive or the lake, and denied to the dev MCP `query_db`. `tl admin audit` lists it. Repeated failures of one name within 15 minutes share one row with a count, and the username column holds only a possible username (else `<invalid>`). A flood of distinct names still grows the table, bounded by the per-source limit and the retention.

### 13. The Entra seam
`IdentityProvider` is the only place credentials are judged, and `Principal` the only thing callers see. Entra ID (OIDC) replaces the password provider, not its callers:
- an `OidcIdentityProvider.principal_for_bearer(token)` validates an Entra access token (issuer, audience, expiry, signature from the tenant's JWKS), maps its `oid` claim to an
  account through a new event `Account.Linked {account_id, issuer, subject}`, and returns a `Principal` with `via="oidc"`; roles come from the account or from a group-to-role map;
- the API resolves bearer tokens through whichever provider the deployment configures (`TL_AUTH_PROVIDER`), so routes, the `Authorizer`, the admin module and the ledger events do not change;
- `authenticate_password` and `/auth/sign-in` are switched off in that configuration; agent tokens stay as they are because agents are not Entra users;
- Phase 1 builds none of that. It only guarantees that nothing outside `tl_core.auth` and the API's resolver reads the credential tables.

### 14. Threat model

| Threat | Mitigation | Residual risk |
|---|---|---|
| Offline guessing of stolen hashes | scrypt 64 MiB, 12-character minimum, common-password list | A weak but listed-safe password still falls to a long attack on a stolen file |
| Online guessing | 5-failure lockout of 15 minutes; constant-cost verification; one error text | Lockout can be used to deny a name; the local `tl admin unlock` and `bootstrap` get an admin back in |
| Password spraying (one password against many names) | the per-source limit (20 failures in 10 minutes, then 429 before any hash); the 12-character minimum and the common-password list; every attempt costs a full scrypt | The in-process limit is per process and per address; a front-door limiter is a release gate (section 15) |
| User enumeration by error, status code or time | one exception and text, full KDF always, unknown names locked like real ones, disabled status shown only after a correct password | A sign-in for a name that exists writes one row; the response is identical |
| Stolen session or agent token | 256-bit tokens stored only as SHA-256, shown once, 12 h session, expiry and instant revocation for agent tokens, revoke on disable and password change | A token in a captured request works until it ends; TLS in front of the API is a deployment duty |
| A database or backup leak | no plaintext secret anywhere; hashes in operational tables that archive, lake, outbox and webhooks never read | The hashes themselves leak with the file (see the guessing row) |
| Secrets in the ledger, logs or errors | events carry metadata only; tests scan the events, logs and error bodies for the password and token text | New code paths must keep the rule; reviewers check it |
| Privilege escalation | every route goes through the `Authorizer`; `admin.*` only for human admins; agents closed by default to an explicit list and always propose-only; last-admin check under the single writer lock | Two roles only; no per-record rules in Phase 1 |
| A session that outlives its token | open streams re-check every 15 s and end at 12 h | up to 15 s after sign-out or revocation |
| Account metadata read by users or agents | account events filtered from `/events`, `/stream`, the lake, MCP, webhooks and the feed | an admin sees them, by design |
| Race on the roster (create, demote, disable) | the ledger's single writer lock serialises write transactions on both adapters; a test fails if that changes | none known |
| Resource exhaustion by sign-in | at most 4 concurrent hashes with a 2 s wait then 503; hashing never inside a write transaction; 2x parameter bounds; length caps and body limits; counter and audit pruning | A flood of sign-ins still costs CPU and audit rows; a rate limiter in front is required |
| The demo account in a real deployment | seeded only for dev, demo or test; it does not authenticate and its sessions stop unless `TL_ENV` allows it; the server refuses to start with it enabled outside dev, demo and test, or on a non-loopback bind | An operator who sets `TL_ENV=dev` on a public host defeats it; the runbook says not to |
| A restore leaves accounts open | restored accounts have no password and no token secret | none: they are closed until an admin acts |
| Dev token file in production | honoured only for `TL_ENV` of `dev`, `test`, `ci` | same as the demo row |

### 15. Release gates

Before any deployment that is not a developer's machine:
1. **A front-door rate limiter** (reverse proxy, gateway or WAF) limits `POST /auth/sign-in`, and `/auth/password`, by client address and, for sign-in, alerts on a high failure rate. The in-process limit of section 6 is
   per process and in memory; several workers each keep their own count, and a restart clears it. It is a second layer, and the runbook (`docs/runbooks/accounts-and-access.md`) lists this as a gate.
2. TLS in front of the API: tokens and passwords travel in requests.
3. `TL_ENV` is not `dev`, `demo` or `test`; no `demo` account exists or it is disabled (the server refuses to start otherwise); the dev token file is absent.
4. `TL_TRUSTED_PROXY_HEADER` is set to the header the proxy writes, if there is a proxy.
5. An admin other than `demo` exists and its password is stored in the operator's vault.

## Consequences
- Contracts changed: `tl_core/auth/types.py` is implemented as frozen, except that the service signatures that store a password take a `PreparedPassword` (made before the unit of work opens) instead of a
  `str`, and `change_password` has no `current_password` (a self-change is `sessions.change_own_password`). Added beside it: `AuthBusyError` (503 `auth_busy`), `accounts.unlock`, `tl_core.auth.audit`, and `AccountNotFoundError` (404 `account_not_found`), `AgentTokenNotFoundError` (404 `agent_token_not_found`),
  `InvalidAccountError` (422 `invalid_account`) and `AccountStateError` (409 `account_state`) in `tl_core.auth.errors`, with rows in `tl_api/errors.py`. The `ForbiddenError` code `forbidden`
  moves from `HTTP_ERRORS` to the error table (same status and body). `ADMIN_ACTION_PREFIX` is the only admin rule the `Authorizer` knows.
- The `guard()` dependency resolves a `Principal` (dev token in dev or test, else `principal_for_bearer`) and calls the `Authorizer`; route signatures do not change. ADR-0005 stays in force for the dev-token path only.
- New schema: `schema/core/auth.yaml` (two projections, five operational tables, seven event classes). Tables in existing dev databases appear when `tl init` runs again.
- Gates affected: this ADR is the auth design approval ADR-0008 decision 6 delegates to the orchestrator.
- No new dependency.

## Alternatives considered
| Option | Why not |
|---|---|
| argon2id (`argon2-cffi`, MIT) | Slightly stronger default, but a native dependency that needs the licence gate and a wheel on every platform; scrypt at OWASP parameters is adequate and standard-library |
| bcrypt | 72-byte password limit and 4 KiB memory use; weaker against GPUs |
| PBKDF2-HMAC-SHA256 | Not memory-hard |
| JWT sessions | Cannot be revoked without a server list, which is the opaque-token design with extra steps; and key handling becomes a new secret to protect |
| Plain SHA-256 of passwords or a fast hash for tokens | A fast hash is correct for 256-bit random tokens, wrong for passwords; passwords use scrypt |
| Account lockout by IP | The service sees no address; left to the deployment's rate limiter |
| Failure counters only for existing accounts | Makes a locked account distinguishable from an unknown name (an enumeration oracle) |
| Secrets in ledger events, encrypted | Breaks the "ledger and archive hold no secret" rule and makes key management part of every restore |

## Addendum (P1-I0 WS-B), 2026-10-12: sessions and the simulator on a Postgres ledger
Status: accepted 2026-10-12 by the orchestrator under ADR-0008 decision 6 after a fresh-context security re-review (pass); proposed by the workstream B supervisor; logged in `docs/reports/APPROVALS.md`. It extends sections 4 and 7 and changes none of their rules. A ledger is now a `DbTarget`: a SQLite file or a `postgresql://` URL (`tl_adapters.db.as_target`).

1. **Session key.** The CLI keeps one stored sign-in per ledger (section 4). A file keeps its key, `db:<absolute path>`. A Postgres ledger is keyed `pg:user@host:port/database`, with the host in lower case and the port defaulting to 5432, and `?options=sha256:<first 16 hex of the SHA-256 of the options value>` when the URL scopes the schema with `options`. The key never holds a password, `sslmode` or any other parameter, and the options are hashed, so nothing written in them (a schema name) is stored in clear. The same ledger reached with another TLS mode or password therefore keeps one session; two users on one server, two databases or two schemas never share one.
2. **Query parameters are an allow-list.** `as_target` accepts only `sslmode`, `options` and `application_name` in a Postgres URL and refuses any other (`host`, `port`, `hostaddr`, `user`, `password`, `sslpassword`, `connect_timeout`...) with a fixed message that does not repeat the value. The driver would take `host=` and `port=` from the query string, so two servers could otherwise share one key (and one stored token), and it fails with a raw `TypeError` on the rest. `display_target` is an allow-list too: it shows `sslmode` and `application_name`, replaces every other value with `***` and always hides the password.
3. **A server is never a file the caller owns.** Section 7's rule holds on a `postgresql://` target without exception: a command needs a session even in a dev setup, and `--actor` is honoured only when it is the session's own actor. `tl logout` ends the server session first; if the server cannot be reached it forgets the local entry anyway and prints one warning line that the server session was not revoked (it ends when it expires).
4. **The simulator's agent on a server.** On a ledger file in a dev setup the operator mints the simulator's agent account and token as `svc:sim` (T11). On a Postgres ledger `TL_ENV=dev` alone is not enough: the simulator needs a signed-in **admin** session for that ledger (`tl login`), and the account and the token are made as, and attributed to, that admin. Without one, `tl sim` stops with its usual "no agent token" line and `TL_SIM_AGENT_TOKEN` (a token an admin issued) is the way in. Found by the security review of workstream B: a probe with `TL_ENV=dev`, no session and a Postgres schema had minted a live `tla_` token.
5. **Consequences.** Tests: `packages/tl-adapters/tests/test_backend.py`, `packages/tl-cli/tests/test_cli_auth_targets.py` and `test_cli_sim_agent_targets.py`. The runbook `docs/runbooks/accounts-and-access.md` states the key and the logout behaviour. No new dependency, no schema change.
