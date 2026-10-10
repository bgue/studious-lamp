# ADR-0006: Dependency licences during the autonomous run

Status: accepted. The owner confirmed the MPL-2.0 allowance (decision 2) on 2026-10-09.
Date: 2026-10-09
Deciders: orchestrator (autonomous run), for owner review
Build spec: 04-gates.md §2 (the row "New dependency with copyleft or unclear licence"), KICKOFF stop conditions

## Context
A copyleft dependency is a human gate, and the KICKOFF delegation of "PyPI dependencies named by tickets" does not cover it.

On 2026-10-09 the orchestrator scanned every installed distribution's licence metadata and found three problems:
- **psycopg 3 (LGPL-3.0).** P0-I5 WS-A proposed it as the Postgres driver. It had not merged.
- **rfc3987 (GPL-3.0+).** It has been on the trunk since P0-I1. `linkml` hard-requires `jsonschema[format]`, and that extra pulls in rfc3987.
- **MPL-2.0 packages, transitive and used unmodified:**
  - `certifi`, through requests and httpx;
  - `tqdm`, through linkml-runtime, curies and pystow;
  - `fqdn`, through jsonschema format checking;
  - `hypothesis`, which is a dev and test dependency only.

## Decision
1. GPL, LGPL and AGPL dependencies are refused, whether direct or transitive. Where the run needs one, it picks a permissive alternative instead of stopping:
   - The Postgres driver is `pg8000` (BSD-3-Clause), used through SQLAlchemy's `postgresql+pg8000` dialect. psycopg is not used.
   - The root `pyproject.toml` overrides `jsonschema[format]` with `jsonschema[format-nongpl]`. jsonschema then validates IRIs with `rfc3987-syntax` (MIT), and rfc3987 is no longer installed. `just check`, `just test` and `just test-tui` stayed green.
2. Accepted (owner confirmed 2026-10-09): MPL-2.0 packages are allowed when they are transitive and unmodified. MPL-2.0 is file-level copyleft. It applies only to the MPL files themselves, and we neither modify nor vendor those files.
   - certifi has no practical replacement in the Python TLS stack.
   - The run continues on this basis. If the owner rejects it, the follow-up is to pin alternatives or vendor a CA bundle.
3. A licence check becomes part of the gates. A script fails `just check` on any GPL, LGPL or AGPL distribution, and on a missing licence. It lists MPL-2.0 packages against an allow-list kept in this ADR. A P0-I5 WS-A ticket builds it.

## Consequences
- Every supervisor must name a new dependency's licence in its relay NOTE, and every APPROVALS.md entry for a dependency states the licence.
- If the owner rejects decision 2, the MPL packages need replacing. That is cheap for fqdn and tqdm. For certifi it means a system CA bundle, which is an ADR-0002 environment change.

## Owner action
Done. The owner replied "Yes continue" to the request to confirm or reject decision 2, on 2026-10-09.
