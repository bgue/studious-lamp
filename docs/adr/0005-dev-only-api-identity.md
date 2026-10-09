# ADR-0005 — Dev-only API identity for Phase 0; the real auth model stays a human gate

Status: accepted
Date: 2026-10-09
Deciders: orchestrator (autonomous run), for owner review
Brief sections: §8 (identity and auth, authorisation), §11.1 (auth), §18.13; build spec 04-gates.md §2

## Context
P0-I4 adds a REST API, SSE stream and MCP server that need an actor identity on every command (§5.1 `actor`).
The authentication and permission model (OIDC/SAML, RBAC + ABAC, confidentiality filters) is a human gate (04-gates.md
§2) and the KICKOFF delegation does not cover it. The run must not stall on it, and it must not ship anything that
looks like an auth model.

## Decision
Phase 0 servers use a **dev-only identity stub**, not an auth model:
1. Identity: static bearer tokens read from a local file (`dev/data/tokens.json`, created by `tl dev token add <actor>`),
   mapping token → actor string (`user:<id>` or `agent:<id>`). A missing or unknown token is HTTP 401. MCP over stdio
   uses an actor passed on the command line.
2. Authorisation: none. Every authenticated actor may call every endpoint. Code paths go through a single
   `authorize(actor, action, resource) -> None` hook that allows everything, so the real model can replace one function.
3. Exposure: servers bind `127.0.0.1` by default and refuse a non-loopback bind unless started with `--insecure-dev`,
   which logs a warning on every request. Nothing in Phase 0 is deployable.
4. MCP write tools stay propose-only (§11.3, §18.12) and are out of P0-I4 scope (P0-I6).

## Consequences
- P0-I4 and later increments can build and test API, SSE and MCP surfaces end to end.
- No password storage, sessions, roles, or ABAC filters are written; the human gate for the real model is untouched.
- Before any non-dev deployment, the owner must approve an auth ADR replacing this one (`authorize` hook and identity).

## Alternatives considered
| Option | Why not |
|---|---|
| Stop the run at P0-I4 for an auth decision | Stalls every later increment; the surfaces can be built safely without an auth model |
| Implement OIDC now | An auth model decision outside the delegation |
| No identity at all | Commands need an actor; tests need distinct actors |
