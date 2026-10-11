# ADR-0008 — Owner decisions for Phase 1

Status: accepted
Date: 2026-10-11
Deciders: repository owner (answers to the orchestrator's Phase 1 questions), recorded by the orchestrator
Brief sections: §16 Phase 1, §18 (security), §22 (sync and merge), §27 (schema lifecycle), §9 M1 (derivation), ADR-0005

## Context
Phase 0 stopped at the end of its scope (`docs/reports/STOPPED.md`) and left human gates open (`docs/reports/PHASE-0.md` §6(a)). Before Phase 1 the orchestrator asked the owner for the scope, the auth model, the delegation and the extraction approach. This ADR records the answers so the next run can act on them without asking again.

## Decision
1. **Scope.** The next run builds a new increment, P1-I0 "Authentication and admin", and then P1-I1 to P1-I8 from `docs/build-spec/07-phase1-plan.md`. It stops at the Phase 1 exit. It has no time cap. On a usage limit it waits for the reset and resumes, keeping about 3 agents active at once (L-P0-I8-O1).
2. **Authentication now: username and password.** Microsoft Entra ID (OIDC) comes later. Identity is resolved behind one seam, so Entra can replace the password provider without changing callers.
   - Accounts, password hashing, sessions or tokens, and lockout are the orchestrator's design, recorded in an ADR for the owner's review.
   - Any new dependency must pass the licence gate.
3. **Authorization: an admin module with two roles, `admin` and `user`.** It has no per-scope or per-record ACLs in Phase 1.
   - The admin module manages accounts, roles and agent service tokens. It is reachable from the CLI, API and TUI.
   - ADR-0005 is superseded for production use. The dev-token path may stay for tests.
4. **Seed account `demo` / `demo`.** It exists in dev and demo setups only, created by `just seed` and `tl init --dev`. It is refused when `TL_ENV=prod` or when the server binds a non-loopback address. A startup warning is shown while it exists.
5. **Agents and the simulator.**
   - MCP agents authenticate with service tokens that an admin issues per agent (`agent:<name>`). The propose-only rule (B15) stays.
   - Simulator actors use seeded user accounts with the `user` role.
6. **Delegation.** The orchestrator may approve every Phase 1 human gate under the KICKOFF delegation, recording each in `docs/reports/APPROVALS.md`. These gates are:
   - `schema/modules/**` merges;
   - Commercial clocks and workflows;
   - confidentiality filters and inbound signing;
   - the auth and permission design details.

   Spend is still not delegated (see 8).
7. **Merges follow git.**
   - (a) Schema and module changes are proposed on a branch, diffed and classified like a pull request, and merged with a recorded merge entry. The schema workbench (P1-I8) uses the same branch, diff and merge flow.
   - (b) Record-level merges use a git-like model: imports, conflicting edits and later offline sync are three-way merges against a common base, conflicts are explicit, and the resolution is recorded.
8. **Extraction uses stubs only.** The derivation pipeline (P1-I3) and the AI enricher (P1-I7) extract real file metadata (type, size, hash, page count, title and author properties where the format exposes them) and leave content fields blank. No LLM call and no spend. Extractors stay behind the plugin interface so a real provider can be added later.

## Consequences
- **Contracts changed:**
  - Identity and authorization replace the ADR-0005 stub in P1-I0.
  - The P1-I3 `Extractor` contract returns metadata-only results.
  - The P1-I8 schema workbench and P1-I3 imports follow decision 7.
- **Plans changed:**
  - `docs/build-spec/07-phase1-plan.md` gains Increment 0.
  - `docs/build-spec/KICKOFF.md` scope, delegation and stop conditions are updated.
- **Gates affected:** the Phase 1 human gates in `07-phase1-plan.md` become delegated approvals. Data migrations of existing data and spend remain stop conditions.

## Alternatives considered
| Option | Why not |
|---|---|
| Roles per scope or record type | The owner chose two roles for Phase 1. Finer ACLs can follow Entra groups. |
| AI extraction with a budget | The owner chose stubs only, to avoid spend. |
| Stop at each increment for review | The owner chose an unattended run to the Phase 1 exit. |
