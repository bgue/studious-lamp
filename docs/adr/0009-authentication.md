# ADR-0009 — Authentication, sessions, agent tokens and the admin roles

Status: proposed (supervisor draft for P1-I0 workstream A; the orchestrator approves under ADR-0008 decision 6)
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
  | `auth_session` | the SHA-256 of each session token, its account, creation, expiry and revocation time |
  | `auth_token_secret` | the SHA-256 of each agent token and its `token_id` |
  | `auth_attempt` | failed-sign-in counters and `locked_until`, keyed by normalised username |
  | `auth_admin_gate` | one row that serialises roster changes (see section 8) |
- Account events are internal: the webhook dispatcher never delivers a `core.Account` stream event, the feed shows no card
  for them, and the events API hides them from non-admins. They contain no secret, but they list usernames and roles.

### 2. Password hashing
- The KDF is **scrypt from the standard library** (`hashlib.scrypt`). No dependency is added (ADR-0008 D5, ADR-0006).
  Parameters: N = 2^16, r = 8, p = 2 (64 MiB, the second OWASP-listed scrypt profile), 16-byte random salt from `secrets`,
  32-byte output, `maxmem` set explicitly to 2 x the need.
- The stored string is self-describing: `scrypt$<log2 N>$<r>$<p>$<salt b64>$<hash b64>` (URL-safe base64, no padding). Verification reads
  the parameters from the string and refuses any with N above 2^20, r above 16 or p above 16, so a tampered row cannot make the server allocate gigabytes.
- A successful sign-in re-hashes the password when the stored parameters are weaker than the current ones (`needs_rehash`).
- At most 4 password hashes run at once in one process (a semaphore), so a burst of sign-ins cannot exhaust memory (4 x 64 MiB).
- The password is NFKC-normalised, then UTF-8 encoded, before hashing. Tests pass cheap parameters (N = 2^4) through
  `ScryptParams`; the production default is the only value read at start-up.
- There is no pepper: a pepper that is lost or changed silently locks every account, and the database file is already
  the whole trust boundary (section 7). An Entra deployment removes passwords altogether.

### 3. Password policy
Applied by `create_account`, `change_password` and a reset; the seeded demo password is the one documented exception.
- 12 to 128 characters (after normalisation); no NUL or other control characters.
- Not equal to the username, not made of one repeated character, and not in a built-in list of the most common passwords.
- No composition rules and no forced rotation (NIST SP 800-63B). A violation is `WeakPasswordError` (422 `weak_password`)
  and says what is wrong without echoing the password.
- A person changes their own password by giving the current one; an admin reset does not need it and is recorded as `forced: true`.
  A password change or reset revokes every session of that account.

### 4. Sessions
- A session token is `tls_` followed by 32 random bytes from `secrets.token_urlsafe` (256 bits of entropy, 43 characters).
  The prefix lets a secret scanner and `principal_for_bearer` tell tokens apart; it carries no meaning for security.
- Only the SHA-256 of the token is stored (`auth_session.token_hash`). The token is high entropy, so a fast hash is correct,
  and a lookup by hash is an equality search on the index. The token is shown once, to the caller of `sign_in`.
- Lifetime: 12 hours absolute, no sliding renewal, so a request never writes. `sign_out` revokes the one session. Disabling an account,
  changing or resetting its password, and `sign_out_all` revoke all of its sessions. A role change takes effect at once because
  the principal is built from `cur_account` on every request, not copied into the session.
- Expired and revoked rows are deleted when a new session is created for the same account.

### 5. Agent tokens
- `tla_` followed by 32 random bytes (`token_urlsafe`). Stored as SHA-256 in `auth_token_secret`; returned once by
  `issue_agent_token`. Metadata (`AgentToken.Issued`: token id, account, label, expiry) is a ledger event; the token is not.
- An admin issues tokens for `agent` accounts only. A token may have an expiry; the CLI and the admin screen default to 90 days
  and need an explicit choice for none. Revocation is immediate. A token whose account is disabled does not authenticate.
- The principal of an agent token is `agent:<username>`, `via="agent_token"`. The propose-only rule (B15) is applied by the callers
  (`agent_must_propose` in the API, propose-only tools in MCP) whatever the agent's role; the `Authorizer` also refuses every `admin.*` action to an agent.

### 6. Lockout
- Counters are keyed by the **normalised username string, whether or not an account exists**, so an unknown name locks exactly like a real one
  and the response never tells them apart. The key is the first 64 characters.
- 5 consecutive failures within a 15-minute window lock the name for 15 minutes. Each further lock doubles the duration (30 min, 1 h, ... capped at 24 h).
  A successful sign-in clears the counters; a name with no failure for 24 hours also starts again at the shortest lock.
- A locked name gets `AccountLockedError` (423 `account_locked`, with `locked_until`) before any password is checked, even with the right password.
- The check order is: locked? -> verify the password (always a full KDF run, see section 7) -> only then is a **disabled** account reported
  (`AccountDisabledError`, 403), so the status of an account is revealed only to someone who has its password.
- Counter rows older than the window with no active lock are deleted whenever a failure is recorded, which bounds the table by the attack rate.
- An admin password reset clears the lock. `tl admin bootstrap --recover` (local access) also clears it, so an attacker who locks the only admin account
  cannot hold the system out for longer than the lock and a local operator is never stuck.
- Source-address throttling is not a service concern (the service sees no address). A deployment puts a rate limiter in front of `POST /auth/sign-in`; the runbook says so.

### 7. Constant time and enumeration
- Every sign-in attempt for an unknown name, an account without a password, or a wrong password runs one full scrypt against the stored hash or a fixed
  dummy hash with the current parameters, so the time does not show whether the account exists.
- The error for an unknown name and a wrong password is the same exception with the same text: `InvalidCredentialsError("invalid username or password")`.
- Comparisons of secrets use `hmac.compare_digest` on bytes (L-P0-I4-B6). Token lookup is by SHA-256 index equality; the token itself is never compared with a stored value.
- `principal_for_bearer` raises one `InvalidCredentialsError` for every bad token (unknown, expired, revoked, disabled account); the API answers 401 `unauthorized`.
- No secret is logged, put in an error message, a `repr`, an event or a trace. `Principal`, `AccountView` and `AgentTokenView` carry none; results that hold a
  token (`IssuedToken`) hide it from `repr`.
- Trust boundary of the embedded modes (decision D3): the embedded TUI and CLI open the database file directly and sign in against the local account store.
  Anyone who can read the file can read hashes and write rows, so file permissions are the real boundary; sign-in there identifies the actor for the ledger and
  applies the roles, it does not defend against the file's owner. Remote use goes through the API.

### 8. Roster changes and the last admin
- `LastAdminError` (409) stops anyone disabling or demoting the last active `admin` person account (D4). Roster changes (create, roles, disable) first update
  the single `auth_admin_gate` row, which serialises them on both databases, then check the count in `cur_account` (`is_admin`, `status`). Two admins cannot
  disable each other at the same time.
- Bootstrap: `tl admin bootstrap` works on the local database only (never over HTTP). When no active admin has a password it creates the first admin or, with
  `--recover <username>`, sets a password on an existing admin and clears its lock. When one exists it refuses.

### 9. Environments
- Dev tokens (`dev/data/tokens.json`, ADR-0005) are honoured only when `TL_ENV` is `dev`, `test` or `ci`. Unset or any other value refuses them, so a missing variable fails closed.
- `seed_demo` runs only for `dev`, `demo` or `test`. It creates `demo` with the role `admin` and the password `demo`, bypassing the password policy. It never changes an
  existing account. A server whose bind address is not loopback refuses to start while `demo` exists and is enabled; every start with it present logs a warning.

### 10. Restore (D1)
A restore from the ledger archive rebuilds `cur_account` and `cur_agent_token` from events and finds no `auth_*` rows. Every restored account therefore has no password and every restored
agent token has no secret, so none can sign in. This is the same rule as webhook secrets. `restore_from_archive` returns a warning that names `tl admin bootstrap --recover <username>`
for the first admin, then `tl admin user reset-password` for the rest and `tl admin token issue` for agents. Sessions are gone, which is also correct.

### 11. The Entra seam
`IdentityProvider` is the only place credentials are judged, and `Principal` the only thing callers see. Entra ID (OIDC) replaces the password provider, not its callers:
- an `OidcIdentityProvider.principal_for_bearer(token)` validates an Entra access token (issuer, audience, expiry, signature from the tenant's JWKS), maps its `oid` claim to an
  account through a new event `Account.Linked {account_id, issuer, subject}`, and returns a `Principal` with `via="oidc"`; roles come from the account or from a group-to-role map;
- the API resolves bearer tokens through whichever provider the deployment configures (`TL_AUTH_PROVIDER`), so routes, the `Authorizer`, the admin module and the ledger events do not change;
- `authenticate_password` and `/auth/sign-in` are switched off in that configuration; agent tokens stay as they are because agents are not Entra users;
- Phase 1 builds none of that. It only guarantees that nothing outside `tl_core.auth` and the API's resolver reads the credential tables.

### 12. Threat model

| Threat | Mitigation | Residual risk |
|---|---|---|
| Offline guessing of stolen hashes | scrypt 64 MiB, 12-character minimum, common-password list | A weak but listed-safe password still falls to a long attack on a stolen file |
| Online guessing | 5-failure lockout with growing duration; constant-cost verification; one error text | Lockout can be used to deny a name (bounded by section 6; the admin can reset it) |
| User enumeration by error, status code or time | one exception and text, full KDF always, unknown names locked like real ones, disabled status shown only after a correct password | A sign-in for a name that exists writes one row; the response is identical |
| Stolen session or agent token | 256-bit tokens stored only as SHA-256, shown once, 12 h session, expiry and instant revocation for agent tokens, revoke on disable and password change | A token in a captured request works until it ends; TLS in front of the API is a deployment duty |
| A database or backup leak | no plaintext secret anywhere; hashes in operational tables that archive, lake, outbox and webhooks never read | The hashes themselves leak with the file (see the guessing row) |
| Secrets in the ledger, logs or errors | events carry metadata only; tests scan the events, logs and error bodies for the password and token text | New code paths must keep the rule; reviewers check it |
| Privilege escalation | every route goes through the `Authorizer`; `admin.*` only for human admins; agents never admin and always propose-only; last-admin guard under a serialising row | Two roles only; no per-record rules in Phase 1 |
| Race on the roster (create, demote, disable) | the `auth_admin_gate` row serialises them on both databases | none known |
| Resource exhaustion by sign-in | at most 4 concurrent hashes; parameter bounds on stored hashes; password length cap; counter table pruning | A flood of sign-ins still costs CPU; a rate limiter in front is required |
| The demo account in a real deployment | seeded only for dev, demo or test; a non-loopback bind refuses to start while it is enabled; warning on every start | An operator who sets `TL_ENV=dev` on a public host defeats it; the runbook says not to |
| A restore leaves accounts open | restored accounts have no password and no token secret | none: they are closed until an admin acts |
| Dev token file in production | honoured only for `TL_ENV` of `dev`, `test`, `ci` | same as the demo row |

## Consequences
- Contracts changed: `tl_core/auth/types.py` is implemented as frozen. Added beside it: `AccountNotFoundError` (404 `account_not_found`), `AgentTokenNotFoundError` (404 `agent_token_not_found`),
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
